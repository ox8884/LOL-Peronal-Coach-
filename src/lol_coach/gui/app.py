"""롤 실전 코치 GUI — 협곡 조합 분석 · ARAM 아수라장 · 전적."""

from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach import __version__
from lol_coach.analysis.aram_mayhem import AugmentPick, AugmentValidation, MayhemAdvice, MayhemCoach
from lol_coach.analysis.comp import CompAnalyzer, CompReport
from lol_coach.analysis.draft import DraftCoach
from lol_coach.analysis.review import analyze_match
from lol_coach.config import load_settings, save_api_key, save_player
from lol_coach.modes import MODE_SUMMONERS_RIFT
from lol_coach.riot.client import RiotAPIError, RiotClient
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm
from lol_coach.static.augment_catalog import AugmentCatalog, CatalogError
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer
from lol_coach.static.icons import champion_ctk, item_name_ctk
from lol_coach.ugg.client import UGGClient
from lol_coach.ugg.counters import CounterClient

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ROLES = [
    ("탑", "top"),
    ("정글", "jungle"),
    ("미드", "mid"),
    ("원딜", "adc"),
    ("서폿", "support"),
]

# 자주 쓰는 서버 우선 배치 (드롭다운)
PLATFORMS = ["kr", "na1", "euw1", "eun1", "jp1", "br1", "oc1", "tr1", "ru", "la1", "la2"]

FT = ("Malgun Gothic", 18, "bold")
FS = ("Malgun Gothic", 14, "bold")
FU = ("Malgun Gothic", 13)
FB = ("Malgun Gothic", 12)
FM = ("Malgun Gothic", 11)


class CoachApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"롤 실전 코치  v{__version__}")
        self.geometry("1040x860")
        self.minsize(900, 720)

        self.dd = DataDragon(language="ko_KR")
        self.loc = get_localizer()
        self.ugg = UGGClient()
        self.counters = CounterClient(self.ugg)
        self.draft = DraftCoach(self.dd)
        self.comp = CompAnalyzer(self.dd)
        self.mayhem = MayhemCoach(self.ugg, self.dd)
        self._aug_catalog = AugmentCatalog()
        self.settings = load_settings()

        self.riot: RiotClient | None = None
        self.profile: PlayerProfile | None = None
        self.form: RecentForm | None = None
        self._busy: set[str] = set()
        self._role_btns: list[ctk.CTkButton] = []
        # (소유 프레임, CTkImage) — 프레임 클리어 시 함께 해제해 누수 방지
        self._icon_refs: list[tuple[Any, Any]] = []
        self._render_target: Any = None
        self._widget: Any = None  # MiniWidget
        self._watcher: Any = None  # GameEndWatcher
        self._last_summary_title = ""
        self._last_summary_lines: list[str] = []
        self._sr_history: list[tuple[Any, tuple, dict]] = []
        self._sr_autocompletes: list[Any] = []
        self._champ_watcher: Any = None  # ChampSelectWatcher
        self._sr_lcu_sig: tuple = ()
        self._aram_lcu_sig: tuple = ()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._boot, daemon=True).start()

    def _on_close(self) -> None:
        for w in (self._watcher, self._champ_watcher):
            try:
                if w is not None:
                    w.stop()
            except Exception:
                pass
        self.destroy()

    def _stop_champ_watch(self) -> None:
        w = self._champ_watcher
        self._champ_watcher = None
        try:
            if w is not None:
                w.stop()
        except Exception:
            pass

    # ── shell ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        ctk.CTkLabel(head, text="롤 실전 코치", font=FT).pack(side="left")
        self.status = ctk.CTkLabel(
            head, text="준비 중…", font=FM, text_color=("gray50", "gray60")
        )
        self.status.pack(side="right")
        ctk.CTkButton(
            head,
            text="📌 미니 위젯",
            width=96,
            height=28,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=self._toggle_widget,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            head,
            text="📋 복사",
            width=72,
            height=28,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=self._copy_summary,
        ).pack(side="right", padx=(0, 8))

        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.t_sr = self.tabs.add("소환사의 협곡")
        self.t_aram = self.tabs.add("ARAM 아수라장")
        self.t_me = self.tabs.add("내 전적")
        for t in (self.t_sr, self.t_aram, self.t_me):
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(1, weight=1)

        self._build_sr()
        self._build_aram()
        self._build_me()

    def _boot(self) -> None:
        try:
            self.dd.ensure_loaded()
            self.loc.ensure_loaded()
            player = self.settings.riot_id or "소환사 미설정"
            self.after(
                0,
                lambda value=player: self.status.configure(
                    text=f"데이터 준비됨  ·  {value}"
                ),
            )
            # 저장된 프로필+키가 있으면 마지막 전적 자동 로드
            if self.settings.riot_api_key and self.settings.riot_id:
                self.after(600, self._load_me)
        except Exception as exc:
            message = str(exc)
            self.after(
                0,
                lambda value=message: self.status.configure(text=f"오류: {value}"),
            )

    # ── helpers ───────────────────────────────────────────────────────

    def _busy_set(
        self, on: bool, btn: ctk.CTkButton | None, idle: str, key: str = "default"
    ) -> None:
        if on:
            self._busy.add(key)
        else:
            self._busy.discard(key)
        if btn:
            btn.configure(
                state="disabled" if on else "normal",
                text="분석 중…" if on else idle,
            )

    def _is_busy(self, key: str) -> bool:
        """특정 작업 키가 실행 중인지 (탭별 동시 진행 허용)."""
        return key in self._busy

    def _clear(self, frame: ctk.CTkBaseClass) -> None:
        for w in frame.winfo_children():
            w.destroy()
        # 이 프레임 소유 아이콘 참조도 해제 (장시간 사용 시 메모리 누수 방지)
        self._icon_refs = [r for r in self._icon_refs if r[0] is not frame]
        self._render_target = frame

    def _keep_icon(self, img: Any) -> Any:
        if img is not None:
            self._icon_refs.append((self._render_target, img))
        return img

    def _lbl(
        self,
        parent: Any,
        text: str,
        row: int,
        *,
        font=FB,
        color=None,
        wrap: int = 960,
        pady: int = 2,
        padx: int = 10,
    ) -> int:
        kw: dict[str, Any] = {
            "text": text,
            "font": font,
            "anchor": "w",
            "justify": "left",
            "wraplength": wrap,
        }
        if color:
            kw["text_color"] = color
        ctk.CTkLabel(parent, **kw).grid(
            row=row, column=0, sticky="ew", padx=padx, pady=pady
        )
        return row + 1

    def _sec(self, parent: Any, title: str, row: int) -> int:
        ctk.CTkLabel(parent, text=f"▸ {title}", font=FS, anchor="w").grid(
            row=row, column=0, sticky="w", padx=10, pady=(14, 4)
        )
        return row + 1

    def _row_frame(self, parent: Any, row: int, padx: int = 10, pady: int = 2) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray22"), corner_radius=8)
        frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        return frame

    def _entry_row(
        self, parent: Any, row: int, label: str, var: tk.StringVar, ph: str = ""
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=FU, width=90, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=5
        )
        entry = ctk.CTkEntry(
            parent, textvariable=var, placeholder_text=ph, font=FU, height=34
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        return entry

    def _attach_champ_ac(
        self,
        entry: ctk.CTkEntry,
        var: tk.StringVar,
        panel_parent: Any,
    ) -> Any:
        """챔피언 입력에 자동완성 부착 (공유 패널). 패널은 호출부가 grid 배치."""
        from lol_coach.gui.champ_autocomplete import ChampionAutocomplete

        ac = ChampionAutocomplete(
            self,
            entry,
            var,
            self.dd,
            list_parent=panel_parent,
            keep_icon=self._keep_icon,
            limit=8,
            icon_size=28,
        )
        self._sr_autocompletes.append(ac)
        return ac

    def _resolve(self, raw: str) -> tuple[str, str]:
        raw = raw.strip()
        if not raw:
            raise ValueError("챔피언을 입력하세요.")
        c = self.dd.resolve_champion(raw)
        if not c:
            raise ValueError(f"챔피언을 찾을 수 없습니다: {raw}")
        return c["id"], c["name"]

    def _role_key(self) -> str:
        lab = self.role_var.get()
        for ko, en in ROLES:
            if ko == lab:
                return en
        return "mid"

    def _select_role(self, label: str) -> None:
        self.role_var.set(label)
        for b in self._role_btns:
            b.configure(
                fg_color=("#3B8ED0", "#1F6AA5")
                if b.cget("text") == label
                else ("gray70", "gray30")
            )

    # ── 미니 위젯 / 요약 / 툴팁 ───────────────────────────────────────

    def _toggle_widget(self) -> None:
        from lol_coach.gui.widget import MiniWidget

        if self._widget is not None and self._widget.winfo_exists():
            self._widget.focus()
            return
        self._widget = MiniWidget(self, on_close=lambda: setattr(self, "_widget", None))
        if self._last_summary_lines:
            self._widget.set_summary(
                self._last_summary_title, self._last_summary_lines
            )

    def _push_summary(self, title: str, lines: list[str]) -> None:
        """마지막 분석 요약 저장 → 미니 위젯이 열여 있으면 갱신."""
        self._last_summary_title = title
        self._last_summary_lines = lines
        try:
            if self._widget is not None and self._widget.winfo_exists():
                self._widget.set_summary(title, lines)
        except Exception:
            pass

    def _copy_summary(self) -> None:
        """마지막 분석 요약을 클립보드로 복사."""
        try:
            if not self._last_summary_lines:
                messagebox.showinfo("복사", "복사할 결과가 아직 없습니다.")
                return
            text = self._last_summary_title + "\n" + "\n".join(self._last_summary_lines)
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status.configure(text="📋 요약 복사됨")
        except Exception as exc:
            messagebox.showerror("복사", f"클립보드 복사 실패: {exc}")

    def _push_sr_history(self, fn: Any, *args: Any) -> None:
        """협곡 결과 렌더 함수를 히스토리에 저장 (최근 20개)."""
        self._sr_history.append((fn, args, {}))
        if len(self._sr_history) > 20:
            self._sr_history.pop(0)

    def _back_sr_history(self) -> None:
        """이전 결과로 복원 (히스토리 pop → 재렌더)."""
        if not self._sr_history:
            messagebox.showinfo("히스토리", "이전 결과가 없습니다.")
            return
        fn, args, _kw = self._sr_history.pop()
        try:
            fn(*args)
        except Exception as exc:
            messagebox.showerror("히스토리", f"이전 결과 복원 실패: {exc}")

    def _push_aram_history(self, fn: Any, *args: Any) -> None:
        """ARAM 브리핑 결과를 히스토리에 저장 (최근 20개)."""
        if not hasattr(self, "_aram_history"):
            self._aram_history = []
        self._aram_history.append((fn, args, {}))
        if len(self._aram_history) > 20:
            self._aram_history.pop(0)

    def _back_aram_history(self) -> None:
        """이전 ARAM 브리핑으로 복원."""
        hist = getattr(self, "_aram_history", [])
        if not hist:
            messagebox.showinfo("히스토리", "이전 결과가 없습니다.")
            return
        fn, args, _kw = hist.pop()
        try:
            fn(*args)
        except Exception as exc:
            messagebox.showerror("히스토리", f"이전 결과 복원 실패: {exc}")

    def _item_tooltip_text(self, item_name: str) -> str:
        try:
            iid = self.dd.item_id_for_name(item_name)
            return self.dd.item_tooltip(iid)
        except Exception:
            return ""

    def _attach_item_tooltip(self, widget: Any, item_name: str) -> None:
        from lol_coach.gui.tooltip import ToolTip

        ToolTip(widget, lambda: self._item_tooltip_text(item_name))

    # ══════════════════════════════════════════════════════════════════
    # 소환사의 협곡
    # ══════════════════════════════════════════════════════════════════

    def _build_sr(self) -> None:
        # ── 빠른 카운터 (메인) ──
        quick = ctk.CTkFrame(self.t_sr, corner_radius=10)
        quick.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        quick.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            quick, text="⚡ 빠른 카운터픽 (픽타임용)", font=FS, anchor="w"
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(quick, text="내 포지션", font=FU).grid(
            row=1, column=0, sticky="w", padx=(12, 6), pady=4
        )
        self.role_var = tk.StringVar(value="미드")
        roles = ctk.CTkFrame(quick, fg_color="transparent")
        roles.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        self._role_btns = []
        for lab, _ in ROLES:
            b = ctk.CTkButton(
                roles,
                text=lab,
                width=58,
                height=30,
                font=FM,
                fg_color=("gray70", "gray30"),
                command=lambda L=lab: self._select_role(L),
            )
            b.pack(side="left", padx=2)
            self._role_btns.append(b)
        self._select_role("미드")

        self.enemy_lane_var = tk.StringVar()
        ctk.CTkLabel(quick, text="적 라이너", font=FU, width=90, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(12, 6), pady=6
        )
        ent = ctk.CTkEntry(
            quick,
            textvariable=self.enemy_lane_var,
            placeholder_text="예: 야스오, 아리, 제드 …",
            font=FU,
            height=36,
        )
        ent.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=6)
        ent.bind("<Return>", self._sr_quick_enter)
        ent.bind("<KP_Enter>", self._sr_quick_enter)
        self._sr_lane_ac = self._attach_champ_ac(ent, self.enemy_lane_var, quick)

        self.sr_quick_btn = ctk.CTkButton(
            quick, text="빠른 추천", width=100, height=36, font=FU, command=self._run_sr_quick
        )
        self.sr_quick_btn.grid(row=2, column=2, padx=(0, 12), pady=6)
        ctk.CTkButton(
            quick,
            text="📜 이전",
            width=64,
            height=36,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=self._back_sr_history,
        ).grid(row=2, column=3, padx=(0, 8), pady=6)

        live_row = ctk.CTkFrame(quick, fg_color="transparent")
        live_row.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4))
        self.sr_live_btn = ctk.CTkButton(
            live_row,
            text="🎮 실행 중인 게임 자동 검색",
            height=32,
            font=FU,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#388E3C", "#2E7D32"),
            command=self._live_fill_sr,
        )
        self.sr_live_btn.pack(side="left")
        self.sr_lcu_btn = ctk.CTkButton(
            live_row,
            text="🎯 밴픽 불러오기 (LCU)",
            height=32,
            font=FU,
            fg_color=("#6A1B9A", "#4A148C"),
            hover_color=("#7B1FA2", "#6A1B9A"),
            command=self._lcu_fill_sr,
        )
        self.sr_lcu_btn.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            live_row,
            text="LCU = 밴픽 중 · Spectator = 로딩/인게임 중",
            font=FM,
            text_color=("gray45", "gray60"),
        ).pack(side="left", padx=10)

        self.sr_status = ctk.CTkLabel(
            quick,
            text="적 한 명 + 포지션만 → 바로 카운터 3~5개 + 한 줄 팁",
            font=FM,
            text_color=("gray45", "gray60"),
        )
        self.sr_status.grid(row=4, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 10))
        # 자동완성 제안 패널 (기본 숨김 — 입력 시 grid)
        self._sr_lane_ac.panel.grid(
            row=5, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 4)
        )
        self._sr_lane_ac.panel.grid_remove()

        # ── 상세 분석 (접이식 느낌의 하단 카드) ──
        detail = ctk.CTkFrame(self.t_sr, corner_radius=10)
        detail.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        detail.grid_columnconfigure(1, weight=1)
        detail.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            detail, text="📋 상세 분석 (조합·용/바론·상황템)", font=FS, anchor="w"
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 4))

        self.my_champ_var = tk.StringVar()
        self.enemy_jg_var = tk.StringVar()
        self.enemy_sup_var = tk.StringVar()
        self.enemy_top_var = tk.StringVar()
        self.enemy_mid_var = tk.StringVar()
        self.enemy_adc_var = tk.StringVar()

        my_ent = self._entry_row(detail, 1, "내 챔피언", self.my_champ_var, "픽한 챔프 (선택)")
        jg_ent = self._entry_row(detail, 2, "적 정글", self.enemy_jg_var, "예: 리 신")
        sup_ent = self._entry_row(detail, 3, "적 서폿", self.enemy_sup_var, "예: 쓰레쉬")

        ctk.CTkLabel(detail, text="적 탑", font=FU, width=70, anchor="w").grid(
            row=2, column=2, sticky="w", padx=(8, 4), pady=5
        )
        top_ent = ctk.CTkEntry(
            detail, textvariable=self.enemy_top_var, font=FU, height=34, width=110
        )
        top_ent.grid(row=2, column=3, sticky="ew", padx=(0, 12), pady=5)
        ctk.CTkLabel(detail, text="적 미드", font=FU, width=70, anchor="w").grid(
            row=3, column=2, sticky="w", padx=(8, 4), pady=5
        )
        mid_ent = ctk.CTkEntry(
            detail, textvariable=self.enemy_mid_var, font=FU, height=34, width=110
        )
        mid_ent.grid(row=3, column=3, sticky="ew", padx=(0, 12), pady=5)
        ctk.CTkLabel(detail, text="적 원딜", font=FU, width=70, anchor="w").grid(
            row=4, column=2, sticky="w", padx=(8, 4), pady=5
        )
        adc_ent = ctk.CTkEntry(
            detail, textvariable=self.enemy_adc_var, font=FU, height=34, width=110
        )
        adc_ent.grid(row=4, column=3, sticky="ew", padx=(0, 12), pady=5)

        # 상세 입력 자동완성 — 각 입력마다 전용 패널 슬롯 (row 5~10)
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
            ac.panel.grid(row=5 + i, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 2))
            ac.panel.grid_remove()

        btn_row = ctk.CTkFrame(detail, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 12))
        self.sr_detail_btn = ctk.CTkButton(
            btn_row,
            text="상세 분석",
            height=36,
            font=FU,
            fg_color=("gray60", "gray35"),
            command=self._run_sr_detail,
        )
        self.sr_detail_btn.pack(side="left")
        ctk.CTkLabel(
            btn_row,
            text="정글·서폿·내 픽까지 넣고 조합/오브젝트/상황템 확인",
            font=FM,
            text_color=("gray45", "gray60"),
        ).pack(side="left", padx=10)

        self.sr_out = ctk.CTkScrollableFrame(
            self.t_sr, corner_radius=10, label_text="결과"
        )
        self.sr_out.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.t_sr.grid_rowconfigure(2, weight=1)
        self.sr_out.grid_columnconfigure(0, weight=1)
        self._lbl(
            self.sr_out,
            "픽타임: 위 「빠른 추천」만 쓰세요.\n"
            "로딩/밴픽 여유 있을 때 「상세 분석」으로 조합까지 보세요.",
            0,
            color=("gray45", "gray60"),
            pady=16,
        )

    def _opt_champ(self, var: tk.StringVar) -> str | None:
        v = var.get().strip()
        if not v:
            return None
        try:
            k, _ = self._resolve(v)
            return k
        except ValueError:
            return v

    # ── 인게임 자동입력 (Spectator V5) ────────────────────────────────

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
            messagebox.showwarning(
                "소환사",
                "Riot ID(Name#TAG)를 「내 전적」탭에 설정해 주세요.",
            )
            return None
        name, tag = rid.split("#", 1)
        platform = settings.platform or "na1"
        if hasattr(self, "platform_var"):
            platform = self.platform_var.get().strip() or platform

        save_api_key(key)
        save_player(name.strip(), tag.strip(), platform=platform)
        self.settings = load_settings()

        client = RiotClient(api_key=key, platform=platform)
        return client, name.strip(), tag.strip()

    def _lcu_fill_sr(self) -> None:
        """LCU: 밴픽 중 적/내 픽 자동 입력 → 바로 카운터 추천."""
        if self._is_busy("sr_lcu"):
            return
        self.sr_status.configure(text="클이언트 밴픽 조회 중…")

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
                    self.sr_status.configure(text="밴픽 조회 실패")
                    messagebox.showinfo(
                        "밴픽 불러오기 (LCU)",
                        f"{m}\n\n밴픽(챔피언 선택) 중에 눌러 주세요.\n"
                        "게임 클라이언트가 실행 중이어야 합니다.",
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
        self._sr_lcu_sig = sig

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
            self._champ_watcher = None

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
                    messagebox.showwarning("인게임 자동입력", m)
                    self.sr_status.configure(text="인게임 조회 실패")
                    self._busy_set(
                        False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live"
                    )

                self.after(0, fail)

        threading.Thread(target=bg, daemon=True).start()

    def _apply_live_sr(self, fill) -> None:
        """LiveFillResult → 협곡 필드 채우고 상세 분석."""
        try:
            if fill.is_aram:
                messagebox.showinfo(
                    "모드 확인",
                    "지금 게임은 칼바람/아수라장으로 보입니다.\n"
                    "「ARAM 아수라장」탭의 인게임 자동검색을 이용해 주세요.",
                )
                self.sr_status.configure(text="ARAM 게임 감지 · ARAM 탭 사용")
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
                messagebox.showinfo(
                    "인게임",
                    f"내 챔프: {fill.my_champ_ko}\n"
                    f"적: {', '.join(n for _, n in fill.enemies_by_role.values()) or '없음'}\n\n"
                    f"{fill.note}",
                )
        except Exception as e:
            messagebox.showerror("오류", str(e))
            self._busy_set(False, self.sr_live_btn, "🎮 실행 중인 게임 자동 검색", key="sr_live")

    # ── 게임 종료 자동 복기 ───────────────────────────────────────────

    def _start_game_end_watcher(self) -> None:
        """인게임 자동입력 성공 후 — 종료를 폴당해 자동 복기."""
        riot = getattr(self, "riot", None)
        profile = getattr(self, "profile", None)
        if riot is None or profile is None:
            return
        watcher = getattr(self, "_watcher", None)
        if watcher is not None and watcher.running:
            return
        from lol_coach.gui.watcher import GameEndWatcher

        client, profile = riot, profile

        def latest() -> Any:
            # 매치 반영까지 지연 있을 수 있어 몇 번 재시도
            import time as _time

            for attempt in range(4):
                ids = client.get_match_ids(profile.puuid, count=1)
                if ids:
                    raw = client.get_match(ids[0])
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
        )
        self._watcher.start()
        self.status.configure(text="🔔 게임 종료 감지 중 — 끝나면 자동 복기")

    def _on_game_ended(self, match: Any) -> None:
        if match is None:
            self.status.configure(text="게임 종료 감지됨 — 매치 조회 실패")
            return
        champ = self.loc.champion(match.champion_name) or match.champion_name
        mark = "승리" if match.win else "패배"
        self.status.configure(text=f"🔔 방금 게임({champ} {mark}) 복기 도착")
        self._notify_game_end(champ, match.win)
        try:
            self._show_match_detail(match)
            self.tabs.set("내 전적")
        except Exception:
            pass

    def _notify_game_end(self, champ: str, win: bool) -> None:
        """게임 종료 알림 — 사운드 + 작업 표시줄 플래시 (비모달)."""
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
                    messagebox.showwarning("인게임 자동검색", m)
                    self.aram_status.configure(text="인게임 조회 실패")
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
            self.aram_status.configure(
                text=f"인게임 · {fill.my_champ_ko} 브리핑 중…"
            )
            self._busy_set(False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")
            self._start_game_end_watcher()
            self._run_aram()
        except Exception as e:
            messagebox.showerror("오류", str(e))
            self._busy_set(False, self.aram_live_btn, "🎮 실행 중인 게임 자동 검색", key="aram_live")

    def _run_sr_quick(self) -> None:
        """픽타임용: 적 라이너 + 포지션만."""
        if self._is_busy("sr_quick"):
            return
        try:
            lane_key, lane_ko = self._resolve(self.enemy_lane_var.get())
        except ValueError as e:
            messagebox.showwarning("입력", str(e))
            return
        role = self._role_key()
        self._busy_set(True, self.sr_quick_btn, "빠른 추천", key="sr_quick")
        self.sr_status.configure(text=f"{lane_ko} 카운터 조회 중…")

        def work() -> None:
            try:
                crep = self.counters.get_counters(
                    lane_key, role=role, limit=5, min_matches=600
                )
                advice = self.draft.advise(crep, top_n=5)
                from lol_coach.static.icons import champion_pil

                for _name, counter in advice.counters[:5]:
                    champion_pil(counter.champion, 48)
                self._push_sr_history(self._render_sr_quick, advice, lane_ko, role)
                self.after(0, lambda: self._render_sr_quick(advice, lane_ko, role))
            except Exception as e:
                msg = str(e)
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
            messagebox.showwarning("입력", "적 라이너를 먼저 입력하세요.\n" + str(e))
            return

        role = self._role_key()
        my_raw = self.my_champ_var.get().strip()
        my_key = my_ko = None
        if my_raw:
            try:
                my_key, my_ko = self._resolve(my_raw)
            except ValueError as e:
                messagebox.showwarning("입력", str(e))
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
                if my_key:
                    gd = crep.lane_counters[0].gd15 if crep.lane_counters else None
                    for c in crep.lane_counters:
                        if c.champion.lower().replace(" ", "") == my_key.lower():
                            gd = c.gd15
                            break
                    matchup = self.draft.matchup_tips(my_key, lane_key, role, gd15=gd)
                from lol_coach.static.icons import champion_pil, item_pil_by_name

                for _name, counter in report.counters[:6]:
                    champion_pil(counter.champion, 40)
                for item in report.core_items[:5]:
                    item_pil_by_name(item, 32)
                for item, _why in report.situational:
                    item_pil_by_name(item, 28)
                self._push_sr_history(self._render_sr_detail, report, matchup)
                self.after(0, lambda: self._render_sr_detail(report, matchup))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._sr_err(msg))
            finally:
                self.after(
                    0, lambda: self._busy_set(False, self.sr_detail_btn, "상세 분석", key="sr_detail")
                )

        threading.Thread(target=work, daemon=True).start()

    def _sr_err(self, msg: str) -> None:
        self._clear(self.sr_out)
        self._lbl(self.sr_out, f"오류: {msg}", 0, color="#E57373")
        self.sr_status.configure(text="실패")

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
            pady=8,
        )
        r = self._sec(self.sr_out, "추천 픽 (GD@15 순)", r)
        if not advice.counters:
            r = self._lbl(self.sr_out, "데이터 부족", r)
        else:
            from lol_coach.static.icons import champion_ctk

            for i, (name, c) in enumerate(advice.counters[:5], 1):
                col = "#81C784" if c.gd15 >= 200 else "#FFB74D"
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
                r += 1

        r = self._sec(self.sr_out, "30초 팁", r)
        for t in advice.lane_tips[:3]:
            r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)
        r = self._lbl(
            self.sr_out,
            "→ 여유 있으면 아래 「상세 분석」으로 정글·서폿·상황템까지 확인",
            r,
            font=FM,
            color=("gray50", "gray60"),
            pady=10,
        )
        self.sr_status.configure(text=f"빠른 추천 완료 · {lane_ko}")
        self.status.configure(text=f"빠른 카운터 · {lane_ko}")
        summary = [f"⚡ vs {lane_ko} · {role_ko}  (패치 {advice.patch})"]
        for i, (name, c) in enumerate(advice.counters[:5], 1):
            tip = (
                "초반 강함"
                if c.gd15 >= 300
                else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
            )
            summary.append(
                f"{i}. {name} — {tip} (GD@15 {c.gd15_str} · {c.matches:,}게임)"
            )
        if advice.lane_tips:
            summary.append("")
            summary += [f"· {t}" for t in advice.lane_tips[:3]]
        self._push_summary(f"⚡ vs {lane_ko} · {role_ko}", summary)

    def _render_sr_detail(self, rep: CompReport, matchup: list[str]) -> None:
        self._clear(self.sr_out)
        r = 0
        r = self._lbl(
            self.sr_out,
            f"📋 {rep.my_champ_ko}  ·  {rep.my_role}  vs  {rep.enemy_lane_ko}  ·  {rep.patch}",
            r,
            font=FS,
            pady=8,
        )
        team = ", ".join(f"{role} {name}" for role, name in rep.enemy_team)
        r = self._lbl(
            self.sr_out, f"적 조합: {team}", r, font=FM, color=("gray50", "gray60")
        )

        r = self._sec(self.sr_out, "라인 카운터", r)
        from lol_coach.static.icons import champion_ctk, item_name_ctk

        for i, (name, c) in enumerate(rep.counters[:6], 1):
            col = "#81C784" if c.gd15 >= 200 else "#FFB74D"
            frame = self._row_frame(self.sr_out, r, pady=2)
            icon = self._keep_icon(champion_ctk(c.champion, 40))
            if icon:
                ctk.CTkLabel(frame, image=icon, text="").pack(
                    side="left", padx=(10, 8), pady=5
                )
            ctk.CTkLabel(
                frame,
                text=f"{i}. {name}    GD@15 {c.gd15_str}    {c.matches:,}게임",
                font=FU,
                text_color=col,
                anchor="w",
            ).pack(side="left", padx=(0, 12), pady=7)
            r += 1

        if matchup:
            r = self._sec(
                self.sr_out,
                f"라인전 — {rep.my_champ_ko} vs {rep.enemy_lane_ko}",
                r,
            )
            for t in matchup:
                r = self._lbl(self.sr_out, f"·  {t}", r, pady=3)

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
                color=("gray50", "gray60"),
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
        summary = [f"📋 {rep.my_champ_ko} vs {rep.enemy_lane_ko}  (패치 {rep.patch})"]
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
        if rep.threats:
            summary.append("")
            summary += [f"⚠ {t}" for t in rep.threats[:2]]
        if rep.core_items:
            summary.append("")
            summary.append("코어: " + " → ".join(rep.core_items[:4]))
        if rep.situational:
            summary.append(
                "상황템: " + ", ".join(f"{i} ({w})" for i, w in rep.situational[:3])
            )
        if rep.action_plan:
            summary.append("")
            summary += [f"☐ {t}" for t in rep.action_plan[:2]]
        self._push_summary(
            f"📋 {rep.my_champ_ko} vs {rep.enemy_lane_ko}", summary
        )

    # ══════════════════════════════════════════════════════════════════
    # ARAM 아수라장
    # ══════════════════════════════════════════════════════════════════

    def _build_aram(self) -> None:
        form = ctk.CTkFrame(self.t_aram, corner_radius=10)
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
            text_color=("gray45", "gray60"),
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
            fg_color=("gray70", "gray35"),
            command=self._open_augment_picker,
        ).pack(side="left")
        ctk.CTkLabel(
            pick_row,
            text="카탈로그 200+개 중 검색 → 클릭으로 입력칸에 추가",
            font=FM,
            text_color=("gray45", "gray60"),
        ).pack(side="left", padx=10)

        btn_row = ctk.CTkFrame(form, fg_color="transparent")
        btn_row.grid(row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 12))
        self.aram_live_btn = ctk.CTkButton(
            btn_row,
            text="🎮 실행 중인 게임 자동 검색",
            height=38,
            font=FU,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#388E3C", "#2E7D32"),
            command=self._live_fill_aram,
        )
        self.aram_live_btn.pack(side="left", padx=(0, 8))
        self.aram_btn = ctk.CTkButton(
            btn_row, text="아수라장 브리핑", height=38, font=FU, command=self._run_aram
        )
        self.aram_btn.pack(side="left")
        self.aram_lcu_btn = ctk.CTkButton(
            btn_row,
            text="🎯 밴픽 (LCU)",
            height=38,
            width=110,
            font=FM,
            fg_color=("#6A1B9A", "#4A148C"),
            hover_color=("#7B1FA2", "#6A1B9A"),
            command=self._lcu_fill_aram,
        )
        self.aram_lcu_btn.pack(side="left", padx=(8, 0))
        self.aram_screen_btn = ctk.CTkButton(
            btn_row,
            text="📷 화면 인식 (베타)",
            height=38,
            width=130,
            font=FM,
            fg_color=("gray60", "gray35"),
            command=self._screen_fill_aram,
        )
        self.aram_screen_btn.pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btn_row,
            text="📜 이전",
            width=64,
            height=38,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=self._back_aram_history,
        ).pack(side="left", padx=(8, 0))
        self.aram_status = ctk.CTkLabel(
            btn_row,
            text="인게임 자동 = 내 챔프 채우고 바로 브리핑 · 수동 입력도 가능",
            font=FM,
            text_color=("gray45", "gray60"),
        )
        self.aram_status.pack(side="left", padx=10)

        self.aram_out = ctk.CTkScrollableFrame(
            self.t_aram, corner_radius=10, label_text="아수라장 브리핑"
        )
        self.aram_out.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.aram_out.grid_columnconfigure(0, weight=1)
        self._lbl(
            self.aram_out,
            "챔피언을 고르면 증강 우선순위와 ARAM 빌드를 바로 보여줍니다.",
            0,
            color=("gray45", "gray60"),
            pady=16,
        )

    def _lcu_fill_aram(self) -> None:
        """LCU: 밴픽 중 내 챔피언 자동 입력."""
        if self._is_busy("aram_lcu"):
            return
        self.aram_status.configure(text="클이언트 밴픽 조회 중…")

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
                    self.aram_status.configure(text="밴픽 조회 실패")
                    messagebox.showinfo(
                        "밴픽 (LCU)",
                        f"{m}\n\n밴픽(챔피언 선택) 중에 눌러 주세요.",
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

    def _screen_fill_aram(self) -> None:
        """화면 캡처 → 제시 증강 자동 입력 (베타)."""
        if self._is_busy("aram_screen"):
            return
        self._busy_set(True, self.aram_screen_btn, "📷 화면 인식 (베타)", key="aram_screen")
        self.aram_status.configure(text="화면에서 증강 인식 중…")

        def bg() -> None:
            try:
                from lol_coach.analysis.augment_screen import (
                    build_templates_from_catalog,
                    capture_screen,
                    match_augments,
                )

                names = [r.name_en for r in self._aug_catalog.records]
                templates = build_templates_from_catalog(names)
                if not templates:
                    raise RuntimeError(
                        "캐시된 증강 아이콘이 없습니다.\n"
                        "브리핑을 한 번 실행해 아이콘을 받은 뒤 다시 시도하세요."
                    )
                screen = capture_screen()
                hits = match_augments(screen, templates, max_results=6)
                resolved: list[str] = []
                for h in hits:
                    rec = self._aug_catalog.get_by_name(h.name)
                    if rec is not None:
                        resolved.append(rec.name_ko or rec.name_en)
                self.after(0, lambda: self._apply_screen_aram(resolved, len(hits)))
            except Exception as e:
                msg = str(e)

                def fail(m: str = msg) -> None:
                    self.aram_status.configure(text="화면 인식 실패")
                    messagebox.showinfo("화면 인식 (베타)", m)

                self.after(0, fail)
            finally:
                self.after(
                    0,
                    lambda: self._busy_set(
                        False, self.aram_screen_btn, "📷 화면 인식 (베타)", key="aram_screen"
                    ),
                )

        threading.Thread(target=bg, daemon=True).start()

    def _apply_screen_aram(self, names: list[str], n_hits: int) -> None:
        if not names:
            self.aram_status.configure(
                text="인식된 증강이 없습니다 — 수동 입력을 이용해 주세요"
            )
            return
        existing = self.aram_aug_var.get().strip()
        text = ", ".join(names)
        self.aram_aug_var.set(f"{existing}, {text}" if existing else text)
        self.aram_status.configure(text=f"화면 인식 {n_hits}개 · {text}")


    def _aram_enter(self, _event=None):
        """제안 목록이 열려 있으면 선택은 autocomplete가 처리, 아니면 분석."""
        ac = getattr(self, "_aram_ac", None)
        if ac is not None and ac.is_open():
            return
        self._run_aram()

    def _sr_quick_enter(self, _event=None) -> None:
        """적 라이너 Enter — 자동완성 목록이 열려 있으면 선택에 맡기고, 아니면 분석."""
        ac = getattr(self, "_sr_lane_ac", None)
        if ac is not None and ac.is_open():
            return
        self._run_sr_quick()

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
                    list_frame, text="일치하는 증강이 없습니다", text_color=("gray50", "gray60")
                ).grid(row=0, column=0, pady=10)
                return
            for i, rec in enumerate(shown[:150]):
                btn = ctk.CTkButton(
                    list_frame,
                    text=_label(rec),
                    anchor="w",
                    height=30,
                    font=FM,
                    fg_color=("gray90", "gray22"),
                    hover_color=("#3B8ED0", "#1F6AA5"),
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
            messagebox.showwarning("입력", str(e))
            return

        offered_raw = self.aram_aug_var.get()
        _names, validation, err = self._parse_offered_augments(offered_raw)
        if err:
            messagebox.showwarning("제시 증강", err)
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
            message = "\n".join(lines)
            messagebox.showwarning("제시 증강 확인", message)
            self.aram_aug_status.configure(text=" · ".join(lines))
            return

        # 선택 후 필드에 정식 한글 이름 표시
        self.aram_champ_var.set(ko)
        self._busy_set(True, self.aram_btn, "아수라장 브리핑", key="aram_brief")
        self.aram_status.configure(text=f"{ko} 분석 중…")

        def work() -> None:
            try:
                offered = validation.valid if validation else []
                adv = self.mayhem.advise(key, offered_augments=[r.name_en for r in offered])
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
                self._push_aram_history(self._render_aram, adv)
                self.after(0, lambda: self._render_aram(adv))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._aram_err(msg))
            finally:
                self.after(
                    0, lambda: self._busy_set(False, self.aram_btn, "아수라장 브리핑", key="aram_brief")
                )

        threading.Thread(target=work, daemon=True).start()

    def _aram_err(self, msg: str) -> None:
        self._clear(self.aram_out)
        self._lbl(self.aram_out, f"오류: {msg}", 0, color="#E57373")
        self.aram_status.configure(text="실패")

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
            color=("gray50", "gray60"),
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
                    color="#FFB74D",
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
                color=("gray50", "gray60"),
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
                    text_color="#81C784",
                    anchor="w",
                    justify="left",
                ).pack(side="left", padx=(0, 12), pady=8)
                r += 1

        r = self._sec(self.aram_out, "2. 피해야 할 증강", r)
        if not adv.avoid_augments:
            r = self._lbl(
                self.aram_out,
                "회피 대상이 없습니다.",
                r,
                color=("gray50", "gray60"),
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
                    text_color="#E57373",
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
                "코어 아이템 이름을 가져오지 못했습니다. u.gg ARAM 페이지를 확인하세요.",
                r,
                color=("gray50", "gray60"),
            )

        r = self._sec(self.aram_out, "4. 실전 팁", r)
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
            color=("gray50", "gray55"),
            pady=(12, 8),
        )
        self.aram_status.configure(text=f"완료 · {adv.champ_ko}")
        self.status.configure(text=f"아수라장 · {adv.champ_ko}")
        summary = [f"🔮 {adv.champ_ko} 아수라장  (패치 {adv.patch})"]
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
        self._push_summary(f"🔮 {adv.champ_ko} 아수라장", summary)

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

    # ══════════════════════════════════════════════════════════════════
    # 내 전적
    # ══════════════════════════════════════════════════════════════════

    def _build_me(self) -> None:
        card = ctk.CTkFrame(self.t_me, corner_radius=10)
        card.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        card.grid_columnconfigure(1, weight=1)

        self.riot_id_var = tk.StringVar(value=self.settings.riot_id)
        self.platform_var = tk.StringVar(value=self.settings.platform or "na1")
        self.api_key_var = tk.StringVar(value=self.settings.riot_api_key or "")

        self._entry_row(card, 0, "Riot ID", self.riot_id_var, "소환사명#KR1")
        ctk.CTkLabel(card, text="서버", font=FU, width=90, anchor="w").grid(
            row=0, column=2, sticky="w", padx=6
        )
        platform_values = list(PLATFORMS)
        cur_plat = (self.settings.platform or "na1").strip().lower()
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
            fg_color=("gray70", "gray35"),
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
            card, text="전적 로드", width=100, height=34, command=self._load_me
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
        ctk.CTkButton(
            misc,
            text="저장",
            width=52,
            height=28,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=self._save_current_profile,
        ).pack(side="left")
        self.rank_lbl = ctk.CTkLabel(
            misc, text="", font=FM, text_color=("gray45", "gray60")
        )
        self.rank_lbl.pack(side="left", padx=12)
        ctk.CTkButton(
            misc,
            text="CSV",
            width=48,
            height=28,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=lambda: self._export_me("csv"),
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            misc,
            text="JSON",
            width=52,
            height=28,
            font=FM,
            fg_color=("gray70", "gray35"),
            command=lambda: self._export_me("json"),
        ).pack(side="right")

        body = ctk.CTkFrame(self.t_me, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=3)
        body.grid_rowconfigure(1, weight=1)

        self.me_matches = ctk.CTkScrollableFrame(
            body, label_text="최근 경기 (클릭 → 복기)", corner_radius=10
        )
        self.me_matches.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        self.me_detail = ctk.CTkScrollableFrame(
            body, label_text="경기 복기 · 학습", corner_radius=10
        )
        self.me_detail.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 0))
        self.me_champs = ctk.CTkScrollableFrame(
            body, label_text="챔피언별 성적", corner_radius=10
        )
        self.me_champs.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(5, 0))
        self._lbl(
            self.me_matches,
            "API 키 + Riot ID로 최근 전적을 불러오세요.\n경기를 클릭하면 팀 조합·오브젝트·복기가 열립니다.",
            0,
            color=("gray45", "gray60"),
            pady=16,
            wrap=320,
        )
        self._lbl(
            self.me_detail,
            "왼쪽 경기를 클릭하면\n아군/적군 5v5 · 오브젝트 · 학습 포인트가 표시됩니다.",
            0,
            color=("gray45", "gray60"),
            pady=16,
            wrap=420,
        )

    def _show_api_help(self) -> None:
        from lol_coach.gui.api_help import open_api_key_help

        open_api_key_help(self)

    # ── 프로필 / 내보내기 ─────────────────────────────────────────────────

    @staticmethod
    def _profile_labels() -> list[str]:
        from lol_coach.config import list_profiles

        labels = [
            f"{p['riot_id']} ({p.get('platform', 'na1')})"
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
        platform = self.platform_var.get().strip() or "na1"
        try:
            add_profile(rid, platform)
        except ValueError as exc:
            messagebox.showwarning("프로필", str(exc))
            return
        self._refresh_profile_menu()
        self.status.configure(text=f"프로필 저장됨 · {rid}")

    def _export_me(self, fmt: str) -> None:
        from tkinter import filedialog

        from lol_coach.analysis.export import (
            export_matches_csv,
            export_matches_json,
        )

        if self.form is None:
            messagebox.showinfo("내보내기", "먼저 전적을 불러오세요.")
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
            messagebox.showerror("내보내기 실패", str(exc))
            return
        self.status.configure(text=f"내보내기 완료 → {out}")
        messagebox.showinfo("내보내기", f"저장했습니다:\n{out}")

    def _load_me(self) -> None:
        if self._is_busy("me_load"):
            return
        rid = self.riot_id_var.get().strip()
        if "#" not in rid:
            messagebox.showwarning("입력", "Riot ID는 Name#TAG 형식")
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
        platform = self.platform_var.get().strip() or "na1"
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
                form = client.get_recent_form(profile, count=15)
                ranks: list = []
                try:
                    ranks = client.get_league_entries(profile.puuid)
                except RiotAPIError:
                    ranks = []
                from lol_coach.static.icons import champion_pil, item_pil

                for match in form.matches:
                    champion_pil(match.champion_name, 40)
                    champion_pil(match.champion_name, 52)
                    for item_id in match.items:
                        item_pil(int(item_id), 28)
                    for player in [*match.ally_team, *match.enemy_team]:
                        champion_pil(player.champion_name, 40)
                        for item_id in player.items:
                            item_pil(int(item_id), 22)
                for champion in form.champion_stats.values():
                    champion_pil(champion.champion_name, 32)
                self.riot, self.profile, self.form = client, profile, form
                self.after(0, lambda: self._render_me(form, ranks))
            except RiotAPIError as e:
                msg = str(e)
                self.after(0, lambda: self._me_err(msg))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._me_err(msg))
            finally:
                self.after(0, lambda: self._busy_set(False, self.me_btn, "전적 로드", key="me_load"))

        threading.Thread(target=work, daemon=True).start()

    def _me_err(self, msg: str) -> None:
        self._clear(self.me_matches)
        self._clear(self.me_detail)
        self._clear(self.me_champs)
        self._lbl(self.me_matches, f"오류: {msg}", 0, color="#E57373", wrap=300)

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
            font=FM,
            pady=8,
            wrap=300,
        )
        for _i, m in enumerate(form.matches, 1):
            mark = "승" if m.win else "패"
            col = "#81C784" if m.win else "#E57373"
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
                "fg_color": ("gray90", "gray22"),
                "hover_color": ("gray80", "gray32"),
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
            frame = ctk.CTkFrame(
                self.me_champs, fg_color=("gray90", "gray22"), corner_radius=8
            )
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
                "집중": "#81C784",
                "유지": ("gray30", "gray70"),
                "표본 부족": ("gray50", "gray55"),
                "정리 검토": "#FFB74D",
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
            color=("gray45", "gray60"),
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
        col = "#81C784" if m.win else "#E57373"

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
                ctk.CTkLabel(cell, text=label[:8], font=FM, text_color=("gray40", "gray65")).pack()
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
            r = self._lbl(self.me_detail, "오브젝트 정보 없음", r, color=("gray50", "gray60"))

        # 팀 조합
        r = self._sec(self.me_detail, "아군 조합", r)
        r = self._render_team_block(self.me_detail, m.ally_team, r, ally=True)
        r = self._sec(self.me_detail, "적군 조합", r)
        r = self._render_team_block(self.me_detail, m.enemy_team, r, ally=False)

        # 심화 복기
        rev = analyze_match(m)
        title_reason = "이 게임을 이긴 주요 이유" if m.win else "이 게임을 진 주요 이유"
        r = self._sec(self.me_detail, title_reason, r)
        for i, t in enumerate(rev.win_loss_reasons, 1):
            r = self._lbl(
                self.me_detail,
                f"{i}.  {t}",
                r,
                color=("#90CAF9" if m.win else "#EF9A9A"),
                wrap=480,
                pady=3,
            )

        r = self._sec(self.me_detail, "내 플레이 — 잘한 점", r)
        for t in rev.good:
            r = self._lbl(self.me_detail, f"✓  {t}", r, color="#81C784", wrap=480, pady=2)

        r = self._sec(self.me_detail, "내 플레이 — 개선할 점 (다음 판 행동)", r)
        for t in rev.improve:
            r = self._lbl(self.me_detail, f"→  {t}", r, color="#FFB74D", wrap=480, pady=2)

        # 한 줄 교훈 강조
        frame = ctk.CTkFrame(
            self.me_detail, fg_color=("#1A237E", "#1A237E"), corner_radius=10
        )
        frame.grid(row=r, column=0, sticky="ew", padx=10, pady=(14, 6))
        ctk.CTkLabel(
            frame,
            text=f"다음 경기 교훈\n{rev.lesson}",
            font=FU,
            text_color="#E3F2FD",
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
            color=("gray50", "gray55"),
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

    def _render_team_block(
        self, parent: Any, players: list, row: int, *, ally: bool
    ) -> int:
        from lol_coach.static.icons import champion_ctk, item_ctk

        loc = self.loc
        if not players:
            return self._lbl(parent, "참가자 정보 없음", row, color=("gray50", "gray60"))
        for p in players:
            champ = loc.champion(p.champion_name) or p.champion_name
            role = loc.role(p.role)
            me = "  ★나" if p.is_me else ""
            bg = ("#E3F2FD", "gray25") if p.is_me else ("gray90", "gray22")
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


def run_app() -> None:
    """첫 실행 시 API 키 설정 → 메인 창."""
    from lol_coach.gui.setup_dialog import ensure_api_key_dialog
    from lol_coach.log import setup_logging

    setup_logging(verbose=False)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    if not ensure_api_key_dialog(force=False):
        return
    app = CoachApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
