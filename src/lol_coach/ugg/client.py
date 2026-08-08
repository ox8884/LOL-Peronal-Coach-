"""Fetch live champion meta builds from u.gg (current patch)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from lol_coach.modes import MODE_ARAM, MODE_SUMMONERS_RIFT, normalize_mode
from lol_coach.ugg.models import BuildSection, ChampionBuild, RunePage, SkillBuild
from lol_coach.ugg.parser import parse_champion_build_html


def _build_to_dict(build: ChampionBuild) -> dict:
    """ChampionBuild → 직렬화 가능 dict (중첩 dataclass 포함)."""

    def _conv(v: Any) -> Any:
        if is_dataclass(v):
            return {k: _conv(x) for k, x in asdict(v).items()}
        if isinstance(v, list):
            return [_conv(x) for x in v]
        return v

    return _conv(build)


def _build_from_dict(data: Any) -> ChampionBuild | None:
    """직렬화된 dict → ChampionBuild (필드 누락/형식 오류는 None)."""
    if not isinstance(data, dict):
        return None
    try:
        runes = RunePage(**{k: v for k, v in (data.get("runes") or {}).items()})
        skills = SkillBuild(**{k: v for k, v in (data.get("skills") or {}).items()})

        def _section(v: Any, label: str) -> BuildSection:
            if not isinstance(v, dict):
                return BuildSection(label=label)
            return BuildSection(**{k: val for k, val in v.items()})

        situational = [
            _section(x, str(x.get("label") or "Situational"))
            for x in (data.get("situational") or [])
            if isinstance(x, dict)
        ]
        build = ChampionBuild(
            champion=str(data.get("champion") or ""),
            role=str(data.get("role") or ""),
            patch=str(data.get("patch") or ""),
            tier=str(data.get("tier") or ""),
            win_rate=data.get("win_rate"),
            pick_rate=data.get("pick_rate"),
            ban_rate=data.get("ban_rate"),
            matches=data.get("matches"),
            rank_filter=str(data.get("rank_filter") or "Emerald+"),
            source_url=str(data.get("source_url") or ""),
            mode=str(data.get("mode") or "summoners_rift"),
            runes=runes,
            skills=skills,
            summoner_spells=list(data.get("summoner_spells") or []),
            summoner_spells_wr=data.get("summoner_spells_wr"),
            starting_items=_section(data.get("starting_items"), "Starting Items"),
            core_items=_section(data.get("core_items"), "Core Items"),
            boots=_section(data.get("boots"), "Boots"),
            situational=situational,
            raw_notes=list(data.get("raw_notes") or []),
        )
        if not build.champion or not build.patch:
            return None
        return build
    except Exception:
        return None

# u.gg role path segments
ROLE_SLUGS = {
    "top": "top",
    "jungle": "jungle",
    "jg": "jungle",
    "mid": "mid",
    "middle": "mid",
    "adc": "adc",
    "bottom": "adc",
    "bot": "adc",
    "support": "support",
    "supp": "support",
    "utility": "support",
}

ROLE_DISPLAY = {
    "top": "TOP",
    "jungle": "JUNGLE",
    "mid": "MIDDLE",
    "adc": "BOTTOM",
    "support": "UTILITY",
}


class UGGError(Exception):
    pass


def normalize_role(role: str) -> str:
    key = role.strip().lower()
    if key not in ROLE_SLUGS:
        raise UGGError(
            f"알 수 없는 포지션 '{role}'. 사용: top, jungle, mid, adc, support"
        )
    return ROLE_SLUGS[key]


def champion_slug(name: str) -> str:
    """Convert champion name/key to u.gg URL slug."""
    s = name.strip().lower()
    s = s.replace("'", "").replace(".", "").replace(" ", "")
    s = re.sub(r"[^a-z0-9]", "", s)
    # u.gg special cases
    specials = {
        "wukong": "monkeyking",
        "monkeyking": "monkeyking",
        "renataglasc": "renata",
        "nunuwillump": "nunu",
        "nunu&willump": "nunu",
        "jarvaniv": "jarvaniv",
        "leesin": "leesin",
        "masteryi": "masteryi",
        "missfortune": "missfortune",
        "twistedfate": "twistedfate",
        "xinzhao": "xinzhao",
        "drmundo": "drmundo",
        "tahmkench": "tahmkench",
        "belveth": "belveth",
        "ksante": "ksante",
        "kogmaw": "kogmaw",
        "reksai": "reksai",
        "cho'gath": "chogath",
        "chogath": "chogath",
        "kai'sa": "kaisa",
        "kaisa": "kaisa",
        "kha'zix": "khazix",
        "khazix": "khazix",
        "vel'koz": "velkoz",
        "velkoz": "velkoz",
    }
    return specials.get(s, s)


class UGGClient:
    """
    Live meta client for u.gg.

    Primary strategy: cloudscraper → champion build HTML → BeautifulSoup parse.
    Secondary: GraphQL getRecommendation (best-effort; param space is unstable).
    """

    BASE = "https://u.gg"
    API = "https://u.gg/api"

    def __init__(
        self,
        timeout: float = 30.0,
        cache_ttl: float = 300.0,
        disk_ttl: float = 72 * 3600.0,
    ):
        self.timeout = timeout
        self.cache_ttl = cache_ttl  # 메모리 캐시
        self.disk_ttl = disk_ttl  # 디스크 영속 캐시 (재시작/Cloudflare 대비)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._session = None
        self._disk_dir: Path | None = None

    def _get_session(self):
        if self._session is not None:
            return self._session
        try:
            import cloudscraper

            self._session = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "mobile": False,
                }
            )
        except Exception:
            import requests

            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
        return self._session

    def _cache_get(self, key: str) -> Any | None:
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key: str, val: Any) -> None:
        self._cache[key] = (time.time(), val)

    # ── 디스크 영속 캐시 (재시작/Cloudflare 차단 시에도 마지막 빌드 유지) ──

    def _cache_base_dir(self) -> Path:
        if self._disk_dir is not None:
            return self._disk_dir
        try:
            from lol_coach.config import cache_root

            self._disk_dir = cache_root() / "ugg"
        except Exception:
            self._disk_dir = Path.cwd() / "cache" / "ugg"
        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return self._disk_dir

    def _disk_cache_path(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
        return self._cache_base_dir() / f"{safe}.json"

    def _disk_read(self, key: str, *, allow_stale: bool = False) -> dict | None:
        """디스크 캐시 원본 dict 조회 (ts 포함) — 제네릭, 없으면 None."""
        try:
            path = self._disk_cache_path(key)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            age = time.time() - float(data.get("ts", 0))
            if age > self.disk_ttl and not allow_stale:
                return None
            return data
        except Exception:
            return None

    def _disk_write(self, key: str, payload: dict) -> None:
        """디스크 캐시 저장 (제네릭)."""
        try:
            path = self._disk_cache_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def _disk_cache_get(
        self, key: str, *, allow_stale: bool = False
    ) -> Any | None:
        """디스크 영속 캐시 조회 — ChampionBuild (네트워크 실패 폴백 포함)."""
        data = self._disk_read(key, allow_stale=allow_stale)
        if data is None:
            return None
        build = _build_from_dict(data.get("build"))
        if build is not None:
            age = time.time() - float(data.get("ts") or 0)
            if age > self.disk_ttl:
                # 호출부가 배너 표시할 수 있도록 속성 표시
                build.stale_cache = True
                build.cache_age_s = age
        return build

    def _disk_cache_set(self, key: str, build: ChampionBuild) -> None:
        """디스크 영속 캐시 저장 (ChampionBuild)."""
        self._disk_write(key, {"ts": time.time(), "build": _build_to_dict(build)})

    # ── 공용 캐시 (CounterReport 등 JSON 직렬화 가능 payload) ──

    def cached_get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        """메모리 → 디스크 순 공용 캐시 조회 (payload 반환, 없으면 None)."""
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        data = self._disk_read(key, allow_stale=allow_stale)
        if data is not None:
            payload = data.get("payload")
            if payload is not None:
                self._cache_set(key, payload)
            return payload
        return None

    def cached_set(self, key: str, payload: Any) -> None:
        """공용 캐시 저장 — payload는 JSON 직렬화 가능해야 한다."""
        self._cache_set(key, payload)
        self._disk_write(key, {"ts": time.time(), "payload": payload})

    def _cache_put_both(self, key: str, build: ChampionBuild) -> None:
        """메모리 + 디스크 캐시에 저장."""
        self._cache_set(key, build)
        self._disk_cache_set(key, build)

    def build_url(
        self,
        champion: str,
        role: str | None = None,
        mode: str = MODE_SUMMONERS_RIFT,
    ) -> str:
        slug = champion_slug(champion)
        try:
            mode_n = normalize_mode(mode)
        except ValueError as exc:
            raise UGGError(str(exc)) from exc

        if mode_n == MODE_ARAM:
            # Live ARAM build pages: /lol/champions/aram/{slug}-aram
            # (covers classic ARAM meta used as closest public build source
            #  for ARAM Mayhem coaching when Mayhem-only pages are absent)
            return f"{self.BASE}/lol/champions/aram/{quote(slug)}-aram"

        if role:
            r = normalize_role(role)
            return f"{self.BASE}/lol/champions/{quote(slug)}/build/{r}"
        return f"{self.BASE}/lol/champions/{quote(slug)}/build"

    def fetch_html(self, url: str) -> str:
        session = self._get_session()
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://u.gg/lol/tier-list",
        }
        resp = session.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise UGGError(
                f"u.gg HTTP {resp.status_code} for {url}. "
                "Cloudflare may be blocking this network."
            )
        text = resp.text
        if "Just a moment" in text and "cloudflare" in text.lower():
            raise UGGError(
                "u.gg blocked by Cloudflare challenge. "
                "Try again later or use a different network."
            )
        if "Page Not Found" in text and len(text) < 200000:
            raise UGGError(f"u.gg page not found: {url}")
        if len(text) < 5000:
            raise UGGError(f"u.gg returned suspiciously small page ({len(text)} bytes)")
        return text

    def get_champion_build(
        self,
        champion: str,
        role: str = "mid",
        mode: str = MODE_SUMMONERS_RIFT,
        use_cache: bool = True,
    ) -> ChampionBuild:
        """
        Fetch current-patch recommended build from u.gg.

        Args:
            champion: Name or key (e.g. 'Ahri', 'miss fortune')
            role: top | jungle | mid | adc | support (SR only)
            mode: summoners_rift | aram  (aram uses ARAM / Mayhem-oriented page)
            use_cache: cache responses for cache_ttl seconds
        """
        try:
            mode_n = normalize_mode(mode)
        except ValueError as exc:
            raise UGGError(str(exc)) from exc

        role_slug = ""
        if mode_n == MODE_SUMMONERS_RIFT:
            role_slug = normalize_role(role)

        cache_key = f"build:{champion_slug(champion)}:{mode_n}:{role_slug or 'aram'}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
            # 메모리 미스 → 디스크 캐시 (재시작/일시 차단 복구)
            disk = self._disk_cache_get(cache_key)
            if disk is not None:
                self._cache_set(cache_key, disk)
                return disk

        url = self.build_url(champion, role_slug or None, mode=mode_n)
        try:
            html = self.fetch_html(url)

            if mode_n == MODE_ARAM:
                role_display = "ARAM"
            else:
                role_display = ROLE_DISPLAY.get(role_slug, role_slug.upper())

            build = parse_champion_build_html(
                html,
                champion=champion,
                role=role_display,
                source_url=url,
            )
            build.mode = mode_n
            if mode_n == MODE_ARAM:
                build.rank_filter = "ARAM (all ranks)"
                if not build.raw_notes:
                    build.raw_notes = []
                build.raw_notes.append(
                    "u.gg 칼바람 빌드 페이지 기준입니다. "
                    "아수라장(큐 2400) 개인 전적은 따로 매칭합니다."
                )

            # SR fallback: role page empty → default build page
            if mode_n == MODE_SUMMONERS_RIFT and build.win_rate is None and role_slug:
                try:
                    html2 = self.fetch_html(
                        self.build_url(champion, None, mode=MODE_SUMMONERS_RIFT)
                    )
                    build2 = parse_champion_build_html(
                        html2,
                        champion=champion,
                        role=role_display,
                        source_url=self.build_url(
                            champion, None, mode=MODE_SUMMONERS_RIFT
                        ),
                    )
                    build2.mode = mode_n
                    if build2.win_rate is not None:
                        build = build2
                except UGGError:
                    pass

            # ARAM fallback: try queueType query param page
            if mode_n == MODE_ARAM and build.win_rate is None:
                try:
                    alt = (
                        f"{self.BASE}/lol/champions/{quote(champion_slug(champion))}"
                        f"/build?queueType=normal_aram"
                    )
                    html3 = self.fetch_html(alt)
                    build3 = parse_champion_build_html(
                        html3, champion=champion, role="ARAM", source_url=alt
                    )
                    build3.mode = MODE_ARAM
                    build3.rank_filter = "ARAM (all ranks)"
                    if build3.win_rate is not None:
                        build = build3
                except UGGError:
                    pass

            self._cache_put_both(cache_key, build)
            return build
        except Exception as exc:
            # 네트워크/Cloudflare 실패 시 TTL 지난 디스크 캐시라도 사용
            if use_cache:
                stale = self._disk_cache_get(cache_key, allow_stale=True)
                if stale is not None:
                    self._cache_set(cache_key, stale)
                    return stale
            if isinstance(exc, UGGError):
                raise
            raise UGGError(str(exc)) from exc

    def get_current_patch(self, sample_champion: str = "Ahri") -> str:
        """Detect the patch string currently shown on u.gg."""
        cache_key = "patch"
        cached = self._cache_get(cache_key)
        if cached:
            return cached
        build = self.get_champion_build(sample_champion, "mid")
        self._cache_set(cache_key, build.patch)
        return build.patch

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        """Low-level GraphQL helper (best-effort)."""
        session = self._get_session()
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://u.gg",
            "Referer": "https://u.gg/",
        }
        resp = session.post(
            self.API, json=payload, headers=headers, timeout=self.timeout
        )
        if resp.status_code != 200:
            raise UGGError(f"GraphQL HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if data.get("errors"):
            raise UGGError(f"GraphQL errors: {data['errors']}")
        return data.get("data") or {}
