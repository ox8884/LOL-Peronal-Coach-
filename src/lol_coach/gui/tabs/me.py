"""내 전적 탭 — MeTab 클래스 (gui-service-split 단계3).

MeTabMixin + MeDetailMixin 을 합성한 래퍼. app(CoachApp) 참조를 받아
__getattr__ 로 위임하므로 기존 믹스인 메서드를 그대로 재사용한다.

퍼블릭 API:
- show_match(match) — 종료 복기가 상세를 여는 단일 경로 (LiveMixin → me_tab.show).
  내부적으로 MeDetailMixin._show_match_detail 을 호출한다.

이후 단계에서 점진적으로 self.<app 속성> 접근을 MeTab 내부 상태로 이전한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.gui.me_tab import MeTabMixin

if TYPE_CHECKING:
    from lol_coach.riot.models import MatchSummary


class MeTab(MeTabMixin, MeDetailMixin):
    """MeTabMixin + MeDetailMixin 합성 — app 참조를 위임받는 래퍼.

    CoachApp 은 self.me_tab = MeTab(self) 로 보유한다.
    기존 믹스인 메서드는 self.<app 속성> 으로 접근하므로 __getattr__ 로 위임.
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    def __getattr__(self, name: str) -> Any:
        # __init__ 실행 전 (self._app 미설정) 접근 방지
        if name.startswith("__"):
            raise AttributeError(name)
        app = self.__dict__.get("_app")
        if app is None:
            raise AttributeError(name)
        return getattr(app, name)

    def show_match(self, match: MatchSummary) -> None:
        """종료 복기 → 상세 뷰 단일 진입점.

        LiveMixin._on_game_ended 는 self._show_match_detail(match) 대신
        self.me_tab.show_match(match) 를 호출한다. 탭이 상세 뷰 소유권을 갖는다.
        """
        self._show_match_detail(match)
