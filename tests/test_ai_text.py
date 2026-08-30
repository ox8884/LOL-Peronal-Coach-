"""gui.ai_text — 요약 정리기(반복 루프 방어) 단위 테스트.

v1.6.104에서 LLM이 'prowess prowess…' 를 수천 번 반복해 위젯을
채워버린 사건의 회귀 방지.
"""

from __future__ import annotations

from lol_coach.gui.ai_text import sanitize_summary_lines


def test_collapses_repeated_token_loops() -> None:
    line = "• 핵심: " + "prowess " * 60
    out = sanitize_summary_lines([line])
    assert len(out) == 1
    assert len(out[0]) < 60
    assert out[0].count("prowess") == 1  # 반복은 한 번만 남기고 접힘


def test_caps_line_and_total() -> None:
    lines = ["x" * 500, "정상 줄", "y" * 500]
    out = sanitize_summary_lines(lines)
    assert all(len(x) <= 240 for x in out)
    assert "정상 줄" in out


def test_max_lines_truncates() -> None:
    out = sanitize_summary_lines([f"줄{i}" for i in range(200)], max_lines=10)
    assert len(out) <= 11
    assert out[-1] == "(이하 생략)"


def test_empty_is_safe() -> None:
    assert sanitize_summary_lines([]) == []
