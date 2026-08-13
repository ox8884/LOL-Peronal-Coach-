"""롤 실전 코치 GUI — 협곡 조합 분석 · ARAM 아수라장 · 전적."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from typing import Any

import customtkinter as ctk

from lol_coach import __version__
from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.analysis.comp import CompAnalyzer
from lol_coach.analysis.draft import DraftCoach
from lol_coach.blitz.client import BlitzClient
from lol_coach.config import Settings, clamp_window_geometry, load_settings
from lol_coach.gui import components as ui
from lol_coach.gui.ai_mixin import AiMixin
from lol_coach.gui.aram_tab import AramTabMixin
from lol_coach.gui.constants import FB, FM, FT, FU, ROLES
from lol_coach.gui.live_mixin import LiveMixin
from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.gui.me_tab import MeTabMixin
from lol_coach.gui.notify_mixin import NotifyMixin
from lol_coach.gui.sr_tab import SrTabMixin
from lol_coach.gui.update_mixin import UpdateMixin
from lol_coach.log import get_logger
from lol_coach.riot.client import RiotClient
from lol_coach.riot.models import PlayerProfile, RecentForm
from lol_coach.static.augment_catalog import AugmentCatalog
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer

_log = get_logger("gui")


def _apply_startup_theme() -> Path:
    """ui.json 스킨 → 팔레트 + CTk theme (다크/라이트 스킨 지원)."""
    from lol_coach.gui.components import (
        appearance_mode_for,
        apply_skin,
        load_skin_name,
        resolve_theme_path,
    )

    skin = load_skin_name()
    apply_skin(skin)
    path = resolve_theme_path(skin)
    ctk.set_appearance_mode(appearance_mode_for(skin))
    ctk.set_default_color_theme(str(path))
    return path


_THEME = _apply_startup_theme()


class CoachApp(
    NotifyMixin,
    UpdateMixin,
    AiMixin,
    SrTabMixin,
    AramTabMixin,
    MeTabMixin,
    MeDetailMixin,
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
                self.geometry(
                    clamp_window_geometry(
                        geo,
                        screen_width=self.winfo_screenwidth(),
                        screen_height=self.winfo_screenheight(),
                    )
                )
            else:
                self.geometry("1120x920")
        except Exception:
            self.geometry("1120x920")
        self.minsize(960, 780)

        self.dd = DataDragon(language="ko_KR")
        self.loc = get_localizer()
        self.blitz = BlitzClient()
        self.counters = self.blitz
        self.draft = DraftCoach(self.dd)
        self.comp = CompAnalyzer(self.dd)
        self.mayhem = MayhemCoach(self.dd)
        self._aug_catalog = AugmentCatalog()
        self.settings: Settings = load_settings()

        self.riot: RiotClient | None = None
        self.profile: PlayerProfile | None = None
        self.form: RecentForm | None = None
        self._growth_report: Any = None
        self._practice_progress: Any = None
        self._busy: set[str] = set()
        self._role_btns: list[ctk.CTkButton] = []
        # (소유 프레임, CTkImage) — 프레임 클리어 시 함께 해제해 누수 방지
        self._icon_refs: list[tuple[Any, Any]] = []
        self._render_target: Any = None
        self._widget: Any = None  # MiniWidget
        self._watcher: Any = None  # GameEndWatcher
        self._watcher_puuid: str | None = None
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
        self._ui_scale_base: float | None = None
        self._font_scale: float = 1.0
        self._lcu_banned_names: list[str] = []
        self._closing: bool = False
        self._threads: set[threading.Thread] = set()

        # UI 배율 (글자·위젯) — ui.json font_scale
        try:
            from lol_coach.config import load_ui_settings
            from lol_coach.gui.constants import apply_tk_ui_scale

            raw = load_ui_settings().get("font_scale", 1.0)
            self._font_scale = float(raw)
            self._ui_scale_base = float(self.tk.call("tk", "scaling"))
            apply_tk_ui_scale(self, self._font_scale, base=self._ui_scale_base)
        except Exception:
            pass

        self._build()
        self._bind_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_mayhem_select_watcher()
        self._spawn_thread(self._boot)

    def _spawn_thread(self, target: Any, *args: Any) -> threading.Thread:
        """워커 스레드 생성·추적 — 종료 시 join 가능하도록 레지스트리에 보관."""

        def _runner() -> None:
            try:
                target(*args)
            finally:
                self._threads.discard(threading.current_thread())

        t = threading.Thread(target=_runner, daemon=True)
        self._threads.add(t)
        t.start()
        return t

    def after(self, ms: int, func: Any = None, *args: Any) -> Any:
        """종료 중에는 워커→메인 마샬링을 차단해 파괴 중 위젯 접근을 막는다."""
        if getattr(self, "_closing", False) and func is not None:
            return None
        try:
            return ctk.CTk.after(self, ms, func, *args)
        except RuntimeError:
            # 위젯 파괴 후 남은 after 호출 — 조용히 무시
            return None

    def report_callback_exception(self, exc: BaseException, val: BaseException, tb: Any) -> None:
        """Tk 콜백(after 등) 예외를 조용히 삼키지 않고 로그 + 상태바로 노출."""
        try:
            _log.error(
                "Tk 콜백 예외: %s",
                val,
                exc_info=(type(exc), val, tb),
            )
        except Exception:
            pass
        try:
            from lol_coach.gui.errors import format_user_error

            msg = format_user_error(val)
            status = getattr(self, "status", None)
            if status is not None:
                status.configure(text=f"⚠ {msg}")
        except Exception:
            pass

    def _on_close(self) -> None:
        self._closing = True
        try:
            gh = getattr(self, "_global_hotkey", None)
            if gh is not None:
                gh.stop()
                self._global_hotkey = None
            gh_aug = getattr(self, "_global_hotkey_aug", None)
            if gh_aug is not None:
                gh_aug.stop()
                self._global_hotkey_aug = None
        except Exception:
            pass
        for w in (
            self._watcher,
            self._champ_watcher,
            getattr(self, "_game_start_watcher", None),
            getattr(self, "_mayhem_select_watcher", None),
            getattr(self, "_mayhem_offer_watcher", None),
        ):
            try:
                if w is not None:
                    w.stop()
            except Exception:
                pass
        # 진행 중인 워커 스레드가 파괴 중인 위젯에 접근하지 않도록 짧게 join
        for t in list(self._threads):
            try:
                if t.is_alive() and t is not threading.current_thread():
                    t.join(timeout=0.5)
            except Exception:
                pass
        # 창 크기/위치 저장 (다음 실행 시 복원)
        try:
            from lol_coach.config import save_ui_settings

            kw: dict = {
                "geometry": self.geometry(),
                "font_scale": getattr(self, "_font_scale", 1.0),
            }
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
        ctk.CTkLabel(head, text="●", font=FT, text_color=ui.GOLD).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(head, text="롤 실전 코치", font=FT).pack(side="left")
        # 현재 스킨 배지 (설정에서 바꾼 뒤 재시작하면 표시)
        try:
            from lol_coach.gui.components import SKIN_SHORT, active_skin

            skin_txt = SKIN_SHORT.get(active_skin(), active_skin())
            self._skin_badge = ctk.CTkLabel(
                head,
                text=f"  {skin_txt}  ",
                font=FM,
                text_color=ui.ON_GOLD,
                fg_color=ui.GOLD,
                corner_radius=10,
            )
            self._skin_badge.pack(side="left", padx=(10, 0))
        except Exception:
            self._skin_badge = None
        self.status = ctk.CTkLabel(head, text="준비 중…", font=FM, text_color=ui.TEXT_DIM)
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
        ctk.CTkButton(
            head,
            text="⚙ 설정",
            width=72,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._open_settings,
        ).pack(side="right", padx=(0, 8))
        # 화면 배율 (빠른 접근 — 상세는 설정 창)
        try:
            from lol_coach.gui.constants import FONT_SCALE_CHOICES

            scale_vals = list(FONT_SCALE_CHOICES)
            cur_s = f"{getattr(self, '_font_scale', 1.0):.1f}"
            if cur_s not in scale_vals:
                scale_vals.insert(0, cur_s)
            self.font_scale_var = tk.StringVar(value=cur_s)
            ctk.CTkOptionMenu(
                head,
                variable=self.font_scale_var,
                values=scale_vals,
                width=64,
                height=28,
                font=FM,
                command=self._set_font_scale,
            ).pack(side="right", padx=(0, 8))
            ctk.CTkLabel(head, text="배율", font=FM, text_color=ui.TEXT_DIM).pack(
                side="right", padx=(0, 2)
            )
        except Exception:
            pass

        self._init_pref_vars()

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

    def _boot_after(self, delay: int, func) -> None:
        """_boot 스레드에서 after() 호출 — 메인루프 시작 전이면 잠시 대기 후 재시도.

        앱 시작 직후 warm 캐시면 _boot 스레드가 mainloop() 시작보다 빨리
        after() 를 부르는 레이스가 있다 (RuntimeError: main thread is not in
        main loop). 위젯이 살아있는 동안 최대 ~5초만 기다렸다가 성공한다.
        """
        import time as _time

        for _ in range(100):
            try:
                self.after(delay, func)
                return
            except RuntimeError:
                _time.sleep(0.05)
            except Exception:
                return  # 위젯 파괴 등 — 재시도 불가

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
            self._boot_after(
                0,
                lambda value=status: self.status.configure(text=value),
            )
            self._boot_after(0, self._refresh_ai_status)
            # 저장된 프로필+키가 있으면 마지막 전적 자동 로드
            if self.settings.riot_api_key and self.settings.riot_id:
                self._boot_after(600, self._load_me)
            # 새 버전 확인 (백그라운드, 실패해도 무해)
            self._spawn_thread(self._check_update)
        except Exception as exc:
            message = str(exc)
            self._boot_after(
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
        ctk.CTkLabel(parent, **kw).grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        return row + 1

    def _sec(self, parent: Any, title: str, row: int) -> int:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        # 결과 영역 밀도 높이기 — 섹션 간격 축소
        head.grid(row=row, column=0, sticky="ew", padx=8, pady=(8, 2))
        bar = ctk.CTkFrame(head, width=3, height=14, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 6))
        bar.pack_propagate(False)
        ctk.CTkLabel(head, text=title, font=FU, anchor="w", text_color=ui.GOLD_SOFT).pack(
            side="left"
        )
        return row + 1

    def _row_frame(self, parent: Any, row: int, padx: int = 10, pady: int = 2) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent,
            fg_color=ui.ROW,
            corner_radius=ui.ROW_RADIUS,
            border_width=ui.ROW_BORDER,
            border_color=ui.BORDER,
        )
        frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        return frame

    def _entry_row(
        self, parent: Any, row: int, label: str, var: tk.StringVar, ph: str = ""
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=FU, width=90, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=5
        )
        entry = ctk.CTkEntry(parent, textvariable=var, placeholder_text=ph, font=FU, height=34)
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
            self._widget.set_summary(self._last_summary_title, self._last_summary_lines)
        self._notify("미니 위젯 열림 · Ctrl+Shift+W 로 토글", level="ok", ms=2500)

    def _set_font_scale(self, value: str) -> None:
        """헤더/설정 드롭다운 — UI 배율 변경."""
        try:
            scale = float(value)
        except (TypeError, ValueError):
            return
        self._font_scale = scale
        try:
            from lol_coach.config import save_ui_settings
            from lol_coach.gui.constants import apply_tk_ui_scale

            base = getattr(self, "_ui_scale_base", None)
            if base is None:
                base = float(self.tk.call("tk", "scaling")) / max(scale, 0.01)
                self._ui_scale_base = base
            apply_tk_ui_scale(self, scale, base=base)
            save_ui_settings(font_scale=scale)
            self._notify(
                f"화면 배율 {scale}x 적용 (일부 글자는 다시 그리면 반영)",
                level="ok",
                ms=2800,
            )
        except Exception as exc:
            self._notify(f"배율 변경 실패: {exc}", level="error")

    def _init_pref_vars(self) -> None:
        """설정 창·런타임이 공유하는 기본 변수 (탭 빌드 전에 생성)."""
        from lol_coach import llm as _llm
        from lol_coach.config import (
            auto_open_latest_match_enabled,
            game_end_auto_review_enabled,
            game_end_notify_enabled,
        )

        if not hasattr(self, "llm_key_var"):
            self.llm_key_var = tk.StringVar(value=self.settings.llm_api_key or "")
        if not hasattr(self, "llm_model_var"):
            cur = self.settings.llm_model or _llm.DEFAULT_MODEL
            self.llm_model_var = tk.StringVar(value=cur)
        if not hasattr(self, "game_end_notify_var"):
            self.game_end_notify_var = tk.BooleanVar(value=game_end_notify_enabled())
        if not hasattr(self, "game_end_auto_review_var"):
            self.game_end_auto_review_var = tk.BooleanVar(value=game_end_auto_review_enabled())
        if not hasattr(self, "auto_open_latest_var"):
            self.auto_open_latest_var = tk.BooleanVar(value=auto_open_latest_match_enabled())
        if not hasattr(self, "game_start_notify_var"):
            from lol_coach.config import game_start_notify_enabled

            self.game_start_notify_var = tk.BooleanVar(value=game_start_notify_enabled())
        if not hasattr(self, "discord_review_var"):
            from lol_coach.config import discord_review_enabled

            self.discord_review_var = tk.BooleanVar(value=discord_review_enabled())
        if not hasattr(self, "discord_webhook_var"):
            from lol_coach.config import discord_webhook_url

            self.discord_webhook_var = tk.StringVar(value=discord_webhook_url())
        if not hasattr(self, "ai_status_lbl"):
            self.ai_status_lbl = None
        if not hasattr(self, "font_scale_var"):
            cur_s = f"{getattr(self, '_font_scale', 1.0):.1f}"
            self.font_scale_var = tk.StringVar(value=cur_s)

    def _open_settings(self) -> None:
        """통합 설정 창 (AI · 알림 · 배율 · 단축키 · API 키)."""
        from lol_coach.gui.settings_dialog import open_settings

        open_settings(self)

    def _apply_skin_live(self, skin: str) -> None:
        """스킨을 저장하고 UI를 즉시 다시 그려 적용 (재시작 불필요)."""
        if getattr(self, "_skin_switching", False):
            return
        from lol_coach.config import save_ui_settings
        from lol_coach.gui.components import (
            SKIN_LABELS,
            active_skin,
            appearance_mode_for,
            apply_skin,
            normalize_skin_name,
            resolve_theme_path,
        )

        name = normalize_skin_name(skin)
        label = SKIN_LABELS.get(name, name)
        if name == active_skin() and not getattr(self, "_force_skin_rebuild", False):
            self._notify(f"이미 적용 중: {label}", level="info", ms=2000)
            return

        self._skin_switching = True
        reopen_settings = False
        try:
            try:
                save_ui_settings(ui_skin=name)
            except Exception as exc:
                self._notify(f"스킨 저장 실패: {exc}", level="error")
                return

            # 유지할 상태
            try:
                tab_name = self.tabs.get()
            except Exception:
                tab_name = None
            form = getattr(self, "form", None)
            ranks = getattr(self, "_last_ranks", None)

            # 설정 창 닫기 (Toplevel — 리빌드 후 다시 열기)
            win = getattr(self, "_settings_win", None)
            if win is not None:
                reopen_settings = True
                try:
                    win.destroy()
                except Exception:
                    pass
                self._settings_win = None

            apply_skin(name)
            path = resolve_theme_path(name)
            ctk.set_appearance_mode(appearance_mode_for(name))
            ctk.set_default_color_theme(str(path))
            global _THEME
            _THEME = path

            # 메인 창 자식만 제거 (StringVar·상태 유지)
            for child in list(self.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
            self._icon_refs = []
            self._sr_autocompletes = []
            self._role_btns = []
            self._me_match_btns = []
            self._toast_win = None
            self.ai_status_lbl = None

            self._build()
            # 배율 재적용
            try:
                scale = float(getattr(self, "_font_scale", 1.0))
                from lol_coach.gui.constants import apply_tk_ui_scale

                base = getattr(self, "_ui_scale_base", None)
                if base is not None:
                    apply_tk_ui_scale(self, scale, base=base)
            except Exception:
                pass

            if tab_name:
                try:
                    self.tabs.set(tab_name)
                    self._style_tabs()
                except Exception:
                    pass

            # 전적 결과가 있으면 다시 그림
            if form is not None:
                try:
                    self._render_me(form, ranks=ranks)
                except Exception as exc:
                    _log.debug("스킨 적용 후 전적 재렌더 실패(무시): %s", exc)

            self._notify(f"스킨 적용: {label}", level="ok", ms=2500)

            if reopen_settings:
                # 연속으로 스킨 고르기 쉽게 설정 다시 열기
                self.after(80, self._open_settings)
        finally:
            self._skin_switching = False

    def _bind_hotkeys(self) -> None:
        """앱 포커스 단축키 + (Windows) 전역 핫키."""
        try:
            self.bind_all("<Control-Shift-W>", lambda _e: self._toggle_widget())
            self.bind_all("<Control-Shift-w>", lambda _e: self._toggle_widget())
            self.bind_all("<Control-Shift-A>", lambda _e: self._capture_offered_augments())
            self.bind_all("<Control-Shift-a>", lambda _e: self._capture_offered_augments())
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

            def _fire_aug() -> None:
                schedule_on_ui(self, self._capture_offered_augments)

            gh_aug = GlobalHotkey(
                _fire_aug,
                hotkey_id=0x4C4F4C32,
                vk=0x41,  # A
            )
            if gh_aug.start():
                self._global_hotkey_aug = gh_aug
            else:
                self._global_hotkey_aug = None
        except Exception:
            if not getattr(self, "_global_hotkey", None):
                self._global_hotkey = None
            self._global_hotkey_aug = None

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

        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\LOLPersonalCoach")
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
    # 스킨은 모듈 import 시 1회 적용. 여기서 한 번 더 동기화 (ui.json 반영)
    theme_path = _apply_startup_theme()
    global _THEME
    _THEME = theme_path
    if not ensure_api_key_dialog(force=False):
        return
    app = CoachApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
