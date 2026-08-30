"""롤 실전 코치 GUI — 협곡 조합 분석 · ARAM 아수라장 · 전적."""

from __future__ import annotations

import re
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
from lol_coach.config import Settings, load_settings
from lol_coach.gui import components as ui
from lol_coach.gui import icons
from lol_coach.gui.ai_mixin import AiMixin
from lol_coach.gui.constants import FB, FCH, FM, FONT_UI, FS, FU, ROLES
from lol_coach.gui.live_mixin import LiveMixin
from lol_coach.gui.notify_mixin import NotifyMixin
from lol_coach.gui.session_mixin import SessionMixin
from lol_coach.gui.tierlist_mixin import TierListMixin
from lol_coach.gui.update_mixin import UpdateMixin
from lol_coach.log import get_logger
from lol_coach.riot.client import RiotClient
from lol_coach.riot.models import PlayerProfile, RecentForm
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


class _TabNav:
    """구 CTkTabview 호환 shim — ``tabs.get()/set()`` 을 사이드바로 라우팅."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def get(self) -> str:
        return self._app._current_nav

    def set(self, name: str) -> None:
        self._app._select_nav(name)


class CoachApp(
    NotifyMixin,
    UpdateMixin,
    AiMixin,
    LiveMixin,
    SessionMixin,
    TierListMixin,
    ctk.CTk,
):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"롤 실전 코치  v{__version__}")
        # 저장된 창 크기/위치 복원 (ui.json) — 멀티모니터 인식
        try:
            from lol_coach.config import clamp_window_geometry, get_virtual_screen, load_ui_settings

            ui = load_ui_settings()
            geo = str(ui.get("geometry") or "")
            vx, vy, vw, vh = get_virtual_screen()
            if geo and "x" in geo:
                self.geometry(
                    clamp_window_geometry(
                        geo,
                        screen_width=self.winfo_screenwidth(),
                        screen_height=self.winfo_screenheight(),
                        vscreen_x=vx,
                        vscreen_y=vy,
                        vscreen_width=vw,
                        vscreen_height=vh,
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
        self.mayhem = MayhemCoach(self.dd, blitz_client=self.blitz)
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
        self._live_client_watcher: Any = None  # LiveClientGameWatcher
        self._live_client_briefed_champ: str = ""
        self._aram_lcu_sig: tuple = ()
        self._ai_gen: int = 0  # AI 카드 generation id (늦은 응답 무시)
        self._latest_version = ""
        self._latest_sha256 = ""
        self._global_hotkey: Any = None
        self._ui_scale_base: float | None = None
        self._font_scale: float = 1.0
        self._lcu_banned_names: list[str] = []
        self._closing: bool = False
        self._overlay_active: bool = False  # 게임 중 증강 오버레이 표시 중
        self._pending_update_installer: str = ""  # 종료 후 실행할 업데이트 인스톨러
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
        self._start_live_client_watcher()
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
        except Exception:
            pass
        # 라이브 세션 워처 정리 (게임 종료/시작 워처 소유권은 세션에)
        sess = getattr(self, "_live_session", None)
        if sess is not None:
            sess.stop_game_end_watcher()
            sess.stop_game_start_watcher()
        for w in (
            getattr(self, "_mayhem_select_watcher", None),
            getattr(self, "_live_client_watcher", None),
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

    # -- cross-tab facade: 탭 믹신 상속 제거 후 SR/ARAM/live 간 호출을
    #    탭 인스턴스로 라우팅 (gui-service-split 단계5)
    def _apply_lcu_aram(self, info: Any, *, force: bool = False) -> None:
        self._ensure_tab_built("ARAM 아수라장")
        self.aram_tab._apply_lcu_aram(info, force=force)

    def _apply_live_aram(self, fill: Any, *, confirm_sr: bool = True) -> None:
        self._ensure_tab_built("ARAM 아수라장")
        self.aram_tab._apply_live_aram(fill, confirm_sr=confirm_sr)

    def _start_aram_champ_watch(self) -> None:
        self._ensure_tab_built("ARAM 아수라장")
        self.aram_tab._start_aram_champ_watch()

    def _switch_to_aram_briefing(self, info: Any) -> None:
        """SR 탭에서 ARAM 밴픽 감지 시 — ARAM 탭으로 전환해 브리핑 (cross-tab facade)."""
        self._apply_lcu_aram(info, force=True)
        self._start_aram_champ_watch()

    def _build(self) -> None:
        """앱 셸: 좌측 사이드바 내비게이션 + 상단 툴바 + 콘텐츠 스택."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_sidebar()

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(12, 6))
        self.status = ctk.CTkLabel(
            head, text="준비 중…", font=FM, text_color=ui.TEXT_DIM, anchor="w"
        )
        self.status.pack(side="left", padx=(4, 8))
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
            ).pack(side="left", padx=(16, 0))
            ctk.CTkLabel(head, text="배율", font=FM, text_color=ui.TEXT_DIM).pack(
                side="left", padx=(6, 0)
            )
        except Exception:
            pass

        from lol_coach.gui.tooltip import ToolTip

        fam = icons.icon_font()
        for icon_name, tip, cmd in (
            ("pin", "미니 위젯 열기/닫기 (Ctrl+Shift+W)", self._toggle_widget),
            ("copy", "마지막 분석 요약 클립보드 복사", self._copy_summary),
        ):
            b = ctk.CTkButton(
                head,
                text=icons.glyph(icon_name),
                width=36 if fam else 72,
                height=28,
                font=(fam, 13) if fam else FM,
                **ui.btn(*ui.BTN_SECONDARY),
                command=cmd,
            )
            b.pack(side="right", padx=(0, 8))
            ToolTip(b, lambda t=tip: t)
        self.update_btn = ctk.CTkButton(
            head,
            text="업데이트",
            width=92,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._check_update_manual,
        )
        self.update_btn.pack(side="right", padx=(0, 8))
        ToolTip(self.update_btn, lambda: "새 버전 확인")

        self._init_pref_vars()

        content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        content.grid(row=1, column=1, sticky="nsew", padx=(0, 14), pady=(0, 12))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self._frames: dict[str, ctk.CTkBaseClass] = {
            "소환사의 협곡": ctk.CTkFrame(content, fg_color=ui.PANEL, corner_radius=12),
            "ARAM 아수라장": ctk.CTkFrame(content, fg_color=ui.PANEL, corner_radius=12),
            "티어표": ctk.CTkFrame(content, fg_color=ui.PANEL, corner_radius=12),
            "내 전적": ctk.CTkFrame(content, fg_color=ui.PANEL, corner_radius=12),
            "세션 리포트": ctk.CTkFrame(content, fg_color=ui.PANEL, corner_radius=12),
        }
        self.t_sr = self._frames["소환사의 협곡"]
        self.t_aram = self._frames["ARAM 아수라장"]
        self.t_tierlist = self._frames["티어표"]
        self.t_me = self._frames["내 전적"]
        self.t_session = self._frames["세션 리포트"]
        for t in self._frames.values():
            t.grid(row=0, column=0, sticky="nsew")
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(1, weight=1)
        # 탭 객체만 만들고 위젯 빌드는 첫 방문 시로 지연 — 기동 속도 개선
        self._tab_built: set[str] = set()
        from lol_coach.gui.tabs.aram import AramTab
        from lol_coach.gui.tabs.me import MeTab
        from lol_coach.gui.tabs.sr import SrTab

        self.sr_tab = SrTab(self)  # type: ignore[abstract]
        self.aram_tab = AramTab(self)  # type: ignore[abstract]
        self.me_tab = MeTab(self)  # type: ignore[abstract]
        self.tabs = _TabNav(self)
        self._select_nav(getattr(self, "_current_nav", "소환사의 협곡"))

    def _ensure_tab_built(self, name: str) -> None:
        """탭 위젯을 필요 시 1회 빌드 (기동 시 첫 화면만 그린다)."""
        if name in self._tab_built or name not in self._frames:
            return
        self._tab_built.add(name)
        try:
            if name == "소환사의 협곡":
                self.sr_tab._build_sr()
            elif name == "ARAM 아수라장":
                self.aram_tab._build_aram()
            elif name == "내 전적":
                self.me_tab._build_me()
            elif name == "티어표":
                self._build_tierlist()
            elif name == "세션 리포트":
                self._build_session()
        except Exception:
            self._tab_built.discard(name)
            _log.exception("탭 지연 빌드 실패: %s", name)

    def _build_sidebar(self) -> None:
        """좌측 사이드바 — 로고·내비게이션·설정."""
        side = ctk.CTkFrame(self, width=208, corner_radius=0, fg_color=ui.PANEL)
        side.grid(row=0, column=0, rowspan=2, sticky="nsw")
        side.grid_propagate(False)

        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.pack(fill="x", padx=18, pady=(18, 2))
        fam = icons.icon_font()
        if fam:
            ctk.CTkLabel(logo, text=icons.glyph("trophy"), font=(fam, 19), text_color=ui.GOLD).pack(
                side="left", padx=(0, 9)
            )
        ctk.CTkLabel(
            logo, text="롤 실전 코치", font=FS, text_color=ui.TEXT_BRIGHT, anchor="w"
        ).pack(side="left")

        meta = ctk.CTkFrame(side, fg_color="transparent")
        meta.pack(fill="x", padx=18, pady=(2, 16))
        ctk.CTkLabel(meta, text=f"v{__version__}", font=FCH, text_color=ui.TEXT_MUTE).pack(
            side="left"
        )
        # 현재 스킨 배지 (설정에서 바꾼 뒤 재시작하면 표시)
        try:
            from lol_coach.gui.components import SKIN_SHORT, active_skin

            skin_txt = SKIN_SHORT.get(active_skin(), active_skin())
            self._skin_badge = ctk.CTkLabel(
                meta,
                text=f"  {skin_txt}  ",
                font=FCH,
                text_color=ui.ON_GOLD,
                fg_color=ui.GOLD,
                corner_radius=10,
            )
            self._skin_badge.pack(side="left", padx=(8, 0))
        except Exception:
            self._skin_badge = None

        self._nav_items: dict[str, tuple[Any, Any, Any, Any]] = {}
        for name, icon_name in (
            ("소환사의 협곡", "game"),
            ("ARAM 아수라장", "lightning"),
            ("티어표", "trophy"),
            ("내 전적", "history"),
            ("세션 리포트", "stats"),
        ):
            self._nav_items[name] = self._nav_item(side, name, icon_name)

        # 하단 고정: 설정
        spacer = ctk.CTkFrame(side, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        self._nav_items["설정"] = self._nav_item(
            side, "설정", "settings", command=self._open_settings
        )

    def _nav_item(
        self, parent: Any, name: str, icon_name: str, *, command: Any | None = None
    ) -> tuple[Any, Any, Any, Any]:
        """사이드바 내비 아이템 (아이콘+텍스트 행). (row, bar, icon, label) 반환."""
        row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=10)
        row.pack(fill="x", padx=10, pady=1)
        bar = ctk.CTkFrame(row, width=3, height=18, corner_radius=2, fg_color="transparent")
        bar.pack(side="left", padx=(9, 6), pady=9)
        bar.pack_propagate(False)
        fam = icons.icon_font()
        ic = ctk.CTkLabel(
            row,
            text=icons.glyph(icon_name),
            font=(fam, 14) if fam else FB,
            text_color=ui.TEXT_DIM,
            width=22,
        )
        ic.pack(side="left", pady=9)
        lbl = ctk.CTkLabel(row, text=name, font=FB, text_color=ui.TEXT, anchor="w")
        lbl.pack(side="left", padx=(7, 8), pady=9)
        activate = command if command is not None else (lambda n=name: self._select_nav(n))
        for w in (row, bar, ic, lbl):
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
            w.bind("<Button-1>", lambda _e: activate())

        def _on_enter(_e: Any) -> None:
            row.configure(fg_color=ui.ROW_HOVER)

        def _on_leave(_e: Any) -> None:
            self._refresh_nav_styles()

        row.bind("<Enter>", _on_enter)
        row.bind("<Leave>", _on_leave)
        return row, bar, ic, lbl

    def _select_nav(self, name: str) -> None:
        """사이드바에서 화면 전환. 구 tabs.set(name) 호환 진입점."""
        if name not in self._frames:
            name = next(iter(self._frames))
        self._ensure_tab_built(name)
        self._current_nav = name
        self._frames[name].tkraise()
        self._refresh_nav_styles()
        # 세션 리포트·티어표는 열 때 1회 로드 (재열기는 새로고침 버튼)
        if name == "세션 리포트" and not getattr(self, "_session_loaded", False):
            self._load_session()
        if name == "티어표" and not getattr(self, "_tierlist_loaded", False):
            self._load_tierlist()

    def _refresh_nav_styles(self) -> None:
        """내비 아이템 선택/비선택 상태 색 갱신."""
        current = getattr(self, "_current_nav", "")
        for name, (row, bar, ic, lbl) in self._nav_items.items():
            sel = name == current
            row.configure(fg_color=ui.INPUT_BG if sel else "transparent")
            bar.configure(fg_color=ui.GOLD if sel else "transparent")
            ic.configure(text_color=ui.GOLD if sel else ui.TEXT_DIM)
            lbl.configure(
                text_color=ui.TEXT_BRIGHT if sel else ui.TEXT,
                font=(FONT_UI, 12, "bold") if sel else FB,
            )

    def _style_tabs(self, *_a: Any) -> None:
        """(호환) 구 CTkTabview 세그먼트 스타일링 자리 — 사이드바 상태 갱신."""
        self._refresh_nav_styles()

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
                self._boot_after(600, self._boot_load_me)
            # 새 버전 확인 (백그라운드, 실패해도 무해)
            self._spawn_thread(self._check_update)
        except Exception as exc:
            message = str(exc)
            self._boot_after(
                0,
                lambda value=message: self.status.configure(text=f"오류: {value}"),
            )

    def _boot_load_me(self) -> None:
        """부팅 시 자동 전적 로드 — 내 전적 탭 위젯을 필요 시 빌드 후 로드."""
        self._ensure_tab_built("내 전적")
        self.me_tab._load_me()

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
        # 섹션 제목은 장식 이모지를 걷어내고 타이포 위계로만 강조
        title = re.sub(r"^[^\w가-힣\"'(]+", "", str(title)).strip()
        if not title:
            title = "-"
        head = ctk.CTkFrame(parent, fg_color="transparent")
        # 섹션 제목 위계 강화 — 바·타이포·여백 크게
        head.grid(row=row, column=0, sticky="ew", padx=10, pady=(16, 6))
        bar = ctk.CTkFrame(head, width=5, height=20, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 10))
        bar.pack_propagate(False)
        ctk.CTkLabel(head, text=title, font=FS, anchor="w", text_color=ui.TEXT_BRIGHT).pack(
            side="left"
        )
        return row + 1

    def _row_frame(
        self, parent: Any, row: int, padx: int = 10, pady: int | tuple[int, int] = 2
    ) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent,
            fg_color=ui.ROW,
            corner_radius=ui.ROW_RADIUS,
            border_width=ui.ROW_BORDER,
            border_color=ui.BORDER,
        )
        frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)

        # 결과 카드 호버 — 테두리 골드 + 배경 살짝 밝게
        def _on_enter(_e: Any, f: ctk.CTkFrame = frame) -> None:
            f.configure(border_color=ui.GOLD, fg_color=ui.ROW_HOVER)

        def _on_leave(_e: Any, f: ctk.CTkFrame = frame) -> None:
            f.configure(border_color=ui.BORDER, fg_color=ui.ROW)

        frame.bind("<Enter>", _on_enter)
        frame.bind("<Leave>", _on_leave)
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

    def _ensure_widget_open(self) -> None:
        """미니 위젯이 닫혀 있으면 연다 (오버레이 자동 표시용)."""
        w = self._widget
        if w is not None and w.winfo_exists():
            return
        self._toggle_widget()  # 닫힌 상태 → 열림

    def _push_mayhem_overlay(self, champ_ko: str, attempt: int = 0) -> None:
        """게임 중 증강 추천 오버레이 — 미니 위젯에 챔피언 맞춤 TOP3 표시.

        ARAM 자동 브리핑 요약이 오버레이를 덮어쓸 수 있어, 최대 3회까지
        마지막 요약을 확인해 다시 푸시한다 (advise는 72h 캐시라 재조회가 싸다).
        """

        def work() -> None:
            try:
                adv = self.mayhem.advise(champ_ko)
            except Exception as exc:
                _log.info("증강 오버레이 조회 실패(무시): %s", exc)
                return
            ft = adv.fixed_top
            lines = []
            for rarity, mark in (("prismatic", "프리즘"), ("gold", "골드"), ("silver", "실버")):
                picks = getattr(ft, rarity, ())[:3]
                if picks:
                    lines.append(f"{mark}: " + " · ".join(p.name_ko for p in picks))
            if not lines:
                return
            title = f"🎮 {champ_ko} 증강 TOP3 · {adv.patch}"
            self.after(
                0,
                lambda t=title, ln=lines: self._show_overlay_summary(t, ln, champ_ko, attempt),
            )

        self._spawn_thread(work)

    def _show_overlay_summary(
        self, title: str, lines: list[str], champ_ko: str, attempt: int
    ) -> None:
        try:
            self._overlay_active = True  # 게임 종료(_on_live_client_game_gone)까지 위젯 보호
            self._ensure_widget_open()
            self._push_summary(title, lines)
            if attempt == 0:
                self._notify("증강 추천 오버레이 표시 (Ctrl+Shift+W 토글)", level="ok", ms=2500)
        except Exception as exc:
            _log.info("오버레이 표시 실패(무시): %s", exc)
            return
        # 브리핑 요약이 오버레이를 덮었으면 재푸시 (게임 시작 후 1분 이내)
        if attempt < 3:
            self.after(20000, lambda: self._repush_overlay_if_covered(champ_ko, attempt + 1))

    def _repush_overlay_if_covered(self, champ_ko: str, attempt: int) -> None:
        try:
            from lol_coach.config import mayhem_overlay_enabled

            if not mayhem_overlay_enabled():
                return
            title = self._last_summary_title or ""
            if title.startswith("🎮"):
                return  # 아직 오버레이가 최신 — 건드리지 않음
            self._push_mayhem_overlay(champ_ko, attempt)
        except Exception as exc:
            _log.info("오버레이 재푸시 실패(무시): %s", exc)

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
        # 저장된 위젯 위치 복원 — 멀티모니터 인식
        try:
            from lol_coach.config import clamp_window_geometry, get_virtual_screen, load_ui_settings

            geo = str(load_ui_settings().get("widget_geometry") or "")
            if geo and "x" in geo:
                vx, vy, vw, vh = get_virtual_screen()
                self._widget.geometry(
                    clamp_window_geometry(
                        geo,
                        screen_width=self.winfo_screenwidth(),
                        screen_height=self.winfo_screenheight(),
                        vscreen_x=vx,
                        vscreen_y=vy,
                        vscreen_width=vw,
                        vscreen_height=vh,
                    )
                )
        except Exception:
            pass

        # 복원 완료 후 위치 저장 활성화 (Tk가 geometry 적용할 시간 여유)
        def _enable_geo_save() -> None:
            w = getattr(self, "_widget", None)
            if w is not None:
                try:
                    if w.winfo_exists():
                        w._geo_ready = True
                except Exception:
                    pass

        self.after(500, _enable_geo_save)
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
        if not hasattr(self, "llm_provider_var"):
            self.llm_provider_var = tk.StringVar(
                value=_llm.normalize_provider(self.settings.llm_provider)
            )
            self._llm_provider_prev = self.llm_provider_var.get()
        if not hasattr(self, "llm_model_var"):
            prov = _llm.get_provider(self.settings.llm_provider)
            cur = self.settings.llm_model or prov.default_model
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
        if not hasattr(self, "mayhem_overlay_var"):
            from lol_coach.config import mayhem_overlay_enabled

            self.mayhem_overlay_var = tk.BooleanVar(value=mayhem_overlay_enabled())
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

            # 자식을 먼저 파괴한 뒤 테마 변경 — set_appearance_mode가
            # 기존 위젯을 부분 업데이트하여 화면이 깨지는 것을 방지
            for child in list(self.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
            self._icon_refs = []
            self._sr_autocompletes = []
            self._role_btns = []
            self._me_match_btns: list[Any] = []
            self._toast_win = None
            self.ai_status_lbl = None

            apply_skin(name)
            path = resolve_theme_path(name)
            # 테마 JSON 먼저 로드 → 그 다음 appearance mode 전환.
            # 반대 순서면 루트 창 배경이 구 테마 색으로 고정되어 깨진다.
            ctk.set_default_color_theme(str(path))
            ctk.set_appearance_mode(appearance_mode_for(name))
            global _THEME
            _THEME = path
            # 루트 CTk 창의 _fg_color 를 새 테마로 갱신 — set_appearance_mode
            # 만으로는 루트 배경이 갱신되지 않는 CTk 버그 회피
            try:
                self.configure(fg_color=ctk.ThemeManager.theme["CTk"]["fg_color"])
            except Exception:
                pass

            self._build()
            # 보류된 geometry·색상 업데이트를 즉시 처리하여 깨짐 방지
            self.update_idletasks()
            self.update()
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
                    self._ensure_tab_built("내 전적")
                    self.me_tab._render_me(form, ranks=ranks)
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
        """마지막 분석 요약 저장 → 미니 위젯이 열여 있으면 갱신.

        게임 중 오버레이(🎮 증강 TOP3)가 표시 중이면 다른 요약이 위젯을
        덮어쓰지 않게 한다 (복사용 저장은 유지). LLM 반복 루프 등
        이상 출력은 sanitize 해서 위젯에 넣는다.
        """
        from lol_coach.gui.ai_text import sanitize_summary_lines

        safe = sanitize_summary_lines(lines)
        self._last_summary_title = title
        self._last_summary_lines = safe
        try:
            if (
                self.__dict__.get("_overlay_active", False)
                and not title.startswith("🎮")
            ):
                return  # 오버레이 보호 — 위젯 갱신 스킵
            if self._widget is not None and self._widget.winfo_exists():
                self._widget.set_summary(title, safe)
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
    # 업데이트 예약 — 앱이 exe 잠금을 내려놓은 뒤 인스톨러 실행 (설치 후 재실행됨)
    pending = getattr(app, "_pending_update_installer", "")
    if pending and Path(pending).is_file():
        import time as _time

        _time.sleep(1.5)
        try:
            from lol_coach.gui.updater import launch_silent_installer

            launch_silent_installer(pending)
        except Exception:
            pass  # 실행 실패 시 사용자가 인스톨러를 수동 실행할 수 있다


if __name__ == "__main__":
    run_app()
