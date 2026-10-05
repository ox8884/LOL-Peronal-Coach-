from pathlib import Path

import pytest

from lol_coach import config as config_mod
from lol_coach.config import (
    InvalidPlatformError,
    Settings,
    add_profile,
    auto_open_latest_match_enabled,
    game_end_auto_review_enabled,
    game_end_notify_enabled,
    list_profiles,
    remove_profile,
    save_api_key,
    save_player,
    set_auto_open_latest_match,
    set_game_end_auto_review,
    set_game_end_notify,
)


def test_settings_validate_missing_key():
    s = Settings(riot_api_key="")
    errs = s.validate()
    assert any("RIOT_API_KEY" in e for e in errs)


def test_default_settings_do_not_embed_developer_riot_id() -> None:
    assert Settings(riot_api_key="").riot_id == ""


def test_save_api_key_and_player(tmp_path: Path):
    env = tmp_path / ".env"
    save_api_key("RGAPI-12345678-1234-1234-1234-123456789abc", env)
    text = env.read_text(encoding="utf-8")
    assert "RIOT_API_KEY=" in text
    save_player("Missouri", "002", platform="na1", env_path=env)
    text = env.read_text(encoding="utf-8")
    assert "Missouri" in text
    assert "002" in text


def test_save_player_rejects_invalid_platform(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    with pytest.raises(InvalidPlatformError):
        save_player("Player", "NA1", platform="attacker.example#", env_path=env_path)

    assert not env_path.exists()


def test_save_player_drops_stale_region_key(tmp_path: Path) -> None:
    """RIOT_REGION은 platform 파생이므로 저장 파일에서 제거한다."""
    env = tmp_path / ".env"
    env.write_text(
        "RIOT_API_KEY=RGAPI-x\nRIOT_REGION=americas\n", encoding="utf-8"
    )
    save_player("Player", "KR1", platform="kr", env_path=env)
    text = env.read_text(encoding="utf-8")
    assert "RIOT_PLATFORM=" in text  # dotenv는 값을 따옴표로 감쌀 수 있음
    assert "kr" in text
    assert "RIOT_REGION" not in text


def test_profiles_add_list_update_remove(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    add_profile("Alpha#KR1", "kr", path=path)
    add_profile("Beta#NA1", "na1", path=path)
    profiles = list_profiles(path)
    assert [p["riot_id"] for p in profiles] == ["Beta#NA1", "Alpha#KR1"]

    # 같은 ID 재저장 → 갱신 + 맨 앞으로
    add_profile("Alpha#KR1", "kr", path=path)
    profiles = list_profiles(path)
    assert [p["riot_id"] for p in profiles] == ["Alpha#KR1", "Beta#NA1"]

    remove_profile("Beta#NA1", path=path)
    profiles = list_profiles(path)
    assert [p["riot_id"] for p in profiles] == ["Alpha#KR1"]


def test_add_profile_validates_riot_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        add_profile("NoTagHere", "kr", path=tmp_path / "profiles.json")


def test_game_end_notify_setting_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ui = tmp_path / "ui.json"
    monkeypatch.setattr(config_mod, "UI_PATH", ui)
    assert game_end_notify_enabled() is True  # default ON
    set_game_end_notify(False)
    assert game_end_notify_enabled() is False
    set_game_end_notify(True)
    assert game_end_notify_enabled() is True
    text = ui.read_text(encoding="utf-8")
    assert "game_end_notify" in text


def test_auto_open_latest_match_setting_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ui = tmp_path / "ui.json"
    monkeypatch.setattr(config_mod, "UI_PATH", ui)
    assert auto_open_latest_match_enabled() is False  # default OFF
    set_auto_open_latest_match(True)
    assert auto_open_latest_match_enabled() is True
    set_auto_open_latest_match(False)
    assert auto_open_latest_match_enabled() is False
    assert "auto_open_latest_match" in ui.read_text(encoding="utf-8")


def test_game_end_auto_review_setting_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ui = tmp_path / "ui.json"
    monkeypatch.setattr(config_mod, "UI_PATH", ui)
    assert game_end_auto_review_enabled() is True  # default ON
    set_game_end_auto_review(False)
    assert game_end_auto_review_enabled() is False
    set_game_end_auto_review(True)
    assert game_end_auto_review_enabled() is True
    assert "game_end_auto_review" in ui.read_text(encoding="utf-8")


def test_list_profiles_missing_file(tmp_path: Path) -> None:
    assert list_profiles(tmp_path / "nope.json") == []


@pytest.fixture
def ai_env(tmp_path, monkeypatch):
    import os
    for name in set(os.environ) | {
        "LOL_COACH_LLM_PROVIDER", "LOL_COACH_LLM_BASE_URL", "LOL_COACH_LLM_KEY",
        "LOL_COACH_LLM_MODEL", "LOL_COACH_LLM_KEY_GROQ",
    }:
        if name.startswith("LOL_COACH_LLM_"):
            monkeypatch.setenv(name, "")
    path = tmp_path / ".env"
    monkeypatch.setattr(config_mod, "ENV_PATH", path)
    return path


def test_custom_settings_deactivate_legacy_credentials(ai_env, monkeypatch):
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "groq")
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GROQ", "legacy-secret")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "legacy-common")
    monkeypatch.setenv("LOL_COACH_LLM_MODEL", "legacy-model")
    monkeypatch.setenv("LOL_COACH_LLM_BASE_URL", "https://new.example/v1")
    settings = config_mod.load_settings()
    assert (settings.llm_provider, settings.llm_base_url, settings.llm_api_key, settings.llm_model) == ("custom", "", "", "")
    assert not ai_env.exists()


def test_custom_settings_save_reload_and_remove_only_owned_legacy(ai_env, monkeypatch):
    from dotenv import dotenv_values
    ai_env.write_text("# keep\nRIOT_API_KEY=RGAPI-test\nOPENAI_API_KEY=other-app\nLOL_COACH_LLM_KEY_GROQ=old\nLOL_COACH_LLM_KEY_FUTURE=keep\n", encoding="utf-8")
    config_mod.save_llm_settings(" https://api.example/custom/ ", " new-secret ", " manual/model ", env_path=ai_env)
    values = dotenv_values(ai_env)
    assert values["LOL_COACH_LLM_BASE_URL"] == "https://api.example/custom"
    assert values["LOL_COACH_LLM_KEY"] == "new-secret"
    assert "LOL_COACH_LLM_KEY_GROQ" not in values
    assert values["OPENAI_API_KEY"] == "other-app"
    assert values["LOL_COACH_LLM_KEY_FUTURE"] == "keep"
    assert values["RIOT_API_KEY"] == "RGAPI-test"
    for name in ("LOL_COACH_LLM_PROVIDER", "LOL_COACH_LLM_BASE_URL", "LOL_COACH_LLM_KEY", "LOL_COACH_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = config_mod.load_settings()
    assert (settings.llm_provider, settings.llm_base_url, settings.llm_api_key, settings.llm_model) == ("custom", "https://api.example/custom", "new-secret", "manual/model")
    config_mod.save_llm_settings("", "", "", env_path=ai_env)
    assert config_mod.load_settings().llm_api_key == ""
    assert dotenv_values(ai_env)["RIOT_API_KEY"] == "RGAPI-test"


def test_custom_invalid_save_is_non_mutating(ai_env):
    ai_env.write_text("# untouched\n", encoding="utf-8")
    with pytest.raises(ValueError):
        config_mod.save_llm_settings("http://remote.example/v1", "secret", "model", env_path=ai_env)
    assert ai_env.read_text(encoding="utf-8") == "# untouched\n"


def test_custom_settings_repr_hides_key():
    settings = Settings(riot_api_key="", llm_api_key="private-ai-secret")
    assert "private-ai-secret" not in repr(settings)


def test_custom_save_failure_keeps_file_and_process_settings(ai_env, monkeypatch):
    import os
    ai_env.write_text("# original\n", encoding="utf-8")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "original-key")
    def fail_replace(self, target):
        raise OSError("disk failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        config_mod.save_llm_settings("https://api.example/v1", "replacement-key", "model", env_path=ai_env)
    assert ai_env.read_text(encoding="utf-8") == "# original\n"
    assert os.environ["LOL_COACH_LLM_KEY"] == "original-key"
    assert list(ai_env.parent.iterdir()) == [ai_env]


@pytest.mark.parametrize("field", ["base_url", "api_key", "model"])
def test_custom_save_rejects_line_injection_before_writing(ai_env, field):
    args = dict(base_url="https://api.example/v1", api_key="key", model="model")
    args[field] += "\nINJECTED=secret"
    with pytest.raises(ValueError) as exc:
        config_mod.save_llm_settings(**args, env_path=ai_env)
    assert "secret" not in str(exc.value)
    assert not ai_env.exists()


@pytest.mark.parametrize("field", ["base_url", "api_key", "model"])
def test_custom_save_rejects_env_interpolation_without_mutation(ai_env, monkeypatch, field):
    import os

    ai_env.write_text("RIOT_API_KEY=dummy-riot-key\n", encoding="utf-8")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "existing-ai-key")
    args = dict(base_url="https://api.example/v1", api_key="key", model="model")
    args[field] += "${RIOT_API_KEY}"
    with pytest.raises(ValueError):
        config_mod.save_llm_settings(**args, env_path=ai_env)
    assert ai_env.read_text(encoding="utf-8") == "RIOT_API_KEY=dummy-riot-key\n"
    assert os.environ["LOL_COACH_LLM_KEY"] == "existing-ai-key"
