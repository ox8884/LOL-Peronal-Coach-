from __future__ import annotations

from types import SimpleNamespace

from lol_coach.gui import ai_mixin


def _saved_app():
    from lol_coach.config import Settings
    app = ai_mixin.AiMixin()
    app.settings = Settings(riot_api_key="", llm_base_url="https://saved.example/v1", llm_api_key="saved-key", llm_model="saved-model")
    app.llm_base_url_var = SimpleNamespace(get=lambda: "https://draft.example/v2")
    app.llm_key_var = SimpleNamespace(get=lambda: "draft-key")
    app.llm_model_var = SimpleNamespace(get=lambda: "draft-model")
    app._ai_gen = 0
    return app


def test_custom_analysis_uses_saved_snapshot_not_draft_fields(monkeypatch):
    app = _saved_app()
    captured = []
    monkeypatch.setattr("lol_coach.llm.coach_lane", lambda *a, **kw: captured.append(kw) or "ok")
    app._ai_coach_lane(SimpleNamespace(counters=[], patch="16.1"), "아리", "mid", "stale-key")
    assert captured[0]["base_url"] == "https://saved.example/v1"
    assert captured[0]["api_key"] == "saved-key"
    assert captured[0]["model"] == "saved-model"


def test_custom_worker_freezes_settings_before_thread_start(monkeypatch):
    from dataclasses import replace
    app = _saved_app()
    work = []
    captured = []
    queued = []
    monkeypatch.setattr(ai_mixin.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: work.append(kw["target"])))
    monkeypatch.setattr("lol_coach.llm.coach_lane", lambda *a, **kw: captured.append(kw) or "ok")
    app._append_ai_card = lambda frame: SimpleNamespace()
    app.after = lambda ms, cb: queued.append(cb)
    app._maybe_ai(None, lambda on_delta=None: app._ai_coach_lane(SimpleNamespace(counters=[], patch="16.1"), "아리", "mid", "saved-key", on_delta))
    app.settings = replace(app.settings, llm_base_url="https://new.example/v1", llm_api_key="new-key", llm_model="new-model")
    work[0]()
    assert captured[0]["api_key"] == "saved-key"
    assert captured[0]["base_url"] == "https://saved.example/v1"


def test_custom_stale_generation_cannot_mutate_card_or_widget():
    app = _saved_app()
    touched = []
    card = SimpleNamespace(_ai_gen=1, winfo_exists=lambda: touched.append(True) or True)
    app._ai_gen = 2
    app._apply_ai_card(card, "stale text", gen=1)
    app._stream_ai_partial(card, 1, "stale partial")
    assert touched == []


def _var(value):
    box = [value]
    return SimpleNamespace(get=lambda: box[0], set=lambda value: box.__setitem__(0, value))


def test_custom_save_updates_snapshot_and_invalidates_generation(monkeypatch):
    from lol_coach.config import Settings
    app = _saved_app()
    app.llm_base_url_var = _var("https://draft.example/v2/")
    saved = Settings(riot_api_key="", llm_base_url="https://draft.example/v2", llm_api_key="draft-key", llm_model="draft-model")
    calls = []
    monkeypatch.setattr(ai_mixin, "save_llm_settings", lambda *args: calls.append(args))
    monkeypatch.setattr(ai_mixin, "load_settings", lambda: saved)
    app.status = SimpleNamespace(configure=lambda **kw: None)
    assert app._save_llm_key() is True
    assert calls == [("https://draft.example/v2/", "draft-key", "draft-model")]
    assert app.settings is saved
    assert app._ai_gen == 1
    assert app.llm_base_url_var.get() == "https://draft.example/v2"


def test_custom_save_failure_preserves_snapshot_and_hides_error(monkeypatch):
    app = _saved_app()
    original = app.settings
    notices = []
    app._notify = lambda message, **kw: notices.append(message)
    def fail(*args):
        raise OSError("private-api-key disk error")
    monkeypatch.setattr(ai_mixin, "save_llm_settings", fail)
    assert app._save_llm_key() is False
    assert app.settings is original
    assert app._ai_gen == 0
    assert notices and "private-api-key" not in notices[0]


def test_custom_connection_probe_snapshots_inputs_and_drops_stale_callback(monkeypatch):
    app = _saved_app()
    work, queued, calls, notices = [], [], [], []
    app.llm_base_url_var = _var("https://draft.example/v2")
    app._notify = lambda message, **kw: notices.append(message)
    app.after = lambda ms, cb: queued.append(cb)
    monkeypatch.setattr(ai_mixin.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: work.append(kw["target"])))
    monkeypatch.setattr("lol_coach.llm.probe_gateway", lambda *a, **kw: calls.append((a, kw)) or (True, "connected"))
    app._test_llm_connection()
    app.llm_base_url_var.set("https://new.example/v3")
    work[0]()
    queued[0]()
    assert calls == [(("draft-key", "draft-model"), {"base_url": "https://draft.example/v2", "provider": "custom"})]
    assert notices == []
    assert app.settings.llm_base_url == "https://saved.example/v1"


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
    monkeypatch.setattr(ai_mixin._log, "warning", lambda message, exc: logged.append(message))
    app = SimpleNamespace(
        _ai_gen=0,
        _ai_request_settings=lambda: ("https://api.example/v1", "key", "model"),
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
    captured: list[str] = []

    def fake_coach_aram(
        _champion,
        _allies,
        _enemies,
        augments,
        _patch,
        **_kwargs,
    ) -> str:
        captured.append(augments)
        return "ok"

    monkeypatch.setattr("lol_coach.llm.coach_aram", fake_coach_aram)
    def pick(name: str) -> SimpleNamespace:
        return SimpleNamespace(name_ko=name, tier="S")

    app = SimpleNamespace(
        _aram_live_fill=None,
        _ai_model=lambda: "model",
        _ai_provider=lambda: "custom",
        _ai_request_settings=lambda: ("https://api.example/v1", "key", "model"),
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
        augment_validation=SimpleNamespace(valid=[]),
        patch="16.15",
    )

    result = ai_mixin.AiMixin._ai_coach_aram(app, advice, "key")

    assert result == "ok"
    assert captured
    augments = captured[0]
    assert all(name in augments for name in ("실버3", "골드3", "프리즘3"))
