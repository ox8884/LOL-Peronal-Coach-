"""blitz.gg 라이브 아수라장(Arena 계열) 챔피언별 증강 티어.

blitz.gg 챔피언 페이지가 사용하는 iesdev 데이터 API를 그대로 사용한다.

- 챔피언 증강 티어: ``/query_objects/prod/lol/aram_mayhem_champion?champion_id={id}``
  → ``{증강ID: {"tier": 1..5}}`` (1이 가장 좋음)
- 증강 게임데이터(한글명·등급): ``/static/json/lol/mayham/{patch}/augments_ko_kr``
  → ``rarity`` 숫자 0/1/2 → 실버/골드/프리즘

네트워크 실패 시 ``None`` — 호출부(MayhemCoach)가 패키지 스냅샷으로 폴백한다.
캐시는 BlitzClient 의 공용 디스크 캐시(72h + stale 폴백)를 재사용한다.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from lol_coach.log import get_logger

_log = get_logger("mayhem_live")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_CHAMPIONS_URL = "https://data.v2.iesdev.com/api/v1/query_objects/prod/lol/aram_mayhem_champions"
_CHAMPION_URL = (
    "https://data.v2.iesdev.com/api/v1/query_objects/prod/lol/aram_mayhem_champion"
    "?champion_id={champion_id}"
)
_GAME_DATA_URL = "https://utils.iesdev.com/static/json/lol/mayham/{patch}/augments_ko_kr"
_RARITY_NAMES = {0: "silver", 1: "gold", 2: "prismatic"}


@dataclass(frozen=True, slots=True)
class LiveItem:
    """라이브 아이템 한 항목 (티어 순 정렬본에 담긴다)."""

    item_id: int
    tier: int  # 1(가장 좋음) ~ 5(나쁨)


@dataclass(frozen=True, slots=True)
class LiveAugment:
    """라이브 증강 한 항목."""

    augment_id: int
    name_ko: str
    name_en: str  # 게임 내부 이름 (예: ARAM_ImTheJuggernaut)
    rarity: str  # silver / gold / prismatic
    tier: int  # 1(가장 좋음) ~ 5(나쁨)
    description_ko: str = ""


@dataclass(frozen=True, slots=True)
class LiveMayhemTop:
    """챔피언별 라이브 증강 추천."""

    patch: str
    updated: str  # 데이터 시점 (dt)
    by_rarity: dict[str, tuple[LiveAugment, ...]] = field(default_factory=dict)
    items: tuple[LiveItem, ...] = ()  # 티어 오름차순

    def top(self, rarity: str, n: int = 3) -> tuple[LiveAugment, ...]:
        return self.by_rarity.get(rarity, ())[:n]


def _get_json(client: Any, key: str, url: str) -> dict[str, Any] | None:
    """JSON GET — BlitzClient 공용 캐시(72h + stale 폴백) 재사용."""
    if client is not None:
        try:
            cached = client.cached_get(key)
            if cached is not None:
                return cached
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception as exc:
        _log.debug("라이브 조회 실패 (%s): %s", key, exc)
        if client is not None:
            try:
                stale = client.cached_get(key, allow_stale=True)
                if stale is not None:
                    return stale
            except Exception:
                pass
        return None
    if client is not None:
        try:
            client.cached_set(key, data)
        except Exception:
            pass
    return data


def _current_patch(client: Any) -> str:
    """아수라장 데이터의 현재 패치 (aram_mayhem_champions rows 의 patch 필드)."""
    data = _get_json(client, "mayhem_champions", _CHAMPIONS_URL)
    if isinstance(data, dict):
        rows = data.get("data") or []
        for row in rows:
            if isinstance(row, dict) and row.get("patch"):
                return str(row["patch"])
    return ""


def _game_data(client: Any, patch: str) -> dict[str, dict[str, Any]]:
    """증강 ID → 게임데이터 (한글명·등급). 패치 스코프 캐시."""
    data = _get_json(client, f"mayhem_gamedata:{patch}", _GAME_DATA_URL.format(patch=patch))
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, item in data.items():
        if isinstance(item, dict) and item.get("enabled", True):
            out[str(key)] = item
    return out


def _augment_meta(item: dict[str, Any]) -> tuple[str, str, str, str]:
    """게임데이터 항목 → (한글명, 영문 내부명, 등급, 설명)."""
    name = str(item.get("displayName") or item.get("name") or "").strip()
    name_en = str(item.get("name") or "").strip()
    try:
        rarity = _RARITY_NAMES.get(int(item.get("rarity")), "")
    except (TypeError, ValueError):
        rarity = ""
    desc = str(item.get("description") or "").strip()
    return name, name_en, rarity, desc


def fetch_live_mayhem_top(
    champion_key: str,
    *,
    client: Any = None,
) -> LiveMayhemTop | None:
    """챔피언 숫자 ID(Data Dragon key) → 라이브 증강 TOP.

    실패 시 None (호출부가 패키지 스냅샷으로 폴백).
    """
    champion_key = str(champion_key or "").strip()
    if not champion_key:
        return None
    patch = _current_patch(client)
    if not patch:
        return None
    game = _game_data(client, patch)
    if not game:
        return None

    data = _get_json(
        client,
        f"mayhem_champ:{champion_key}:{patch}",
        _CHAMPION_URL.format(champion_id=champion_key),
    )
    rows = data.get("data") if isinstance(data, dict) else None
    if not rows:
        return None
    row = rows[0] if isinstance(rows, list) else None
    if not isinstance(row, dict):
        return None
    inner = row.get("data") or {}
    tiers = inner.get("augments") if isinstance(inner, dict) else None
    if not isinstance(tiers, dict) or not tiers:
        return None
    updated = str(row.get("dt") or "")
    raw_items = inner.get("items") if isinstance(inner, dict) else None
    live_items: list[LiveItem] = []
    if isinstance(raw_items, dict):
        for raw_id, info in raw_items.items():
            if not isinstance(info, dict):
                continue
            try:
                live_items.append(LiveItem(item_id=int(raw_id), tier=int(info.get("tier"))))
            except (TypeError, ValueError):
                continue
    live_items.sort(key=lambda it: it.tier)

    buckets: dict[str, list[LiveAugment]] = {"silver": [], "gold": [], "prismatic": []}
    for raw_id, info in tiers.items():
        if not isinstance(info, dict):
            continue
        try:
            aid = int(raw_id)
            tier = int(info.get("tier"))
        except (TypeError, ValueError):
            continue
        if tier < 1 or tier > 5:
            continue
        item = game.get(str(aid)) or game.get(aid)
        if item is None:
            continue
        name, name_en, rarity, desc = _augment_meta(item)
        if not name or not rarity:
            continue
        buckets[rarity].append(LiveAugment(aid, name, name_en, rarity, tier, desc))

    if not any(buckets.values()):
        return None
    by_rarity = {
        rarity: tuple(sorted(augs, key=lambda a: a.tier)) for rarity, augs in buckets.items()
    }
    return LiveMayhemTop(
        patch=patch, updated=updated, by_rarity=by_rarity, items=tuple(live_items)
    )
