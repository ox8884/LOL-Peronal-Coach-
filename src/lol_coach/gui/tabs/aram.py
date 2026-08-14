"""ARAM 아수라장 탭 — AramTab 클래스 (gui-service-split 단계4/5).

AramTabMixin 을 합성한 래퍼. TabBase 로 app 속성을 위임한다.
"""

from __future__ import annotations

from lol_coach.gui.aram_tab import AramTabMixin
from lol_coach.gui.tabs._base import TabBase


class AramTab(TabBase, AramTabMixin):
    """AramTabMixin 합성 — CoachApp.aram_tab 필드로 보유."""
