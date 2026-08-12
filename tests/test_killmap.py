from lol_coach.analysis.killmap import (
    KillMapData,
    build_kill_map,
    flatten_events,
    participant_index,
)

MATCH = {
    "info": {
        "participants": [
            {"participantId": 1, "teamId": 100, "championId": 103, "championName": "Ahri"},
            {"participantId": 2, "teamId": 100, "championId": 64, "championName": "LeeSin"},
            {"participantId": 3, "teamId": 200, "championId": 238, "championName": "Zed"},
            {"participantId": 4, "teamId": 200, "championId": 412, "championName": "Thresh"},
        ]
    }
}


def _tl(frames: list[dict]) -> dict:
    return {
        "info": {
            "frames": frames,
            "participants": [
                {"participantId": i, "puuid": f"p{i}"} for i in range(1, 5)
            ],
        }
    }


def _kill(ts: int, killer: int, victim: int, x: float, y: float) -> dict:
    return {
        "type": "CHAMPION_KILL",
        "timestamp": ts,
        "killerId": killer,
        "victimId": victim,
        "position": {"x": x, "y": y},
    }


def test_flatten_events_merges_frames_in_timestamp_order() -> None:
    info = {
        "frames": [
            {"timestamp": 0, "events": [_kill(90000, 3, 1, 1.0, 1.0)]},
            {"timestamp": 60000, "events": []},
            {"timestamp": 120000, "events": [_kill(30000, 4, 2, 2.0, 2.0)]},
        ]
    }
    events = flatten_events(info)
    assert [e["timestamp"] for e in events] == [30000, 90000]
    # 원본 프레임 순서가 아니라 timestamp 순서여야 한다


def test_participant_index_reads_team_and_champion_from_match() -> None:
    idx = participant_index(MATCH)
    assert idx[1].team_id == 100
    assert idx[1].champion_id == 103
    assert idx[1].champion_name == "Ahri"
    assert idx[3].team_id == 200


def test_build_kill_map_classifies_my_kills_and_deaths() -> None:
    tl = _tl(
        [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 500, "y": 500}},
                    "2": {"position": {"x": 1400, "y": 1400}},
                    "3": {"position": {"x": 14000, "y": 14000}},
                    "4": {"position": {"x": 7000, "y": 7000}},
                },
                "events": [
                    _kill(30000, 3, 1, 7000.0, 7000.0),   # 내 데스
                    _kill(35000, 1, 4, 7100.0, 6900.0),   # 내 킬
                    _kill(55000, 3, 1, 7200.0, 6800.0),   # 내 데스
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)

    assert isinstance(data, KillMapData)
    assert len(data.my_deaths) == 2
    assert len(data.my_kills) == 1
    assert data.my_team == 100
    assert data.total_kills == 3
    assert [k.timestamp for k in data.my_deaths] == [30000, 55000]
    assert data.my_deaths[0].killer_champ_id == 238  # Zed
    assert data.my_deaths[0].killer_team == 200
    assert data.my_kills[0].victim_team == 200


def test_build_kill_map_skips_events_without_position() -> None:
    tl = _tl(
        [
            {
                "timestamp": 60000,
                "participantFrames": {},
                "events": [
                    {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1},
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)
    assert data.total_kills == 0
    assert data.my_deaths == []
