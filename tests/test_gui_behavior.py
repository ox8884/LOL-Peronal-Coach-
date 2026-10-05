from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from lol_coach.gui import app as app_module


def test_widget_native_style_checks_errors_and_readback(monkeypatch):
    import ctypes

    from lol_coach.gui import widget

    style = [0]
    failure = [""]

    def get_style(*args):
        if failure[0] == "read":
            ctypes.set_last_error(1400)
            return 0
        return style[0]

    def set_style(hwnd, index, value):
        if failure[0] == "write":
            ctypes.set_last_error(5)
            return 0
        previous = style[0]
        if failure[0] != "ignored":
            style[0] = value
        return previous

    api = SimpleNamespace(GetWindowLongW=get_style, SetWindowLongW=set_style)
    monkeypatch.setattr(widget, "_user32", lambda: api)
    assert widget._set_exstyle_transparent(1, True), "이전 스타일 0도 정상 성공일 수 있습니다"
    assert style[0] & widget._WS_EX_TRANSPARENT
    assert widget._set_exstyle_transparent(1, False)
    assert not style[0] & widget._WS_EX_TRANSPARENT
    for mode in ("read", "write", "ignored"):
        failure[0] = mode
        assert not widget._set_exstyle_transparent(1, True), mode


def test_autocomplete_caches_empty_results_but_retries_errors(monkeypatch):
    from lol_coach.gui.champ_autocomplete import ChampionAutocomplete

    searches = []
    query = "없는챔피언"
    fail = False

    def search(q, **kw):
        searches.append(q)
        if fail:
            raise RuntimeError("게임 데이터 준비 중")
        return []

    # Keep the real apply/hide lifecycle; no Tk renderer is needed for zero hits.
    ac = object.__new__(ChampionAutocomplete)
    ac._choosing = False
    ac._committed = None
    ac._shown_q = ""
    ac._panel_visible = False
    ac._rows = []
    ac.limit = 8
    ac.dd = SimpleNamespace(search_champions=search)
    monkeypatch.setattr(ac, "_text", lambda: query)
    monkeypatch.setattr(ac, "_cancel_job", lambda: None)
    monkeypatch.setattr(ac, "_clear_list", lambda: None)
    for _ in range(20):
        ac._apply()
    assert searches == ["없는챔피언"]
    ac.hide()
    ac._apply()
    assert len(searches) == 2, "명시적으로 닫은 뒤 재검색할 수 있어야 합니다"
    query = "아리"
    fail = True
    ac._apply()
    fail = False
    ac._apply()
    assert searches[-2:] == ["아리", "아리"], "일시적인 실패를 빈 결과로 저장하지 않습니다"


def test_explicit_skin_does_not_poll_appearance_33_times_per_second(monkeypatch):
    import customtkinter as ctk

    from lol_coach.gui import components

    tracker = ctk.AppearanceModeTracker
    monkeypatch.setattr(components, "load_skin_name", lambda: "classic")
    scheduled = []
    monkeypatch.setattr(tracker, "app_list", [SimpleNamespace(after=lambda ms, fn: scheduled.append(ms))])
    monkeypatch.setattr(tracker, "detect_appearance_mode", lambda: (_ for _ in ()).throw(
        AssertionError("고정 스킨에서 시스템 테마를 조회하면 안 됩니다")
    ))
    app_module._apply_startup_theme()
    tracker.update()
    assert scheduled == [1000]
    # User-selected light/dark changes remain synchronous, independent of polling.
    original_mode = ctk.get_appearance_mode()
    try:
        ctk.set_appearance_mode("light")
        assert ctk.get_appearance_mode() == "Light"
        ctk.set_appearance_mode("dark")
        assert ctk.get_appearance_mode() == "Dark"
    finally:
        ctk.set_appearance_mode(original_mode)


def test_aram_result_does_not_wait_for_icon_prefetch(monkeypatch):
    from lol_coach.gui import aram_tab as module
    from lol_coach.gui.tabs.aram import AramTab

    events = []
    advice = SimpleNamespace(
        champ_key="Ahri", champ_ko="아리", core_slots=[], core_item_ids=[],
        top_augments=[], avoid_augments=[],
        fixed_top=SimpleNamespace(silver=[], gold=[], prismatic=[]),
    )
    app = SimpleNamespace(
        _is_busy=lambda key: False,
        _resolve=lambda raw: ("Ahri", "아리"),
        aram_champ_var=SimpleNamespace(get=lambda: "아리", set=lambda value: None),
        aram_status=SimpleNamespace(configure=lambda **kw: None),
        aram_btn=None, _busy_set=lambda *a, **kw: None,
        mayhem=SimpleNamespace(advise=lambda key: advice),
        after=lambda ms, fn: fn(),
        _aram_history=[],
    )
    monkeypatch.setattr(module.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
    monkeypatch.setattr(module, "champion_pil", lambda *a: events.append("icon"), raising=False)
    monkeypatch.setattr(module.AramTabMixin, "_render_aram", lambda self, adv: events.append("result"))
    tab = AramTab(app)
    tab._run_aram()
    assert events == ["result"], "아이콘 준비 전에 추천 내용을 표시해야 합니다"


def test_aram_icon_fill_bounds_workers_and_discards_previous_screen(monkeypatch):
    from lol_coach.gui import aram_tab as module
    from lol_coach.gui.tabs.aram import AramTab

    workers = []
    callbacks = []
    updates = []
    downloads = []
    monkeypatch.setattr(
        module.threading, "Thread",
        lambda target, **kw: SimpleNamespace(start=lambda: workers.append(target)),
    )
    icon = SimpleNamespace(cget=lambda key: SimpleNamespace(info={}))
    label = SimpleNamespace(winfo_exists=lambda: True, configure=lambda **kw: updates.append(kw))
    app = SimpleNamespace(after=lambda ms, fn: callbacks.append(fn), _icon_refs=[], aram_out=object())
    tab = AramTab(app)
    tab._cancel_aram_icons()
    app._aram_icon_jobs = [(label, lambda: downloads.append("old"))] * 8
    tab._schedule_aram_icon_fill()
    assert len(workers) == 4

    tab._cancel_aram_icons()
    app._aram_icon_jobs = [(label, lambda: (downloads.append("current"), icon)[1])]
    tab._schedule_aram_icon_fill()
    assert len(workers) == 4, "연속 선택해도 다운로드 워커가 늘어나면 안 됩니다"
    for worker in workers:
        worker()
    assert downloads == ["current"]
    assert app._aram_icon_running == 0
    assert updates == []
    callbacks[0]()
    assert updates == [{"image": icon, "text": "", "fg_color": "transparent"}]
    assert app._icon_refs == [], "재사용 라벨이 이미지를 소유하므로 별도 참조 목록을 늘리지 않습니다"

    tab._cancel_aram_icons()
    callbacks[0]()
    assert len(updates) == 1, "선택 화면 복귀 후 늦게 온 아이콘은 버려야 합니다"


def test_live_augment_icon_does_not_query_lcu_on_ui_thread(monkeypatch):
    from lol_coach.gui import aram_tab as module
    from lol_coach.gui.tabs.aram import AramTab
    from lol_coach.static import mayhem_augments

    monkeypatch.setattr(module, "augment_ctk", lambda *a: None)
    queried = []
    monkeypatch.setattr(mayhem_augments, "augment_meta", lambda aid: SimpleNamespace(id=aid))
    monkeypatch.setattr(mayhem_augments, "icon_bytes_for", lambda *args: None)
    monkeypatch.setattr(module.AramTabMixin, "_ensure_aug_lcu", lambda self: queried.append(True))
    pick = SimpleNamespace(name_en="New augment", record=SimpleNamespace(id="live:123"))
    assert AramTab(SimpleNamespace())._augment_icon(pick, 32) is None
    assert queried == []


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
        _send_discord_review_card=lambda match: None,
        _settle_prediction=lambda match: None,
        _settle_blame=lambda match: None,
        _game_end_auto_review_on=lambda: True,
        me_tab=SimpleNamespace(show_match=lambda match: shown.append(match)),
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
        _send_discord_review_card=lambda match: None,
        _settle_prediction=lambda match: None,
        _settle_blame=lambda match: None,
        _game_end_auto_review_on=lambda: False,
        me_tab=SimpleNamespace(show_match=lambda match: shown.append(match)),
    )
    app_module.CoachApp._on_game_ended(
        app, SimpleNamespace(champion_name="Caitlyn", win=False)
    )
    assert shown == []


def test_game_end_hands_off_to_discord_sender() -> None:
    sent: list[object] = []
    app = SimpleNamespace(
        loc=SimpleNamespace(champion=lambda name: name),
        status=SimpleNamespace(configure=lambda **kwargs: None),
        _notify_game_end=lambda champ, win: None,
        _send_discord_review_card=lambda match: sent.append(match),
        _settle_prediction=lambda match: None,
        _settle_blame=lambda match: None,
        _game_end_auto_review_on=lambda: False,
        me_tab=SimpleNamespace(show_match=lambda match: None),
    )
    match = SimpleNamespace(champion_name="Caitlyn", win=False)

    app_module.CoachApp._on_game_ended(app, match)

    assert sent == [match]


def test_game_end_skips_settle_on_remake() -> None:
    sent: list[object] = []
    settled: list[object] = []
    shown: list[object] = []
    status: list[str] = []
    app = SimpleNamespace(
        loc=SimpleNamespace(champion=lambda name: name),
        status=SimpleNamespace(configure=lambda **kwargs: status.append(kwargs["text"])),
        _notify_game_end=lambda champ, win: sent.append("notify"),
        _send_discord_review_card=lambda match: sent.append(match),
        _settle_prediction=lambda match: settled.append("pred"),
        _settle_blame=lambda match: settled.append("blame"),
        _game_end_auto_review_on=lambda: True,
        me_tab=SimpleNamespace(show_match=lambda match: shown.append(match)),
    )
    remake = SimpleNamespace(
        champion_name="Caitlyn",
        win=False,
        game_duration_s=95,
        team_early_surrender=True,
    )
    app_module.CoachApp._on_game_ended(app, remake)
    assert sent == []
    assert settled == []
    assert shown == []
    assert any("리메이크" in t for t in status)


def test_discord_review_card_skips_without_webhook(
    tmp_path, monkeypatch
) -> None:
    """웹훅이 설정돼 있지 않으면 렌더·전송 경로를 타지 않는다."""
    import importlib

    config_mod = importlib.import_module("lol_coach.config")
    monkeypatch.setattr(config_mod, "UI_PATH", tmp_path / "ui.json")
    monkeypatch.delenv("LOL_COACH_DISCORD_WEBHOOK", raising=False)

    app = SimpleNamespace(
        _build_review_card_png=lambda match: (_ for _ in ()).throw(
            AssertionError("should not render without webhook")
        ),
        _post_discord_card=lambda **kw: None,
    )

    app_module.CoachApp._send_discord_review_card(app, SimpleNamespace())


def test_discord_review_toggle_saves(
    tmp_path, monkeypatch
) -> None:
    """디스코드 자동 전송 토글 — 설정 즉시 저장 경로."""
    import importlib

    config_mod = importlib.import_module("lol_coach.config")
    monkeypatch.setattr(config_mod, "UI_PATH", tmp_path / "ui.json")
    monkeypatch.delenv("LOL_COACH_DISCORD_WEBHOOK", raising=False)

    app = SimpleNamespace(
        discord_review_var=SimpleNamespace(get=lambda: False),
        _notify=lambda *a, **k: None,
    )
    from lol_coach.gui.tabs.me import MeTab

    app.me_tab = MeTab(app)
    app.me_tab._on_discord_review_toggle()
    assert config_mod.discord_review_enabled() is False

    app.discord_review_var = SimpleNamespace(get=lambda: True)
    app.me_tab._on_discord_review_toggle()
    assert config_mod.discord_review_enabled() is True


def test_post_discord_card_helper(tmp_path, monkeypatch) -> None:
    """공통 웹훅 헬퍼 — 미설정 시 스킵, 설정 시 전송+토스트."""
    import importlib

    import lol_coach.gui.live_mixin as lm
    from lol_coach.gui.discord_cards import DiscordCards

    config_mod = importlib.import_module("lol_coach.config")
    monkeypatch.setattr(config_mod, "UI_PATH", tmp_path / "ui.json")
    monkeypatch.delenv("LOL_COACH_DISCORD_WEBHOOK", raising=False)

    class SyncThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    import threading as real_threading

    monkeypatch.setattr(real_threading, "Thread", SyncThread)
    notify_mod = importlib.import_module("lol_coach.notify.discord")
    posted: list = []
    monkeypatch.setattr(
        notify_mod, "post_card", lambda webhook_url, **kw: posted.append(kw)
    )
    notifications: list = []
    renders: list = []
    app = SimpleNamespace(
        after=lambda ms, fn: fn(),
        _notify=lambda msg, level="info", ms=3800, **_k: notifications.append(msg),
    )

    def _ensure_discord_cards() -> DiscordCards:
        return DiscordCards(
            after_cb=lambda ms, fn: app.after(ms, fn),
            notify_cb=app._notify,
        )

    app._ensure_discord_cards = _ensure_discord_cards

    def render() -> bytes:
        renders.append(1)
        return b"png"

    # 1) 웹훅 미설정 → 렌더·전송 없이 스킵 (부수 효과 없음)
    lm.LiveMixin._post_discord_card(
        app,
        title_fn=lambda: "t",
        description_fn=lambda: "d",
        png_bytes_fn=render,
        footer_fn=lambda: "f",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    assert renders == []
    assert posted == []

    # 2) 웹훅 설정 → 렌더 + 전송 + 성공 토스트
    config_mod.set_discord_webhook("https://discord.com/api/webhooks/1/tok")
    lm.LiveMixin._post_discord_card(
        app,
        title_fn=lambda: "t2",
        description_fn=lambda: "d2",
        png_bytes_fn=render,
        footer_fn=lambda: "f2",
        ok_msg="전송 완료",
        fail_msg="전송 실패",
    )
    assert renders == [1]
    assert posted and posted[0]["png_bytes"] == b"png"
    assert posted[0]["title"] == "t2"
    assert any("전송 완료" in n for n in notifications)


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
        me_detail=SimpleNamespace(),
        _clear=lambda frame: None,
        _notify=lambda *a, **k: None,
    )
    from lol_coach.gui.tabs.me import MeTab

    app.me_tab = MeTab(app)
    object.__setattr__(
        app.me_tab, "_show_match_detail", lambda m: shown.append(m.match_id)
    )
    app.me_tab._nav_match(-1)
    app.me_tab._nav_match(1)
    # index was 1; after -1 would show A, but _nav_match uses _me_match_index
    # without updating unless _show_match_detail does — we mock show so index stays 1
    # first call: 1-1=0 → A; second: still index 1 → 1+1=2 → C
    assert shown == ["A", "C"]


def test_match_index_of() -> None:
    m0 = SimpleNamespace(match_id="A")
    m1 = SimpleNamespace(match_id="B")
    app = SimpleNamespace(form=SimpleNamespace(matches=[m0, m1]))
    from lol_coach.gui.tabs.me import MeTab

    app.me_tab = MeTab(app)
    assert app.me_tab._match_index_of(m1) == 1
    assert app.me_tab._match_index_of(SimpleNamespace(match_id="Z")) is None


def test_apply_skin_live_method_exists() -> None:
    assert callable(app_module.CoachApp._apply_skin_live)


def test_legacy_skin_preferences_use_the_new_palettes() -> None:
    from lol_coach.gui import components as ui

    assert ui.normalize_skin_name("classic") == "charcoal"
    assert ui.normalize_skin_name("neon") == "midnight"
    assert ui.normalize_skin_name("cream") == "paper"
    assert ui.normalize_skin_name("unknown") == ui.DEFAULT_SKIN


def test_three_skins_match_the_packaged_theme_and_readable_text() -> None:
    import json

    from lol_coach.gui import components as ui

    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    assert ui.SKINS == ("charcoal", "midnight", "paper")
    try:
        for skin in ui.SKINS:
            ui.apply_skin(skin)
            palette = ui._PALETTES[skin]
            assert json.loads(ui.resolve_theme_path(skin).read_text()) == ui.build_ctk_theme(palette)
            assert ui.appearance_mode_for(skin) == ("light" if skin == "paper" else "dark")
            for tier in ("S", "A", "B", "C"):
                high, low = sorted(map(luminance, ui.tier(tier)), reverse=True)
                assert (high + 0.05) / (low + 0.05) >= 4.5, (skin, tier)
            for text in ("TEXT", "TEXT_BRIGHT", "TEXT_DIM", "TEXT_MUTE"):
                for background in ("BG", "PANEL", "CARD", "ROW"):
                    high, low = sorted((luminance(palette[text]), luminance(palette[background])), reverse=True)
                    assert (high + 0.05) / (low + 0.05) >= 4.5, (skin, text, background)
    finally:
        ui.apply_skin(ui.DEFAULT_SKIN)


def test_init_pref_vars_creates_shared_settings() -> None:
    from lol_coach.config import (
        auto_open_latest_match_enabled,
        game_end_auto_review_enabled,
        game_end_notify_enabled,
    )

    # tk.StringVar needs a root — only test method existence / pure defaults via config
    assert game_end_notify_enabled() in (True, False)
    assert game_end_auto_review_enabled() in (True, False)
    assert auto_open_latest_match_enabled() in (True, False)
    assert callable(app_module.CoachApp._init_pref_vars)
    assert callable(app_module.CoachApp._open_settings)


def test_render_sr_detail_with_situational_items(monkeypatch) -> None:
    """회귀: 믹스인 분리 시 FB import 누락 → 상황템 렌더 NameError.

    상황템·코어가 있는 리포트로 상세 렌더가 끝까지 완료되는지 확인한다.
    """
    from lol_coach.analysis.comp import CompReport
    from lol_coach.gui import sr_tab

    def _fake_widget(*_a, **_k):
        return SimpleNamespace(pack=lambda *a2, **k2: None)

    monkeypatch.setattr(sr_tab, "ctk", SimpleNamespace(CTkLabel=_fake_widget))
    monkeypatch.setattr(
        sr_tab.ui,
        "tier_chip",
        lambda *a, **k: SimpleNamespace(pack=lambda *a2, **k2: None),
    )
    monkeypatch.setattr(sr_tab, "champion_ctk", lambda *a, **k: None)
    monkeypatch.setattr(sr_tab, "item_name_ctk", lambda *a, **k: None)

    status_msgs: list[str] = []
    app = SimpleNamespace(
        sr_out=SimpleNamespace(),
        sr_status=SimpleNamespace(
            configure=lambda **k: status_msgs.append(k.get("text"))
        ),
        status=SimpleNamespace(
            configure=lambda **k: status_msgs.append(k.get("text"))
        ),
        _ai_key=lambda: "",
        _push_summary=lambda title, lines: None,
        _clear=lambda f: None,
        _sec=lambda p, t, r: r + 1,
        _lbl=lambda p, t, r, **k: r + 1,
        _row_frame=lambda p, r, **k: SimpleNamespace(),
        _keep_icon=lambda img: None,
        _attach_item_tooltip=lambda w, n: None,
    )
    counter = SimpleNamespace(
        champion="Leblanc", gd15=150, gd15_str="+150", matches=15234
    )
    rep = CompReport(
        my_role="미드",
        my_champ_ko="아리",
        enemy_lane_ko="르블랑",
        enemy_team=[
            ("탑", "가렌"),
            ("정글", "리신"),
            ("미드", "르블랑"),
            ("원딜", "케이틀린"),
            ("서폿", "블리츠크랭크"),
        ],
        patch="15.4",
        counters=[("르블랑", counter)],
        threats=["위협 1"],
        midgame=["중반 1"],
        core_items=["리안드리의 고통"],
        situational=[("존야의 모래시계", "AP 폭발 대응")],
        runes_line="감전",
        spells_line="점멸/점화",
        skill_line="Q>W>E",
        action_plan=["행동 1"],
    )
    sr_tab.SrTabMixin._render_sr_detail(app, rep, ["라인전 팁 1"])
    assert any("상세 완료" in m for m in status_msgs)


def test_should_auto_open_latest_config_fallback(monkeypatch) -> None:
    """회귀: me_tab의 auto_open_latest_match_enabled import 누락(NameError)."""
    from lol_coach.gui import me_tab

    monkeypatch.setattr(me_tab, "auto_open_latest_match_enabled", lambda: True)
    app = SimpleNamespace()
    assert me_tab.MeTabMixin._should_auto_open_latest(app) is True


def test_report_callback_exception_surfaces_status() -> None:
    """Tk 콜백 예외가 상태바로 노출되고 예외를 다시 던지지 않는다."""
    status_msgs: list[str] = []
    app = SimpleNamespace(
        status=SimpleNamespace(
            configure=lambda **k: status_msgs.append(k.get("text"))
        )
    )
    app_module.CoachApp.report_callback_exception(
        app, ValueError, ValueError("boom"), None
    )
    assert status_msgs and status_msgs[0].startswith("⚠")


def test_check_update_enables_button(monkeypatch) -> None:
    """회귀: v1.6.8 분리 때 _version_tuple self 유실 → 업데이트 확인 항상 실패.

    새 버전이 있으면 업데이트 버튼이 활성화되고 상태바에 안내가 뜬다.
    """
    from lol_coach.gui import update_mixin as um
    from lol_coach.gui.update_mixin import UpdateMixin

    monkeypatch.setattr("lol_coach.gui.updater.fetch_latest_tag", lambda: "1.6.33")
    monkeypatch.setattr(
        "lol_coach.gui.updater.fetch_expected_sha256", lambda v: "abc123"
    )
    monkeypatch.setattr(um, "__version__", "1.6.32")

    btn_calls: list[dict] = []
    status_calls: list[str] = []
    app = SimpleNamespace(
        update_btn=SimpleNamespace(
            configure=lambda **k: btn_calls.append(k)
        ),
        status=SimpleNamespace(
            configure=lambda **k: status_calls.append(k.get("text")),
            cget=lambda k: "데이터 준비됨",
        ),
        after=lambda ms, fn: fn(),
        _latest_version="",
        _latest_sha256="",
    )
    app._version_tuple = UpdateMixin._version_tuple.__get__(app)  # type: ignore[attr-defined]
    UpdateMixin._check_update(app)
    assert app._latest_version == "1.6.33"
    assert btn_calls and btn_calls[-1].get("state") == "normal"
    assert "v1.6.33" in btn_calls[-1].get("text", "")
    assert status_calls and "v1.6.33" in status_calls[0]


def test_check_update_same_version_keeps_enabled(monkeypatch) -> None:
    from lol_coach.gui import update_mixin as um
    from lol_coach.gui.update_mixin import UpdateMixin

    monkeypatch.setattr("lol_coach.gui.updater.fetch_latest_tag", lambda: "1.6.32")
    monkeypatch.setattr(um, "__version__", "1.6.32")
    btn_calls: list[dict] = []
    app = SimpleNamespace(
        update_btn=SimpleNamespace(configure=lambda **k: btn_calls.append(k)),
        status=SimpleNamespace(configure=lambda **k: None, cget=lambda k: "x"),
        after=lambda ms, fn: fn(),
        _latest_version="",
        _latest_sha256="",
    )
    app._version_tuple = UpdateMixin._version_tuple.__get__(app)  # type: ignore[attr-defined]
    UpdateMixin._check_update(app)
    assert app._latest_version == ""
    assert btn_calls[-1].get("state") == "normal"
    assert "최신" in btn_calls[-1].get("text", "")


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
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    app.aram_tab._set_aram_inputs_expanded(False)
    assert app._aram_inputs_expanded is False
    assert "remove" in calls
    app.aram_tab._set_aram_inputs_expanded(True)
    assert app._aram_inputs_expanded is True
    assert "grid" in calls


def test_aram_freshness_banner_normalizes_date_only_and_preserves_offsets(monkeypatch) -> None:
    from lol_coach.gui import aram_tab as aram_tab_module
    from lol_coach.gui.tabs.aram import AramTab

    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(
        aram_tab_module,
        "datetime",
        SimpleNamespace(
            fromisoformat=datetime.fromisoformat,
            now=lambda _tz=None: now,
        ),
    )
    tab = AramTab(SimpleNamespace())

    def banner(updated_at: str) -> str:
        source = SimpleNamespace(updated_at=updated_at, patch="16.15")
        return tab._aram_freshness_banner(SimpleNamespace(source=source, patch="16.15"))

    assert "18일" in banner("2026-08-28")
    assert "17일" in banner("2026-08-28T12:00:00-05:00")
    assert banner("2026-09-10") == ""


def test_should_auto_open_latest_reads_var() -> None:
    app = SimpleNamespace(auto_open_latest_var=SimpleNamespace(get=lambda: False))
    from lol_coach.gui.tabs.me import MeTab

    app.me_tab = MeTab(app)
    assert app.me_tab._should_auto_open_latest() is False
    app.auto_open_latest_var = SimpleNamespace(get=lambda: True)
    assert app.me_tab._should_auto_open_latest() is True


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
    from lol_coach.gui.tabs.me import MeTab

    app.me_tab = MeTab(app)
    app.me_tab._set_me_summary_expanded(False)
    assert app._me_summary_expanded is False
    assert False in calls  # grid_remove
    calls.clear()
    app.me_tab._set_me_summary_expanded(True)
    assert app._me_summary_expanded is True
    assert True in calls  # grid


def test_ai_key_points_prioritize_actionable_lines() -> None:
    text = """
    배경 설명
    핵심: 먼저 뒤에서 포킹하세요.
    아이템: 세 번째 코어는 방어 아이템입니다.
    주의: 암살자 진입 때 점멸을 아끼세요.
    """

    from lol_coach.gui.ai_text import ai_key_points

    points = ai_key_points(text, limit=2)

    assert points == [
        "핵심: 먼저 뒤에서 포킹하세요.",
        "주의: 암살자 진입 때 점멸을 아끼세요.",
    ]


def test_launch_installer_defers_to_after_exit(monkeypatch) -> None:
    """설치는 앱 종료 후로 예약된다 — 즉시 실행하지 않아 잠금 경합을 피한다 (회귀 방지)."""
    import tempfile
    import types

    from lol_coach.gui.update_mixin import UpdateMixin

    tmp = Path(tempfile.mkdtemp()) / "LOL-Coach-Setup-v1.6.104.exe"
    tmp.write_bytes(b"x" * 100)

    btn_calls: list[dict] = []
    status_calls: list[str] = []
    destroy_calls: list[int] = []
    app = types.SimpleNamespace(
        update_btn=types.SimpleNamespace(configure=lambda **k: btn_calls.append(k)),
        status=types.SimpleNamespace(configure=lambda **k: status_calls.append(k.get("text"))),
        after=lambda ms, fn: (destroy_calls.append(ms), fn()),  # 예약 즉시 실행
        destroy=lambda: destroy_calls.append("destroy"),
        _on_close=lambda: destroy_calls.append("on_close"),
        _pending_update_installer="",
        _latest_version="1.6.104",
    )
    UpdateMixin._launch_installer(app, str(tmp), "1.6.104")
    assert app._pending_update_installer == str(tmp)
    assert destroy_calls == [600, "on_close"]  # 종료 경로가 _on_close 정리를 탄다
    assert destroy_calls == [600, "on_close"]
    assert any("종료 후" in t for t in status_calls)


def test_launch_installer_missing_file_fails_gracefully(monkeypatch) -> None:
    import types

    from lol_coach.gui.update_mixin import UpdateMixin

    errors: list[str] = []
    app = types.SimpleNamespace(
        update_btn=types.SimpleNamespace(configure=lambda **k: None),
        status=types.SimpleNamespace(configure=lambda **k: None),
        after=lambda ms, fn: None,
        _pending_update_installer="",
        _latest_version="1.6.104",
        _update_failed=lambda msg: errors.append(msg),
    )
    UpdateMixin._launch_installer(app, str(Path("존재하지않는/installer.exe")), "1.6.104")
    assert errors and "찾을 수 없습니다" in errors[0]
    assert app._pending_update_installer == ""


def _fake_hotkey_user32(monkeypatch, fake):
    import ctypes

    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name, **kw: fake.kernel if name == "kernel32" else fake,
        raising=False,
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87, raising=False)


class _FakeHotkeyUser32:
    def __init__(self):
        import queue
        import threading
        from unittest.mock import Mock

        self.messages = queue.Queue()
        self.peek_entered = threading.Event()
        self.allow_peek = threading.Event()
        self.register_entered = threading.Event()
        self.allow_register = threading.Event()
        self.wait_entered = threading.Event()
        self.peek_calls = 0
        self.register_calls = 0
        self.unregister_calls = 0
        self.posted = []
        self.register_result = True
        self.block_peek = False
        self.block_register = False
        self.wake = threading.Event()
        self.stop_signaled = False
        self.wait_calls = 0
        self.wait_result = None
        self.event_result = 0x1234567887654321
        self.kernel = SimpleNamespace(
            CreateEventW=Mock(side_effect=lambda *args: self.event_result),
            SetEvent=Mock(side_effect=self._signal_stop),
            CloseHandle=Mock(return_value=1),
        )
        self.MsgWaitForMultipleObjects = Mock(side_effect=self._wait)

    def _signal_stop(self, handle):
        self.stop_signaled = True
        self.wake.set()
        return 1

    def _wait(self, count, handles, all_events, timeout, mask):
        assert count == 1 and timeout == 0xFFFFFFFF
        self.wait_calls += 1
        self.wait_entered.set()
        if self.wait_result is not None:
            return self.wait_result
        assert self.wake.wait(3.0), "test must wake the blocked hotkey worker"
        return 0 if self.stop_signaled else 1

    def post(self, message, wparam=0):
        self.messages.put((message, wparam))
        self.wake.set()

    def PeekMessageW(self, msg_ptr, _hwnd, _min_filter, _max_filter, remove):
        import ctypes
        import queue
        from ctypes import wintypes

        self.peek_calls += 1
        self.peek_entered.set()
        if self.block_peek:
            self.allow_peek.wait(1.0)
        if not remove:
            return 0
        try:
            message, wparam = self.messages.get_nowait()
        except queue.Empty:
            self.wake.clear()
            return 0
        msg = ctypes.cast(msg_ptr, ctypes.POINTER(wintypes.MSG)).contents
        msg.message, msg.wParam = message, wparam
        return 1

    def RegisterHotKey(self, _hwnd, hotkey_id, modifiers, vk):
        self.register_calls += 1
        self.register_entered.set()
        if self.block_register:
            self.allow_register.wait(1.0)
        return int(self.register_result)

    def UnregisterHotKey(self, _hwnd, hotkey_id):
        self.unregister_calls += 1
        return 1

    def PostThreadMessageW(self, thread_id, message, wparam, lparam):
        self.posted.append((thread_id, message, wparam, lparam))
        self.post(message, wparam)
        return 1

def test_global_hotkey_blocks_for_messages_and_invokes_callback_once(monkeypatch) -> None:
    import threading

    from lol_coach.gui.global_hotkey import WM_HOTKEY, GlobalHotkey

    fake = _FakeHotkeyUser32()
    _fake_hotkey_user32(monkeypatch, fake)
    calls = []
    callback_seen = threading.Event()

    def callback() -> None:
        calls.append(True)
        callback_seen.set()

    hotkey = GlobalHotkey(callback)
    assert hotkey.start(wait=True) is True
    try:
        assert fake.wait_entered.wait(1.0), "등록 후 Windows 이벤트에서 대기해야 합니다"
        assert fake.peek_calls == 1, "유휴 상태에서 PeekMessageW를 반복하면 안 됩니다"
        fake.post(WM_HOTKEY, hotkey._hotkey_id)
        assert callback_seen.wait(1.0)
        assert calls == [True]
    finally:
        hotkey.stop()

    assert fake.unregister_calls == 1
    assert fake.posted == []
    fake.kernel.CloseHandle.assert_called_once_with(fake.event_result)


def test_global_hotkey_stop_during_startup_skips_registration(monkeypatch) -> None:
    import threading

    from lol_coach.gui.global_hotkey import GlobalHotkey

    fake = _FakeHotkeyUser32()
    fake.block_peek = True
    _fake_hotkey_user32(monkeypatch, fake)
    hotkey = GlobalHotkey(lambda: None)
    hotkey.start(wait=False)
    assert fake.peek_entered.wait(1.0)

    stop_seen = threading.Event()
    stop_done = threading.Event()
    original_stop = hotkey._stop

    class StopProbe:
        def clear(self):
            original_stop.clear()

        def set(self):
            original_stop.set()
            stop_seen.set()

        def is_set(self):
            return original_stop.is_set()

        def wait(self, timeout=None):
            return original_stop.wait(timeout)

    hotkey._stop = StopProbe()
    stopper = threading.Thread(target=lambda: (hotkey.stop(), stop_done.set()))
    stopper.start()
    assert stop_seen.wait(1.0)
    assert fake.posted == [], "스레드 message queue가 생기기 전에는 WM_QUIT를 보낼 수 없습니다"

    fake.allow_peek.set()
    assert stop_done.wait(1.0)
    stopper.join(1.0)
    assert fake.register_calls == 0
    assert hotkey._thread is None


def test_global_hotkey_reports_registration_failure(monkeypatch) -> None:
    from lol_coach.gui.global_hotkey import GlobalHotkey

    fake = _FakeHotkeyUser32()
    fake.register_result = False
    _fake_hotkey_user32(monkeypatch, fake)
    hotkey = GlobalHotkey(lambda: None)

    assert hotkey.start(wait=True) is False
    assert "RegisterHotKey 실패" in hotkey.error
    hotkey.stop()
    assert fake.wait_calls == 0
    assert fake.unregister_calls == 0


def test_global_hotkey_handles_wait_failure_and_unregisters(monkeypatch) -> None:
    from lol_coach.gui.global_hotkey import GlobalHotkey

    fake = _FakeHotkeyUser32()
    fake.wait_result = 0xFFFFFFFF
    _fake_hotkey_user32(monkeypatch, fake)
    hotkey = GlobalHotkey(lambda: None)

    hotkey.start(wait=True)
    hotkey._thread.join(1.0)
    assert "MsgWaitForMultipleObjects 실패" in hotkey.error
    assert fake.unregister_calls == 1
    hotkey.stop()
    fake.kernel.CloseHandle.assert_called_once_with(fake.event_result)


def test_global_hotkey_stops_even_when_thread_messages_cannot_be_posted(monkeypatch) -> None:
    from lol_coach.gui.global_hotkey import GlobalHotkey

    fake = _FakeHotkeyUser32()
    _fake_hotkey_user32(monkeypatch, fake)
    monkeypatch.setattr(fake, "PostThreadMessageW", lambda *args: 0)
    hotkey = GlobalHotkey(lambda: None)
    assert hotkey.start(wait=True)
    worker = hotkey._thread
    try:
        assert fake.wait_entered.wait(1.0)
        hotkey.stop()
        assert not worker.is_alive(), "메시지 전송 실패에도 종료되어야 합니다"
        assert fake.unregister_calls == 1
        assert hotkey.registered is False
        fake.kernel.CloseHandle.assert_called_once_with(fake.event_result)
    finally:
        fake.post(0x0012)
        worker.join(1.0)


def test_global_hotkey_stop_during_registration_discards_queued_callback(monkeypatch) -> None:
    import threading

    from lol_coach.gui.global_hotkey import WM_HOTKEY, GlobalHotkey

    fake = _FakeHotkeyUser32()
    fake.block_register = True
    _fake_hotkey_user32(monkeypatch, fake)
    calls = []
    hotkey = GlobalHotkey(lambda: calls.append(True))
    hotkey.start(wait=False)
    assert fake.register_entered.wait(1.0)
    fake.post(WM_HOTKEY, hotkey._hotkey_id)
    stopper = threading.Thread(target=hotkey.stop)
    stopper.start()
    assert hotkey._stop.wait(1.0)
    fake.allow_register.set()
    stopper.join(2.0)
    assert not stopper.is_alive()
    assert hotkey._thread is None
    assert calls == []
    assert fake.unregister_calls == 1


def test_global_hotkey_reports_stop_event_creation_failure(monkeypatch) -> None:
    from lol_coach.gui.global_hotkey import GlobalHotkey

    fake = _FakeHotkeyUser32()
    fake.event_result = 0
    _fake_hotkey_user32(monkeypatch, fake)
    hotkey = GlobalHotkey(lambda: None)
    try:
        assert hotkey.start(wait=True) is False
        assert "CreateEvent 실패" in hotkey.error
        assert fake.register_calls == 0
    finally:
        hotkey.stop()
    fake.kernel.CloseHandle.assert_not_called()
