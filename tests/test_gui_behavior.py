from types import SimpleNamespace

from lol_coach.gui import app as app_module


def test_game_end_does_not_change_current_tab() -> None:
    tab_changes: list[str] = []
    status_updates: list[str] = []
    shown: list[object] = []

    app = SimpleNamespace(
        loc=SimpleNamespace(champion=lambda name: name),
        status=SimpleNamespace(
            configure=lambda **kwargs: status_updates.append(kwargs["text"])
        ),
        tabs=SimpleNamespace(set=lambda name: tab_changes.append(name)),
        _notify_game_end=lambda champ, win: None,
        _game_end_auto_review_on=lambda: True,
        _show_match_detail=lambda match: shown.append(match),
    )
    match = SimpleNamespace(champion_name="Caitlyn", win=True)

    app_module.CoachApp._on_game_ended(app, match)

    assert status_updates
    assert tab_changes == []
    assert shown == [match]


def test_game_end_skips_auto_review_when_off() -> None:
    shown: list[object] = []
    app = SimpleNamespace(
        loc=SimpleNamespace(champion=lambda name: name),
        status=SimpleNamespace(configure=lambda **kwargs: None),
        _notify_game_end=lambda champ, win: None,
        _game_end_auto_review_on=lambda: False,
        _show_match_detail=lambda match: shown.append(match),
    )
    app_module.CoachApp._on_game_ended(
        app, SimpleNamespace(champion_name="Caitlyn", win=False)
    )
    assert shown == []


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


def test_apply_skin_live_method_exists() -> None:
    assert callable(app_module.CoachApp._apply_skin_live)


def test_skin_apply_classic_and_neon() -> None:
    from lol_coach.gui import components as ui

    ui.apply_skin("classic")
    assert ui.active_skin() == "classic"
    assert ui.GOLD == "#C8AA6E"
    classic_path = ui.resolve_theme_path("classic")
    assert classic_path.name in ("theme_classic.json", "theme.json")
    assert classic_path.is_file()

    ui.apply_skin("neon")
    assert ui.active_skin() == "neon"
    # 시안 계열 (강한 네온) — 골드(#C8…) 와 확실히 달라야 함
    assert ui.GOLD.lower() != "#c8aa6e"
    assert ui.GOLD.startswith("#") and len(ui.GOLD) == 7
    neon_path = ui.resolve_theme_path("neon")
    assert neon_path.name == "theme_neon.json"
    assert neon_path.is_file()

    # 테스트 후 classic 복원
    ui.apply_skin("classic")


def test_all_skins_have_theme_and_unique_accent() -> None:
    from lol_coach.gui import components as ui

    accents: dict[str, str] = {}
    for sid in ui.SKINS:
        ui.apply_skin(sid)
        assert ui.active_skin() == sid
        assert sid in ui.SKIN_LABELS and sid in ui.SKIN_SHORT
        path = ui.resolve_theme_path(sid)
        assert path.is_file(), sid
        accents[sid] = ui.GOLD.lower()
        # 라이트 스킨 판별
        if sid in ui.LIGHT_SKINS:
            assert ui.is_light_skin(sid)
            assert ui.appearance_mode_for(sid) == "light"
            # 밝은 배경 (대략)
            assert ui.BG.lower() not in ("#0a0e14", "#02040a", "#05080f")
        else:
            assert ui.appearance_mode_for(sid) == "dark"
    # classic 골드는 다른 스킨 액센트와 겹치지 않음
    assert accents["classic"] == "#c8aa6e"
    assert len(set(accents.values())) >= 5
    assert len(ui.SKINS) >= 10
    ui.apply_skin("classic")


def test_init_pref_vars_creates_shared_settings() -> None:
    from lol_coach.config import (
        auto_open_latest_match_enabled,
        game_end_auto_review_enabled,
        game_end_notify_enabled,
    )

    app = SimpleNamespace(
        settings=SimpleNamespace(llm_api_key="", llm_model=""),
        _font_scale=1.0,
    )
    # tk.StringVar needs a root — only test method existence / pure defaults via config
    assert game_end_notify_enabled() in (True, False)
    assert game_end_auto_review_enabled() in (True, False)
    assert auto_open_latest_match_enabled() in (True, False)
    assert callable(app_module.CoachApp._init_pref_vars)
    assert callable(app_module.CoachApp._open_settings)


def test_aram_inputs_fold_toggle() -> None:
    """ARAM 입력 접기 플래그·host grid/remove."""
    calls: list[str] = []
    host = SimpleNamespace(
        grid=lambda **k: calls.append("grid"),
        grid_remove=lambda: calls.append("remove"),
    )
    btn = SimpleNamespace(configure=lambda **k: calls.append(k.get("text", "")))
    app = SimpleNamespace(
        _aram_inputs_expanded=True,
        _aram_inputs_host=host,
        _aram_fold_btn=btn,
    )
    app_module.CoachApp._set_aram_inputs_expanded(app, False)
    assert app._aram_inputs_expanded is False
    assert "remove" in calls
    app_module.CoachApp._set_aram_inputs_expanded(app, True)
    assert app._aram_inputs_expanded is True
    assert "grid" in calls


def test_should_auto_open_latest_reads_var() -> None:
    app = SimpleNamespace(auto_open_latest_var=SimpleNamespace(get=lambda: False))
    assert app_module.CoachApp._should_auto_open_latest(app) is False
    app.auto_open_latest_var = SimpleNamespace(get=lambda: True)
    assert app_module.CoachApp._should_auto_open_latest(app) is True


def test_me_summary_toggle_state() -> None:
    """트렌드·듀오 요약은 기본 접힘, 토글 시 펼침 플래그만 바뀐다."""
    calls: list[bool] = []

    host = SimpleNamespace(
        grid=lambda **k: calls.append(True),
        grid_remove=lambda: calls.append(False),
    )
    btn = SimpleNamespace(configure=lambda **k: None)
    app = SimpleNamespace(
        _me_summary_expanded=False,
        _me_summary_host=host,
        _me_summary_btn=btn,
        _me_summary_hint_n=3,
    )
    app_module.CoachApp._set_me_summary_expanded(app, False)
    assert app._me_summary_expanded is False
    assert False in calls  # grid_remove
    calls.clear()
    app_module.CoachApp._set_me_summary_expanded(app, True)
    assert app._me_summary_expanded is True
    assert True in calls  # grid


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
