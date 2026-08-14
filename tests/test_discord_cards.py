"""DiscordCards 서비스 회귀 테스트 (gui-service-split 단계2).

v1.6.56 회귀 고정:
- webhook_url 이 None/빈 문자열이면 렌더·전송 경로를 타지 않는다.
- 전송 실패 시 예외 메시지에 웹훅 토큰이 누출되지 않는다.
- 전송 성공 시 ok 토스트, 실패 시 fail 토스트.
"""

from __future__ import annotations

import threading

import pytest

from lol_coach.gui.discord_cards import DiscordCards
from lol_coach.notify.discord import DiscordWebhookError


class _SyncThread:
    """threading.Thread 를 동기화 — target 을 즉시 실행."""

    def __init__(self, target, daemon=None) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


@pytest.fixture(autouse=True)
def _sync_threading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(threading, "Thread", _SyncThread)


def _make_cards(notifications: list[str]) -> DiscordCards:
    return DiscordCards(
        after_cb=lambda ms, fn: fn(),
        notify_cb=lambda msg, level="info", ms=3800, **_k: notifications.append(msg),
    )


def test_post_card_skips_when_webhook_none() -> None:
    """webhook_url 이 None 이면 렌더·전송 없이 스킵 (부수 효과 없음)."""
    notifications: list[str] = []
    cards = _make_cards(notifications)
    renders: list[int] = []

    cards.post_card(
        webhook_url=None,
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=lambda: renders.append(1) or b"png",
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    assert renders == []
    assert notifications == []


def test_post_card_skips_when_webhook_empty() -> None:
    """빈 문자열도 스킵 — falsy 검사."""
    notifications: list[str] = []
    cards = _make_cards(notifications)
    renders: list[int] = []

    cards.post_card(
        webhook_url="",
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=lambda: renders.append(1) or b"png",
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    assert renders == []
    assert notifications == []


def test_post_card_success_sends_and_toasts(monkeypatch: pytest.MonkeyPatch) -> None:
    """웹훅 설정 시 — 렌더 + 전송 + 성공 토스트."""
    import lol_coach.notify.discord as notify_mod

    posted: list = []
    monkeypatch.setattr(notify_mod, "post_card", lambda url, **kw: posted.append(kw))
    notifications: list[str] = []
    cards = _make_cards(notifications)
    renders: list[int] = []

    cards.post_card(
        webhook_url="https://discord.com/api/webhooks/1/tok",
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=lambda: renders.append(1) or b"png",
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    assert renders == [1]
    assert posted and posted[0]["png_bytes"] == b"png"
    assert posted[0]["title"] == "t"
    assert any("전송 완료" in n for n in notifications)


def test_post_card_failure_does_not_leak_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """전송 실패 시 — DiscordWebhookError 의 안전한 메시지만 토스트 (토큰 누출 금지)."""
    import lol_coach.notify.discord as notify_mod

    token_url = "https://discord.com/api/webhooks/999/SUPER_SECRET_TOKEN"

    def _raise(url: str, **kw):
        raise DiscordWebhookError("웹훅 요청 실패: 연결 실패 (HTTP/네트워크)")

    monkeypatch.setattr(notify_mod, "post_card", _raise)
    notifications: list[str] = []
    cards = _make_cards(notifications)

    cards.post_card(
        webhook_url=token_url,
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=lambda: b"png",
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    # 실패 토스트에 토큰이 들어가지 않는다
    assert any("전송 실패" in n for n in notifications)
    assert not any("SUPER_SECRET_TOKEN" in n for n in notifications)
    assert not any("webhooks/999" in n for n in notifications)


def test_post_card_unknown_exception_no_token_in_toast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """post_card 밖의 예외 — fail_msg 만 토스트 (예외 문자열 노출 금지)."""
    import lol_coach.notify.discord as notify_mod

    token_url = "https://discord.com/api/webhooks/999/SUPER_SECRET_TOKEN"

    def _raise(url: str, **kw):
        raise RuntimeError(f"unexpected error with {url}")

    monkeypatch.setattr(notify_mod, "post_card", _raise)
    notifications: list[str] = []
    cards = _make_cards(notifications)

    cards.post_card(
        webhook_url=token_url,
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=lambda: b"png",
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    # RuntimeError 문자열(토큰 포함)은 토스트에 나오지 않는다
    assert any("전송 실패" in n for n in notifications)
    assert not any("SUPER_SECRET_TOKEN" in n for n in notifications)
    assert not any("webhooks/999" in n for n in notifications)
