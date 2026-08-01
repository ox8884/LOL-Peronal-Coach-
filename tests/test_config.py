from pathlib import Path

import pytest

from lol_coach.config import (
    InvalidPlatformError,
    Settings,
    add_profile,
    list_profiles,
    remove_profile,
    save_api_key,
    save_player,
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


def test_list_profiles_missing_file(tmp_path: Path) -> None:
    assert list_profiles(tmp_path / "nope.json") == []
