"""GUI 테스트 공용 헬퍼.

Windows에서 Tcl 초기화가 간헐적으로 실패("tk wasn't installed properly")
하는 일시 오류가 있어, 루트 생성을 한 번 재시도한다.
"""

from __future__ import annotations

import time
import tkinter as tk


def make_root() -> tk.Tk:
    """일시적 Tcl 초기화 오류를 한 번 재시도하는 withdrawn 루트."""
    try:
        root = tk.Tk()
    except tk.TclError:
        time.sleep(0.3)
        root = tk.Tk()
    root.withdraw()
    return root
