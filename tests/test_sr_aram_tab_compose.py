"""SrTab / AramTab 래퍼 회귀 테스트 (gui-service-split 단계4).

- __getattr__ 이 app 속성 접근을 위임
- dunder / 누락 속성은 AttributeError
"""

from __future__ import annotations

import types

from lol_coach.gui.tabs.aram import AramTab
from lol_coach.gui.tabs.sr import SrTab


def test_srtab_getattr_delegates_app_attributes() -> None:
    sentinel = object()
    app = types.SimpleNamespace(form=sentinel)
    sr = SrTab(app)

    assert sr.form is sentinel  # __getattr__ 위임


def test_aramtab_getattr_delegates_app_attributes() -> None:
    sentinel = object()
    app = types.SimpleNamespace(form=sentinel)
    aram = AramTab(app)

    assert aram.form is sentinel  # __getattr__ 위임


def test_srtab_getattr_raises_for_dunder() -> None:
    sr = SrTab(types.SimpleNamespace())
    try:
        sr.__nonexistent__  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("dunder 접근은 AttributeError 를 일으켜야 함")


def test_aramtab_getattr_raises_for_dunder() -> None:
    aram = AramTab(types.SimpleNamespace())
    try:
        aram.__nonexistent__  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("dunder 접근은 AttributeError 를 일으켜야 함")


def test_srtab_getattr_raises_when_app_missing_attribute() -> None:
    sr = SrTab(types.SimpleNamespace())
    try:
        sr.nonexistent_attribute  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("app 에 없는 속성은 AttributeError 를 일으켜야 함")


def test_aramtab_getattr_raises_when_app_missing_attribute() -> None:
    aram = AramTab(types.SimpleNamespace())
    try:
        aram.nonexistent_attribute  # noqa: B018
    except AttributeError:
        return
    raise AssertionError("app 에 없는 속성은 AttributeError 를 일으켜야 함")
