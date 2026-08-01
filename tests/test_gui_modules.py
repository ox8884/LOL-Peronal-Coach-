"""신규 GUI 모듈(미니 위젯/툴팁) 생성 테스트 — 실제 Tk로 인스턴스화."""

import tkinter as tk

import customtkinter as ctk
import pytest

from lol_coach.gui.tooltip import ToolTip
from lol_coach.gui.widget import MiniWidget

_ROOT = None


def _root() -> ctk.CTk:
    """CTk는 프로세스당 한 번만 안전하게 초기화된다 (재생성 시 Tcl 오류)."""
    global _ROOT
    if _ROOT is None or not _ROOT.winfo_exists():
        ctk.set_appearance_mode("dark")
        _ROOT = ctk.CTk()
        _ROOT.withdraw()
    return _ROOT


@pytest.fixture(scope="module", autouse=True)
def _cleanup_root():
    yield
    # CTk 루트를 모듈 끝에서 파괴 — 살아 남으면 후속 테스트의 CTk 생성 시
    # PIL 이미지가 이 인터프리터에 묶여 "pyimageN doesn't exist" 오류 발생.
    global _ROOT
    if _ROOT is not None:
        try:
            _ROOT.destroy()
        except Exception:
            pass
        _ROOT = None


def test_mini_widget_summary_update() -> None:
    root = _root()
    widget = MiniWidget(root)
    widget.set_summary("⚡ vs 야스오", ["1. 아리 GD@15 +250", "· 팁 한 줄"])
    labels = [
        w.cget("text")
        for w in widget.body.winfo_children()
        if isinstance(w, ctk.CTkLabel)
    ]
    assert any("아리" in t for t in labels)
    # 갱신 시 이전 내용은 교첸다 (누적 아님)
    widget.set_summary("📋 상세", ["새 줄"])
    labels = [
        w.cget("text")
        for w in widget.body.winfo_children()
        if isinstance(w, ctk.CTkLabel)
    ]
    assert labels == ["새 줄"]
    widget.destroy()


def test_tooltip_bind_and_hide() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        btn = tk.Button(root, text="item")
        btn.pack()
        tip = ToolTip(btn, lambda: "설명 텍스트")
        tip.hide()  # 열리지 않은 상태에서도 안전
        tip._cancel()
        # 빈 텍스트면 표시하지 않음
        tip2 = ToolTip(btn, lambda: "")
        tip2._show()
        assert tip2._tip is None
    finally:
        root.destroy()


def test_widget_topmost_toggle() -> None:
    root = _root()
    widget = MiniWidget(root)
    assert widget.attributes("-topmost") == 1
    widget.top_var.set(False)
    widget._toggle_top()
    assert widget.attributes("-topmost") == 0
    widget.destroy()
