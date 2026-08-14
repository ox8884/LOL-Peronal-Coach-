import tkinter as tk
from collections.abc import Callable
from types import SimpleNamespace

import pytest
from conftest import make_root

from lol_coach.gui import app as app_module
from lol_coach.gui import aram_tab as aram_tab_module


class FakeRiotClient:
    def __init__(self) -> None:
        self.resolve_called = False

    def resolve_player(self, game_name: str, tag_line: str) -> SimpleNamespace:
        self.resolve_called = True
        return SimpleNamespace(puuid="player-puuid", riot_id=f"{game_name}#{tag_line}")

    def get_active_game(self, puuid: str) -> None:
        return None


@pytest.mark.parametrize(
    "handler_name",
    ["_live_fill_sr", "_live_fill_aram"],
)
def test_live_lookup_defers_player_resolution_to_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
) -> None:
    client = FakeRiotClient()
    worker_targets: list[Callable[[], None]] = []

    class FakeThread:
        def __init__(self, *, target: Callable[[], None], daemon: bool) -> None:
            worker_targets.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    status = SimpleNamespace(configure=lambda **_kwargs: None)
    app = SimpleNamespace(
        _busy=False,
        _is_busy=lambda key: False,
        _ensure_riot_for_live=lambda: (
            client,
            client.resolve_player("Player", "NA1"),
        ),
        _prepare_riot_for_live=lambda: (client, "Player", "NA1"),
        _busy_set=lambda *_args, **_kwargs: None,
        after=lambda *_args: None,
        dd=SimpleNamespace(ensure_loaded=lambda: None),
        sr_live_btn=object(),
        aram_live_btn=object(),
        sr_status=status,
        aram_status=status,
    )

    from lol_coach.gui.tabs.aram import AramTab
    from lol_coach.gui.tabs.sr import SrTab

    app.sr_tab = SrTab(app)
    app.aram_tab = AramTab(app)
    tab = app.sr_tab if handler_name == "_live_fill_sr" else app.aram_tab
    getattr(tab, handler_name)()

    assert client.resolve_called is False
    assert len(worker_targets) == 1

    worker_targets[0]()

    assert client.resolve_called is True

def test_live_fill_aram_only_changes_champion() -> None:
    """라이브 클라이언트 자동입력은 챔피언만 변경하고 제시 증강은 건드리지 않는다."""
    root = make_root()
    root.withdraw()

    calls: list[str] = []

    class DummyAc:
        def hide(self):
            pass

    class StubApp:
        _busy = False
        _is_busy = staticmethod(lambda key: False)
        _aram_ac = DummyAc()
        aram_champ_var = tk.StringVar(value="")
        aram_status = SimpleNamespace(configure=lambda **kw: calls.append(("status", kw)))
        aram_live_btn = object()

        def _busy_set(self, *_args, **_kwargs):
            calls.append("busy_set")

        def _start_game_end_watcher(self):
            calls.append("watcher")

        def _run_aram(self):
            calls.append("run_aram")

    fill = SimpleNamespace(
        is_sr=False,
        is_aram=True,
        my_champ_ko="아리",
    )

    app = StubApp()
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    object.__setattr__(
        app.aram_tab, "_run_aram", lambda: calls.append("run_aram")
    )
    app.aram_tab._apply_live_aram(fill)

    assert app.aram_champ_var.get() == "아리"
    assert "run_aram" in calls
    root.destroy()



def test_run_aram_allows_empty_offered_augments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 입력도 챔피언 기준 추천을 위한 분석 워커를 시작한다."""
    root = make_root()
    root.withdraw()

    worker_targets: list[Callable[[], None]] = []

    class FakeThread:
        def __init__(self, *, target: Callable[[], None], daemon: bool) -> None:
            worker_targets.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app = SimpleNamespace(
        _busy=False,
        _aram_ac=SimpleNamespace(hide=lambda: None),
        _is_busy=lambda key: False,
        _resolve=lambda raw: ("Ahri", "아리"),
        _busy_set=lambda *_args, **_kwargs: None,
        aram_champ_var=tk.StringVar(value="아리"),
        aram_btn=object(),
        aram_status=SimpleNamespace(configure=lambda **kw: None),
    )
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    object.__setattr__(
        app.aram_tab, "_parse_offered_augments", lambda raw: ([], None, "")
    )

    app.aram_tab._run_aram()

    assert len(worker_targets) == 1
    root.destroy()



def test_run_aram_spawns_worker_for_valid_offered_augments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid offered augments must proceed to the worker thread."""
    root = make_root()
    root.withdraw()

    warnings: list[tuple[str, str]] = []
    worker_targets: list[Callable[[], None]] = []

    class FakeThread:
        def __init__(self, *, target: Callable[[], None], daemon: bool) -> None:
            worker_targets.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(
        aram_tab_module.messagebox,
        "showwarning",
        lambda title, msg: warnings.append((title, msg)),
    )

    app = SimpleNamespace(
        _busy=False,
        _is_busy=lambda key: False,
        _aram_ac=SimpleNamespace(hide=lambda: None),
        _resolve=lambda raw: ("Ahri", "아리"),
        _busy_set=lambda *_args, **_kwargs: None,
        aram_champ_var=tk.StringVar(value="아리"),
        aram_btn=object(),
        aram_status=SimpleNamespace(configure=lambda **kw: None),
    )
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    object.__setattr__(
        app.aram_tab,
        "_parse_offered_augments",
        lambda raw: (
            ["Jeweled Gauntlet"],
            SimpleNamespace(
                valid=[SimpleNamespace(name_en="Jeweled Gauntlet")],
                unknowns=[],
                duplicates=[],
            ),
            "",
        ),
    )

    app.aram_tab._run_aram()

    assert len(worker_targets) == 1
    assert len(warnings) == 0
    root.destroy()

