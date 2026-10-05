"""LiveSession 순수 로직 — 워처 교체·리메이크·아수라장 폼."""

import threading
from queue import Queue
from types import SimpleNamespace

import pytest

from lol_coach.gui.live_session import (
    LiveSession,
    form_sample_for_queue,
    is_mayhem_queue,
    is_remake_or_abort,
    live_queue_label,
    peek_live_game_id,
    should_replace_end_watcher,
)
from lol_coach.modes import QUEUE_ARAM, QUEUE_ARAM_MAYHEM


def test_live_queue_label_splits_mayhem() -> None:
    assert live_queue_label(QUEUE_ARAM_MAYHEM) == "아수라장"
    assert live_queue_label(QUEUE_ARAM) == "칼바람"
    assert live_queue_label(420) == "소환사의 협곡"


def test_should_auto_brief_select() -> None:
    from lol_coach.gui.live_session import should_auto_brief_select

    assert should_auto_brief_select(None) is False
    assert (
        should_auto_brief_select(SimpleNamespace(is_aram=False, my_champion_id=103))
        is False
    )
    assert (
        should_auto_brief_select(SimpleNamespace(is_aram=True, my_champion_id=0)) is False
    )
    assert (
        should_auto_brief_select(SimpleNamespace(is_aram=True, my_champion_id=103)) is True
    )


def test_is_mayhem_queue() -> None:
    assert is_mayhem_queue(2400) is True
    assert is_mayhem_queue(450) is False


def test_is_remake_or_abort() -> None:
    assert is_remake_or_abort(None) is True
    assert is_remake_or_abort(SimpleNamespace(team_early_surrender=True)) is True
    assert is_remake_or_abort(SimpleNamespace(game_duration_s=90)) is True
    assert is_remake_or_abort(SimpleNamespace(game_duration_s=900)) is False
    assert is_remake_or_abort(SimpleNamespace(champion_name="Ahri")) is False


def test_should_replace_end_watcher() -> None:
    assert (
        should_replace_end_watcher(
            running=False, same_account=True, current_id=1, incoming_id=1
        )
        is True
    )
    assert (
        should_replace_end_watcher(
            running=True, same_account=True, current_id=111, incoming_id=111
        )
        is False
    )
    assert (
        should_replace_end_watcher(
            running=True, same_account=True, current_id=111, incoming_id=222
        )
        is True
    )
    assert (
        should_replace_end_watcher(
            running=True, same_account=False, current_id=111, incoming_id=111
        )
        is True
    )
    assert (
        should_replace_end_watcher(
            running=True, same_account=True, current_id=111, incoming_id=0
        )
        is False
    )


def test_peek_live_game_id() -> None:
    assert peek_live_game_id(SimpleNamespace(), "p") == 0
    client = SimpleNamespace(get_active_game=lambda _p: SimpleNamespace(game_id=99))
    assert peek_live_game_id(client, "p") == 99


def test_form_sample_prefers_mayhem_matches() -> None:
    mayhem = [
        SimpleNamespace(queue_id=2400, win=True),
        SimpleNamespace(queue_id=2400, win=True),
        SimpleNamespace(queue_id=2400, win=False),
        SimpleNamespace(queue_id=2400, win=True),
        SimpleNamespace(queue_id=2400, win=True),
    ]
    sr = [SimpleNamespace(queue_id=420, win=False) for _ in range(10)]
    form = SimpleNamespace(matches=mayhem + sr, winrate=30.0, games=15)
    wr, n = form_sample_for_queue(form, 2400)
    assert n == 5
    assert wr == 80.0


def test_form_sample_falls_back_to_all_when_mayhem_thin() -> None:
    form = SimpleNamespace(
        matches=[SimpleNamespace(queue_id=2400, win=True)],
        winrate=55.0,
        games=20,
    )
    wr, n = form_sample_for_queue(form, 2400)
    assert n == 20
    assert wr == 55.0


@pytest.fixture
def end_lookup(monkeypatch):
    workers: list = []
    scheduled: list = []
    watchers: list = []

    class FakeWatcher:
        running = False

        def __init__(self, **kwargs):
            self.callbacks = kwargs
            watchers.append(self)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    monkeypatch.setattr(
        threading,
        "Thread",
        lambda *, target, daemon: SimpleNamespace(start=lambda: workers.append(target)),
    )
    session = LiveSession(after_cb=lambda _ms, fn: scheduled.append(fn))
    return session, workers, scheduled, watchers


def test_end_watcher_repeated_start_never_queries_on_ui_thread() -> None:
    entered = threading.Event()
    release = threading.Event()
    scheduled = Queue()
    query_threads: list[threading.Thread] = []
    main_thread = threading.current_thread()

    def get_active_game(_puuid):
        query_threads.append(threading.current_thread())
        entered.set()
        if threading.current_thread() is not main_thread:
            release.wait(timeout=2)
        return SimpleNamespace(game_id=111)

    session = LiveSession(after_cb=lambda _ms, fn: scheduled.put(fn))
    existing = SimpleNamespace(running=True)
    session.watcher = existing
    session.watcher_puuid = "p1"
    session.watcher_game_id = 111
    client = SimpleNamespace(get_active_game=get_active_game)

    try:
        for _ in range(3):
            session.start_game_end_watcher(
                client=client,
                profile=SimpleNamespace(puuid="p1"),
                on_end=lambda _match: None,
                on_waiting=lambda: None,
            )
        assert entered.wait(timeout=2)
        assert main_thread not in query_threads
        assert len(query_threads) == 1
        assert session.watcher is existing
        release.set()
        scheduled.get(timeout=2)()
        assert session.watcher is existing
    finally:
        release.set()
        for thread in query_threads:
            if thread is not main_thread:
                thread.join(timeout=2)


def test_end_watcher_pending_profile_lookup_cannot_replace_new_profile(end_lookup) -> None:
    session, workers, scheduled, watchers = end_lookup
    queried: list[str] = []

    def get_active_game(puuid):
        queried.append(puuid)
        return SimpleNamespace(game_id=111 if puuid == "p1" else 222)

    client = SimpleNamespace(get_active_game=get_active_game)
    for puuid in ("p1", "p2"):
        session.start_game_end_watcher(
            client=client,
            profile=SimpleNamespace(puuid=puuid),
            on_end=lambda _match: None,
            on_waiting=lambda: None,
        )
    assert queried == []
    assert len(workers) == 2
    workers[1]()
    scheduled.pop(0)()
    current = session.watcher
    workers[0]()
    while scheduled:
        scheduled.pop(0)()
    assert session.watcher is current
    assert len(watchers) == 1
    assert session.watcher_puuid == "p2"
    assert session.watcher_game_id == 222


def test_stop_end_watcher_cancels_pending_lookup(end_lookup) -> None:
    session, workers, scheduled, watchers = end_lookup
    session.start_game_end_watcher(
        client=SimpleNamespace(get_active_game=lambda _p: SimpleNamespace(game_id=111)),
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda _match: None,
        on_waiting=lambda: None,
    )
    assert len(workers) == 1
    workers.pop()()
    session.stop_game_end_watcher()
    while scheduled:
        scheduled.pop(0)()
    assert session.watcher is None
    assert watchers == []


@pytest.mark.parametrize("replace", [False, True])
def test_end_watcher_stale_queued_callbacks_are_ignored(end_lookup, replace) -> None:
    session, workers, scheduled, watchers = end_lookup
    ended: list = []
    waiting: list = []
    client = SimpleNamespace(
        get_active_game=lambda _p: SimpleNamespace(game_id=111),
        get_match_ids=lambda _p, count: ["RECENT"],
        get_match=lambda _id: {"info": {"gameId": 111}},
        summarize_match=lambda _raw, _p: "RECENT",
    )
    session.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=ended.append,
        on_waiting=lambda: waiting.append(True),
    )
    if workers:
        workers.pop()()
    while scheduled:
        scheduled.pop(0)()
    old = watchers[0]
    old.callbacks["on_game_end"]("OLD")
    old.callbacks["get_latest_match"]()
    if replace:
        session.start_game_end_watcher(
            client=client,
            profile=SimpleNamespace(puuid="p2"),
            on_end=ended.append,
            on_waiting=lambda: waiting.append(True),
        )
    else:
        session.stop_game_end_watcher()
    old.callbacks["on_game_seen"](SimpleNamespace(game_id=999))
    while scheduled:
        scheduled.pop(0)()
    assert ended == []
    assert waiting == []
    assert session.watcher_game_id != 999
