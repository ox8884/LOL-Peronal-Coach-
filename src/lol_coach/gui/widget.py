"""상시 표시 미니 오버레이 위젯 — 마지막 분석 요약을 게임 위에 띄워둔다.

- 제목/본문 클릭 → 메인 창 포커스 (인게임에서 바로 복귀)
- 복사 버튼 → 요약 전체를 클립보드로
- 투명도 조절 + 클릭 통과(클릭스루) → 게임 플레이를 가리지 않는 진짜 오버레이
- 메인/위젯 단축키 Ctrl+Shift+W 로 토글 (클릭 통과 중에도 전역 핫키로 해제)
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.gui import icons
from lol_coach.gui.constants import FCH, FONT_UI

FS = (FONT_UI, 14, "bold")

# Windows 확장 창 스타일
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020


def _user32() -> Any:
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    api.GetWindowLongW.restype = wintypes.LONG
    api.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    api.SetWindowLongW.restype = wintypes.LONG
    return api


def _hwnd_of(widget: Any) -> int:
    """Tk 위젯 → 실제 최상위 HWND (Windows). 실패 시 0."""
    try:
        return int(_user32().GetAncestor(widget.winfo_id(), 2) or 0)
    except Exception:
        return 0


def _set_exstyle_transparent(hwnd: int, enabled: bool) -> bool:
    """WS_EX_TRANSPARENT(마우스 이벤트 통과) 토글. 성공 여부 반환."""
    if not hwnd:
        return False
    try:
        import ctypes

        user32 = _user32()
        ctypes.set_last_error(0)
        ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if not ex and ctypes.get_last_error():
            return False
        style = ex | _WS_EX_LAYERED | _WS_EX_TRANSPARENT if enabled else ex & ~_WS_EX_TRANSPARENT
        ctypes.set_last_error(0)
        previous = user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
        if not previous and ctypes.get_last_error():
            return False
        ctypes.set_last_error(0)
        actual = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        return not ctypes.get_last_error() and bool(actual & _WS_EX_TRANSPARENT) == enabled
    except Exception:
        return False


class MiniWidget(ctk.CTkToplevel):
    """always-on-top 요약 오버레이. ``set_summary``로 내용 갱신."""

    def __init__(self, master: Any, on_close: Any = None) -> None:
        super().__init__(master)
        self.title("롤 코치 위젯")
        # 화면 밖에서 초기화 — app.py에서 저장된 위치로 옮길 때 깜빡임 방지
        self.geometry("340x460+-9999+-9999")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        self.minsize(300, 200)
        self._on_close = on_close
        self._master = master
        self._summary_lines: list[str] = []
        self._clickthrough = False
        self._recovery_bar: ctk.CTkToplevel | None = None
        self.protocol("WM_DELETE_WINDOW", self._close)

        accent = ctk.CTkFrame(self, height=3, corner_radius=0, fg_color=ui.GOLD)
        accent.pack(fill="x")

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(8, 2))
        self.title_lbl = ctk.CTkLabel(
            head, text="요약 없음", font=FS, anchor="w", text_color=ui.GOLD_SOFT
        )
        self.title_lbl.pack(side="left")
        self._icon_btn(head, "copy", 34, self.copy_summary).pack(side="right", padx=(6, 0))
        # 폰트 크기 조절 — 작게/크게
        try:
            from lol_coach.config import load_ui_settings

            saved_size = int(load_ui_settings().get("widget_font_size", 11) or 11)
        except (TypeError, ValueError):
            saved_size = 11
        self._font_size = max(9, min(20, saved_size))
        fam = icons.icon_font()
        size_font: tuple = (fam, 11) if fam else (FONT_UI, 13, "bold")
        self._icon_btn(head, "remove", 26, self._font_smaller, glyph_font=size_font).pack(
            side="right", padx=(4, 0)
        )
        self._icon_btn(head, "add", 26, self._font_larger, glyph_font=size_font).pack(
            side="right", padx=(4, 0)
        )
        ctk.CTkLabel(
            head,
            text="⌃⇧W",
            font=FCH,
            text_color=ui.TEXT_MUTE,
        ).pack(side="right", padx=(0, 6))
        self.title_lbl.bind("<Button-1>", lambda _e: self.focus_main())

        # 오버레이 컨트롤 행 — 항상 위 · 투명도 · 클릭 통과
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=(0, 4))
        self.top_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            ctrl,
            text="항상 위",
            variable=self.top_var,
            width=66,
            font=FCH,
            command=self._toggle_top,
        ).pack(side="left")
        self._click_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ctrl,
            text="클릭 통과",
            variable=self._click_var,
            width=76,
            font=FCH,
            command=self._toggle_clickthrough,
        ).pack(side="right")
        ctk.CTkLabel(ctrl, text="투명", font=FCH, text_color=ui.TEXT_MUTE).pack(
            side="right", padx=(6, 4)
        )
        try:
            from lol_coach.config import load_ui_settings

            saved_alpha = float(load_ui_settings().get("widget_alpha", 1.0) or 1.0)
        except (TypeError, ValueError):
            saved_alpha = 1.0
        self._alpha = max(0.5, min(1.0, saved_alpha))
        self._alpha_slider = ctk.CTkSlider(
            ctrl,
            from_=0.5,
            to=1.0,
            width=64,
            number_of_steps=10,
            command=self._set_alpha,
        )
        self._alpha_slider.set(self._alpha)
        self._alpha_slider.pack(side="right")

        self.body = ctk.CTkScrollableFrame(
            self,
            corner_radius=10,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.body.pack(fill="both", expand=True, padx=10, pady=(2, 10))
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
        self._alpha_save_after: str | None = None  # 알파 저장 디바운스 after id
        self.bind("<Configure>", self._on_configure, add="+")

    def _icon_btn(
        self,
        parent: Any,
        icon_name: str,
        size: int,
        command: Any,
        *,
        glyph_font: tuple | None = None,
    ) -> ctk.CTkButton:
        """아이콘 폰트 버튼 (없으면 한글 텍스트 폴백)."""
        fam = icons.icon_font()
        text = icons.glyph(icon_name)
        if fam and text:
            font = glyph_font or (fam, 12)
            width = size
        else:
            text = icons.FALLBACK_TEXT.get(icon_name, icon_name)
            font = FCH
            width = size + 16
        return ctk.CTkButton(
            parent,
            text=text,
            width=width,
            height=26,
            font=font,
            **ui.btn(*ui.BTN_SECONDARY),
            command=command,
        )

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
            font=(FONT_UI, self._font_size),
            anchor="w",
            justify="left",
            wraplength=max(200, self.winfo_width() - 24 if self.winfo_width() > 24 else 310),
            **kw,
        )
        lbl.pack(fill="x", padx=4, pady=2)
        lbl.bind("<Button-1>", lambda _e: self.focus_main())
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
        new_font = (FONT_UI, self._font_size)
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

    def _set_alpha(self, value: float) -> None:
        self._alpha = max(0.5, min(1.0, float(value)))
        try:
            self.attributes("-alpha", self._alpha)
        except Exception:
            pass
        # 슬라이더 드래그 중 command가 계속 발화한다 — 투명도 적용은 즉시,
        # 디스크 쓰기(ui.json)는 300ms 디바운스
        try:
            self.after_cancel(self._alpha_save_after)
        except Exception:
            pass
        try:
            self._alpha_save_after = self.after(300, self._save_alpha)
        except Exception:
            self._save_alpha()

    def _save_alpha(self) -> None:
        self._alpha_save_after = None
        try:
            from lol_coach.config import save_ui_settings

            save_ui_settings(widget_alpha=round(self._alpha, 2))
        except Exception:
            pass

    def _toggle_clickthrough(self) -> None:
        self._set_clickthrough(bool(self._click_var.get()))

    def _set_clickthrough(self, enabled: bool) -> None:
        """본문만 통과시키고 별도 네이티브 창에 해제/닫기를 남긴다."""
        try:
            if enabled:
                self._show_recovery_bar()
                if self._alpha >= 0.99:
                    self._alpha_slider.set(0.9)
                    self._set_alpha(0.9)
            ok = _set_exstyle_transparent(_hwnd_of(self), enabled)
        except tk.TclError:
            ok = False
        if not ok:
            self._click_var.set(self._clickthrough)
            if not self._clickthrough:
                self._hide_recovery_bar()
            self._notify_parent("클릭 통과를 변경하지 못했습니다. 위젯을 닫고 다시 열어 주세요.", level="warn")
            return
        self._clickthrough = enabled
        self._click_var.set(enabled)
        if enabled:
            self._notify_parent("클릭 통과 켜짐 · 위젯 상단에서 해제하거나 닫을 수 있습니다", level="ok")
        else:
            self._hide_recovery_bar()

    def _show_recovery_bar(self) -> None:
        if self._recovery_bar is not None:
            return
        bar = self._recovery_bar = ctk.CTkToplevel(self)
        bar.protocol("WM_DELETE_WINDOW", self._close)
        bar.withdraw()
        bar.overrideredirect(True)
        bar.transient(self)
        bar.attributes("-topmost", bool(self.top_var.get()))
        frame = ctk.CTkFrame(bar, corner_radius=0, fg_color=ui.PANEL)
        frame.pack(fill="both", expand=True)
        self._recovery_reset = ctk.CTkButton(
            frame, text="클릭 통과 해제", font=FCH, width=150, height=30,
            **ui.btn(*ui.BTN_PRIMARY), command=self.reset_clickthrough,
        )
        self._recovery_reset.pack(side="left", padx=6, pady=6)
        self._recovery_close = ctk.CTkButton(
            frame, text="닫기", font=FCH, width=60, height=30,
            **ui.btn(*ui.BTN_SECONDARY), command=self._close,
        )
        self._recovery_close.pack(side="right", padx=6, pady=6)
        bar.update_idletasks()
        self._position_recovery_bar()
        bar.deiconify()
        bar.lift()

    def _position_recovery_bar(self) -> None:
        bar = self._recovery_bar
        if bar is not None:
            # Tk Toplevel은 물리 픽셀을 사용해 CTk 배율과 무관하게 부모에 맞춘다.
            tk.Toplevel.geometry(
                bar,
                f"{self.winfo_width()}x{bar.winfo_reqheight()}"
                f"+{self.winfo_rootx()}+{self.winfo_rooty()}"
            )

    def _hide_recovery_bar(self) -> None:
        if self._recovery_bar is not None:
            self._recovery_bar.destroy()
            self._recovery_bar = None

    def _notify_parent(self, msg: str, level: str = "info") -> None:
        try:
            m = self._master
            if hasattr(m, "_notify"):
                m._notify(msg, level=level)
        except Exception:
            pass

    def reset_clickthrough(self) -> None:
        self._set_clickthrough(False)

    def _on_configure(self, _event: Any) -> None:
        """위젯 이동/리사이즈 시 geometry 저장 (디바운스).

        <Configure> 는 맵핑 시에도 발생하므로, 복원 완료(_geo_ready) 전에는
        기본 위치가 덮어쓰지 않도록 저장을 건너뛴다.
        """
        if _event.widget is not self:
            return
        self._position_recovery_bar()
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
        if self._recovery_bar is not None:
            self._recovery_bar.attributes("-topmost", bool(self.top_var.get()))

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

    def destroy(self) -> None:
        self._hide_recovery_bar()
        super().destroy()

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
