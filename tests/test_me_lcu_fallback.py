from lol_coach.analysis.lcu_match import build_local_form
from lol_coach.gui.me_tab import _compose_me_load_error
from lol_coach.riot.models import PlayerProfile


def test_compose_me_load_error_prefers_riot_message() -> None:
    assert "키가 만료" in _compose_me_load_error(
        "Riot API 키가 만료되었거나 올바르지 않습니다.",
        "클라이언트 lockfile은 있지만 연결이 되지 않습니다.",
    )
    assert "대체 전적도 실패" in _compose_me_load_error("API 실패", "LCU 실패")
    assert _compose_me_load_error("", "클라이언트만 실패") == "클라이언트만 실패"
    assert _compose_me_load_error("", "") == "전적을 불러오지 못했습니다."


def _fake_lcu(games: list[dict], details: dict[int, dict]):
    class FakeLCU:
        def current_summoner_name(self):
            return "채니미"

        def match_history(self, beg_index, end_index):
            return games

        def match_detail(self, game_id):
            return details[game_id]

    return FakeLCU()


def test_local_form_via_fake_lcu() -> None:
    dto = {
        "gameId": 7,
        "queueId": 420,
        "gameDuration": 1500,
        "gameCreation": 1785724798858,
        "gameVersion": "16.15",
        "gameMode": "CLASSIC",
        "participantIdentities": [
            {"participantId": 1, "player": {"summonerName": "채니미"}},
            {"participantId": 2, "player": {"summonerName": "적"}},
        ],
        "participants": [
            {
                "participantId": 1,
                "teamId": 100,
                "championId": 103,
                "timeline": {"lane": "MID", "role": "SOLO"},
                "stats": {
                    "kills": 3, "deaths": 5, "assists": 7,
                    "totalMinionsKilled": 120, "neutralMinionsKilled": 0,
                    "goldEarned": 9000, "totalDamageDealtToChampions": 18000,
                    "visionScore": 10, "win": False, "gameDuration": 1500,
                    "champLevel": 13,
                },
            },
            {
                "participantId": 2,
                "teamId": 200,
                "championId": 238,
                "timeline": {"lane": "MID", "role": "SOLO"},
                "stats": {
                    "kills": 8, "deaths": 2, "assists": 4,
                    "totalMinionsKilled": 150, "neutralMinionsKilled": 0,
                    "goldEarned": 12000, "totalDamageDealtToChampions": 24000,
                    "visionScore": 12, "win": True, "gameDuration": 1500,
                    "champLevel": 14,
                },
            },
        ],
    }
    lcu = _fake_lcu([{"gameId": 7}], {7: dto})
    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")

    form, err = build_local_form(lcu, 15, profile)

    assert err == ""
    assert form is not None
    assert form.games == 1
    m = form.matches[0]
    assert m.match_id == "KR_7"
    assert m.win is False
    assert m.deaths == 5
    assert len([p for p in m.ally_team if not p.is_me]) == 0  # 본인 제외 아군 없음
    assert len(m.enemy_team) == 1
