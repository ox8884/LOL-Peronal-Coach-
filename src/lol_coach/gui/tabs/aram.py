"""ARAM 아수라장 탭 — AramTab 클래스 (gui-service-split 단계4).

AramTabMixin 을 합성한 래퍼. app(CoachApp) 참조를 받아 __getattr__ 로 위임하므로
기존 믹스인 메서드를 그대로 재사용한다.

이후 단계에서 점진적으로 self.<app 속성> 접근을 AramTab 내부 상태로 이전한다.
"""

from __future__ import annotations

from typing import Any

from lol_coach.gui.aram_tab import AramTabMixin


class AramTab(AramTabMixin):
    """AramTabMixin 합성 — app 참조를 위임받는 래퍼.

    CoachApp 은 self.aram_tab = AramTab(self) 로 보유한다.
    기존 믹스인 메서드는 self.<app 속성> 으로 접근하므로 __getattr__ 로 위임.
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        app = self.__dict__.get("_app")
        if app is None:
            raise AttributeError(name)
        return getattr(app, name)
