"""내 전적 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.export import export_matches_csv, export_matches_json
from lol_coach.analysis.pool import diagnose_pool
from lol_coach.analysis.review import analyze_match
from lol_coach.config import (
    DEFAULT_PLATFORM,
    add_profile,
    game_end_notify_enabled,
    list_profiles,
    load_settings,
    remove_profile,
    save_api_key,
    save_player,
    set_game_end_notify,
)
from lol_coach.gui import components as ui
from lol_coach.gui.constants import AI_MODELS, FM, FS, FU, PLATFORMS
from lol_coach.riot.client import RiotAPIError, RiotClient
from lol_coach.static.icons import champion_ctk, item_ctk


class MeTabMixin:
    def _build_me(self) -> None:
        card = ctk.CTkFrame(
            self.t_me, corner_radius=12, border_width=1, border_color=ui.BORDER
        )
        card.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        card.grid_columnconfigure(1, weight=1)

        self.riot_id_var = tk.StringVar(value=self.settings.riot_id)
        from lol_coach.config import DEFAULT_PLATFORM as _DEF_PLAT

        self.platform_var = tk.StringVar(value=self.settings.platform or _DEF_PLAT)
        self.api_key_var = tk.StringVar(value=self.settings.riot_api_key or "")

        self._entry_row(card, 0, "Riot ID", self.riot_id_var, "소환사명#KR1")
        ctk.CTkLabel(card, text="서버", font=FU, width=90, anchor="w").grid(
            row=0, column=2, sticky="w", padx=6
        )
        platform_values = list(PLATFORMS)
        cur_plat = (self.settings.platform or _DEF_PLAT).strip().lower()
        if cur_plat and cur_plat not in platform_values:
            platform_values.insert(0, cur_plat)
        ctk.CTkOptionMenu(
            card,
            variable=self.platform_var,
            values=platform_values,
            width=90,
            height=34,
            font=FU,
        ).grid(row=0, column=3, padx=(0, 12), pady=5)

        key_lab = ctk.CTkFrame(card, fg_color="transparent")
        key_lab.grid(row=1, column=0, sticky="w", padx=(12, 4), pady=5)
        ctk.CTkLabel(key_lab, text="API 키", font=FU).pack(side="left")
        ctk.CTkButton(
            key_lab,
            text="❓ 도움말",
            width=72,
            height=26,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._show_api_help,
        ).pack(side="left", padx=(6, 0))
        ctk.CTkEntry(
            card,
            textvariable=self.api_key_var,
            font=FM,
            height=34,
            show="•",
            placeholder_text="RGAPI-…  (처음이면 도움말 클릭)",
        ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.me_btn = ctk.CTkButton(
            card,
            text="전적 로드",
            width=100,
            height=34,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._load_me,
        )
        self.me_btn.grid(row=1, column=3, padx=(6, 12), pady=5)

        # ── 프로필 선택 / 랭크 표시 / 전적 내보내기 ──
        misc = ctk.CTkFrame(card, fg_color="transparent")
        misc.grid(row=2, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(misc, text="프로필", font=FU).pack(side="left")
        self.profile_var = tk.StringVar(value="")
        self.profile_menu = ctk.CTkOptionMenu(
            misc,
            variable=self.profile_var,
            values=self._profile_labels(),
            width=170,
            height=28,
            font=FM,
            command=self._on_profile_pick,
        )
        self.profile_menu.pack(side="left", padx=(6, 4))
        ctk.CTkLabel(misc, text="최근", font=FM).pack(side="left", padx=(10, 2))
        self.count_var = tk.StringVar(value="15")
        ctk.CTkOptionMenu(
            misc,
            variable=self.count_var,
            values=["5", "10", "15", "20", "30", "50"],
            width=58,
            height=28,
            font=FM,
        ).pack(side="left")
        ctk.CTkLabel(misc, text="경기", font=FM).pack(side="left", padx=(2, 0))
        ctk.CTkButton(
            misc,
            text="저장",
            width=52,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._save_current_profile,
        ).pack(side="left")
        ctk.CTkButton(
            misc,
            text="삭제",
            width=52,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._delete_current_profile,
        ).pack(side="left", padx=(4, 0))
        self.rank_lbl = ctk.CTkLabel(
            misc, text="", font=FM, text_color=ui.TEXT_DIM
        )
        self.rank_lbl.pack(side="left", padx=12)
        ctk.CTkButton(
            misc,
            text="CSV",
            width=48,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=lambda: self._export_me("csv"),
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            misc,
            text="JSON",
            width=52,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=lambda: self._export_me("json"),
        ).pack(side="right")
        ctk.CTkButton(
            misc,
            text="🧹 초기화",
            width=72,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._reset_me,
        ).pack(side="right", padx=(0, 6))

        # ── AI 코칭 설정 (선택) — 키/모델 행 분리 ──
        ai_key_row = ctk.CTkFrame(card, fg_color="transparent")
        ai_key_row.grid(row=3, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 2))
        ctk.CTkLabel(ai_key_row, text="AI 코칭 키", font=FU, width=90, anchor="w").pack(side="left")
        self.llm_key_var = tk.StringVar(value=self.settings.llm_api_key or "")
        ctk.CTkEntry(
            ai_key_row,
            textvariable=self.llm_key_var,
            font=FM,
            height=28,
            show="•",
            placeholder_text="opencode-go 키 (비우면 자동 감지)",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            ai_key_row,
            text="저장",
            width=52,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._save_llm_key,
        ).pack(side="left")

        ai_model_row = ctk.CTkFrame(card, fg_color="transparent")
        ai_model_row.grid(row=4, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(ai_model_row, text="AI 모델", font=FU, width=90, anchor="w").pack(side="left")
        from lol_coach import llm as _llm

        cur_model = self.settings.llm_model or _llm.DEFAULT_MODEL
        model_values = list(AI_MODELS)
        if cur_model not in model_values:
            model_values.insert(0, cur_model)
        self.llm_model_var = tk.StringVar(value=cur_model)
        ctk.CTkOptionMenu(
            ai_model_row,
            variable=self.llm_model_var,
            values=model_values,
            width=210,
            height=28,
            font=FM,
        ).pack(side="left", padx=(0, 8))
        self.ai_status_lbl = ctk.CTkLabel(
            ai_model_row, text="", font=FM, text_color=ui.TEXT_DIM
        )
        self.ai_status_lbl.pack(side="left")

        # ── 알림 설정 ──
        notify_row = ctk.CTkFrame(card, fg_color="transparent")
        notify_row.grid(row=5, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 10))
        self.game_end_notify_var = tk.BooleanVar(value=game_end_notify_enabled())
        ctk.CTkCheckBox(
            notify_row,
            text="게임 종료 알림 (소리 · 작업표시줄 깜빡임)",
            variable=self.game_end_notify_var,
            font=FU,
            command=self._on_game_end_notify_toggle,
        ).pack(side="left")
        ctk.CTkLabel(
            notify_row,
            text="꺼도 상태바·자동 복기는 그대로",
            font=FS,
            text_color=ui.TEXT_DIM,
        ).pack(side="left", padx=(12, 0))

        body = ctk.CTkFrame(self.t_me, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=3)
        body.grid_rowconfigure(1, weight=1)

        self.me_matches = ctk.CTkScrollableFrame(
            body,
            label_text="최근 경기 (클릭 → 복기)",
            corner_radius=10,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.me_matches.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        self.me_detail = ctk.CTkScrollableFrame(
            body,
            label_text="경기 복기 · 학습",
            corner_radius=10,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.me_detail.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 0))
        self.me_champs = ctk.CTkScrollableFrame(
            body,
            label_text="챔피언별 성적",
            corner_radius=10,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.BORDER,
        )
        self.me_champs.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(5, 0))
        self._lbl(
            self.me_matches,
            "API 키 + Riot ID로 최근 전적을 불러오세요.\n경기를 클릭하면 팀 조합·오브젝트·복기가 열립니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=320,
        )
        self._lbl(
            self.me_detail,
            "왼쪽 경기를 클릭하면\n아군/적군 5v5 · 오브젝트 · 학습 포인트가 표시됩니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=420,
        )


    def _show_api_help(self) -> None:
        from lol_coach.gui.api_help import open_api_key_help

        open_api_key_help(self)


    def _profile_labels(self) -> list[str]:
        from lol_coach.config import list_profiles

        labels = [
            f"{p['riot_id']} ({p.get('platform', 'kr')})"
            for p in list_profiles()
        ]
        return labels or ["(저장된 프로필 없음)"]


    def _refresh_profile_menu(self) -> None:
        try:
            self.profile_menu.configure(values=self._profile_labels())
        except Exception:
            pass


    def _on_profile_pick(self, label: str) -> None:
        if not label or label.startswith("("):
            return
        rid, _, tail = label.partition(" (")
        self.riot_id_var.set(rid)
        platform = tail.rstrip(")").strip()
        if platform:
            self.platform_var.set(platform)


    def _save_current_profile(self) -> None:
        from lol_coach.config import add_profile

        rid = self.riot_id_var.get().strip()
        from lol_coach.config import DEFAULT_PLATFORM

        platform = self.platform_var.get().strip() or DEFAULT_PLATFORM
        try:
            add_profile(rid, platform)
        except ValueError as exc:
            self._notify(str(exc), level="warn")
            return
        self._refresh_profile_menu()
        self.status.configure(text=f"프로필 저장됨 · {rid}")


    def _on_game_end_notify_toggle(self) -> None:
        """게임 종료 소리·작업표시줄 알림 on/off 즉시 저장."""
        on = bool(self.game_end_notify_var.get())
        try:
            set_game_end_notify(on)
        except Exception as exc:
            self._notify(f"알림 설정 저장 실패: {exc}", level="error")
            return
        if on:
            self._notify("게임 종료 알림 켜짐 (소리 · 작업표시줄)", level="ok", ms=2200)
        else:
            self._notify(
                "게임 종료 알림 끔 — 소리·깜빡임 없음 (복기는 유지)",
                level="info",
                ms=2800,
            )


    def _delete_current_profile(self) -> None:
        """현재 선택된 프로필을 삭제 (확인 후)."""
        from lol_coach.config import remove_profile

        label = self.profile_var.get()
        if not label or label.startswith("("):
            self._notify("삭제할 프로필을 먼저 선택하세요.", level="warn")
            return
        rid, _, tail = label.partition(" (")
        platform = tail.rstrip(")").strip()
        if not messagebox.askyesno(
            "프로필 삭제",
            f"'{rid}' 프로필을 삭제할까요?\n\n"
            "삭제는 목록에서만 제거되며, Riot 계정이나 전적에는 영향이 없습니다.",
        ):
            return
        try:
            remove_profile(rid)
        except Exception as exc:
            self._notify(f"프로필 삭제 실패: {exc}", level="error")
            return
        # 입력칸에서도 해당 Riot ID 제거 (현재 프로필이면 비움)
        if self.riot_id_var.get().strip() == rid:
            self.riot_id_var.set("")
            if platform == self.platform_var.get().strip():
                from lol_coach.config import DEFAULT_PLATFORM

                self.platform_var.set(DEFAULT_PLATFORM)
        self.profile_var.set("")
        self._refresh_profile_menu()
        self.status.configure(text=f"프로필 삭제됨 · {rid}")


    def _export_me(self, fmt: str) -> None:
        from tkinter import filedialog

        from lol_coach.analysis.export import (
            export_matches_csv,
            export_matches_json,
        )

        if self.form is None:
            self._notify("먼저 전적을 불러오세요.", level="warn")
            return
        rid = (self.profile.riot_id if self.profile else "matches").replace("#", "_")
        path = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            initialfile=f"lol_coach_{rid}.{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}")],
        )
        if not path:
            return
        try:
            if fmt == "json":
                out = export_matches_json(self.form, path)
            else:
                out = export_matches_csv(self.form, path)
        except Exception as exc:
            self._notify(f"내보내기 실패: {exc}", level="error")
            return
        self._notify(f"내보내기 완료 → {out}", level="ok", ms=4000)


    def _load_me(self) -> None:
        if self._is_busy("me_load"):
            # 이미 로드 중이면 조용히 무시하지 않고 안내
            self.status.configure(text="전적 로드 중… (완료되면 자동 표시)")
            return
        rid = self.riot_id_var.get().strip()
        if "#" not in rid:
            self._notify("Riot ID는 Name#TAG 형식이어야 합니다.", level="warn")
            return
        name, tag = rid.split("#", 1)
        key = self.api_key_var.get().strip()
        if not key:
            if messagebox.askyesno(
                "API 키가 없어요",
                "전적을 보려면 Riot API 키가 필요합니다.\n\n"
                "도움말을 열어 발급 방법을 볼까요?",
            ):
                self._show_api_help()
            return
        from lol_coach.config import DEFAULT_PLATFORM

        platform = self.platform_var.get().strip() or DEFAULT_PLATFORM
        try:
            save_api_key(key)
            save_player(name.strip(), tag.strip(), platform=platform)
            self.settings = load_settings()
        except Exception:
            pass

        self._busy_set(True, self.me_btn, "전적 로드", key="me_load")

        def work() -> None:
            try:
                client = RiotClient(api_key=key, platform=platform)
                profile = client.resolve_player(name.strip(), tag.strip())
                try:
                    count = int(self.count_var.get())
                except (TypeError, ValueError):
                    count = 15
                count = min(max(count, 5), 50)
                form = client.get_recent_form(profile, count=count)
                ranks: list = []
                try:
                    ranks = client.get_league_entries(profile.puuid)
                except RiotAPIError:
                    ranks = []
                self.riot, self.profile, self.form = client, profile, form
                self._last_ranks = ranks
                # 먼저 데이터로 렌더링 (아이콘은 placeholder) — 프리페치가
                # 수백 개 다운로드로 오래 걸려도 전적이 즉시 보이도록
                self.after(0, lambda: self._render_me(form, ranks))
                # 아이콘 프리페치 (백그라운드) — 완료되면 아이콘 포함 재렌더
                self._prefetch_match_icons(form)
            except RiotAPIError as e:
                from lol_coach.gui.errors import format_user_error

                msg = format_user_error(e)
                self.after(0, lambda: self._me_err(msg))
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                msg = format_user_error(e)
                self.after(0, lambda: self._me_err(msg))
            finally:
                self.after(0, lambda: self._busy_set(False, self.me_btn, "전적 로드", key="me_load"))

        threading.Thread(target=work, daemon=True).start()


    def _me_err(self, msg: str) -> None:
        self._clear(self.me_matches)
        self._clear(self.me_detail)
        self._clear(self.me_champs)
        self._lbl(self.me_matches, f"오류: {msg}", 0, color=ui.RED_SOFT, wrap=300)
        self._notify(msg, level="error", ms=5200)


    def _prefetch_match_icons(self, form: RecentForm) -> None:
        """전적 아이콘 백그라운드 프리페치 — 중복 제거 후 필요 크기만 다운로드.

        완료 시 같은 form 이 화면에 있을 때만 재렌더 (다른 탭/새 로드면 생략).
        """
        token = id(form)
        self._me_icon_token = token

        def _work() -> None:
            try:
                from lol_coach.static.icons import champion_pil, item_pil

                champs: set[str] = set()
                items: set[int] = set()
                for match in form.matches:
                    champs.add(match.champion_name)
                    for item_id in match.items:
                        if item_id:
                            items.add(int(item_id))
                    for player in [*match.ally_team, *match.enemy_team]:
                        champs.add(player.champion_name)
                        for item_id in player.items:
                            if item_id:
                                items.add(int(item_id))
                for champion in form.champion_stats.values():
                    champs.add(champion.champion_name)

                # 리스트/상세/풀 진단에 쓰는 크기만 (중복 호출 제거)
                for name in champs:
                    if not name:
                        continue
                    champion_pil(name, 32)
                    champion_pil(name, 40)
                    champion_pil(name, 52)
                for iid in items:
                    item_pil(iid, 22)
                    item_pil(iid, 28)
            except Exception:
                pass
            try:
                if (
                    getattr(self, "_me_icon_token", None) == token
                    and getattr(self, "form", None) is form
                    and self.me_matches.winfo_exists()
                ):
                    self.after(
                        0,
                        lambda: self._render_me(
                            form, getattr(self, "_last_ranks", [])
                        ),
                    )
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()


    def _reset_me(self) -> None:
        """내 전적 탭 입력·결과 전체 초기화 (API 키·저장된 .env/프로필은 유지)."""
        # 진행 중이던 로드 중단 처리 — 버튼/busy 정상화 (안 누른 것처럼)
        self._busy.discard("me_load")
        try:
            self.me_btn.configure(state="normal", text="전적 로드")
        except Exception:
            pass
        self.riot_id_var.set("")
        from lol_coach.config import DEFAULT_PLATFORM

        self.platform_var.set(DEFAULT_PLATFORM)
        # API 키 입력칸은 비우지 않음 — .env 에 저장된 키 유지 (재입력 방지)
        self.api_key_var.set(self.settings.riot_api_key or "")
        self.profile_var.set("")
        self.rank_lbl.configure(text="")
        self._clear(self.me_matches)
        self._clear(self.me_detail)
        self._clear(self.me_champs)
        self._lbl(
            self.me_matches,
            "API 키 + Riot ID로 최근 전적을 불러오세요.\n"
            "경기를 클릭하면 팀 조합·오브젝트·복기가 열립니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=320,
        )
        self._lbl(
            self.me_detail,
            "왼쪽 경기를 클릭하면\n아군/적군 5v5 · 오브젝트 · 학습 포인트가 표시됩니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=420,
        )
        self.riot = None
        self.profile = None
        self.form = None
        self.status.configure(text="전적 탭 초기화 — Riot ID만 입력하면 바로 로드")


    def _render_me(self, form: RecentForm, ranks: list | None = None) -> None:
        from lol_coach.static.icons import champion_ctk

        self._clear(self.me_matches)
        self._clear(self.me_champs)
        self._clear(self.me_detail)
        # 랭크 한 줄 (카드 상단 레이블)
        try:
            from lol_coach.display import rank_line

            line = rank_line(ranks or [])
            self.rank_lbl.configure(text=line.strip() if line else "언랭/기록 없음")
        except Exception:
            pass
        loc = self.loc
        r = 0
        r = self._lbl(
            self.me_matches,
            f"{form.profile.riot_id}\n"
            f"{form.wins}승 {form.losses}패 ({form.winrate}%) · KDA {form.avg_kda}\n"
            f"↓ 클릭하면 복기",
            r,
            font=FU,
            color=ui.TEXT_BRIGHT,
            pady=8,
            wrap=300,
        )
        # 트렌드 카드 + 미니 차트
        try:
            from lol_coach.analysis.trends import analyze_trends
            from lol_coach.gui.trend_viz import pack_kda_bars, pack_win_streak_bar

            trend = analyze_trends(form)
            r = self._sec(self.me_matches, "📈 최근 트렌드", r)
            if trend.win_sequence:
                bar = pack_win_streak_bar(self.me_matches, trend.win_sequence)
                bar.grid(row=r, column=0, sticky="ew", padx=8, pady=(2, 2))
                r += 1
            if trend.kda_sequence:
                kbar = pack_kda_bars(self.me_matches, trend.kda_sequence)
                kbar.grid(row=r, column=0, sticky="ew", padx=8, pady=(0, 4))
                r += 1
            sev_color = {
                "good": ui.GREEN,
                "warn": ui.WARN,
                "bad": ui.RED_SOFT,
                "info": ui.TEXT_DIM,
            }
            for line in trend.lines[:6]:
                col = sev_color.get(line.severity, ui.TEXT_DIM)
                r = self._lbl(
                    self.me_matches,
                    f"· {line.label}: {line.detail}",
                    r,
                    font=FM,
                    color=col,
                    pady=1,
                    wrap=300,
                )
            if trend.focus_note:
                r = self._lbl(
                    self.me_matches,
                    trend.focus_note,
                    r,
                    font=FM,
                    color=ui.GOLD_SOFT,
                    pady=4,
                    wrap=300,
                )
        except Exception:
            pass
        # 듀오 통계
        try:
            from lol_coach.analysis.duo import analyze_duos

            duo = analyze_duos(form, min_games=2, limit=6)
            if duo.partners:
                r = self._sec(self.me_matches, "👥 같이 뛴 소환사", r)
                for p in duo.partners:
                    col = (
                        ui.GREEN
                        if p.winrate >= 55
                        else (ui.RED_SOFT if p.winrate < 45 else ui.TEXT)
                    )
                    r = self._lbl(
                        self.me_matches,
                        f"· {p.riot_id}  {p.wins}승{p.losses}패 "
                        f"({p.winrate}%) · {p.games}판",
                        r,
                        font=FM,
                        color=col,
                        pady=1,
                        wrap=300,
                    )
            elif form.matches and duo.total_with_any == 0:
                r = self._lbl(
                    self.me_matches,
                    "듀오 통계: 아군 Riot ID가 비어 있어 집계 불가",
                    r,
                    font=FM,
                    color=ui.TEXT_MUTE,
                    pady=2,
                    wrap=300,
                )
        except Exception:
            pass
        for _i, m in enumerate(form.matches, 1):
            mark = "승" if m.win else "패"
            col = ui.GREEN if m.win else ui.RED_SOFT
            champ = loc.champion(m.champion_name) or m.champion_name
            ctx = loc.mode(m.mode_label) if "ARAM" in m.mode_label else loc.role(m.role)
            icon = self._keep_icon(champion_ctk(m.champion_name, 40))
            btn_kw: dict[str, Any] = {
                "text": (
                    f"[{mark}] {champ} · {ctx}\n"
                    f"{m.kda_str}  CS {m.cs}  {m.duration_min}분  ·  딜 {m.damage_to_champs:,}"
                ),
                "font": FM,
                "anchor": "w",
                "height": 56,
                "fg_color": ui.ROW,
                "hover_color": ui.ROW_HOVER,
                "text_color": col,
                "command": lambda mm=m: self._show_match_detail(mm),
            }
            if icon:
                btn_kw["image"] = icon
                btn_kw["compound"] = "left"
            btn = ctk.CTkButton(self.me_matches, **btn_kw)
            btn.grid(row=r, column=0, sticky="ew", padx=6, pady=2)
            r += 1

        cr = 0
        for c in sorted(
            form.champion_stats.values(), key=lambda x: (-x.games, -x.winrate)
        ):
            name = loc.champion(c.champion_name) or c.champion_name
            frame = ctk.CTkFrame(self.me_champs, fg_color=ui.ROW, corner_radius=10)
            frame.grid(row=cr, column=0, sticky="ew", padx=6, pady=2)
            ic = self._keep_icon(champion_ctk(c.champion_name, 32))
            if ic:
                ctk.CTkLabel(frame, image=ic, text="").pack(
                    side="left", padx=(8, 6), pady=5
                )
            ctk.CTkLabel(
                frame,
                text=f"{name}  {c.games}G {c.winrate}%  KDA {c.avg_kda}",
                font=FM,
                anchor="w",
            ).pack(side="left", padx=(0, 10), pady=6)
            cr += 1

        # ── 챔피언 풀 진단 ──
        if form.champion_stats:
            from lol_coach.analysis.pool import diagnose_pool

            verdict_color = {
                "집중": ui.GREEN,
                "유지": ui.TEXT,
                "표본 부족": ui.TEXT_DIM,
                "정리 검토": ui.WARN,
            }
            report = diagnose_pool(form)
            cr = self._sec(
                self.me_champs,
                f"풀 진단 (전체 승률 {report.overall_wr}%)",
                cr,
            )
            for e in report.entries:
                if e.verdict == "표본 부족" and len(report.entries) > 6:
                    continue  # 챔프가 많으면 판정 불가는 접어둠
                name = loc.champion(e.champion_name) or e.champion_name
                cr = self._lbl(
                    self.me_champs,
                    f"【{e.verdict}】 {name} — {e.reason}",
                    cr,
                    font=FM,
                    color=verdict_color.get(e.verdict),
                    wrap=320,
                    pady=2,
                )

        self._lbl(
            self.me_detail,
            "왼쪽 경기를 클릭하면 팀 조합·오브젝트·학습 포인트가 여기에 표시됩니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=420,
        )
        self.status.configure(text=f"전적 로드 · {form.profile.riot_id}")
        # 첫 경기 자동 선택
        if form.matches:
            self._show_match_detail(form.matches[0])


    def _show_match_detail(self, m: MatchSummary) -> None:
        """한 판 복기 패널."""
        from lol_coach.static.icons import champion_ctk, item_ctk

        self._clear(self.me_detail)
        loc = self.loc
        loc.ensure_loaded()
        champ = loc.champion(m.champion_name) or m.champion_name
        role = loc.role(m.role)
        mode = loc.mode(m.mode_label)
        mark = "승리" if m.win else "패배"
        col = ui.GREEN if m.win else ui.RED_SOFT

        r = 0
        head = self._row_frame(self.me_detail, r, pady=6)
        cicon = self._keep_icon(champion_ctk(m.champion_name, 52))
        if cicon:
            ctk.CTkLabel(head, image=cicon, text="").pack(
                side="left", padx=(10, 10), pady=8
            )
        ctk.CTkLabel(
            head,
            text=f"[{mark}]  {champ} · {role}  ·  {mode}\n"
            f"{m.duration_min}분  ·  {m.kda_str} (KDA {m.kda_ratio})  ·  "
            f"CS {m.cs} ({m.cs_per_min}/분)  ·  Lv{m.champ_level}",
            font=FS,
            text_color=col,
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(0, 12), pady=8)
        r += 1

        # 핵심 지표
        r = self._sec(self.me_detail, "내 지표", r)
        kp = ""
        if m.kill_participation is not None:
            kp_v = m.kill_participation * 100 if m.kill_participation <= 1 else m.kill_participation
            kp = f"킬관여 {kp_v:.0f}%"
        ds = ""
        if m.damage_share is not None:
            ds_v = m.damage_share * 100 if m.damage_share <= 1 else m.damage_share
            ds = f"딜지분 {ds_v:.0f}%"
        bits = [
            f"딜 {m.damage_to_champs:,}",
            f"받은 피해 {m.damage_taken:,}",
            f"골드 {m.gold:,}" + (f" ({m.gold_per_min}/분)" if m.gold_per_min else ""),
            f"비전 {m.vision_score}",
            f"와드 {m.wards_placed}/{m.wards_killed} (제어 {m.control_wards})",
            f"포탑 파괴 {m.turret_kills}",
        ]
        if kp:
            bits.insert(0, kp)
        if ds:
            bits.insert(1, ds)
        if m.first_blood:
            bits.append("선취혈")
        if m.solo_kills:
            bits.append(f"솔킬 {m.solo_kills}")
        if m.largest_multi_kill >= 2:
            bits.append(f"멀티킬 {m.largest_multi_kill}")
        r = self._lbl(self.me_detail, "  ·  ".join(bits), r, font=FM, wrap=480, pady=4)

        # 아이템 아이콘 행
        if m.items:
            r = self._sec(self.me_detail, "아이템", r)
            items_frame = self._row_frame(self.me_detail, r, pady=3)
            names = self.dd.item_names(m.items) if m.items else []
            for idx, iid in enumerate(m.items[:7]):
                if not iid:
                    continue
                ic = self._keep_icon(item_ctk(int(iid), 28))
                cell = ctk.CTkFrame(items_frame, fg_color="transparent")
                cell.pack(side="left", padx=4, pady=6)
                if ic:
                    ctk.CTkLabel(cell, image=ic, text="").pack()
                label = names[idx] if idx < len(names) else str(iid)
                ctk.CTkLabel(cell, text=label[:8], font=FM, text_color=ui.TEXT_DIM).pack()
            r += 1

        # 오브젝트
        r = self._sec(self.me_detail, "오브젝트 (아군 : 적군)", r)
        if m.obj:
            a, e = m.obj.ally, m.obj.enemy
            r = self._lbl(
                self.me_detail,
                f"드래곤  {a.dragons} : {e.dragons}    "
                f"바론  {a.barons} : {e.barons}    "
                f"전령  {a.heralds} : {e.heralds}",
                r,
                font=FU,
                wrap=480,
            )
            r = self._lbl(
                self.me_detail,
                f"포탑  {a.towers} : {e.towers}    "
                f"억제기  {a.inhibitors} : {e.inhibitors}"
                + (f"    공허 유충  {a.grubs} : {e.grubs}" if (a.grubs or e.grubs) else ""),
                r,
                font=FU,
                wrap=480,
            )
        else:
            r = self._lbl(self.me_detail, "오브젝트 정보 없음", r, color=ui.TEXT_DIM)

        # 팀 조합
        r = self._sec(self.me_detail, "아군 조합", r)
        r = self._render_team_block(self.me_detail, m.ally_team, r, ally=True)
        r = self._sec(self.me_detail, "적군 조합", r)
        r = self._render_team_block(self.me_detail, m.enemy_team, r, ally=False)

        # ── 타임라인 요약 (백그라운드 fetch, 실패 시 조용히 생략) ──
        tl_row = r
        r = self._sec(self.me_detail, "타임라인", r)
        r = self._lbl(
            self.me_detail,
            "불러오는 중…",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            wrap=480,
        )
        riot = getattr(self, "riot", None)
        if riot is not None:
            match_id = m.match_id
            pid = (m.raw_participant or {}).get("participantId")
            try:
                pid = int(pid) if pid else None
            except (TypeError, ValueError):
                pid = None

            def _tl_work() -> None:
                try:
                    from lol_coach.analysis.review import timeline_brief

                    tl = riot.get_match_timeline(match_id)
                    lines = timeline_brief(tl, my_participant_id=pid)
                except Exception:
                    lines = []
                self.after(0, lambda ls=lines: self._apply_timeline(tl_row, ls))

            threading.Thread(target=_tl_work, daemon=True).start()

        # 심화 복기
        rev = analyze_match(m)
        title_reason = "이 게임을 이긴 주요 이유" if m.win else "이 게임을 진 주요 이유"
        r = self._sec(self.me_detail, title_reason, r)
        for i, t in enumerate(rev.win_loss_reasons, 1):
            r = self._lbl(
                self.me_detail,
                f"{i}.  {t}",
                r,
                color=(ui.BLUE_SOFT if m.win else ui.RED_SOFT),
                wrap=480,
                pady=3,
            )

        r = self._sec(self.me_detail, "내 플레이 — 잘한 점", r)
        for t in rev.good:
            r = self._lbl(self.me_detail, f"✓  {t}", r, color=ui.GREEN, wrap=480, pady=2)

        r = self._sec(self.me_detail, "내 플레이 — 개선할 점 (다음 판 행동)", r)
        for t in rev.improve:
            r = self._lbl(self.me_detail, f"→  {t}", r, color=ui.WARN, wrap=480, pady=2)

        # 한 줄 교훈 강조
        frame = ctk.CTkFrame(
            self.me_detail,
            fg_color=ui.PANEL,
            corner_radius=10,
            border_width=1,
            border_color=ui.GOLD,
        )
        frame.grid(row=r, column=0, sticky="ew", padx=10, pady=(14, 6))
        ctk.CTkLabel(
            frame,
            text=f"다음 경기 교훈\n{rev.lesson}",
            font=FU,
            text_color=ui.GOLD_SOFT,
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(anchor="w", padx=14, pady=12)
        r += 1

        r = self._lbl(
            self.me_detail,
            f"매치 ID  {m.match_id}",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=(8, 8),
            wrap=480,
        )

        # 미니 위젯용 요약 — 방금 판 결과를 위젯에서 바로 확인
        summary = [
            f"[{mark}] {champ} · {role}  ·  {m.duration_min}분",
            f"KDA {m.kda_str}  ·  CS {m.cs}  ·  딜 {m.damage_to_champs:,}",
        ]
        if kp:
            summary.append(f"킬관여 {kp}")
        try:
            if rev.win_loss_reasons:
                summary.append("")
                summary.append("주요 원인: " + rev.win_loss_reasons[0])
            if rev.improve:
                summary.append("")
                summary.append("개선: " + rev.improve[0])
            if rev.lesson:
                summary.append("")
                summary.append("교훈: " + rev.lesson)
        except Exception:
            pass
        self._push_summary(
            f"🔔 방금 게임 {champ} {mark}", summary
        )
        key = self._ai_key()
        if key:
            self._maybe_ai(
                self.me_detail,
                lambda: self._ai_coach_review(m, rev, key),
            )


    def _apply_timeline(self, tl_row: int, lines: list[str]) -> None:
        """타임라인 fetch 결과를 복기 패널에 반영 (빈 결과면 자리만 제거)."""
        try:
            row = tl_row
            for w in self.me_detail.winfo_children():
                try:
                    txt = str(w.cget("text"))
                except Exception:
                    txt = ""
                if txt == "불러오는 중…":
                    info = w.grid_info()
                    try:
                        row = int(info.get("row", tl_row))
                    except (TypeError, ValueError):
                        row = tl_row
                    w.destroy()
            if lines:
                self._lbl(
                    self.me_detail,
                    " · ".join(lines),
                    row,
                    font=FM,
                    color=ui.TEXT_DIM,
                    wrap=480,
                )
        except Exception:
            pass


    def _render_team_block(
        self, parent: Any, players: list, row: int, *, ally: bool
    ) -> int:
        from lol_coach.static.icons import champion_ctk, item_ctk

        loc = self.loc
        if not players:
            return self._lbl(parent, "참가자 정보 없음", row, color=ui.TEXT_DIM)
        for p in players:
            champ = loc.champion(p.champion_name) or p.champion_name
            role = loc.role(p.role)
            me = "  ★나" if p.is_me else ""
            bg = "#132238" if p.is_me else ui.ROW
            frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8)
            frame.grid(row=row, column=0, sticky="ew", padx=10, pady=2)

            left = ctk.CTkFrame(frame, fg_color="transparent")
            left.pack(side="left", padx=(8, 6), pady=6)
            ic = self._keep_icon(champion_ctk(p.champion_name, 40))
            if ic:
                ctk.CTkLabel(left, image=ic, text="").pack()

            mid = ctk.CTkFrame(frame, fg_color="transparent")
            mid.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=4)
            ctk.CTkLabel(
                mid,
                text=f"{role}  {champ}{me}\n"
                f"{p.kda_str}  CS {p.cs}  딜 {p.damage_to_champs:,}  "
                f"골드 {p.gold:,}  시야 {p.vision_score}  Lv{p.champ_level}",
                font=FM,
                anchor="w",
                justify="left",
            ).pack(anchor="w")

            if p.items:
                items_row = ctk.CTkFrame(mid, fg_color="transparent")
                items_row.pack(anchor="w", pady=(3, 0))
                for iid in p.items[:6]:
                    if not iid:
                        continue
                    iic = self._keep_icon(item_ctk(int(iid), 22))
                    if iic:
                        ctk.CTkLabel(items_row, image=iic, text="").pack(
                            side="left", padx=1
                        )
            row += 1
        return row

