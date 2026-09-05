"""ARAM 아수라장 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.aram_mayhem import (
    AugmentPick,
    AugmentTierTop,
    MayhemAdvice,
)
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FONT_UI, FS, FU
from lol_coach.gui.types import MixinBase
from lol_coach.static.augment_icons import augment_ctk, augment_pil, refresh_augment_sync
from lol_coach.static.icons import (
    cache_dir,
    champion_ctk,
    champion_pil,
    item_ctk,
    item_name_ctk,
    item_pil,
    item_pil_by_name,
    to_ctk,
)


def _tier_chip_label(pick: AugmentPick) -> str:
    """S/A/B가 전체 메타인지 지금 챔프 전용인지 칩에 적는다."""
    letter = (pick.tier or "B").strip().upper()[:1] or "B"
    if str(pick.reason or "").startswith("Blitz.gg"):
        return f"이 챔프 {letter}"
    return f"일반 {letter}"


class AramTabMixin(MixinBase):
    def _push_aram_history(self, fn: Any, *args: Any) -> None:
        """ARAM 브리핑 결과를 히스토리에 저장 (최근 20개). 메인 스레드에서만 호출."""
        self._aram_history.append((fn, args, {}))
        if len(self._aram_history) > 20:
            self._aram_history.pop(0)

    def _back_aram_history(self) -> None:
        """이전 ARAM 브리핑으로 복원."""
        hist = getattr(self, "_aram_history", [])
        if not hist:
            self._notify("이전 결과가 없습니다.", level="warn")
            return
        fn, args, _kw = hist.pop()
        try:
            fn(*args)
        except Exception as exc:
            self._notify(f"이전 결과 복원 실패: {exc}", level="error")

    def _live_fill_aram(self) -> None:
        """ARAM: 내 챔프 자동 입력 후 브리핑 실행."""
        if self._is_busy("aram_live"):
            return
        prepared = self._prepare_riot_for_live()
        if prepared is None:
            return
        client, game_name, tag_line = prepared
        self._busy_set(True, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")
        self.aram_status.configure(text="인게임 조회 중…")

        def bg() -> None:
            try:
                from lol_coach.analysis.live_fill import parse_live_game

                profile = client.resolve_player(game_name, tag_line)
                game = client.get_active_game(profile.puuid)
                if not game:
                    raise ValueError(
                        f"{profile.riot_id} 님은 지금 인게임이 아닙니다.\n\n"
                        "로딩~인게임 중에 다시 눌러 주세요. (밴픽 중엔 보통 안 됨)"
                    )
                self.dd.ensure_loaded()
                fill = parse_live_game(game, self.dd, my_puuid=profile.puuid)
                self.riot = client
                self.profile = profile
                self.after(0, lambda f=fill: self._apply_live_aram(f))
            except Exception as e:
                msg = str(e)

                def fail(m: str = msg) -> None:
                    from lol_coach.gui.errors import format_user_error

                    self.aram_status.configure(text="인게임 조회 실패")
                    self._notify(format_user_error(m), level="warn", ms=5000)
                    self._busy_set(
                        False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live"
                    )

                self.after(0, fail)

        threading.Thread(target=bg, daemon=True).start()

    def _apply_live_aram(self, fill, *, confirm_sr: bool = True) -> None:
        try:
            if (
                confirm_sr
                and fill.is_sr
                and not fill.is_aram
                and not messagebox.askyesno(
                    "모드 확인",
                    "지금 게임은 소환사 협곡으로 보입니다.\n"
                    f"그래도 내 챔프({fill.my_champ_ko})로 ARAM 브리핑을 할까요?\n\n"
                    "협곡 조합 분석은 「소환사의 협곡」탭 인게임 자동입력을 쓰세요.",
                )
            ):
                self._busy_set(
                    False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live"
                )
                self.aram_status.configure(text="취소됨")
                return

            ac = getattr(self, "_aram_ac", None)
            if ac is not None:
                ac.hide()
            # 라이브 클라이언트 자동입력 — 내 챔피언 + 적 챔피언 칸 채우기
            self.aram_champ_var.set(fill.my_champ_ko)
            self._aram_live_fill = fill
            enemy_kos = [ko for _k, ko in fill.enemies_by_role.values()] + [
                ko for _k, ko in fill.enemies_extra
            ]
            for idx, ev in enumerate(getattr(self, "aram_enemy_vars", [])):
                ev.set(enemy_kos[idx] if idx < len(enemy_kos) else "")
            self.aram_status.configure(text=f"인게임 · {fill.my_champ_ko} 브리핑 중…")
            self._busy_set(
                False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live"
            )
            self._start_game_end_watcher()
            self._run_aram()
        except Exception as e:
            self._notify_error(e)
            self._busy_set(
                False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live"
            )

    def _set_aram_inputs_expanded(self, expanded: bool) -> None:
        """입력 패널 접기/펼치기 — 브리핑·AI 코칭 영역 최대화 (협곡과 동일 UX)."""
        self._aram_inputs_expanded = expanded
        host = getattr(self, "_aram_inputs_host", None)
        btn = getattr(self, "_aram_fold_btn", None)
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

    def _toggle_aram_inputs(self) -> None:
        self._set_aram_inputs_expanded(not getattr(self, "_aram_inputs_expanded", True))

    def _collapse_aram_inputs_for_results(self) -> None:
        """브리핑 결과가 나오면 입력란 접어 상세 코칭 영역 확보."""
        try:
            self._set_aram_inputs_expanded(False)
        except Exception:
            pass

    def _build_aram(self) -> None:
        # 접기 바 (항상 표시) + 입력 호스트 + 결과(최대 공간) — 협곡 탭과 동일 패턴
        bar = ctk.CTkFrame(self.t_aram, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))
        self._aram_fold_btn = ctk.CTkButton(
            bar,
            text="▲ 입력 접기 (결과 크게)",
            height=26,
            width=160,
            font=FCH,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._toggle_aram_inputs,
        )
        self._aram_fold_btn.pack(side="left")
        ctk.CTkLabel(
            bar,
            text="브리핑 후 자동으로 접혀 AI·상세 코칭이 크게 보입니다",
            font=FCH,
            text_color=ui.TEXT_MUTE,
        ).pack(side="left", padx=8)

        self._aram_inputs_host = ctk.CTkFrame(self.t_aram, fg_color="transparent")
        self._aram_inputs_host.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self._aram_inputs_expanded = True
        self._aram_inputs_host.grid_columnconfigure(0, weight=1)

        form = ctk.CTkFrame(
            self._aram_inputs_host,
            corner_radius=ui.ROW_RADIUS,
            border_width=ui.ROW_BORDER,
            border_color=ui.BORDER,
            fg_color=ui.ROW,
        )
        form.grid(row=0, column=0, sticky="ew", padx=6, pady=(2, 1))
        form.grid_columnconfigure(1, weight=1)

        self.aram_champ_var = tk.StringVar()
        aram_entry = self._entry_row(
            form, 0, "내 챔피언*", self.aram_champ_var, "예: 리신, 미스 포츈, 아리"
        )

        # 자동완성 목록: form 안 고정 슬롯 (Toplevel 안 씀 → CTk 크래시 방지)
        from lol_coach.gui.champ_autocomplete import ChampionAutocomplete

        self._aram_ac = ChampionAutocomplete(
            self,
            aram_entry,
            self.aram_champ_var,
            self.dd,
            list_parent=form,
            keep_icon=self._keep_icon,
            limit=8,
            icon_size=32,
        )
        # row1: 제안 목록 (기본 숨김, 입력 시 grid)
        self._aram_ac.panel.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 4))
        self._aram_ac.panel.grid_remove()

        aram_entry.bind("<Return>", self._aram_enter, add="+")
        aram_entry.bind("<KP_Enter>", self._aram_enter, add="+")

        # 적 챔피언 입력 (선택) — ARAM은 적 전원이 보이므로 5명 입력 시
        # 조합 위협 + 적응형 빌드(4~6슬롯 분기)가 켜진다. 비워도 브리핑 가능.
        enemy_row = ctk.CTkFrame(form, fg_color="transparent")
        enemy_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 0))
        enemy_row.grid_columnconfigure((1, 3, 5, 7, 9), weight=1, uniform="enemy")
        ctk.CTkLabel(enemy_row, text="적 챔피언 (선택)", font=FCH, anchor="w").grid(
            row=0, column=0, columnspan=10, sticky="w", pady=(0, 2)
        )
        self.aram_enemy_vars: list[tk.StringVar] = []
        for ei in range(5):
            var = tk.StringVar()
            self.aram_enemy_vars.append(var)
            col_label = ei * 2
            col_entry = ei * 2 + 1
            ctk.CTkLabel(enemy_row, text=f"적{ei + 1}", font=FB, width=28, anchor="e").grid(
                row=1, column=col_label, sticky="e", padx=(4 if ei == 0 else 6, 2), pady=2
            )
            ent = ctk.CTkEntry(
                enemy_row,
                textvariable=var,
                placeholder_text="챔피언",
                font=FM,
                height=26,
                width=90,
            )
            ent.grid(row=1, column=col_entry, sticky="ew", padx=(0, 4), pady=2)
            ent.bind("<Return>", self._aram_enter, add="+")
            ent.bind("<KP_Enter>", self._aram_enter, add="+")

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 6))
        self.aram_live_btn = ctk.CTkButton(
            btn_row,
            text="🎮 실행 중인 게임 자동 검색",
            height=32,
            font=FU,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._live_fill_aram,
        )
        self.aram_live_btn.pack(side="left", padx=(0, 6))
        self.aram_btn = ctk.CTkButton(
            btn_row,
            text="아수라장 브리핑",
            height=34,
            font=FU,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._run_aram,
        )
        self.aram_btn.pack(side="left")
        self.aram_lcu_btn = ctk.CTkButton(
            btn_row,
            text="🎯 밴픽 (LCU)",
            height=32,
            width=104,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._lcu_fill_aram,
        )
        self.aram_lcu_btn.pack(side="left", padx=(6, 0))
        ctk.CTkButton(
            btn_row,
            text="📜 이전",
            width=58,
            height=32,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._back_aram_history,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btn_row,
            text="🧹 초기화",
            width=72,
            height=32,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._reset_aram,
        ).pack(side="left", padx=(8, 0))
        self.aram_status = ctk.CTkLabel(
            btn_row,
            text="인게임 자동 = 내 챔프 채우고 바로 브리핑 · 수동 입력도 가능",
            font=FM,
            text_color=ui.TEXT_DIM,
        )
        self.aram_status.pack(side="left", padx=10)

        self.aram_out = ctk.CTkScrollableFrame(
            self.t_aram,
            corner_radius=ui.CARD_RADIUS,
            label_text="아수라장 브리핑 · AI 코칭",
            fg_color=ui.PANEL,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        self.aram_out.grid(row=2, column=0, sticky="nsew", padx=6, pady=(2, 6))
        self.t_aram.grid_rowconfigure(0, weight=0)
        self.t_aram.grid_rowconfigure(1, weight=0)
        self.t_aram.grid_rowconfigure(2, weight=1)
        self.aram_out.grid_columnconfigure(0, weight=1)
        self._render_aram_empty_state()

    # ARAM 인기 챔피언 표시용 고정 순서 (알파벳 — Data Dragon 키)
    _ARAM_QUICK_KEYS: tuple[str, ...] = (
        "Ahri",
        "Lux",
        "Jinx",
        "Ezreal",
        "Yasuo",
        "Zed",
        "MissFortune",
        "KaiSa",
        "Veigar",
        "Brand",
        "Sona",
        "Lulu",
        "Garen",
        "Darius",
        "Teemo",
        "Shaco",
        "Pyke",
        "Khazix",
        "Ashe",
        "Caitlyn",
        "Morgana",
        "Blitzcrank",
        "Thresh",
        "Leona",
    )

    def _aram_quick_pick(self, champ_ko: str) -> None:
        """빈 결과 영역의 챔피언 타일 클릭 → 입력 채우고 브리핑 실행."""
        self.aram_champ_var.set(champ_ko)
        self._run_aram()

    def _aram_freshness_banner(self, adv: MayhemAdvice) -> str:
        """증강 카탈로그 데이터 신선도 메시지. 14일 초과 시 경고."""
        src = adv.source
        if src is None:
            return ""
        updated = src.updated_at or ""
        if not updated:
            return ""
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).days
        except (ValueError, TypeError):
            return ""
        if age < 0:
            return ""
        patch = src.patch or adv.patch or ""
        if age >= 14:
            return f"⚠ 증강 데이터 {age}일 경과 (패치 {patch}) — 최신 패치와 다를 수 있음"
        if age >= 7:
            return f"ℹ 증강 데이터 {age}일 경과 (패치 {patch})"
        return ""

    def _back_to_aram_pick(self) -> None:
        """브리핑 결과 → 챔피언 선택 그리드로 복귀 (챔프 입력은 유지)."""
        self._render_aram_empty_state()
        self.aram_status.configure(text="챔피언을 골라 빠르게 브리핑")

    def _render_aram_empty_state(self) -> None:
        """빈 결과 영역 — blitz.gg 스타일 챔피언 그리드 (클릭 시 브리핑)."""
        self._aram_rendered = False
        self._clear(self.aram_out)

        # 헤더
        head = ctk.CTkFrame(self.aram_out, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(14, 4))
        ctk.CTkLabel(
            head,
            text="🎯 챔피언을 골라 빠르게 브리핑",
            font=FS,
            anchor="w",
            text_color=ui.TEXT_BRIGHT,
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text="·  클릭 시 증강 우선순위 + ARAM 빌드 즉시 표시",
            font=FU,
            anchor="w",
            text_color=ui.TEXT_DIM,
        ).pack(side="left", padx=(6, 0))

        # 챔피언 타일 그리드 (6열)
        grid = ctk.CTkFrame(self.aram_out, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 10))
        cols = 6
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1, uniform="champ")

        from lol_coach.static.icons import champion_ctk

        for i, key in enumerate(self._ARAM_QUICK_KEYS):
            row = i // cols
            col = i % cols
            resolved = self.dd.resolve_champion(key)
            if not resolved:
                continue
            ko = resolved["name"]
            tile = ctk.CTkFrame(
                grid,
                fg_color=ui.ROW,
                corner_radius=ui.ROW_RADIUS,
                border_width=ui.ROW_BORDER,
                border_color=ui.BORDER,
                cursor="hand2",
            )
            tile.grid(row=row, column=col, sticky="ew", padx=4, pady=4)
            tile.grid_propagate(False)
            tile.configure(height=64)

            icon = self._keep_icon(champion_ctk(key, 36))
            if icon:
                ctk.CTkLabel(tile, image=icon, text="").pack(side="left", padx=(8, 6), pady=6)
            ctk.CTkLabel(
                tile,
                text=ko,
                font=FU,
                anchor="w",
                text_color=ui.TEXT,
            ).pack(side="left", padx=(0, 8), pady=6)

            # 호버/클릭 바인딩
            def _on_enter(_e: Any, t=tile) -> None:
                t.configure(fg_color=ui.ROW_HOVER, border_color=ui.GOLD)

            def _on_leave(_e: Any, t=tile) -> None:
                t.configure(fg_color=ui.ROW, border_color=ui.BORDER)

            def _on_click(_e: Any, name=ko) -> None:
                self._aram_quick_pick(name)

            tile.bind("<Enter>", _on_enter)
            tile.bind("<Leave>", _on_leave)
            tile.bind("<Button-1>", _on_click)
            for child in tile.winfo_children():
                child.bind("<Enter>", _on_enter)
                child.bind("<Leave>", _on_leave)
                child.bind("<Button-1>", _on_click)

        # 하단 안내
        self._lbl(
            self.aram_out,
            "인게임 자동 검색 버튼으로 밴픽에서 바로 불러올 수도 있습니다.",
            2,
            color=ui.TEXT_DIM,
            pady=(2, 14),
        )

        # 빈 상태 챔피언 타일 아이콘 백그라운드 채우기 + 재렌더
        self._schedule_aram_empty_icon_fill()

    def _schedule_aram_empty_icon_fill(self) -> None:
        """백그라운드 스레드에서 빈 상태 챔피언 타일 아이콘을 캐시한 뒤 한 번 다시 그린다."""
        cd = cache_dir()
        missing = [k for k in self._ARAM_QUICK_KEYS if not (cd / f"c_{k}_36.png").exists()]
        if not missing:
            return
        sig = ("empty", tuple(missing))
        if getattr(self, "_aram_empty_icon_sig", None) == sig:
            return
        self._aram_empty_icon_sig = sig

        def on_done() -> None:
            # 빈 상태가 유지 중이면 (브리핑 결과로 교체되지 않았으면) 재렌더
            if not getattr(self, "_aram_rendered", False):
                self._render_aram_empty_state()

        def _bg() -> None:
            from lol_coach.static.icons import champion_pil as _cpil

            for k in missing:
                _cpil(k, 36)  # 백그라운드 다운로드 + 캐시
            self.after(0, on_done)

        self._spawn_thread(_bg)

    def _lcu_fill_aram(self) -> None:
        """LCU: 밴픽 중 내 챔피언 자동 입력."""
        if self._is_busy("aram_lcu"):
            return
        self.aram_status.configure(text="클라이언트 밴픽 조회 중…")

        def bg() -> None:
            try:
                from lol_coach.lcu import LCUClient

                lcu = LCUClient()
                info = lcu.champ_select()
                self.dd.ensure_loaded()
                self.after(0, lambda: self._apply_lcu_aram(info, force=True))
                # 밴픽 동안 리롤/픽 변화 추적
                self.after(0, self._start_aram_champ_watch)
            except Exception as e:
                msg = str(e)

                def fail(m: str = msg) -> None:
                    from lol_coach.gui.errors import format_user_error

                    self.aram_status.configure(text="밴픽 조회 실패")
                    self._notify(
                        format_user_error(m) + " · 밴픽 중에 다시 시도",
                        level="warn",
                        ms=5000,
                    )

                self.after(0, fail)

        threading.Thread(target=bg, daemon=True).start()

    def _apply_lcu_aram(self, info: Any, *, force: bool = False) -> None:
        if not info.my_champion_id:
            self.aram_status.configure(text="아직 챔피언을 고르지 않았습니다")
            return
        # 챔피언이 바뀌었을 때만 브리핑 재실행 (리롤 dedupe)
        sig = (info.my_champion_id,)
        if not force and sig == self._aram_lcu_sig:
            return
        self._aram_lcu_sig: tuple = sig
        ko = self.dd.champion_name(info.my_champion_id)
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            ac.hide()
        self.aram_champ_var.set(ko)
        self.aram_status.configure(text=f"밴픽 입력 완료 · {ko} — 브리핑 생성 중…")
        self._run_aram()

    def _start_aram_champ_watch(self) -> None:
        """ARAM 밴픽 폴당 — 리롤/픽 변화 시 브리핑 갱신."""
        self._start_champ_watch(
            apply_fn=self._apply_lcu_aram,
            status_label=self.aram_status,
            watching_text="밴픽 추적 중 — 리롤하면 자동 갱신",
        )

    def _aram_enter(self, _event=None):
        """제안 목록이 열려 있으면 선택은 autocomplete가 처리, 아니면 분석."""
        ac = getattr(self, "_aram_ac", None)
        if ac is not None and ac.is_open():
            return
        self._run_aram()

    def _run_aram(self) -> None:
        if self._is_busy("aram_brief"):
            return
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            ac.hide()
        try:
            key, ko = self._resolve(self.aram_champ_var.get())
        except ValueError as e:
            self._notify(str(e), level="warn")
            return

        # 선택 후 필드에 정식 한글 이름 표시
        self.aram_champ_var.set(ko)
        self._busy_set(True, self.aram_btn, "아수라장 브리핑", key="aram_brief")
        self.aram_status.configure(text=f"{ko} 분석 중…")

        def work() -> None:
            try:
                adv = self.mayhem.advise(key)
                # 조합 위협 + 적응형 빌드(4~6슬롯 분기): 인게임 자동검색 또는
                # 수동으로 입력한 적 챔피언이 있으면 태그 기반 분석을 돌린다.
                try:
                    from lol_coach.analysis.aram_comp import analyze_aram_comp

                    fill = getattr(self, "_aram_live_fill", None)
                    enemies: list[tuple[str, str]] = []
                    allies: list[tuple[str, str]] = []
                    my_key = key
                    if fill is not None:
                        enemies = list(fill.enemies_by_role.values()) + list(fill.enemies_extra)
                        allies = list(fill.allies)
                        my_key = fill.my_champ_key or key
                    # 수동 입력한 적 챔피언 보충 (인게임과 겹치면 무시)
                    existing_enemy_keys = {k.lower() for k, _ in enemies}
                    for ev in getattr(self, "aram_enemy_vars", []):
                        raw = ev.get().strip()
                        if not raw:
                            continue
                        try:
                            ek, eko = self._resolve(raw)
                        except ValueError:
                            continue
                        if ek.lower() in existing_enemy_keys:
                            continue
                        existing_enemy_keys.add(ek.lower())
                        enemies.append((ek, eko))
                    if enemies:
                        rep = analyze_aram_comp(
                            self.dd,
                            allies=allies,
                            enemies=enemies,
                            my_key=my_key,
                        )
                        adv.comp_lines = rep.lines
                        # 적 조합 태그로 빌드 후반(4~6슬롯) 분기
                        try:
                            c = self.dd.resolve_champion(adv.champ_key or adv.champ_ko)
                            my_tags = set(c.get("tags") or []) if c else set()
                            new_slots, note = self.mayhem._adaptive_late_slots(
                                adv.core_slots, my_tags, rep.enemy_tags
                            )
                            if note:
                                adv.core_slots = new_slots
                                adv.core_item_ids = [self.dd.item_id_for_name(s) for s in new_slots]
                                adv.adaptive_build_note = note
                        except Exception:
                            pass
                except Exception:
                    pass
                champion_pil(adv.champ_key or adv.champ_ko, 52)
                for index, item in enumerate(adv.core_slots):
                    item_id = adv.core_item_ids[index] if index < len(adv.core_item_ids) else None
                    if item_id is not None:
                        item_pil(item_id, 38)
                    else:
                        item_pil_by_name(item, 38)
                # 캐시 프리페치는 메인 스레드가 아닌 워커에서만 네트워크 가능.
                # 증강 아이콘은 후보 URL 다운로드 실패 시 12s 타임아웃이 걸리므로
                # 순차로 돌면 하나가 브리핑 전체를 지연시킨다 — 6워커 병렬 조회.
                aug_jobs: list[tuple[str, int]] = [(p.name_en, 40) for p in adv.top_augments]
                aug_jobs += [(p.name_en, 36) for p in adv.avoid_augments]
                for picks in (
                    adv.fixed_top.silver,
                    adv.fixed_top.gold,
                    adv.fixed_top.prismatic,
                ):
                    aug_jobs += [(p.name_en, 34) for p in picks]

                def _fetch_aug(job: tuple[str, int]) -> None:
                    try:
                        augment_pil(job[0], job[1])
                    except Exception:
                        pass

                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=6) as pool:
                    for _ in pool.map(_fetch_aug, aug_jobs):
                        pass

                def _done() -> None:
                    self._push_aram_history(self._render_aram, adv)
                    self._render_aram(adv)
                    # 리롤 어드바이저 토스트 — 표본·데이터 부족이면 침묵
                    reroll = getattr(adv, "reroll", None)
                    if reroll is not None and reroll.actions:
                        level = "warn" if reroll.tier == "B" else "ok"
                        self._notify(reroll.actions[0], level=level, ms=5000)

                self.after(0, _done)
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                msg = format_user_error(e)
                self.after(0, lambda: self._aram_err(msg))
            finally:
                self.after(
                    0,
                    lambda: self._busy_set(
                        False, self.aram_btn, "아수라장 브리핑", key="aram_brief"
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _aram_err(self, msg: str) -> None:
        self._aram_rendered = True
        self._clear(self.aram_out)
        self._lbl(self.aram_out, f"오류: {msg}", 0, color=ui.RED_SOFT)
        self.aram_status.configure(text="실패")
        self._notify(msg, level="error", ms=4800)

    def _reset_aram(self) -> None:
        """ARAM 탭 입력·결과 전체 초기화."""
        self._stop_champ_watch()
        self.aram_champ_var.set("")
        for ev in getattr(self, "aram_enemy_vars", []):
            ev.set("")
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            try:
                ac.hide()
            except Exception:
                pass
        self._render_aram_empty_state()
        self.aram_status.configure(text="초기화됨 — 챔피언을 입력하세요")
        self.status.configure(text="ARAM 탭 초기화")
        try:
            self._set_aram_inputs_expanded(True)
        except Exception:
            pass
        self._aram_live_fill = None

    def _ensure_aug_lcu(self) -> Any | None:
        """증강 아이콘 LCU 에셋 조회용 클라이언트 (클라이언트 실행 중일 때만)."""
        lcu = getattr(self, "_aug_lcu", None)
        if lcu is not None:
            return lcu
        try:
            from lol_coach.lcu import LCUClient

            if LCUClient.is_client_running():
                lcu = LCUClient()
                self._aug_lcu: Any = lcu
        except Exception:
            self._aug_lcu = None
        return lcu

    def _augment_icon(self, pick: Any, size: int) -> Any:
        """증강 아이콘 — 카탈로그 우선, 라이브 전용 증강은 LCU 에셋으로 폴백."""
        ic = augment_ctk(pick.name_en, size)
        if ic:
            return ic
        raw_id = str(getattr(pick.record, "id", "") or "")
        if not raw_id.startswith("live:"):
            return None
        aid = raw_id.removeprefix("live:")
        if not aid.isdigit():
            return None
        try:
            import io

            from PIL import Image as PILImage

            from lol_coach.static import mayhem_augments as ma

            meta = ma.augment_meta(int(aid))
            if meta is None:
                return None
            raw = ma.icon_bytes_for(meta, self._ensure_aug_lcu())
            if not raw:
                return None
            return to_ctk(PILImage.open(io.BytesIO(raw)), size)
        except Exception:
            return None

    def _render_fixed_augment_board(
        self,
        parent: Any,
        row: int,
        fixed_top: AugmentTierTop,
        *,
        champ_ko: str = "",
        augment_source: str = "",
    ) -> int:
        title = f"1. {champ_ko} 맞춤 TOP 3" if champ_ko else "1. 희귀도별 TOP 3"
        row = self._sec(parent, title, row)
        board = ctk.CTkFrame(parent, fg_color="transparent")
        board.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 8))
        columns = (
            ("실버 TOP 3", fixed_top.silver, ui.TEXT_DIM),
            ("골드 TOP 3", fixed_top.gold, ui.GOLD),
            ("프리즘 TOP 3", fixed_top.prismatic, ui.BLUE_SOFT),
        )
        for column_index, (title, picks, color) in enumerate(columns):
            board.grid_columnconfigure(column_index, weight=1, uniform="rarity")
            column = ctk.CTkFrame(
                board,
                fg_color=ui.CARD,
                corner_radius=ui.CARD_RADIUS,
                border_width=ui.CARD_BORDER,
                border_color=ui.BORDER,
            )
            column.grid(
                row=0,
                column=column_index,
                sticky="nsew",
                padx=(0 if column_index == 0 else 4, 0 if column_index == 2 else 4),
            )
            ctk.CTkLabel(
                column,
                text=title,
                font=FS,
                text_color=color,
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 4))
            if not picks:
                ctk.CTkLabel(
                    column,
                    text="추천 데이터 없음",
                    font=FB,
                    text_color=ui.TEXT_DIM,
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(4, 8))
                continue
            for rank, pick in enumerate(picks, 1):
                card = ctk.CTkFrame(
                    column,
                    fg_color=ui.ROW,
                    corner_radius=ui.ROW_RADIUS,
                    border_width=ui.CARD_BORDER,
                    border_color=ui.BORDER,
                )
                card.pack(fill="x", padx=6, pady=(0, 4 if rank < 3 else 8))
                icon = self._keep_icon(self._augment_icon(pick, 32))
                if icon:
                    ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(8, 6), pady=4)
                else:
                    self._augment_missing_card(card, pick, size=32).pack(
                        side="left", padx=(8, 6), pady=4
                    )
                ctk.CTkLabel(
                    card,
                    text=(f"{rank}위  {pick.name_ko}\n{pick.desc}"),
                    font=FB,
                    text_color=ui.TEXT_BRIGHT if rank == 1 else ui.TEXT,
                    anchor="w",
                    justify="left",
                    wraplength=225,
                ).pack(fill="x", expand=True, side="left", padx=(0, 8), pady=4)
        if augment_source:
            ctk.CTkLabel(
                board,
                text=f"출처 · {augment_source}",
                font=FCH,
                text_color=ui.TEXT_MUTE,
                anchor="w",
            ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(2, 0))
        return row + 1

    def _render_aram_meta_augments(self, adv: MayhemAdvice, r: int) -> int:
        """메타 증강 추천 섹션 (TOP 추천 + 회피 + 시너지 + 아이콘 비동기 채움).

        브리핑 순서: 아이템 빌드(2) → 메타 증강 추천(3).
        """
        r = self._sec(self.aram_out, "3. 메타 증강 추천", r)
        r = self._lbl(
            self.aram_out,
            "칩 「일반 S」는 전체 메타 등급, 「이 챔프 S」는 지금 고른 챔피언 전용 순위입니다.",
            r,
            color=ui.TEXT_DIM,
            font=FM,
        )
        # 증강 시너지 라인 — archetype_prefer/avoid 기반
        synergy_lines = getattr(adv, "synergy_lines", None) or []
        for sl in synergy_lines:
            r = self._lbl(
                self.aram_out,
                f"✦ {sl}",
                r,
                font=FM,
                color=ui.BLUE_SOFT,
            )
        # 챔피언 메타 증강 TOP 추천 (제시 입력 없이 blitz 순위 기반)
        for i, pick in enumerate(adv.top_augments, 1):
            frame = self._row_frame(self.aram_out, r, padx=10, pady=2)
            aicon = self._keep_icon(self._augment_icon(pick, 32))
            if aicon:
                ctk.CTkLabel(frame, image=aicon, text="").pack(side="left", padx=(8, 6), pady=4)
            else:
                self._augment_missing_card(frame, pick, size=32).pack(
                    side="left", padx=(8, 6), pady=4
                )
            ctk.CTkLabel(
                frame,
                text=f"{i}. {pick.name_ko}  —  {pick.record.description_ko}\n({pick.reason})",
                font=FB,
                text_color=ui.TEXT,
                anchor="w",
                justify="left",
            ).pack(side="left", padx=(0, 8), pady=4)
            r += 1

        if adv.avoid_augments:
            for pick in adv.avoid_augments:
                frame = self._row_frame(self.aram_out, r, padx=10, pady=2)
                aicon = self._keep_icon(self._augment_icon(pick, 32))
                if aicon:
                    ctk.CTkLabel(frame, image=aicon, text="").pack(side="left", padx=(8, 6), pady=4)
                else:
                    self._augment_missing_card(frame, pick, size=32).pack(
                        side="left", padx=(8, 6), pady=4
                    )
                ctk.CTkLabel(
                    frame,
                    text=f"✕ {pick.name_ko}  —  {pick.record.description_ko}\n({pick.reason})",
                    font=FB,
                    text_color=ui.RED_SOFT,
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 8), pady=4)
                r += 1

        self._aram_render_gen: int = getattr(self, "_aram_render_gen", 0) + 1
        self._schedule_aram_icon_fill(adv, self._aram_render_gen)
        return r

    def _render_aram_build_grid(
        self,
        parent: Any,
        row: int,
        adv: MayhemAdvice,
    ) -> int:
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 4))
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1, uniform="build")
        slots = list(adv.core_slots[:6])
        while len(slots) < 6:
            slots.append("상황 아이템 선택")
        source = "Blitz 추천 순서" if adv.build_url else "역할 기반 안전 폴백"
        for index, item in enumerate(slots):
            card = ctk.CTkFrame(
                grid,
                fg_color=ui.ROW,
                corner_radius=ui.ROW_RADIUS,
                border_width=ui.CARD_BORDER,
                border_color=ui.BORDER,
            )
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=(0 if index % 3 == 0 else 3, 0 if index % 3 == 2 else 3),
                pady=(0 if index < 3 else 3, 3 if index < 3 else 0),
            )
            item_id = adv.core_item_ids[index] if index < len(adv.core_item_ids) else None
            icon = self._keep_icon(
                item_ctk(item_id, 36) if item_id is not None else item_name_ctk(item, 36)
            )
            if icon:
                ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(8, 6), pady=6)
            else:
                fallback = ctk.CTkFrame(
                    card,
                    width=36,
                    height=36,
                    corner_radius=ui.ROW_RADIUS,
                    fg_color=ui.GOLD,
                )
                fallback.pack(side="left", padx=(8, 6), pady=6)
                fallback.pack_propagate(False)
                ctk.CTkLabel(
                    fallback,
                    text=(item or "?")[:1],
                    font=FCH,
                    text_color=ui.ON_GOLD,
                ).place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                card,
                text=f"{index + 1}슬롯\n{item}\n{source}",
                font=FU if index < 3 else FB,
                text_color=ui.TEXT_BRIGHT,
                anchor="w",
                justify="left",
                wraplength=240,
            ).pack(fill="x", expand=True, side="left", padx=(0, 8), pady=6)
        return row + 1

    def _schedule_aram_icon_fill(self, adv: MayhemAdvice, gen: int) -> None:
        """메인 스레드에선 아이콘을 못 받으니, 없는 것만 받은 뒤 한 번 다시 그린다."""
        names: list[str] = []
        for pick in (*adv.top_augments, *adv.avoid_augments):
            names.append(pick.name_en)
        if adv.augment_validation is not None:
            names.extend(rec.name_en for rec in adv.augment_validation.valid)
        for group in (adv.fixed_top.silver, adv.fixed_top.gold, adv.fixed_top.prismatic):
            names.extend(pick.name_en for pick in group)
        uniq = list(dict.fromkeys(n for n in names if n))
        missing = [n for n in uniq if augment_pil(n, 40) is None]
        if not missing:
            return
        sig = (adv.champ_key, tuple(missing))
        if getattr(self, "_aram_icon_sig", None) == sig:
            return
        self._aram_icon_sig = sig

        def work() -> None:
            from concurrent.futures import ThreadPoolExecutor

            def _refresh(name: str) -> None:
                try:
                    refresh_augment_sync(name)
                except Exception:
                    pass

            # 누락 아이콘 병렬 보강 — 실패 후보는 idx에 이어받아 저장되므로
            # 다음 브리핑에서 남은 후보를 시도한다
            with ThreadPoolExecutor(max_workers=4) as pool:
                for _ in pool.map(_refresh, missing):
                    pass
            try:
                # 다운로드 중 다른 브리핑이 그려졌으면 옛 결과로 덮지 않는다
                self.after(
                    0,
                    lambda: self._render_aram(adv)
                    if getattr(self, "_aram_render_gen", 0) == gen
                    else None,
                )
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _render_aram(self, adv: MayhemAdvice) -> None:
        self._aram_rendered = True
        self._clear(self.aram_out)
        r = 0

        head = self._row_frame(self.aram_out, r, padx=10, pady=(6, 4))
        ck = adv.champ_key or adv.champ_ko
        cicon = self._keep_icon(champion_ctk(ck, 36))
        if cicon:
            ctk.CTkLabel(head, image=cicon, text="").pack(side="left", padx=(8, 8), pady=4)
        ctk.CTkLabel(
            head,
            text=f"{adv.champ_ko}  ·  ARAM 아수라장 · 패치 {adv.patch}",
            font=FM,
            anchor="w",
            justify="left",
            text_color=ui.TEXT_BRIGHT,
        ).pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkButton(
            head,
            text="← 챔피언 선택",
            width=96,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._back_to_aram_pick,
        ).pack(side="right", padx=(0, 6), pady=4)
        r += 1

        # 증강 카탈로그 신선도 배너 (정직한 출처)
        freshness = self._aram_freshness_banner(adv)
        if freshness:
            r = self._lbl(
                self.aram_out,
                freshness,
                r,
                font=FM,
                color=ui.WARN,
                pady=2,
            )

        r = self._lbl(
            self.aram_out,
            "※ 아수라장/칼바람은 룬 선택 없음 · 증강 + 아이템만 본다.",
            r,
            font=FM,
            color=ui.TEXT_DIM,
        )

        # 리롤 어드바이저 칩 — 표본·데이터 부족이면 표시 안 함 (침묵 원칙)
        reroll = getattr(adv, "reroll", None)
        if reroll is not None and reroll.actions:
            chip_color = ui.RED_SOFT if reroll.tier == "B" else ui.GREEN
            r = self._lbl(
                self.aram_out,
                "🎲 " + " ".join(reroll.actions),
                r,
                font=FM,
                color=chip_color,
            )

        r = self._render_fixed_augment_board(
            self.aram_out,
            r,
            adv.fixed_top,
            champ_ko=adv.champ_ko,
            augment_source=getattr(adv, "augment_source", ""),
        )

        r = self._render_aram_build_grid(self.aram_out, r, adv)
        # 적응형 빌드 분기 안내 (적 조합 기반 4~6슬롯 교체 시)
        adaptive_note = getattr(adv, "adaptive_build_note", "") or ""
        if adaptive_note:
            r = self._lbl(
                self.aram_out,
                f"🔧 상황 빌드 — {adaptive_note}",
                r,
                font=FM,
                color=ui.WARN,
            )

        r = self._render_aram_meta_augments(adv, r)

        key = self._ai_key()
        if key:
            ai_host = ctk.CTkFrame(self.aram_out, fg_color="transparent")
            ai_host.grid(row=r, column=0, sticky="ew")
            ai_host.grid_columnconfigure(0, weight=1)
            self._maybe_ai(
                ai_host,
                lambda on_delta=None: self._ai_coach_aram(adv, key, on_delta=on_delta),
            )
            r += 1

        # 조합 위협·시너지 (인게임 자동검색 시 채워짐)
        comp_lines = getattr(adv, "comp_lines", None) or []
        if comp_lines:
            r = self._sec(self.aram_out, "4. 조합 위협 · 시너지", r)
            for cl in comp_lines:
                kind = getattr(cl, "kind", "note")
                text = getattr(cl, "text", str(cl))
                col = (
                    ui.RED_SOFT
                    if kind == "threat"
                    else (ui.GREEN if kind == "synergy" else ui.TEXT_DIM)
                )
                prefix = "⚠ " if kind == "threat" else ("✦ " if kind == "synergy" else "· ")
                r = self._lbl(self.aram_out, f"{prefix}{text}", r, pady=2, color=col)
            tip_sec = "5. 실전 팁"
        else:
            tip_sec = "4. 실전 팁"

        r = self._sec(self.aram_out, tip_sec, r)
        for t in adv.play_tips:
            r = self._lbl(self.aram_out, f"·  {t}", r, pady=3)

        meta_lines: list[str] = []
        if adv.source:
            src = adv.source
            if src.patch:
                meta_lines.append(f"패치 {src.patch}")
            if src.updated_at:
                meta_lines.append(f"갱신 {src.updated_at}")
            if src.primary:
                meta_lines.append(f"출처 {src.primary}")
        if not meta_lines:
            meta_lines.append(f"출처  {adv.source_url}")
        if adv.build_url:
            meta_lines.append(f"빌드 출처  {adv.build_url}")
        r = self._lbl(
            self.aram_out,
            "  ·  ".join(meta_lines),
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=(12, 8),
        )
        self.aram_status.configure(text=f"완료 · {adv.champ_ko}")
        self.status.configure(text=f"아수라장 · {adv.champ_ko}")
        # 결과 영역 확보 (협곡 탭과 동일) — 테스트 더블에는 없을 수 있음
        try:
            self._collapse_aram_inputs_for_results()
        except Exception:
            pass
        summary = []
        for label, picks in (
            ("실버", adv.fixed_top.silver),
            ("골드", adv.fixed_top.gold),
            ("프리즘", adv.fixed_top.prismatic),
        ):
            summary.append(
                f"{label}: "
                + " · ".join(f"{i}위 {pick.name_ko}" for i, pick in enumerate(picks, 1))
            )
        if adv.avoid_augments:
            summary.append("")
            summary.append("✕ 피할 것: " + ", ".join(p.name_ko for p in adv.avoid_augments[:3]))
        if adv.core_slots:
            summary.append("")
            summary.append("6슬롯: " + " → ".join(adv.core_slots[:6]))
        if adv.play_tips:
            summary.append("")
            summary += [f"· {t}" for t in adv.play_tips[:2]]
        comp_lines = getattr(adv, "comp_lines", None) or []
        if comp_lines:
            summary.append("")
            summary.append("조합")
            for cl in comp_lines[:3]:
                text = getattr(cl, "text", str(cl))
                summary.append(f"· {text}")
        self._push_summary(f"🔮 {adv.champ_ko} 아수라장  (패치 {adv.patch})", summary)

    def _augment_missing_card(self, parent: Any, pick: AugmentPick, size: int = 40) -> ctk.CTkFrame:
        """아이콘이 없을 때 명시적 이름+등급 배지."""
        rarity = pick.rarity or "gold"
        color = {
            "prismatic": ui.PURPLE,
            "gold": ui.GOLD,
            "silver": ui.TEXT_DIM,
        }.get(rarity, ui.GOLD)
        card = ctk.CTkFrame(
            parent,
            width=size,
            height=size,
            corner_radius=6,
            fg_color=color,
        )
        card.pack_propagate(False)
        label = (pick.name_ko or pick.name_en or "?")[:1]
        ctk.CTkLabel(
            card,
            text=label,
            font=(FONT_UI, max(10, size // 2), "bold"),
            text_color=ui.ON_GOLD,
        ).place(relx=0.5, rely=0.5, anchor="center")
        return card
