"""사용자 표시 에러 메시지."""

from __future__ import annotations

from lol_coach.gui.errors import format_user_error, is_recoverable
from lol_coach.riot.client import RiotAPIError


def test_format_api_key_expired() -> None:
    exc = RiotAPIError(403, "Forbidden")
    text = format_user_error(exc)
    assert "API 키" in text
    assert "24시간" in text


def test_format_404_account() -> None:
    text = format_user_error(RiotAPIError(404, "Not found"))
    assert "소환사" in text or "찾지" in text


def test_format_rate_limit() -> None:
    text = format_user_error(RiotAPIError(429, "rate limit"))
    assert "한도" in text or "429" in text or "초" in text


def test_format_cloudflare() -> None:
    text = format_user_error(RuntimeError("u.gg blocked by Cloudflare challenge"))
    assert "u.gg" in text or "메타" in text


def test_format_lcu_lockfile() -> None:
    text = format_user_error(RuntimeError("lockfile 을 찾을 수 없습니다"))
    assert "클라이언트" in text or "밴픽" in text


def test_is_recoverable() -> None:
    assert is_recoverable(RiotAPIError(429, "x"))
    assert is_recoverable(RiotAPIError(401, "x"))
