"""GUI 검증 캡처 스크립트 (개발 전용).

앱을 띄워 세션 리포트·내 전적·미니 위젯 화면을 PNG로 저장 후 종료.
topmost로 잠깐 앞에 나타났다가 자동으로 닫힌다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageGrab

OUT = Path("shots")
OUT.mkdir(exist_ok=True)


def grab(app, name: str) -> None:
    app.update_idletasks()
    app.update()
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    w = app.winfo_width()
    h = app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(OUT / name)
    print("saved", name)


def run() -> None:
    from lol_coach.gui.app import CoachApp

    app = CoachApp()
    app.geometry("1120x920+40+40")
    app.attributes("-topmost", True)
    app.update()

    def s1() -> None:
        grab(app, "1_main.png")
        app._select_nav("세션 리포트")
        app.after(1500, s2)

    def s2() -> None:
        grab(app, "2_session.png")
        app._select_nav("내 전적")
        app.after(1200, s3)

    def s3() -> None:
        grab(app, "3_me.png")
        app._select_nav("ARAM 아수라장")
        app.after(800, s4)

    def s4() -> None:
        grab(app, "4_aram.png")
        app._toggle_widget()
        app.after(1200, s5)

    def s5() -> None:
        w = getattr(app, "_widget", None)
        if w is not None:
            try:
                wx = w.winfo_rootx()
                wy = w.winfo_rooty()
                ImageGrab.grab((wx, wy, wx + 360, wy + 480)).save(OUT / "5_widget.png")
                print("saved 5_widget.png")
            except Exception as exc:
                print("widget shot failed:", exc)
        app.after(300, app.destroy)
        app.after(1500, app.quit)

    app.after(5000, s1)
    app.mainloop()


if __name__ == "__main__":
    code = 0
    try:
        run()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        code = 1
    sys.exit(code)
