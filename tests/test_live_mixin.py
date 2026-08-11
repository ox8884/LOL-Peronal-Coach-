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
