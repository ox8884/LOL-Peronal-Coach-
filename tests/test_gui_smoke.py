"""실 GUI 스모크 — CoachApp 생성·이벤트 처리·종료.

v1.6.33 회귀(Protocol 스텁이 tkinter를 섀도잉해 시작 시 RecursionError)를
잡기 위한 최소 실기동 테스트. Tk 디스플레이가 있는 환경에서만 의미가 있다.
"""

from __future__ import annotations

import tkinter as _tk

from lol_coach.gui.app import CoachApp


def test_coach_app_instantiates_and_destroys() -> None:
    """앱 시작 크래시 회귀 — tk 초기화가 실제로 완료되는지 검증."""

    def _run() -> None:
        app = CoachApp()
        try:
            app.update()
            assert "롤 실전 코치" in app.title()
        finally:
            app.destroy()

    try:
        _run()
    except _tk.TclError:
        # Windows Tk 초기화 경합(Can't find usable tk.tcl) — 일시 오류 1회 재시도
        _run()
