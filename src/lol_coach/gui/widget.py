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
        # 화면 밖에서 초기화 — app.py에서 저장된 위치로 옮길 때 깜빡임 방지
        self.geometry("340x460+-9999+-9999")
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
        # 폰트 크기 조절 — 작게/크게
        try:
            from lol_coach.config import load_ui_settings

            saved_size = int(load_ui_settings().get("widget_font_size", 11) or 11)
        except (TypeError, ValueError):
            saved_size = 11
        self._font_size = max(9, min(20, saved_size))
        ctk.CTkButton(
            head,
            text="−",
            width=26,
            height=26,
            font=("Malgun Gothic", 14, "bold"),
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._font_smaller,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            head,
            text="＋",
            width=26,
            height=26,
            font=("Malgun Gothic", 14, "bold"),
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._font_larger,
        ).pack(side="right", padx=(2, 0))
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
        self._apply_font_size()

        try:
            self.bind("<Control-Shift-W>", lambda _e: self._toggle_from_widget())
            self.bind("<Control-Shift-w>", lambda _e: self._toggle_from_widget())
        except Exception:
            pass
        # 이동/리사이즈 시 위치 실시간 저장 (다음 실행 시 복원)
        self._geo_save_scheduled = False
        self._geo_ready = False  # app.py에서 복원 완료 후 True로 전환
        self.bind("<Configure>", self._on_configure)

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
            font=("Malgun Gothic", self._font_size),
            anchor="w",
            justify="left",
            wraplength=max(200, self.winfo_width() - 24 if self.winfo_width() > 24 else 310),
            **kw,
        )
        lbl.pack(fill="x", padx=4, pady=2)
        try:
            lbl.bind("<Button-1>", lambda _e: self.focus_main())
        except Exception:
            pass
        return lbl

    def _font_larger(self) -> None:
        self._font_size = min(20, self._font_size + 1)
        self._apply_font_size()
        self._save_font_size()

    def _font_smaller(self) -> None:
        self._font_size = max(9, self._font_size - 1)
        self._apply_font_size()
        self._save_font_size()

    def _apply_font_size(self) -> None:
        """본문 라벨 폰트 크기 + wraplength 일괄 적용."""
        new_font = ("Malgun Gothic", self._font_size)
        wrap = max(200, self.winfo_width() - 24 if self.winfo_width() > 24 else 310)
        for w in self.body.winfo_children():
            try:
                if isinstance(w, ctk.CTkLabel):
                    w.configure(font=new_font, wraplength=wrap)
            except Exception:
                pass

    def _save_font_size(self) -> None:
        try:
            from lol_coach.config import save_ui_settings

            save_ui_settings(widget_font_size=self._font_size)
        except Exception:
            pass

    def _on_configure(self, _event: Any) -> None:
        """위젯 이동/리사이즈 시 geometry 저장 (디바운스).

        <Configure> 는 맵핑 시에도 발생하므로, 복원 완료(_geo_ready) 전에는
        기본 위치가 덮어쓰지 않도록 저장을 건너뛴다.
        """
        if not self._geo_ready or self._geo_save_scheduled:
            return
        self._geo_save_scheduled = True
        try:
            self.after(300, self._save_geometry)
        except Exception:
            self._geo_save_scheduled = False

    def _save_geometry(self) -> None:
        self._geo_save_scheduled = False
        if not self._geo_ready:
            return
        try:
            from lol_coach.config import save_ui_settings

            save_ui_settings(widget_geometry=self.geometry())
        except Exception:
            pass

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
        # 닫기 전 최종 위치 저장 (복원 완료 후에만)
        if self._geo_ready:
            self._save_geometry()
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
