"""소환사의 협곡 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.comp import CompReport
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FS, FU, ROLES
from lol_coach.gui.constants import counter_tier as _counter_tier
from lol_coach.gui.types import MixinBase
from lol_coach.modes import MODE_SUMMONERS_RIFT
from lol_coach.static.icons import champion_ctk, champion_pil, item_name_ctk, item_pil_by_name


class SrTabMixin(MixinBase):
    def _push_sr_history(self, fn: Any, *args: Any) -> None:
        """협곡 결과 렌더 함수를 히스토리에 저장 (최근 20개). 메인 스레드에서만 호출."""
        self._sr_history.append((fn, args, {}))
        if len(self._sr_history) > 20:
            self._sr_history.pop(0)


    def _back_sr_history(self) -> None:
        """이전 결과로 복원 (히스토리 pop → 재렌더)."""
        if not self._sr_history:
            self._notify("이전 결과가 없습니다.", level="warn")
            return
        fn, args, _kw = self._sr_history.pop()
        try:
            fn(*args)
        except Exception as exc:
            self._notify(f"이전 결과 복원 실패: {exc}", level="error")


    def _set_sr_inputs_expanded(self, expanded: bool) -> None:
        """입력 패널 접기/펼치기 — 결과(상세 코칭) 영역 최대화."""
        self._sr_inputs_expanded = expanded
        host = getattr(self, "_sr_inputs_host", None)
        btn = getattr(self, "_sr_fold_btn", None)
        if host is None:
            return
        if expanded:
            host.grid()
            if btn is not None:
                btn.configure(text="▲ 입력 접기 (결과 크게)")
        else:
            host.grid_remove()
            if btn is not None:
                btn.configure(text="▼ 입력 펼치기")

    def _toggle_sr_inputs(self) -> None:
        self._set_sr_inputs_expanded(not getattr(self, "_sr_inputs_expanded", True))

    def _collapse_sr_inputs_for_results(self) -> None:
        """분석 결과가 나오면 입력란 접어 코칭 영역 확보."""
        try:
            self._set_sr_inputs_expanded(False)
        except Exception:
            pass

    def _build_sr(self) -> None:
        # 접기 바 (항상 표시) + 입력 호스트 + 결과(최대 공간)
        bar = ctk.CTkFrame(self.t_sr, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))
        self._sr_fold_btn = ctk.CTkButton(
            bar,
            text="▲ 입력 접기 (결과 크게)",
            height=26,
            width=160,
            font=FCH,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._toggle_sr_inputs,
        )
        self._sr_fold_btn.pack(side="left")
        ctk.CTkLabel(
            bar,
            text="분석 후 자동으로 접혀 상세 코칭이 크게 보입니다",
            font=FCH,
            text_color=ui.TEXT_MUTE,
        ).pack(side="left", padx=8)

        self._sr_inputs_host = ctk.CTkFrame(self.t_sr, fg_color="transparent")
        self._sr_inputs_host.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self._sr_inputs_expanded = True

        # ── 빠른 카운터 (메인) ──
        quick = ctk.CTkFrame(
            self._sr_inputs_host,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        quick.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        quick.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            quick, text="⚡ 빠른 카운터", font=FU, anchor="w", text_color=ui.GOLD_SOFT
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 2))

        ctk.CTkLabel(quick, text="포지션", font=FM).grid(
            row=1, column=0, sticky="w", padx=(10, 4), pady=2
        )
        self.role_var = tk.StringVar(value="미드")
        roles = ctk.CTkFrame(quick, fg_color="transparent")
        roles.grid(row=1, column=1, columnspan=2, sticky="w", pady=2)
        self._role_btns = []
        for lab, _ in ROLES:
            b = ctk.CTkButton(
                roles,
                text=lab,
                width=48,
                height=26,
                font=FM,
                fg_color=ui.PANEL,
                text_color=ui.GOLD_SOFT,
                command=lambda L=lab: self._select_role(L),
            )
            b.pack(side="left", padx=1)
            self._role_btns.append(b)
        self._select_role("미드")

        self.enemy_lane_var = tk.StringVar()
        ctk.CTkLabel(quick, text="적 라이너", font=FM, width=72, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(10, 4), pady=3
        )
        ent = ctk.CTkEntry(
            quick,
            textvariable=self.enemy_lane_var,
            placeholder_text="예: 야스오, 아리, 제드 …",
            font=FM,
            height=30,
        )
        ent.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=3)
        ent.bind("<Return>", self._sr_quick_enter)
        ent.bind("<KP_Enter>", self._sr_quick_enter)
        self._sr_lane_ac = self._attach_champ_ac(ent, self.enemy_lane_var, quick)

        self.sr_quick_btn = ctk.CTkButton(
            quick,
            text="빠른 추천",
            width=88,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._run_sr_quick,
        )
        self.sr_quick_btn.grid(row=2, column=2, padx=(0, 8), pady=3)
        ctk.CTkButton(
            quick,
            text="📜",
            width=36,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._back_sr_history,
        ).grid(row=2, column=3, padx=(0, 8), pady=3)

        live_row = ctk.CTkFrame(quick, fg_color="transparent")
        live_row.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 2))
        self.sr_live_btn = ctk.CTkButton(
            live_row,
            text="🎮 인게임",
            height=28,
            width=88,
            font=FM,
            **ui.btn(*ui.BTN_SUCCESS),
            command=self._live_fill_sr,
        )
        self.sr_live_btn.pack(side="left")
        self.sr_lcu_btn = ctk.CTkButton(
            live_row,
            text="🎯 밴픽",
            height=28,
            width=72,
            font=FM,
            **ui.btn(*ui.BTN_PURPLE),
            command=self._lcu_fill_sr,
        )
        self.sr_lcu_btn.pack(side="left", padx=(6, 0))
        ctk.CTkButton(
            live_row,
            text="🧹",
            width=36,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._reset_sr,
        ).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(
            live_row,
            text="LCU=밴픽 · Spectator=인게임",
            font=FCH,
            text_color=ui.TEXT_MUTE,
        ).pack(side="left", padx=8)

        self.sr_status = ctk.CTkLabel(
            quick,
            text="적 한 명 + 포지션 → 카운터 추천",
            font=FCH,
            text_color=ui.TEXT_DIM,
        )
        self.sr_status.grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 4))
        # 자동완성 제안 패널 (기본 숨김 — 입력 시 grid)
        self._sr_lane_ac.panel.grid(
            row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 2)
        )
        self._sr_lane_ac.panel.grid_remove()

        # ── 상세 분석 입력 (콤팩트 2행) ──
        detail = ctk.CTkFrame(
            self._sr_inputs_host,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        detail.grid(row=1, column=0, sticky="ew", padx=6, pady=2)
        self._sr_inputs_host.grid_columnconfigure(0, weight=1)
        detail.grid_columnconfigure(1, weight=1)
        detail.grid_columnconfigure(3, weight=1)
        detail.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            detail, text="📋 상세 입력", font=FU, anchor="w", text_color=ui.GOLD_SOFT
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(6, 2))

        self.my_champ_var = tk.StringVar()
        self.enemy_jg_var = tk.StringVar()
        self.enemy_sup_var = tk.StringVar()
        self.enemy_top_var = tk.StringVar()
        self.enemy_mid_var = tk.StringVar()
        self.enemy_adc_var = tk.StringVar()

        def _mini_entry(parent, row, col, label, var, ph, width=100):
            ctk.CTkLabel(parent, text=label, font=FCH, width=52, anchor="w").grid(
                row=row, column=col, sticky="w", padx=(6, 2), pady=2
            )
            e = ctk.CTkEntry(
                parent,
                textvariable=var,
                placeholder_text=ph,
                font=FM,
                height=28,
                width=width,
            )
            e.grid(row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=2)
            return e

        my_ent = _mini_entry(detail, 1, 0, "내챔", self.my_champ_var, "선택", 110)
        jg_ent = _mini_entry(detail, 1, 2, "적정글", self.enemy_jg_var, "리 신", 100)
        sup_ent = _mini_entry(detail, 1, 4, "적서폿", self.enemy_sup_var, "쓰레쉬", 100)
        top_ent = _mini_entry(detail, 2, 0, "적탑", self.enemy_top_var, "", 100)
        mid_ent = _mini_entry(detail, 2, 2, "적미드", self.enemy_mid_var, "", 100)
        adc_ent = _mini_entry(detail, 2, 4, "적원딜", self.enemy_adc_var, "", 100)

        # 상세 입력 자동완성 — 각 입력마다 전용 패널 슬롯
        for i, (ent, var) in enumerate(
            [
                (my_ent, self.my_champ_var),
                (jg_ent, self.enemy_jg_var),
                (sup_ent, self.enemy_sup_var),
                (top_ent, self.enemy_top_var),
                (mid_ent, self.enemy_mid_var),
                (adc_ent, self.enemy_adc_var),
            ]
        ):
            ac = self._attach_champ_ac(ent, var, detail)
            ac.panel.grid(row=4 + i, column=0, columnspan=6, sticky="ew", padx=8, pady=0)
            ac.panel.grid_remove()

        btn_row = ctk.CTkFrame(detail, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=6, sticky="w", padx=10, pady=(2, 6))
        self.sr_detail_btn = ctk.CTkButton(
            btn_row,
            text="상세 분석",
            height=28,
            width=90,
            font=FM,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._run_sr_detail,
        )
        self.sr_detail_btn.pack(side="left")
        ctk.CTkLabel(
            btn_row,
            text="내 픽+적 조합 → 카운터·밴·아이템·AI 코칭",
            font=FCH,
            text_color=ui.TEXT_MUTE,
        ).pack(side="left", padx=8)

        self.sr_out = ctk.CTkScrollableFrame(
            self.t_sr,
            corner_radius=ui.CARD_RADIUS,
            label_text="결과 · AI 상세 코칭 (여기를 크게 보세요)",
            fg_color=ui.PANEL,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        self.sr_out.grid(row=2, column=0, sticky="nsew", padx=6, pady=(2, 6))
        self.t_sr.grid_rowconfigure(0, weight=0)
        self.t_sr.grid_rowconfigure(1, weight=0)
        self.t_sr.grid_rowconfigure(2, weight=1)
        self.sr_out.grid_columnconfigure(0, weight=1)
        self._lbl(
            self.sr_out,
            "픽타임: 「빠른 추천」 · 여유 있으면 「상세 분석」\n"
            "분석이 끝나면 입력란이 접히고 AI 상세 코칭이 크게 표시됩니다.",
            0,
            color=ui.TEXT_DIM,
            pady=12,
        )


    def _opt_champ(self, var: tk.StringVar) -> str | None:
        v = var.get().strip()
        if not v:
            return None
        try:
            k, _ = self._resolve(v)
            return k
        except ValueError:
            # 잘못된 이름은 분석에 넣지 않음 (이전엔 raw 문자열이 새어 나감)
            return None


    def _lcu_fill_sr(self) -> None:
        """LCU: 밴픽 중 적/내 픽 자동 입력 → 바로 카운터 추천."""
        if self._is_busy("sr_lcu"):
            return
        self.sr_status.configure(text="클라이언트 밴픽 조회 중…")

        def bg() -> None:
            try:
                from lol_coach.lcu import LCUClient

                lcu = LCUClient()
                info = lcu.champ_select()
                self.dd.ensure_loaded()
                self.after(0, lambda: self._apply_lcu_sr(info, force=True))
                # 밴픽 동안 픽 변화를 계속 추적 (종료 시 자동 정지)
                self.after(0, self._start_sr_champ_watch)
            except Exception as e:
                msg = str(e)

                def fail(m: str = msg) -> None:
                    from lol_coach.gui.errors import format_user_error

                    self.sr_status.configure(text="밴픽 조회 실패")
                    self._notify(
                        format_user_error(m) + " · 밴픽 중·클라이언트 실행 확인",
                        level="warn",
                        ms=5000,
                    )

                self.after(0, fail)

        threading.Thread(target=bg, daemon=True).start()


    def _apply_lcu_sr(self, info: Any, *, force: bool = False) -> None:
        from lol_coach.analysis.live_fill import _assign_roles

        # 픽이 바뀌었을 때만 재분석 (밴픽 폴링 dedupe)
        sig = (
            tuple(info.enemy_champion_ids),
            info.my_champion_id,
            tuple(info.ban_champion_ids),
            info.my_position,
        )
        if not force and sig == self._sr_lcu_sig:
            return
        self._sr_lcu_sig: tuple = sig

        if info.is_aram:
            # ARAM 밴픽 감지 → SR 추적 중단, ARAM 탭으로 전환
            self.sr_status.configure(text="ARAM 밴픽 감지 · ARAM 탭으로 이동")
            self._stop_champ_watch()
            self.tabs.set("ARAM 아수라장")
            self._apply_lcu_aram(info, force=True)
            self._start_aram_champ_watch()
            return

        def champ_ko(cid: int) -> str:
            return self.dd.champion_name(cid)

        # 내 픽/포지션
        if info.my_champion_id:
            self.my_champ_var.set(champ_ko(info.my_champion_id))
        pos_map = {
            "top": "탑",
            "jungle": "정글",
            "middle": "미드",
            "bottom": "원딜",
            "utility": "서폿",
        }
        if info.my_position in pos_map:
            self._select_role(pos_map[info.my_position])

        # 적 픽 → 태그 기반 포지션 추정
        enemies_raw = []
        for cid in info.enemy_champion_ids:
            c = self.dd._champions_by_id.get(int(cid))
            if not c:
                continue
            enemies_raw.append(
                {
                    "key": c["id"],
                    "ko": c["name"],
                    "tags": list(c.get("tags") or []),
                    "spell1": 0,
                    "spell2": 0,
                }
            )
        by_role = _assign_roles(enemies_raw) if enemies_raw else {}
        role_vars = {
            "top": self.enemy_top_var,
            "jungle": self.enemy_jg_var,
            "mid": self.enemy_mid_var,
            "adc": self.enemy_adc_var,
            "support": self.enemy_sup_var,
        }
        for r, var in role_vars.items():
            if r in by_role:
                var.set(by_role[r][1])

        my_role = self._role_key()
        lane = by_role.get(my_role)
        if lane:
            self.enemy_lane_var.set(lane[1])

        bans = [champ_ko(c) for c in info.ban_champion_ids if c]
        # 영문 키도 보관 (밴 추천 merge 용)
        ban_en: list[str] = []
        for cid in info.ban_champion_ids:
            if not cid:
                continue
            c = self.dd._champions_by_id.get(int(cid))
            if c:
                ban_en.append(str(c.get("id") or c.get("name") or ""))
            ban_en.append(champ_ko(cid))
        self._lcu_banned_names = ban_en
        ban_txt = f" · 밴: {', '.join(bans[:5])}" if bans else ""
        n = len(info.enemy_champion_ids)
        self.sr_status.configure(
            text=f"밴픽 입력 완료 · 적 {n}명{ban_txt} (포지션은 추정)"
        )
        self.status.configure(text="LCU 밴픽 연동됨")
        if self.enemy_lane_var.get().strip():
            self._run_sr_quick()


    def _start_sr_champ_watch(self) -> None:
        """밴픽 폴링 시작 — 픽 변화가 감지되면 필드를 갱신."""
        from lol_coach.gui.watcher import ChampSelectWatcher
        from lol_coach.lcu import LCUClient

        self._stop_champ_watch()

        def get() -> Any:
            return LCUClient().champ_select()

        def on_update(info: Any) -> None:
            self.after(0, lambda: self._apply_lcu_sr(info))

        def on_end() -> None:
            self.after(0, lambda: self.sr_status.configure(text="밴픽 종료 · 추적 중단"))
            self._champ_watcher: Any = None

        self._champ_watcher = ChampSelectWatcher(
            get_champ_select=get,
            on_update=on_update,
            on_end=on_end,
            interval_s=4.0,
        )
        self._champ_watcher.start()
        self.sr_status.configure(text="밴픽 추적 중 — 픽 바뀌면 자동 갱신")


    def _live_fill_sr(self) -> None:
        """협곡: 인게임 적 조합 + 내 챔프 자동 입력 후 상세 분석."""
        if self._is_busy("sr_live"):
            return
        prepared = self._prepare_riot_for_live()
        if prepared is None:
            return
        client, game_name, tag_line = prepared
        self._busy_set(True, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live")
        self.sr_status.configure(text="인게임 조회 중…")

        def bg() -> None:
            try:
                from lol_coach.analysis.live_fill import parse_live_game

                profile = client.resolve_player(game_name, tag_line)
                game = client.get_active_game(profile.puuid)
                if not game:
                    raise ValueError(
                        f"{profile.riot_id} 님은 지금 인게임이 아닙니다.\n\n"
                        "· 밴픽 중에는 보통 조회 불가\n"
                        "· 로딩~인게임에서 다시 시도"
                    )
                self.dd.ensure_loaded()
                fill = parse_live_game(game, self.dd, my_puuid=profile.puuid)
                self.riot = client
                self.profile = profile
                self.after(0, lambda f=fill: self._apply_live_sr(f))
            except Exception as e:
                msg = str(e)

                def fail(m: str = msg) -> None:
                    from lol_coach.gui.errors import format_user_error

                    self.sr_status.configure(text="인게임 조회 실패")
                    self._notify(format_user_error(m), level="warn", ms=5000)
                    self._busy_set(
                        False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live"
                    )

                self.after(0, fail)

        threading.Thread(target=bg, daemon=True).start()


    def _apply_live_sr(self, fill) -> None:
        """LiveFillResult → 협곡 필드 채우고 상세 분석."""
        try:
            if fill.is_aram:
                self.sr_status.configure(text="ARAM 게임 감지 · ARAM 탭 사용")
                self._notify(
                    "칼바람/아수라장 게임입니다 — 「ARAM 아수라장」탭의 인게임 자동검색을 쓰세요.",
                    level="warn",
                    ms=4500,
                )
                self._busy_set(False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live")
                return

            self.my_champ_var.set(fill.my_champ_ko)
            role_vars = {
                "top": self.enemy_top_var,
                "jungle": self.enemy_jg_var,
                "mid": self.enemy_mid_var,
                "adc": self.enemy_adc_var,
                "support": self.enemy_sup_var,
            }
            for _r, var in role_vars.items():
                var.set("")
            for r, (_key, ko) in fill.enemies_by_role.items():
                if r in role_vars:
                    role_vars[r].set(ko)

            # 빠른 카운터용 적 라이너 = 내 포지션 맞은 적
            my_role = self._role_key()
            lane = fill.enemies_by_role.get(my_role)
            if not lane and fill.enemies_by_role:
                # 아무 적이나
                lane = next(iter(fill.enemies_by_role.values()))
            if lane:
                self.enemy_lane_var.set(lane[1])

            names = [
                f"{r}:{ko}" for r, (_, ko) in fill.enemies_by_role.items()
            ]
            self.sr_status.configure(
                text=f"인게임 입력 완료 · {fill.my_champ_ko} vs {', '.join(names)}"
            )
            self.status.configure(text=f"인게임 · {fill.my_champ_ko}")
            self._busy_set(False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live")
            self._start_game_end_watcher()
            # 적 라이너 있으면 상세 분석까지
            if self.enemy_lane_var.get().strip():
                self._run_sr_detail()
            else:
                enemies = ", ".join(n for _, n in fill.enemies_by_role.values()) or "없음"
                self._notify(
                    f"인게임 입력 · {fill.my_champ_ko} vs {enemies}",
                    level="ok",
                    ms=4000,
                )
        except Exception as e:
            self._notify_error(e)
            self._busy_set(False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live")


    def _run_sr_quick(self) -> None:
        """픽타임용: 적 라이너 + 포지션만."""
        if self._is_busy("sr_quick"):
            return
        try:
            lane_key, lane_ko = self._resolve(self.enemy_lane_var.get())
        except ValueError as e:
            self._notify(str(e), level="warn")
            return
        role = self._role_key()
        self._busy_set(True, self.sr_quick_btn, "빠른 추천", key="sr_quick")
        self.sr_status.configure(text=f"{lane_ko} 카운터 조회 중…")

        my_raw = ""
        if hasattr(self, "my_champ_var"):
            my_raw = self.my_champ_var.get().strip()

        def work() -> None:
            try:
                crep = self.counters.get_counters(
                    lane_key, role=role, limit=5, min_matches=600
                )
                advice = self.draft.advise(crep, top_n=5)
                ban_lines: list[str] = []
                if my_raw:
                    try:
                        my_key, _my_ko = self._resolve(my_raw)
                        from lol_coach.analysis.bans import (
                            get_ban_suggestions,
                            merge_lcu_bans,
                        )

                        br = get_ban_suggestions(
                            self.counters, my_key, role=role, limit=5
                        )
                        already = list(getattr(self, "_lcu_banned_names", []) or [])
                        if already:
                            br = merge_lcu_bans(br, already)
                        ban_lines = [
                            f"{self.loc.champion(b.champion) or b.champion} — {b.reason}"
                            for b in br.bans
                        ]
                    except Exception:
                        ban_lines = []
                advice.ban_lines = ban_lines
                for _name, counter in advice.counters[:5]:
                    champion_pil(counter.champion, 48)

                def _done() -> None:
                    self._collapse_sr_inputs_for_results()
                    self._push_sr_history(self._render_sr_quick, advice, lane_ko, role)
                    self._render_sr_quick(advice, lane_ko, role)

                self.after(0, _done)
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                msg = format_user_error(e)
                self.after(0, lambda: self._sr_err(msg))
            finally:
                self.after(
                    0, lambda: self._busy_set(False, self.sr_quick_btn, "빠른 추천", key="sr_quick")
                )

        threading.Thread(target=work, daemon=True).start()


    def _run_sr_detail(self) -> None:
        """전체 조합 + 아이템 상세."""
        if self._is_busy("sr_detail"):
            return
        try:
            lane_key, lane_ko = self._resolve(self.enemy_lane_var.get())
        except ValueError as e:
            self._notify("적 라이너를 먼저 입력하세요. " + str(e), level="warn")
            return

        role = self._role_key()
        my_raw = self.my_champ_var.get().strip()
        my_key = my_ko = None
        if my_raw:
            try:
                my_key, my_ko = self._resolve(my_raw)
            except ValueError as e:
                self._notify(str(e), level="warn")
                return

        self._busy_set(True, self.sr_detail_btn, "상세 분석", key="sr_detail")
        self.sr_status.configure(text=f"{lane_ko} 상세 분석 중…")

        def work() -> None:
            try:
                crep = self.counters.get_counters(
                    lane_key, role=role, limit=8, min_matches=600
                )
                build = None
                if my_key:
                    build = self.ugg.get_champion_build(
                        my_key, role=role, mode=MODE_SUMMONERS_RIFT
                    )
                    build.champion = my_ko or my_key
                report = self.comp.analyze(
                    my_role=role,
                    enemy_lane=lane_key,
                    my_champ=my_key,
                    enemy_jg=self._opt_champ(self.enemy_jg_var),
                    enemy_sup=self._opt_champ(self.enemy_sup_var),
                    enemy_top=self._opt_champ(self.enemy_top_var),
                    enemy_mid=self._opt_champ(self.enemy_mid_var),
                    enemy_adc=self._opt_champ(self.enemy_adc_var),
                    counter_report=crep,
                    my_build=build,
                )
                matchup: list[str] = []
                ban_lines: list[str] = []
                if my_key:
                    gd = crep.lane_counters[0].gd15 if crep.lane_counters else None
                    for c in crep.lane_counters:
                        if c.champion.lower().replace(" ", "") == my_key.lower():
                            gd = c.gd15
                            break
                    matchup = self.draft.matchup_tips(my_key, lane_key, role, gd15=gd)
                    try:
                        from lol_coach.analysis.bans import (
                            get_ban_suggestions,
                            merge_lcu_bans,
                        )

                        br = get_ban_suggestions(
                            self.counters, my_key, role=role, limit=5
                        )
                        already = list(getattr(self, "_lcu_banned_names", []) or [])
                        if already:
                            br = merge_lcu_bans(br, already)
                        ban_lines = [
                            f"{self.loc.champion(b.champion) or b.champion} — {b.reason}"
                            for b in br.bans
                        ]
                    except Exception:
                        ban_lines = []
                report.ban_lines = ban_lines
                for _name, counter in report.counters[:6]:
                    champion_pil(counter.champion, 40)
                for item in report.core_items[:5]:
                    item_pil_by_name(item, 32)
                for item, _why in report.situational:
                    item_pil_by_name(item, 28)

                def _done() -> None:
                    self._collapse_sr_inputs_for_results()
                    self._push_sr_history(self._render_sr_detail, report, matchup)
                    self._render_sr_detail(report, matchup)

                self.after(0, _done)
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                msg = format_user_error(e)
                self.after(0, lambda: self._sr_err(msg))
            finally:
                self.after(
                    0, lambda: self._busy_set(False, self.sr_detail_btn, "상세 분석", key="sr_detail")
                )

        threading.Thread(target=work, daemon=True).start()


    def _sr_err(self, msg: str) -> None:
        self._clear(self.sr_out)
        self._lbl(self.sr_out, f"오류: {msg}", 0, color=ui.RED_SOFT)
        self.sr_status.configure(text="실패")
        self._notify(msg, level="error", ms=4800)


    def _reset_sr(self) -> None:
        """협곡 탭 입력·결과 전체 초기화."""
        self._stop_champ_watch()
        self.enemy_lane_var.set("")
        self.my_champ_var.set("")
        for var in (
            self.enemy_jg_var,
            self.enemy_sup_var,
            self.enemy_top_var,
            self.enemy_mid_var,
            self.enemy_adc_var,
        ):
            var.set("")
        self._clear(self.sr_out)
        self._lbl(
            self.sr_out,
            "픽타임: 위 「빠른 추천」만 쓰세요.\n"
            "로딩/밴픽 여유 있을 때 「상세 분석」으로 조합까지 보세요.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
        )
        self.sr_status.configure(text="초기화됨 — 적 라이너 + 포지션부터 입력")
        self.status.configure(text="협곡 탭 초기화")


    def _render_sr_quick(self, advice, lane_ko: str, role: str) -> None:
        """픽타임용 짧은 결과."""
        from lol_coach.ugg.counters import ROLE_KO

        self._clear(self.sr_out)
        role_ko = ROLE_KO.get(role, role)
        r = 0
        r = self._lbl(
            self.sr_out,
            f"⚡ {lane_ko} 상대 · {role_ko}  ·  패치 {advice.patch}",
            r,
            font=FS,
            color=ui.GOLD_SOFT,
            pady=8,
        )
        r = self._sec(self.sr_out, "추천 픽 (GD@15 순)", r)
        if not advice.counters:
            r = self._lbl(self.sr_out, "데이터 부족", r)
        else:
            for i, (name, c) in enumerate(advice.counters[:5], 1):
                col = ui.GREEN if c.gd15 >= 200 else ui.WARN
                tip = "초반 강함" if c.gd15 >= 300 else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
                frame = self._row_frame(self.sr_out, r, pady=3)
                icon = self._keep_icon(champion_ctk(c.champion, 48))
                if icon:
                    ctk.CTkLabel(frame, image=icon, text="").pack(
                        side="left", padx=(10, 8), pady=6
                    )
                ctk.CTkLabel(
                    frame,
                    text=f"{i}. {name}\nGD@15 {c.gd15_str}  ·  {tip}  ·  {c.matches:,}게임",
                    font=FU,
                    text_color=col,
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 12), pady=6)
                ui.tier_chip(frame, _counter_tier(c.gd15), font=FCH, width=30).pack(
                    side="right", padx=(0, 12)
                )
                r += 1

        r = self._sec(self.sr_out, "30초 팁", r)
        for t in advice.lane_tips[:3]:
            r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)
        r = self._lbl(
            self.sr_out,
            "→ 여유 있으면 아래 「상세 분석」으로 정글·서폿·상황템까지 확인",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=10,
        )
        # 밴 힌트: 내 챔프가 있으면 그 챔프를 카운터하는 픽
        ban_lines = getattr(advice, "ban_lines", None) or []
        if ban_lines:
            r = self._sec(self.sr_out, "🚫 밴 추천 (내 챔프 기준)", r)
            for bl in ban_lines[:5]:
                r = self._lbl(self.sr_out, f"·  {bl}", r, pady=2, color=ui.WARN)

        self.sr_status.configure(text=f"빠른 추천 완료 · {lane_ko}")
        self.status.configure(text=f"빠른 카운터 · {lane_ko}")
        key = self._ai_key()
        if key:
            self._maybe_ai(
                self.sr_out,
                lambda: self._ai_coach_lane(advice, lane_ko, role, key),
            )
        summary = []
        for i, (name, c) in enumerate(advice.counters[:5], 1):
            tip = (
                "초반 강함"
                if c.gd15 >= 300
                else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
            )
            summary.append(
                f"{i}. {name} — {tip} (GD@15 {c.gd15_str} · {c.matches:,}게임)"
            )
        if ban_lines:
            summary.append("")
            summary.append("🚫 밴 추천")
            summary += [f"· {b}" for b in ban_lines[:4]]
        if advice.lane_tips:
            summary.append("")
            summary += [f"· {t}" for t in advice.lane_tips[:3]]
        self._push_summary(
            f"⚡ vs {lane_ko} · {role_ko}  (패치 {advice.patch})", summary
        )


    def _render_sr_detail(self, rep: CompReport, matchup: list[str]) -> None:
        self._clear(self.sr_out)
        r = 0
        r = self._lbl(
            self.sr_out,
            f"📋 {rep.my_champ_ko} · {rep.my_role} vs {rep.enemy_lane_ko} · {rep.patch}",
            r,
            font=FU,
            color=ui.GOLD_SOFT,
            pady=4,
        )
        team = ", ".join(f"{role} {name}" for role, name in rep.enemy_team)
        r = self._lbl(
            self.sr_out, f"적 조합: {team}", r, font=FCH, color=ui.TEXT_DIM, pady=1
        )

        r = self._sec(self.sr_out, "라인 카운터", r)
        for i, (name, c) in enumerate(rep.counters[:5], 1):
            col = ui.GREEN if c.gd15 >= 200 else ui.WARN
            frame = self._row_frame(self.sr_out, r, pady=1)
            icon = self._keep_icon(champion_ctk(c.champion, 28))
            if icon:
                ctk.CTkLabel(frame, image=icon, text="").pack(
                    side="left", padx=(8, 6), pady=2
                )
            ctk.CTkLabel(
                frame,
                text=f"{i}. {name}  GD@15 {c.gd15_str}  {c.matches:,}게임",
                font=FM,
                text_color=col,
                anchor="w",
            ).pack(side="left", padx=(0, 8), pady=2)
            ui.tier_chip(frame, _counter_tier(c.gd15), font=FCH, width=26).pack(
                side="right", padx=(0, 8)
            )
            r += 1

        if matchup:
            r = self._sec(
                self.sr_out,
                f"라인전 — {rep.my_champ_ko} vs {rep.enemy_lane_ko}",
                r,
            )
            for t in matchup:
                r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)

        ban_lines = getattr(rep, "ban_lines", None) or []
        if ban_lines:
            r = self._sec(self.sr_out, "🚫 밴 추천 (내 챔프를 카운터하는 픽)", r)
            for bl in ban_lines[:5]:
                r = self._lbl(self.sr_out, f"·  {bl}", r, pady=2, color=ui.WARN)

        r = self._sec(self.sr_out, "조합 · 정글/서폿 개입", r)
        for t in rep.threats:
            r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)

        r = self._sec(self.sr_out, "중반 용 · 바론 · 한타", r)
        for t in rep.midgame:
            r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)

        r = self._sec(self.sr_out, "아이템 · 룬", r)
        if rep.runes_line:
            r = self._lbl(self.sr_out, f"룬  {rep.runes_line}", r)
        if rep.skill_line:
            r = self._lbl(self.sr_out, f"스킬  {rep.skill_line}", r)
        if rep.spells_line:
            r = self._lbl(self.sr_out, f"스펠  {rep.spells_line}", r)
        if rep.core_items:
            for i, item in enumerate(rep.core_items[:5], 1):
                frame = self._row_frame(self.sr_out, r, pady=1)
                ic = self._keep_icon(item_name_ctk(item, 32))
                if ic:
                    ctk.CTkLabel(frame, image=ic, text="").pack(
                        side="left", padx=(10, 8), pady=4
                    )
                item_lbl = ctk.CTkLabel(
                    frame, text=f"{i}코어  {item}", font=FU, anchor="w"
                )
                item_lbl.pack(side="left", padx=(0, 12), pady=4)
                self._attach_item_tooltip(item_lbl, item)
                r += 1
        else:
            r = self._lbl(
                self.sr_out,
                "코어: 내 챔피언 입력 시 표시",
                r,
                color=ui.TEXT_DIM,
            )
        if rep.situational:
            r = self._lbl(self.sr_out, "상황템 (적 조합)", r, font=FU, pady=(8, 2))
            for item, why in rep.situational:
                frame = self._row_frame(self.sr_out, r, pady=1)
                ic = self._keep_icon(item_name_ctk(item, 28))
                if ic:
                    ctk.CTkLabel(frame, image=ic, text="").pack(
                        side="left", padx=(10, 8), pady=3
                    )
                situ_lbl = ctk.CTkLabel(
                    frame, text=f"{item}  —  {why}", font=FB, anchor="w"
                )
                situ_lbl.pack(side="left", padx=(0, 12), pady=3)
                self._attach_item_tooltip(situ_lbl, item)
                r += 1

        r = self._sec(self.sr_out, "체크리스트", r)
        for t in rep.action_plan:
            r = self._lbl(self.sr_out, f"☐  {t}", r, pady=2)

        self.sr_status.configure(text=f"상세 완료 · {rep.enemy_lane_ko}")
        self.status.configure(text=f"상세 분석 · {rep.enemy_lane_ko}")
        key = self._ai_key()
        if key:
            self._maybe_ai(
                self.sr_out,
                lambda: self._ai_coach_comp(rep, matchup, key),
            )
        summary = []
        for i, (name, c) in enumerate(rep.counters[:4], 1):
            tip = (
                "초반 강함"
                if c.gd15 >= 300
                else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
            )
            summary.append(f"{i}. {name} — {tip} (GD@15 {c.gd15_str})")
        if matchup:
            summary.append("")
            summary.append("라인전: " + matchup[0])
            if len(matchup) > 1:
                summary.append("· " + matchup[1])
        ban_lines = getattr(rep, "ban_lines", None) or []
        if ban_lines:
            summary.append("")
            summary.append("🚫 밴 추천")
            summary += [f"· {b}" for b in ban_lines[:3]]
        if rep.threats:
            summary.append("")
            summary += [f"⚠ {t}" for t in rep.threats[:2]]
        if rep.core_items:
            summary.append("")
            summary.append("코어: " + " → ".join(rep.core_items[:5]))
        if rep.situational:
            summary.append(
                "상황템: " + ", ".join(f"{i} ({w})" for i, w in rep.situational[:3])
            )
        if rep.action_plan:
            summary.append("")
            summary += [f"☐ {t}" for t in rep.action_plan[:2]]
        self._push_summary(
            f"📋 {rep.my_champ_ko} vs {rep.enemy_lane_ko}  (패치 {rep.patch})",
            summary,
        )


    def _sr_quick_enter(self, _event=None) -> None:
        """적 라이너 Enter — 자동완성 목록이 열려 있으면 선택에 맡기고, 아니면 분석."""
        ac = getattr(self, "_sr_lane_ac", None)
        if ac is not None and ac.is_open():
            return
        self._run_sr_quick()

