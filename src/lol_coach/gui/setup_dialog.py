"""첫 실행 — Riot API 키 / Riot ID 설정 창 (친절한 step-by-step)."""

from __future__ import annotations

import re
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from lol_coach.config import (
    DEFAULT_PLATFORM,
    load_settings,
    save_api_key,
    save_player,
)
from lol_coach.gui import components as ui
from lol_coach.gui.api_help import RIOT_DEV_URL, open_api_key_help

_API_KEY_RE = re.compile(r"^RGAPI-[0-9a-fA-F-]{8,}$")

FT = ("Malgun Gothic", 16, "bold")
FU = ("Malgun Gothic", 13)
FM = ("Malgun Gothic", 11)
FS = ("Malgun Gothic", 12)

STEP_TEXT = """\
친구에게 앱을 처음 받았을 때 따라 하면 됩니다!

【1단계】 키 발급 사이트 열기
  · 아래 「사이트 열기」 버튼을 누르거나
  · 브라우저에 입력: https://developer.riotgames.com/

【2단계】 Riot 계정으로 로그인
  · 평소 롤 할 때 쓰는 계정으로 Sign In
  · 계정이 없으면 회원가입 후 로그인

【3단계】 Dashboard 로 이동
  · 로그인 후 오른쪽 위 프로필 / Dashboard
  · 개발자 포털 메인에서 키 관리 화면으로 들어갑니다

【4단계】 Personal / Development API Key 확인
  · 화면에 "Development API Key" 또는
    "Personal API Key" 라고 된 항목을 찾으세요
  · (앱 승인용 Production 키가 아닙니다)
  · 개인·친구끼리 쓰는 개발용 키를 고르면 됩니다

【5단계】 키 복사
  · 키가 보이면 복사 버튼 클릭
  · 없으면 [Regenerate API Key] 로 새로 만든 뒤 복사
  · 반드시 RGAPI- 로 시작하는 전체 문자열을 복사
    예) RGAPI-a1b2c3d4-e5f6-...

【6단계】 이 창에 붙여넣기
  · 「Riot API 키」 칸에 Ctrl+V
  · Riot ID: 게임 닉네임#태그  (예: 소환사명#KR1)
  · 서버: 한국 kr / 북미 na1 / 유럽 euw1 등

【7단계】 저장 후 시작
  · [저장 후 시작] 클릭
  · 키는 이 PC의 앱 폴더 .env 에만 저장됩니다

※ 개발용 키는 보통 24시간마다 만료됩니다.
  만료되면 같은 사이트에서 다시 복사해 오면 됩니다.
"""


class SetupDialog(ctk.CTkToplevel):
    """모달 설정. result=True 면 앱 계속."""

    def __init__(self, master: ctk.CTk | None = None, *, force: bool = False):
        super().__init__(master)
        self.title("롤 실전 코치 — 처음 실행 설정")
        self.geometry("580x700")
        self.minsize(520, 600)
        self.result = False
        self.force = force

        self.grab_set()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        settings = load_settings()
        self.api_var = tk.StringVar(value=settings.riot_api_key or "")
        self.riot_var = tk.StringVar(value=settings.riot_id)
        self.platform_var = tk.StringVar(value=settings.platform or DEFAULT_PLATFORM)

        # 헤더
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text="환영합니다! 👋", font=FT).pack(side="left")
        ctk.CTkButton(
            head,
            text="❓ 자세한 도움말",
            width=120,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=lambda: open_api_key_help(self),
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text="전적을 보려면 Riot API 키가 필요해요. 아래 순서대로 진행해 주세요.",
            font=FS,
            text_color=ui.TEXT_DIM,
            wraplength=520,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        # 스크롤 안내
        guide = ctk.CTkTextbox(self, height=260, font=FM, wrap="word")
        guide.pack(fill="x", padx=20, pady=(0, 10))
        guide.insert("1.0", STEP_TEXT)
        guide.configure(state="disabled")

        link_row = ctk.CTkFrame(self, fg_color="transparent")
        link_row.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(
            link_row,
            text="🌐 키 발급 사이트 열기 (developer.riotgames.com)",
            height=36,
            font=FU,
            command=lambda: webbrowser.open(RIOT_DEV_URL),
        ).pack(fill="x")

        # 입력
        form = ctk.CTkFrame(self, corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 8))

        key_lab = ctk.CTkFrame(form, fg_color="transparent")
        key_lab.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(key_lab, text="Riot API 키 *", font=FU).pack(side="left")
        ctk.CTkButton(
            key_lab,
            text="도움말",
            width=70,
            height=26,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=lambda: open_api_key_help(self),
        ).pack(side="left", padx=8)

        self.api_entry = ctk.CTkEntry(
            form,
            textvariable=self.api_var,
            show="•",
            height=36,
            font=FU,
            placeholder_text="RGAPI- 로 시작하는 키를 붙여넣으세요",
        )
        self.api_entry.pack(fill="x", padx=14, pady=(4, 8))
        self.api_entry.focus_set()

        ctk.CTkLabel(form, text="Riot ID (게임 닉네임#태그)", font=FU).pack(anchor="w", padx=14)
        ctk.CTkEntry(
            form,
            textvariable=self.riot_var,
            height=34,
            font=FU,
            placeholder_text="예: 소환사명#KR1",
        ).pack(fill="x", padx=14, pady=(4, 8))

        ctk.CTkLabel(form, text="서버 코드 (platform)", font=FU).pack(anchor="w", padx=14)
        ctk.CTkEntry(
            form,
            textvariable=self.platform_var,
            height=34,
            font=FU,
            placeholder_text="한국 kr  ·  북미 na1  ·  유럽 euw1",
        ).pack(fill="x", padx=14, pady=(4, 12))

        ctk.CTkLabel(
            self,
            text="※ 키는 이 PC에만 저장됩니다. 카톡·디스코드에 올리지 마세요.",
            font=FM,
            text_color=ui.TEXT_DIM,
        ).pack(anchor="w", padx=20, pady=(0, 6))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 18))
        ctk.CTkButton(
            btn_row,
            text="저장 후 시작",
            height=42,
            font=FU,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self._on_save,
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(
            btn_row,
            text="나중에 (전적만 제외)",
            height=42,
            font=FU,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._on_skip,
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.bind("<Return>", lambda _e: self._on_save())

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _on_skip(self) -> None:
        if messagebox.askyesno(
            "나중에 하기",
            "API 키 없이 앱을 열까요?\n\n"
            "· 카운터픽 / ARAM 아수라장 → 사용 가능\n"
            "· 내 전적 / 경기 복기 → 키 등록 후 가능\n\n"
            "언제든지 [내 전적] 탭에서 키를 넣을 수 있어요.",
            parent=self,
        ):
            self.result = True
            self.destroy()

    def _on_save(self) -> None:
        key = self.api_var.get().strip().strip("\"'")
        if not key:
            messagebox.showwarning(
                "API 키가 비어 있어요",
                "키 발급 사이트에서 RGAPI-… 키를 복사해\n"
                "위 칸에 붙여넣어 주세요.\n\n"
                "「도움말」 또는 「사이트 열기」를 눌러 보세요!",
                parent=self,
            )
            return
        if not _API_KEY_RE.match(key) and not messagebox.askyesno(
            "키 형식 확인",
            "보통 키는 RGAPI- 로 시작해요.\n지금 형식이 조금 달라 보입니다.\n\n그래도 저장할까요?",
            parent=self,
        ):
            return
        rid = self.riot_var.get().strip()
        if "#" not in rid:
            messagebox.showwarning(
                "Riot ID 형식",
                "게임에서 보이는 것처럼\n닉네임#태그 로 입력해 주세요.\n예: 소환사명#KR1",
                parent=self,
            )
            return
        name, tag = rid.split("#", 1)
        platform = (self.platform_var.get() or DEFAULT_PLATFORM).strip().lower()
        try:
            save_api_key(key)
            save_player(name.strip(), tag.strip(), platform=platform)
        except Exception as exc:
            messagebox.showerror("저장 실패", str(exc), parent=self)
            return
        messagebox.showinfo(
            "저장 완료",
            "설정이 저장되었습니다!\n이제 「내 전적」에서 전적을 불러올 수 있어요.",
            parent=self,
        )
        self.result = True
        self.destroy()


def ensure_api_key_dialog(force: bool = False) -> bool:
    """키가 없거나 force면 설정 창. 반환: 앱 계속 여부."""
    settings = load_settings()
    if settings.riot_api_key and not force:
        return True

    root = ctk.CTk()
    root.withdraw()
    dlg = SetupDialog(root, force=force)
    root.wait_window(dlg)
    ok = bool(dlg.result)
    root.destroy()
    return ok
