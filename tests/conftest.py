"""GUI 테스트 공용 헬퍼.

Windows에서 Tcl 초기화가 간헐적으로 실패("tk wasn't installed properly")
하는 일시 오류가 있어, 루트 생성을 짧은 백오프로 재시도한다.
"""

from __future__ import annotations

import time
import tkinter as tk

import pytest

from lol_coach import llm as _llm

_TK_RETRIES = 5
_TK_RETRY_SLEEP_S = 0.4


def make_root() -> tk.Tk:
    """일시적 Tcl 초기화 오류를 백오프로 재시도하는 withdrawn 루트."""
    for attempt in range(_TK_RETRIES):
        try:
            root = tk.Tk()
            root.withdraw()
            return root
        except tk.TclError:
            if attempt == _TK_RETRIES - 1:
                raise
            time.sleep(_TK_RETRY_SLEEP_S * (attempt + 1))
    raise AssertionError("unreachable")

@pytest.fixture(autouse=True)
def _reset_llm_module_session():
    """모듈 수준 LLM 세션 캐시를 테스트 간에 초기화.

    llm.chat() 이 세션을 재사용하면서, secure_session 을 monkeypatch 하는
    테스트가 캐시된 실세션에 가로막히는 것을 맞는다.
    """
    _llm._LLM_SESSION = None
    yield
    _llm._LLM_SESSION = None
