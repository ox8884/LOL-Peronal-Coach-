"""내 전적 탭 — MeTab 클래스 (gui-service-split 단계3/5).

MeTabMixin + MeDetailMixin 을 합성한 래퍼. TabBase 로 app 속성을 위임한다.

퍼블릭 API:
- show_match(match) — 종료 복기가 상세를 여는 단일 경로 (LiveMixin → me_tab.show).
  내부적으로 MeDetailMixin._show_match_detail 을 호출한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.gui.me_tab import MeTabMixin
from lol_coach.gui.tabs._base import TabBase

if TYPE_CHECKING:
    from lol_coach.riot.models import MatchSummary


class MeTab(TabBase, MeTabMixin, MeDetailMixin):
    """MeTabMixin + MeDetailMixin 합성 — CoachApp.me_tab 필드로 보유."""

    def show_match(self, match: MatchSummary) -> None:
        """종료 복기 → 상세 뷰 단일 진입점.

        LiveMixin._on_game_ended 는 self.me_tab.show_match(match) 를 호출한다.
        탭이 상세 뷰 소유권을 갖는다.
        """
        self._show_match_detail(match)
