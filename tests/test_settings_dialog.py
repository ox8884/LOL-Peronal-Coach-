"""설정창 회귀 테스트 — 탭 믹스인 이동으로 끊어진 command 참조 방지.

v1.6.100에서 설정창이 `app._show_api_help` / `app._on_discord_review_toggle`
(실제 소유자는 me_tab) 참조 때문에 열리지 않던 버그의 회귀 방지.
"""

from __future__ import annotations

import tkinter as tk

from lol_coach.gui.settings_dialog import SettingsDialog


def _stub_attrs(app: tk.Tk) -> None:
    """설정창이 참조하는 app 속성을 실제 루트에 얹는다 (누락 시 AttributeError)."""
    from lol_coach.config import (
        auto_open_latest_match_enabled,
        discord_review_enabled,
        game_end_auto_review_enabled,
        game_end_notify_enabled,
    )

    class _Settings:
        llm_api_key = ""
        llm_provider = "custom"
        llm_base_url = ""
        llm_model = ""

    app.settings = _Settings()
    app.llm_key_var = tk.StringVar()
    app.llm_provider_var = tk.StringVar(value="custom")
    app.llm_base_url_var = tk.StringVar()
    app.llm_model_var = tk.StringVar()
    app.game_end_notify_var = tk.BooleanVar(value=game_end_notify_enabled())
    app.game_end_auto_review_var = tk.BooleanVar(value=game_end_auto_review_enabled())
    app.auto_open_latest_var = tk.BooleanVar(value=auto_open_latest_match_enabled())
    app.game_start_notify_var = tk.BooleanVar(value=False)
    app.mayhem_overlay_var = tk.BooleanVar(value=True)
    app.widget_visible_var = tk.BooleanVar(value=False)
    app.boot_auto_load_var = tk.BooleanVar(value=True)
    app.discord_review_var = tk.BooleanVar(value=discord_review_enabled())
    app.discord_webhook_var = tk.StringVar()
    app.font_scale_var = tk.StringVar(value="1.0")
    app.ai_status_lbl = None

    class _MeTab:
        """설정창이 me_tab 으로 위임하는 토글 메서드 보유 (실제 MeTabMixin과 동일 소유)."""

        def _on_game_end_notify_toggle(self, *a) -> None: ...
        def _on_game_start_notify_toggle(self, *a) -> None: ...
        def _on_game_end_auto_review_toggle(self, *a) -> None: ...
        def _on_auto_open_latest_toggle(self, *a) -> None: ...
        def _on_boot_auto_load_toggle(self, *a) -> None: ...
        def _on_discord_review_toggle(self, *a) -> None: ...

        def _on_mayhem_overlay_toggle(self, *a) -> None: ...

    app.me_tab = _MeTab()

    for name in (
        "_save_llm_key",
        "_test_llm_connection",
        "_refresh_ai_status",
        "_apply_skin_live",
        "_set_font_scale",
        "_set_widget_visible",
        "_on_game_end_notify_toggle",
        "_on_game_start_notify_toggle",
        "_on_game_end_auto_review_toggle",
        "_on_auto_open_latest_toggle",
        "_on_discord_review_toggle",
        "_save_discord_webhook",
        "_send_test_card",
    ):
        setattr(app, name, lambda *a, _n=name: None)
    # 주의: _show_api_help 는 설정창 자체 메서드로 위임 — app 에는 없어야 정상


def test_settings_dialog_opens_without_attribute_errors() -> None:
    from tests.conftest import make_root

    root = make_root()
    _stub_attrs(root)

    dlg = SettingsDialog(root)
    root.update()
    assert dlg.winfo_exists()
    dlg.destroy()
    root.destroy()


def test_settings_dialog_has_own_api_help() -> None:
    """`_show_api_help` 는 설정창 자체 메서드여야 한다 (app 참조 회귀 방지)."""
    assert callable(getattr(SettingsDialog, "_show_api_help", None))


def test_custom_models_are_requested_on_click_and_ignore_old_endpoint(monkeypatch):
    from lol_coach import llm
    from tests.conftest import make_root

    root = make_root()
    _stub_attrs(root)
    monkeypatch.setattr(SettingsDialog, "_focus_self", lambda self: None)
    monkeypatch.setattr(SettingsDialog, "grab_set", lambda self: None)
    workers, completions, requests = [], [], []
    root._spawn_thread = workers.append
    dialog = SettingsDialog(root)
    dialog.withdraw()
    root.after = lambda ms, callback, *a: completions.append(callback)

    def models(**kwargs):
        requests.append(kwargs)
        return ["provider/model-a", "model-b"]

    monkeypatch.setattr(llm, "list_models", models)
    try:
        root.llm_base_url_var.set("https://one.example/v1")
        root.llm_key_var.set("test-key")
        assert workers == []
        dialog._ai_models_button.invoke()
        assert len(workers) == 1
        root.llm_base_url_var.set("https://two.example/v1")
        workers.pop()()
        completions.pop()()
        assert dialog._ai_model_menu.cget("values") == []
        assert requests == [{"api_key": "test-key", "base_url": "https://one.example/v1"}]
        dialog._ai_models_button.invoke()
        workers.pop()()
        completions.pop()()
        assert dialog._ai_model_menu.cget("values") == ["provider/model-a", "model-b"]
        dialog._ai_model_menu.set("my/manual-model")
        assert root.llm_model_var.get() == "my/manual-model"
        assert not hasattr(dialog, "_ai_provider_menu")
        dialog.destroy()
        assert root.llm_base_url_var.trace_info() == []
        assert root.llm_key_var.trace_info() == []
        assert root.ai_status_lbl is None
    finally:
        root.destroy()


def test_custom_models_error_keeps_manual_model_and_hides_secret(monkeypatch):
    from lol_coach import llm
    from tests.conftest import make_root

    root = make_root()
    _stub_attrs(root)
    monkeypatch.setattr(SettingsDialog, "_focus_self", lambda self: None)
    monkeypatch.setattr(SettingsDialog, "grab_set", lambda self: None)
    workers, completions = [], []
    root._spawn_thread = workers.append
    dialog = SettingsDialog(root)
    dialog.withdraw()
    root.after = lambda ms, callback, *a: completions.append(callback)

    def unavailable(**kwargs):
        raise RuntimeError("server echoed test-secret")

    monkeypatch.setattr(llm, "list_models", unavailable)
    try:
        root.llm_model_var.set("manual-only")
        dialog._ai_models_button.invoke()
        workers.pop()()
        completions.pop()()
        assert root.llm_model_var.get() == "manual-only"
        assert "test-secret" not in dialog._models_status.cget("text")
        assert dialog._ai_models_button.cget("state") == "normal"
    finally:
        root.destroy()
