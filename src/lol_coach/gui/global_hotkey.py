"""Windows 전역 핫키 (Ctrl+Shift+W) — 앱 포커스 없이도 위젯 토글.

실패해도 앱 동작에는 영향 없음 (권한·충돌 시 조용히 비활성).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_W = 0x57
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001


class GlobalHotkey:
    """스레드 메시지 루프로 RegisterHotKey 를 폴링."""

    def __init__(
        self,
        callback: Callable[[], None],
        *,
        hotkey_id: int = 0x4C4F4C31,  # 'LOL1'
        modifiers: int = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
        vk: int = VK_W,
    ) -> None:
        self._callback = callback
        self._hotkey_id = hotkey_id
        self._modifiers = modifiers
        self._vk = vk
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.registered = False
        self.error: str = ""

    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return self.registered
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="lol-coach-hotkey", daemon=True)
        self._thread.start()
        # 등록 결과 대기 (짧게)
        for _ in range(40):
            if self.registered or self.error:
                break
            self._stop.wait(0.025)
        return self.registered

    def stop(self) -> None:
        self._stop.set()
        # 메시지 펌핑 깨우기용 — 등록 스레드에 빈 메시지
        try:
            import ctypes

            if self._thread is not None and self._thread.ident:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread.ident,
                    0x0012,
                    0,
                    0,  # WM_QUIT-ish; Peek will exit on stop
                )
        except Exception:
            pass
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=1.5)
        self._thread = None
        self.registered = False

    def _loop(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes
        except Exception as exc:  # pragma: no cover
            self.error = str(exc)
            return

        user32 = ctypes.windll.user32
        # 이 스레드에 핫키 등록
        ok = user32.RegisterHotKey(None, self._hotkey_id, self._modifiers, self._vk)
        if not ok:
            err = ctypes.get_last_error()
            self.error = f"RegisterHotKey 실패 (code={err})"
            return
        self.registered = True
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                # 논블로킹 폴링
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                        try:
                            self._callback()
                        except Exception:
                            pass
                self._stop.wait(0.05)
        finally:
            try:
                user32.UnregisterHotKey(None, self._hotkey_id)
            except Exception:
                pass
            self.registered = False


def schedule_on_ui(app: Any, fn: Callable[[], None]) -> None:
    """워커/핫키 스레드 → Tk 메인 스레드 마샬링."""
    try:
        app.after(0, fn)
    except Exception:
        try:
            fn()
        except Exception:
            pass
