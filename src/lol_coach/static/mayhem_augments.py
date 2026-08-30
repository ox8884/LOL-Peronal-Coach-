"""아수라장(Arena 계열) 증강 메타데이터 — ID → 한글 이름·등급·아이콘.

LCU 경기 상세의 ``stats.playerAugment1~6`` 은 숫자 ID만 담고 있다.
CommunityDragon 의 ``cherry-augments.json`` (ko_kr) 이 ID → 한글 이름 /
등급 / 아이콘 에셋 경로를 제공하며, 아이콘은 롤 클라이언트(LCU)의
``/lol-game-data/assets/...`` 에서 바이너리로 받아 디스크 캐시한다.

- 카탈로그/아이콘은 모두 캐시 우선. 네트워크·클라이언트 실패 시 조용히
  기능 생략 (복기 카드는 이름만으로, 카탈로그까지 없으면 섹션 숨김).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lol_coach.log import get_logger

_log = get_logger("augments")

_CDRAGON_URL = (
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
    "global/ko_kr/v1/cherry-augments.json"
)
_CATALOG_TTL_S = 7 * 24 * 3600  # 패치마다 바뀔 수 있으나 7일 캐시면 충분

# LCU rarity → 화면 등급 키
_RARITY_MAP = {
    "kSilver": "silver",
    "kGold": "gold",
    "kPrismatic": "prismatic",
}


@dataclass(frozen=True)
class AugmentMeta:
    """단일 증강 메타데이터."""

    id: int
    name: str  # 한글 표시명 (예: "마법 미사일")
    rarity: str  # silver / gold / prismatic / ""
    icon_path: str  # LCU 에셋 경로 (예: /lol-game-data/assets/ASSETS/...)


_mem_catalog: dict[int, AugmentMeta] | None = None


def _catalog_file() -> Path:
    from lol_coach.config import cache_root

    return cache_root() / "augments" / "cherry_augments.json"


def _fetch_catalog_file() -> bool:
    """CDragon에서 카탈로그 내려받아 캐시에 저장. 성공 여부 반환."""
    import requests

    dest = _catalog_file()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(_CDRAGON_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return False
        dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as exc:
        _log.debug("증강 카탈로그 다운로드 실패(무시): %s", exc)
        return False


def _parse_catalog(raw: list[dict[str, Any]]) -> dict[int, AugmentMeta]:
    out: dict[int, AugmentMeta] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            aid = int(item.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if not aid:
            continue
        name = str(item.get("nameTRA") or item.get("simpleNameTRA") or "").strip()
        if not name:
            continue
        out[aid] = AugmentMeta(
            id=aid,
            name=name,
            rarity=_RARITY_MAP.get(str(item.get("rarity") or ""), ""),
            icon_path=str(item.get("augmentSmallIconPath") or ""),
        )
    return out


def load_catalog(*, force: bool = False) -> dict[int, AugmentMeta]:
    """증강 ID 메타데이터 로드 (파일 캐시 → 만료 시 CDragon 재다운로드)."""
    global _mem_catalog
    if _mem_catalog is not None and not force:
        return _mem_catalog
    path = _catalog_file()
    stale = True
    if path.is_file():
        try:
            stale = (time.time() - path.stat().st_mtime) > _CATALOG_TTL_S
        except OSError:
            stale = True
    if (stale or force) and not _fetch_catalog_file() and not path.is_file():
        _mem_catalog = {}
        return _mem_catalog
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _mem_catalog = _parse_catalog(raw if isinstance(raw, list) else [])
    except Exception as exc:
        _log.debug("증강 카탈로그 파싱 실패(무시): %s", exc)
        _mem_catalog = {}
    return _mem_catalog


def augment_meta(augment_id: int) -> AugmentMeta | None:
    """ID → 메타데이터. 카탈로그 없으면 None."""
    return load_catalog().get(int(augment_id))


def resolve_display(
    augment_ids: list[int] | None = None,
    augment_names: list[str] | None = None,
) -> list[AugmentMeta]:
    """MatchSummary의 증강 필드 → 표시 목록.

    - augment_ids(LCU): 카탈로그에서 한글 이름·등급 조회 (없으면 제외)
    - augment_names(Match-V5 영문 이름): 등급 없이 이름만 표시
    """
    out: list[AugmentMeta] = []
    for aid in augment_ids or []:
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            continue
        if aid <= 0:
            continue
        meta = augment_meta(aid)
        if meta is not None:
            out.append(meta)
    for name in augment_names or []:
        name = str(name).strip()
        if name:
            out.append(AugmentMeta(id=0, name=name, rarity="", icon_path=""))
    return out


def icon_bytes_for(meta: AugmentMeta, lcu: Any = None) -> bytes | None:
    """증강 아이콘 바이너리 (디스크 캐시 → LCU 에셋). 클라이언트 없으면 None."""
    if not meta.icon_path:
        return None
    from lol_coach.config import cache_root

    cache = cache_root() / "icons" / f"aug_{meta.id}.png"
    if cache.is_file() and cache.stat().st_size > 0:
        try:
            return cache.read_bytes()
        except OSError:
            return None
    if lcu is None:
        return None
    try:
        raw = lcu._get_raw(meta.icon_path)
    except Exception as exc:
        _log.debug("증강 아이콘 조회 실패(무시): %s", exc)
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    except OSError:
        pass
    return raw
