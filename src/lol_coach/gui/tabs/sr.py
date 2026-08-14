"""소환사의 협곡 탭 — SrTab 클래스 (gui-service-split 단계4/5).

SrTabMixin 을 합성한 래퍼. TabBase 로 app 속성을 위임한다.
"""

from __future__ import annotations

from lol_coach.gui.sr_tab import SrTabMixin
from lol_coach.gui.tabs._base import TabBase


class SrTab(TabBase, SrTabMixin):
    """SrTabMixin 합성 — CoachApp.sr_tab 필드로 보유."""
