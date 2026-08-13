"""blitz.gg SR 메타 클라이언트 — fetch + 메모리/디스크 캐시 + stale 폴백.

SR 빌드/카운터 데이터는 blitz.gg 단일 소스이며, 캐시는 72시간 디스크
보존과 네트워크 실패 시 stale 폴백을 사용합니다.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import cloudscraper

from lol_coach.blitz.models import (
    BlitzError,
    BuildSection,
    ChampionBuild,
    CounterReport,
    RunePage,
    SkillBuild,
    report_from_dict,
    report_to_dict,
)
from lol_coach.blitz.parser import (
    champion_slug,
    normalize_role,
    parse_build_html,
    parse_counters_html,
)

_BASE = "https://blitz.gg/lol"
_ALLOWED_BLITZ_HOSTS = frozenset({"blitz.gg", "www.blitz.gg"})
_MAX_REDIRECTS = 3
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MIN_RESPONSE_BYTES = 30_000


def _section_to_dict(section: BuildSection) -> dict:
    return {
        "label": section.label,
        "items": section.items,
        "win_rate": section.win_rate,
        "matches": section.matches,
        "note": section.note,
    }


def _build_to_dict(build: ChampionBuild) -> dict:
    return {
        "champion": build.champion,
        "role": build.role,
        "patch": build.patch,
        "tier": build.tier,
        "win_rate": build.win_rate,
        "pick_rate": build.pick_rate,
        "ban_rate": build.ban_rate,
        "matches": build.matches,
        "rank_filter": build.rank_filter,
        "source_url": build.source_url,
        "mode": build.mode,
        "runes": {
            "primary_tree": build.runes.primary_tree,
            "secondary_tree": build.runes.secondary_tree,
            "keystone": build.runes.keystone,
            "primary_runes": build.runes.primary_runes,
            "secondary_runes": build.runes.secondary_runes,
            "shards": build.runes.shards,
            "win_rate": build.runes.win_rate,
            "matches": build.runes.matches,
        },
        "skills": {
            "priority": build.skills.priority,
            "order_by_level": build.skills.order_by_level,
            "win_rate": build.skills.win_rate,
            "matches": build.skills.matches,
        },
        "summoner_spells": build.summoner_spells,
        "summoner_spells_wr": build.summoner_spells_wr,
        "starting_items": _section_to_dict(build.starting_items),
        "core_items": _section_to_dict(build.core_items),
        "boots": _section_to_dict(build.boots),
        "situational": [_section_to_dict(s) for s in build.situational],
        "raw_notes": build.raw_notes,
    }


def _section_from_dict(v: Any, label: str) -> BuildSection:
    if not isinstance(v, dict):
        return BuildSection(label=label)
    return BuildSection(
        label=str(v.get("label") or label),
        items=[str(x) for x in (v.get("items") or [])],
        win_rate=v.get("win_rate"),
        matches=v.get("matches"),
        note=str(v.get("note") or ""),
    )


def _build_from_dict(data: Any) -> ChampionBuild | None:
    """직렬화된 dict → ChampionBuild (손상 시 None)."""
    if not isinstance(data, dict):
        return None
    if any(not str(data.get(field) or "").strip() for field in ("champion", "role", "patch")):
        return None
    try:
        runes_raw = data.get("runes") or {}
        skills_raw = data.get("skills") or {}
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
            runes=RunePage(
                primary_tree=str(runes_raw.get("primary_tree") or ""),
                secondary_tree=str(runes_raw.get("secondary_tree") or ""),
                keystone=str(runes_raw.get("keystone") or ""),
                primary_runes=[str(x) for x in (runes_raw.get("primary_runes") or [])],
                secondary_runes=[str(x) for x in (runes_raw.get("secondary_runes") or [])],
                shards=[str(x) for x in (runes_raw.get("shards") or [])],
                win_rate=runes_raw.get("win_rate"),
                matches=runes_raw.get("matches"),
            ),
            skills=SkillBuild(
                priority=[str(x) for x in (skills_raw.get("priority") or [])],
                order_by_level=[str(x) for x in (skills_raw.get("order_by_level") or [])],
                win_rate=skills_raw.get("win_rate"),
                matches=skills_raw.get("matches"),
            ),
            summoner_spells=[str(x) for x in (data.get("summoner_spells") or [])],
            summoner_spells_wr=data.get("summoner_spells_wr"),
            starting_items=_section_from_dict(data.get("starting_items"), "Starting Items"),
            core_items=_section_from_dict(data.get("core_items"), "Core Items"),
            boots=_section_from_dict(data.get("boots"), "Boots"),
            situational=[
                _section_from_dict(x, str(x.get("label") or "Situational"))
                for x in (data.get("situational") or [])
                if isinstance(x, dict)
            ],
            raw_notes=[str(x) for x in (data.get("raw_notes") or [])],
        )
        if not build.champion:
            return None
        return build
    except Exception:
        return None


class BlitzClient:
    """blitz.gg 빌드/카운터 조회 — 메모리(5분)+디스크(72h) 캐시, stale 폴백."""

    def __init__(
        self,
        timeout: float = 30.0,
        cache_ttl: float = 300.0,
        disk_ttl: float = 72 * 3600.0,
    ) -> None:
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.disk_ttl = disk_ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._session = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        self._disk_dir: Path | None = None
        try:
            from lol_coach.config import cache_root

            self._disk_dir = cache_root() / "blitz"
            self._disk_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # ── URL ──

    def build_url(self, champion: str, role: str = "mid") -> str:
        url = f"{_BASE}/champions/{champion_slug(champion)}/build"
        if role:
            url += f"?role={normalize_role(role).upper()}"
        return url

    def counters_url(self, enemy: str, role: str = "mid") -> str:
        return (
            f"{_BASE}/champions/{champion_slug(enemy)}/counters?role={normalize_role(role).upper()}"
        )

    # ── 네트워크 ──

    @staticmethod
    def _validate_blitz_url(url: str) -> None:
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise BlitzError("blitz.gg 주소가 올바르지 않습니다.") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _ALLOWED_BLITZ_HOSTS
            or parsed.username
            or parsed.password
            or port not in (None, 443)
        ):
            raise BlitzError("blitz.gg 주소만 허용됩니다.")

    @classmethod
    def _redirect_target(cls, current_url: str, location: str) -> str:
        if not location.strip():
            raise BlitzError("blitz.gg 리디렉션 주소가 비어 있습니다.")
        target = urljoin(current_url, location)
        cls._validate_blitz_url(target)
        return target

    @staticmethod
    def _response_html(resp: Any) -> str:
        headers = getattr(resp, "headers", {}) or {}
        content_length = headers.get("Content-Length")
        try:
            if content_length is not None and int(content_length) > _MAX_RESPONSE_BYTES:
                raise BlitzError("blitz.gg 응답이 너무 큽니다.")
        except (TypeError, ValueError) as exc:
            raise BlitzError("blitz.gg 응답 크기를 확인할 수 없습니다.") from exc

        chunks: list[bytes] = []
        total = 0
        iterator = getattr(resp, "iter_content", None)
        if callable(iterator):
            for chunk in iterator(chunk_size=64 * 1024):
                if not chunk:
                    continue
                raw = chunk.encode() if isinstance(chunk, str) else bytes(chunk)
                total += len(raw)
                if total > _MAX_RESPONSE_BYTES:
                    raise BlitzError("blitz.gg 응답이 너무 큽니다.")
                chunks.append(raw)
            encoding = getattr(resp, "encoding", None) or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace")

        text = str(getattr(resp, "text", ""))
        if len(text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise BlitzError("blitz.gg 응답이 너무 큽니다.")
        return text

    def fetch_html(self, url: str) -> str:
        current_url = url
        for _ in range(_MAX_REDIRECTS + 1):
            self._validate_blitz_url(current_url)
            resp = None
            try:
                resp = self._session.get(
                    current_url,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=False,
                )
                status = int(getattr(resp, "status_code", 0) or 0)
                if status in {301, 302, 303, 307, 308}:
                    location = str((getattr(resp, "headers", {}) or {}).get("Location") or "")
                    current_url = self._redirect_target(current_url, location)
                    continue
                resp.raise_for_status()
                html = self._response_html(resp)
            except BlitzError:
                raise
            except Exception as exc:
                raise BlitzError("blitz.gg 접속에 실패했습니다.") from exc
            finally:
                if resp is not None:
                    close = getattr(resp, "close", None)
                    if callable(close):
                        close()
            if len(html.encode("utf-8")) < _MIN_RESPONSE_BYTES:
                raise BlitzError("blitz.gg 응답이 비어 있습니다 (차단/구조 변경 가능)")
            return html
        raise BlitzError("blitz.gg 리디렉션이 너무 많습니다.")

    # ── 공용 캐시 ──

    def _cache_get(self, key: str) -> Any | None:
        hit = self._cache.get(key)
        if hit is None:
            return None
        ts, val = hit
        if time.time() - ts > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key: str, val: Any) -> None:
        self._cache[key] = (time.time(), val)

    def _disk_cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", key)
        return (self._disk_dir or Path("cache") / "blitz") / f"{safe}.json"

    def _disk_read(self, key: str, *, allow_stale: bool = False) -> dict | None:
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
        try:
            path = self._disk_cache_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def cached_get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        data = self._disk_read(key, allow_stale=allow_stale)
        if data is not None:
            payload = data.get("payload")
            if payload is not None:
                age = time.time() - float(data.get("ts") or 0)
                if age <= self.disk_ttl:
                    self._cache_set(key, payload)
            return payload
        return None

    def cached_set(self, key: str, payload: Any) -> None:
        self._cache_set(key, payload)
        self._disk_write(key, {"ts": time.time(), "payload": payload})

    # ── SR 빌드 ──

    def get_champion_build(
        self,
        champion: str,
        role: str = "mid",
        use_cache: bool = True,
    ) -> ChampionBuild:
        url = self.build_url(champion, role)
        key = f"build:{champion_slug(champion)}:{normalize_role(role)}"
        if use_cache:
            cached = self.cached_get(key)
            if cached is not None:
                build = _build_from_dict(cached)
                if build is not None:
                    return build
        try:
            html = self.fetch_html(url)
            build = parse_build_html(
                html, champion=champion, role=normalize_role(role), source_url=url
            )
        except BlitzError:
            stale = self.cached_get(key, allow_stale=True) if use_cache else None
            if stale is not None:
                build = _build_from_dict(stale)
                if build is not None:
                    build.stale_cache = True
                    raw = self._disk_read(key, allow_stale=True) or {}
                    build.cache_age_s = time.time() - float(raw.get("ts") or 0)
                    return build
            raise
        if use_cache:
            self.cached_set(key, _build_to_dict(build))
        return build

    # ── 카운터 ──

    @staticmethod
    def _filter_counter_report(
        report: CounterReport,
        *,
        limit: int,
        min_matches: int,
    ) -> CounterReport:
        if limit < 1 or min_matches < 0:
            raise BlitzError("카운터 조회 옵션이 올바르지 않습니다.")
        lane = [p for p in report.lane_counters if p.matches >= min_matches]
        hard = [p for p in report.hard_matchups if p.matches >= min_matches]
        return CounterReport(
            enemy=report.enemy,
            role=report.role,
            patch=report.patch,
            source_url=report.source_url,
            lane_counters=lane[:limit],
            hard_matchups=hard[: min(limit, 5)],
            stale_cache=report.stale_cache,
            cache_age_s=report.cache_age_s,
        )

    def _counter_cache_age(self, key: str) -> float:
        data = self._disk_read(key, allow_stale=True)
        if data is None:
            return 0.0
        return max(0.0, time.time() - float(data.get("ts") or 0))

    def get_counters(
        self,
        enemy: str,
        role: str = "mid",
        limit: int = 10,
        min_matches: int = 800,
        use_cache: bool = True,
    ) -> CounterReport:
        url = self.counters_url(enemy, role)
        normalized_role = normalize_role(role)
        key = f"counters:v2:{champion_slug(enemy)}:{normalized_role}"
        legacy_key = f"counters:{champion_slug(enemy)}:{normalized_role}"
        if use_cache:
            for cache_key in (key, legacy_key):
                cached = self.cached_get(cache_key)
                if cached is None:
                    continue
                try:
                    report = report_from_dict(cached)
                    return self._filter_counter_report(report, limit=limit, min_matches=min_matches)
                except BlitzError:
                    continue
        try:
            html = self.fetch_html(url)
            report = parse_counters_html(
                html,
                enemy=enemy,
                role=normalized_role,
                source_url=url,
                min_matches=0,
            )
        except BlitzError:
            if use_cache:
                for cache_key in (key, legacy_key):
                    stale = self.cached_get(cache_key, allow_stale=True)
                    if stale is None:
                        continue
                    try:
                        stale_report = report_from_dict(stale)
                        stale_report.stale_cache = True
                        stale_report.cache_age_s = self._counter_cache_age(cache_key)
                        return self._filter_counter_report(
                            stale_report, limit=limit, min_matches=min_matches
                        )
                    except BlitzError:
                        continue
            raise
        if use_cache:
            self.cached_set(key, report_to_dict(report))
        return self._filter_counter_report(report, limit=limit, min_matches=min_matches)

    # ── 패치 ──

    def get_current_patch(self, sample_champion: str = "Ahri") -> str:
        return self.get_champion_build(sample_champion).patch
