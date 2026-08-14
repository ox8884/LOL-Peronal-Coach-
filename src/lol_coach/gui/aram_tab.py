"""ARAM 아수라장 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.aram_mayhem import (
    AugmentPick,
    AugmentTierTop,
    AugmentValidation,
    MayhemAdvice,
)
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FS, FT, FU
from lol_coach.gui.types import MixinBase
from lol_coach.static.augment_catalog import CatalogError
from lol_coach.static.augment_icons import augment_ctk, augment_pil, refresh_augment_sync
from lol_coach.static.icons import (
    cache_dir,
    champion_ctk,
    champion_pil,
    item_ctk,
    item_name_ctk,
    item_pil,
    item_pil_by_name,
)


def _tier_chip_label(pick: AugmentPick) -> str:
    """S/A/B가 전체 메타인지 지금 챔프 전용인지 칩에 적는다."""
    letter = (pick.tier or "B").strip().upper()[:1] or "B"
    if str(pick.reason or "").startswith("Blitz.gg"):
        return f"이 챔프 {letter}"
    return f"일반 {letter}"


def _next_augment_fill(
    current_text: str,
    prev_filled: tuple[str, ...] | None,
    new_augs: list[str],
) -> str | None:
    """리롤 시 이전 자동 입력을 새 목록으로 교체할지 결정.

    - 입력칸이 비어 있으면 항상 새 목록으로 채운다.
    - 이전에 자동으로 채운 값과 동일하면(리롤) 새 목록으로 갱신한다.
    - 사용자가 직접 수정했다면 덮지 않는다(None).
    """
    augs = [a for a in new_augs if a]
    if not augs:
        return None
    cur = tuple(n.strip() for n in re.split(r"[,，\n]", current_text or "") if n.strip())
    if not current_text.strip():
        return ", ".join(augs)
    if prev_filled is not None and cur == prev_filled:
        return ", ".join(augs)
    return None


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
            # 라이브 클라이언트 자동입력은 챔피언만 변경한다.
            self.aram_champ_var.set(fill.my_champ_ko)
            self._aram_live_fill = fill
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

        # ── 제시 증강 입력 (쉼표/줄바꿈 구분) ──
        self.aram_aug_var = tk.StringVar()
        self.aram_aug_entry = self._entry_row(
            form,
            2,
            "제시 증강",
            self.aram_aug_var,
            "예: Jeweled Gauntlet, 보석 건틀릿, Back to Basics",
        )
        self.aram_aug_status = ctk.CTkLabel(
            form,
            text="",
            font=FM,
            text_color=ui.TEXT_DIM,
        )
        self.aram_aug_status.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 2))

        # 간단한 실시간 카탈로그 힌트 (입력할 때마다)
        self.aram_aug_var.trace_add("write", self._on_aram_aug_changed)
        # 증강 카탈로그에서 선택 (제시 증강 입력칸 바로 아래)
        pick_row = ctk.CTkFrame(form, fg_color="transparent")
        pick_row.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 1))
        ctk.CTkButton(
            pick_row,
            text="🗂 증강 목록에서 선택",
            width=128,
            height=26,
            font=FU,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._open_augment_picker,
        ).pack(side="left")
        ctk.CTkLabel(
            pick_row,
            text="카탈로그 200+개 중 검색 → 클릭으로 추가",
            font=FU,
            text_color=ui.TEXT_DIM,
        ).pack(side="left", padx=8)

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
        "Ahri", "Lux", "Jinx", "Ezreal", "Yasuo", "Zed",
        "MissFortune", "KaiSa", "Veigar", "Brand", "Sona", "Lulu",
        "Garen", "Darius", "Teemo", "Shaco", "Pyke", "Khazix",
        "Ashe", "Caitlyn", "Morgana", "Blitzcrank", "Thresh", "Leona",
    )

    def _aram_quick_pick(self, champ_ko: str) -> None:
        """빈 결과 영역의 챔피언 타일 클릭 → 입력 채우고 브리핑 실행."""
        self.aram_champ_var.set(champ_ko)
        self._run_aram()

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
                ctk.CTkLabel(tile, image=icon, text="").pack(
                    side="left", padx=(8, 6), pady=6
                )
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
        missing = [
            k for k in self._ARAM_QUICK_KEYS
            if not (cd / f"c_{k}_36.png").exists()
        ]
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
        # 챔피언/증강이 바뀌었을 때만 브리핑 재실행 (리롤·늦은 증강 폴링 dedupe)
        sig = (
            info.my_champion_id,
            tuple(getattr(info, "my_augments", None) or []),
        )
        if not force and sig == self._aram_lcu_sig:
            return
        self._aram_lcu_sig: tuple = sig
        ko = self.dd.champion_name(info.my_champion_id)
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            ac.hide()
        self.aram_champ_var.set(ko)
        # 제시 증강 자동 입력 (LCU — 아수라장 밴픽에서 받아온 이름)
        augs = list(getattr(info, "my_augments", None) or [])
        new_fill = _next_augment_fill(
            self.aram_aug_var.get(),
            getattr(self, "_aram_lcu_filled", None),
            augs,
        )
        if new_fill is not None:
            self.aram_aug_var.set(new_fill)
        if augs:
            self._aram_lcu_filled = tuple(augs)
        self.aram_status.configure(text=f"밴픽 입력 완료 · {ko} — 브리핑 생성 중…")
        self._run_aram()
        if augs:
            self._notify_augment_verdict(augs)

    def _apply_offered_augments(self, names: list[str]) -> None:
        """인게임/LCU에서 읽은 제시 증강 이름을 칸에 넣고 판정한다."""
        if not hasattr(self, "aram_aug_var"):
            return
        cleaned = [str(n).strip() for n in names if str(n).strip()]
        if len(cleaned) < 2:
            return
        _raw, validation, err = self._parse_offered_augments(", ".join(cleaned))
        if err or validation is None or len(validation.valid) < 2:
            return
        labels = [r.name_ko or r.name_en for r in validation.valid[:3]]
        new_fill = _next_augment_fill(
            self.aram_aug_var.get(),
            getattr(self, "_aram_lcu_filled", None),
            labels,
        )
        if new_fill is None:
            return
        self.aram_aug_var.set(new_fill)
        self._aram_lcu_filled = tuple(labels)
        champ = ""
        if hasattr(self, "aram_champ_var"):
            champ = str(self.aram_champ_var.get() or "").strip()
        if not champ:
            try:
                self.aram_status.configure(text="증강 이름 입력됨 · 챔피언을 지정하면 판정")
            except Exception:
                pass
            return
        self.aram_status.configure(text=f"인게임 증강 감지 · {champ} — 판정 중…")
        self._run_aram()
        self._notify_augment_verdict([r.name_en for r in validation.valid[:3]])

    def _notify_augment_verdict(self, augs: list[str]) -> None:
        """LCU 증강 목록 수신 직후 — 판정 토스트 + 디스코드 카드 (백그라운드)."""
        if not augs:
            return
        raw = self.aram_champ_var.get()
        champ = raw.strip() if raw else ""
        if not champ:
            return

        def work() -> None:
            try:
                key, ko = self._resolve(champ)
                _names, validation, err = self._parse_offered_augments(", ".join(augs))
                if err or validation is None or not validation.valid:
                    return
                adv = self.mayhem.advise(
                    key, offered_augments=[r.name_en for r in validation.valid]
                )
            except Exception:
                return
            if adv.top_augments:
                top = adv.top_augments[0]
                tier = f" {top.tier}등급" if top.tier else ""
                self.after(
                    0,
                    lambda: self._notify(
                        f"🎯 증강 판정 — {top.name_ko} 선택{tier}",
                        level="ok",
                        ms=6500,
                        force=True,
                    ),
                )
                self.after(0, lambda: self._send_augment_card(adv))
            elif adv.avoid_augments:
                bad = adv.avoid_augments[0]
                self.after(
                    0,
                    lambda: self._notify(
                        f"⚠️ 증강 주의 — {bad.name_ko} 피하세요",
                        level="warn",
                        ms=6500,
                        force=True,
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _send_augment_card(self, adv: MayhemAdvice) -> None:
        """증강 판정 카드 디스코드 전송 (설정돼 있고 켜져 있을 때만)."""

        def render() -> bytes:
            from lol_coach.gui.augment_card import augment_card_bytes

            return augment_card_bytes(adv)

        def desc() -> str:
            lines = [f"{i + 1}순위: {p.name_ko}" for i, p in enumerate(adv.top_augments[:3])]
            return " · ".join(lines) if lines else "제시 증강 판정 결과"

        self._post_discord_card(
            title_fn=lambda: f"⚡ {adv.champ_ko} 증강 판정",
            description_fn=lambda: f"지금 제시된 증강 — {desc()}",
            png_bytes_fn=render,
            footer_fn=lambda: "롤 실전 코치 · LCU 실시간 판정",
            ok_msg="📮 증강 판정 카드 전송 완료",
            fail_msg="증강 카드 전송 실패",
        )

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

    def _on_aram_aug_changed(self, *_a: Any) -> None:
        """실시간으로 입력 중인 증강 이름을 카탈로그와 비교해 힌트를 보여줍니다."""
        text = self.aram_aug_var.get().strip()
        if not text:
            self.aram_aug_status.configure(text="")
            return
        names = [n.strip() for n in re.split(r"[,，\n]", text) if n.strip()]
        if not names:
            self.aram_aug_status.configure(text="")
            return
        try:
            _records, unknowns, duplicates = self._aug_catalog.resolve_many(names)
        except Exception:
            self.aram_aug_status.configure(text="")
            return
        parts: list[str] = []
        if unknowns:
            parts.append(f"알 수 없음: {', '.join(unknowns)}")
        if duplicates:
            parts.append(f"중복: {', '.join(duplicates)}")
        resolved = len(names) - len(unknowns) - len(duplicates)
        if resolved == len(names):
            self.aram_aug_status.configure(text="증강 확인됨")
            return
        self.aram_aug_status.configure(text=" · ".join(parts))

    def _open_augment_picker(self) -> None:
        """카탈로그 증강 검색/선택 팝업 — 클릭 시 입력칸에 추가."""
        win = ctk.CTkToplevel(self)
        win.title("증강 목록")
        win.geometry("480x560")
        win.attributes("-topmost", True)
        win.transient(self)

        search_var = tk.StringVar()
        search = ctk.CTkEntry(win, textvariable=search_var, placeholder_text="검색 (한글/영어)")
        search.pack(fill="x", padx=12, pady=(12, 6))

        list_frame = ctk.CTkScrollableFrame(win, label_text="카탈로그 증강")
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        list_frame.grid_columnconfigure(0, weight=1)

        records = list(self._aug_catalog.records)

        def _label(rec: Any) -> str:
            ko = rec.name_ko or rec.name_en
            rarity = {"prismatic": "◆", "gold": "★", "silver": "☆"}.get(rec.rarity, "·")
            return f"{rarity} {ko}  ({rec.name_en})"

        def _apply_filter(*_a: Any) -> None:
            q = search_var.get().strip().lower()
            for child in list_frame.winfo_children():
                child.destroy()
            if not q:
                shown = records
            else:
                shown = [
                    r
                    for r in records
                    if q in (r.name_ko or "").lower() or q in (r.name_en or "").lower()
                ]
            if not shown:
                ctk.CTkLabel(
                    list_frame, text="일치하는 증강이 없습니다", text_color=ui.TEXT_DIM
                ).grid(row=0, column=0, pady=10)
                return
            for i, rec in enumerate(shown[:150]):
                btn = ctk.CTkButton(
                    list_frame,
                    text=_label(rec),
                    anchor="w",
                    height=30,
                    font=FM,
                    fg_color=ui.ROW,
                    hover_color=ui.ROW_HOVER,
                    command=lambda r=rec: self._pick_augment(r, win),
                )
                btn.grid(row=i, column=0, sticky="ew", padx=4, pady=1)

        search_var.trace_add("write", _apply_filter)
        _apply_filter()
        search.focus_set()

    def _pick_augment(self, rec: Any, win: Any) -> None:
        """피커에서 선택한 증강을 제시 증강 입력칸에 추가."""
        name = rec.name_ko or rec.name_en
        cur = self.aram_aug_var.get().strip()
        parts = [p.strip() for p in re.split(r"[,，\n]", cur) if p.strip()]
        if name not in parts:
            parts.append(name)
        self.aram_aug_var.set(", ".join(parts))
        try:
            win.destroy()
        except Exception:
            pass
        self.aram_status.configure(text=f"증강 추가됨 · {name} — 브리핑을 눌러 주세요")

    def _suggest_augments(self, names: list[str], *, limit: int = 5) -> list[str]:
        """Return actionable catalog suggestions for unknown augment names."""
        if not names:
            return []
        seen: set[str] = set()
        out: list[str] = []
        for name in names:
            for rec in self._aug_catalog.suggestions(name, limit=limit):
                label = rec.name_ko or rec.name_en
                if label and label not in seen:
                    seen.add(label)
                    out.append(label)
                    if len(out) >= limit:
                        return out
        return out

    def _parse_offered_augments(self, raw: str) -> tuple[list[str], AugmentValidation | None, str]:
        """Returns (names, validation_or_none, error_message)."""
        raw = raw.strip()
        if not raw:
            return [], None, ""
        names = [n.strip() for n in re.split(r"[,，\n]", raw) if n.strip()]
        try:
            validation = self.mayhem.resolve_offered(names)
        except CatalogError as e:
            return names, None, str(e)
        except Exception as e:
            return names, None, f"증강 목록을 확인할 수 없습니다: {e}"
        return names, validation, ""

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

        offered_raw = self.aram_aug_var.get()
        _names, validation, err = self._parse_offered_augments(offered_raw)
        if err:
            self._notify(err, level="warn")
            return
        unknowns = validation.unknowns if validation else []
        duplicates = validation.duplicates if validation else []
        if unknowns or duplicates:
            lines: list[str] = []
            if unknowns:
                lines.append(f"카탈로그에 없는 증강: {', '.join(unknowns)}")
            if duplicates:
                lines.append(f"중복된 증강: {', '.join(duplicates)}")
            suggestions = self._suggest_augments(unknowns)
            if suggestions:
                lines.append(f"비슷한 증강: {', '.join(suggestions)}")
            lines.append("확인 후 다시 입력해 주세요.")
            message = " · ".join(lines)
            self.aram_aug_status.configure(text=message)
            self._notify(message, level="warn", ms=5500)
            return

        # 선택 후 필드에 정식 한글 이름 표시
        self.aram_champ_var.set(ko)
        self._busy_set(True, self.aram_btn, "아수라장 브리핑", key="aram_brief")
        self.aram_status.configure(text=f"{ko} 분석 중…")

        def work() -> None:
            try:
                offered = validation.valid if validation else []
                adv = self.mayhem.advise(key, offered_augments=[r.name_en for r in offered])
                # 인게임 조합이 있으면 태그 기반 위협/시너지 요약
                try:
                    fill = getattr(self, "_aram_live_fill", None)
                    if fill is not None:
                        from lol_coach.analysis.aram_comp import analyze_aram_comp

                        enemies = list(fill.enemies_by_role.values()) + list(fill.enemies_extra)
                        rep = analyze_aram_comp(
                            self.dd,
                            allies=list(fill.allies),
                            enemies=enemies,
                            my_key=fill.my_champ_key or key,
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
                                adv.core_item_ids = [
                                    self.dd.item_id_for_name(s) for s in new_slots
                                ]
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
                # 캐시 프리페치는 메인 스레드가 아닌 워커에서만 네트워크 가능
                for pick in adv.top_augments:
                    augment_pil(pick.name_en, 40)
                for pick in adv.avoid_augments:
                    augment_pil(pick.name_en, 36)
                for picks in (
                    adv.fixed_top.silver,
                    adv.fixed_top.gold,
                    adv.fixed_top.prismatic,
                ):
                    for pick in picks:
                        augment_pil(pick.name_en, 34)

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
        self.aram_aug_var.set("")
        self.aram_aug_status.configure(text="")
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            try:
                ac.hide()
            except Exception:
                pass
        self._render_aram_empty_state()
        self.aram_status.configure(text="초기화됨 — 챔피언 + 제시 증강을 입력하세요")
        self.status.configure(text="ARAM 탭 초기화")
        try:
            self._set_aram_inputs_expanded(True)
        except Exception:
            pass

    def _render_fixed_augment_board(
        self,
        parent: Any,
        row: int,
        fixed_top: AugmentTierTop,
    ) -> int:
        row = self._sec(parent, "1. 희귀도별 고정 TOP 3", row)
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
            ).pack(fill="x", padx=12, pady=(12, 8))
            if not picks:
                ctk.CTkLabel(
                    column,
                    text="추천 데이터 없음",
                    font=FB,
                    text_color=ui.TEXT_DIM,
                    anchor="w",
                ).pack(fill="x", padx=12, pady=(8, 16))
                continue
            for rank, pick in enumerate(picks, 1):
                card = ctk.CTkFrame(
                    column,
                    fg_color=ui.ROW,
                    corner_radius=ui.ROW_RADIUS,
                    border_width=ui.CARD_BORDER,
                    border_color=ui.BORDER,
                )
                card.pack(fill="x", padx=8, pady=(0, 6 if rank < 3 else 12))
                icon = self._keep_icon(augment_ctk(pick.name_en, 48))
                if icon:
                    ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(10, 8), pady=10)
                else:
                    self._augment_missing_card(card, pick, size=48).pack(
                        side="left", padx=(10, 8), pady=10
                    )
                ctk.CTkLabel(
                    card,
                    text=(f"{rank}위  {pick.name_ko}\n{pick.desc}\nBlitz 챔피언별 {rank}순위"),
                    font=FB,
                    text_color=ui.TEXT_BRIGHT if rank == 1 else ui.TEXT,
                    anchor="w",
                    justify="left",
                    wraplength=225,
                ).pack(fill="x", expand=True, side="left", padx=(0, 10), pady=10)
        return row + 1

    def _render_aram_build_grid(
        self,
        parent: Any,
        row: int,
        adv: MayhemAdvice,
    ) -> int:
        row = self._sec(parent, "3. 6슬롯 완성 빌드", row)
        if adv.spells_line:
            row = self._lbl(parent, f"스펠  {adv.spells_line}", row, font=FU)
        if adv.skill_line:
            row = self._lbl(parent, f"스킬  {adv.skill_line}", row, font=FU)
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 8))
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
                padx=(0 if index % 3 == 0 else 4, 0 if index % 3 == 2 else 4),
                pady=(0 if index < 3 else 4, 4 if index < 3 else 0),
            )
            item_id = adv.core_item_ids[index] if index < len(adv.core_item_ids) else None
            icon = self._keep_icon(
                item_ctk(item_id, 52) if item_id is not None else item_name_ctk(item, 52)
            )
            if icon:
                ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(12, 10), pady=12)
            else:
                fallback = ctk.CTkFrame(
                    card,
                    width=52,
                    height=52,
                    corner_radius=ui.ROW_RADIUS,
                    fg_color=ui.GOLD,
                )
                fallback.pack(side="left", padx=(12, 10), pady=12)
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
            ).pack(fill="x", expand=True, side="left", padx=(0, 12), pady=12)
        return row + 1

    def _schedule_aram_icon_fill(self, adv: MayhemAdvice) -> None:
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
            for name in missing:
                try:
                    refresh_augment_sync(name)
                except Exception:
                    pass
            try:
                self.after(0, lambda: self._render_aram(adv))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _render_offered_pick_row(
        self, row: int, pick: AugmentPick, *, index: int, tone: str
    ) -> int:
        color = ui.GREEN if tone == "pick" else ui.TEXT_BRIGHT
        frame = self._row_frame(self.aram_out, row, padx=10, pady=4)
        aicon = self._keep_icon(augment_ctk(pick.name_en, 48))
        if aicon:
            ctk.CTkLabel(frame, image=aicon, text="").pack(side="left", padx=(12, 10), pady=10)
        else:
            self._augment_missing_card(frame, pick, size=48).pack(side="left", padx=(12, 10), pady=10)
        ctk.CTkLabel(
            frame,
            text=f"{index}. {pick.name_ko}\n→ {pick.record.description_ko}\n({pick.reason})",
            font=FU,
            text_color=color,
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(0, 12), pady=10)
        ui.tier_chip(frame, _tier_chip_label(pick), font=FS, width=78).pack(
            side="right", padx=(0, 14)
        )
        return row + 1

    def _render_aram(self, adv: MayhemAdvice) -> None:
        self._aram_rendered = True
        self._clear(self.aram_out)
        r = 0

        head = self._row_frame(self.aram_out, r, padx=10, pady=8)
        ck = adv.champ_key or adv.champ_ko
        cicon = self._keep_icon(champion_ctk(ck, 72))
        if cicon:
            ctk.CTkLabel(head, image=cicon, text="").pack(side="left", padx=(14, 12), pady=10)
        ctk.CTkLabel(
            head,
            text=f"{adv.champ_ko}\nARAM 아수라장 · 패치 {adv.patch}",
            font=FT,
            anchor="w",
            justify="left",
            text_color=ui.TEXT_BRIGHT,
        ).pack(side="left", padx=(0, 14), pady=10)
        r += 1

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

        r = self._render_fixed_augment_board(self.aram_out, r, adv.fixed_top)

        if adv.augment_validation is not None:
            val = adv.augment_validation
            notes: list[str] = []
            if val.unknowns:
                notes.append(f"알 수 없는 증강: {', '.join(val.unknowns)}")
            if val.duplicates:
                notes.append(f"중복 제시: {', '.join(val.duplicates)}")
            if notes:
                r = self._lbl(
                    self.aram_out,
                    " · ".join(notes),
                    r,
                    color=ui.WARN,
                    font=FM,
                )

        r = self._sec(self.aram_out, "2. 지금 제시된 증강 판정", r)
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
        if not adv.augment_validation.valid:
            r = self._lbl(
                self.aram_out,
                "아수라장 증강 3장은 맵에서 레벨 3·7·11·15에 뜹니다. "
                "뜬 3장 이름을 위 입력칸에 적으면 판정합니다. "
                "밴픽 중에는 앱이 LCU에서 자동으로 가져옵니다.",
                r,
                color=ui.TEXT_DIM,
            )
        else:
            shown_ids: set[str] = set()
            for i, pick in enumerate(adv.top_augments, 1):
                r = self._render_offered_pick_row(r, pick, index=i, tone="pick")
                shown_ids.add(pick.record.id)

            avoid_ids = {p.record.id for p in adv.avoid_augments}
            rest_n = len(adv.top_augments)
            for rec in val.valid:
                if rec.id in shown_ids or rec.id in avoid_ids:
                    continue
                rest_n += 1
                mid = AugmentPick(
                    record=rec,
                    tier=rec.fallback_tier or "B",
                    score=0,
                    reason=(
                        f"전체 메타 {rec.fallback_tier or 'B'}등급 · "
                        "지금 챔프 전용 순위는 아님"
                    ),
                )
                r = self._render_offered_pick_row(r, mid, index=rest_n, tone="mid")
                shown_ids.add(rec.id)

        if adv.avoid_augments:
            for pick in adv.avoid_augments:
                frame = self._row_frame(self.aram_out, r, padx=10, pady=3)
                aicon = self._keep_icon(augment_ctk(pick.name_en, 48))
                if aicon:
                    ctk.CTkLabel(frame, image=aicon, text="").pack(
                        side="left", padx=(12, 10), pady=8
                    )
                else:
                    self._augment_missing_card(frame, pick, size=48).pack(
                        side="left", padx=(12, 10), pady=8
                    )
                ctk.CTkLabel(
                    frame,
                    text=f"✕ {pick.name_ko}  —  {pick.record.description_ko}\n({pick.reason})",
                    font=FB,
                    text_color=ui.RED_SOFT,
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 14), pady=8)
                r += 1

        self._schedule_aram_icon_fill(adv)
        r = self._render_aram_build_grid(self.aram_out, r, adv)

        key = self._ai_key()
        if key:
            ai_host = ctk.CTkFrame(self.aram_out, fg_color="transparent")
            ai_host.grid(row=r, column=0, sticky="ew")
            ai_host.grid_columnconfigure(0, weight=1)
            self._maybe_ai(
                ai_host,
                lambda: self._ai_coach_aram(adv, key),
            )
            r += 1

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
        if adv.spells_line:
            summary.append("")
            summary.append("스펠: " + adv.spells_line)
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
            font=("Malgun Gothic", max(10, size // 2), "bold"),
            text_color=ui.ON_GOLD,
        ).place(relx=0.5, rely=0.5, anchor="center")
        return card
