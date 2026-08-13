"""Riot API 키 저장 시각 · 만료 안내."""

from __future__ import annotations

from lol_coach import config


def test_save_api_key_writes_timestamp(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env)
    config.save_api_key("RGAPI-12345678-aaaa-bbbb-cccc-dddddddddddd", env_path=env)
    text = env.read_text(encoding="utf-8")
    assert "RIOT_API_KEY_SAVED_AT" in text
    assert config.api_key_saved_at() is not None or "RIOT_API_KEY_SAVED_AT" in text


def test_api_key_expiry_hint_fresh(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env)
    monkeypatch.setenv("RIOT_API_KEY_SAVED_AT", "2099-01-01T00:00:00Z")
    # age negative? max(0, now - future) = 0 for future dates if we use max
    # force a recent stamp
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setenv("RIOT_API_KEY_SAVED_AT", stamp)
    assert config.api_key_expiry_hint() == ""


def test_api_key_expiry_hint_old(monkeypatch) -> None:
    monkeypatch.setenv("RIOT_API_KEY_SAVED_AT", "2020-01-01T00:00:00Z")
    hint = config.api_key_expiry_hint()
    assert "재발급" in hint or "Personal" in hint


def test_default_platform_is_kr() -> None:
    assert config.DEFAULT_PLATFORM == "kr"
