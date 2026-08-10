"""display / analysis.stats 포맷터 단위 테스트 — CLI 출력 회귀 방지."""

from lol_coach.analysis.stats import format_recent_form
from lol_coach.display import (
    games,
    join_items,
    pct,
    platform_ko,
    rank_filter_ko,
    rank_line,
    result_ko,
    wr_short,
)
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm


def _match() -> MatchSummary:
    return MatchSummary(
        match_id="KR_1",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MID",
        win=True,
        kills=8,
        deaths=2,
        assists=9,
        cs=210,
        gold=12500,
        damage_to_champs=23000,
        vision_score=22,
        game_duration_s=1800,
        queue_id=420,
        kill_participation=0.55,
        damage_share=0.3,
    )


def _form() -> RecentForm:
    return RecentForm(
        profile=PlayerProfile(
            game_name="테스터", tag_line="KR1", puuid="p", platform="kr"
        ),
        matches=[],
        wins=0,
        losses=0,
        avg_kda=0.0,
        avg_cs_per_min=0.0,
        role_counts={},
        champion_stats={},
    )


def test_pct_and_games() -> None:
    assert pct(51.4, 1) == "51.4%"
    assert pct(None) == "—"
    assert games(15000) == "1.5만 게임"
    assert games(10000) == "1만 게임"
    assert games(999) == "999게임"
    assert games(None) == "—"


def test_wr_short_units() -> None:
    assert wr_short(52.4) == "52.4%"
    assert wr_short(52.4, 15234) == "52.4% · 1.5만"
    assert wr_short(52.4, 6800) == "52.4% · 6.8천"
    assert wr_short(52.4, 500) == "52.4% · 500"
    assert wr_short(None) == ""


def test_join_and_rank_filter() -> None:
    assert join_items(["A", "", "B"]) == "A → B"
    assert join_items([]) == ""
    assert rank_filter_ko("emerald+") == "에메랄드+"
    assert rank_filter_ko("diamond +") == "다이아+"
    assert rank_filter_ko("all ranks") == "전체"
    assert rank_filter_ko("") == "전체"
    assert rank_filter_ko("칼바람") == "칼바람"


def test_platform_and_result_ko() -> None:
    assert platform_ko("kr") == "한국"
    assert platform_ko("NA1") == "북미"
    assert platform_ko("xx1") == "XX1"
    assert result_ko(True) == "승"
    assert result_ko(False) == "패"


def test_rank_line_summary() -> None:
    ranks = [
        type("R", (), {"queue_type": "RANKED_SOLO_5x5", "tier": "EMERALD", "rank": "II", "league_points": 93, "wins": 12, "losses": 10, "winrate": 54.5})(),
        type("R", (), {"queue_type": "RANKED_FLEX_SR", "tier": "GOLD", "rank": "IV", "league_points": 20, "wins": 3, "losses": 5, "winrate": 37.5})(),
    ]
    out = rank_line(ranks)
    assert "솔로 랭크" in out and "에메랄드" in out and "93LP" in out
    assert "자유 랭크" in out and "골드" in out
    assert rank_line([]) == ""


def test_format_recent_form_empty() -> None:
    out = format_recent_form(_form())
    assert "테스터#KR1" in out
    assert "0게임" in out
    assert "경기 없음" in out


def test_format_recent_form_with_match() -> None:
    form = _form()
    form.matches = [_match()]
    form.wins = 1
    form.losses = 0
    out = format_recent_form(form)
    assert "아리" in out or "Ahri" in out
    assert "[승]" in out
