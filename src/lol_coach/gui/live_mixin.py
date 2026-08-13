"""인게임/종료 감지 공통

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Any

from lol_coach.config import DEFAULT_PLATFORM, load_settings, save_api_key, save_player
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger
from lol_coach.riot.client import RiotClient

_log = get_logger("live")


class LiveMixin(MixinBase):
    def _start_champ_watch(
        self,
        *,
        apply_fn: Any,
        status_label: Any,
        watching_text: str,
    ) -> None:
        """밴픽 폴당 공통 로직 (SR/ARAM 공용).

        탭별로 다른 건 적용 콜백(``_apply_lcu_sr``/``_apply_lcu_aram``)과
        상태 레이블뿐이라 여기서 한 번만 만든다.
        """
        from lol_coach.gui.watcher import ChampSelectWatcher
        from lol_coach.lcu import LCUClient

        self._stop_champ_watch()

        def get() -> Any:
            return LCUClient().champ_select()

        def on_update(info: Any) -> None:
            self.after(0, lambda: apply_fn(info))

        def on_end() -> None:
            self.after(
                0, lambda: status_label.configure(text="밴픽 종료 · 추적 중단")
            )
            self._champ_watcher: Any = None

        self._champ_watcher = ChampSelectWatcher(
            get_champ_select=get,
            on_update=on_update,
            on_end=on_end,
            interval_s=4.0,
        )
        self._champ_watcher.start()
        status_label.configure(text=watching_text)

    def _prepare_riot_for_live(self) -> tuple[RiotClient, str, str] | None:
        settings = load_settings()
        key = (settings.riot_api_key or "").strip()
        if not key and hasattr(self, "api_key_var"):
            # 내 전적 탭에 입력해 둔 키 시도
            key = self.api_key_var.get().strip()
        if not key:
            if messagebox.askyesno(
                "API 키 필요",
                "인게임 자동입력은 Riot API 키가 필요합니다.\n\n"
                "「내 전적」탭에서 키를 저장하거나\n도움말을 열까요?",
            ):
                self._show_api_help()
            return None

        rid = settings.riot_id
        if hasattr(self, "riot_id_var"):
            rid = self.riot_id_var.get().strip() or rid
        if "#" not in rid:
            self._notify(
                "Riot ID(Name#TAG)를 「내 전적」탭에 설정해 주세요.",
                level="warn",
            )
            return None
        name, tag = rid.split("#", 1)

        platform = settings.platform or DEFAULT_PLATFORM
        if hasattr(self, "platform_var"):
            platform = self.platform_var.get().strip() or platform

        save_api_key(key)
        save_player(name.strip(), tag.strip(), platform=platform)
        self.settings = load_settings()

        client = RiotClient(api_key=key, platform=platform)
        return client, name.strip(), tag.strip()


    def _start_game_end_watcher(self) -> None:
        """인게임 자동입력 성공 후 — 종료를 폴당해 자동 복기."""
        riot = getattr(self, "riot", None)
        profile = getattr(self, "profile", None)
        if riot is None or profile is None:
            return
        watcher = getattr(self, "_watcher", None)
        if watcher is not None and watcher.running:
            if getattr(self, "_watcher_puuid", None) == profile.puuid:
                return
            watcher.stop()
            self._watcher = None
        self._watcher_puuid = profile.puuid
        from lol_coach.gui.watcher import GameEndWatcher

        client, profile = riot, profile
        baseline_match_id: str | None = None
        live_game_id: int = 0

        def _raw_game_id(raw: Any) -> int:
            info = raw.get("info") if isinstance(raw, dict) else None
            if not isinstance(info, dict):
                return 0
            try:
                return int(info.get("gameId") or 0)
            except (TypeError, ValueError):
                return 0

        def capture_baseline(game: Any) -> None:
            """게임 첫 감지 시 — 종료 후 새 매치를 가려낼 베이스라인 캡처."""
            nonlocal baseline_match_id, live_game_id
            live_game_id = int(getattr(game, "game_id", 0) or 0)
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
            # 매치 반영까지 지연 있을 수 있어 몇 번 재시도
            import time as _time

            # tkinter after()를 워커 스레드에서 호출 — 기존 워처 콜백 패턴과 동일
            self.after(
                0,
                lambda: self.status.configure(text="⏳ 게임 전적 업데이트 중…"),
            )
            for attempt in range(4):
                ids = client.get_match_ids(profile.puuid, count=1)
                if ids:
                    match_id = ids[0]
                    if baseline_match_id is None:
                        if live_game_id:
                            # 베이스라인 없음(캡처 실패) — gameId 검증으로
                            # 이전 매치를 새 경기로 오인하지 않게 대기
                            raw = client.get_match(match_id)
                            if _raw_game_id(raw) == live_game_id:
                                return client.summarize_match(raw, profile.puuid)
                        else:
                            # 첫 게임 — 최신 매치 그대로 사용
                            raw = client.get_match(match_id)
                            return client.summarize_match(raw, profile.puuid)
                    elif match_id != baseline_match_id:
                        raw = client.get_match(match_id)
                        return client.summarize_match(raw, profile.puuid)
                if attempt < 3:
                    _time.sleep(20)
            return None

        def on_end(match: Any) -> None:
            self.after(0, lambda: self._on_game_ended(match))

        self._watcher = GameEndWatcher(
            get_active_game=lambda: client.get_active_game(profile.puuid),
            get_latest_match=latest,
            on_game_end=on_end,
            on_game_seen=capture_baseline,
        )
        self._watcher.start()
        if self._game_end_auto_review_on():
            self.status.configure(text="🔔 게임 종료 감지 중 — 끝나면 자동 복기")
        else:
            self.status.configure(text="🔔 게임 종료 감지 중 — 자동 복기 끔")


    def _start_game_start_watcher(self) -> None:
        """전적 로드 후 — 게임 시작을 1분 간격으로 감지 (시작 시 1회 알림)."""
        riot = getattr(self, "riot", None)
        profile = getattr(self, "profile", None)
        if riot is None or profile is None:
            return
        w = getattr(self, "_game_start_watcher", None)
        if w is not None and w.running:
            if getattr(self, "_game_start_puuid", None) == profile.puuid:
                return
            # 계정이 바뀌면 옛 puuid 폴링 중단 후 재시작
            try:
                w.stop()
            except Exception:
                pass
            self._game_start_watcher = None
        self._game_start_puuid = profile.puuid
        from lol_coach.gui.watcher import GameStartWatcher

        def on_start(game: Any) -> None:
            self.after(0, lambda g=game: self._on_game_started(g))

        def on_game_gone() -> None:
            self.after(0, self._on_game_gone)

        self._game_start_watcher = GameStartWatcher(
            get_active_game=lambda: riot.get_active_game(profile.puuid),
            on_game_start=on_start,
            on_game_gone=on_game_gone,
        )
        self._game_start_watcher.start()

    def _game_start_label(self, game: Any) -> str:
        try:
            from lol_coach.modes import ARAM_QUEUES

            qid = int(getattr(game, "game_queue_config_id", 0) or 0)
            mode = "칼바람·아수라장" if qid in ARAM_QUEUES else "소환사의 협곡"
            cid = getattr(game, "my_champion_id", None)
            champ = self.dd.champion_name(int(cid)) if cid else "?"
            return f"{mode} · 내 챔피언 {champ}"
        except Exception:
            return "게임 시작"

    def _game_start_summary_lines(self, game: Any) -> list[str]:
        lines: list[str] = []
        try:
            cid = getattr(game, "my_champion_id", None)
            champ = self.dd.champion_name(int(cid)) if cid else "?"
            lines.append(f"내 챔피언: {champ}")
            my_team_id = int(getattr(game, "my_team_id", 0) or 0)
            allies: list[str] = []
            enemies: list[str] = []
            for p in getattr(game, "participants", None) or []:
                pcid = int(p.get("championId") or 0)
                if not pcid:
                    continue
                name = self.dd.champion_name(pcid)
                team_id = int(p.get("teamId") or 0)
                roster = allies if team_id == my_team_id else enemies
                if name and name not in roster:
                    roster.append(name)
            if allies:
                lines.append("아군: " + " · ".join(allies[:5]))
            if enemies:
                lines.append("적군: " + " · ".join(enemies[:5]))
        except Exception:
            pass
        return lines

    def _on_game_started(self, game: Any) -> None:
        """게임 시작 — 알림 + 상태바 + 미니 위젯 브리핑 (1회)."""
        label = self._game_start_label(game)
        self._live_notification_blocked = False
        if self._game_start_notify_on():
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            self._notify(f"🎮 게임 시작! {label}", level="ok", ms=3000)
        self._live_notification_blocked = True
        self.status.configure(text=f"🎮 {label}")
        try:
            lines = self._game_start_summary_lines(game)
            self._push_summary("🎮 진행 중 게임", lines)
        except Exception:
            pass
        self._start_game_end_watcher()

    def _game_start_notify_on(self) -> bool:
        """게임 시작 알림 on/off (설정 체크박스 또는 ui.json). 기본 ON."""
        var = getattr(self, "game_start_notify_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            from lol_coach.config import game_start_notify_enabled

            return game_start_notify_enabled()
        except Exception:
            return True


    def _on_game_gone(self) -> None:
        """게임 시작 감지가 None으로 복귀 — 종료로 간주해 알림 차단 해제.

        GameEndWatcher가 없어도(자동 검색을 누르지 않아도) 차단 플래그가
        세션 내내 걸려 있지 않도록 하는 안전장치.
        """
        self._live_notification_blocked = False
        flush = getattr(self, "_flush_notification_queue", None)
        if flush is not None:
            flush()

    def _on_game_ended(self, match: Any) -> None:
        self._live_notification_blocked = False
        flush = getattr(self, "_flush_notification_queue", None)
        if flush is not None:
            flush()
        if match is None:
            self.status.configure(text="게임 종료 감지됨 — 매치 조회 실패")
            return
        champ = self.loc.champion(match.champion_name) or match.champion_name
        mark = "승리" if match.win else "패배"
        auto_review = self._game_end_auto_review_on()
        if auto_review:
            self.status.configure(text=f"🔔 방금 게임({champ} {mark}) 복기 도착")
        else:
            self.status.configure(
                text=f"🔔 방금 게임({champ} {mark}) 종료 · 자동 복기 끔"
            )
        self._notify_game_end(champ, match.win)
        self._send_discord_review_card(match)
        if not auto_review:
            return
        try:
            self._show_match_detail(match)
        except Exception as exc:
            _log.exception("자동 복기 화면 표시 실패: %s", exc)
            self.status.configure(text=f"자동 복기 표시 실패: {exc}")
            self._notify("자동 복기 화면을 열지 못했습니다.", level="error", ms=5200)


    def _send_discord_review_card(self, match: Any) -> None:
        """게임 종료 시 — 디스코드 웹훅으로 복기 카드 전송 (백그라운드 스레드).

        웹훅 URL이 설정돼 있고 자동 전송이 켜져 있을 때만 동작하며,
        실패는 상태바·알림으로 노출하고 조용히 삼키지 않는다.
        """
        try:
            from lol_coach.config import discord_review_enabled, discord_webhook_url

            webhook = discord_webhook_url()
            if not webhook or not discord_review_enabled():
                return
        except Exception:
            return
        import threading

        def work() -> None:
            try:
                png = self._build_review_card_png(match)
                if png is None:
                    self.after(
                        0,
                        lambda: self._notify(
                            "디스코드 카드 렌더 실패 — 타임라인 없음",
                            level="warn",
                        ),
                    )
                    return
                from lol_coach.notify.discord import post_card

                champ = self.loc.champion(match.champion_name) or match.champion_name
                mark = "승리" if match.win else "패배"
                kda = f"{match.kills}/{match.deaths}/{match.assists}"
                post_card(
                    webhook,
                    title=f"{champ} {mark} — 복기 카드",
                    description=(
                        f"{match.mode_label} · KDA {kda} · "
                        f"{match.duration_min:.0f}분 — 상세는 카드 이미지"
                    ),
                    png_bytes=png,
                    footer=f"롤 실전 코치 · Riot Match-V5 · {match.match_id}",
                )
                self.after(
                    0,
                    lambda: self._notify(
                        "📮 디스코드로 복기 카드 전송 완료", level="ok"
                    ),
                )
            except Exception as exc:
                _log.exception("디스코드 복기 카드 전송 실패: %s", exc)
                self.after(
                    0,
                    lambda e=exc: self._notify(
                        f"디스코드 전송 실패: {e}", level="error", ms=5200
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _build_review_card_png(self, match: Any) -> bytes | None:
        """복기 카드 PNG 바이트 — 킬 지도·붕괴 스냅샷 포함 (실패해도 텍스트 카드)."""
        from lol_coach.analysis.killmap import build_kill_map, map_id_for_queue
        from lol_coach.analysis.review import analyze_match
        from lol_coach.gui.map_render import (
            render_collapse_snapshot,
            render_kill_minimap,
        )
        from lol_coach.gui.review_card import review_card_bytes
        from lol_coach.static.icons import map_pil

        match_id = str(getattr(match, "match_id", "") or "")
        minimap = collapse = None
        caption = ""
        tl = raw = None
        local_mode = bool(getattr(self, "_me_local_mode", False))
        riot = getattr(self, "riot", None)
        if not local_mode and riot is not None and match_id:
            try:
                tl = riot.get_match_timeline(match_id)
                raw = riot.get_match(match_id)
            except Exception:
                tl = raw = None
        if (tl is None or raw is None) and match_id:
            try:
                from lol_coach.analysis.lcu_match import try_local_timeline
                from lol_coach.lcu import LCUClient

                pair = try_local_timeline(
                    LCUClient(), match_id, id_to_key=self.dd.champion_key
                )
                if pair is not None:
                    tl, raw = pair
            except Exception:
                pass
        pid = None
        raw_pid = (match.raw_participant or {}).get("participantId")
        try:
            pid = int(raw_pid) if raw_pid is not None else None
        except (TypeError, ValueError):
            pid = None
        if tl is not None and raw is not None:
            try:
                km = build_kill_map(tl, raw, pid)
                if km.my_kills or km.my_deaths:
                    base = map_pil(map_id_for_queue(match.queue_id), 512)
                    minimap = render_kill_minimap(km, base, size=320)
                    if km.collapse is not None:
                        collapse = render_collapse_snapshot(km, base, size=300)
                        caption = km.collapse.caption
            except Exception:
                minimap = collapse = None
        rev = analyze_match(match)
        return review_card_bytes(
            match,
            rev,
            minimap=minimap,
            collapse=collapse,
            collapse_caption=caption,
        )

    def _game_end_notify_on(self) -> bool:
        """내 전적 탭 체크박스 또는 ui.json 설정. 기본 ON."""
        var = getattr(self, "game_end_notify_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            from lol_coach.config import game_end_notify_enabled

            return game_end_notify_enabled()
        except Exception:
            return True

    def _game_end_auto_review_on(self) -> bool:
        """종료 시 복기 패널 자동 열기. 기본 ON."""
        var = getattr(self, "game_end_auto_review_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            from lol_coach.config import game_end_auto_review_enabled

            return game_end_auto_review_enabled()
        except Exception:
            return True

    def _notify_game_end(self, champ: str, win: bool) -> None:
        """게임 종료 알림 — 사운드 + 작업 표시줄 플래시 (비모달).

        설정에서 끈 경우 상태바만 남고 소리/플래시는 생략.
        """
        if not self._game_end_notify_on():
            return
        try:
            import winsound

            winsound.MessageBeep(
                winsound.MB_ICONASTERISK if win else winsound.MB_ICONHAND
            )
        except Exception:
            pass
        try:
            # 작업 표시줄 깜빡임 (win32 전용, 실패해도 무해)
            import ctypes

            hwnd = self.winfo_id()
            # 내부 위젯이 아닌 최상위 창 핸들 찾기
            top = ctypes.windll.user32.GetAncestor(ctypes.c_void_p(hwnd), 2)  # GA_ROOT
            ctypes.windll.user32.FlashWindow(ctypes.c_void_p(top or hwnd), True)
        except Exception:
            pass

