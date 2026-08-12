from lol_coach.analysis.killmap import (
    KillMapData,
    build_kill_map,
    compute_bounds,
    flatten_events,
    game_to_pixel,
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


def test_collapse_detects_three_kills_in_30s_same_team() -> None:
    tl = _tl(
        [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 1000, "y": 1000}},
                    "2": {"position": {"x": 2000, "y": 1000}},
                    "3": {"position": {"x": 7000, "y": 7000}},
                    "4": {"position": {"x": 7100, "y": 6900}},
                },
                "events": [
                    _kill(30000, 3, 1, 7000.0, 7000.0),
                    _kill(40000, 4, 2, 7100.0, 6900.0),
                    _kill(55000, 3, 1, 7200.0, 6800.0),
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)

    c = data.collapse
    assert c is not None
    assert c.winning_team == 200  # 킬러 팀
    assert c.kill_count == 3
    assert c.timestamp == 55000
    # 생존자는 최근접 프레임 위치, 사망자(1,2)는 킬 이벤트 위치
    by_pid = {p.participant_id: p for p in c.players}
    assert not by_pid[1].alive and (by_pid[1].x, by_pid[1].y) == (7200.0, 6800.0)
    assert by_pid[3].alive and (by_pid[3].x, by_pid[3].y) == (7000.0, 7000.0)
    assert "아군" in c.caption  # 내 팀 기준 아군(200)이 아니므로


def test_collapse_requires_window_within_30_seconds() -> None:
    tl = _tl(
        [
            {
                "timestamp": 120000,
                "participantFrames": {},
                "events": [
                    _kill(10000, 3, 1, 100.0, 100.0),
                    _kill(30000, 3, 2, 200.0, 200.0),
                    _kill(45000, 3, 1, 300.0, 300.0),  # 첫 킬과 35초 차 — 같은 윈도우 아님
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)
    assert data.collapse is None


def test_collapse_tie_breaks_to_later_fight() -> None:
    tl = _tl(
        [
            {
                "timestamp": 180000,
                "participantFrames": {},
                "events": [
                    _kill(10000, 3, 1, 100.0, 100.0),
                    _kill(20000, 3, 2, 200.0, 200.0),
                    _kill(29000, 4, 1, 300.0, 300.0),   # 1차: 3킬
                    _kill(100000, 4, 2, 400.0, 400.0),
                    _kill(110000, 3, 1, 500.0, 500.0),
                    _kill(119000, 4, 2, 600.0, 600.0),  # 2차: 3킬 (동률 → 늦은 쪽)
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)
    assert data.collapse is not None
    assert data.collapse.timestamp == 119000


def test_collapse_ignores_mixed_team_kills() -> None:
    tl = _tl(
        [
            {
                "timestamp": 60000,
                "participantFrames": {},
                "events": [
                    _kill(10000, 3, 1, 100.0, 100.0),
                    _kill(15000, 1, 3, 200.0, 200.0),   # 다른 팀 킬
                    _kill(20000, 4, 2, 300.0, 300.0),
                ],
            }
        ]
    )
    data = build_kill_map(tl, MATCH, my_participant_id=1)
    assert data.collapse is None


def test_compute_bounds_from_frames_and_kills() -> None:
    info = {
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 100, "y": 200}},
                    "2": {"position": {"x": 14000, "y": 13000}},
                },
                "events": [_kill(30000, 3, 1, 0.0, 0.0)],
            }
        ]
    }
    bounds = compute_bounds(info)
    x0, x1, y0, y1 = bounds
    assert x0 < 0 < x1 and y0 < 0 < y1  # 여백 포함
    assert x1 > 14000 and y1 > 13000
    # 데이터 없는 경우 안전 기본값
    assert compute_bounds({"frames": []}) == (0.0, 1.0, 0.0, 1.0)


def test_game_to_pixel_maps_and_flips_y() -> None:
    bounds = (0.0, 1000.0, 0.0, 1000.0)
    size = 100
    # 여백 3%: px = 3 + 0.94 * fx * size
    px0, py0 = game_to_pixel(0.0, 0.0, bounds, size)
    assert px0 == 3 and py0 == 97  # y 최소 → 이미지 아래쪽 (플립)
    px1, py1 = game_to_pixel(1000.0, 1000.0, bounds, size)
    assert px1 == 97 and py1 == 3


def test_game_to_pixel_clamps_out_of_range() -> None:
    bounds = (0.0, 1000.0, 0.0, 1000.0)
    px, py = game_to_pixel(-5000.0, 99999.0, bounds, 100)
    assert px == 3 and py == 3  # 클램프 후 여백 위치


def test_flatten_events_includes_legacy_top_level_events() -> None:
    info = {
        "events": [{"type": "CHAMPION_KILL", "timestamp": 50000}],
        "frames": [
            {"timestamp": 60000, "events": [{"type": "WARD_PLACED", "timestamp": 30000}]}
        ],
    }
    events = flatten_events(info)
    assert [e["timestamp"] for e in events] == [30000, 50000]
