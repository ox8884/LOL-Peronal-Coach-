"""설정창 디스코드 섹션 — 웹훅 URL 마스킹 (API 키와 동일 정책)."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import customtkinter as ctk
import pytest

from lol_coach.gui.settings_dialog import SettingsDialog

_ROOT: ctk.CTk | None = None


def _root() -> ctk.CTk:
    global _ROOT
    if _ROOT is None or not _ROOT.winfo_exists():
        for attempt in range(5):
            try:
                _ROOT = ctk.CTk()
                _ROOT.withdraw()
                break
            except tk.TclError:
                if attempt == 4:
                    raise
                import time as _time

                _time.sleep(0.4 * (attempt + 1))
    return _ROOT


@pytest.fixture(scope="module", autouse=True)
def _cleanup_root():
    yield
    global _ROOT
    if _ROOT is not None:
        try:
            _ROOT.destroy()
        except Exception:
            pass


def _find_entry(widget) -> ctk.CTkEntry:
    found: list[ctk.CTkEntry] = []

    def walk(w):
        for child in w.winfo_children():
            if isinstance(child, ctk.CTkEntry):
                found.append(child)
            walk(child)

    walk(widget)
    assert found, "웹훅 입력 엔트리를 찾지 못했습니다"
    return found[0]


def test_discord_webhook_entry_is_masked() -> None:
    """웹훅 토큰은 화면에 평문으로 노출되지 않는다 (show='•')."""
    root = _root()
    parent = ctk.CTkFrame(root)
    app = SimpleNamespace(
        discord_webhook_var=tk.StringVar(root, value="https://discord.com/api/webhooks/1/tok"),
        discord_review_var=tk.BooleanVar(root, value=True),
        _on_discord_review_toggle=lambda: None,
    )
    fake_self = SimpleNamespace(
        app=app,
        _card=lambda p, r: SettingsDialog._card(None, p, r),
        _save_discord_webhook=lambda: None,
        _send_test_card=lambda: None,
    )
    SettingsDialog._build_discord(fake_self, parent, 0)
    entry = _find_entry(parent)
    assert entry.cget("show") == "•"
    parent.destroy()
