"""인게임 종료 감지 워처 — Spectator 폴당 → 종료 시 최근 매치 콜백.

GUI(app.py)에서 인게임 자동입력 성공 후 시작한다.
콜백은 워커 스레드에서 호출되므로 GUI 갱신은 ``after()`` 로 마샬링할 것.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from lol_coach.log import get_logger
from lol_coach.riot.models import MatchSummary

_log = get_logger("watcher")


class GameEndWatcher:
    def __init__(
        self,
        *,
        get_active_game: Callable[[], Any],
        get_latest_match: Callable[[], MatchSummary | None],
        on_game_end: Callable[[MatchSummary | None], None],
        on_game_seen: Callable[[Any], None] | None = None,
        interval_s: float = 45.0,
        fast_interval_s: float = 15.0,
        max_idle_polls: int = 240,
    ) -> None:
        """
        - get_active_game: 현재 게임 (없으면 None) — 예외는 남겨도 됨
        - get_latest_match: 종료 감지 후 가장 최근 매치 1개
        - on_game_end: 종료 시 1회 호출
        - on_game_seen: 인게임을 처음 감지했을 때 1회 호출 (베이스라인 캡처용)
        - max_idle_polls: 인게임이 아닌 상태가 이 횟수만큼 계속되면 자동 종료
        - fast_interval_s: 게임을 한 번 본 뒤(종료 임박) 폴링 간격 — 감지 지연 단축
        """
        self._get_active_game = get_active_game
        self._get_latest_match = get_latest_match
        self._on_game_end = on_game_end
        self._on_game_seen = on_game_seen
        self._interval = interval_s
        self._max_idle = max_idle_polls
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_game_id: int | None = None
        self._ended = False
        self._fast_interval = fast_interval_s
        self._seen_game = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        idle = 0
        while not self._stop.is_set() and not self._ended:
            in_game = True
            try:
                in_game = self.poll_once()
            except Exception as exc:  # 네트워크 흔들림은 무시하고 계속
                _log.debug("워처 폴당 오류(무시): %s", exc)
            idle = 0 if in_game else idle + 1
            if idle >= self._max_idle:
                break
            wait = self._fast_interval if self._seen_game else self._interval
            self._stop.wait(wait)

    def poll_once(self) -> bool:
        """1회 폴당. 반환: 현재 인게임 여부 (테스트에서 직접 호출 가능)."""
        if self._ended:
            return False
        game = self._get_active_game()
        if game is not None:
            game_id = int(getattr(game, "game_id", 0) or 0)
            self._last_game_id = game_id or self._last_game_id
            if not self._seen_game:
                self._seen_game = True
                if self._on_game_seen is not None:
                    self._on_game_seen(game)
            return True
        # 인게임 아님: 직전에 게임이 있었으면 종료로 판정
        if self._last_game_id is not None:
            self._ended = True
            match = None
            try:
                match = self._get_latest_match()
            except Exception as exc:
                _log.debug("종료 후 매치 조회 실패: %s", exc)
            self._on_game_end(match)
        return False


class GameStartWatcher:
    """게임 시작 감지 — 게임 없음 → 게임 있음 전환 시 1회 콜백.

    게임이 끝나 다시 None 이 되면 자동 재무장한다. 콜백은 워커 스레드에서
    호출되므로 GUI 갱신은 ``after()`` 로 마샬링할 것.
    """

    def __init__(
        self,
        *,
        get_active_game: Callable[[], Any],
        on_game_start: Callable[[Any], None],
        on_game_gone: Callable[[], None] | None = None,
        interval_s: float = 60.0,
    ) -> None:
        self._get_active_game = get_active_game
        self._on_game_start = on_game_start
        self._on_game_gone = on_game_gone
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._armed = True

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> bool:
        """1회 폴당. 반환: 이번 폴에서 게임 시작을 새로 감지했는지 (테스트용)."""
        try:
            game = self._get_active_game()
        except Exception:
            # 네트워크 흔들림은 '게임 없음'이 아님 — 상태 유지 (중복 알림 방지)
            return False
        if game is not None:
            if self._armed:
                self._armed = False
                self._on_game_start(game)
                return True
            return False
        if not self._armed:
            # 게임 → None 전환: 재무장하고 종료 콜백 1회
            self._armed = True
            if self._on_game_gone is not None:
                try:
                    self._on_game_gone()
                except Exception as exc:
                    _log.debug("게임 종료 콜백 오류(무시): %s", exc)
        return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # 네트워크 흔들림은 무시하고 계속
                _log.debug("게임 시작 폴당 오류(무시): %s", exc)
            self._stop.wait(self._interval)


class MayhemOfferWatcher:
    """게임 중 Live Client Data에서 제시 증강 이름을 폴링한다."""

    def __init__(
        self,
        *,
        get_payload: Callable[[], Any],
        on_names: Callable[[list[str]], None],
        interval_s: float = 2.0,
    ) -> None:
        self._get_payload = get_payload
        self._on_names = on_names
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: tuple[str, ...] = ()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> bool:
        try:
            payload = self._get_payload()
        except Exception:
            return False
        if not payload:
            return False
        from lol_coach.lcu import extract_augment_names

        names = extract_augment_names(payload)
        if len(names) < 2:
            return False
        sig = tuple(names[:6])
        if sig == self._last:
            return False
        self._last = sig
        try:
            self._on_names(list(names))
        except Exception as exc:
            _log.debug("인게임 증강 콜백 오류(무시): %s", exc)
            return False
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                _log.debug("인게임 증강 폴링 오류(무시): %s", exc)
            self._stop.wait(self._interval)


class AlwaysOnChampSelect:
    """앱이 켜져 있는 동안 LCU 밴픽을 폴링한다.

    클라이언트가 꺼져 있거나 밴픽이 아니면 조용히 넘어간다.
    콜백은 워커 스레드에서 호출되므로 GUI 갱신은 after() 로 마샬링할 것.
    """

    def __init__(
        self,
        *,
        get_champ_select: Callable[[], Any],
        on_update: Callable[[Any], None],
        should_handle: Callable[[Any], bool] | None = None,
        interval_s: float = 3.0,
    ) -> None:
        self._get_champ_select = get_champ_select
        self._on_update = on_update
        self._should_handle = should_handle
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> bool:
        """1회 폴. 반환: 이번 폴에서 on_update 를 호출했는지."""
        try:
            info = self._get_champ_select()
        except Exception:
            return False
        if info is None or not getattr(info, "in_champ_select", False):
            return False
        if self._should_handle is not None and not self._should_handle(info):
            return False
        try:
            self._on_update(info)
        except Exception as exc:
            _log.debug("상시 밴픽 콜백 오류(무시): %s", exc)
            return False
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                _log.debug("상시 밴픽 폴링 오류(무시): %s", exc)
            self._stop.wait(self._interval)


class ChampSelectWatcher:
    """챔피언 셀렉트 폴링 — 밴픽 중 픽이 바뀔 때마다 콜백.

    LCU 밴픽은 여러 단계에 걸쳐 픽이 채워지므로, 한 번 스냅샷 대신
    셀렉트가 끝날 때까지 짧은 간격으로 읽어 최신 상태를 전달한다.
    콜백은 워커 스레드에서 호출되므로 GUI 갱신은 ``after()`` 로 마샬링할 것.
    """

    def __init__(
        self,
        *,
        get_champ_select: Callable[[], Any],
        on_update: Callable[[Any], None],
        on_end: Callable[[], None] | None = None,
        interval_s: float = 3.0,
        max_polls: int = 120,
    ) -> None:
        """
        - get_champ_select: 현재 ChampSelectInfo (없으면 예외 또는 None)
        - on_update: 유효한 셀렉트 상태를 읽을 때마다 호출
        - on_end: 셀렉트가 끝났을 때 1회 호출
        - max_polls: 이 횟수만큼 폴링하면 자동 종료 (안전장치)
        """
        self._get_champ_select = get_champ_select
        self._on_update = on_update
        self._on_end = on_end
        self._interval = interval_s
        self._max_polls = max_polls
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        polls = 0
        while not self._stop.is_set() and polls < self._max_polls:
            polls += 1
            try:
                info = self._get_champ_select()
            except Exception as exc:
                # 404/연결 실패 = 셀렉트 종료 (또는 클라이언트 없음)
                _log.debug("밴픽 폴링 종료: %s", exc)
                self._fire_end()
                break
            if info is None or not getattr(info, "in_champ_select", False):
                self._fire_end()
                break
            try:
                self._on_update(info)
            except Exception as exc:
                _log.debug("밴픽 갱신 콜백 오류(무시): %s", exc)
            self._stop.wait(self._interval)
        if not self._stop.is_set():
            self._fire_end()

    def _fire_end(self) -> None:
        if self._on_end is None:
            return
        try:
            self._on_end()
        except Exception as exc:
            _log.debug("밴픽 종료 콜백 오류(무시): %s", exc)


class LiveClientGameWatcher:
    """Live Client Data API 기반 게임 시작 감지 (API 키 불필요, 로컬).

    게임 없음 → 게임 있음 전환 시 콜백.
    콜백이 mark_handled() 를 호출하기 전까지 _armed 유지 —
    로딩 화면에서 gameData 가 덜 채워졌으면 다음 폴에서 재시도한다.
    게임이 끝나 None 이 되면 재무장한다.
    """

    def __init__(
        self,
        *,
        on_game_start: Callable[[dict[str, Any]], None],
        on_game_gone: Callable[[], None] | None = None,
        interval_s: float = 3.0,
    ) -> None:
        self._on_game_start = on_game_start
        self._on_game_gone = on_game_gone
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._armed = True

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def mark_handled(self) -> None:
        """콜백이 데이터를 성공적으로 처리했음을 알린다 — 다음 게임까지 disarm."""
        self._armed = False

    def poll_once(self) -> bool:
        """1회 폴. 반환: 이번 폴에서 콜백을 호출했는지."""
        from lol_coach.lcu import fetch_live_client_data

        try:
            data = fetch_live_client_data(timeout=1.5)
        except Exception:
            return False
        if data is not None:
            if self._armed:
                try:
                    self._on_game_start(data)
                except Exception as exc:
                    _log.debug("Live Client 게임 시작 콜백 오류(무시): %s", exc)
                # mark_handled() 가 호출될 때까지 _armed 유지 → 재시도
            return False
        if not self._armed:
            self._armed = True
            if self._on_game_gone is not None:
                try:
                    self._on_game_gone()
                except Exception as exc:
                    _log.debug("Live Client 게임 종료 콜백 오류(무시): %s", exc)
        return False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                _log.debug("Live Client 폴링 오류(무시): %s", exc)
            self._stop.wait(self._interval)
