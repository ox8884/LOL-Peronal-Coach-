from lol_coach.analysis.live_fill import parse_live_game
from lol_coach.riot.models import LiveGame


class FakeDataDragon:
    def __init__(self) -> None:
        champions = [
            (1, "Garen", "가렌", ["Fighter", "Tank"]),
            (2, "Kennen", "케넨", ["Mage", "Fighter"]),
            (3, "LeeSin", "리 신", ["Fighter", "Assassin"]),
            (4, "Zed", "제드", ["Assassin"]),
            (5, "Jinx", "징크스", ["Marksman"]),
            (6, "Leona", "레오나", ["Tank", "Support"]),
        ]
        self._champions_by_id = {
            champion_id: {"id": key, "name": name, "tags": tags}
            for champion_id, key, name, tags in champions
        }

    def ensure_loaded(self) -> None:
        return None


def test_live_fill_assigns_roles_by_team_fit_not_participant_order() -> None:
    game = LiveGame(
        game_id=1,
        game_mode="CLASSIC",
        game_type="MATCHED_GAME",
        game_queue_config_id=420,
        map_id=11,
        game_start_time=0,
        game_length=0,
        participants=[
            {"puuid": "me", "teamId": 100, "championId": 1},
            {"teamId": 200, "championId": 2, "spell1Id": 4, "spell2Id": 12},
            {"teamId": 200, "championId": 3, "spell1Id": 4, "spell2Id": 11},
            {"teamId": 200, "championId": 4, "spell1Id": 4, "spell2Id": 14},
            {"teamId": 200, "championId": 5, "spell1Id": 4, "spell2Id": 7},
            {"teamId": 200, "championId": 6, "spell1Id": 4, "spell2Id": 14},
        ],
        my_team_id=100,
        my_champion_id=1,
    )

    result = parse_live_game(game, FakeDataDragon(), my_puuid="me")
    assert result.is_mayhem is False

    assert {role: champion[0] for role, champion in result.enemies_by_role.items()} == {
        "top": "Kennen",
        "jungle": "LeeSin",
        "mid": "Zed",
        "adc": "Jinx",
        "support": "Leona",
    }


def test_live_fill_marks_mayhem_queue() -> None:
    game = LiveGame(
        game_id=2,
        game_mode="ARAM",
        game_type="MATCHED_GAME",
        game_queue_config_id=2400,
        map_id=12,
        game_start_time=0,
        game_length=0,
        participants=[{"puuid": "me", "teamId": 100, "championId": 4}],
        my_team_id=100,
        my_champion_id=4,
    )
    result = parse_live_game(game, FakeDataDragon(), my_puuid="me")
    assert result.is_aram is True
    assert result.is_mayhem is True
    assert result.my_champ_key == "Zed"
