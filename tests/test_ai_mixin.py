from __future__ import annotations

from types import SimpleNamespace

from lol_coach.gui import ai_mixin


def test_ai_builder_failure_renders_failure_card(monkeypatch) -> None:
    applied: list[str | None] = []
    logged: list[str] = []
    card = SimpleNamespace()

    class ImmediateThread:
        def __init__(self, *, target, daemon: bool) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(ai_mixin.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(ai_mixin._log, "exception", lambda message, exc: logged.append(message))
    app = SimpleNamespace(
        _ai_gen=0,
        _ai_key=lambda: "key",
        _append_ai_card=lambda _frame: card,
        _apply_ai_card=lambda _card, text, gen=None: applied.append(text),
        after=lambda _ms, callback: callback(),
    )

    ai_mixin.AiMixin._maybe_ai(
        app,
        object(),
        lambda: (_ for _ in ()).throw(RuntimeError("builder failed")),
    )

    assert applied == [None]
    assert logged
