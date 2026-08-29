"""비모달 알림 — 상태바 + 짧은 토스트 (인게임 중 모달 차단 완화)."""

from __future__ import annotations

import ctypes
from typing import Any

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FONT_UI
from lol_coach.gui.types import MixinBase


class NotifyMixin(MixinBase):
    """CoachApp 믹스인: ``_notify`` / ``_flash_status``."""

    def _flash_status(self, text: str) -> None:
        """메인 상태바만 갱신."""
        try:
            self.status.configure(text=text)
        except Exception:
            pass

    def _notify(
        self,
        message: str,
        *,
        level: str = "info",
        ms: int = 3800,
        also_status: bool = True,
        force: bool = False,
    ) -> None:
        """게임 중에는 큐에 넣고, 그 외에는 상태바 + 토스트를 표시한다.

        force=True 이면 인게임 차단을 무시한다 (사용자가 누른 증강 읽기 등).
        """
        if not force and getattr(self, "_live_notification_blocked", False):
            self._queue_notification(message, level, ms, also_status)
            return
        self._deliver_notification(
            message,
            level=level,
            ms=ms,
            also_status=also_status,
            overlay=force,
        )

    def _queue_notification(
        self,
        message: str,
        level: str,
        ms: int,
        also_status: bool,
    ) -> None:
        queue = getattr(self, "_notification_queue", None)
        if queue is None:
            queue = []
            self._notification_queue = queue
        item = (message, level, ms, also_status)
        if item not in queue:
            queue.append(item)

    def _flush_notification_queue(self) -> None:
        queue = list(getattr(self, "_notification_queue", []))
        self._notification_queue = []
        if not queue:
            return
        # 심각도 우선 플러시 — 게임 중 쌓인 error/warn가 info에 묻히지 않게
        priority = {"error": 0, "warn": 1, "ok": 2, "info": 3}
        message, level, ms, also_status = min(queue, key=lambda item: priority.get(item[1], 3))
        self._deliver_notification(
            message,
            level=level,
            ms=ms,
            also_status=also_status,
        )

    def _deliver_notification(
        self,
        message: str,
        *,
        level: str = "info",
        ms: int = 3800,
        also_status: bool = True,
        overlay: bool = False,
    ) -> None:
        """상태바 + 화면 하단 토스트 (자동 소멸).

        level: info | warn | error | ok
        overlay=True 이면 롤 위에 뜨는 별도 창도 연다 (전체화면 전용은 가려질 수 있음).
        """
        colors = {
            "info": (ui.PANEL, ui.GOLD_SOFT),
            "warn": (ui.PANEL, ui.WARN),
            "error": (ui.PANEL, ui.RED_SOFT),
            "ok": (ui.PANEL, ui.GREEN),
        }
        bg, fg = colors.get(level, colors["info"])
        if also_status:
            self._flash_status(message)

        # 이전 토스트 제거
        old = getattr(self, "_toast_win", None)
        if old is not None:
            try:
                self.after_cancel(getattr(self, "_toast_after", None))
            except Exception:
                pass
            try:
                old.destroy()
            except Exception:
                pass
            self._toast_win = None

        try:
            import customtkinter as ctk

            toast = ctk.CTkFrame(
                self,
                fg_color=bg,
                corner_radius=10,
                border_width=1,
                border_color=ui.BORDER,
            )
            toast.place(relx=0.5, rely=0.94, anchor="s")
            ctk.CTkLabel(
                toast,
                text=message,
                font=FM,
                text_color=fg,
                wraplength=720,
                justify="center",
            ).pack(padx=16, pady=10)
            self._toast_win = toast

            def _hide() -> None:
                try:
                    cur = self._toast_win
                    if cur is not None and cur is toast:
                        cur.destroy()
                        self._toast_win = None
                except Exception:
                    pass

            self._toast_after = self.after(ms, _hide)
        except Exception:
            pass
        if overlay:
            self._show_overlay_toast(message, level=level, ms=ms)

    def _show_overlay_toast(self, message: str, *, level: str = "info", ms: int = 6000) -> None:
        """게임 위에 뜨는 작은 안내. 포커스는 빼앗지 않는다."""
        old = getattr(self, "_overlay_win", None)
        if old is not None:
            try:
                self.after_cancel(getattr(self, "_overlay_after", None))
            except Exception:
                pass
            try:
                old.destroy()
            except Exception:
                pass
            self._overlay_win = None
        try:
            import tkinter as tk

            colors = {
                "info": ("#1B2230", "#E8C872"),
                "warn": ("#2A2214", "#E0A040"),
                "error": ("#2A1418", "#E07070"),
                "ok": ("#14241A", "#7DCEA0"),
            }
            bg, fg = colors.get(level, colors["info"])
            parent: Any = self
            win = tk.Toplevel(parent)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            try:
                win.attributes("-alpha", 0.94)
            except Exception:
                pass
            frame = tk.Frame(win, bg=bg, bd=1, relief="solid", highlightthickness=0)
            frame.pack(fill="both", expand=True)
            tk.Label(
                frame,
                text=message,
                font=(FONT_UI, 13, "bold"),
                fg=fg,
                bg=bg,
                wraplength=720,
                justify="center",
            ).pack(padx=18, pady=12)
            win.update_idletasks()
            ww = win.winfo_reqwidth()
            sw = win.winfo_screenwidth()
            win.geometry(f"+{max(24, (sw - ww) // 2)}+40")
            _noactivate_topmost(win)
            self._overlay_win = win

            def _hide() -> None:
                try:
                    cur = getattr(self, "_overlay_win", None)
                    if cur is not None and cur is win:
                        cur.destroy()
                        self._overlay_win = None
                except Exception:
                    pass

            self._overlay_after = self.after(ms, _hide)
        except Exception:
            pass

    def _notify_error(self, exc: BaseException | str, *, context: str = "") -> None:
        from lol_coach.gui.errors import format_user_error

        self._notify(format_user_error(exc, context=context), level="error", ms=5200)


def _noactivate_topmost(win: object) -> None:
    try:
        hwnd = int(win.winfo_id())  # type: ignore[attr-defined]
        user32 = ctypes.windll.user32
        gwl_exstyle = -20
        style = user32.GetWindowLongW(hwnd, gwl_exstyle)
        style |= 0x08000000 | 0x00000080 | 0x00000008  # NOACTIVATE | TOOLWINDOW | TOPMOST
        user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
    except Exception:
        pass
