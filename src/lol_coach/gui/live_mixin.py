"""인게임/종료 감지 공통

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox
from typing import Any

from lol_coach.config import DEFAULT_PLATFORM, load_settings, save_api_key, save_player
from lol_coach.gui.live_session import (
    EndWatcherController,
    form_sample_for_queue,
    is_mayhem_queue,
    is_remake_or_abort,
    live_queue_label,
    peek_live_game_id,
    should_auto_brief_select,
    should_replace_end_watcher,
)
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger
from lol_coach.riot.client import RiotClient

_log = get_logger("live")

__all__ = ["LiveMixin", "is_remake_or_abort"]


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
            self.after(0, lambda: status_label.configure(text="밴픽 종료 · 추적 중단"))
            self._champ_watcher: Any = None

        self._champ_watcher = ChampSelectWatcher(
            get_champ_select=get,
            on_update=on_update,
            on_end=on_end,
            interval_s=4.0,
        )
        self._champ_watcher.start()
        status_label.configure(text=watching_text)

    def _start_mayhem_select_watcher(self) -> None:
        """앱이 켜져 있으면 LCU 아수라장 밴픽을 상시 추적한다 (버튼 불필요)."""
        w = getattr(self, "_mayhem_select_watcher", None)
        if w is not None and getattr(w, "running", False):
            return
        from lol_coach.gui.watcher import AlwaysOnChampSelect
        from lol_coach.lcu import LCUClient

        def get() -> Any:
            try:
                return LCUClient().champ_select()
            except Exception:
                return None

        def on_update(info: Any) -> None:
            self.after(0, lambda i=info: self._on_mayhem_select(i))

        self._mayhem_select_watcher = AlwaysOnChampSelect(
            get_champ_select=get,
            on_update=on_update,
            should_handle=should_auto_brief_select,
            interval_s=3.0,
        )
        self._mayhem_select_watcher.start()

    def _on_mayhem_select(self, info: Any) -> None:
        """아수라장 밴픽 — 챔프/증강이 바뀌면 탭을 열고 브리핑을 바로 돌린다."""
        if not should_auto_brief_select(info):
            return
        apply = getattr(self, "_apply_lcu_aram", None)
        if apply is None:
            return
        sig = (
            int(getattr(info, "my_champion_id", 0) or 0),
            tuple(getattr(info, "my_augments", None) or []),
        )
        if sig == getattr(self, "_aram_lcu_sig", ()):
            return
        try:
            tabs = getattr(self, "tabs", None)
            if tabs is not None:
                tabs.set("ARAM 아수라장")
                style = getattr(self, "_style_tabs", None)
                if callable(style):
                    style()
        except Exception:
            pass
        try:
            self.dd.ensure_loaded()
        except Exception:
            pass
        apply(info)

    def _start_mayhem_offer_watcher(self) -> None:
        """아수라장 인게임 — 맵에서 뜨는 제시 증강을 라이브 데이터로 읽는다."""
        w = getattr(self, "_mayhem_offer_watcher", None)
        if w is not None and getattr(w, "running", False):
            return
        from lol_coach.gui.watcher import MayhemOfferWatcher
        from lol_coach.lcu import fetch_live_client_data

        def on_names(names: list[str]) -> None:
            self.after(0, lambda n=list(names): self._on_mayhem_offers(n))

        def on_pick_window(level: int) -> None:
            self.after(500, lambda: self._capture_offered_augments())

        self._mayhem_offer_watcher = MayhemOfferWatcher(
            get_payload=fetch_live_client_data,
            on_names=on_names,
            on_pick_window=on_pick_window,
            interval_s=2.0,
        )
        self._mayhem_offer_watcher.start()

    def _on_mayhem_offers(self, names: list[str]) -> None:
        apply = getattr(self, "_apply_offered_augments", None)
        if apply is None:
            return
        apply(names)

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
        incoming_id = peek_live_game_id(riot, profile.puuid)
        watcher = getattr(self, "_watcher", None)
        running = watcher is not None and bool(getattr(watcher, "running", False))
        same_account = getattr(self, "_watcher_puuid", None) == profile.puuid
        current_id = int(getattr(self, "_watcher_game_id", 0) or 0)
        if not should_replace_end_watcher(
            running=running,
            same_account=same_account,
            current_id=current_id,
            incoming_id=incoming_id,
        ):
            return
        if watcher is not None and running:
            watcher.stop()
            self._watcher = None
        self._watcher_puuid = profile.puuid
        self._watcher_game_id = incoming_id
        self._watcher_gen = int(getattr(self, "_watcher_gen", 0) or 0) + 1
        my_gen = self._watcher_gen
        ctrl = getattr(self, "_end_watcher_ctrl", None)
        if ctrl is None:
            ctrl = EndWatcherController()
            self._end_watcher_ctrl = ctrl
        ctrl.gen = my_gen
        self._watcher = ctrl.make(
            client=riot,
            profile=profile,
            incoming_id=incoming_id,
            is_current_gen=lambda: int(getattr(self, "_watcher_gen", 0) or 0) == my_gen,
            on_end=lambda match: self.after(0, lambda m=match: self._on_game_ended(m)),
            on_waiting=lambda: self.after(
                0,
                lambda: self.status.configure(text="⏳ 게임 전적 업데이트 중…"),
            ),
            on_game_id=lambda gid: setattr(self, "_watcher_game_id", gid),
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
            qid = int(getattr(game, "game_queue_config_id", 0) or 0)
            mode = live_queue_label(qid)
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
        try:
            qid = int(getattr(game, "game_queue_config_id", 0) or 0)
        except (TypeError, ValueError):
            qid = 0
        if is_mayhem_queue(qid):
            self._auto_brief_mayhem(game)
            self._start_mayhem_offer_watcher()
        self._predict_game_start(game)
        self._scout_game_start(game)
        self._start_game_end_watcher()

    def _auto_brief_mayhem(self, game: Any) -> None:
        """아수라장 시작 — 챔프를 채우고 TOP3·6슬롯 브리핑을 바로 연다."""
        if not hasattr(self, "aram_champ_var") or not hasattr(self, "_run_aram"):
            return
        try:
            from lol_coach.analysis.live_fill import parse_live_game

            puuid = getattr(getattr(self, "profile", None), "puuid", None)
            fill = parse_live_game(game, self.dd, my_puuid=puuid)
        except Exception as exc:
            _log.debug("아수라장 자동 브리핑 스킵: %s", exc)
            return
        try:
            tabs = getattr(self, "tabs", None)
            if tabs is not None:
                tabs.set("ARAM 아수라장")
        except Exception:
            pass
        apply = getattr(self, "_apply_live_aram", None)
        if apply is None:
            return
        apply(fill, confirm_sr=False)

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
        if is_remake_or_abort(match):
            self.status.configure(text="게임 종료 감지됨 — 리메이크/조기 종료 (정산 생략)")
            return
        champ = self.loc.champion(match.champion_name) or match.champion_name
        mark = "승리" if match.win else "패배"
        auto_review = self._game_end_auto_review_on()
        if auto_review:
            self.status.configure(text=f"🔔 방금 게임({champ} {mark}) 복기 도착")
        else:
            self.status.configure(text=f"🔔 방금 게임({champ} {mark}) 종료 · 자동 복기 끔")
        self._notify_game_end(champ, match.win)
        self._send_discord_review_card(match)
        self._settle_prediction(match)
        self._settle_blame(match)
        if not auto_review:
            return
        try:
            self._show_match_detail(match)
        except Exception as exc:
            _log.exception("자동 복기 화면 표시 실패: %s", exc)
            self.status.configure(text=f"자동 복기 표시 실패: {exc}")
            self._notify("자동 복기 화면을 열지 못했습니다.", level="error", ms=5200)

    def _send_discord_review_card(self, match: Any) -> None:
        """게임 종료 시 — 디스코드 웹훅으로 복기 카드 전송."""

        def champ() -> str:
            return self.loc.champion(match.champion_name) or match.champion_name

        def render() -> bytes:
            png = self._build_review_card_png(match)
            if png is None:
                raise RuntimeError("타임라인 없음 — 카드 렌더 실패")
            return png

        self._post_discord_card(
            title_fn=lambda: f"{champ()} {'승리' if match.win else '패배'} — 복기 카드",
            description_fn=lambda: (
                f"{match.mode_label} · KDA "
                f"{match.kills}/{match.deaths}/{match.assists} · "
                f"{match.duration_min:.0f}분 — 상세는 카드 이미지"
            ),
            png_bytes_fn=render,
            footer_fn=lambda: f"롤 실전 코치 · Riot Match-V5 · {match.match_id}",
            ok_msg="📮 디스코드로 복기 카드 전송 완료",
            fail_msg="디스코드 전송 실패",
        )

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

                pair = try_local_timeline(LCUClient(), match_id, id_to_key=self.dd.champion_key)
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

    def _predict_game_start(self, game: Any) -> None:
        """게임 시작 — 승패 예측 계산·저장 + 토스트 + 디스코드 카드 (백그라운드)."""
        try:
            my_champ_id = int(getattr(game, "my_champion_id", 0) or 0)
            my_team_id = int(getattr(game, "my_team_id", 0) or 0)
            participants = list(getattr(game, "participants", None) or [])
            if not my_champ_id or not my_team_id or len(participants) < 6:
                return
            qid = int(getattr(game, "game_queue_config_id", 0) or 0)
            start_ms = int(getattr(game, "game_start_time", 0) or 0)
        except (TypeError, ValueError):
            return
        import threading

        def work() -> None:
            try:
                from lol_coach.analysis.prediction import (
                    add_prediction,
                    predict_game,
                )
                from lol_coach.config import PROJECT_ROOT

                form = getattr(self, "_me_form_full", None)
                winrate, games = form_sample_for_queue(form, qid)
                pred = predict_game(
                    self.dd,
                    my_champ_id=my_champ_id,
                    my_team_id=my_team_id,
                    participants=participants,
                    form_winrate=winrate,
                    form_sample=games,
                    created_at_ms=start_ms or None,
                )
                add_prediction(PROJECT_ROOT / "cache" / "predictions.json", pred)
                head = pred.reasons[0] if pred.reasons else ""
                self.after(
                    0,
                    lambda: self._notify(
                        f"🔮 승률 예측 {pred.win_prob}% — {head}",
                        level="ok",
                        ms=5200,
                    ),
                )
                self.after(0, lambda: self._send_prediction_card(pred, qid))
            except Exception as exc:
                _log.exception("승패 예측 실패: %s", exc)

        threading.Thread(target=work, daemon=True).start()

    def _send_prediction_card(self, pred: Any, queue_id: int) -> None:
        """게임 시작 — 예측 카드 디스코드 전송."""

        def champ_ko() -> str:
            return self.dd.champion_name(pred.my_champ_id) or "?"

        def render() -> bytes:
            from lol_coach.gui.prediction_card import prediction_card_bytes
            from lol_coach.modes import display_mode_for_queue

            return prediction_card_bytes(
                pred,
                champ_ko=champ_ko(),
                mode_label=display_mode_for_queue(queue_id),
            )

        self._post_discord_card(
            title_fn=lambda: f"🔮 승패 예측 — {champ_ko()}",
            description_fn=lambda: (
                f"예상 승률 {pred.win_prob}% · {(pred.reasons or ('양팀 팽팽',))[0]}"
            ),
            png_bytes_fn=render,
            footer_fn=lambda: "롤 실전 코치 · 조합 + 내 폼 기반 예측",
            ok_msg="📮 승패 예측 카드 전송 완료",
            fail_msg="예측 카드 전송 실패",
        )

    def _settle_prediction(self, match: Any) -> None:
        """게임 종료 — 예측 소비 + 성적표 토스트 + 디스코드 카드 (백그라운드)."""
        try:
            ally = tuple(
                sorted(
                    {
                        int(p.champion_id)
                        for p in (getattr(match, "ally_team", None) or [])
                        if getattr(p, "champion_id", 0)
                    }
                )
            )
            enemy = tuple(
                sorted(
                    {
                        int(p.champion_id)
                        for p in (getattr(match, "enemy_team", None) or [])
                        if getattr(p, "champion_id", 0)
                    }
                )
            )
            if len(ally) < 3 or len(enemy) < 3:
                return
            qid = int(getattr(match, "queue_id", 0) or 0)
        except (TypeError, ValueError):
            return
        import threading

        def work() -> None:
            try:
                from lol_coach.analysis.prediction import consume_prediction
                from lol_coach.config import PROJECT_ROOT

                pred = consume_prediction(
                    PROJECT_ROOT / "cache" / "predictions.json",
                    ally_roster=ally,
                    enemy_roster=enemy,
                )
                if pred is None:
                    return
                champ_ko = self.loc.champion(match.champion_name) or match.champion_name
                hit = (pred.win_prob >= 50) == bool(match.win)
                mark = "적중" if hit else "빗나감"
                self.after(
                    0,
                    lambda: self._notify(
                        f"🧾 예측 성적표 — 예측 {pred.win_prob}% → "
                        f"{'승리' if match.win else '패배'} · {mark}!",
                        level="ok" if hit else "warn",
                        ms=6000,
                    ),
                )
                self.after(
                    0,
                    lambda: self._send_receipt_card(pred, champ_ko, qid, bool(match.win), match),
                )
            except Exception as exc:
                _log.exception("예측 성적표 정산 실패: %s", exc)

        threading.Thread(target=work, daemon=True).start()

    def _send_receipt_card(
        self,
        pred: Any,
        champ_ko: str,
        queue_id: int,
        win: bool,
        match: Any,
    ) -> None:
        """게임 종료 — 예측 성적표 카드 디스코드 전송."""
        hit = (pred.win_prob >= 50) == win

        def render() -> bytes:
            from lol_coach.analysis.review import analyze_match
            from lol_coach.gui.prediction_card import receipt_card_bytes
            from lol_coach.modes import display_mode_for_queue

            return receipt_card_bytes(
                pred,
                champ_ko=champ_ko,
                mode_label=display_mode_for_queue(queue_id),
                win=win,
                lesson=analyze_match(match).lesson or "",
            )

        self._post_discord_card(
            title_fn=lambda: f"🧾 예측 성적표 — {champ_ko}",
            description_fn=lambda: (
                f"예측 {pred.win_prob}% → {'승리' if win else '패배'} · "
                f"{'적중' if hit else '빗나감'}"
            ),
            png_bytes_fn=render,
            footer_fn=lambda: "롤 실전 코치 · 예측 성적표",
            ok_msg="📮 예측 성적표 카드 전송 완료",
            fail_msg="성적표 카드 전송 실패",
        )

    def _settle_blame(self, match: Any) -> None:
        """게임 종료 — 누구 탓 % 정산 토스트 + 디스코드 카드 (백그라운드)."""
        import threading

        def work() -> None:
            try:
                from lol_coach.analysis.blame import analyze_blame

                report = analyze_blame(match)
                if report is None:
                    return
                champ_ko = self.loc.champion(match.champion_name) or match.champion_name
                self.after(
                    0,
                    lambda: self._notify(
                        f"⚖️ 이 판 탓 — 나 {report.me_pct}% · "
                        f"팀 {report.team_pct}% · 상대 {report.enemy_pct}%",
                        level="info",
                        ms=6000,
                    ),
                )
                self.after(
                    0,
                    lambda: self._send_blame_card(report, champ_ko),
                )
            except Exception as exc:
                _log.exception("팀운 정산 실패: %s", exc)

        threading.Thread(target=work, daemon=True).start()

    def _send_blame_card(self, report: Any, champ_ko: str) -> None:
        """게임 종료 — 팀운 정산 카드 디스코드 전송."""

        def render() -> bytes:
            from lol_coach.gui.blame_card import blame_card_bytes

            return blame_card_bytes(report, champ_ko=champ_ko)

        self._post_discord_card(
            title_fn=lambda: f"⚖️ 이 판 누구 탓 — {champ_ko}",
            description_fn=lambda: (
                f"{report.verdict} (나 {report.me_pct}% · "
                f"팀 {report.team_pct}% · 상대 {report.enemy_pct}%)"
            ),
            png_bytes_fn=render,
            footer_fn=lambda: "롤 실전 코치 · 팀운 정산",
            ok_msg="📮 팀운 정산 카드 전송 완료",
            fail_msg="팀운 정산 카드 전송 실패",
        )

    def _post_discord_card(
        self,
        *,
        title_fn: Callable[[], str],
        description_fn: Callable[[], str],
        png_bytes_fn: Callable[[], bytes],
        footer_fn: Callable[[], str],
        ok_msg: str,
        fail_msg: str,
    ) -> None:
        """웹훅 가드 + 백그라운드 전송 + 토스트 공통 경로.

        제목·설명·PNG·푸터는 전부 지연 호출 — 웹훅이 설정되지 않았거나
        자동 전송이 꺼져 있으면 어떤 부수 효과도 일으키지 않는다.
        실패는 상태바·알림으로 노출하고 조용히 삼키지 않는다.
        """
        try:
            from lol_coach.config import discord_review_enabled, discord_webhook_url

            webhook = discord_webhook_url()
            if not webhook or not discord_review_enabled():
                return
        except Exception:
            return

        def work() -> None:
            try:
                from lol_coach.notify.discord import post_card

                post_card(
                    webhook,
                    title=title_fn(),
                    description=description_fn(),
                    png_bytes=png_bytes_fn(),
                    footer=footer_fn(),
                )
                self.after(
                    0,
                    lambda: self._notify(ok_msg, level="ok", ms=2600),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda e=exc: self._notify(f"{fail_msg}: {e}", level="error", ms=5200),
                )

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _scout_game_start(self, game: Any) -> None:
        """게임 시작 — 10인 정찰 + 리드 칩 토스트·카드 (백그라운드)."""
        try:
            participants = list(getattr(game, "participants", None) or [])
            profile = getattr(self, "profile", None)
            my_puuid = getattr(profile, "puuid", "") if profile else ""
            riot = getattr(self, "riot", None)
            if not participants or not my_puuid or riot is None:
                return
        except (TypeError, ValueError):
            return
        import threading

        def work() -> None:
            try:
                import time as _time

                from lol_coach.analysis.scouting import (
                    build_scouting_report,
                    scouting_headline,
                )
                from lol_coach.config import cache_root

                report = build_scouting_report(
                    riot,
                    participants,
                    my_puuid,
                    cache_path=cache_root() / "scout_cache.json",
                    now_ms=int(_time.time() * 1000),
                )
                if report.scanned == 0:
                    return
                headline = scouting_headline(report)
                self.after(
                    0,
                    lambda: self._notify(
                        f"🔍 정찰 완료 — {headline}",
                        level="info",
                        ms=6500,
                    ),
                )
                self.after(0, lambda: self._send_scouting_card(report))
            except Exception as exc:
                _log.exception("10인 정찰 실패: %s", exc)

        threading.Thread(target=work, daemon=True).start()

    def _send_scouting_card(self, report: Any) -> None:
        """정찰 카드 디스코드 전송 (설정돼 있고 켜져 있을 때만)."""

        def render() -> bytes:
            from lol_coach.gui.scouting_card import scouting_card_bytes

            return scouting_card_bytes(report, self.dd)

        from lol_coach.analysis.scouting import scouting_headline

        self._post_discord_card(
            title_fn=lambda: "🔍 10인 정찰 — 리드 칩",
            description_fn=lambda: scouting_headline(report),
            png_bytes_fn=render,
            footer_fn=lambda: (
                f"롤 실전 코치 · 정찰 {report.scanned}명 · 표본 3판 미만 침묵"
            ),
            ok_msg="📮 정찰 카드 전송 완료",
            fail_msg="정찰 카드 전송 실패",
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

            winsound.MessageBeep(winsound.MB_ICONASTERISK if win else winsound.MB_ICONHAND)
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
