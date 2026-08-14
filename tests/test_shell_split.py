"""셸 축소 회귀 테스트 (gui-service-split 단계5).

CoachApp MRO 에 탭 믹스인이 없는지, 탭 인스턴스가 필드로 존재하는지 검증.
"""

from __future__ import annotations

from lol_coach.gui.app import CoachApp
from lol_coach.gui.aram_tab import AramTabMixin
from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.gui.me_tab import MeTabMixin
from lol_coach.gui.sr_tab import SrTabMixin
from lol_coach.gui.tabs.aram import AramTab
from lol_coach.gui.tabs.me import MeTab
from lol_coach.gui.tabs.sr import SrTab


def test_coach_app_mro_excludes_tab_mixins() -> None:
    """CoachApp MRO 에 탭 믹스인 4개가 없다 (gui-service-split 완료 기준)."""
    mro = CoachApp.__mro__
    assert SrTabMixin not in mro
    assert AramTabMixin not in mro
    assert MeTabMixin not in mro
    assert MeDetailMixin not in mro


def test_coach_app_keeps_service_mixins() -> None:
    """서비스 믹스인(Notify, Update, Ai, Live)은 유지한다."""
    from lol_coach.gui.ai_mixin import AiMixin
    from lol_coach.gui.live_mixin import LiveMixin
    from lol_coach.gui.notify_mixin import NotifyMixin
    from lol_coach.gui.update_mixin import UpdateMixin

    mro = CoachApp.__mro__
    assert NotifyMixin in mro
    assert UpdateMixin in mro
    assert AiMixin in mro
    assert LiveMixin in mro


def test_tab_classes_are_separate_from_coach_app() -> None:
    """탭 클래스가 CoachApp 과 별개 객체다 (필드로 보유)."""
    assert SrTab is not CoachApp
    assert AramTab is not CoachApp
    assert MeTab is not CoachApp
    # 탭은 CoachApp 을 상속하지 않는다
    assert not issubclass(SrTab, CoachApp)
    assert not issubclass(AramTab, CoachApp)
    assert not issubclass(MeTab, CoachApp)


def test_tab_classes_inherit_tab_mixins() -> None:
    """각 탭 클래스가 대응하는 믹스인을 합성 상속한다."""
    assert issubclass(SrTab, SrTabMixin)
    assert issubclass(AramTab, AramTabMixin)
    assert issubclass(MeTab, MeTabMixin)
    assert issubclass(MeTab, MeDetailMixin)
