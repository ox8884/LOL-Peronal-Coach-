"""lol.ps 아수라장 자료 — 챔피언 티어, 추천·비추천 증강, 템트리.

https://lol.ps/aram-mayhem 페이지에 딸린 데이터(`__data.json`)를 받아 화면에 필요한 값만
작게 저장한다. robots.txt 가 막은 `/api` 는 쓰지 않는다.

빠르게 뜨는 것이 먼저다:
- 한 번 받은 것은 메모리 → 디스크(`cache/lolps/`) 순으로 바로 돌려준다 (챔피언당 수 KB).
- 같은 패치의 자료가 오래됐으면 지금 것을 먼저 주고 뒤에서 새로 받는다.
- 패치가 바뀐 자료만 그 자리에서 다시 받는다. 받지 못하면 예전 것을 준다.
네트워크는 워커 스레드에서만 부른다 (`network=False` 면 캐시만 본다).
"""

from __future__ import annotations

import gzip
import json
import os
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lol_coach.config import cache_root
from lol_coach.log import get_logger

_log = get_logger("lolps")

PAGE_URL = "https://lol.ps/aram-mayhem"
_UA = "lol-coach (+https://github.com/ox8884/LOL-Peronal-Coach-)"
_MAX_BYTES = 4 * 1024 * 1024  # 응답 상한 — 이상 응답 방어
INDEX_TTL_S = 6 * 3600
CHAMP_TTL_S = 24 * 3600
# lol.ps 는 S/A/B/C, 앱 안에서는 숫자(1이 가장 좋음)로 비교하고 화면에는 글자로 보여 준다
TIER_NUM = {"S": 1, "A": 2, "B": 3, "C": 4, "D": 5}
# 빌드 유형 — lol.ps 티어판의 딱지와 같은 이름
BUILD_NAMES = {
    "ap": "AP 딜러", "ad": "AD 딜러", "tank": "탱커", "support": "서포터",
    "ap_bruiser": "AP 브루저", "ad_bruiser": "AD 브루저", "mixed": "하이브리드",
}
_FORMAT = 3  # 저장 형식 — 바뀌면 예전 캐시를 버리고 다시 받는다

_lock = threading.Lock()
_mem: dict[str, dict[str, Any]] = {}
_refreshing: set[str] = set()


# ── 저장 ────────────────────────────────────────────────────────────
def _path(name: str) -> Path:
    folder = cache_root() / "lolps"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.json"


def _load(name: str) -> dict[str, Any] | None:
    with _lock:
        hit = _mem.get(name)
    if hit is not None:
        return hit
    try:
        data = json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    with _lock:
        _mem[name] = data
    return data


def _save(name: str, data: dict[str, Any]) -> None:
    with _lock:
        _mem[name] = data
    try:
        path = _path(name)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)  # 동시 실행·강제 종료에도 반쪽 파일이 남지 않게
    except OSError as exc:
        _log.debug("lol.ps 캐시 저장 실패(무시): %s", exc)


def _age(entry: dict[str, Any]) -> float:
    return time.time() - float(entry.get("fetched") or 0)


# ── 받기 ────────────────────────────────────────────────────────────
def unflatten(values: list[Any]) -> Any:
    """SvelteKit(devalue)의 평탄화 배열을 보통 객체로 되돌린다.

    배열의 0번이 뿌리이고, 객체·배열 안의 숫자는 다른 칸의 번호다. 음수는 값 없음.
    """
    memo: dict[int, Any] = {}

    def get(index: int) -> Any:
        if index < 0:
            return None
        if index in memo:
            return memo[index]
        value = values[index]
        if isinstance(value, dict):
            obj: dict[str, Any] = {}
            memo[index] = obj
            for key, ref in value.items():
                obj[key] = get(ref)
            return obj
        if isinstance(value, list):
            if value and isinstance(value[0], str):  # ["Date", "2026-…"] 같은 타입 표시
                memo[index] = value[1] if len(value) > 1 and not isinstance(value[1], int) else None
                return memo[index]
            arr: list[Any] = []
            memo[index] = arr
            arr.extend(get(ref) for ref in value)
            return arr
        memo[index] = value
        return value

    return get(0)


def _fetch_nodes(path: str, *, page_only: bool) -> list[Any]:
    """`/aram-mayhem{path}/__data.json` → 노드별 자료 (건너뛴 노드는 None)."""
    url = f"{PAGE_URL}{path}/__data.json"
    if page_only:
        url += "?x-sveltekit-invalidated=0001"  # 공통 자료(챔피언 이름 등 100KB+)는 받지 않는다
    request = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip", "Accept-Language": "ko"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(_MAX_BYTES + 1)
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    if len(raw) > _MAX_BYTES:
        raise ValueError(f"응답 크기 초과: {url}")
    payload = json.loads(raw.decode("utf-8"))
    return [
        unflatten(node["data"]) if isinstance(node, dict) and node.get("type") == "data" else None
        for node in payload.get("nodes", [])
    ]


def _parse_index(nodes: list[Any]) -> dict[str, Any] | None:
    """목록 페이지 → 패치, 챔피언 티어·역할·승률, 증강 사전."""
    layout = next((n for n in nodes if isinstance(n, dict) and "versionInfo" in n), None)
    page = next((n for n in nodes if isinstance(n, dict) and "champions" in n), None)
    if not layout or not page or not page.get("champions") or not page.get("augments"):
        return None
    versions = [v for v in layout["versionInfo"] or [] if v.get("isActive")] or layout["versionInfo"]
    if not versions:
        return None
    # 사이트의 티어판은 '챔피언 + 빌드 유형'별 티어(roleTiers)를 성능 점수 순으로 놓는다.
    # 챔피언 목록의 tier 는 다른 값이라 티어판과 어긋난다 — 쓰지 않는다.
    board = sorted(
        (
            {
                "id": row["id"], "type": row.get("type", ""), "tier": row["tier"],
                "perf": row.get("perf") or 0, "win": row.get("winRate"), "pick": row.get("pickRate"),
            }
            for row in page.get("roleTiers") or []
            if row.get("id") and row.get("tier") in TIER_NUM
        ),
        key=lambda row: (TIER_NUM[row["tier"]], -row["perf"]),
    )
    best: dict[int, dict[str, Any]] = {}
    for row in board:  # 정렬돼 있으니 처음 만나는 줄이 그 챔피언의 가장 좋은 빌드
        best.setdefault(row["id"], row)
    champs = {
        str(c["id"]): {
            "name": c.get("name", ""),
            "tier": (best.get(c["id"]) or {}).get("tier") or c.get("tier", ""),
            "roles": c.get("roles") or [],
            "win": (best.get(c["id"]) or {}).get("win"),
            "pick": (best.get(c["id"]) or {}).get("pick"),
        }
        for c in page["champions"]
        if c.get("id") and c.get("status", "ok") == "ok"
    }
    augments = {
        str(a["id"]): {
            "name": a.get("name", ""),
            "name_id": a.get("nameId", ""),
            "rarity": a.get("rarity", ""),
            "tier": a.get("tier", ""),
            "desc": a.get("description", ""),
            "roles": a.get("roleFit") or [],
        }
        for a in page["augments"]
        if a.get("id") and a.get("name")
    }
    return {
        "patch": str(versions[0].get("description") or ""),
        "patch_date": str(versions[0].get("patchDate") or ""),
        "fetched": time.time(),
        "v": _FORMAT,
        "champs": champs,
        "board": board,
        "augments": augments,
    }


def _augment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "rank": row.get("rank") or 0,
        "name": row.get("name", ""),
        "rarity": row.get("rarity", ""),
        "desc": row.get("description", ""),
        "items": [i for i in row.get("items") or [] if i],
        "signature": [i for i in row.get("signatureItems") or [] if i],
    }


def _parse_champion(nodes: list[Any], patch: str) -> dict[str, Any] | None:
    """챔피언 페이지 → 주 빌드의 아이템 6개·추천·비추천 증강, 주문, 승률."""
    page = next((n for n in nodes if isinstance(n, dict) and "detail" in n), None)
    detail = (page or {}).get("detail") or {}
    # 사이트는 빌드 유형마다 탭을 두고 첫 탭(주로 쓰는 빌드)을 보여 준다. 합친 목록(detail.good)은
    # 두 빌드의 추천이 섞여 아이템과 맞지 않는다 (예: 신 짜오 하이브리드 템에 AD 브루저 증강).
    builds = [b for b in detail.get("builds") or [] if b.get("items") and b.get("good")]
    main = builds[0] if builds else detail
    items = [i for i in main.get("items") or [] if i]
    good = [_augment(row) for row in main.get("good") or [] if row.get("id") and row.get("name")]
    if not items or not good:
        return None
    overall = detail.get("overall") or {}
    return {
        "patch": patch,
        "fetched": time.time(),
        "v": _FORMAT,
        "build": BUILD_NAMES.get(str(main.get("type") or ""), ""),
        "items": items,
        "spells": detail.get("spells") or [],
        "good": good,
        "bad": [_augment(row) for row in main.get("bad") or [] if row.get("id") and row.get("name")],
        "unavailable": [row["id"] for row in (page or {}).get("unavailable") or [] if row.get("id")],
        "win": overall.get("winRate"),
        "pick": overall.get("pickRate"),
    }


def _download_index() -> dict[str, Any] | None:
    try:
        data = _parse_index(_fetch_nodes("", page_only=False))
    except Exception as exc:
        _log.info("lol.ps 목록 조회 실패: %s", exc)
        return None
    if data is not None:
        _save("index", data)
    return data


def _download_champion(champion_id: int, patch: str) -> dict[str, Any] | None:
    try:
        data = _parse_champion(_fetch_nodes(f"/champion/{champion_id}", page_only=True), patch)
    except Exception as exc:
        _log.info("lol.ps 챔피언 %s 조회 실패: %s", champion_id, exc)
        return None
    if data is not None:
        _save(f"champ_{champion_id}", data)
    return data


def _refresh_later(name: str, work: Callable[[], Any]) -> None:
    """오래된 자료를 뒤에서 새로 받는다 (같은 것을 겹쳐 받지 않는다)."""
    with _lock:
        if name in _refreshing:
            return
        _refreshing.add(name)

    def run() -> None:
        try:
            work()
        finally:
            with _lock:
                _refreshing.discard(name)

    threading.Thread(target=run, daemon=True).start()


# ── 공개 함수 ───────────────────────────────────────────────────────
def index(*, network: bool = True) -> dict[str, Any] | None:
    """목록 자료. 캐시가 있으면 바로 주고, 6시간이 지났으면 뒤에서 새로 받는다."""
    cached = _load("index")
    if cached is not None and cached.get("v") == _FORMAT:
        if network and _age(cached) >= INDEX_TTL_S:
            _refresh_later("index", _download_index)
        return cached
    return _download_index() if network else None


def champion(champion_id: int, *, network: bool = True) -> dict[str, Any] | None:
    """챔피언 자료. 같은 패치면 캐시를 바로 주고, 패치가 바뀌었으면 다시 받는다."""
    listing = index(network=network)
    patch = str((listing or {}).get("patch") or "")
    name = f"champ_{champion_id}"
    cached = _load(name)
    # 예전 형식도 패치가 바뀐 것처럼 다시 받는다 (받지 못하면 예전 것을 그대로 쓴다)
    if cached is not None and cached.get("v") == _FORMAT and (not patch or cached.get("patch") == patch):
        if network and _age(cached) >= CHAMP_TTL_S:
            _refresh_later(name, lambda: _download_champion(champion_id, patch))
        return cached
    if not network or not patch:
        return cached
    return _download_champion(champion_id, patch) or cached


def champion_tiers(*, network: bool = True) -> tuple[str, str, dict[int, int]] | None:
    """전체 챔피언 티어 → (패치, 받은 날짜, {챔피언 숫자 ID: 1~4}). 없으면 None."""
    listing = index(network=network)
    if not listing:
        return None
    tiers = {
        int(cid): TIER_NUM[c["tier"]]
        for cid, c in listing["champs"].items()
        if c.get("tier") in TIER_NUM
    }
    if not tiers:
        return None
    day = time.strftime("%Y-%m-%d", time.localtime(float(listing.get("fetched") or 0)))
    return str(listing["patch"]), day, tiers


def tier_board(*, network: bool = True) -> tuple[str, str, list[tuple[int, int, str, float]]] | None:
    """lol.ps 티어판 그대로 → (패치, 받은 날짜, [(티어 1~4, 챔피언 ID, 빌드 유형 이름, 승률)]).

    한 챔피언이 빌드 유형마다 따로 나온다 (예: 케일 하이브리드·AD 딜러). 사이트와 같은 순서.
    """
    listing = index(network=network)
    if not listing or not listing.get("board"):
        return None
    rows = [
        (TIER_NUM[row["tier"]], int(row["id"]), BUILD_NAMES.get(row["type"], ""), row.get("win") or 0.0)
        for row in listing["board"]
    ]
    day = time.strftime("%Y-%m-%d", time.localtime(float(listing.get("fetched") or 0)))
    return str(listing["patch"]), day, rows


def prefetch_all(should_stop: Callable[[], bool] = lambda: False, pause_s: float = 0.3) -> int:
    """이번 패치 자료가 없는 챔피언을 천천히 미리 받는다. 반환: 새로 받은 수.

    패치마다 한 번, 한 번에 하나씩, 사이를 띄워서 받는다 (사이트에 부담을 주지 않게).
    """
    listing = _load("index")
    if listing is None or listing.get("v") != _FORMAT or _age(listing) >= INDEX_TTL_S:
        listing = _download_index() or listing  # 뒤에서 도는 작업이라 새 목록을 기다려도 된다
    if not listing:
        return 0
    patch = str(listing["patch"])
    # 좋은 티어부터 — 자주 잡게 되는 챔피언이 먼저 준비된다
    order = sorted(listing["champs"], key=lambda cid: TIER_NUM.get(listing["champs"][cid]["tier"], 9))
    done = 0
    for cid in order:
        if should_stop():
            break
        cached = _load(f"champ_{cid}")
        if cached is not None and cached.get("patch") == patch and cached.get("v") == _FORMAT:
            continue
        if _download_champion(int(cid), patch) is not None:
            done += 1
        time.sleep(pause_s)
    return done
