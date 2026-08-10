"""ddragon 정적 데이터 공용 디스크 캐시 — DataDragon · KoreanLocalizer 공유.

패치(버전)에 따라 바뀌는 JSON(champion/item/summoner/runes/versions)을
``cache_root()/ddragon/`` 아래에 버전 키로 저장한다.

- TTL: versions.json 12시간 / 데이터 파일 7일 (신규 챔피언·아이템 반영 주기 고려)
- 네트워크 실패 시 TTL이 지난 캐시라도 반환 (오프라인 방어)
- 두 클래스가 같은 파일을 받아가던 중복 요청을 제거 (실행당 요청 ~14 → 0~1)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from lol_coach.http_security import MAX_JSON_RESPONSE_BYTES, read_limited_json

VERSION_TTL_S = 12 * 3600  # versions.json — 패치 반영 지연 최소화
DATA_TTL_S = 7 * 24 * 3600  # 데이터 파일 (champion/item/summoner/runes)


def _root() -> Path:
    try:
        from lol_coach.config import cache_root

        root = cache_root() / "ddragon"
    except Exception:
        root = Path.cwd() / "cache" / "ddragon"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root


def _path(key: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)
    return _root() / f"{safe}.json"


def read_cache(key: str, *, allow_stale: bool = False) -> dict | None:
    """캐시 payload dict 반환 — 없거나 TTL 지났으면 None.

    반환 dict 형식: ``{"ts": float, "body": Any}``
    """
    try:
        p = _path(key)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "body" not in data:
            return None
        ttl = VERSION_TTL_S if key == "versions" else DATA_TTL_S
        age = time.time() - float(data.get("ts") or 0)
        if age > ttl and not allow_stale:
            return None
        return data
    except Exception:
        return None


def write_cache(key: str, body: Any) -> None:
    """JSON 직렬화 가능 body 를 키별로 저장."""
    try:
        p = _path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"ts": time.time(), "body": body}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(p)
    except Exception:
        pass


def get_json(
    session: requests.Session,
    url: str,
    key: str,
    *,
    timeout: float,
) -> Any:
    """디스크 캐시 우선 → 네트워크 → 저장. 실패 시 stale 캐시 폴백.

    - TTL 이내 캐시가 있으면 네트워크 없이 즉시 반환
    - 없으면 ``session.get(url)`` 후 저장
    - 네트워크 실패 시 TTL 지난 캐시라도 반환, 캐시도 없으면 예외 전파
    """
    hit = read_cache(key)
    if hit is not None:
        return hit["body"]
    try:
        resp = session.get(
            url,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        )
        resp.raise_for_status()
        body = read_limited_json(resp, MAX_JSON_RESPONSE_BYTES)
    except Exception:
        stale = read_cache(key, allow_stale=True)
        if stale is not None:
            return stale["body"]
        raise
    write_cache(key, body)
    return body
