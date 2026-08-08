"""인게임/종료 감지 공통

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

from tkinter import messagebox
from typing import Any

from lol_coach.config import DEFAULT_PLATFORM, load_settings, save_api_key, save_player
from lol_coach.riot.client import RiotClient


class LiveMixin:
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
            self._notify(
                "Riot ID(Name#TAG)를 「내 전적」탭에 설정해 주세요.",
                level="warn",
            )
            return None
        name, tag = rid.split("#", 1)

        platform = settings.platform or DEFAULT_PLATFORM
        if hasattr(self, "platform_var"):
            platform = self.platform_var.get().strip() or platform

        save_api_key(key)
        save_player(name.strip(), tag.strip(), platform=platform)
        self.settings = load_settings()

        client = RiotClient(api_key=key, platform=platform)
        return client, name.strip(), tag.strip()


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
        if self._game_end_auto_review_on():
            self.status.configure(text="🔔 게임 종료 감지 중 — 끝나면 자동 복기")
        else:
            self.status.configure(text="🔔 게임 종료 감지 중 — 자동 복기 끔")


    def _on_game_ended(self, match: Any) -> None:
        if match is None:
            self.status.configure(text="게임 종료 감지됨 — 매치 조회 실패")
            return
        champ = self.loc.champion(match.champion_name) or match.champion_name
        mark = "승리" if match.win else "패배"
        auto_review = self._game_end_auto_review_on()
        if auto_review:
            self.status.configure(text=f"🔔 방금 게임({champ} {mark}) 복기 도착")
        else:
            self.status.configure(
                text=f"🔔 방금 게임({champ} {mark}) 종료 · 자동 복기 끔"
            )
        self._notify_game_end(champ, match.win)
        if not auto_review:
            return
        try:
            self._show_match_detail(match)
        except Exception:
            pass


    def _game_end_notify_on(self) -> bool:
        """내 전적 탭 체크박스 또는 ui.json 설정. 기본 ON."""
        var = getattr(self, "game_end_notify_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            from lol_coach.config import game_end_notify_enabled

            return game_end_notify_enabled()
        except Exception:
            return True

    def _game_end_auto_review_on(self) -> bool:
        """종료 시 복기 패널 자동 열기. 기본 ON."""
        var = getattr(self, "game_end_auto_review_var", None)
        if var is not None:
            try:
                return bool(var.get())
            except Exception:
                pass
        try:
            from lol_coach.config import game_end_auto_review_enabled

            return game_end_auto_review_enabled()
        except Exception:
            return True

    def _notify_game_end(self, champ: str, win: bool) -> None:
        """게임 종료 알림 — 사운드 + 작업 표시줄 플래시 (비모달).

        설정에서 끈 경우 상태바만 남고 소리/플래시는 생략.
        """
        if not self._game_end_notify_on():
            return
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

