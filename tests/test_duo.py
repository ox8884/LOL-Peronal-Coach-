"""듀오 통계 단위 테스트."""

from __future__ import annotations

from lol_coach.analysis.duo import analyze_duos
from lol_coach.riot.models import MatchPlayer, MatchSummary, PlayerProfile, RecentForm


def _match(win: bool, allies: list[str]) -> MatchSummary:
    team = [
        MatchPlayer(
            champion_name="X",
            champion_id=1,
            role="MIDDLE",
            team_id=100,
            kills=1,
            deaths=1,
            assists=1,
            cs=100,
            gold=5000,
            damage_to_champs=5000,
            vision_score=10,
            champ_level=10,
            riot_id=rid,
            is_me=False,
            win=win,
        )
        for rid in allies
    ]
    return MatchSummary(
        match_id="m",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MIDDLE",
        win=win,
        kills=5,
        deaths=3,
        assists=7,
        cs=180,
        gold=12000,
        damage_to_champs=20000,
        vision_score=20,
        game_duration_s=1800,
        queue_id=420,
        ally_team=team,
    )


def test_duo_counts_and_wr() -> None:
    matches = [
        _match(True, ["Friend#KR1", "Other#KR1"]),
        _match(True, ["Friend#KR1"]),
        _match(False, ["Friend#KR1"]),
        _match(True, ["Solo#KR1"]),  # only 1 game with Solo — filtered
    ]
    form = RecentForm(
        profile=PlayerProfile("Me", "KR1", "puuid", "kr"),
        matches=matches,
        wins=3,
        losses=1,
        avg_kda=2.0,
        avg_cs_per_min=6.0,
        role_counts={},
        champion_stats={},
    )
    rep = analyze_duos(form, min_games=2)
    assert len(rep.partners) == 1
    assert rep.partners[0].riot_id == "Friend#KR1"
    assert rep.partners[0].games == 3
    assert rep.partners[0].wins == 2
    assert rep.partners[0].winrate == round(100 * 2 / 3, 1)


def test_duo_empty_without_ids() -> None:
    m = _match(True, [])
    form = RecentForm(
        profile=PlayerProfile("Me", "KR1", "p", "kr"),
        matches=[m],
        wins=1,
        losses=0,
        avg_kda=1.0,
        avg_cs_per_min=6.0,
        role_counts={},
        champion_stats={},
    )
    rep = analyze_duos(form, min_games=1)
    assert rep.partners == []
