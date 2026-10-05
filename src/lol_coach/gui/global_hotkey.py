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
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
INFINITE = 0xFFFFFFFF
WAIT_FAILED = 0xFFFFFFFF


class GlobalHotkey:
    """스레드 메시지 루프로 RegisterHotKey 를 대기."""

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
        self._registration_ready = threading.Event()
        self._handle_lock = threading.Lock()
        self._stop_handle: int | None = None
        self._kernel32: Any = None
        self._thread: threading.Thread | None = None
        self.registered = False
        self.error: str = ""

    def start(self, wait: bool = True) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return self.registered
        self._stop.clear()
        self._registration_ready.clear()
        self.registered = False
        self.error = ""
        self._thread = threading.Thread(target=self._loop, name="lol-coach-hotkey", daemon=True)
        self._thread.start()
        if not wait:
            # 부팅 경로 — 등록 확인(최대 1초)을 기다리면 mainloop 시작 전
            # 메인 스레드가 블록된다. 등록 성공 여부는 registered 속성으로.
            return False
        # 등록 결과 대기 (짧게). 등록 스레드가 신호를 보낼 때만 깨어난다.
        self._registration_ready.wait(timeout=1.0)
        return self.registered

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        with self._handle_lock:
            if self._stop_handle is not None and not self._kernel32.SetEvent(self._stop_handle):
                import ctypes

                self.error = f"SetEvent 실패 (code={ctypes.get_last_error()})"
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.5)
        if t is None or not t.is_alive():
            self._thread = None

    def _loop(self) -> None:
        handle = None
        registered = False
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateEventW.restype = wintypes.HANDLE
            kernel32.SetEvent.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            user32.MsgWaitForMultipleObjects.argtypes = [
                wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL,
                wintypes.DWORD, wintypes.DWORD,
            ]
            user32.MsgWaitForMultipleObjects.restype = wintypes.DWORD
            handle = kernel32.CreateEventW(None, True, False, None)
            if not handle:
                self.error = f"CreateEvent 실패 (code={ctypes.get_last_error()})"
                return
            with self._handle_lock:
                self._kernel32 = kernel32
                self._stop_handle = handle
            handles = (wintypes.HANDLE * 1)(handle)
            msg = wintypes.MSG()
            # PeekMessageW는 이 스레드에 message queue를 만들기 위한 1회 호출이다.
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
            if self._stop.is_set():
                return

            ok = user32.RegisterHotKey(None, self._hotkey_id, self._modifiers, self._vk)
            if not ok:
                err = ctypes.get_last_error()
                self.error = f"RegisterHotKey 실패 (code={err})"
                return
            registered = self.registered = True
            self._registration_ready.set()

            while not self._stop.is_set():
                # 메시지 queue와 종료 이벤트를 함께 기다려 WM_QUIT 전송에 의존하지 않는다.
                result = user32.MsgWaitForMultipleObjects(1, handles, False, INFINITE, QS_ALLINPUT)
                if result == 0:
                    break
                if result == WAIT_FAILED:
                    self.error = f"MsgWaitForMultipleObjects 실패 (code={ctypes.get_last_error()})"
                    break
                while not self._stop.is_set() and user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        return
                    if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                        try:
                            self._callback()
                        except Exception:
                            pass
        except Exception as exc:
            self.error = str(exc)
        finally:
            self._registration_ready.set()
            try:
                if registered:
                    user32.UnregisterHotKey(None, self._hotkey_id)
            except Exception:
                pass
            self.registered = False
            with self._handle_lock:
                self._stop_handle = None
                if handle:
                    kernel32.CloseHandle(handle)
                self._kernel32 = None


def schedule_on_ui(app: Any, fn: Callable[[], None]) -> None:
    """워커/핫키 스레드 → Tk 메인 스레드 마샬링."""
    try:
        app.after(0, fn)
    except Exception:
        try:
            fn()
        except Exception:
            pass
