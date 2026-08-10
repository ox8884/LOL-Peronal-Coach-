"""자동 업데이트 UI 핸들러

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from tkinter import messagebox

from lol_coach import __version__
from lol_coach.gui import components as ui
from lol_coach.gui.types import MixinBase


class UpdateMixin(MixinBase):
    def _version_tuple(self, v: str) -> tuple[int, ...]:
        from lol_coach.gui.updater import version_tuple

        return version_tuple(v)


    def _check_update(self) -> None:
        """GitHub 최신 릴리스 확인 — 새 버전이 있으면 업데이트 버튼 활성화."""
        # 워커 스레드에서 호출됨 — 메인루프 시작 전 레이스를 피하기 위해
        # 실제 앱의 _boot_after 를 우선 사용 (테스트 스텁은 after 로 폴백)
        schedule = getattr(self, "_boot_after", None) or self.after
        try:
            from lol_coach.gui.updater import fetch_expected_sha256, fetch_latest_tag

            latest = fetch_latest_tag()
            if not latest:
                return
            cur = __version__.lstrip("v")
            if self._version_tuple(latest) > self._version_tuple(cur):
                self._latest_version = latest
                self._latest_sha256 = fetch_expected_sha256(latest)

                def _show() -> None:
                    self.update_btn.configure(
                        state="normal",
                        text=f"🔄 v{latest} 업데이트",
                        **ui.btn(*ui.BTN_SUCCESS),
                    )
                    self.status.configure(
                        text=f"⬆ 새 버전 v{latest} 사용 가능 — 버튼으로 자동 업데이트"
                    )

                schedule(0, _show)
        except Exception:
            # 오프라인/API 실패 — 상태바에 한 번만 힌트
            schedule(
                0,
                lambda: self.status.configure(
                    text=self.status.cget("text") or "업데이트 확인 실패 (오프라인일 수 있음)"
                ),
            )


    def _start_update(self) -> None:
        """업데이트 버튼 — 인스톨러 다운로드·검증 후 자동 설치."""
        latest = getattr(self, "_latest_version", "")
        if not latest:
            self._notify("이미 최신 버전입니다.", level="ok")
            return
        has_hash = bool(getattr(self, "_latest_sha256", ""))
        extra = (
            "· SHA256 무결성 검증 후 설치합니다\n"
            if has_hash
            else "· ⚠ 이 릴리스에 SHA256 파일이 없어 크기만 확인합니다\n"
        )
        if not messagebox.askyesno(
            "자동 업데이트",
            f"v{latest} 인스톨러를 다운로드해서 자동 설치할까요?\n\n"
            f"{extra}"
            "· 다운로드 후 설치 프로그램이 실행됩니다 (관리자 확인 필요)\n"
            "· 설치가 끝나면 새 버전으로 자동 실행됩니다\n"
            "· 설정(.env)·캐시·프로필은 그대로 유지됩니다",
        ):
            return
        self.update_btn.configure(state="disabled", text="⬇ 다운로드 중…")
        threading.Thread(target=self._download_update, daemon=True).start()


    def _download_update(self) -> None:
        """백그라운드로 인스톨러 다운로드 → SHA256 검증 → 설치 실행."""
        latest = getattr(self, "_latest_version", "")
        try:
            from lol_coach.config import cache_root
            from lol_coach.gui import updater as upd

            if not upd.is_valid_version(latest):
                raise ValueError(f"잘못된 릴리스 버전: {latest!r}")

            dest_dir = cache_root() / "updates"
            dest = dest_dir / f"LOL-Coach-Setup-v{latest}.exe"
            expected = getattr(self, "_latest_sha256", "") or upd.fetch_expected_sha256(
                latest
            )
            self._latest_sha256 = expected

            def on_pct(p: int) -> None:
                self.after(
                    0,
                    lambda pct=p: (
                        self.update_btn.configure(text=f"⬇ 다운로드 {pct}%"),
                        self.status.configure(text=f"⬇ v{latest} 다운로드 {pct}%"),
                    ),
                )

            need_dl = True
            if dest.exists() and dest.stat().st_size > 5_000_000:
                if expected:
                    try:
                        upd.verify_installer(dest, expected)
                        need_dl = False
                    except ValueError:
                        dest.unlink(missing_ok=True)
                else:
                    need_dl = False
            if need_dl:
                self.after(
                    0, lambda: self.status.configure(text=f"⬇ v{latest} 다운로드 중…")
                )
                upd.download_installer(latest, dest, progress=on_pct)
            if expected:
                self.after(0, lambda: self.status.configure(text="🔒 SHA256 검증 중…"))
                upd.verify_installer(dest, expected)
                self.after(0, lambda: self._launch_installer(str(dest), latest))
                return

            # 해시 없음 — 메인 스레드에서 확인 후 설치
            def _ask_and_launch(path: str = str(dest), ver: str = latest) -> None:
                if messagebox.askyesno(
                    "업데이트 검증",
                    "릴리스에 SHA256 파일이 없어 무결성을 확인하지 못했습니다.\n"
                    "그래도 설치를 진행할까요?\n\n"
                    f"{path}",
                ):
                    self._launch_installer(path, ver)
                else:
                    self._update_failed("사용자가 설치를 취소했습니다.")

            self.after(0, _ask_and_launch)
        except Exception as exc:
            self.after(
                0,
                lambda e=exc: self._update_failed(
                    f"업데이트 실패: {e}\n\n"
                    "네트워크를 확인하거나 Releases 페이지에서 직접 받아 주세요.\n"
                    "https://github.com/ox8884/LOL-Peronal-Coach-/releases/latest"
                ),
            )


    def _update_failed(self, msg: str) -> None:
        self.update_btn.configure(
            state="normal",
            text=f"🔄 v{getattr(self, '_latest_version', '')} 업데이트",
        )
        self.status.configure(text="업데이트 실패")
        messagebox.showerror("업데이트", msg)


    def _launch_installer(self, installer_path: str, latest: str) -> None:
        """인스톨러 무음 실행 후 앱 종료 (설치 완료 시 새 버전으로 재실행)."""
        try:
            from lol_coach.gui.updater import launch_silent_installer

            launch_silent_installer(installer_path)
            self.status.configure(
                text=f"설치 프로그램 실행됨 — 설치 후 v{latest}로 재실행됩니다"
            )
        except Exception as exc:
            self._update_failed(
                f"설치 프로그램 실행 실패: {exc}\n\n{installer_path}"
            )
            return
        self.after(800, self.destroy)

