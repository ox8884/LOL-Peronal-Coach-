"""전적 트렌드 분석 단위 테스트."""

from __future__ import annotations

from lol_coach.analysis.trends import analyze_trends
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm


def _m(
    *,
    win: bool,
    deaths: int = 4,
    kills: int = 5,
    assists: int = 5,
    cs: int = 180,
    dur: int = 1800,
    cs10: int | None = 70,
    champ: str = "Ahri",
) -> MatchSummary:
    return MatchSummary(
        match_id="x",
        champion_name=champ,
        champion_id=1,
        role="MIDDLE",
        lane="MIDDLE",
        win=win,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=cs,
        gold=10000,
        damage_to_champs=20000,
        vision_score=20,
        game_duration_s=dur,
        queue_id=420,
        cs10=cs10,
    )


def test_empty_form() -> None:
    form = RecentForm(
        profile=PlayerProfile("a", "b", "p", "kr"),
        matches=[],
        wins=0,
        losses=0,
        avg_kda=0.0,
        avg_cs_per_min=0.0,
        role_counts={},
        champion_stats={},
    )
    rep = analyze_trends(form)
    assert rep.games == 0
    assert rep.lines


def test_losing_streak_and_high_deaths() -> None:
    matches = [_m(win=False, deaths=9) for _ in range(4)] + [
        _m(win=True, deaths=2)
    ]
    form = RecentForm(
        profile=PlayerProfile("a", "b", "p", "kr"),
        matches=matches,
        wins=1,
        losses=4,
        avg_kda=1.0,
        avg_cs_per_min=6.0,
        role_counts={},
        champion_stats={},
    )
    rep = analyze_trends(form, recent_n=5)
    labels = " ".join(x.label for x in rep.lines)
    assert "연패" in labels or "데스" in labels
    assert rep.avg_deaths >= 7.0


def test_win_rate_delta() -> None:
    # recent 5 wins, older 5 losses
    matches = [_m(win=True) for _ in range(5)] + [_m(win=False) for _ in range(5)]
    form = RecentForm(
        profile=PlayerProfile("a", "b", "p", "kr"),
        matches=matches,
        wins=5,
        losses=5,
        avg_kda=3.0,
        avg_cs_per_min=7.0,
        role_counts={},
        champion_stats={},
    )
    rep = analyze_trends(form, recent_n=5)
    assert rep.recent_wr == 100.0
    assert rep.older_wr == 0.0
    assert any("상승" in x.label for x in rep.lines)
    assert len(rep.win_sequence) == 10
    assert all(rep.win_sequence[:5])  # recent wins first
    assert len(rep.kda_sequence) == 10
