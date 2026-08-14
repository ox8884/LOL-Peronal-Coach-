"""게임 종료 워처 상태 전이 테스트 (네트워크 없음)."""

from types import SimpleNamespace

from lol_coach.gui.live_session import LiveSession
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
    sess = LiveSession(after_cb=lambda ms, fn: None)
    sess.start_game_start_watcher(
        client=SimpleNamespace(),
        profile=SimpleNamespace(puuid="p1"),
        get_active_game=lambda: None,
        on_game_start=lambda game: None,
        on_game_gone=lambda: None,
        watcher_factory=FakeWatcher,
    )
    assert len(started) == 1
    # 같은 계정 재호출 → 유지
    sess.start_game_start_watcher(
        client=SimpleNamespace(),
        profile=SimpleNamespace(puuid="p1"),
        get_active_game=lambda: None,
        on_game_start=lambda game: None,
        on_game_gone=lambda: None,
        watcher_factory=FakeWatcher,
    )
    assert len(started) == 1 and len(stopped) == 0
    # 다른 계정 → 재시작
    sess.start_game_start_watcher(
        client=SimpleNamespace(),
        profile=SimpleNamespace(puuid="p2"),
        get_active_game=lambda: None,
        on_game_start=lambda game: None,
        on_game_gone=lambda: None,
        watcher_factory=FakeWatcher,
    )
    assert len(stopped) == 1
    assert len(started) == 2


def test_start_game_end_watcher_restarts_on_profile_change(monkeypatch) -> None:

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
    client = SimpleNamespace(
        get_active_game=lambda _puuid: None,
        get_match_ids=lambda _puuid, count: [],
    )
    sess = LiveSession(after_cb=lambda _ms, _fn: None)

    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p2"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )

    assert len(started) == 2
    assert len(stopped) == 1


def test_start_game_end_watcher_restarts_on_new_game_id(monkeypatch) -> None:

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
    client = SimpleNamespace(
        get_active_game=lambda _puuid: SimpleNamespace(game_id=live["id"]),
        get_match_ids=lambda _puuid, count: [],
    )
    sess = LiveSession(after_cb=lambda _ms, _fn: None)

    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
    assert len(started) == 1 and len(stopped) == 0

    live["id"] = 222
    sess.start_game_end_watcher(
        client=client,
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
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


def test_mayhem_offer_watcher_emits_new_names_once() -> None:
    from lol_coach.gui.watcher import MayhemOfferWatcher

    payloads = iter(
        [
            None,
            {"foo": 1},
            {"offeredAugments": [{"name": "Jeweled Gauntlet"}, {"name": "Fey Magic"}]},
            {"offeredAugments": [{"name": "Jeweled Gauntlet"}, {"name": "Fey Magic"}]},
        ]
    )
    seen: list[list[str]] = []
    watcher = MayhemOfferWatcher(
        get_payload=lambda: next(payloads, None),
        on_names=seen.append,
        interval_s=0.01,
    )
    assert watcher.poll_once() is False
    assert watcher.poll_once() is False
    assert watcher.poll_once() is True
    assert watcher.poll_once() is False
    assert seen == [["Jeweled Gauntlet", "Fey Magic"]]


def test_always_on_champ_select_fires_only_for_aram_pick() -> None:
    from lol_coach.gui.watcher import AlwaysOnChampSelect
    from lol_coach.lcu import parse_champ_select

    seen: list = []
    aram = parse_champ_select(
        {
            "localPlayerCellId": 1,
            "timer": {"phase": "FINALIZATION"},
            "myTeam": [{"cellId": 1, "championId": 103, "augments": []}],
            "theirTeam": [],
        }
    )
    sr = parse_champ_select(
        {
            "localPlayerCellId": 0,
            "timer": {"phase": "FINALIZATION"},
            "myTeam": [{"cellId": 0, "championId": 103}],
            "theirTeam": [{"cellId": 5, "championId": 157}],
        }
    )
    states = iter([None, sr, aram])

    watcher = AlwaysOnChampSelect(
        get_champ_select=lambda: next(states, None),
        on_update=seen.append,
        should_handle=lambda info: bool(info.is_aram and info.my_champion_id),
        interval_s=0.01,
    )
    assert watcher.poll_once() is False
    assert watcher.poll_once() is False  # 협곡 밴픽은 스킵
    assert watcher.poll_once() is True
    assert seen == [aram]


def test_always_on_champ_select_swallows_lcu_errors() -> None:
    from lol_coach.gui.watcher import AlwaysOnChampSelect

    def boom():
        raise OSError("no client")

    watcher = AlwaysOnChampSelect(
        get_champ_select=boom,
        on_update=lambda _i: None,
        interval_s=0.01,
    )
    assert watcher.poll_once() is False


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


def test_end_watcher_stale_generation_ignored(monkeypatch) -> None:
    """옛 세대 watcher의 on_end는 무시 — 새 게임 정산을 덮어쓰지 않는다 (v1.6.56 회귀 고정)."""
    ended: list = []
    watchers: list = []

    class FakeWatcher:
        running = True

        def __init__(self, **kwargs) -> None:
            watchers.append(self)
            self.kwargs = kwargs

        def start(self) -> None:
            on_game_seen = self.kwargs.get("on_game_seen")
            if on_game_seen is not None:
                on_game_seen(SimpleNamespace(game_id=999))

        def stop(self) -> None:
            pass

    game_ids = iter([111, 222])

    class FakeClient:
        def get_active_game(self, puuid: str):
            return SimpleNamespace(game_id=next(game_ids))

        def get_match_ids(self, puuid: str, count: int) -> list[str]:
            return []

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    sess = LiveSession(after_cb=lambda ms, fn: fn())

    # 첫 watcher (game_id=111, gen=1)
    sess.start_game_end_watcher(
        client=FakeClient(),
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: ended.append(m),
        on_waiting=lambda: None,
    )
    assert sess.watcher_gen == 1
    first_on_end = watchers[0].kwargs["on_game_end"]

    # game_id=222 → 교체 (gen=2)
    sess.start_game_end_watcher(
        client=FakeClient(),
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: ended.append(m),
        on_waiting=lambda: None,
    )
    assert sess.watcher_gen == 2

    # 옛 세대의 on_end 호출 → 무시 (ended에 추가 안 됨)
    first_on_end(SimpleNamespace(match_id="OLD"))
    assert ended == []

    # 현재 세대의 on_end 호출 → 실행
    second_on_end = watchers[1].kwargs["on_game_end"]
    second_on_end(SimpleNamespace(match_id="NEW"))
    assert len(ended) == 1
    assert ended[0].match_id == "NEW"


def test_stop_game_end_watcher_clears_state(monkeypatch) -> None:
    """stop_game_end_watcher 는 watcher 를 멈추고 None 으로 비운다."""
    stopped: list = []

    class FakeWatcher:
        running = False

        def __init__(self, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            stopped.append(1)

    class FakeClient:
        def get_active_game(self, puuid: str):
            return None

        def get_match_ids(self, puuid: str, count: int) -> list[str]:
            return []

    monkeypatch.setattr("lol_coach.gui.watcher.GameEndWatcher", FakeWatcher)
    sess = LiveSession(after_cb=lambda ms, fn: fn())
    sess.start_game_end_watcher(
        client=FakeClient(),
        profile=SimpleNamespace(puuid="p1"),
        on_end=lambda m: None,
        on_waiting=lambda: None,
    )
    assert sess.watcher is not None
    sess.stop_game_end_watcher()
    assert sess.watcher is None
    assert len(stopped) == 1
