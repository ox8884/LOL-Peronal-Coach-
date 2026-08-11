from lol_coach.analysis.trends import analyze_trends
from lol_coach.riot.client import aggregate_form
from lol_coach.riot.models import MatchSummary, PlayerProfile


def _match(match_id: str, deaths: int) -> MatchSummary:
    return MatchSummary(
        match_id=match_id,
        champion_name="Ahri",
        champion_id=1,
        role="MIDDLE",
        lane="MIDDLE",
        win=deaths < 7,
        kills=5,
        deaths=deaths,
        assists=7,
        cs=180,
        gold=10_000,
        damage_to_champs=20_000,
        vision_score=20,
        game_duration_s=1_500,
        queue_id=420,
        game_version="15.1",
    )


def test_recurring_pattern_produces_one_evidence_backed_practice_target() -> None:
    profile = PlayerProfile(
        game_name="Jay",
        tag_line="KR1",
        puuid="PUUID",
        platform="kr",
    )
    form = aggregate_form(
        profile,
        [
            _match("M-1", 8),
            _match("M-2", 2),
            _match("M-3", 9),
            _match("M-4", 3),
            _match("M-5", 10),
        ],
    )

    report = analyze_trends(form, recent_n=5)
    target = report.practice_target

    assert target is not None
    assert target.metric == "deaths"
    assert target.threshold == 7
    assert target.observed_games == 3
    assert target.sample_games == 5
    assert target.match_ids == ("M-1", "M-3", "M-5")
    assert target.action_key == "avoid_death_spike"
