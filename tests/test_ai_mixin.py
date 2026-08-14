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


def test_aram_ai_uses_fixed_rarity_top_and_all_six_slots(monkeypatch) -> None:
    captured: list[tuple[str, str]] = []

    def fake_coach_aram(
        _champion,
        _allies,
        _enemies,
        augments,
        build,
        _patch,
        **_kwargs,
    ) -> str:
        captured.append((augments, build))
        return "ok"

    monkeypatch.setattr("lol_coach.llm.coach_aram", fake_coach_aram)
    def pick(name: str) -> SimpleNamespace:
        return SimpleNamespace(name_ko=name, tier="S")

    app = SimpleNamespace(
        _aram_live_fill=None,
        _ai_model=lambda: "model",
        _ai_provider=lambda: "opencode-go",
    )
    advice = SimpleNamespace(
        champ_ko="베이가",
        fixed_top=SimpleNamespace(
            silver=(pick("실버1"), pick("실버2"), pick("실버3")),
            gold=(pick("골드1"), pick("골드2"), pick("골드3")),
            prismatic=(pick("프리즘1"), pick("프리즘2"), pick("프리즘3")),
        ),
        top_augments=[],
        avoid_augments=[],
        core_slots=["A", "B", "C", "D", "E", "F"],
        spells_line="",
        patch="16.15",
    )

    result = ai_mixin.AiMixin._ai_coach_aram(app, advice, "key")

    assert result == "ok"
    assert captured
    augments, build = captured[0]
    assert all(name in augments for name in ("실버3", "골드3", "프리즘3"))
    assert build.endswith("6코어 F")
