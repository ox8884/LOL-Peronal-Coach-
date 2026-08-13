"""LiveSession 순수 로직 — 워처 교체·리메이크·아수라장 폼."""

from types import SimpleNamespace

from lol_coach.gui.live_session import (
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
