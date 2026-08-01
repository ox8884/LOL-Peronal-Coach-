"""Riot API 키 발급 도움말 (공통)."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

RIOT_DEV_URL = "https://developer.riotgames.com/"

HELP_TITLE = "Riot API 키란? · 발급 방법"

HELP_BODY = """\
안녕하세요! 처음이어도 따라만 하면 됩니다 🙂

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
왜 API 키가 필요한가요?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이 앱이 여러분의 롤 전적·승률·매치 상세를 불러오려면
Riot Games 공식 서버에 "조회 허가증"이 필요합니다.

그 허가증이 바로 API 키예요.
· 전적 / 챔피언 성적 / 경기 복기 → 키 필요
· 카운터픽 · ARAM 증강(u.gg) → 키 없이도 사용 가능

키는 본인 PC의 .env 파일에 저장되고 Riot 공식 API 요청에만 사용됩니다.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━
키 받는 방법 (처음부터 끝까지)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① 아래 주소로 이동하세요
   https://developer.riotgames.com/

② 오른쪽 위 [Sign In] 또는 [Login]
   · 평소 쓰는 Riot 계정으로 로그인
   · 없다면 회원가입 후 로그인

③ 로그인 후 상단 메뉴에서
   [Dashboard] 또는 프로필 아이콘 → Dashboard

④ 페이지에 보이는 키 종류 안내
   · Development API Key  /  Personal API Key
   · 둘 다 개인 연습·친구 공유용으로 쓰는 개발용 키입니다
   · 앱 등록(제품 승인) 없이 바로 쓸 수 있는 키를 고르세요
   · 화면에 "Personal API Key" 또는 "Development API Key" 가
     보이면 그것을 사용하면 됩니다
   · (Production / App Registration 키는 나중에 회사·서비스용)

⑤ [Regenerate] 또는 키가 이미 있으면 복사 아이콘 클릭
   · 키 형태 예시:
     RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   · RGAPI- 로 시작하는 긴 문자열 전체를 복사하세요

⑥ 이 앱 입력칸에 붙여넣기 (Ctrl+V)
   · Riot ID 예: 소환사명#KR1
   · 서버(platform) 예:
       한국 → kr
       북미 → na1
       유럽 서부 → euw1

⑦ [저장 후 시작] 또는 [전적 로드] 클릭


━━━━━━━━━━━━━━━━━━━━━━━━━━━━
자주 하는 실수
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· 키 일부만 복사함 → 반드시 RGAPI- 부터 끝까지
· 24시간이 지나 만료됨 → 같은 페이지에서 다시 발급(Regenerate)
· 서버를 잘못 넣음 → 한국 계정인데 na1 이면 전적이 안 나옴
· 키를 카톡/디스코드에 올리지 마세요 (도용 위험)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━
키 만료되면?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
개발용 키는 보통 24시간마다 만료됩니다.
다시 developer.riotgames.com → Dashboard → 새 키 복사 →
앱의 [내 전적] 탭에서 API 키를 바꿔 저장하면 됩니다.


문제가 있으면 위 사이트가 정상인지,
로그인이 되어 있는지 먼저 확인해 주세요.
"""


def open_api_key_help(parent=None) -> None:
    """도움말 창을 띄웁니다."""
    win = ctk.CTkToplevel(parent)
    win.title(HELP_TITLE)
    win.geometry("560x640")
    win.minsize(480, 480)

    if parent is not None:
        try:
            win.transient(parent)
            win.grab_set()
        except Exception:
            pass

    head = ctk.CTkFrame(win, fg_color="transparent")
    head.pack(fill="x", padx=16, pady=(14, 6))
    ctk.CTkLabel(
        head,
        text="🔑 Riot API 키 안내",
        font=("Malgun Gothic", 16, "bold"),
    ).pack(side="left")

    ctk.CTkButton(
        head,
        text="브라우저에서 키 발급 사이트 열기",
        width=200,
        height=32,
        font=("Malgun Gothic", 12),
        command=lambda: webbrowser.open(RIOT_DEV_URL),
    ).pack(side="right")

    box = ctk.CTkTextbox(win, font=("Malgun Gothic", 12), wrap="word")
    box.pack(fill="both", expand=True, padx=16, pady=(4, 8))
    box.insert("1.0", HELP_BODY)
    box.configure(state="disabled")

    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(fill="x", padx=16, pady=(0, 14))
    ctk.CTkLabel(
        foot,
        text=RIOT_DEV_URL,
        font=("Malgun Gothic", 11),
        text_color=("#1F6AA5", "#5BA3D9"),
    ).pack(side="left")
    ctk.CTkButton(
        foot, text="닫기", width=90, height=32, command=win.destroy
    ).pack(side="right")
