"""디스코드 웹훅 전송·검증·설정 테스트."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

notify_mod = importlib.import_module("lol_coach.notify.discord")
config_mod = importlib.import_module("lol_coach.config")

VALID_URL = "https://discord.com/api/webhooks/123456789/TOKEN_abc"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


class FakeSession:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("FakeSession 응답이 소진되었습니다")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


@pytest.fixture
def webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트 중 실제 웹훅 설정·네트워크 접근 차단."""
    monkeypatch.delenv("LOL_COACH_DISCORD_WEBHOOK", raising=False)
    monkeypatch.setattr(notify_mod.time, "sleep", lambda s: None)


# ── URL 검증 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/1/2",  # https 아님
        "https://evil.com/api/webhooks/1/2",  # 호스트 불허
        "https://discord.com/api/other/1/2",  # 경로 오류
        "https://discord.com",  # 경로 없음
    ],
)
def test_validate_rejects_bad_urls(url: str) -> None:
    with pytest.raises(notify_mod.DiscordWebhookError):
        notify_mod.validate_webhook_url(url)


@pytest.mark.parametrize(
    "url",
    [
        VALID_URL,
        "https://discordapp.com/api/webhooks/1/2",
        "https://canary.discord.com/api/webhooks/1/2",
        "https://discord.com/api/webhooks/1/2?thread_id=999",
    ],
)
def test_validate_accepts_discord_urls(url: str) -> None:
    notify_mod.validate_webhook_url(url)  # 예외 없으면 통과


# ── 전송 ────────────────────────────────────────────────


def test_post_card_success_204(monkeypatch: pytest.MonkeyPatch, webhook_env: None) -> None:
    fake = FakeSession(FakeResponse(204))
    monkeypatch.setattr(notify_mod, "secure_session", lambda: fake)

    notify_mod.post_card(
        VALID_URL,
        title="테스트 제목",
        description="본문",
        png_bytes=b"\x89PNG-data",
        footer="푸터",
    )
    assert len(fake.calls) == 1
    url, kwargs = fake.calls[0]
    assert url == VALID_URL
    payload = json.loads(kwargs["data"]["payload_json"])
    assert payload["embeds"][0]["title"] == "테스트 제목"
    assert payload["embeds"][0]["image"]["url"] == "attachment://review.png"
    filename, filedata, mimetype = kwargs["files"]["file"]
    assert filename == "review.png"
    assert filedata == b"\x89PNG-data"
    assert mimetype == "image/png"
    assert kwargs["allow_redirects"] is False


def test_post_card_retries_on_429(monkeypatch: pytest.MonkeyPatch, webhook_env: None) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(notify_mod.time, "sleep", lambda s: sleeps.append(s))
    fake = FakeSession(
        FakeResponse(429, headers={"Retry-After": "2"}),
        FakeResponse(204),
    )
    monkeypatch.setattr(notify_mod, "secure_session", lambda: fake)

    notify_mod.post_card(VALID_URL, title="t", description="d", png_bytes=b"x")
    assert len(fake.calls) == 2
    assert sleeps == [2.0]


def test_post_card_retries_on_5xx_then_fails(
    monkeypatch: pytest.MonkeyPatch, webhook_env: None
) -> None:
    fake = FakeSession(
        FakeResponse(500, content=b"boom"),
        FakeResponse(502),
        FakeResponse(503),
    )
    monkeypatch.setattr(notify_mod, "secure_session", lambda: fake)

    with pytest.raises(notify_mod.DiscordWebhookError, match="서버 오류"):
        notify_mod.post_card(VALID_URL, title="t", description="d", png_bytes=b"x")
    assert len(fake.calls) == 3


def test_post_card_4xx_fails_immediately(
    monkeypatch: pytest.MonkeyPatch, webhook_env: None
) -> None:
    fake = FakeSession(FakeResponse(404, content=b'{"message": "Unknown Webhook"}'))
    monkeypatch.setattr(notify_mod, "secure_session", lambda: fake)

    with pytest.raises(notify_mod.DiscordWebhookError, match="HTTP 404"):
        notify_mod.post_card(VALID_URL, title="t", description="d", png_bytes=b"x")
    assert len(fake.calls) == 1


def test_post_card_network_error_wrapped(
    monkeypatch: pytest.MonkeyPatch, webhook_env: None
) -> None:
    fake = FakeSession(ConnectionError("refused"))
    monkeypatch.setattr(notify_mod, "secure_session", lambda: fake)

    with pytest.raises(notify_mod.DiscordWebhookError, match="refused"):
        notify_mod.post_card(VALID_URL, title="t", description="d", png_bytes=b"x")


def test_post_card_rejects_empty_and_oversize(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(notify_mod.DiscordWebhookError, match="비어"):
        notify_mod.post_card(VALID_URL, title="t", description="d", png_bytes=b"")
    with pytest.raises(notify_mod.DiscordWebhookError, match="8MB"):
        notify_mod.post_card(
            VALID_URL,
            title="t",
            description="d",
            png_bytes=b"\x00" * (notify_mod.MAX_PNG_BYTES + 1),
        )


def test_post_card_invalid_url_raises_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notify_mod, "secure_session", lambda: FakeSession(FakeResponse(204)))
    with pytest.raises(notify_mod.DiscordWebhookError, match="https"):
        notify_mod.post_card(
            "http://discord.com/api/webhooks/1/2",
            title="t",
            description="d",
            png_bytes=b"x",
        )


# ── 설정 라운드트립 ─────────────────────────────────────


@pytest.fixture
def ui_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    ui = tmp_path / "ui.json"
    monkeypatch.setattr(config_mod, "UI_PATH", ui)
    monkeypatch.delenv("LOL_COACH_DISCORD_WEBHOOK", raising=False)
    return ui


def test_discord_webhook_roundtrip(ui_path: Path) -> None:
    assert config_mod.discord_webhook_url() == ""
    config_mod.set_discord_webhook(VALID_URL)
    assert config_mod.discord_webhook_url() == VALID_URL
    config_mod.set_discord_webhook("")
    assert config_mod.discord_webhook_url() == ""


def test_discord_webhook_env_overrides_ui(ui_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_mod.set_discord_webhook("https://discord.com/api/webhooks/1/ui-token")
    monkeypatch.setenv("LOL_COACH_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/1/env-token")
    assert config_mod.discord_webhook_url() == "https://discord.com/api/webhooks/1/env-token"


def test_discord_review_toggle_default_on(ui_path: Path) -> None:
    assert config_mod.discord_review_enabled() is True
    config_mod.set_discord_review(False)
    assert config_mod.discord_review_enabled() is False
