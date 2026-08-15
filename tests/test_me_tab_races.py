from collections.abc import Callable
from types import SimpleNamespace

from lol_coach.gui import me_tab
from lol_coach.gui.me_tab import MeTabMixin


class _Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value


class _Widget:
    def configure(self, **_kwargs: str) -> None:
        return None


def test_me_load_callback_is_discarded_when_generation_changes() -> None:
    # Given
    callbacks: list[Callable[[], None]] = []
    applied: list[str] = []
    app = SimpleNamespace(
        _me_load_gen=1,
        after=lambda _delay, callback: callbacks.append(callback),
    )

    # When
    MeTabMixin._schedule_me_load(app, 1, lambda: applied.append("stale"))
    app._me_load_gen = 2
    callbacks[0]()

    # Then
    assert applied == []


def test_prefetched_icons_do_not_render_after_form_changes(monkeypatch) -> None:
    # Given
    callbacks: list[Callable[[], None]] = []
    rendered: list[SimpleNamespace] = []
    form = SimpleNamespace(matches=[])

    class _ImmediateThread:
        def __init__(self, *, target, daemon: bool) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(me_tab.threading, "Thread", _ImmediateThread)
    app = SimpleNamespace(
        _me_form_full=form,
        _last_ranks=[],
        me_matches=SimpleNamespace(winfo_exists=lambda: True),
        after=lambda _delay, callback: callbacks.append(callback),
        _render_me=lambda current_form, _ranks: rendered.append(current_form),
    )

    # When
    MeTabMixin._prefetch_match_icons(app, form)
    app._me_form_full = None
    callbacks[0]()

    # Then
    assert rendered == []


def test_reset_invalidates_load_and_detail_generations() -> None:
    # Given
    app = SimpleNamespace(
        _busy={"me_load"},
        _me_load_gen=3,
        _me_detail_gen=7,
        me_btn=_Widget(),
        riot_id_var=_Value("Player#KR1"),
        platform_var=_Value("kr"),
        api_key_var=_Value("RGAPI-test"),
        profile_var=_Value("profile"),
        settings=SimpleNamespace(riot_api_key="RGAPI-test"),
        rank_lbl=_Widget(),
        me_matches=SimpleNamespace(),
        me_detail=SimpleNamespace(),
        me_champs=SimpleNamespace(),
        status=_Widget(),
        _clear=lambda _frame: None,
        _lbl=lambda *_args, **_kwargs: None,
        riot=SimpleNamespace(),
        profile=SimpleNamespace(),
        form=SimpleNamespace(),
        _me_form_full=SimpleNamespace(),
        _me_search_var=_Value(""),
        _refresh_result_filter_btns=lambda: None,
        _me_search_after=None,
    )

    # When
    MeTabMixin._reset_me(app)

    # Then
    assert app._me_load_gen == 4
    assert app._me_detail_gen == 8
