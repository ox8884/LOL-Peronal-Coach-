"""blitz.gg SR 메타 클라이언트 — fetch + 메모리/디스크 캐시 + stale 폴백.

u.gg 의존 제거 후 SR 빌드/카운터 데이터는 전부 blitz.gg 단일 소스.
캐시 설계는 기존 UGGClient 패턴을 그대로 승계한다 (disk_ttl 72h, 네트워크
실패 시 TTL 지난 캐시 폴백).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

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
        "starting_items": {
            "label": build.starting_items.label,
            "items": build.starting_items.items,
            "win_rate": build.starting_items.win_rate,
            "matches": build.starting_items.matches,
        },
        "core_items": {
            "label": build.core_items.label,
            "items": build.core_items.items,
            "win_rate": build.core_items.win_rate,
            "matches": build.core_items.matches,
        },
        "boots": {
            "label": build.boots.label,
            "items": build.boots.items,
            "win_rate": build.boots.win_rate,
            "matches": build.boots.matches,
        },
        "situational": [
            {"label": s.label, "items": s.items} for s in build.situational
        ],
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
    )


def _build_from_dict(data: Any) -> ChampionBuild | None:
    """직렬화된 dict → ChampionBuild (손상 시 None)."""
    if not isinstance(data, dict):
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
                secondary_runes=[
                    str(x) for x in (runes_raw.get("secondary_runes") or [])
                ],
                shards=[str(x) for x in (runes_raw.get("shards") or [])],
                win_rate=runes_raw.get("win_rate"),
                matches=runes_raw.get("matches"),
            ),
            skills=SkillBuild(
                priority=[str(x) for x in (skills_raw.get("priority") or [])],
                order_by_level=[
                    str(x) for x in (skills_raw.get("order_by_level") or [])
                ],
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
            f"{_BASE}/champions/{champion_slug(enemy)}/counters"
            f"?role={normalize_role(role).upper()}"
        )

    # ── 네트워크 ──

    def fetch_html(self, url: str) -> str:
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            raise BlitzError(f"blitz.gg 접속 실패: {exc}") from exc
        if len(html) < 30000:
            raise BlitzError("blitz.gg 응답이 비어 있습니다 (차단/구조 변경 가능)")
        return html

    # ── 공용 캐시 ──

    def _cache_get(self, key: str) -> Any | None:
        hit = self._cache.get(key)
        if hit is None:
            return None
        ts, val = hit
        if time.time() - ts > self.cache_ttl:
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
        except Exception:
            stale = self.cached_get(key, allow_stale=True)
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

    def get_counters(
        self,
        enemy: str,
        role: str = "mid",
        limit: int = 10,
        min_matches: int = 800,
    ) -> CounterReport:
        url = self.counters_url(enemy, role)
        key = f"counters:{champion_slug(enemy)}:{normalize_role(role)}"
        cached = self.cached_get(key)
        if cached is not None:
            try:
                return report_from_dict(cached)
            except BlitzError:
                pass
        try:
            html = self.fetch_html(url)
            report = parse_counters_html(
                html,
                enemy=enemy,
                role=normalize_role(role),
                source_url=url,
                min_matches=min_matches,
            )
        except BlitzError:
            stale = self.cached_get(key, allow_stale=True)
            if stale is not None:
                try:
                    return report_from_dict(stale)
                except BlitzError:
                    pass
            raise
        self.cached_set(key, report_to_dict(report))
        return report

    # ── 패치 ──

    def get_current_patch(self, sample_champion: str = "Ahri") -> str:
        return self.get_champion_build(sample_champion).patch
