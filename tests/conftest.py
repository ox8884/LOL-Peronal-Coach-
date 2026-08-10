"""GUI 테스트 공용 헬퍼.

Windows에서 Tcl 초기화가 간헐적으로 실패("tk wasn't installed properly")
하는 일시 오류가 있어, 루트 생성을 짧은 백오프로 재시도한다.
"""

from __future__ import annotations

import time
import tkinter as tk

_TK_RETRIES = 5
_TK_RETRY_SLEEP_S = 0.4


def make_root() -> tk.Tk:
    """일시적 Tcl 초기화 오류를 백오프로 재시도하는 withdrawn 루트."""
    for attempt in range(_TK_RETRIES):
        try:
            root = tk.Tk()
            root.withdraw()
            return root
        except tk.TclError:
            if attempt == _TK_RETRIES - 1:
                raise
            time.sleep(_TK_RETRY_SLEEP_S * (attempt + 1))
    raise AssertionError("unreachable")
