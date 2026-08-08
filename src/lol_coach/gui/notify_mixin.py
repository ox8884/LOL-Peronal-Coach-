"""비모달 알림 — 상태바 + 짧은 토스트 (인게임 중 모달 차단 완화)."""

from __future__ import annotations

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM


class NotifyMixin:
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
    ) -> None:
        """상태바 + 화면 하단 토스트 (자동 소멸).

        level: info | warn | error | ok
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
                    if getattr(self, "_toast_win", None) is toast:
                        toast.destroy()
                        self._toast_win = None
                except Exception:
                    pass

            self._toast_after = self.after(ms, _hide)
        except Exception:
            pass

    def _notify_error(self, exc: BaseException | str, *, context: str = "") -> None:
        from lol_coach.gui.errors import format_user_error

        self._notify(format_user_error(exc, context=context), level="error", ms=5200)
