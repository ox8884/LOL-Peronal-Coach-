"""상시 표시 미니 위젯 — 마지막 분석 요약을 게임 위에 띄워둔다."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

FM = ("Malgun Gothic", 11)
FS = ("Malgun Gothic", 13, "bold")


class MiniWidget(ctk.CTkToplevel):
    """always-on-top 요약 창. ``set_summary``로 내용 갱신."""

    def __init__(self, master: Any, on_close: Any = None) -> None:
        super().__init__(master)
        self.title("롤 코치 위젯")
        self.geometry("340x460")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self._on_close = on_close
        self.protocol("WM_DELETE_WINDOW", self._close)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 4))
        self.title_lbl = ctk.CTkLabel(head, text="요약 없음", font=FS, anchor="w")
        self.title_lbl.pack(side="left")
        self.top_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            head,
            text="항상 위",
            variable=self.top_var,
            width=70,
            font=FM,
            command=self._toggle_top,
        ).pack(side="right")

        self.body = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._lbl("분석을 실행하면 여기에 요약이 표시됩니다.")

    def _lbl(self, text: str, **kw: Any) -> None:
        ctk.CTkLabel(
            self.body,
            text=text,
            font=FM,
            anchor="w",
            justify="left",
            wraplength=310,
            **kw,
        ).pack(fill="x", padx=4, pady=2)

    def _toggle_top(self) -> None:
        self.attributes("-topmost", bool(self.top_var.get()))

    def _close(self) -> None:
        if callable(self._on_close):
            self._on_close()
        self.destroy()

    def set_summary(self, title: str, lines: list[str]) -> None:
        self.title_lbl.configure(text=title or "요약")
        for w in self.body.winfo_children():
            w.destroy()
        if not lines:
            self._lbl("표시할 내용이 없습니다.")
            return
        for line in lines:
            self._lbl(line)
