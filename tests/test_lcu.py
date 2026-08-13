"""LCU lockfile 파싱 + 챔피언 셀렉트 세션 파싱 테스트 (네트워크 없음)."""

import pytest

from lol_coach.lcu import (
    ChampSelectInfo,
    LCUClient,
    LCUError,
    parse_champ_select,
    parse_lockfile,
    parse_match_history,
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


def test_parse_champ_select_augments() -> None:
    """ARAM 아수라장 — 제시 증강 자동 읽기 (dict/문자열 혼합 대응)."""
    session = {
        "localPlayerCellId": 1,
        "timer": {"phase": "FINALIZATION"},
        "myTeam": [
            {
                "cellId": 1,
                "championId": 103,
                "assignedPosition": "bottom",
                "augments": [
                    {"name": "Jeweled Gauntlet", "id": 57},
                    "Back to Basics",
                    {"name": "Jeweled Gauntlet", "id": 57},
                    {"name": "57", "id": 57},
                ],
            },
            {"cellId": 2, "championId": 412, "augments": []},
        ],
        "theirTeam": [],
    }
    info = parse_champ_select(session)
    assert info.my_augments == ["Jeweled Gauntlet", "Back to Basics"]
    assert info.is_aram

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


def test_parse_match_history_variants() -> None:
    nested = {"games": {"games": [{"gameId": 1}, {"gameId": 2}], "gameCount": 2}}
    assert [g["gameId"] for g in parse_match_history(nested)] == [1, 2]

    flat = {"games": [{"gameId": 3}]}
    assert [g["gameId"] for g in parse_match_history(flat)] == [3]

    assert parse_match_history({"games": {"games": []}}) == []
    assert parse_match_history({}) == []
    assert parse_match_history("bad") == []
    # gameId 없는 항목은 걸러낸다
    assert [g["gameId"] for g in parse_match_history({"games": [{"gameId": 0}, {"gameId": 5}]})] == [5]


def test_match_history_and_timeline_methods(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(self, path: str):
        calls.append(path)
        if path.startswith("/lol-match-history/v1/products"):
            return {"games": {"games": [{"gameId": 9}]}}
        if path.startswith("/lol-match-history/v1/games/9"):
            return {"gameId": 9, "participants": []}
        if path.startswith("/lol-match-history/v1/game-timelines/9"):
            return {"frames": []}
        raise AssertionError(f"unexpected path {path}")

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert [g["gameId"] for g in client.match_history(0, 10)] == [9]
    assert client.match_detail(9)["gameId"] == 9
    assert client.match_timeline(9) == {"frames": []}


def test_match_timeline_returns_none_on_404(monkeypatch) -> None:
    def fake_get(self, path: str):
        raise LCUError("엔드포인트 없음(404): " + path)

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert client.match_timeline(9) is None


def test_current_summoner_name(monkeypatch) -> None:
    from lol_coach.lcu import LCUClient

    def fake_get(self, path: str):
        return {"displayName": "채니미"}

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert client.current_summoner_name() == "채니미"
