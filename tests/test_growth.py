from __future__ import annotations

import json
from pathlib import Path

from lol_coach.analysis.growth import (
    PracticeProgress,
    analyze_growth,
    diagnose_playstyle,
    growth_share_lines,
    load_growth,
    merge_match_history,
    records_from_form,
    render_growth_card,
    sync_practice_progress,
)
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm

DAY_MS = 24 * 60 * 60 * 1000


def _match(
    match_id: str,
    *,
    ended_at_ms: int,
    win: bool,
    deaths: int = 4,
    duration_s: int = 1800,
    kda_kills: int = 6,
) -> MatchSummary:
    return MatchSummary(
        match_id=match_id,
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MIDDLE",
        win=win,
        kills=kda_kills,
        deaths=deaths,
        assists=6,
        cs=180,
        gold=11000,
        damage_to_champs=20000,
        vision_score=20,
        game_duration_s=duration_s,
        queue_id=420,
        cs10=70,
        game_end_timestamp=ended_at_ms,
    )


def _form(matches: list[MatchSummary]) -> RecentForm:
    return RecentForm(
        profile=PlayerProfile("테스트", "KR1", "PUUID", "kr"),
        matches=matches,
        wins=sum(m.win for m in matches),
        losses=sum(not m.win for m in matches),
        avg_kda=0.0,
        avg_cs_per_min=0.0,
        role_counts={},
        champion_stats={},
    )


def test_weekly_report_compares_current_and_previous_week() -> None:
    now = 30 * DAY_MS
    matches = [
        _match("C1", ended_at_ms=now - DAY_MS, win=True, deaths=3),
        _match("C2", ended_at_ms=now - 2 * DAY_MS, win=True, deaths=4),
        _match("P1", ended_at_ms=now - 8 * DAY_MS, win=False, deaths=8),
        _match("P2", ended_at_ms=now - 9 * DAY_MS, win=True, deaths=6),
    ]

    report = analyze_growth(records_from_form(_form(matches)), now_ms=now)

    assert report.weekly.current.games == 2
    assert report.weekly.previous.games == 2
    assert report.weekly.winrate_delta == 50.0
    assert report.weekly.deaths_delta == -3.5


def test_habit_scanner_detects_loss_requeue_with_sample_guard() -> None:
    base = 40 * DAY_MS
    matches: list[MatchSummary] = []
    end = base
    for index in range(6):
        matches.append(
            _match(
                f"L{index}",
                ended_at_ms=end,
                win=False,
                deaths=7,
                duration_s=1500,
            )
        )
        end += 35 * 60 * 1000

    report = analyze_growth(records_from_form(_form(matches)), now_ms=end + DAY_MS)

    requeue = next(signal for signal in report.habits if signal.key == "loss_requeue")
    assert requeue.sample_games == 5
    assert requeue.winrate == 0.0
    assert requeue.severity == "bad"


def test_habit_scanner_hides_requeue_when_sample_is_too_small() -> None:
    base = 50 * DAY_MS
    matches = [
        _match("A", ended_at_ms=base, win=False),
        _match("B", ended_at_ms=base + 35 * 60 * 1000, win=True),
    ]

    report = analyze_growth(records_from_form(_form(matches)), now_ms=base + DAY_MS)

    assert all(signal.key != "loss_requeue" for signal in report.habits)


def test_merge_history_deduplicates_and_recovers_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text("not-json", encoding="utf-8")
    match = _match("M1", ended_at_ms=DAY_MS, win=True)

    first = merge_match_history(_form([match]), path=path)
    second = merge_match_history(_form([match]), path=path)

    assert [record.match_id for record in first] == ["M1"]
    assert [record.match_id for record in second] == ["M1"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert len(payload["profiles"]["PUUID"]["matches"]) == 1


def test_practice_progress_grades_only_matches_after_assignment(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    now = 80 * DAY_MS
    initial = _form(
        [
            _match("OLD1", ended_at_ms=now - 1000, win=False, deaths=8),
            _match("OLD2", ended_at_ms=now - 2000, win=False, deaths=9),
            _match("OLD3", ended_at_ms=now - 3000, win=False, deaths=7),
        ]
    )

    assigned = sync_practice_progress(initial, path=path, now_ms=now)
    updated = _form(
        [
            _match("NEW1", ended_at_ms=now + 2000, win=True, deaths=4),
            _match("NEW2", ended_at_ms=now + 1000, win=False, deaths=8),
            *initial.matches,
        ]
    )
    graded = sync_practice_progress(updated, path=path, now_ms=now + 3000)

    assert assigned is not None
    assert assigned.graded_games == 0
    assert graded is not None
    assert graded.graded_games == 2
    assert graded.successes == 1
    assert graded.completion_rate == 50.0


def test_growth_share_card_contains_metrics_and_writes_png(tmp_path: Path) -> None:
    now = 90 * DAY_MS
    records = records_from_form(
        _form(
            [
                _match("C", ended_at_ms=now - DAY_MS, win=True, deaths=3),
                _match("P", ended_at_ms=now - 8 * DAY_MS, win=False, deaths=8),
            ]
        )
    )
    report = analyze_growth(records, now_ms=now)
    practice = PracticeProgress("avoid_death_spike", 7, now - 2 * DAY_MS, 2, 1, 50.0)

    lines = growth_share_lines("테스트#KR1", report, practice)
    output = render_growth_card("테스트#KR1", report, practice, tmp_path / "growth.png")

    assert lines[0] == "테스트#KR1 · 주간 성장 리포트"
    assert any("숙제 달성률 50.0%" in line for line in lines)
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_load_growth_persists_matches_and_returns_report(tmp_path: Path) -> None:
    now = 100 * DAY_MS
    form = _form([_match("M", ended_at_ms=now - DAY_MS, win=True, deaths=3)])

    report, practice = load_growth(form, path=tmp_path / "growth.json", now_ms=now)

    assert report.weekly.current.games == 1
    assert practice is None


def test_playstyle_diagnosis_returns_four_axis_code_with_enough_sample() -> None:
    now = 110 * DAY_MS
    matches = [
        _match(
            f"M{index}",
            ended_at_ms=now - index * DAY_MS,
            win=index % 2 == 0,
            deaths=3 if index % 2 == 0 else 8,
            kda_kills=9,
        )
        for index in range(10)
    ]

    diagnosis = diagnose_playstyle(records_from_form(_form(matches)))

    assert diagnosis is not None
    assert len(diagnosis.code) == 4
    assert diagnosis.sample_games == 10
    assert len(diagnosis.axes) == 4


def test_playstyle_diagnosis_requires_eight_summoners_rift_games() -> None:
    matches = [_match(f"M{index}", ended_at_ms=index * DAY_MS, win=True) for index in range(7)]

    assert diagnose_playstyle(records_from_form(_form(matches))) is None
