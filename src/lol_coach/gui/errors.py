"""사용자 표시용 에러 메시지 정규화.

내부 예외 문자열을 그대로 띄우지 않고, 조치 가능한 짧은 안내로 바꾼다.
"""

from __future__ import annotations


def format_user_error(exc: BaseException | str, *, context: str = "") -> str:
    """예외 → 상태바/카드용 한국어 안내."""
    if isinstance(exc, str):
        text = exc.strip()
        status = _guess_status(text)
        msg = text
    else:
        status = getattr(exc, "status_code", None)
        msg = str(exc).strip() or exc.__class__.__name__

    name = type(exc).__name__ if not isinstance(exc, str) else ""
    lower = msg.lower()

    # Riot API
    if status in (401, 403) or "api 키" in msg.lower() or "forbidden" in lower:
        return (
            "Riot API 키가 만료되었거나 올바르지 않습니다. "
            "developer.riotgames.com 에서 Development 키를 다시 발급해 "
            "「내 전적」탭에 저장하세요. (개발 키는 24시간마다 만료)"
        )
    if status == 404 or "not found" in lower:
        if "match" in lower:
            return "경기 데이터를 찾지 못했습니다. 잠시 후 다시 시도하세요."
        return "소환사/계정을 찾지 못했습니다. Riot ID·서버(kr 등)를 확인하세요."
    if status == 429 or "rate limit" in lower:
        return "Riot API 요청 한도에 걸렸습니다. 20~60초 후 다시 시도하세요."
    if status in (500, 502, 503, 504) or "server error" in lower:
        return "Riot 서버 일시 오류입니다. 잠시 후 다시 시도하세요."
    if status == 0 or "network error" in lower or "max retries" in lower:
        return "네트워크 오류입니다. 인터넷 연결을 확인한 뒤 다시 시도하세요."

    # LCU
    if "LCU" in name or "lockfile" in lower or "lcu" in lower:
        if "없" in msg or "not found" in lower or "찾을 수 없" in msg:
            return (
                "리그 클라이언트를 찾지 못했습니다. 게임을 켠 뒤, "
                "밴픽(챔피언 선택) 중에 다시 눌러 주세요. "
                "(설치 경로가 다르면 환경변수 LOL_LOCKFILE 설정)"
            )
        if "밴픽" in msg or "champ select" in lower or "세션" in msg:
            return "지금은 밴픽 중이 아닙니다. 챔피언 선택 화면에서 다시 시도하세요."
        return f"클라이언트 연동 실패: {_short(msg)}"

    # u.gg / scrape
    if "cloudflare" in lower or "u.gg" in lower:
        return (
            "메타 사이트(u.gg) 접속이 막혔거나 불안정합니다. "
            "캐시된 빌드가 있으면 그것을 쓰고, 없으면 잠시 후 다시 시도하세요."
        )

    prefix = f"{context}: " if context else ""
    return f"{prefix}{_short(msg)}"


def _short(msg: str, limit: int = 220) -> str:
    msg = " ".join(msg.split())
    if len(msg) <= limit:
        return msg
    return msg[: limit - 1] + "…"


def _guess_status(text: str) -> int | None:
    import re

    m = re.search(r"\[(\d{3})\]", text)
    if m:
        return int(m.group(1))
    return None


def is_recoverable(exc: BaseException) -> bool:
    """모달 대신 상태바로 충분한 경미한 오류 여부."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403, 404, 429):
        return True
    msg = str(exc).lower()
    return any(
        k in msg
        for k in ("lockfile", "cloudflare", "rate limit", "network", "timeout")
    )
