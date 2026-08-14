"""탭 래퍼 공통 베이스 (gui-service-split 단계5).

CoachApp MRO 에서 탭 믹스인을 제거한 뒤, 탭 인스턴스가 app 의 속성을
투명하게 공유하도록 한다. __getattr__ / __setattr__ 로 app 에 위임해서
기존 믹스인 코드의 ``self.<attr>`` 접근이 그대로 동작하도록 보존한다.

- 읽기(__getattr__): 탭에 없는 속성을 app 에서 찾는다 (메서드 포함).
- 쓰기(__setattr__): ``_app`` 만 탭 자체에 두고, 나머지는 app 에 설정한다.
  → 탭 믹스인이 ``self.role_var = ...`` 로 설정한 상태가 app 에 저장되어
    app 의 다른 메서드(self.role_var)가 접근할 수 있다.

상태를 탭 내부로 옮기는 작업은 후속 단계에서 진행한다.
"""

from __future__ import annotations

from typing import Any


class TabBase:
    """탭 래퍼 공통 베이스 — app 속성을 __getattr__/__setattr__ 로 위임."""

    def __init__(self, app: Any) -> None:
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        app = self.__dict__.get("_app")
        if app is None:
            raise AttributeError(name)
        return getattr(app, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_app":
            object.__setattr__(self, name, value)
            return
        app = self.__dict__.get("_app")
        if app is None:
            object.__setattr__(self, name, value)
        else:
            setattr(app, name, value)
