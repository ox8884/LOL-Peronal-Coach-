"""설정창 회귀 테스트 — 탭 믹스인 이동으로 끊어진 command 참조 방지.

v1.6.100에서 설정창이 `app._show_api_help` / `app._on_discord_review_toggle`
(실제 소유자는 me_tab) 참조 때문에 열리지 않던 버그의 회귀 방지.
"""

from __future__ import annotations

import tkinter as tk

from lol_coach.gui.settings_dialog import SettingsDialog


def _stub_attrs(app: tk.Tk) -> None:
    """설정창이 참조하는 app 속성을 실제 루트에 얹는다 (누락 시 AttributeError)."""
    from lol_coach import llm as _llm
    from lol_coach.config import (
        auto_open_latest_match_enabled,
        discord_review_enabled,
        game_end_auto_review_enabled,
        game_end_notify_enabled,
    )

    class _Settings:
        llm_api_key = ""
        llm_provider = "opencode-go"
        llm_model = ""

    app.settings = _Settings()
    app.llm_key_var = tk.StringVar()
    app.llm_provider_var = tk.StringVar(value=_llm.normalize_provider("opencode-go"))
    app._llm_provider_prev = app.llm_provider_var.get()
    prov = _llm.get_provider("opencode-go")
    app.llm_model_var = tk.StringVar(value=prov.default_model)
    app.game_end_notify_var = tk.BooleanVar(value=game_end_notify_enabled())
    app.game_end_auto_review_var = tk.BooleanVar(value=game_end_auto_review_enabled())
    app.auto_open_latest_var = tk.BooleanVar(value=auto_open_latest_match_enabled())
    app.game_start_notify_var = tk.BooleanVar(value=False)
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
        def _on_discord_review_toggle(self, *a) -> None: ...

    app.me_tab = _MeTab()

    for name in (
        "_on_llm_provider_change",
        "_refresh_llm_provider_ui",
        "_save_llm_key",
        "_test_llm_connection",
        "_start_openrouter_oauth",
        "_refresh_ai_status",
        "_apply_skin_live",
        "_set_font_scale",
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
