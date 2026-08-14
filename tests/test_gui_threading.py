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
        aram_aug_var = tk.StringVar(value="Jeweled Gauntlet")
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
    assert app.aram_aug_var.get() == "Jeweled Gauntlet"
    assert "run_aram" in calls
    root.destroy()


def test_parse_offered_augments_validates_catalog() -> None:
    """수동 제시 증강 입력이 카탈로그 기준으로 정규화·중복·unknown 을 반환한다."""
    root = make_root()
    root.withdraw()

    app = SimpleNamespace(
        _aug_catalog=app_module.AugmentCatalog(),
        mayhem=app_module.MayhemCoach(),
        aram_aug_status=SimpleNamespace(configure=lambda **kw: None),
    )
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    names, validation, err = app.aram_tab._parse_offered_augments(
        "Jeweled Gauntlet, 보석 건틀릿, UnknownAug"
    )

    assert err == ""
    assert validation is not None
    assert len(validation.valid) == 1
    assert validation.valid[0].name_en == "Jeweled Gauntlet"
    assert validation.duplicates == ["보석 건틀릿"]
    assert validation.unknowns == ["UnknownAug"]
    assert names == ["Jeweled Gauntlet", "보석 건틀릿", "UnknownAug"]
    root.destroy()


def test_render_aram_shows_only_offered_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """렌더링은 제시된 증강만 보여주고 source/patch/update 메타데이터를 포함한다."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # 이미지 생성을 막아 Tk 이미지 네임스페이스(pyimage1) 충돌 방지 —
    # 이 테스트는 텍스트 렌더링 검증이므로 아이콘은 None 으로 충분하다.
    item_icon_ids: list[int] = []
    monkeypatch.setattr(aram_tab_module, "champion_ctk", lambda *a, **k: None)
    monkeypatch.setattr(
        aram_tab_module,
        "item_ctk",
        lambda item_id, _size: item_icon_ids.append(item_id),
    )
    monkeypatch.setattr(aram_tab_module, "item_name_ctk", lambda *a, **k: None)
    import lol_coach.static.augment_icons as _aug_icons

    monkeypatch.setattr(_aug_icons, "augment_ctk", lambda *a, **k: None)

    class TestApp(ctk.CTk):
        def __init__(self):
            super().__init__()
            self._busy = False
            self._icon_refs: list = []
            self.aram_out = ctk.CTkScrollableFrame(self)
            self.aram_status = ctk.CTkLabel(self, text="")
            self.status = ctk.CTkLabel(self, text="")
            self.mayhem = app_module.MayhemCoach()
            self._aug_catalog = app_module.AugmentCatalog()
            self.aram_champ_var = tk.StringVar(value="아리")
            self.aram_aug_var = tk.StringVar(
                value="Jeweled Gauntlet, Back to Basics, Blade Waltz, Glass Cannon"
            )

        def _clear(self, frame):
            for w in frame.winfo_children():
                w.destroy()

        def _row_frame(self, parent, row, padx=10, pady=2):
            frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray22"), corner_radius=8)
            frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
            return frame

        def _lbl(self, parent, text, row, *, font=app_module.FB, color=None, wrap=960, pady=2, padx=10):
            kw = {"text": text, "font": font, "anchor": "w", "justify": "left", "wraplength": wrap}
            if color:
                kw["text_color"] = color
            ctk.CTkLabel(parent, **kw).grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
            return row + 1

        def _sec(self, parent, title, row):
            ctk.CTkLabel(parent, text=f"▸ {title}", font=aram_tab_module.FS, anchor="w").grid(
                row=row, column=0, sticky="w", padx=10, pady=(14, 4)
            )
            return row + 1

        def _keep_icon(self, img):
            if img is not None:
                self._icon_refs.append(img)
            return img

        def _push_summary(self, title, lines):
            pass

        def _ai_key(self) -> str:
            return ""

        def _maybe_ai(self, frame, builder):
            pass

        _augment_missing_card = aram_tab_module.AramTabMixin._augment_missing_card

        def _schedule_aram_icon_fill(self, adv):
            return None

        _render_offered_pick_row = aram_tab_module.AramTabMixin._render_offered_pick_row
        _render_fixed_augment_board = aram_tab_module.AramTabMixin._render_fixed_augment_board
        _render_aram_build_grid = aram_tab_module.AramTabMixin._render_aram_build_grid

    try:
        app = TestApp()
    except tk.TclError as exc:
        pytest.skip(f"Tk 초기화 실패: {exc}")
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    offered = ["Jeweled Gauntlet", "Back to Basics", "Blade Waltz", "Glass Cannon"]
    adv = app.mayhem.advise("아리", offered_augments=offered)

    app.aram_tab._render_aram(adv)

    def _collect_texts(widget):
        out: list[str] = []
        for w in widget.winfo_children():
            if isinstance(w, ctk.CTkLabel):
                try:
                    out.append(str(w.cget("text")))
                except Exception:
                    pass
            else:
                out.extend(_collect_texts(w))
        return out

    texts = " ".join(_collect_texts(app.aram_out))
    assert all(name in texts for name in ("보석 건틀릿", "기본으로", "검무", "유리 대포"))
    assert all(label in texts for label in ("실버 TOP 3", "골드 TOP 3", "프리즘 TOP 3"))
    assert all(item in texts for item in adv.core_slots[:6])
    assert item_icon_ids == adv.core_item_ids
    assert "6슬롯 완성 빌드" in texts
    assert adv.patch in texts or not adv.patch
    if adv.source:
        assert adv.source.primary in texts
        assert adv.source.updated_at in texts
    assert len(app.aram_out.winfo_children()) > 0

    app.destroy()


def test_run_aram_blocks_invalid_offered_augments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown/duplicate offered augments must block analysis and show suggestions."""
    root = make_root()
    root.withdraw()

    notices: list[str] = []
    worker_targets: list[Callable[[], None]] = []

    class FakeThread:
        def __init__(self, *, target: Callable[[], None], daemon: bool) -> None:
            worker_targets.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)

    app = SimpleNamespace(
        _busy=False,
        _is_busy=lambda key: False,
        _aram_ac=SimpleNamespace(hide=lambda: None),
        _resolve=lambda raw: ("Ahri", "아리"),
        _busy_set=lambda *_args, **_kwargs: None,
        _notify=lambda msg, **kw: notices.append(msg),
        aram_aug_var=tk.StringVar(
            value="Jeweled Gauntlet, Jeweled Gauntlet, NotAnAug"
        ),
        aram_champ_var=tk.StringVar(value="아리"),
        aram_aug_status=SimpleNamespace(configure=lambda **kw: None),
        aram_btn=object(),
        aram_status=SimpleNamespace(configure=lambda **kw: None),
    )
    from lol_coach.gui.tabs.aram import AramTab

    app.aram_tab = AramTab(app)
    object.__setattr__(
        app.aram_tab,
        "_parse_offered_augments",
        lambda raw: (
            ["Jeweled Gauntlet", "Jeweled Gauntlet", "NotAnAug"],
            SimpleNamespace(
                valid=[], unknowns=["NotAnAug"], duplicates=["Jeweled Gauntlet"]
            ),
            "",
        ),
    )
    object.__setattr__(
        app.aram_tab, "_suggest_augments", lambda names, **kw: ["Jeweled Gauntlet"]
    )

    app.aram_tab._run_aram()

    assert len(worker_targets) == 0
    assert len(notices) == 1
    msg = notices[0]
    assert "NotAnAug" in msg
    assert "Jeweled Gauntlet" in msg
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
        aram_aug_var=tk.StringVar(value=""),
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
        aram_aug_var=tk.StringVar(value="Jeweled Gauntlet"),
        aram_champ_var=tk.StringVar(value="아리"),
        aram_aug_status=SimpleNamespace(configure=lambda **kw: None),
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

