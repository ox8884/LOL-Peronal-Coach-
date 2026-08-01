"""게임 종료 워처 상태 전이 테스트 (네트워크 없음)."""

from types import SimpleNamespace

from lol_coach.gui.watcher import GameEndWatcher


def _game(game_id: int):
    return SimpleNamespace(game_id=game_id)


def test_end_detection_fires_callback_once() -> None:
    states = iter([_game(111), _game(111), None, None])
    ended: list = []

    watcher = GameEndWatcher(
        get_active_game=lambda: next(states, None),
        get_latest_match=lambda: "MATCH",
        on_game_end=ended.append,
        interval_s=0.01,
    )
    assert watcher.poll_once() is True  # 인게임
    assert watcher.poll_once() is True
    assert watcher.poll_once() is False  # 종료 감지
    assert ended == ["MATCH"]
    # 이후에는 재발화하지 않음
    assert watcher.poll_once() is False
    assert ended == ["MATCH"]


def test_no_game_never_fires() -> None:
    ended: list = []
    watcher = GameEndWatcher(
        get_active_game=lambda: None,
        get_latest_match=lambda: "MATCH",
        on_game_end=ended.append,
        interval_s=0.01,
    )
    for _ in range(3):
        assert watcher.poll_once() is False
    assert ended == []


def test_match_lookup_failure_still_notifies() -> None:
    states = iter([_game(5), None])
    ended: list = []

    def boom():
        raise RuntimeError("match api down")

    watcher = GameEndWatcher(
        get_active_game=lambda: next(states, None),
        get_latest_match=boom,
        on_game_end=ended.append,
        interval_s=0.01,
    )
    watcher.poll_once()
    watcher.poll_once()
    assert ended == [None]


def test_stop_halts_loop() -> None:
    watcher = GameEndWatcher(
        get_active_game=lambda: _game(1),
        get_latest_match=lambda: None,
        on_game_end=lambda m: None,
        interval_s=0.01,
    )
    watcher.start()
    assert watcher.running
    watcher.stop()
    watcher._thread.join(timeout=2)
    assert not watcher.running
