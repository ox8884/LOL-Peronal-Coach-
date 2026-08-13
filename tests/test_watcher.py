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


def test_game_start_detection_arms_and_refires() -> None:
    """게임 시작 감지 — 시작 1회 콜백, 게임 종료 후 재무장."""
    from lol_coach.gui.watcher import GameStartWatcher

    started: list = []
    states = iter([None, None, _game(1), _game(1), None, None, _game(2)])
    watcher = GameStartWatcher(
        get_active_game=lambda: next(states, None),
        on_game_start=started.append,
        interval_s=0.01,
    )
    assert watcher.poll_once() is False  # 게임 없음 (대기)
    assert watcher.poll_once() is False
    assert watcher.poll_once() is True  # 시작 감지 → 1회
    assert started == [_game(1)]
    assert watcher.poll_once() is False  # 진행 중 — 재발화 없음
    assert watcher.poll_once() is False  # 게임 종료 → 재무장
    assert watcher.poll_once() is False
    assert watcher.poll_once() is True  # 두 번째 게임 시작
    assert started == [_game(1), _game(2)]


def test_game_start_error_does_not_rearm() -> None:
    """폴 중 네트워크 오류는 '게임 없음'이 아님 — 중복 알림 방지."""
    from lol_coach.gui.watcher import GameStartWatcher

    started: list = []
    calls = {"n": 0}

    def get():
        calls["n"] += 1
        if calls["n"] == 1:
            return _game(1)
        if calls["n"] == 2:
            raise OSError("net down")
        return _game(1)

    watcher = GameStartWatcher(
        get_active_game=get,
        on_game_start=started.append,
        interval_s=0.01,
    )
    assert watcher.poll_once() is True  # 시작 감지
    assert watcher.poll_once() is False  # 오류 — 상태 유지
    assert watcher.poll_once() is False  # 같은 게임 — 재발화 없음
    assert started == [_game(1)]


def test_game_gone_callback_fires_once_per_game() -> None:
    """게임 → None 전환 시 종료 콜백 1회, 이후 재무장."""
    from lol_coach.gui.watcher import GameStartWatcher

    gone: list = []
    states = iter([None, _game(1), _game(1), None, None, _game(2), None])
    watcher = GameStartWatcher(
        get_active_game=lambda: next(states, None),
        on_game_start=lambda g: None,
        on_game_gone=lambda: gone.append(1),
        interval_s=0.01,
    )
    assert watcher.poll_once() is False  # 게임 없음 (대기)
    assert watcher.poll_once() is True  # 시작 감지
    assert watcher.poll_once() is False  # 진행 중
    assert watcher.poll_once() is False  # 종료 → 콜백 1회
    assert gone == [1]
    assert watcher.poll_once() is False  # None 계속 — 재발화 없음
    assert gone == [1]
    assert watcher.poll_once() is True  # 두 번째 게임 시작
    assert watcher.poll_once() is False  # 두 번째 종료 → 콜백 2회째
    assert gone == [1, 1]


def test_start_game_start_watcher_restarts_on_profile_change(monkeypatch) -> None:
    """다른 계정 로드 시 게임 시작 watcher 재시작 (옛 puuid 폴링 방지)."""
    from lol_coach.gui import live_mixin as lm

    started: list = []
    stopped: list = []

    class FakeWatcher:
        running = True

        def __init__(self, **_kw) -> None:
            pass

        def start(self) -> None:
            started.append(self)

        def stop(self) -> None:
            stopped.append(self)

    monkeypatch.setattr("lol_coach.gui.watcher.GameStartWatcher", FakeWatcher)
    app = SimpleNamespace(
        riot=SimpleNamespace(),
        profile=SimpleNamespace(puuid="p1"),
        after=lambda ms, fn: None,
        _game_start_watcher=None,
        _game_start_puuid=None,
    )
    lm.LiveMixin._start_game_start_watcher(app)
    assert len(started) == 1
    # 같은 계정 재호출 → 유지
    lm.LiveMixin._start_game_start_watcher(app)
    assert len(started) == 1 and len(stopped) == 0
    # 다른 계정 → 재시작
    app.profile = SimpleNamespace(puuid="p2")
    lm.LiveMixin._start_game_start_watcher(app)
    assert len(stopped) == 1
    assert len(started) == 2


def test_start_game_end_watcher_restarts_on_profile_change(monkeypatch) -> None:
    from lol_coach.gui import live_mixin as lm

    started: list = []
    stopped: list = []

    class FakeWatcher:
        running = True

        def __init__(self, **_kwargs) -> None:
            pass

        def start(self) -> None:
            started.append(self)

        def stop(self) -> None:
            stopped.append(self)

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    app = SimpleNamespace(
        riot=SimpleNamespace(
            get_active_game=lambda _puuid: None,
            get_match_ids=lambda _puuid, count: [],
        ),
        profile=SimpleNamespace(puuid="p1"),
        after=lambda _ms, _fn: None,
        status=SimpleNamespace(configure=lambda **_kwargs: None),
        _game_end_auto_review_on=lambda: True,
        _watcher=None,
        _watcher_puuid=None,
    )

    lm.LiveMixin._start_game_end_watcher(app)
    lm.LiveMixin._start_game_end_watcher(app)
    app.profile = SimpleNamespace(puuid="p2")
    lm.LiveMixin._start_game_end_watcher(app)

    assert len(started) == 2
    assert len(stopped) == 1


def test_start_game_end_watcher_restarts_on_new_game_id(monkeypatch) -> None:
    from lol_coach.gui import live_mixin as lm

    started: list = []
    stopped: list = []
    live = {"id": 111}

    class FakeWatcher:
        running = True

        def __init__(self, **_kwargs) -> None:
            pass

        def start(self) -> None:
            started.append(self)

        def stop(self) -> None:
            stopped.append(self)

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    app = SimpleNamespace(
        riot=SimpleNamespace(
            get_active_game=lambda _puuid: SimpleNamespace(game_id=live["id"]),
            get_match_ids=lambda _puuid, count: [],
        ),
        profile=SimpleNamespace(puuid="p1"),
        after=lambda _ms, _fn: None,
        status=SimpleNamespace(configure=lambda **_kwargs: None),
        _game_end_auto_review_on=lambda: True,
        _watcher=None,
        _watcher_puuid=None,
    )

    lm.LiveMixin._start_game_end_watcher(app)
    lm.LiveMixin._start_game_end_watcher(app)
    assert len(started) == 1 and len(stopped) == 0

    live["id"] = 222
    lm.LiveMixin._start_game_end_watcher(app)
    assert len(stopped) == 1
    assert len(started) == 2


def test_game_start_summary_splits_ally_and_enemy_rosters() -> None:
    from lol_coach.gui import live_mixin as lm

    game = SimpleNamespace(
        my_champion_id=1,
        my_team_id=100,
        participants=[
            {"championId": 1, "teamId": 100},
            {"championId": 2, "teamId": 100},
            {"championId": 3, "teamId": 200},
            {"championId": 4, "teamId": 200},
        ],
    )
    app = SimpleNamespace(
        dd=SimpleNamespace(champion_name=lambda cid: f"챔프{cid}"),
        form=SimpleNamespace(matches=[]),
    )

    lines = lm.LiveMixin._game_start_summary_lines(app, game)

    assert lines == [
        "내 챔피언: 챔프1",
        "아군: 챔프1 · 챔프2",
        "적군: 챔프3 · 챔프4",
    ]


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
