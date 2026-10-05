"""실 GUI 스모크 — CoachApp 생성·이벤트 처리·종료.

v1.6.33 회귀(Protocol 스텁이 tkinter를 섀도잉해 시작 시 RecursionError)를
잡기 위한 최소 실기동 테스트. Tk 디스플레이가 있는 환경에서만 의미가 있다.
"""

from __future__ import annotations

import tkinter as _tk

from lol_coach.gui.app import CoachApp


def _widget_test_app(monkeypatch, tmp_path, saved=None):
    from lol_coach import config
    from lol_coach.gui import app as module

    monkeypatch.setattr(config, "UI_PATH", tmp_path / "ui.json")
    config.save_ui_settings(**(saved or {}))
    monkeypatch.setattr(module, "load_settings", lambda: config.Settings(riot_api_key=""))
    for name in ("_spawn_thread", "_bind_hotkeys", "_start_mayhem_select_watcher", "_start_live_client_watcher"):
        monkeypatch.setattr(CoachApp, name, lambda *a, **kw: None)
    app = CoachApp()
    app.update()
    return app


def test_widget_settings_visibility_and_late_overlay(monkeypatch, tmp_path):
    from lol_coach import config
    from lol_coach.gui.settings_dialog import SettingsDialog

    app = _widget_test_app(monkeypatch, tmp_path)
    try:
        assert not app.widget_visible_var.get()
        app._ensure_widget_open()  # 기존 사용자는 자동 표시 유지
        app.update()
        assert app.widget_visible_var.get()
        dlg = SettingsDialog(app)
        app.update()
        dlg.widget_switch.toggle()
        assert app._widget is None
        assert config.load_ui_settings()["widget_visible"] is False
        app._show_overlay_summary("🎮 늦은 응답", ["추천"], "아리", 0)
        app._ensure_widget_open()
        assert app._widget is None
        assert not app._overlay_active
        dlg.widget_switch.toggle()
        app.update()
        assert app._widget.winfo_exists()
        assert config.load_ui_settings()["widget_visible"] is True
        app._toggle_widget()  # 단축키/메인 버튼과 설정 상태 동기화
        assert not dlg.widget_switch.get()
        app._toggle_widget()
        app.update()
        app._widget._close()  # 위젯 X 버튼
        assert not app.widget_visible_var.get()
        assert config.load_ui_settings()["widget_visible"] is False
        dlg.destroy()
        app._toggle_widget()
        from lol_coach.gui import components as ui

        skin = "classic" if ui.active_skin() != "classic" else "slate"
        app._force_skin_rebuild = True
        app._apply_skin_live(skin)
        app.update()
        assert app._widget.winfo_exists()
        assert app.widget_visible_var.get()
        app._toggle_widget()
        assert app._widget is None
    finally:
        app.destroy()


def test_widget_restores_explicit_visibility(monkeypatch, tmp_path):
    from lol_coach import config

    app = _widget_test_app(monkeypatch, tmp_path, {"widget_visible": True})
    try:
        assert app._widget.winfo_exists()
        assert app.widget_visible_var.get()
        assert not app._widget._clickthrough
    finally:
        app.destroy()
    assert config.load_ui_settings()["widget_visible"] is True


def test_widget_clickthrough_recovery_and_close(monkeypatch, tmp_path):
    from lol_coach.gui import widget as module

    app = _widget_test_app(monkeypatch, tmp_path)
    applied = []
    monkeypatch.setattr(module, "_set_exstyle_transparent", lambda hwnd, enabled: applied.append(enabled) or True)
    try:
        app._toggle_widget()
        app.update()
        widget = app._widget
        widget._click_var.set(True)
        widget._toggle_clickthrough()
        app.update()
        assert widget._recovery_bar.winfo_ismapped()
        assert widget._clickthrough
        import customtkinter as ctk

        try:
            for scale in (1.3, 1.0):
                ctk.set_widget_scaling(scale)
                app.update()
                assert widget._recovery_reset.winfo_rootx() + widget._recovery_reset.winfo_width() < widget._recovery_close.winfo_rootx()
        finally:
            ctk.set_widget_scaling(1.0)
        widget._recovery_reset.invoke()
        assert not widget._clickthrough
        assert not widget._click_var.get()
        assert widget._recovery_bar is None
        assert applied[-2:] == [True, False]
        widget._click_var.set(True)
        widget._toggle_clickthrough()
        app.update()
        bar = widget._recovery_bar
        monkeypatch.setattr(module, "_set_exstyle_transparent", lambda *a: False)
        widget._recovery_reset.invoke()
        assert widget._clickthrough, "실패 시 해제됐다고 표시하면 안 됩니다"
        assert bar.winfo_exists(), "해제 실패해도 닫기는 사용할 수 있어야 합니다"
        widget._recovery_close.invoke()
        assert not bar.winfo_exists()
        assert app._widget is None
        assert not app.widget_visible_var.get()
        monkeypatch.setattr(module, "_set_exstyle_transparent", lambda *a: True)
        app._toggle_widget()
        app.update()
        widget = app._widget
        widget._click_var.set(True)
        widget._toggle_clickthrough()
        bar = widget._recovery_bar
        app.tk.call(bar.protocol("WM_DELETE_WINDOW"))
        assert app._widget is None, "복구 창의 OS 닫기도 위젯 전체를 닫아야 합니다"
        assert not bar.winfo_exists()
    finally:
        app.destroy()


def test_clear_releases_cached_image_callbacks():
    import gc
    import weakref
    from types import SimpleNamespace

    import customtkinter as ctk
    from PIL import Image

    from lol_coach.gui import components as ui
    from lol_coach.gui.champ_autocomplete import ChampionAutocomplete

    root = ctk.CTk()
    host = ctk.CTkFrame(root)
    image = ctk.CTkImage(Image.new("RGB", (32, 32)))
    app = SimpleNamespace(_icon_refs=[(host, image)], _render_target=host)
    refs = []
    try:
        for _ in range(3):
            group = ctk.CTkFrame(host)
            for kind in (ctk.CTkLabel, ctk.CTkButton):
                widget = kind(group, image=image, text="")
                refs.append(weakref.ref(widget))
            del widget, group
            CoachApp._clear(app, host)
        gc.collect()
        assert host.winfo_children() == []
        assert image._configure_callback_list == []
        assert all(ref() is None for ref in refs)

        autocomplete = object.__new__(ChampionAutocomplete)
        autocomplete._list_box = host
        group = ctk.CTkFrame(host)
        widget = ctk.CTkButton(group, image=image, text="")
        ref = weakref.ref(widget)
        del widget, group
        autocomplete._clear_list()
        gc.collect()
        assert image._configure_callback_list == []
        assert ref() is None
        reused = ctk.CTkLabel(host, image=ctk.CTkImage(Image.new("RGB", (16, 16))), text="")
        reused.pack()
        root.update()
        ui.clear_image(reused)
        gc.collect()
        assert not reused._label.cget("image")
        reused.configure(font=("Arial", 14))
    finally:
        root.destroy()


def test_autocomplete_only_fills_missing_icons(monkeypatch):
    from types import SimpleNamespace

    import customtkinter as ctk
    from PIL import Image

    from lol_coach.gui import champ_autocomplete as module
    from lol_coach.static import icons

    workers = []
    downloads = []
    image = ctk.CTkImage(Image.new("RGB", (32, 32)), size=(32, 32))
    placeholder_pil = Image.new("RGB", (32, 32))
    placeholder_pil.info["lol_coach_placeholder"] = True
    placeholder = ctk.CTkImage(placeholder_pil, size=(32, 32))
    missing = set()
    monkeypatch.setattr(icons, "champion_ctk", lambda key, size: placeholder if key in missing else image)

    def download(key, size):
        downloads.append(key)
        missing.discard(key)

    monkeypatch.setattr(icons, "champion_pil", download)
    monkeypatch.setattr(module.threading, "Thread", lambda target, **kw: SimpleNamespace(start=lambda: workers.append(target)))
    root = ctk.CTk()
    entry = ctk.CTkEntry(root)
    entry.pack()
    ac = module.ChampionAutocomplete(root, entry, _tk.StringVar(root), SimpleNamespace())
    hits = [{"id": "Ahri", "name": "아리"}, {"id": "Garen", "name": "가렌"}]
    try:
        ac._fill(hits)
        assert workers == [], "이미 있는 아이콘은 워커/전체 목록 재생성을 유발하지 않습니다"
        missing.add("Garen")
        ac._fill(hits)
        assert len(workers) == 1
        workers.pop()()
        root.update()
        assert downloads == ["Garen"]
        assert ac._rows == hits
        assert not placeholder._configure_callback_list, "실제 아이콘으로 갱신되어야 합니다"
        assert len(image._configure_callback_list) == 2
    finally:
        ac.hide()
        root.destroy()


def test_opening_aram_during_boot_does_not_fetch_on_ui_thread(monkeypatch, tmp_path):
    from lol_coach import config
    from lol_coach.gui import app as app_module

    monkeypatch.setattr(config, "UI_PATH", tmp_path / "ui.json")
    monkeypatch.setattr(app_module, "load_settings", lambda: config.Settings(riot_api_key=""))
    monkeypatch.setattr(CoachApp, "_spawn_thread", lambda *_args: None)
    monkeypatch.setattr(CoachApp, "_bind_hotkeys", lambda _self: None)
    monkeypatch.setattr(CoachApp, "_start_mayhem_select_watcher", lambda _self: None)
    monkeypatch.setattr(CoachApp, "_start_live_client_watcher", lambda _self: None)
    app = CoachApp()
    try:
        def no_network():
            raise AssertionError("탭 전환이 게임 데이터 다운로드를 기다리면 안 됩니다")

        monkeypatch.setattr(app.dd, "ensure_loaded", no_network)
        app._select_nav("ARAM 아수라장")
        app.update()
        assert "ARAM 아수라장" in app._tab_built
        assert app._page_title.cget("text") == "ARAM 아수라장"
        assert [name for name, frame in app._frames.items() if frame.winfo_ismapped()] == [
            "ARAM 아수라장"
        ], "선택하지 않은 화면은 Windows 표시 트리에서도 제외해야 합니다"
        assert any("준비 중" in widget.cget("text") for widget in app._aram_picker.winfo_children())

        app.dd._loaded = True
        app.dd._version = "16.19.1"
        monkeypatch.setattr(app.dd, "resolve_champion", lambda _key: None)
        app._on_static_data_ready()
        app.update()
        assert app._patch_label.cget("text") == "게임 데이터 16.19.1"
        assert len(app._aram_picker.winfo_children()) > 1
        picker = app._aram_picker
        app.aram_champ_var.set("아리")
        app._select_nav("소환사의 협곡")
        app.update()
        assert app._page_title.cget("text") == "소환사의 협곡"
        assert not app.t_aram.winfo_ismapped()
        app._select_nav("ARAM 아수라장")
        app.update()
        assert app._aram_picker is picker
        assert app.aram_champ_var.get() == "아리"
        assert not app.t_sr.winfo_ismapped()
        assert app.t_aram.winfo_ismapped()
        import customtkinter as ctk

        try:
            for scale in (1.3, 0.9, 1.0):
                ctk.set_widget_scaling(scale)
                app.update()
                assert [name for name, frame in app._frames.items() if frame.winfo_ismapped()] == [
                    "ARAM 아수라장"
                ], "배율 변경이 숨은 탭을 다시 표시하면 안 됩니다"
        finally:
            ctk.set_widget_scaling(1.0)
    finally:
        app.destroy()


def test_coach_app_instantiates_and_destroys() -> None:
    """앱 시작 크래시 회귀 — tk 초기화가 실제로 완료되는지 검증."""

    def _run() -> None:
        app = CoachApp()
        try:
            app.update()
            assert "롤 실전 코치" in app.title()
        finally:
            app.destroy()

    try:
        _run()
    except _tk.TclError:
        # Windows Tk 초기화 경합(Can't find usable tk.tcl) — 일시 오류 1회 재시도
        _run()


def test_augment_board_keeps_full_description_accessible_at_minimum_width(monkeypatch):
    from types import SimpleNamespace

    import customtkinter as ctk

    from lol_coach.analysis.aram_mayhem import AugmentTierTop
    from lol_coach.gui import tooltip
    from lol_coach.gui.aram_view import AugmentBoard
    from lol_coach.gui.components import PANEL

    tips = []
    monkeypatch.setattr(tooltip, "ToolTip", lambda widget, getter, **kw: tips.append(getter))
    root = ctk.CTk()
    root.geometry("680x600")
    host = ctk.CTkFrame(root, fg_color=PANEL)
    host.pack(fill="both", expand=True)
    host.grid_columnconfigure(0, weight=1)
    description = "공격 시 추가 피해를 입힙니다. " * 12
    pick = SimpleNamespace(
        name_ko="시작부터 끝까지", name_en="Test", rarity="gold",
        desc=description, reason="검증용 추천 근거",
    )
    proxy = SimpleNamespace(
        _sec=lambda parent, title, row: row,
        _update_aram_icon=lambda *args, **kw: None,
        _augment_icon=lambda *args: None,
    )
    try:
        board = AugmentBoard(host, proxy)
        board.pack(fill="x")
        board.show(AugmentTierTop((pick,) * 3, (pick,) * 3, (pick,) * 3), "test")
        root.update()
        assert any(description in tip() for tip in tips), "축약한 설명은 전체 툴팁으로 확인할 수 있어야 합니다"
        assert host.winfo_reqheight() < 430, "긴 원문이 추천 보드 전체를 밀어내면 안 됩니다"
        pick2 = SimpleNamespace(**{**vars(pick), "name_ko": "다음 증강", "desc": "새 효과"})
        cards = tuple(board.slots)
        board.show(AugmentTierTop((pick2,), (), ()), "next")
        root.update()
        assert tuple(board.slots) == cards
        assert any("새 효과" in tip() for tip in tips)
        assert not any(description in tip() for tip in tips)
    finally:
        root.destroy()


def test_aram_result_reuses_slots_and_defers_details():
    from types import SimpleNamespace

    import customtkinter as ctk

    from lol_coach.analysis.aram_mayhem import MayhemAdvice
    from lol_coach.gui.aram_view import AramResultView

    root = ctk.CTk()
    root.geometry("900x800")
    def flush_deferred():
        root.update_idletasks()
        root.after(10, root.quit)
        root.mainloop()

    tab = SimpleNamespace(
        _back_to_aram_pick=lambda: None,
        _update_aram_icon=lambda *a, **kw: None,
        _augment_icon=lambda *a: None,
        _schedule_aram_icon_fill=lambda: None,
        _aram_freshness_banner=lambda adv: "",
        _ai_key=lambda: "",
        _clear=lambda frame: [w.destroy() for w in frame.winfo_children()],
        _ai_gen=0,
    )
    try:
        host = ctk.CTkScrollableFrame(root)
        host.pack(fill="both", expand=True)
        host.grid_columnconfigure(0, weight=1)
        view = AramResultView(host, tab)
        view.grid(row=0, column=0, sticky="ew")
        first = MayhemAdvice("아리", "16.19", champ_key="Ahri", core_slots=["첫 아이템"], play_tips=["첫 팁"])
        second = MayhemAdvice("가렌", "16.19", champ_key="Garen", play_tips=["다음 팁"])
        view.show(first)
        flush_deferred()
        slots = tuple(view.items)
        assert view.details is None, "접힌 상세 설명은 아직 만들지 않아야 합니다"
        view.toggle_details()
        flush_deferred()
        assert view.details is not None
        assert "첫 팁" in "\n".join(label.cget("text") for label in view._detail_labels)
        view.show(second)
        assert view.champion.cget("text") == "가렌"
        assert tuple(view.items) == slots
        assert view.items[0].name.cget("text") == "상황 아이템"
        flush_deferred()
        assert view.expanded
        assert "다음 팁" in "\n".join(label.cget("text") for label in view._detail_labels)
        assert "첫 팁" not in "\n".join(label.cget("text") for label in view._detail_labels)
        view.show(second)
        flush_deferred()
        assert "다음 팁" in "\n".join(label.cget("text") for label in view._detail_labels), "동일 결과 재표시 때 상세 내용이 지워지면 안 됩니다"
        ai = []
        tab._ai_key = lambda: "test-no-network"
        tab._maybe_ai = lambda *args: ai.append(view.advice.champ_key)
        view.show(first)
        view.show(second)
        flush_deferred()
        assert ai == ["Garen"], "핵심 표시 후 AI 요청은 마지막 챔피언에만 시작합니다"
        view.show(first)
        view.suspend()
        flush_deferred()
        assert view._pending is None, "선택 화면으로 돌아가면 대기 중 상세 작업도 취소합니다"
        assert ai == ["Garen"]
    finally:
        root.destroy()
