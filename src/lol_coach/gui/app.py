"""롤 실전 코치 GUI — 협곡 조합 분석 · ARAM 아수라장 · 전적."""

from __future__ import annotations

import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach import __version__
from lol_coach.analysis.aram_mayhem import AugmentPick, AugmentValidation, MayhemAdvice, MayhemCoach
from lol_coach.analysis.comp import CompAnalyzer, CompReport
from lol_coach.analysis.draft import DraftCoach
from lol_coach.analysis.review import analyze_match
from lol_coach.config import load_settings, save_api_key, save_player
from lol_coach.gui import components as ui
from lol_coach.modes import MODE_SUMMONERS_RIFT
from lol_coach.riot.client import RiotAPIError, RiotClient
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm
from lol_coach.static.augment_catalog import AugmentCatalog, CatalogError
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer
from lol_coach.static.icons import champion_ctk, item_name_ctk
from lol_coach.ugg.client import UGGClient
from lol_coach.ugg.counters import CounterClient

_THEME = Path(__file__).with_name("theme.json")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme(str(_THEME))

from lol_coach.gui.constants import (
    AI_BODY,
    AI_MODELS,
    AI_SECTION,
    AI_SUMMARY,
    AI_TITLE,
    FB,
    FCH,
    FM,
    FS,
    FT,
    FU,
    PLATFORMS,
    ROLES,
    counter_tier as _counter_tier,
)
from lol_coach.gui.ai_text import ai_key_points as _ai_key_points
from lol_coach.gui.ai_text import ai_lines as _ai_lines

from lol_coach.gui.ai_mixin import AiMixin
from lol_coach.gui.aram_tab import AramTabMixin
from lol_coach.gui.live_mixin import LiveMixin
from lol_coach.gui.me_tab import MeTabMixin
from lol_coach.gui.notify_mixin import NotifyMixin
from lol_coach.gui.sr_tab import SrTabMixin
from lol_coach.gui.update_mixin import UpdateMixin

class CoachApp(
    NotifyMixin,
    UpdateMixin,
    AiMixin,
    SrTabMixin,
    AramTabMixin,
    MeTabMixin,
    LiveMixin,
    ctk.CTk,
):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"롤 실전 코치  v{__version__}")
        # 저장된 창 크기/위치 복원 (ui.json)
        try:
            from lol_coach.config import load_ui_settings

            ui = load_ui_settings()
            geo = str(ui.get("geometry") or "")
            if geo and "x" in geo:
                self.geometry(geo)
            else:
                self.geometry("1040x860")
        except Exception:
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
        self._aram_history: list[tuple[Any, tuple, dict]] = []
        self._sr_autocompletes: list[Any] = []
        self._champ_watcher: Any = None  # ChampSelectWatcher
        self._sr_lcu_sig: tuple = ()
        self._aram_lcu_sig: tuple = ()
        self._ai_gen: int = 0  # AI 카드 generation id (늦은 응답 무시)
        self._latest_version = ""
        self._latest_sha256 = ""
        self._global_hotkey: Any = None

        self._build()
        self._bind_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._boot, daemon=True).start()


    def _on_close(self) -> None:
        try:
            gh = getattr(self, "_global_hotkey", None)
            if gh is not None:
                gh.stop()
                self._global_hotkey = None
        except Exception:
            pass
        for w in (self._watcher, self._champ_watcher):
            try:
                if w is not None:
                    w.stop()
            except Exception:
                pass
        # 창 크기/위치 저장 (다음 실행 시 복원)
        try:
            from lol_coach.config import save_ui_settings

            kw: dict = {"geometry": self.geometry()}
            w = getattr(self, "_widget", None)
            if w is not None:
                try:
                    if w.winfo_exists():
                        kw["widget_geometry"] = w.geometry()
                except Exception:
                    pass
            save_ui_settings(**kw)
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


    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        ctk.CTkLabel(head, text="●", font=FT, text_color=ui.GOLD).pack(
            side="left", padx=(0, 6)
        )
        ctk.CTkLabel(head, text="롤 실전 코치", font=FT).pack(side="left")
        self.status = ctk.CTkLabel(
            head, text="준비 중…", font=FM, text_color=ui.TEXT_DIM
        )
        self.status.pack(side="right")
        ctk.CTkButton(
            head,
            text="📌 위젯 ⌃⇧W",
            width=96,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._toggle_widget,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            head,
            text="📋 복사",
            width=72,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._copy_summary,
        ).pack(side="right", padx=(0, 8))
        self.update_btn = ctk.CTkButton(
            head,
            text="🔄 업데이트",
            width=96,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            state="disabled",
            command=self._start_update,
        )
        self.update_btn.pack(side="right", padx=(0, 8))

        self.tabs = ctk.CTkTabview(
            self,
            corner_radius=12,
            fg_color=ui.PANEL,
            segmented_button_fg_color=ui.INPUT_BG,
            segmented_button_selected_color=ui.GOLD,
            segmented_button_selected_hover_color=ui.GOLD_HOVER,
            segmented_button_unselected_color=ui.INPUT_BG,
            segmented_button_unselected_hover_color=ui.ROW_HOVER,
            text_color=ui.GOLD_SOFT,
            command=self._style_tabs,
        )
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.t_sr = self.tabs.add("소환사의 협곡")
        self.t_aram = self.tabs.add("ARAM 아수라장")
        self.t_me = self.tabs.add("내 전적")
        for t in (self.t_sr, self.t_aram, self.t_me):
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(1, weight=1)
        self._style_tabs()

        self._build_sr()
        self._build_aram()
        self._build_me()


    def _style_tabs(self, *_a: Any) -> None:
        """탭 세그먼트 버튼의 텍스트 색을 상태별로 지정.

        CTk 6.x 탭뷰는 세그먼트 전체에 단일 text_color만 받아서,
        내부 CTkButton에 개별 색을 다시 입힌다 (선택=다크/골드, 비선택=연골드).
        """
        try:
            current = self.tabs.get()
            for name, btn in self.tabs._segmented_button._buttons_dict.items():
                active = name == current
                btn.configure(
                    text_color=ui.ON_GOLD if active else ui.GOLD_SOFT,
                    font=("Malgun Gothic", 12, "bold") if active else ("Malgun Gothic", 12),
                )
        except Exception:
            pass


    def _boot(self) -> None:
        try:
            self.dd.ensure_loaded()
            self.loc.ensure_loaded()
            player = self.settings.riot_id or "소환사 미설정"
            from lol_coach.config import api_key_expiry_hint

            hint = api_key_expiry_hint()
            status = f"데이터 준비됨  ·  {player}"
            if hint:
                status = f"{hint}  ·  {player}"
            self.after(
                0,
                lambda value=status: self.status.configure(text=value),
            )
            self.after(0, self._refresh_ai_status)
            # 저장된 프로필+키가 있으면 마지막 전적 자동 로드
            if self.settings.riot_api_key and self.settings.riot_id:
                self.after(600, self._load_me)
            # 새 버전 확인 (백그라운드, 실패해도 무해)
            threading.Thread(target=self._check_update, daemon=True).start()
        except Exception as exc:
            message = str(exc)
            self.after(
                0,
                lambda value=message: self.status.configure(text=f"오류: {value}"),
            )


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
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", padx=10, pady=(14, 4))
        bar = ctk.CTkFrame(head, width=3, height=17, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 8))
        bar.pack_propagate(False)
        ctk.CTkLabel(head, text=title, font=FS, anchor="w").pack(side="left")
        return row + 1


    def _row_frame(self, parent: Any, row: int, padx: int = 10, pady: int = 2) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=ui.ROW, corner_radius=10, border_width=1, border_color=ui.BORDER
        )
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
            selected = b.cget("text") == label
            b.configure(
                fg_color=ui.GOLD if selected else ui.PANEL,
                hover_color=ui.GOLD_HOVER if selected else ui.ROW_HOVER,
                text_color=ui.ON_GOLD if selected else ui.GOLD_SOFT,
            )


    def _toggle_widget(self) -> None:
        """미니 위젯 열기/닫기 (단축키: Ctrl+Shift+W)."""
        from lol_coach.gui.widget import MiniWidget

        if self._widget is not None and self._widget.winfo_exists():
            try:
                self._widget.destroy()
            except Exception:
                pass
            self._widget = None
            self._notify("미니 위젯 닫음", level="info", ms=1800)
            return
        self._widget = MiniWidget(
            self,
            on_close=lambda: setattr(self, "_widget", None),
        )
        # 저장된 위젯 위치 복원
        try:
            from lol_coach.config import load_ui_settings

            geo = str(load_ui_settings().get("widget_geometry") or "")
            if geo and "x" in geo:
                self._widget.geometry(geo)
        except Exception:
            pass
        if self._last_summary_lines:
            self._widget.set_summary(
                self._last_summary_title, self._last_summary_lines
            )
        self._notify("미니 위젯 열림 · Ctrl+Shift+W 로 토글", level="ok", ms=2500)

    def _bind_hotkeys(self) -> None:
        """앱 포커스 단축키 + (Windows) 전역 핫키."""
        try:
            self.bind_all("<Control-Shift-W>", lambda _e: self._toggle_widget())
            self.bind_all("<Control-Shift-w>", lambda _e: self._toggle_widget())
        except Exception:
            pass
        # 전역 핫키 — 게임 포커스 중에도 토글 (등록 실패해도 무해)
        try:
            from lol_coach.gui.global_hotkey import GlobalHotkey, schedule_on_ui

            def _fire() -> None:
                schedule_on_ui(self, self._toggle_widget)

            gh = GlobalHotkey(_fire)
            if gh.start():
                self._global_hotkey = gh
            else:
                self._global_hotkey = None
        except Exception:
            self._global_hotkey = None


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
                self._notify("복사할 결과가 아직 없습니다.", level="warn")
                return
            text = self._last_summary_title + "\n" + "\n".join(self._last_summary_lines)
            self.clipboard_clear()
            self.clipboard_append(text)
            self._notify("📋 요약 복사됨", level="ok", ms=2200)
        except Exception as exc:
            self._notify(f"클립보드 복사 실패: {exc}", level="error")


    def _item_tooltip_text(self, item_name: str) -> str:
        try:
            iid = self.dd.item_id_for_name(item_name)
            return self.dd.item_tooltip(iid)
        except Exception:
            return ""


    def _attach_item_tooltip(self, widget: Any, item_name: str) -> None:
        from lol_coach.gui.tooltip import ToolTip

        ToolTip(widget, lambda: self._item_tooltip_text(item_name))



def _acquire_single_instance() -> bool:
    """Windows 뮤텍스로 중복 실행 방지. 이미 실행 중이면 False."""
    try:
        import ctypes

        mutex = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Global\\LOLPersonalCoach"
        )
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            try:
                ctypes.windll.kernel32.CloseHandle(mutex)
            except Exception:
                pass
            return False
        return True
    except Exception:
        return True  # 비 Windows / 실패 시 중복 방지 없이 진행


def run_app() -> None:
    """첫 실행 시 API 키 설정 → 메인 창."""
    if not _acquire_single_instance():
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(
                "롤 실전 코치",
                "이미 실행 중입니다.\n작업 표시줄의 기존 창을 확인해 주세요.",
            )
            root.destroy()
        except Exception:
            pass
        return
    from lol_coach.gui.setup_dialog import ensure_api_key_dialog
    from lol_coach.log import setup_logging

    setup_logging(verbose=False)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme(str(_THEME))
    if not ensure_api_key_dialog(force=False):
        return
    app = CoachApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
