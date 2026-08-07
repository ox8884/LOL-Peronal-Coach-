"""밴 추천 변환 테스트."""

from __future__ import annotations

from lol_coach.analysis.bans import ban_report_from_counters, merge_lcu_bans
from lol_coach.ugg.counters import CounterPick, CounterReport


def test_ban_report_from_counters() -> None:
    report = CounterReport(
        enemy="Ahri",
        role="mid",
        patch="15.1",
        source_url="https://u.gg/x",
        lane_counters=[
            CounterPick("Fizz", 400, 10000),
            CounterPick("Yasuo", 200, 8000),
        ],
    )
    bans = ban_report_from_counters(report, my_champ="Ahri", limit=5)
    assert bans.my_champ == "Ahri"
    assert len(bans.bans) == 2
    assert bans.bans[0].champion == "Fizz"
    assert "GD@15" in bans.bans[0].reason


def test_merge_lcu_bans_moves_already_banned() -> None:
    report = CounterReport(
        enemy="Ahri",
        role="mid",
        patch="15.1",
        source_url="u",
        lane_counters=[
            CounterPick("Fizz", 400, 1000),
            CounterPick("Yasuo", 200, 1000),
        ],
    )
    bans = ban_report_from_counters(report, my_champ="Ahri")
    bans = merge_lcu_bans(bans, ["Fizz"])
    assert bans.bans[0].champion == "Yasuo"
    assert bans.bans[1].champion == "Fizz"
    assert "이미 밴" in bans.bans[1].reason
