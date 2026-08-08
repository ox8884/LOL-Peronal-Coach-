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

from lol_coach.analysis.aram_mayhem import AugmentValidation
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FS, FU
from lol_coach.static.augment_catalog import CatalogError
from lol_coach.static.augment_icons import augment_ctk, augment_pil
from lol_coach.static.icons import champion_ctk, champion_pil, item_name_ctk, item_pil_by_name


class AramTabMixin:
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


    def _apply_live_aram(self, fill) -> None:
        try:
            if fill.is_sr and not fill.is_aram and not messagebox.askyesno(
                "모드 확인",
                "지금 게임은 소환사 협곡으로 보입니다.\n"
                f"그래도 내 챔프({fill.my_champ_ko})로 ARAM 브리핑을 할까요?\n\n"
                "협곡 조합 분석은 「소환사의 협곡」탭 인게임 자동입력을 쓰세요.",
            ):
                self._busy_set(False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")
                self.aram_status.configure(text="취소됨")
                return

            ac = getattr(self, "_aram_ac", None)
            if ac is not None:
                ac.hide()
            # 라이브 클라이언트 자동입력은 챔피언만 변경한다.
            self.aram_champ_var.set(fill.my_champ_ko)
            self._aram_live_fill = fill
            self.aram_status.configure(
                text=f"인게임 · {fill.my_champ_ko} 브리핑 중…"
            )
            self._busy_set(False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")
            self._start_game_end_watcher()
            self._run_aram()
        except Exception as e:
            self._notify_error(e)
            self._busy_set(False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")


    def _build_aram(self) -> None:
        form = ctk.CTkFrame(
            self.t_aram, corner_radius=12, border_width=1, border_color=ui.BORDER
        )
        form.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
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
        self._aram_ac.panel.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 4)
        )
        self._aram_ac.panel.grid_remove()

        aram_entry.bind("<Return>", self._aram_enter, add="+")
        aram_entry.bind("<KP_Enter>", self._aram_enter, add="+")

        # ── 제시 증강 입력 (쉼표/줄바꿈 구분) ──
        self.aram_aug_var = tk.StringVar()
        self.aram_aug_entry = self._entry_row(
            form, 2, "제시 증강", self.aram_aug_var, "예: Jeweled Gauntlet, 보석 건틀릿, Back to Basics"
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
            corner_radius=10,
            label_text="아수라장 브리핑",
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.aram_out.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.aram_out.grid_columnconfigure(0, weight=1)
        self._lbl(
            self.aram_out,
            "챔피언을 고르면 증강 우선순위와 ARAM 빌드를 바로 보여줍니다.",
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
        # 챔피언이 바뀌었을 때만 브리핑 재실행 (리롤 폴링 dedupe)
        if not force and info.my_champion_id == self._aram_lcu_sig:
            return
        self._aram_lcu_sig = info.my_champion_id
        ko = self.dd.champion_name(info.my_champion_id)
        ac = getattr(self, "_aram_ac", None)
        if ac is not None:
            ac.hide()
        self.aram_champ_var.set(ko)
        self.aram_status.configure(text=f"밴픽 입력 완료 · {ko} — 브리핑 생성 중…")
        self._run_aram()


    def _start_aram_champ_watch(self) -> None:
        """ARAM 밴픽 폴링 — 리롤/픽 변화 시 브리핑 갱신."""
        from lol_coach.gui.watcher import ChampSelectWatcher
        from lol_coach.lcu import LCUClient

        self._stop_champ_watch()

        def get() -> Any:
            return LCUClient().champ_select()

        def on_update(info: Any) -> None:
            self.after(0, lambda: self._apply_lcu_aram(info))

        def on_end() -> None:
            self.after(0, lambda: self.aram_status.configure(text="밴픽 종료 · 추적 중단"))
            self._champ_watcher = None

        self._champ_watcher = ChampSelectWatcher(
            get_champ_select=get,
            on_update=on_update,
            on_end=on_end,
            interval_s=4.0,
        )
        self._champ_watcher.start()
        self.aram_status.configure(text="밴픽 추적 중 — 리롤하면 자동 갱신")


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

                        enemies = list(fill.enemies_by_role.values()) + list(
                            fill.enemies_extra
                        )
                        rep = analyze_aram_comp(
                            self.dd,
                            allies=list(fill.allies),
                            enemies=enemies,
                            my_key=fill.my_champ_key or key,
                        )
                        adv.comp_lines = rep.lines  # type: ignore[attr-defined]
                except Exception:
                    pass
                from lol_coach.static.augment_icons import augment_pil
                from lol_coach.static.icons import champion_pil, item_pil_by_name

                champion_pil(adv.champ_key or adv.champ_ko, 52)
                for item in adv.core_slots:
                    item_pil_by_name(item, 32)
                # 캐시 프리페치는 메인 스레드가 아닌 워커에서만 네트워크 가능
                for pick in adv.top_augments:
                    augment_pil(pick.name_en, 40)
                for pick in adv.avoid_augments:
                    augment_pil(pick.name_en, 36)

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
                    0, lambda: self._busy_set(False, self.aram_btn, "아수라장 브리핑", key="aram_brief")
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


    def _render_aram(self, adv: MayhemAdvice) -> None:
        from lol_coach.static.augment_icons import augment_ctk

        self._clear(self.aram_out)
        r = 0

        head = self._row_frame(self.aram_out, r, pady=6)
        ck = adv.champ_key or adv.champ_ko
        cicon = self._keep_icon(champion_ctk(ck, 52))
        if cicon:
            ctk.CTkLabel(head, image=cicon, text="").pack(
                side="left", padx=(10, 10), pady=8
            )
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

        r = self._sec(
            self.aram_out,
            "1. 제시된 증강 비교" if adv.augment_validation.valid else "1. 챔피언 기준 추천 증강 Top 5",
            r,
        )
        if not adv.top_augments:
            r = self._lbl(
                self.aram_out,
                "추천할 증강을 찾지 못했습니다. 제시된 증강 이름을 입력해 다시 비교하세요.",
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
                    self._augment_missing_card(frame, pick).pack(
                        side="left", padx=(10, 8), pady=8
                    )
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

        r = self._sec(self.aram_out, "2. 피해야 할 증강", r)
        if not adv.avoid_augments:
            r = self._lbl(
                self.aram_out,
                "회피 대상이 없습니다.",
                r,
                color=ui.TEXT_DIM,
            )
        else:
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

        r = self._sec(self.aram_out, "3. ARAM 아이템 빌드 (1코어 → 5코어)", r)
        if adv.spells_line:
            r = self._lbl(self.aram_out, f"스펠  {adv.spells_line}", r, font=FU)
        if adv.skill_line:
            r = self._lbl(self.aram_out, f"스킬  {adv.skill_line}", r, font=FU)
        if adv.core_slots:
            for i, item in enumerate(adv.core_slots, 1):
                frame = self._row_frame(self.aram_out, r, pady=2)
                ic = self._keep_icon(item_name_ctk(item, 32))
                if ic:
                    ctk.CTkLabel(frame, image=ic, text="").pack(
                        side="left", padx=(10, 8), pady=6
                    )
                ctk.CTkLabel(
                    frame,
                    text=f"{i}코어    {item}",
                    font=FU,
                    anchor="w",
                ).pack(side="left", padx=(0, 12), pady=6)
                r += 1
        else:
            r = self._lbl(
                self.aram_out,
                "코어 아이템 이름을 가져오지 못했습니다. Blitz ARAM 페이지를 확인하세요.",
                r,
                color=ui.TEXT_DIM,
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
        key = self._ai_key()
        if key:
            self._maybe_ai(
                self.aram_out,
                lambda: self._ai_coach_aram(adv, key),
            )
        summary = []
        for i, p in enumerate(adv.top_augments[:5], 1):
            reason = p.reason or ""
            summary.append(f"{i}. {p.name_ko} ({p.tier or '?'}) — {reason}")
        if adv.avoid_augments:
            summary.append("")
            summary.append(
                "✕ 피할 것: " + ", ".join(p.name_ko for p in adv.avoid_augments[:3])
            )
        if adv.spells_line:
            summary.append("")
            summary.append("스펠: " + adv.spells_line)
        if adv.core_slots:
            summary.append("")
            summary.append("빌드: " + " → ".join(adv.core_slots[:4]))
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
        self._push_summary(
            f"🔮 {adv.champ_ko} 아수라장  (패치 {adv.patch})", summary
        )


    def _augment_missing_card(
        self, parent: Any, pick: AugmentPick, size: int = 40
    ) -> ctk.CTkFrame:
        """아이콘이 없을 때 명시적 이름+등급 배지."""
        rarity = pick.rarity or "gold"
        color = {
            "prismatic": ("#A064DC", "#7B4AA8"),
            "gold": ("#C8A028", "#9A7A1E"),
            "silver": ("#8C96A0", "#6B737A"),
        }.get(rarity, ("#C8A028", "#9A7A1E"))
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
            text_color="white",
        ).place(relx=0.5, rely=0.5, anchor="center")
        return card

