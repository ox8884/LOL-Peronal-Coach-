"""LCU lockfile 파싱 + 챔피언 셀렉트 세션 파싱 테스트 (네트워크 없음)."""

import pytest

from lol_coach.lcu import (
    ChampSelectInfo,
    LCUError,
    parse_champ_select,
    parse_lockfile,
)


def test_parse_lockfile_ok() -> None:
    lf = parse_lockfile("League of Legends:12345:54321:secret-password:https")
    assert lf.pid == 12345
    assert lf.port == 54321
    assert lf.password == "secret-password"
    assert lf.protocol == "https"


def test_parse_lockfile_invalid() -> None:
    with pytest.raises(LCUError):
        parse_lockfile("not:a:lockfile")
    with pytest.raises(LCUError):
        parse_lockfile("")


_SESSION = {
    "localPlayerCellId": 2,
    "timer": {"phase": "FINALIZATION"},
    "myTeam": [
        {"cellId": 0, "championId": 238, "assignedPosition": "top"},
        {"cellId": 1, "championId": 64, "assignedPosition": "jungle"},
        {"cellId": 2, "championId": 103, "assignedPosition": "middle"},
        {"cellId": 3, "championId": 0, "assignedPosition": "bottom"},
        {"cellId": 4, "championId": 412, "assignedPosition": "utility"},
    ],
    "theirTeam": [
        {"cellId": 5, "championId": 157},
        {"cellId": 6, "championId": 84},
        {"cellId": 7, "championId": 0},
        {"cellId": 8, "championId": 555},
        {"cellId": 9, "championId": 53},
    ],
    "actions": [
        [
            {"actorCellId": 0, "championId": 266, "type": "ban"},
            {"actorCellId": 5, "championId": 777, "type": "ban"},
            {"actorCellId": 1, "championId": 266, "type": "ban"},  # 중복 밴
            {"actorCellId": 2, "championId": 103, "type": "pick"},
        ]
    ],
}


def test_parse_champ_select_full() -> None:
    info = parse_champ_select(_SESSION)
    assert info.phase == "FINALIZATION"
    assert info.my_cell_id == 2
    assert info.my_champion_id == 103
    assert info.my_position == "middle"
    # 내 픽 제외 아군
    assert info.ally_champion_ids == [238, 64, 412]
    # 미픽(0) 제외 적
    assert info.enemy_champion_ids == [157, 84, 555, 53]
    assert info.ban_champion_ids == [266, 777]
    assert not info.is_aram
    assert info.in_champ_select


def test_parse_champ_select_aram_like() -> None:
    session = {
        "localPlayerCellId": 1,
        "timer": {"phase": "FINALIZATION"},
        "myTeam": [
            {"cellId": 0, "championId": 1},
            {"cellId": 1, "championId": 103},
        ],
        "theirTeam": [],
        "actions": [],
    }
    info = parse_champ_select(session)
    assert info.is_aram
    assert info.my_champion_id == 103
    assert info.enemy_champion_ids == []


def test_parse_champ_select_empty() -> None:
    info = parse_champ_select({})
    assert info.my_cell_id == -1
    assert not info.in_champ_select
    assert isinstance(info, ChampSelectInfo)
