"""라이브 세션 — 워처 소유권·리메이크 게이트·모드 판정.

tkinter / CustomTkinter 를 import 하지 않는다.
콜백으로 UI에 결과를 넘긴다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lol_coach.log import get_logger
from lol_coach.modes import (
    ARAM_QUEUES,
    QUEUE_ARAM,
    QUEUE_ARAM_MAYHEM,
    is_aram_queue,
)

_log = get_logger("live")

_MIN_SETTLE_DURATION_S = 300
_FORM_SAMPLE_MIN = 5


def should_auto_brief_select(info: Any) -> bool:
    """아수라장/칼바람 밴픽에서 내 챔프가 잡혔을 때만 자동 브리핑."""
    if info is None:
        return False
    if not bool(getattr(info, "is_aram", False)):
        return False
    try:
        return int(getattr(info, "my_champion_id", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def is_mayhem_queue(queue_id: int) -> bool:
    return int(queue_id or 0) == QUEUE_ARAM_MAYHEM


def live_queue_label(queue_id: int) -> str:
    """게임 시작 토스트용 짧은 모드명. 아수라장과 칼바람을 구분한다."""
    qid = int(queue_id or 0)
    if qid == QUEUE_ARAM_MAYHEM:
        return "아수라장"
    if qid == QUEUE_ARAM or qid in ARAM_QUEUES:
        return "칼바람"
    return "소환사의 협곡"


def is_remake_or_abort(match: Any) -> bool:
    """리메이크·조기항복은 예측/팀운/디스코드를 정산하지 않는다.

    game_duration_s 가 없는 스텁(테스트)은 건너뛰지 않는다.
    """
    if match is None:
        return True
    if bool(getattr(match, "team_early_surrender", False)):
        return True
    duration = getattr(match, "game_duration_s", None)
    if duration is None:
        return False
    try:
        return int(duration) < _MIN_SETTLE_DURATION_S
    except (TypeError, ValueError):
        return False


def should_replace_end_watcher(
    *,
    running: bool,
    same_account: bool,
    current_id: int,
    incoming_id: int,
) -> bool:
    """새 종료 워처를 띄울지. 같은 계정·같은 게임이면 유지."""
    if not running:
        return True
    if not same_account:
        return True
    return bool(incoming_id and incoming_id != current_id)


def peek_live_game_id(client: Any, puuid: str) -> int:
    get_live = getattr(client, "get_active_game", None)
    if not callable(get_live):
        return 0
    try:
        live = get_live(puuid)
    except Exception:
        return 0
    if live is None:
        return 0
    try:
        return int(getattr(live, "game_id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def form_sample_for_queue(form: Any, queue_id: int) -> tuple[float | None, int]:
    """예측에 쓸 승률·표본. 아수라장이면 그 큐 전적을 우선한다."""
    if form is None:
        return None, 0
    matches = list(getattr(form, "matches", None) or [])
    qid = int(queue_id or 0)

    def _from(rows: list[Any]) -> tuple[float | None, int]:
        if len(rows) < _FORM_SAMPLE_MIN:
            return None, 0
        wins = sum(1 for m in rows if getattr(m, "win", False))
        return round(100.0 * wins / len(rows), 1), len(rows)

    if is_mayhem_queue(qid) and matches:
        mayhem = [m for m in matches if int(getattr(m, "queue_id", 0) or 0) == QUEUE_ARAM_MAYHEM]
        wr, n = _from(mayhem)
        if n:
            return wr, n
        aram = [m for m in matches if is_aram_queue(int(getattr(m, "queue_id", 0) or 0))]
        wr, n = _from(aram)
        if n:
            return wr, n

    wr = getattr(form, "winrate", None)
    games = int(getattr(form, "games", 0) or 0)
    if wr is None or games < _FORM_SAMPLE_MIN:
        return None, 0
    return float(wr), games


class EndWatcherController:
    """종료 워처 한 개의 세대·베이스라인. tk 없음."""

    def __init__(self) -> None:
        self.watcher: Any = None
        self.puuid: str | None = None
        self.game_id: int = 0
        self.gen: int = 0

    def next_gen(self) -> int:
        self.gen += 1
        return self.gen

    def make(
        self,
        *,
        client: Any,
        profile: Any,
        incoming_id: int,
        is_current_gen: Callable[[], bool],
        on_end: Callable[[Any], None],
        on_waiting: Callable[[], None],
        on_game_id: Callable[[int], None],
    ) -> Any:
        from lol_coach.gui.watcher import GameEndWatcher

        self.puuid = getattr(profile, "puuid", None)
        self.game_id = int(incoming_id or 0)
        baseline_match_id: str | None = None
        live_game_id: int = int(incoming_id or 0)

        def _raw_game_id(raw: Any) -> int:
            info = raw.get("info") if isinstance(raw, dict) else None
            if not isinstance(info, dict):
                return 0
            try:
                return int(info.get("gameId") or 0)
            except (TypeError, ValueError):
                return 0

        def capture_baseline(game: Any) -> None:
            nonlocal baseline_match_id, live_game_id
            live_game_id = int(getattr(game, "game_id", 0) or 0)
            self.game_id = live_game_id
            on_game_id(live_game_id)
            import time as _time

            for attempt in range(3):
                try:
                    ids = client.get_match_ids(profile.puuid, count=1)
                    baseline_match_id = ids[0] if ids else None
                    return
                except Exception as exc:
                    _log.debug("베이스라인 캡처 실패 %d/3: %s", attempt + 1, exc)
                    if attempt < 2:
                        _time.sleep(15)

        def latest() -> Any:
            import time as _time

            on_waiting()
            for attempt in range(4):
                ids = client.get_match_ids(profile.puuid, count=1)
                if ids:
                    match_id = ids[0]
                    if baseline_match_id is None:
                        if live_game_id:
                            raw = client.get_match(match_id)
                            if _raw_game_id(raw) == live_game_id:
                                return client.summarize_match(raw, profile.puuid)
                        else:
                            raw = client.get_match(match_id)
                            return client.summarize_match(raw, profile.puuid)
                    elif match_id != baseline_match_id:
                        raw = client.get_match(match_id)
                        return client.summarize_match(raw, profile.puuid)
                if attempt < 3:
                    _time.sleep(20)
            return None

        def _on_end(match: Any) -> None:
            if not is_current_gen():
                return
            on_end(match)

        watcher = GameEndWatcher(
            get_active_game=lambda: client.get_active_game(profile.puuid),
            get_latest_match=latest,
            on_game_end=_on_end,
            on_game_seen=capture_baseline,
        )
        self.watcher = watcher
        return watcher


class LiveSession:
    """게임 시작/종료 워처의 소유권을 한 곳에 둔다.

    v1.6.56 회귀의 진원지 — ``_watcher``/``_watcher_gen``/``_watcher_puuid`` 가
    CoachApp self 에 흩어져 탭과 경합하던 것을 이 객체로 모은다.
    tk 를 import 하지 않고, UI 갱신은 ``after_cb`` 콜백으로 마살럳한다.
    """

    def __init__(
        self,
        *,
        after_cb: Callable[[int, Callable[[], None]], None],
    ) -> None:
        self._after = after_cb
        # 게임 종료 워처 소유권
        self.watcher: Any = None
        self.watcher_gen: int = 0
        self.watcher_puuid: str | None = None
        self.watcher_game_id: int = 0
        self._end_ctrl: EndWatcherController | None = None
        # 게임 시작 워처 소유권
        self.game_start_watcher: Any = None
        self.game_start_puuid: str | None = None

    # ── 게임 종료 워처 ─────────────────────────────────────────────

    def start_game_end_watcher(
        self,
        *,
        client: Any,
        profile: Any,
        on_end: Callable[[Any], None],
        on_waiting: Callable[[], None],
    ) -> None:
        """종료 워처를 (필요시 교체 후) 시작. 같은 계정·같은 게임이면 유지."""
        incoming_id = peek_live_game_id(client, profile.puuid)
        running = self.watcher is not None and bool(getattr(self.watcher, "running", False))
        same_account = self.watcher_puuid == profile.puuid
        if not should_replace_end_watcher(
            running=running,
            same_account=same_account,
            current_id=self.watcher_game_id,
            incoming_id=incoming_id,
        ):
            return
        if self.watcher is not None and running:
            self.watcher.stop()
            self.watcher = None
        self.watcher_puuid = profile.puuid
        self.watcher_game_id = incoming_id
        self.watcher_gen += 1
        my_gen = self.watcher_gen
        if self._end_ctrl is None:
            self._end_ctrl = EndWatcherController()
        self._end_ctrl.gen = my_gen

        def _set_game_id(gid: int) -> None:
            self.watcher_game_id = gid

        def _is_current_gen() -> bool:
            return self.watcher_gen == my_gen

        def _on_end_cb(match: Any) -> None:
            def _emit() -> None:
                on_end(match)

            self._after(0, _emit)

        self.watcher = self._end_ctrl.make(
            client=client,
            profile=profile,
            incoming_id=incoming_id,
            is_current_gen=_is_current_gen,
            on_end=_on_end_cb,
            on_waiting=lambda: self._after(0, on_waiting),
            on_game_id=_set_game_id,
        )
        self.watcher.start()

    def stop_game_end_watcher(self) -> None:
        if self.watcher is not None:
            try:
                self.watcher.stop()
            except Exception:
                pass
            self.watcher = None

    # ── 게임 시작 워처 ─────────────────────────────────────────────

    def start_game_start_watcher(
        self,
        *,
        client: Any,
        profile: Any,
        get_active_game: Callable[[], Any],
        on_game_start: Callable[[Any], None],
        on_game_gone: Callable[[], None],
        watcher_factory: Callable[..., Any],
    ) -> None:
        """시작 워처 시작. 같은 계정이면 유지, 바뀌면 옛 puuid 폴당 중단 후 재시작."""
        if self.game_start_watcher is not None and getattr(
            self.game_start_watcher, "running", False
        ):
            if self.game_start_puuid == profile.puuid:
                return
            try:
                self.game_start_watcher.stop()
            except Exception:
                pass
            self.game_start_watcher = None
        self.game_start_puuid = profile.puuid

        def _on_start(game: Any) -> None:
            def _emit() -> None:
                on_game_start(game)

            self._after(0, _emit)

        def _on_gone() -> None:
            self._after(0, on_game_gone)

        self.game_start_watcher = watcher_factory(
            get_active_game=get_active_game,
            on_game_start=_on_start,
            on_game_gone=_on_gone,
        )
        self.game_start_watcher.start()

    def stop_game_start_watcher(self) -> None:
        if self.game_start_watcher is not None:
            try:
                self.game_start_watcher.stop()
            except Exception:
                pass
            self.game_start_watcher = None
