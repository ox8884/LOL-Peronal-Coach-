import time
from types import SimpleNamespace

from lol_coach.gui import live_mixin


def test_delayed_match_publication_ignores_previous_match(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fetched: list[str] = []
    sleeps: list[float] = []
    status_updates: list[str] = []
    match_ids = iter([["OLD"], ["OLD"], ["NEW"]])

    class FakeWatcher:
        running = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self) -> None:
            on_game_seen = captured.get("on_game_seen")
            if on_game_seen is not None:
                on_game_seen(SimpleNamespace(game_id=123))

    class FakeClient:
        def get_active_game(self, puuid: str):
            return None

        def get_match_ids(self, puuid: str, count: int) -> list[str]:
            return next(match_ids)

        def get_match(self, match_id: str):
            fetched.append(match_id)
            return SimpleNamespace(match_id=match_id)

        def summarize_match(self, raw, puuid: str):
            return raw

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    app = SimpleNamespace(
        riot=FakeClient(),
        profile=SimpleNamespace(puuid="PUUID"),
        status=SimpleNamespace(
            configure=lambda **kwargs: status_updates.append(kwargs["text"])
        ),
        _game_end_auto_review_on=lambda: True,
        after=lambda ms, callback: callback(),
    )

    live_mixin.LiveMixin._start_game_end_watcher(app)
    latest = captured["get_latest_match"]

    match = latest()

    assert match.match_id == "NEW"
    assert fetched == ["NEW"]
    assert sleeps == [20]
    assert any(status.startswith("⏳") for status in status_updates)


def test_baseline_capture_failure_retries(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sleeps: list[float] = []
    fetched: list[str] = []
    baseline_calls = {"n": 0}
    match_ids = iter([["OLD"], ["OLD"], ["NEW"]])

    class FakeWatcher:
        running = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self) -> None:
            on_game_seen = captured.get("on_game_seen")
            if on_game_seen is not None:
                on_game_seen(SimpleNamespace(game_id=123))

    class FakeClient:
        def get_active_game(self, puuid: str):
            return None

        def get_match_ids(self, puuid: str, count: int) -> list[str]:
            baseline_calls["n"] += 1
            if baseline_calls["n"] == 1:
                raise OSError("net down")
            return next(match_ids)

        def get_match(self, match_id: str):
            fetched.append(match_id)
            return {"info": {"gameId": 123}, "match_id": match_id}

        def summarize_match(self, raw, puuid: str):
            return SimpleNamespace(match_id=raw["match_id"])

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    app = SimpleNamespace(
        riot=FakeClient(),
        profile=SimpleNamespace(puuid="PUUID"),
        status=SimpleNamespace(configure=lambda **kwargs: None),
        _game_end_auto_review_on=lambda: True,
        after=lambda ms, callback: callback(),
    )

    live_mixin.LiveMixin._start_game_end_watcher(app)
    latest = captured["get_latest_match"]

    match = latest()

    assert match.match_id == "NEW"
    assert fetched == ["NEW"]
    assert sleeps == [15, 20]


def test_baseline_capture_total_failure_verifies_game_id(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sleeps: list[float] = []
    fetched: list[str] = []
    fail = {"on": True}
    match_ids = iter([["OLD"], ["OLD"], ["NEW"]])

    class FakeWatcher:
        running = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self) -> None:
            on_game_seen = captured.get("on_game_seen")
            if on_game_seen is not None:
                on_game_seen(SimpleNamespace(game_id=777))

    class FakeClient:
        def get_active_game(self, puuid: str):
            return None

        def get_match_ids(self, puuid: str, count: int) -> list[str]:
            if fail["on"]:
                raise OSError("net down")
            return next(match_ids)

        def get_match(self, match_id: str):
            fetched.append(match_id)
            return {"info": {"gameId": 777 if match_id == "NEW" else 123}}

        def summarize_match(self, raw, puuid: str):
            return SimpleNamespace(match_id=raw["info"]["gameId"])

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    app = SimpleNamespace(
        riot=FakeClient(),
        profile=SimpleNamespace(puuid="PUUID"),
        status=SimpleNamespace(configure=lambda **kwargs: None),
        _game_end_auto_review_on=lambda: True,
        after=lambda ms, callback: callback(),
    )

    live_mixin.LiveMixin._start_game_end_watcher(app)
    fail["on"] = False  # baseline 캡처(3회 실패) 후 API 복구
    latest = captured["get_latest_match"]

    match = latest()

    assert match.match_id == 777
    assert fetched == ["OLD", "OLD", "NEW"]
    assert sleeps == [15, 15, 20, 20]


def test_is_remake_or_abort() -> None:
    assert live_mixin.is_remake_or_abort(None) is True
    assert live_mixin.is_remake_or_abort(SimpleNamespace(team_early_surrender=True)) is True
    assert live_mixin.is_remake_or_abort(SimpleNamespace(game_duration_s=90)) is True
    assert live_mixin.is_remake_or_abort(SimpleNamespace(game_duration_s=900)) is False
    assert live_mixin.is_remake_or_abort(SimpleNamespace(champion_name="Ahri")) is False


def test_on_game_started_auto_briefs_mayhem() -> None:
    briefed: list = []
    predicted: list = []
    app = SimpleNamespace(
        _live_notification_blocked=False,
        _game_start_label=lambda _g: "아수라장 · 내 챔피언 아리",
        _game_start_notify_on=lambda: False,
        status=SimpleNamespace(configure=lambda **_k: None),
        _game_start_summary_lines=lambda _g: [],
        _push_summary=lambda *_a: None,
        _auto_brief_mayhem=lambda g: briefed.append(g),
        _predict_game_start=lambda g: predicted.append(g),
        _scout_game_start=lambda _g: None,
        _start_game_end_watcher=lambda: None,
    )
    game = SimpleNamespace(game_queue_config_id=2400)
    live_mixin.LiveMixin._on_game_started(app, game)
    assert briefed == [game]
    assert predicted == [game]


def test_on_game_started_skips_auto_brief_on_rift() -> None:
    briefed: list = []
    app = SimpleNamespace(
        _live_notification_blocked=False,
        _game_start_label=lambda _g: "협곡",
        _game_start_notify_on=lambda: False,
        status=SimpleNamespace(configure=lambda **_k: None),
        _game_start_summary_lines=lambda _g: [],
        _push_summary=lambda *_a: None,
        _auto_brief_mayhem=lambda g: briefed.append(g),
        _predict_game_start=lambda _g: None,
        _scout_game_start=lambda _g: None,
        _start_game_end_watcher=lambda: None,
    )
    live_mixin.LiveMixin._on_game_started(
        app, SimpleNamespace(game_queue_config_id=420)
    )
    assert briefed == []


def test_game_start_label_says_mayhem(monkeypatch) -> None:
    app = SimpleNamespace(dd=SimpleNamespace(champion_name=lambda _cid: "아리"))
    game = SimpleNamespace(game_queue_config_id=2400, my_champion_id=103)
    assert "아수라장" in live_mixin.LiveMixin._game_start_label(app, game)
    classic = SimpleNamespace(game_queue_config_id=450, my_champion_id=103)
    assert "칼바람" in live_mixin.LiveMixin._game_start_label(app, classic)


def test_on_game_gone_unblocks_notifications_and_flushes() -> None:
    flushed: list = []
    app = SimpleNamespace(
        _live_notification_blocked=True,
        _flush_notification_queue=lambda: flushed.append(1),
    )

    live_mixin.LiveMixin._on_game_gone(app)

    assert app._live_notification_blocked is False
    assert flushed == [1]
