from lol_coach.analysis.lcu_match import (
    build_local_form,
    game_id_of,
    lcu_to_match_summary,
    lcu_to_timeline_v5,
    match_id_for,
    try_local_timeline,
)

ME = "채니미#KR1"

PLAYERS = [
    {"participantId": 1, "teamId": 100, "championId": 103, "stats": {}},
    {"participantId": 2, "teamId": 100, "championId": 64, "stats": {}},
    {"participantId": 3, "teamId": 200, "championId": 238, "stats": {}},
    {"participantId": 4, "teamId": 200, "championId": 412, "stats": {}},
]

ME_STATS = {
    "kills": 10, "deaths": 2, "assists": 8,
    "totalMinionsKilled": 180, "neutralMinionsKilled": 20,
    "goldEarned": 12000, "totalDamageDealtToChampions": 25000,
    "visionScore": 18, "win": True, "gameDuration": 1800,
    "item0": 3089, "item1": 3157, "item2": 0,
    "spell1Id": 4, "spell2Id": 7,
    "perkPrimaryStyle": 8100, "perkSubStyle": 8300,
    "totalDamageTaken": 15000, "wardsPlaced": 10, "wardsKilled": 3,
    "detectorWardsPlaced": 2, "turretKills": 1, "inhibitorKills": 0,
    "firstBloodKill": True, "largestMultiKill": 2,
    "totalTimeSpentDead": 90, "dragonKills": 0, "baronKills": 0,
    "champLevel": 16,
}


def _dto(stats: dict | None = None) -> dict:
    players = []
    for p in PLAYERS:
        cp = dict(p)
        if p["participantId"] == 1:
            cp["stats"] = stats if stats is not None else ME_STATS
            cp["timeline"] = {"lane": "MID", "role": "SOLO"}
        else:
            cp["stats"] = {
                "kills": 0, "deaths": 0, "assists": 0,
                "totalMinionsKilled": 0, "neutralMinionsKilled": 0,
                "goldEarned": 0, "totalDamageDealtToChampions": 0,
                "visionScore": 0, "win": False, "gameDuration": 1800,
                "champLevel": 10,
            }
            cp["timeline"] = {"lane": "NONE", "role": "NONE"}
        players.append(cp)
    return {
        "gameId": 5614132333,
        "queueId": 420,
        "gameDuration": 1800,
        "gameCreation": 1785724798858,
        "gameVersion": "16.15.801.3452",
        "gameMode": "CLASSIC",
        "participantIdentities": [
            {"participantId": 1, "player": {"summonerName": "채니미"}},
            {"participantId": 2, "player": {"summonerName": "팀원1"}},
            {"participantId": 3, "player": {"summonerName": "적1"}},
            {"participantId": 4, "player": {"summonerName": "적2"}},
        ],
        "participants": players,
    }


def test_match_id_for_and_game_id_of() -> None:
    assert match_id_for(5614132333) == "KR_5614132333"
    assert match_id_for(5614132333, platform="na1") == "NA1_5614132333"
    assert game_id_of("KR_5614132333") == 5614132333
    assert game_id_of("NA1_123") == 123
    assert game_id_of("garbage") is None


def test_lcu_to_match_summary_maps_core_fields() -> None:
    ms = lcu_to_match_summary(_dto(), my_summoner_name="채니미")

    assert ms is not None
    assert ms.match_id == "KR_5614132333"
    assert ms.champion_id == 103
    assert ms.champion_name == "103"  # id_to_key 없으면 str(id) 폴백
    assert ms.role == "MIDDLE"
    assert ms.lane == "MID"
    assert ms.win is True
    assert ms.kills == 10 and ms.deaths == 2 and ms.assists == 8
    assert ms.cs == 200
    assert ms.gold == 12000
    assert ms.damage_to_champs == 25000
    assert ms.vision_score == 18
    assert ms.game_duration_s == 1800
    assert ms.queue_id == 420
    assert ms.game_version == "16.15.801.3452"
    assert ms.game_end_timestamp == 1785724798858
    assert ms.items[:2] == [3089, 3157]
    assert ms.summoner_spells == [4, 7]
    assert ms.primary_rune == 8100
    assert ms.champ_level == 16
    assert ms.first_blood is True
    assert ms.largest_multi_kill == 2
    assert ms.time_dead_s == 90
    assert ms.wards_placed == 10
    assert len(ms.ally_team) == 2 and len(ms.enemy_team) == 2
    assert any(p.is_me for p in ms.ally_team)


def test_lcu_to_match_summary_uses_id_to_key() -> None:
    ms = lcu_to_match_summary(
        _dto(),
        my_summoner_name="채니미",
        id_to_key=lambda cid: {103: "Ahri", 64: "LeeSin", 238: "Zed", 412: "Thresh"}[cid],
    )
    assert ms is not None
    assert ms.champion_name == "Ahri"
    assert {p.champion_name for p in ms.enemy_team} == {"Zed", "Thresh"}


def test_lcu_to_match_summary_returns_none_without_me() -> None:
    assert lcu_to_match_summary(_dto(), my_summoner_name="없는사람") is None
    assert lcu_to_match_summary({"gameId": 0}, my_summoner_name="채니미") is None


def test_lcu_to_timeline_v5_wraps_frames() -> None:
    dto = {
        "frameInterval": 60000,
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 500, "y": 500}},
                    "3": {"position": {"x": 7000, "y": 7000}},
                },
                "events": [
                    {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 7000, "y": 7000}},
                ],
            }
        ],
    }
    v5 = lcu_to_timeline_v5(dto)
    assert v5["info"]["frameInterval"] == 60000
    assert len(v5["info"]["frames"]) == 1
    assert v5["info"]["frames"][0]["events"][0]["type"] == "CHAMPION_KILL"


def test_lcu_timeline_feeds_killmap() -> None:
    from lol_coach.analysis.killmap import build_kill_map

    match = {
        "info": {
            "participants": [
                {"participantId": 1, "teamId": 100, "championId": 103, "championName": "Ahri"},
                {"participantId": 2, "teamId": 100, "championId": 64, "championName": "LeeSin"},
                {"participantId": 3, "teamId": 200, "championId": 238, "championName": "Zed"},
                {"participantId": 4, "teamId": 200, "championId": 412, "championName": "Thresh"},
            ]
        }
    }
    tl_dto = {
        "frameInterval": 60000,
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 1000, "y": 1000}},
                    "2": {"position": {"x": 2000, "y": 1000}},
                    "3": {"position": {"x": 7000, "y": 7000}},
                    "4": {"position": {"x": 7100, "y": 6900}},
                },
                "events": [
                    {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 1500, "y": 1500}},
                    {"type": "CHAMPION_KILL", "timestamp": 35000, "killerId": 1, "victimId": 4, "position": {"x": 6900, "y": 7000}},
                    {"type": "CHAMPION_KILL", "timestamp": 40000, "killerId": 4, "victimId": 2, "position": {"x": 4000, "y": 3000}},
                    {"type": "CHAMPION_KILL", "timestamp": 55000, "killerId": 3, "victimId": 1, "position": {"x": 7200, "y": 6800}},
                ],
            }
        ],
    }
    data = build_kill_map(lcu_to_timeline_v5(tl_dto), match, my_participant_id=1)
    assert len(data.my_deaths) == 2
    assert len(data.my_kills) == 1
    assert data.collapse is not None and data.collapse.timestamp == 55000


def test_build_local_form_collects_recent_matches() -> None:
    from lol_coach.riot.models import PlayerProfile

    class FakeLCU:
        def current_summoner_name(self) -> str:
            return "채니미"

        def match_history(self, beg_index: int, end_index: int) -> list[dict]:
            assert beg_index == 0 and end_index == 15
            return [{"gameId": 1}, {"gameId": 2}, {"gameId": 0}]

        def match_detail(self, game_id: int):
            return _dto()

    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")
    form, err = build_local_form(FakeLCU(), 15, profile)
    assert err == ""
    assert form is not None and form.games == 2
    assert all(m.match_id in ("KR_1", "KR_2") for m in form.matches)


def test_build_local_form_reports_error_when_lcu_empty() -> None:
    from lol_coach.riot.models import PlayerProfile

    class FakeLCU:
        def current_summoner_name(self) -> str:
            return "채니미"

        def match_history(self, beg_index: int, end_index: int) -> list[dict]:
            return []

        def match_detail(self, game_id: int):
            raise AssertionError("호출되면 안 됨")

    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")
    form, err = build_local_form(FakeLCU(), 15, profile)
    assert form is None
    assert "전적이 없습니다" in err


def test_try_local_timeline_returns_v5_and_match() -> None:
    class FakeLCU:
        def match_timeline(self, game_id: int):
            assert game_id == 5614132333
            return {"frames": [], "frameInterval": 60000}

        def match_detail(self, game_id: int):
            return {"gameId": game_id, "participants": []}

    tl, match = try_local_timeline(FakeLCU(), "KR_5614132333")
    assert tl["info"]["frameInterval"] == 60000
    assert match["info"]["participants"] == []


def test_try_local_timeline_none_when_no_endpoint() -> None:
    class FakeLCU:
        def match_timeline(self, game_id: int):
            return None

        def match_detail(self, game_id: int):
            raise AssertionError("타임라인 없으면 상세도 호출하지 않음")

    assert try_local_timeline(FakeLCU(), "KR_5614132333") is None
    assert try_local_timeline(FakeLCU(), "not_a_match_id") is None


def test_try_local_timeline_participant_index_works() -> None:
    from lol_coach.analysis.killmap import build_kill_map, participant_index

    class FakeLCU:
        def match_timeline(self, game_id: int):
            return {
                "frameInterval": 60000,
                "frames": [
                    {
                        "timestamp": 60000,
                        "participantFrames": {
                            "1": {"position": {"x": 1000, "y": 1000}},
                            "3": {"position": {"x": 7000, "y": 7000}},
                        },
                        "events": [
                            {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 1500, "y": 1500}},
                            {"type": "CHAMPION_KILL", "timestamp": 40000, "killerId": 4, "victimId": 2, "position": {"x": 4000, "y": 3000}},
                            {"type": "CHAMPION_KILL", "timestamp": 55000, "killerId": 3, "victimId": 1, "position": {"x": 7200, "y": 6800}},
                        ],
                    }
                ],
            }

        def match_detail(self, game_id: int):
            return {
                "gameId": game_id,
                "participants": [
                    {"participantId": 1, "teamId": 100, "championId": 103},
                    {"participantId": 2, "teamId": 100, "championId": 64},
                    {"participantId": 3, "teamId": 200, "championId": 238},
                    {"participantId": 4, "teamId": 200, "championId": 412},
                ],
            }

    tl, match = try_local_timeline(FakeLCU(), "KR_5614132333")
    idx = participant_index(match)
    assert idx[3].team_id == 200 and idx[1].team_id == 100

    data = build_kill_map(tl, match, my_participant_id=1)
    assert len(data.my_deaths) == 2
    assert data.collapse is not None  # 팀 판정이 살아 있으면 붕괴가 잡힌다
    assert data.collapse.winning_team == 200
