"""MeTab 래퍼 회귀 테스트 (gui-service-split 단계3).

- show_match 가 _show_match_detail 로 위임하는 단일 경로
- __getattr__ 이 app 속성 접근을 위임
- (live_mixin._on_game_ended → me_tab.show_match 경로는 test_gui_behavior.py 의
  test_game_end_* 3개 테스트가 이미 커버)

show_match 는 MeDetailMixin._show_match_detail 을 호출한다. _show_match_detail
본체는 app 의 다양한 속성에 접근하므로, 여기서는 인스턴스 속성으로 스텁을 끼워넣어
"show_match → _show_match_detail" 위임 사실만 검증한다.
"""

from __future__ import annotations

import types

from lol_coach.gui.tabs.me import MeTab


def test_show_match_delegates_to_show_match_detail() -> None:
    shown: list[object] = []
    app = types.SimpleNamespace()
    me = MeTab(app)
    me._show_match_detail = lambda match: shown.append(match)  # type: ignore[method-assign]
    match = types.SimpleNamespace(champion_name="Caitlyn", win=True)

    me.show_match(match)

    assert shown == [match]


def test_metab_getattr_delegates_app_attributes() -> None:
    sentinel = object()
    app = types.SimpleNamespace(form=sentinel)
    me = MeTab(app)

    assert me.form is sentinel  # __getattr__ 위임


def test_metab_getattr_raises_for_dunder() -> None:
    app = types.SimpleNamespace()
    me = MeTab(app)

    try:
        me.__nonexistent__  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("dunder 접근은 AttributeError 를 일으켜야 함")


def test_metab_getattr_raises_when_app_missing_attribute() -> None:
    app = types.SimpleNamespace()
    me = MeTab(app)

    try:
        me.nonexistent_attribute  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("app 에 없는 속성은 AttributeError 를 일으켜야 함")
