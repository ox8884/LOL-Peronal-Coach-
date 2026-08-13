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
from lol_coach.gui.constants import FB, FCH, FM, FS, FU
from lol_coach.gui.types import MixinBase
from lol_coach.static.augment_catalog import CatalogError
from lol_coach.static.augment_icons import augment_ctk, augment_pil
from lol_coach.static.icons import (
    champion_ctk,
    champion_pil,
    item_ctk,
    item_name_ctk,
    item_pil,
    item_pil_by_name,
)


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
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        form.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
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
        pick_row.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 2))
        ctk.CTkButton(
            pick_row,
            text="🗂 증강 목록에서 선택",
            width=140,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._open_augment_picker,
        ).pack(side="left")
        ctk.CTkLabel(
            pick_row,
            text="카탈로그 200+개 중 검색 → 클릭으로 입력칸에 추가",
            font=FM,
            text_color=ui.TEXT_DIM,
        ).pack(side="left", padx=10)

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 12))
        self.aram_live_btn = ctk.CTkButton(
            btn_row,
            text="🎮 실행 중인 게임 자동 검색",
            height=38,
            font=FU,
            **ui.btn(*ui.BTN_SUCCESS),
            command=self._live_fill_aram,
        )
        self.aram_live_btn.pack(side="left", padx=(0, 8))
        self.aram_btn = ctk.CTkButton(
            btn_row,
            text="아수라장 브리핑",
            height=38,
            font=FU,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._run_aram,
        )
        self.aram_btn.pack(side="left")
        self.aram_lcu_btn = ctk.CTkButton(
            btn_row,
            text="🎯 밴픽 (LCU)",
            height=38,
            width=110,
            font=FM,
            **ui.btn(*ui.BTN_PURPLE),
            command=self._lcu_fill_aram,
        )
        self.aram_lcu_btn.pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btn_row,
            text="📜 이전",
            width=64,
            height=38,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._back_aram_history,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btn_row,
            text="🧹 초기화",
            width=72,
            height=38,
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
        self._lbl(
            self.aram_out,
            "챔피언을 고르면 증강 우선순위와 ARAM 빌드를 바로 보여줍니다.\n"
            "브리핑 후 입력이 접혀 AI 상세 코칭이 크게 보입니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
        )

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

    def _hide_floating_for_ocr(self) -> list[tuple[str, Any]]:
        """위젯/오버레이가 롤 카드 위에 겹쳐 읽히지 않게 잠깐 숨긴다."""
        hidden: list[tuple[str, Any]] = []
        for kind, attr in (("overlay", "_overlay_win"), ("widget", "_widget")):
            win = getattr(self, attr, None)
            if win is None:
                continue
            try:
                if win.winfo_exists():
                    win.withdraw()
                    hidden.append((kind, win))
            except Exception:
                pass
        return hidden

    def _restore_floating_after_ocr(self, hidden: list[tuple[str, Any]]) -> None:
        for kind, win in hidden:
            try:
                if not win.winfo_exists():
                    continue
                win.deiconify()
                if kind == "widget":
                    win.attributes("-topmost", True)
            except Exception:
                pass

    def _capture_offered_augments(self) -> None:
        """증강 선택 창이 떠 있을 때 화면에서 3장을 읽어 판정한다."""
        if getattr(self, "_ocr_busy", False):
            return
        if not hasattr(self, "_aug_catalog"):
            return
        self._ocr_busy = True
        try:
            self.status.configure(text="증강 창 읽는 중… Ctrl+Shift+A")
        except Exception:
            pass
        try:
            if hasattr(self, "aram_status"):
                self.aram_status.configure(text="증강 창 읽는 중…")
        except Exception:
            pass
        hidden = self._hide_floating_for_ocr()

        def work() -> None:
            from lol_coach.analysis.augment_ocr import OfferedRead, inspect_offered_from_screen

            result = OfferedRead([], "error")
            try:
                result = inspect_offered_from_screen(list(self._aug_catalog.records))
            except Exception as exc:
                from lol_coach.log import get_logger

                get_logger("augocr").debug("증강 캡처 실패: %s", exc)

            def done() -> None:
                self._restore_floating_after_ocr(hidden)
                self._ocr_busy = False
                self._finish_offered_read(result)

            self.after(0, done)

        # 위젯이 화면에서 사라진 뒤에 찍는다
        self.after(120, lambda: threading.Thread(target=work, daemon=True).start())

    def _finish_offered_read(self, result: Any) -> None:
        names = list(getattr(result, "names", None) or [])
        reason = str(getattr(result, "reason", "") or "")
        if names and reason == "ok":
            self._apply_offered_augments(names)
            self._notify(
                "증강 인식 — " + " · ".join(names),
                level="ok",
                ms=5500,
                force=True,
            )
            try:
                self._push_summary("증강 인식", names)
            except Exception:
                pass
            try:
                if hasattr(self, "aram_status"):
                    self.aram_status.configure(text="증강 인식 · " + " · ".join(names))
            except Exception:
                pass
            return
        messages = {
            "blank": (
                "롤 전체화면이라 화면이 검게 캡처됐습니다. "
                "비디오 → 테두리 없는 창 모드로 바꾼 뒤 Ctrl+Shift+A"
            ),
            "empty_ocr": "글자를 읽지 못했습니다. 증강 3장이 크게 보이는 상태에서 다시 눌러 주세요.",
            "no_match": "글자는 읽었지만 제시 3장을 맞추지 못했습니다. 카드가 가려지지 않게 다시 눌러 주세요.",
            "weak_match": (
                "앱 추천 목록만 읽힌 것 같습니다. 롤 증강 3장이 화면 가운데에 "
                "크게 보이게 한 뒤 Ctrl+Shift+A"
            ),
            "error": "화면 읽기에 실패했습니다. 잠시 후 Ctrl+Shift+A 로 다시 시도해 주세요.",
        }
        msg = messages.get(
            reason,
            "증강 3장이 크게 보이는 상태에서 Ctrl+Shift+A 를 다시 눌러 주세요.",
        )
        self._notify(msg, level="warn", ms=7000, force=True)
        try:
            self._push_summary("증강 인식 실패", [msg])
        except Exception:
            pass
        try:
            if hasattr(self, "aram_status"):
                self.aram_status.configure(text="증강 인식 실패")
        except Exception:
            pass

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
        self._clear(self.aram_out)
        self._lbl(
            self.aram_out,
            "챔피언을 고르면 증강 우선순위와 ARAM 빌드를 바로 보여줍니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
        )
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
            ).pack(fill="x", padx=10, pady=(10, 6))
            if not picks:
                ctk.CTkLabel(
                    column,
                    text="추천 데이터 없음",
                    font=FB,
                    text_color=ui.TEXT_DIM,
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(8, 14))
                continue
            for rank, pick in enumerate(picks, 1):
                card = ctk.CTkFrame(
                    column,
                    fg_color=ui.ROW,
                    corner_radius=ui.ROW_RADIUS,
                    border_width=ui.CARD_BORDER,
                    border_color=ui.BORDER,
                )
                card.pack(fill="x", padx=8, pady=(0, 6 if rank < 3 else 10))
                icon = self._keep_icon(augment_ctk(pick.name_en, 34))
                if icon:
                    ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(8, 6), pady=8)
                else:
                    self._augment_missing_card(card, pick, size=34).pack(
                        side="left", padx=(8, 6), pady=8
                    )
                ctk.CTkLabel(
                    card,
                    text=(f"{rank}위  {pick.name_ko}\n{pick.desc}\nBlitz 챔피언별 {rank}순위"),
                    font=FM,
                    text_color=ui.TEXT_BRIGHT if rank == 1 else ui.TEXT,
                    anchor="w",
                    justify="left",
                    wraplength=225,
                ).pack(fill="x", expand=True, side="left", padx=(0, 8), pady=8)
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
                item_ctk(item_id, 38) if item_id is not None else item_name_ctk(item, 38)
            )
            if icon:
                ctk.CTkLabel(card, image=icon, text="").pack(side="left", padx=(10, 8), pady=10)
            else:
                fallback = ctk.CTkFrame(
                    card,
                    width=38,
                    height=38,
                    corner_radius=ui.ROW_RADIUS,
                    fg_color=ui.GOLD,
                )
                fallback.pack(side="left", padx=(10, 8), pady=10)
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
            ).pack(fill="x", expand=True, side="left", padx=(0, 10), pady=10)
        return row + 1

    def _render_aram(self, adv: MayhemAdvice) -> None:
        self._clear(self.aram_out)
        r = 0

        head = self._row_frame(self.aram_out, r, pady=6)
        ck = adv.champ_key or adv.champ_ko
        cicon = self._keep_icon(champion_ctk(ck, 52))
        if cicon:
            ctk.CTkLabel(head, image=cicon, text="").pack(side="left", padx=(10, 10), pady=8)
        ctk.CTkLabel(
            head,
            text=f"{adv.champ_ko}  ·  ARAM 아수라장\n패치 {adv.patch}",
            font=FS,
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(0, 12), pady=8)
        r += 1

        r = self._lbl(
            self.aram_out,
            "※ 아수라장/칼바람은 룬 선택 없음 · 증강 + 아이템만 본다.",
            r,
            font=FM,
            color=ui.TEXT_DIM,
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
        if not adv.augment_validation.valid:
            r = self._lbl(
                self.aram_out,
                "아수라장 증강 3장은 맵에서 레벨 3·7·11·15에 뜹니다. "
                "창이 뜨면 앱이 화면에서 이름을 읽습니다. "
                "안 되면 3장이 보이는 상태에서 Ctrl+Shift+A. "
                "전체화면이면 비디오 → 테두리 없는 창 모드가 읽기 쉽습니다.",
                r,
                color=ui.TEXT_DIM,
            )
        else:
            for i, pick in enumerate(adv.top_augments, 1):
                frame = self._row_frame(self.aram_out, r, pady=3)
                aicon = self._keep_icon(augment_ctk(pick.name_en, 40))
                if aicon:
                    ctk.CTkLabel(frame, image=aicon, text="").pack(
                        side="left", padx=(10, 8), pady=8
                    )
                else:
                    # 이미지 없을 때 명시적 이름+등급 카드
                    self._augment_missing_card(frame, pick).pack(side="left", padx=(10, 8), pady=8)
                ctk.CTkLabel(
                    frame,
                    text=f"{i}. {pick.name_ko}\n→ {pick.record.description_ko}\n({pick.reason})",
                    font=FU,
                    text_color=ui.GREEN,
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 12), pady=8)
                ui.tier_chip(frame, pick.tier or "B", font=FCH, width=30).pack(
                    side="right", padx=(0, 12)
                )
                r += 1

        if adv.avoid_augments:
            for pick in adv.avoid_augments:
                frame = self._row_frame(self.aram_out, r, pady=2)
                aicon = self._keep_icon(augment_ctk(pick.name_en, 36))
                if aicon:
                    ctk.CTkLabel(frame, image=aicon, text="").pack(
                        side="left", padx=(10, 8), pady=6
                    )
                else:
                    self._augment_missing_card(frame, pick, size=36).pack(
                        side="left", padx=(10, 8), pady=6
                    )
                ctk.CTkLabel(
                    frame,
                    text=f"✕ {pick.name_ko}  —  {pick.record.description_ko}\n({pick.reason})",
                    font=FB,
                    text_color=ui.RED_SOFT,
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 12), pady=6)
                r += 1

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
