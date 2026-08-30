"""analysis.session — 오늘의 세션 리포트 단위 테스트."""

from __future__ import annotations

from datetime import datetime
from datetime import time as dt_time

from lol_coach.analysis.session import analyze_session, filter_today
from lol_coach.riot.models import MatchSummary


def _make(
    *,
    end_dt: datetime,
    win: bool,
    champ: str = "아리",
    kills: int = 6,
    deaths: int = 3,
    assists: int = 8,
) -> MatchSummary:
    return MatchSummary(
        match_id=f"KR_{end_dt.timestamp()}_{champ}",
        champion_name=champ,
        champion_id=0,
        role="MIDDLE",
        lane="MIDDLE",
        win=win,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=200,
        gold=12000,
        damage_to_champs=20000,
        vision_score=20,
        game_duration_s=1800,
        queue_id=420,
        game_end_timestamp=int(end_dt.timestamp() * 1000),
    )


def test_filter_today_and_report_counts() -> None:
    now = datetime(2026, 8, 28, 21, 0)
    midnight = datetime.combine(now.date(), dt_time.min)
    yesterday = datetime(2026, 8, 27, 23, 0)

    matches = [
        _make(end_dt=midnight.replace(hour=1), win=True),
        _make(end_dt=midnight.replace(hour=3), win=False),
        _make(end_dt=now.replace(hour=20), win=True),
        _make(end_dt=yesterday, win=True),  # 어제 — 제외
    ]
    today = filter_today(matches, now_s=now.timestamp())
    assert len(today) == 3

    rep = analyze_session(matches, now_s=now.timestamp())
    assert len(rep.matches) == 3
    assert rep.wins == 2
    assert rep.losses == 1
    assert rep.winrate == 66.7
    # 최신 기준: 승 → 연승 1
    assert rep.streak == 1
    assert rep.top_champs and rep.top_champs[0][0] == "아리"
    assert rep.lines and rep.lines[0].startswith("3게임 2승 1패")


def test_lose_streak_flagged() -> None:
    now = datetime(2026, 8, 28, 23, 0)
    matches = [
        _make(end_dt=datetime(2026, 8, 28, 18), win=False),
        _make(end_dt=datetime(2026, 8, 28, 19), win=False),
        _make(end_dt=datetime(2026, 8, 28, 20), win=False),
    ]
    rep = analyze_session(matches, now_s=now.timestamp())
    assert rep.streak == -3
    assert any("연패" in line for line in rep.lines)


def test_empty_day_is_safe() -> None:
    rep = analyze_session([], now_s=datetime(2026, 8, 28, 12).timestamp())
    assert rep.matches == []
    assert rep.lines == []
