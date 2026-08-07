"""상시 표시 미니 위젯 — 마지막 분석 요약을 게임 위에 띄워둔다.

- 제목/본문 클릭 → 메인 창 포커스 (인게임에서 바로 복귀)
- 복사 버튼 → 요약 전체를 클립보드로
- 메인/위젯 단축키 Ctrl+Shift+W 로 토글
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui

FM = ("Malgun Gothic", 11)
FS = ("Malgun Gothic", 14, "bold")


class MiniWidget(ctk.CTkToplevel):
    """always-on-top 요약 창. ``set_summary``로 내용 갱신."""

    def __init__(self, master: Any, on_close: Any = None) -> None:
        super().__init__(master)
        self.title("롤 코치 위젯")
        self.geometry("340x460")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self._on_close = on_close
        self._master = master
        self._summary_lines: list[str] = []
        self.protocol("WM_DELETE_WINDOW", self._close)

        accent = ctk.CTkFrame(self, height=3, corner_radius=0, fg_color=ui.GOLD)
        accent.pack(fill="x")

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(8, 4))
        self.title_lbl = ctk.CTkLabel(
            head, text="요약 없음", font=FS, anchor="w", text_color=ui.GOLD_SOFT
        )
        self.title_lbl.pack(side="left")
        ctk.CTkButton(
            head,
            text="📋",
            width=34,
            height=26,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self.copy_summary,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkLabel(
            head,
            text="⌃⇧W",
            font=("Malgun Gothic", 9),
            text_color=ui.TEXT_MUTE,
        ).pack(side="right", padx=(0, 4))
        self.title_lbl.bind("<Button-1>", lambda _e: self.focus_main())
        self.top_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            head,
            text="항상 위",
            variable=self.top_var,
            width=70,
            font=FM,
            command=self._toggle_top,
        ).pack(side="right")

        self.body = ctk.CTkScrollableFrame(
            self,
            corner_radius=10,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._lbl("분석을 실행하면 여기에 요약이 표시됩니다.")

        try:
            self.bind("<Control-Shift-W>", lambda _e: self._toggle_from_widget())
            self.bind("<Control-Shift-w>", lambda _e: self._toggle_from_widget())
        except Exception:
            pass

    def _toggle_from_widget(self) -> None:
        try:
            if hasattr(self._master, "_toggle_widget"):
                self._master._toggle_widget()
        except Exception:
            pass

    def _lbl(self, text: str, **kw: Any) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(
            self.body,
            text=text,
            font=FM,
            anchor="w",
            justify="left",
            wraplength=310,
            **kw,
        )
        lbl.pack(fill="x", padx=4, pady=2)
        try:
            lbl.bind("<Button-1>", lambda _e: self.focus_main())
        except Exception:
            pass
        return lbl

    def _toggle_top(self) -> None:
        self.attributes("-topmost", bool(self.top_var.get()))

    def focus_main(self) -> None:
        """메인 창을 앞으로 (최소화 풀기 + 포커스)."""
        try:
            m = self._master
            m.deiconify()
            m.lift()
            m.focus_force()
        except Exception:
            pass

    def copy_summary(self) -> None:
        """현재 요약을 클립보드로 복사."""
        try:
            text = self.title_lbl.cget("text") or "요약"
            if self._summary_lines:
                text += "\n" + "\n".join(self._summary_lines)
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def _close(self) -> None:
        if callable(self._on_close):
            self._on_close()
        self.destroy()

    def set_summary(self, title: str, lines: list[str]) -> None:
        self.title_lbl.configure(text=title or "요약")
        self._summary_lines = list(lines)
        for w in self.body.winfo_children():
            w.destroy()
        if not lines:
            self._lbl("표시할 내용이 없습니다.")
            return
        for line in lines:
            self._lbl(line)
