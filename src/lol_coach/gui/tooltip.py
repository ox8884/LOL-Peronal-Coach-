"""CTk 위젯용 호버 툴팁 (아이템/룬 설명 표시)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from lol_coach.gui import components as ui


class ToolTip:
    """위젯에 마우스를 올리면 작은 설명 창을 띄운다.

    ``text_fn``: 표시할 문자열을 돌려주는 콜백 (빈 문자열이면 표시 안 함).
    지연 생성(lazy)이라 메인 스레드에서 네트워크를 타지 않는다 —
    데이터는 미리 로드된 DataDragon/로컬라이저에서만 가져올 것.
    """

    def __init__(
        self,
        widget: tk.Widget,
        text_fn: Callable[[], str],
        *,
        delay_ms: int = 350,
        wrap: int = 320,
    ) -> None:
        self.widget = widget
        self.text_fn = text_fn
        self.delay = delay_ms
        self.wrap = wrap
        self._tip: tk.Toplevel | None = None
        self._job: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self) -> None:
        self._job = None
        if self._tip is not None:
            return
        try:
            text = self.text_fn() or ""
        except Exception:
            text = ""
        if not text.strip():
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tip.attributes("-topmost", True)
        frame = tk.Frame(
            tip, background=ui.PANEL, highlightbackground=ui.GOLD,
            highlightthickness=1,
        )
        frame.pack()
        tk.Label(
            frame,
            text=text,
            justify="left",
            background=ui.PANEL,
            foreground=ui.TEXT,
            font=("Malgun Gothic", 10),
            wraplength=self.wrap,
            padx=8,
            pady=6,
        ).pack()
        self._tip = tip

    def hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
