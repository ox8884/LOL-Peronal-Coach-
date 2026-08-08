from types import SimpleNamespace

from lol_coach.gui import app as app_module


def test_game_end_does_not_change_current_tab() -> None:
    tab_changes: list[str] = []
    status_updates: list[str] = []

    app = SimpleNamespace(
        loc=SimpleNamespace(champion=lambda name: name),
        status=SimpleNamespace(
            configure=lambda **kwargs: status_updates.append(kwargs["text"])
        ),
        tabs=SimpleNamespace(set=lambda name: tab_changes.append(name)),
        _notify_game_end=lambda champ, win: None,
        _show_match_detail=lambda match: None,
    )
    match = SimpleNamespace(champion_name="Caitlyn", win=True)

    app_module.CoachApp._on_game_ended(app, match)

    assert status_updates
    assert tab_changes == []


def test_notify_game_end_respects_toggle() -> None:
    """알림 OFF면 소리/플래시 경로를 타지 않는다."""
    app_off = SimpleNamespace(
        _game_end_notify_on=lambda: False,
        winfo_id=lambda: (_ for _ in ()).throw(AssertionError("should not flash")),
    )
    app_module.CoachApp._notify_game_end(app_off, "케이틀린", True)

    # ON이면 예외 없이 실행 (winsound/ctypes 실패해도 무해)
    app_on = SimpleNamespace(
        _game_end_notify_on=lambda: True,
        winfo_id=lambda: 1,
    )
    app_module.CoachApp._notify_game_end(app_on, "케이틀린", False)


def test_game_end_notify_on_reads_var() -> None:
    app = SimpleNamespace(game_end_notify_var=SimpleNamespace(get=lambda: False))
    assert app_module.CoachApp._game_end_notify_on(app) is False
    app.game_end_notify_var = SimpleNamespace(get=lambda: True)
    assert app_module.CoachApp._game_end_notify_on(app) is True


def test_match_nav_prev_next() -> None:
    """이전/다음 복기 네비가 인덱스를 따라 이동한다."""
    shown: list[str] = []
    m0 = SimpleNamespace(match_id="A")
    m1 = SimpleNamespace(match_id="B")
    m2 = SimpleNamespace(match_id="C")
    app = SimpleNamespace(
        form=SimpleNamespace(matches=[m0, m1, m2]),
        _me_match_index=1,
        _show_match_detail=lambda m: shown.append(m.match_id),
        _notify=lambda *a, **k: None,
    )
    app_module.CoachApp._nav_match(app, -1)
    app_module.CoachApp._nav_match(app, 1)
    # index was 1; after -1 would show A, but _nav_match uses _me_match_index
    # without updating unless _show_match_detail does — we mock show so index stays 1
    # first call: 1-1=0 → A; second: still index 1 → 1+1=2 → C
    assert shown == ["A", "C"]


def test_match_index_of() -> None:
    m0 = SimpleNamespace(match_id="A")
    m1 = SimpleNamespace(match_id="B")
    app = SimpleNamespace(form=SimpleNamespace(matches=[m0, m1]))
    assert app_module.CoachApp._match_index_of(app, m1) == 1
    assert app_module.CoachApp._match_index_of(app, SimpleNamespace(match_id="Z")) is None


def test_ai_key_points_prioritize_actionable_lines() -> None:
    text = """
    배경 설명
    핵심: 먼저 뒤에서 포킹하세요.
    아이템: 세 번째 코어는 방어 아이템입니다.
    주의: 암살자 진입 때 점멸을 아끼세요.
    """

    points = app_module._ai_key_points(text, limit=2)

    assert points == [
        "핵심: 먼저 뒤에서 포킹하세요.",
        "주의: 암살자 진입 때 점멸을 아끼세요.",
    ]
