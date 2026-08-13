"""내 전적 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.export import export_matches_csv, export_matches_json
from lol_coach.analysis.pool import diagnose_pool
from lol_coach.config import (
    DEFAULT_PLATFORM,
    Settings,
    add_profile,
    auto_open_latest_match_enabled,
    list_profiles,
    load_settings,
    remove_profile,
    save_api_key,
    save_player,
    set_auto_open_latest_match,
    set_discord_review,
    set_game_end_auto_review,
    set_game_end_notify,
    set_game_start_notify,
)
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FU, PLATFORMS
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger
from lol_coach.modes import (
    ARAM_QUEUES,
    QUEUE_ARAM_MAYHEM,
    QUEUE_NORMAL_BLIND,
    QUEUE_NORMAL_DRAFT,
    QUEUE_RANKED_FLEX,
    QUEUE_RANKED_SOLO,
)
from lol_coach.riot.client import RiotAPIError, RiotClient, aggregate_form
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm
from lol_coach.static.icons import champion_ctk

_log = get_logger("me")

# 내 전적 큐 필터 (None = 전체)
_ME_QUEUE_FILTERS: list[tuple[str, set[int] | None]] = [
    ("전체", None),
    ("솔랭", {QUEUE_RANKED_SOLO}),
    ("자유랭크", {QUEUE_RANKED_FLEX}),
    ("일반", {QUEUE_NORMAL_DRAFT, QUEUE_NORMAL_BLIND}),
    ("칼바람", set(ARAM_QUEUES) - {QUEUE_ARAM_MAYHEM}),
    ("아수라장", {QUEUE_ARAM_MAYHEM}),
]


class MeTabMixin(MixinBase):
    riot: RiotClient | None
    profile: PlayerProfile | None
    form: RecentForm | None
    _me_form_full: RecentForm | None

    def _schedule_me_load(self, generation: int, callback: Callable[[], None]) -> None:
        def apply() -> None:
            if generation == getattr(self, "_me_load_gen", -1):
                callback()

        self.after(0, apply)

    def _build_me(self) -> None:
        card = ctk.CTkFrame(
            self.t_me,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
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
        self.rank_lbl = ctk.CTkLabel(misc, text="", font=FM, text_color=ui.TEXT_DIM)
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
        # AI·알림·배율 등은 헤더 「⚙ 설정」으로 이동 (전적 영역 확보)

        # ── 큐 필터 칩 (row 3) ──
        filt = ctk.CTkFrame(card, fg_color="transparent")
        filt.grid(row=3, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(filt, text="필터", font=FM, text_color=ui.TEXT_DIM).pack(side="left")
        self._me_filter_btns: list[ctk.CTkButton] = []
        for label, _qset in _ME_QUEUE_FILTERS:
            btn = ctk.CTkButton(
                filt,
                text=label,
                width=64,
                height=24,
                font=FM,
                **ui.btn(*ui.BTN_TERTIARY),
                command=lambda lab=label: self._set_me_filter(lab),
            )
            btn.pack(side="left", padx=(4, 0))
            self._me_filter_btns.append(btn)
        # 기존 필터 유지 (스킨 변경 리빌드 시에도 선택 보존)
        cur_label = "전체"
        for lab, qset in _ME_QUEUE_FILTERS:
            if qset == getattr(self, "_me_queue_filter", None):
                cur_label = lab
                break
        self._set_me_filter(cur_label, rerender=False)

        body = ctk.CTkFrame(self.t_me, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=3)
        body.grid_rowconfigure(1, weight=1)

        self.me_matches = ctk.CTkScrollableFrame(
            body,
            label_text="최근 경기 (클릭 → 복기)",
            corner_radius=ui.CARD_RADIUS,
            fg_color=ui.PANEL,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        self.me_matches.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        self.me_detail = ctk.CTkScrollableFrame(
            body,
            label_text="경기 복기 · 학습",
            corner_radius=ui.CARD_RADIUS,
            fg_color=ui.PANEL,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        self.me_detail.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 0))
        self.me_champs = ctk.CTkScrollableFrame(
            body,
            label_text="챔피언별 성적",
            corner_radius=ui.CARD_RADIUS,
            fg_color=ui.PANEL,
            border_width=ui.CARD_BORDER,
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
        labels = [f"{p['riot_id']} ({p.get('platform', 'kr')})" for p in list_profiles()]
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
        rid = self.riot_id_var.get().strip()
        platform = self.platform_var.get().strip() or DEFAULT_PLATFORM
        try:
            add_profile(rid, platform)
        except ValueError as exc:
            self._notify(str(exc), level="warn")
            return
        self._refresh_profile_menu()
        self.status.configure(text=f"프로필 저장됨 · {rid}")

    def _on_discord_review_toggle(self) -> None:
        """게임 종료 시 디스코드 복기 카드 자동 전송 on/off."""
        on = bool(self.discord_review_var.get())
        try:
            set_discord_review(on)
        except Exception as exc:
            self._notify(f"디스코드 자동 전송 설정 저장 실패: {exc}", level="error")
            return
        if on:
            self._notify(
                "게임 종료 시 디스코드로 복기 카드 자동 전송 켜짐",
                level="ok",
                ms=2400,
            )
        else:
            self._notify("디스코드 자동 전송 끔", level="info", ms=2000)

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
                "게임 종료 알림 끔 — 소리·깜빡임 없음",
                level="info",
                ms=2400,
            )

    def _on_game_start_notify_toggle(self) -> None:
        """게임 시작 알림 on/off 즉시 저장."""
        on = bool(self.game_start_notify_var.get())
        try:
            set_game_start_notify(on)
        except Exception as exc:
            self._notify(f"게임 시작 알림 설정 저장 실패: {exc}", level="error")
            return
        if on:
            self._notify("게임 시작 알림 켜짐 (소리 · 상태바 · 위젯)", level="ok", ms=2200)
        else:
            self._notify("게임 시작 알림 끔", level="info", ms=2000)

    def _on_game_end_auto_review_toggle(self) -> None:
        """게임 종료 시 복기 패널 자동 열기 on/off."""
        on = bool(self.game_end_auto_review_var.get())
        try:
            set_game_end_auto_review(on)
        except Exception as exc:
            self._notify(f"자동 복기 설정 저장 실패: {exc}", level="error")
            return
        if on:
            self._notify(
                "게임 종료 시 복기 패널을 자동으로 엽니다",
                level="ok",
                ms=2400,
            )
        else:
            self._notify(
                "종료 시 자동 복기 끔 — 상태바 알림만 (목록에서 선택)",
                level="info",
                ms=2800,
            )

    def _on_auto_open_latest_toggle(self) -> None:
        """전적 로드 시 최근 1판 자동 복기 on/off."""
        on = bool(self.auto_open_latest_var.get())
        try:
            set_auto_open_latest_match(on)
        except Exception as exc:
            self._notify(f"자동 복기 설정 저장 실패: {exc}", level="error")
            return
        if on:
            self._notify(
                "전적 로드 시 최근 1판을 자동으로 엽니다",
                level="ok",
                ms=2400,
            )
        else:
            self._notify(
                "자동 복기 끔 — 왼쪽 목록에서 경기를 선택하세요",
                level="info",
                ms=2600,
            )

    def _should_auto_open_latest(self) -> bool:
        var = getattr(self, "auto_open_latest_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            return auto_open_latest_match_enabled()
        except Exception:
            return False

    def _delete_current_profile(self) -> None:
        """현재 선택된 프로필을 삭제 (확인 후)."""
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
                self.platform_var.set(DEFAULT_PLATFORM)
        self.profile_var.set("")
        self._refresh_profile_menu()
        self.status.configure(text=f"프로필 삭제됨 · {rid}")

    def _export_me(self, fmt: str) -> None:
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

    def _export_growth_card(self) -> None:
        form = getattr(self, "_me_form_full", None) or getattr(self, "form", None)
        report = getattr(self, "_growth_report", None)
        if form is None or report is None:
            self._notify("전적을 먼저 불러와 주세요.", level="warn")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile="롤실전코치-주간성장.png",
        )
        if not path:
            return
        try:
            from lol_coach.analysis.growth import render_growth_card

            output = render_growth_card(
                form.profile.riot_id,
                report,
                getattr(self, "_practice_progress", None),
                path,
            )
            self._notify(f"성장 카드 저장 완료: {output.name}", level="ok")
        except (OSError, ValueError) as exc:
            self._notify(f"성장 카드 저장 실패: {exc}", level="error")

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
        platform = self.platform_var.get().strip() or DEFAULT_PLATFORM
        if not key:
            # 키 없음 → 로컬 전적 모드로 즉시 시도
            self._load_me_local(count=None, platform=platform)
            return
        try:
            save_api_key(key)
            save_player(name.strip(), tag.strip(), platform=platform)
            self.settings: Settings = load_settings()
        except Exception as exc:
            from lol_coach.log import get_logger as _get_logger

            _get_logger("me").warning("설정 저장 실패: %s", exc)
            self._notify("설정 저장에 실패했습니다 (계속 진행).", level="warn")

        self._busy_set(True, self.me_btn, "전적 로드", key="me_load")

        # tkinter 변수는 메인 스레드에서만 읽는다 (워커에서 Tcl 호출 금지)
        try:
            count = int(self.count_var.get())
        except (TypeError, ValueError):
            count = 15
        count = min(max(count, 5), 50)
        load_gen = int(getattr(self, "_me_load_gen", 0)) + 1
        self._me_load_gen = load_gen

        def work() -> None:
            try:
                client = RiotClient(api_key=key, platform=platform)
                profile = client.resolve_player(name.strip(), tag.strip())
                form = client.get_recent_form(profile, count=count)
                ranks: list = []
                try:
                    ranks = client.get_league_entries(profile.puuid)
                except RiotAPIError:
                    ranks = []

                def finish_success() -> None:
                    try:
                        self.riot = client
                        self._me_local_mode = False
                        self.profile = profile
                        self.form = form
                        self._me_form_full = form
                        self._last_ranks = ranks
                        from lol_coach.analysis.growth import load_growth

                        growth, practice = load_growth(form, now_ms=int(time.time() * 1000))
                        self._growth_report = growth
                        self._practice_progress = practice
                        self._render_me(form, ranks)
                        self._prefetch_match_icons(form)
                        self._start_game_start_watcher()
                        self._start_game_end_watcher()
                    finally:
                        self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

                self._schedule_me_load(load_gen, finish_success)
            except RiotAPIError as e:
                from lol_coach.gui.errors import format_user_error

                key_problem = getattr(e, "status_code", None) == 403
                fallback = format_user_error(e)

                def finish_riot_error() -> None:
                    self._load_me_local(
                        count=count,
                        platform=platform,
                        key_problem=key_problem,
                        fallback_msg=fallback,
                    )
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

                self._schedule_me_load(load_gen, finish_riot_error)
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                fallback = format_user_error(e)

                def finish_error() -> None:
                    self._load_me_local(count=count, platform=platform, fallback_msg=fallback)
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

                self._schedule_me_load(load_gen, finish_error)

        threading.Thread(target=work, daemon=True).start()

    def _load_me_local(
        self,
        *,
        count: int | None,
        platform: str,
        key_problem: bool = False,
        fallback_msg: str = "",
    ) -> None:
        """Riot API 없이 LCU 로컬 전적으로 전적 로드 (폴백 경로).

        key_problem: 403 만료 등 키 문제로 넘어온 경우 (개인 키 안내 다이얼로그).
        """
        from lol_coach.analysis.lcu_match import build_local_form
        from lol_coach.lcu import LCUClient, LCUError
        from lol_coach.riot.models import PlayerProfile

        if count is None:
            try:
                count = int(self.count_var.get())
            except (TypeError, ValueError):
                count = 15
        count = min(max(count, 5), 50)
        load_gen = int(getattr(self, "_me_load_gen", 0)) + 1
        self._me_load_gen = load_gen
        name, tag = self.riot_id_var.get().split("#", 1)

        def work() -> None:
            local_err = ""
            form = None
            try:
                lcu = LCUClient()
                profile = PlayerProfile(
                    game_name=name.strip(),
                    tag_line=tag.strip(),
                    puuid="",
                    platform=platform,
                )
                form, local_err = build_local_form(
                    lcu, count, profile, id_to_key=self.dd.champion_key
                )
            except LCUError as exc:
                local_err = str(exc)
            except Exception as exc:
                local_err = str(exc)

            def finish() -> None:
                try:
                    if form is not None:
                        self._me_local_mode = True
                        for attr in ("_game_start_watcher", "_watcher"):
                            w = getattr(self, attr, None)
                            if w is not None:
                                try:
                                    w.stop()
                                except Exception:
                                    pass
                            setattr(self, attr, None)
                        self.riot = None  # 로컬 모드 — Riot API 워처 중지/미시작
                        self.profile = PlayerProfile(
                            game_name=name.strip(),
                            tag_line=tag.strip(),
                            puuid="",
                            platform=platform,
                        )
                        self.form = form
                        self._me_form_full = form
                        self._last_ranks = []
                        from lol_coach.analysis.growth import load_growth

                        growth, practice = load_growth(form, now_ms=int(time.time() * 1000))
                        self._growth_report = growth
                        self._practice_progress = practice
                        self._render_me(form, [])
                        self._prefetch_match_icons(form)
                        mode_text = "로컬 전적 모드 (롤 클라이언트 전적 · API 키 불필요)"
                        if key_problem:
                            mode_text += " — Riot API 키 문제로 전환됨"
                        self.status.configure(text=mode_text)
                        if key_problem:
                            self._maybe_show_personal_key_dialog()
                    else:
                        msg = local_err or fallback_msg or "전적을 불러오지 못했습니다."
                        self._me_err(msg)
                        if key_problem and not local_err:
                            self._maybe_show_personal_key_dialog()
                finally:
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

            self._schedule_me_load(load_gen, finish)

        threading.Thread(target=work, daemon=True).start()

    def _maybe_show_personal_key_dialog(self) -> None:
        """개인 키(Personal App) 안내 — 세션당 1회."""
        if getattr(self, "_personal_key_dialog_shown", False):
            return
        self._personal_key_dialog_shown = True
        try:
            from tkinter import messagebox

            messagebox.showinfo(
                "Riot API 키 안내",
                "개발용(Development) 키는 24시간마다 만료됩니다.\n\n"
                "developer.riotgames.com 에서 앱을 'Personal' 유형으로 등록하면\n"
                "만료 없이 장기간 사용할 수 있는 개인 키를 받을 수 있어요.\n\n"
                "지금은 키 없이도 롤 클라이언트 전적으로 계속 사용 중입니다.",
            )
        except Exception:
            pass

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
            except Exception as exc:
                _log.debug("전적 아이콘 프리페치 실패(무시): %s", exc)

            def render_if_current() -> None:
                if (
                    getattr(self, "_me_icon_token", None) == token
                    and getattr(self, "_me_form_full", None) is form
                    and self.me_matches.winfo_exists()
                ):
                    self._render_me(form, getattr(self, "_last_ranks", []))

            try:
                self.after(0, render_if_current)
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True).start()

    def _reset_me(self) -> None:
        """내 전적 탭 입력·결과 전체 초기화 (API 키·저장된 .env/프로필은 유지)."""
        # 진행 중이던 로드 중단 처리 — 버튼/busy 정상화 (안 누른 것처럼)
        self._busy.discard("me_load")
        self._me_load_gen = int(getattr(self, "_me_load_gen", 0)) + 1
        self._me_detail_gen = int(getattr(self, "_me_detail_gen", 0)) + 1
        try:
            self.me_btn.configure(state="normal", text="전적 로드")
        except Exception:
            pass
        self.riot_id_var.set("")
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
        self._me_form_full = None
        self.status.configure(text="전적 탭 초기화 — Riot ID만 입력하면 바로 로드")

    def _set_me_filter(self, label: str, *, rerender: bool = True) -> None:
        """내 전적 큐 필터 칩 선택 — 선택 상태 표시 + 재렌더."""
        for lab, qset in _ME_QUEUE_FILTERS:
            if lab == label:
                self._me_queue_filter = qset
                break
        for btn in getattr(self, "_me_filter_btns", []) or []:
            try:
                selected = btn.cget("text") == label
            except Exception:
                continue
            btn.configure(
                fg_color=ui.GOLD if selected else ui.PANEL,
                hover_color=ui.GOLD_HOVER if selected else ui.ROW_HOVER,
                text_color=ui.ON_GOLD if selected else ui.GOLD_SOFT,
            )
        if rerender:
            form = getattr(self, "_me_form_full", None)
            if form is not None:
                self._render_me(form, getattr(self, "_last_ranks", None))

    def _scroll_me_matches_top(self) -> None:
        try:
            canvas = getattr(self.me_matches, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0)
        except Exception:
            pass

    def _set_me_summary_expanded(self, expanded: bool) -> None:
        """트렌드·듀오 요약 접기/펼치기 (경기 목록이 항상 위에 오도록 아래에 배치)."""
        self._me_summary_expanded = bool(expanded)
        host = getattr(self, "_me_summary_host", None)
        btn = getattr(self, "_me_summary_btn", None)
        if host is not None:
            try:
                if expanded:
                    host.grid()
                else:
                    host.grid_remove()
            except Exception:
                pass
        if btn is not None:
            try:
                n = int(getattr(self, "_me_summary_hint_n", 0) or 0)
                if expanded:
                    btn.configure(text="▲ 트렌드·듀오 접기")
                else:
                    extra = f" ({n})" if n else ""
                    btn.configure(text=f"▼ 트렌드·듀오 보기{extra}")
            except Exception:
                pass

    def _toggle_me_summary(self) -> None:
        self._set_me_summary_expanded(not getattr(self, "_me_summary_expanded", False))

    def _fill_me_summary(self, host: Any, form: RecentForm) -> int:
        """트렌드·듀오 내용을 host 안에 채운다. 넣은 줄 수 힌트를 반환."""
        lines_n = 0
        sr = 0
        try:
            from lol_coach.analysis.trends import analyze_trends
            from lol_coach.gui.trend_viz import pack_kda_bars, pack_win_streak_bar

            trend = analyze_trends(form)
            sr = self._sec(host, "📈 최근 트렌드", sr)
            if trend.win_sequence:
                bar = pack_win_streak_bar(host, trend.win_sequence)
                bar.grid(row=sr, column=0, sticky="ew", padx=8, pady=(2, 2))
                sr += 1
                lines_n += 1
            if trend.kda_sequence:
                kbar = pack_kda_bars(host, trend.kda_sequence)
                kbar.grid(row=sr, column=0, sticky="ew", padx=8, pady=(0, 4))
                sr += 1
                lines_n += 1
            if trend.practice_target is not None:
                target = trend.practice_target
                sr = self._lbl(
                    host,
                    (
                        f"이번 연습 목표 · 최근 소환사의 협곡 {target.sample_games}판 중 "
                        f"{target.observed_games}판에서 데스 {target.threshold}+ 관찰됨\n"
                        "→ 다음 판은 첫 데스 전 웨이브와 시야를 우선하세요"
                    ),
                    sr,
                    font=FM,
                    color=ui.WARN,
                    pady=4,
                    wrap=320,
                )
                lines_n += 1
            sev_color = {
                "good": ui.GREEN,
                "warn": ui.WARN,
                "bad": ui.RED_SOFT,
                "info": ui.TEXT_DIM,
            }
            for line in trend.lines[:6]:
                col = sev_color.get(line.severity, ui.TEXT_DIM)
                sr = self._lbl(
                    host,
                    f"· {line.label}: {line.detail}",
                    sr,
                    font=FM,
                    color=col,
                    pady=1,
                    wrap=300,
                )
                lines_n += 1
            if trend.focus_note:
                sr = self._lbl(
                    host,
                    trend.focus_note,
                    sr,
                    font=FM,
                    color=ui.GOLD_SOFT,
                    pady=4,
                    wrap=300,
                )
                lines_n += 1
        except Exception as exc:
            _log.debug("트렌드 요약 렌더 실패(무시): %s", exc)
        growth = getattr(self, "_growth_report", None)
        if growth is not None:
            weekly = growth.weekly
            sr = self._sec(host, "📅 주간 성장", sr)
            if weekly.current.games:
                previous = weekly.previous
                delta = (
                    f"{weekly.winrate_delta:+.1f}%p"
                    if weekly.winrate_delta is not None
                    else "이전 주 표본 없음"
                )
                sr = self._lbl(
                    host,
                    f"이번 주 {weekly.current.games}판 · 승률 {weekly.current.winrate:.1f}% · {delta}",
                    sr,
                    font=FM,
                    color=ui.TEXT_BRIGHT,
                    wrap=300,
                )
                sr = self._lbl(
                    host,
                    f"KDA {weekly.current.avg_kda:.2f} · 평균 데스 {weekly.current.avg_deaths:.1f} · "
                    f"CS/분 {weekly.current.avg_cs_per_min:.1f}"
                    + (f"\n이전 주 {previous.games}판과 자동 비교" if previous.games else ""),
                    sr,
                    font=FM,
                    color=ui.TEXT_DIM,
                    wrap=300,
                )
                lines_n += 2
            else:
                sr = self._lbl(
                    host,
                    "이번 주 완료된 경기가 없습니다.",
                    sr,
                    font=FM,
                    color=ui.TEXT_MUTE,
                    wrap=300,
                )
                lines_n += 1

            practice = getattr(self, "_practice_progress", None)
            if practice is not None:
                if practice.graded_games:
                    practice_text = (
                        f"숙제 채점 · {practice.successes}/{practice.graded_games}판 성공 "
                        f"({practice.completion_rate:.1f}%)"
                    )
                    practice_color = ui.GREEN if practice.completion_rate >= 60 else ui.WARN
                else:
                    practice_text = "숙제 배정 완료 · 다음 소환사의 협곡부터 자동 채점"
                    practice_color = ui.WARN
                sr = self._lbl(
                    host,
                    practice_text,
                    sr,
                    font=FM,
                    color=practice_color,
                    wrap=300,
                )
                lines_n += 1

            if growth.habits:
                sr = self._sec(host, "🔮 습관 스캐너", sr)
                habit_colors = {"good": ui.GREEN, "bad": ui.RED_SOFT, "info": ui.TEXT_DIM}
                for signal in growth.habits:
                    sr = self._lbl(
                        host,
                        f"· {signal.label}: {signal.detail}",
                        sr,
                        font=FM,
                        color=habit_colors.get(signal.severity, ui.TEXT_DIM),
                        wrap=300,
                    )
                    lines_n += 1
            from lol_coach.analysis.growth import diagnose_playstyle, records_from_form

            diagnosis = diagnose_playstyle(records_from_form(form))
            if diagnosis is not None:
                sr = self._sec(host, "🧬 플레이 유형", sr)
                sr = self._lbl(
                    host,
                    f"{diagnosis.name} · {diagnosis.code} · 소환사의 협곡 {diagnosis.sample_games}판",
                    sr,
                    font=FM,
                    color=ui.GOLD_SOFT,
                    wrap=300,
                )
                axes = " · ".join(f"{axis.label} {axis.score}" for axis in diagnosis.axes)
                sr = self._lbl(
                    host,
                    axes,
                    sr,
                    font=FM,
                    color=ui.TEXT_DIM,
                    wrap=300,
                )
                lines_n += 2
            actions = ctk.CTkFrame(host, fg_color="transparent")
            actions.grid(row=sr, column=0, sticky="ew", padx=8, pady=(5, 8))
            ctk.CTkButton(
                actions,
                text="PNG 성장 카드 저장",
                height=28,
                font=FM,
                **ui.btn(*ui.BTN_SECONDARY),
                command=self._export_growth_card,
            ).pack(side="left")
            sr += 1
            lines_n += 1
        try:
            from lol_coach.analysis.duo import analyze_duos

            duo = analyze_duos(form, min_games=2, limit=6)
            if duo.partners:
                sr = self._sec(host, "👥 같이 뛴 소환사", sr)
                for p in duo.partners:
                    col = (
                        ui.GREEN
                        if p.winrate >= 55
                        else (ui.RED_SOFT if p.winrate < 45 else ui.TEXT)
                    )
                    sr = self._lbl(
                        host,
                        f"· {p.riot_id}  {p.wins}승{p.losses}패 ({p.winrate}%) · {p.games}판",
                        sr,
                        font=FM,
                        color=col,
                        pady=1,
                        wrap=300,
                    )
                    lines_n += 1
            elif form.matches and duo.total_with_any == 0:
                sr = self._lbl(
                    host,
                    "듀오 통계: 아군 Riot ID가 비어 있어 집계 불가",
                    sr,
                    font=FM,
                    color=ui.TEXT_MUTE,
                    pady=2,
                    wrap=300,
                )
                lines_n += 1
        except Exception as exc:
            _log.debug("듀오 요약 렌더 실패(무시): %s", exc)
        if lines_n == 0:
            self._lbl(
                host,
                "표시할 트렌드·듀오 요약이 없습니다.",
                sr,
                font=FM,
                color=ui.TEXT_DIM,
                pady=6,
                wrap=300,
            )
        return lines_n

    def _render_me(self, form: RecentForm, ranks: list | None = None) -> None:
        self._clear(self.me_matches)
        self._clear(self.me_champs)
        self._clear(self.me_detail)
        self._me_match_btns: list[tuple[str, Any]] = []
        self._me_match_index: int | None = None
        self._me_summary_host = None
        self._me_summary_btn = None
        # 큐 필터 적용 — 표시용 재집계 (원본은 _me_form_full 유지)
        fq = getattr(self, "_me_queue_filter", None)
        if fq:
            filtered = [m for m in form.matches if m.queue_id in fq]
            form = aggregate_form(form.profile, filtered)
        self.form = form
        # 랭크 한 줄 (카드 상단 레이블)
        try:
            from lol_coach.display import rank_line

            line = rank_line(ranks or [])
            self.rank_lbl.configure(text=line.strip() if line else "언랭/기록 없음")
        except Exception:
            pass
        loc = self.loc
        n_matches = len(form.matches)
        # 아이콘 소유 프레임 = 경기 목록 (clear 시 함께 해제)
        self._render_target = self.me_matches
        r = 0
        # ── 1) 짧은 헤더 ──
        r = self._lbl(
            self.me_matches,
            f"{form.profile.riot_id}  ·  "
            f"{form.wins}승 {form.losses}패 ({form.winrate}%)  ·  KDA {form.avg_kda}",
            r,
            font=FU,
            color=ui.TEXT_BRIGHT,
            pady=(8, 2),
            wrap=300,
        )
        r = self._lbl(
            self.me_matches,
            ui.provenance_label(form.provenance),
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=(0, 4),
            wrap=320,
        )
        # ── 2) 경기 목록 먼저 (스크롤 없이 바로 클릭) ──
        r = self._sec(
            self.me_matches,
            f"최근 경기 {n_matches}판  ·  클릭 → 복기",
            r,
        )
        if not form.matches:
            r = self._lbl(
                self.me_matches,
                "불러온 경기가 없습니다.",
                r,
                color=ui.TEXT_DIM,
                pady=8,
                wrap=300,
            )
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
                "border_width": 0,
                "border_color": ui.BORDER,
                "command": lambda mm=m: self._show_match_detail(mm),
            }
            if icon:
                btn_kw["image"] = icon
                btn_kw["compound"] = "left"
            btn = ctk.CTkButton(self.me_matches, **btn_kw)
            btn.grid(row=r, column=0, sticky="ew", padx=6, pady=2)
            self._me_match_btns.append((getattr(m, "match_id", ""), btn))
            r += 1

        # ── 3) 트렌드·듀오는 접힌 요약 (기본 접힘 → 경기 목록이 파묻히지 않음) ──
        toggle_row = ctk.CTkFrame(self.me_matches, fg_color="transparent")
        toggle_row.grid(row=r, column=0, sticky="ew", padx=6, pady=(10, 4))
        r += 1
        self._me_summary_btn = ctk.CTkButton(
            toggle_row,
            text="▼ 트렌드·듀오 보기",
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._toggle_me_summary,
        )
        self._me_summary_btn.pack(side="left", fill="x", expand=True)
        self._me_summary_host = ctk.CTkFrame(self.me_matches, fg_color=ui.ROW, corner_radius=10)
        self._me_summary_host.grid(row=r, column=0, sticky="ew", padx=6, pady=(0, 8))
        r += 1
        # 요약 내용은 호스트 안 별도 그리드 (부모 스크롤과 분리된 행)
        self._me_summary_host.grid_columnconfigure(0, weight=1)
        hint_n = self._fill_me_summary(self._me_summary_host, form)
        self._me_summary_hint_n = hint_n
        # 기본 접힘 유지 (이전 펼침 상태 기억)
        want_open = bool(getattr(self, "_me_summary_expanded", False))
        self._set_me_summary_expanded(want_open)
        self._scroll_me_matches_top()

        cr = 0
        for c in sorted(form.champion_stats.values(), key=lambda x: (-x.games, -x.winrate)):
            name = loc.champion(c.champion_name) or c.champion_name
            frame = ctk.CTkFrame(self.me_champs, fg_color=ui.ROW, corner_radius=10)
            frame.grid(row=cr, column=0, sticky="ew", padx=6, pady=2)
            ic = self._keep_icon(champion_ctk(c.champion_name, 32))
            if ic:
                ctk.CTkLabel(frame, image=ic, text="").pack(side="left", padx=(8, 6), pady=5)
            ctk.CTkLabel(
                frame,
                text=f"{name}  {c.games}G {c.winrate}%  KDA {c.avg_kda}",
                font=FM,
                anchor="w",
            ).pack(side="left", padx=(0, 10), pady=6)
            cr += 1

        # ── 챔피언 풀 진단 ──
        if form.champion_stats:
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
            "왼쪽 경기를 클릭하면 팀 조합·오브젝트·학습 포인트가 여기에 표시됩니다.\n"
            "「전적 로드 시 최근 1판 자동 복기」를 켜면 로드 직후 최신 판이 열립니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=420,
        )
        self.status.configure(text=f"전적 로드 · {form.profile.riot_id}")
        # 옵션 ON일 때만 최근 1판 자동 복기 (기본 OFF)
        if form.matches and self._should_auto_open_latest():
            self._show_match_detail(form.matches[0])

    def _match_index_of(self, m: MatchSummary) -> int | None:
        form = getattr(self, "form", None)
        matches = list(getattr(form, "matches", None) or [])
        mid = getattr(m, "match_id", None)
        if mid:
            for i, other in enumerate(matches):
                if getattr(other, "match_id", None) == mid:
                    return i
        try:
            return matches.index(m)
        except ValueError:
            return None

