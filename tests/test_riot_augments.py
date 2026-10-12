from lol_coach.riot.client import RiotClient


def test_summarize_match_reads_player_augment_ids() -> None:
    me = {
        "puuid": "ME", "teamId": 100, "championName": "Ahri", "win": True,
        "playerAugment1": 57, "playerAugment2": 0, "playerAugment3": 1201,
    }
    match = {
        "metadata": {"matchId": "KR_1"},
        "info": {"queueId": 2400, "gameDuration": 900, "participants": [me], "teams": []},
    }
    client = RiotClient.__new__(RiotClient)
    m = client.summarize_match(match, "ME")
    assert m is not None
    assert m.augment_ids == [57, 1201]
