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
import os
import tempfile
import threading
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
_catalog_lock = threading.Lock()
_fail_at = 0.0  # 마지막 로드 실패 시각 — 실패를 세션 내내 메모이즈하지 않고 재시도
_RETRY_S = 120


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
        # 임시 파일 → 교체 (쓰기 중 종료로 mtime 만 새로운 깨진 파일이 7일 남지 않게)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False))
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
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
    """증강 ID 메타데이터 로드 (파일 캐시 → 만료 시 CDragon 재다운로드).

    빈 결과(오프라인 첫 실행)는 메모이즈하지 않고 _RETRY_S 뒤 다시 시도한다.
    """
    global _mem_catalog, _fail_at
    if _mem_catalog and not force:
        return _mem_catalog
    if not force and time.time() - _fail_at < _RETRY_S:
        return {}
    with _catalog_lock:  # 동시 첫 호출이 15초 다운로드를 중복하지 않게
        if _mem_catalog and not force:
            return _mem_catalog
        catalog = _load_catalog_unlocked(force)
        if catalog:
            _mem_catalog = catalog
        else:
            _fail_at = time.time()
        return catalog


def _load_catalog_unlocked(force: bool) -> dict[int, AugmentMeta]:
    path = _catalog_file()
    stale = True
    if path.is_file():
        try:
            stale = (time.time() - path.stat().st_mtime) > _CATALOG_TTL_S
        except OSError:
            stale = True
    fetched = (stale or force) and _fetch_catalog_file()
    if (stale or force) and not fetched and not path.is_file():
        return {}

    def _read() -> dict[int, AugmentMeta] | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.debug("증강 카탈로그 파싱 실패: %s", exc)
            return None
        return _parse_catalog(raw if isinstance(raw, list) else [])

    catalog = _read()
    # 손상된 캐시는 mtime 이 새로워도 다시 받는다
    if catalog is None and not fetched and _fetch_catalog_file():
        catalog = _read()
    return catalog or {}


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


def meta_by_name(name: str) -> AugmentMeta | None:
    """한글 이름 → 메타데이터. 같은 이름의 아레나 증강보다 아수라장(Kiwi) 것을 먼저."""
    hits = [m for m in load_catalog().values() if m.name == name]
    hits.sort(key=lambda m: "/kiwi/" not in m.icon_path.lower())
    return hits[0] if hits else None


# 증강 ID → 마지막 아이콘 조회 실패 시각 (부정 캐시). 클라이언트 재시작 등은 TTL 후 재시도.
_icon_failures: dict[int, float] = {}
_ICON_RETRY_S = 300.0
# 클라이언트의 /lol-game-data/assets/... 는 CommunityDragon 에 소문자 경로로 그대로 있다
_CDRAGON_ASSETS = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/"
_LCU_ASSETS = "/lol-game-data/assets/"


def _icon_cache(augment_id: int) -> Path:
    from lol_coach.config import cache_root

    return cache_root() / "icons" / f"aug_{augment_id}.png"


def cached_icon_bytes(augment_id: int) -> bytes | None:
    """디스크에 받아 둔 증강 아이콘만 본다 (네트워크 없음 — UI 스레드에서도 안전)."""
    cache = _icon_cache(augment_id)
    try:
        return cache.read_bytes() if cache.is_file() and cache.stat().st_size > 0 else None
    except OSError:
        return None


def _download_icon(icon_path: str) -> bytes | None:
    """롤 클라이언트가 꺼져 있어도 아이콘을 받는다 (CommunityDragon, 1KB 남짓)."""
    if not icon_path.startswith(_LCU_ASSETS):
        return None
    from lol_coach import http_security
    from lol_coach.static.augment_icons import _validate_image

    url = _CDRAGON_ASSETS + icon_path[len(_LCU_ASSETS):].lower()
    data = http_security.download_same_origin(
        http_security.secure_session(), url,
        http_security.DownloadPolicy(10.0, http_security.MAX_IMAGE_RESPONSE_BYTES),
    )
    return data if _validate_image(data) else None


def icon_bytes_for(meta: AugmentMeta, lcu: Any = None) -> bytes | None:
    """증강 아이콘 바이너리 (디스크 캐시 → 롤 클라이언트 → CommunityDragon). 없으면 None."""
    if not meta.icon_path:
        return None
    hit = cached_icon_bytes(meta.id)
    if hit is not None:
        return hit
    # 최근에 실패한 에셋은 다시 요청하지 않는다 (클릭마다 최대 6회 × 타임아웃 방지)
    failed_at = _icon_failures.get(meta.id)
    if failed_at is not None and time.monotonic() - failed_at < _ICON_RETRY_S:
        return None
    raw = None
    if lcu is not None:
        try:
            raw = lcu._get_raw(meta.icon_path)
        except Exception as exc:
            _log.debug("증강 아이콘 LCU 조회 실패(웹으로 진행): %s", exc)
    if not raw:
        try:
            raw = _download_icon(meta.icon_path)
        except Exception as exc:
            _log.debug("증강 아이콘 다운로드 실패(무시): %s", exc)
    if not raw:
        _icon_failures[meta.id] = time.monotonic()
        return None
    cache = _icon_cache(meta.id)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    except OSError:
        pass
    return raw


# ── 설명 (숫자가 채워진 한국어) ─────────────────────────────────────
# blitz.gg 가 패치마다 올리는 아수라장 증강 게임 자료 (~190KB). lol.ps 설명은 숫자가 빠져 있다
# ("일정 시간 동안 의 적응형 능력치") — 같은 증강 ID 로 이 자료의 설명을 쓴다.
_TEXT_URL = "https://utils.iesdev.com/static/json/lol/mayham/{patch}/augments_ko_kr"
_texts_mem: dict[str, dict[int, tuple[str, str]]] = {}
_texts_fail_at = 0.0
_texts_lock = threading.Lock()


def _strip_tooltip(text: str) -> str:
    """자세한 설명에서 경기 중 수치(<rules>)와 소개 문구(<flavorText>)를 뺀다."""
    import re

    return re.sub(r"<(rules|flavorText)>.*?</\1>", "", text or "", flags=re.S).strip()


def _fetch_texts(patch: str) -> dict[int, tuple[str, str]] | None:
    """이 패치(없으면 바로 전 패치 둘까지)의 설명을 받는다.

    ponytail: 패치 첫날 이번 패치 자료가 아직 없으면 전 패치 설명을 이번 패치 이름으로 저장해 그 패치 내내 쓴다.
    수치가 바뀐 증강이 문제 되면 받은 패치 번호도 저장해 하루 뒤 다시 받게 하면 된다.
    """
    import requests

    major, _, minor = patch.partition(".")
    if not (major.isdigit() and minor.isdigit()):
        return None
    for back in range(3):
        url = _TEXT_URL.format(patch=f"{major}.{int(minor) - back}")
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        data = resp.json()
        rows = data.values() if isinstance(data, dict) else []
        out = {
            int(row["id"]): (str(row.get("description") or ""), _strip_tooltip(str(row.get("tooltip") or "")))
            for row in rows
            if isinstance(row, dict) and str(row.get("id") or "").isdigit()
        }
        return out or None
    return None


def augment_texts(patch: str | None, *, network: bool = True) -> dict[int, tuple[str, str]]:
    """증강 ID → (요약 설명, 자세한 설명). 게임 자료 그대로라 태그·아이콘 토큰이 섞여 있다.

    패치마다 한 번 받아 디스크에 둔다. 받지 못하면 가장 최근에 받아 둔 것을 준다.
    """
    global _texts_fail_at
    key = ".".join(str(patch or "").split(".")[:2])
    with _texts_lock:
        if key in _texts_mem:
            return _texts_mem[key]
    from lol_coach.config import cache_root

    folder = cache_root() / "augments"
    path = folder / f"texts_{key}.json"

    def read(file: Path) -> dict[int, tuple[str, str]] | None:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
            return {int(k): (str(v[0]), str(v[1])) for k, v in raw.items()}
        except (OSError, ValueError, TypeError, IndexError, AttributeError):
            return None

    texts = read(path) if key else None
    if texts is None and key and network and time.time() - _texts_fail_at >= _RETRY_S:
        try:
            texts = _fetch_texts(key)
        except Exception as exc:
            _log.info("증강 설명 받기 실패(이전 자료로 진행): %s", exc)
        if texts:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)
            except OSError:
                pass
        else:
            _texts_fail_at = time.time()
    if texts is None:  # 이번 패치 것이 없으면 가장 최근에 받아 둔 것 (메모리에는 넣지 않는다 — 나중에 다시 받는다)
        older = sorted(folder.glob("texts_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        return next((t for t in map(read, older) if t), {})
    with _texts_lock:
        _texts_mem[key] = texts
    return texts
