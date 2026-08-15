#!/usr/bin/env python3
"""네온 아레나 스킨 프로토타입 — ARAM 탭 단독 렌더 (실제 CustomTkinter 픽셀).

실행:
    cd ~/lol-coach
    uv run python docs/redesign/prototype_neon_arena.py          # 창 띄워서 보기
    uv run python docs/redesign/prototype_neon_arena.py --smoke  # 1.5초 후 자동 종료 (검증)

앱 본체를 전혀 건드리지 않는 독립 파일. 네온 아레나 팔레트 + 구운 그라데이션 자산 1장으로
방향 A를 실제 CTk 렌더링으로 검증한다. 승인 시 이 토큰을 components.py 신규 스킨으로 이식.

CTk 제약 메모: 글로우/블러는 불가 → 액센트 보더(1~2px) + 라운드 카드(16px)로 근사.
그라데이션은 구운 PNG 1장을 루트 배경으로만 사용 (카드 사이/가장자리에 노출).
"""
from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk
from PIL import Image

# ── 네온 아레나 팔레트 (components.py 토큰 체계 준수) ──────────────────────────
BG           = "#060912"
PANEL        = "#0B1020"
CARD         = "#0F1628"
CARD_HI      = "#141E36"
ROW          = "#131C33"
BORDER       = "#1E2A45"
BORDER_HI    = "#2A3A5C"
INPUT_BG     = "#080D1A"
INPUT_BORDER = "#2A3A5C"
ACCENT       = "#8B5CF6"   # violet — 주 액센트
ACCENT_HOVER = "#A78BFA"
ACCENT_SOFT  = "#C4B5FD"
ON_ACCENT    = "#0B1020"
CYAN         = "#22D3EE"   # 시안 — 보조 액센트
CYAN_SOFT    = "#67E8F9"
GOLD_TIER    = "#FDE047"
GREEN        = "#34D399"
RED          = "#F87171"
TEXT         = "#C9D4E0"
TEXT_BRIGHT  = "#F0F6FF"
TEXT_DIM     = "#7A8AAA"
TEXT_MUTE    = "#4A5570"

FAMILY = "Malgun Gothic"
ROOT_DIR = Path(__file__).resolve().parent
BG_IMAGE = ROOT_DIR / "assets" / "neon_arena_bg.png"

WIN_W, WIN_H = 1120, 920
SIDE = 18
GAP = 12
TOP = 14
CONTENT_W = WIN_W - SIDE * 2  # 1084


def F(size: int, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY, size=size, weight="bold" if bold else "normal")


# ── 목 데이터 ────────────────────────────────────────────────────────────────
RARITY = [
    ("실버", TEXT_DIM, [
        ("신속한 발걸음", "이동속도 +8%"),
        ("생명력 증강", "최대 체력 +150"),
        ("정밀 사격", "스킬 가속 +10"),
    ]),
    ("골드", ACCENT, [
        ("처형인의 대검", "처치 시 체력 회복"),
        ("마나순환 팔찌", "마나 재생 +50%"),
        ("굳건한 방패", "받는 피해 -8%"),
    ]),
    ("프리즘", CYAN, [
        ("무한한 삼위일체", "공격력·주문력·가속"),
        ("시간 왜곡 물약", "포션 효과 +30%"),
        ("통찰력 우위", "스킬 가속 +25"),
    ]),
]
BUILD = ["채찍", "만년 서리", "리안드리", "정령의 형상", "란두인", "밴시"]
AI_TIPS = [
    "초반 교전은 포킹 스킬 위주로 안전하게 이득을 쌓으세요.",
    "궁극기는 아군 CC 연계 후 진입하는 타이밍에 사용하세요.",
    "적 조합에 돌진기가 많아 둔화/속박 증강을 우선하세요.",
]


def _sec(parent: ctk.CTkBaseClass, title: str, accent: str = ACCENT) -> ctk.CTkFrame:
    """3px 액센트 바 + 섹션 제목 (실제 app._sec 충실 재현). 반환: 헤더 프레임."""
    f = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=22)
    f.pack_propagate(False)
    bar = ctk.CTkFrame(f, fg_color=accent, corner_radius=0, width=3)
    bar.pack(side="left", padx=(0, 8), pady=2, fill="y")
    ctk.CTkLabel(f, text=title, font=F(15, True), text_color=TEXT_BRIGHT).pack(
        side="left", padx=2
    )
    return f


def _ghost_btn(parent: ctk.CTkBaseClass, text: str) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, font=F(12), width=64, height=28,
        fg_color="transparent", hover_color=ROW, border_width=1,
        border_color=BORDER_HI, text_color=TEXT_DIM, corner_radius=10,
    )


def _augment_slot(parent: ctk.CTkBaseClass, name: str, effect: str, tint: str) -> ctk.CTkFrame:
    row = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=46)
    row.pack_propagate(False)
    icon = ctk.CTkFrame(row, fg_color=ROW, border_width=1, border_color=BORDER_HI,
                        corner_radius=8, width=34, height=34)
    icon.pack_propagate(False)
    icon.pack(side="left", padx=(0, 10))
    ctk.CTkLabel(icon, text=name[0], font=F(14, True), text_color=tint).pack(expand=True)
    txt = ctk.CTkFrame(row, fg_color="transparent", corner_radius=0)
    txt.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(txt, text=name, font=F(13, True), text_color=TEXT_BRIGHT,
                 anchor="w").pack(fill="x")
    ctk.CTkLabel(txt, text=effect, font=F(11), text_color=TEXT_DIM,
                 anchor="w").pack(fill="x")
    return row


def build_header(root: ctk.CTk) -> None:
    h = ctk.CTkFrame(root, fg_color="transparent", corner_radius=0,
                     width=CONTENT_W, height=46)
    h.pack_propagate(False)
    h.place(x=SIDE, y=TOP)
    logo = ctk.CTkFrame(h, fg_color=ACCENT, corner_radius=14, width=28, height=28)
    logo.pack_propagate(False)
    logo.pack(side="left", padx=(2, 12))
    ctk.CTkLabel(logo, text="◆", font=F(14, True), text_color=ON_ACCENT).pack(expand=True)
    ctk.CTkLabel(h, text="롤 실전 코치", font=F(20, True), text_color=TEXT_BRIGHT).pack(
        side="left", padx=2
    )
    right = ctk.CTkFrame(h, fg_color="transparent", corner_radius=0)
    right.pack(side="right")
    badge = ctk.CTkFrame(right, fg_color="#1A1230", border_width=1, border_color=ACCENT,
                         corner_radius=12, height=26)
    badge.pack_propagate(False)
    badge.pack(side="left", padx=(0, 8))
    ctk.CTkLabel(badge, text="  네온 아레나  ", font=F(11, True), text_color=ACCENT_SOFT).pack(
        side="left", padx=6
    )
    _ghost_btn(right, "통계").pack(side="left", padx=2)
    _ghost_btn(right, "설정").pack(side="left", padx=2)


def build_tabs(root: ctk.CTk) -> None:
    bar = ctk.CTkFrame(root, fg_color="transparent", corner_radius=0,
                        width=CONTENT_W, height=40)
    bar.pack_propagate(False)
    bar.place(x=SIDE, y=TOP + 46 + GAP)
    for label, active in (("소환사의 협곡", False), ("ARAM 아수라장", True), ("내 전적", False)):
        if active:
            ctk.CTkButton(
                bar, text=label, font=F(13, True), height=36,
                fg_color=CARD_HI, hover_color=CARD_HI, border_width=2,
                border_color=ACCENT, text_color=TEXT_BRIGHT, corner_radius=12,
            ).pack(side="left", padx=(0, 8))
        else:
            ctk.CTkButton(
                bar, text=label, font=F(13), height=36,
                fg_color="transparent", hover_color=ROW, border_width=0,
                text_color=TEXT_DIM, corner_radius=12,
            ).pack(side="left", padx=(0, 8))


def build_input_hint(root: ctk.CTk) -> None:
    y = TOP + 46 + GAP + 40 + GAP
    box = ctk.CTkFrame(root, fg_color=PANEL, border_width=1, border_color=BORDER,
                       corner_radius=12, width=CONTENT_W, height=38)
    box.pack_propagate(False)
    box.place(x=SIDE, y=y)
    ctk.CTkLabel(box, text="▪  챔피언명 입력 또는 LCU 자동 분석  ·  지금은 스킨 미리보기",
                 font=F(12), text_color=TEXT_DIM).pack(side="left", padx=14)
    pill = ctk.CTkFrame(box, fg_color="#0E2A33", border_width=1, border_color=CYAN,
                        corner_radius=10, height=22)
    pill.pack_propagate(False)
    pill.pack(side="right", padx=12)
    ctk.CTkLabel(pill, text=" 자동 ", font=F(10, True), text_color=CYAN_SOFT).pack(
        side="left", padx=6
    )


def build_rarity(root: ctk.CTk) -> None:
    y = TOP + 46 + GAP + 40 + GAP + 38 + GAP
    card_w = (CONTENT_W - 2 * GAP) // 3  # 353
    h = 318
    for i, (title, tint, slots) in enumerate(RARITY):
        x = SIDE + i * (card_w + GAP)
        card = ctk.CTkFrame(root, fg_color=CARD, border_width=1, border_color=tint,
                            corner_radius=16, width=card_w, height=h)
        card.place(x=x, y=y)
        card.grid_propagate(False)
        card.pack_propagate(False)
        inner = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        inner.pack(fill="both", expand=True, padx=14, pady=14)
        _sec(inner, title, accent=tint).pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(inner, text=f"메타 TOP {len(slots)}", font=F(10),
                     text_color=TEXT_MUTE, anchor="w").pack(fill="x", pady=(0, 6))
        for name, effect in slots:
            _augment_slot(inner, name, effect, tint).pack(fill="x", pady=4)


def build_ai(root: ctk.CTk) -> None:
    y = TOP + 46 + GAP + 40 + GAP + 38 + GAP + 318 + GAP
    h = 182
    panel = ctk.CTkFrame(root, fg_color=CARD, border_width=2, border_color=ACCENT,
                         corner_radius=16, width=CONTENT_W, height=h)
    panel.place(x=SIDE, y=y)
    panel.pack_propagate(False)
    inner = ctk.CTkFrame(panel, fg_color="transparent", corner_radius=0)
    inner.pack(fill="both", expand=True, padx=16, pady=14)
    head = ctk.CTkFrame(inner, fg_color="transparent", corner_radius=0)
    head.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(head, text="◈", font=F(14, True), text_color=ACCENT_SOFT).pack(side="left",
                                                                                padx=(0, 8))
    ctk.CTkLabel(head, text="AI 코칭", font=F(15, True), text_color=TEXT_BRIGHT).pack(
        side="left"
    )
    ctk.CTkLabel(head, text="아수라장 특화", font=F(10), text_color=TEXT_MUTE).pack(
        side="left", padx=10
    )
    for tip in AI_TIPS:
        ctk.CTkLabel(inner, text=f"·  {tip}", font=F(12), text_color=TEXT,
                     anchor="w", justify="left").pack(fill="x", pady=2)


def build_build(root: ctk.CTk) -> None:
    y = TOP + 46 + GAP + 40 + GAP + 38 + GAP + 318 + GAP + 182 + GAP
    h = 176
    panel = ctk.CTkFrame(root, fg_color=CARD, border_width=1, border_color=BORDER_HI,
                         corner_radius=16, width=CONTENT_W, height=h)
    panel.place(x=SIDE, y=y)
    panel.pack_propagate(False)
    inner = ctk.CTkFrame(panel, fg_color="transparent", corner_radius=0)
    inner.pack(fill="both", expand=True, padx=14, pady=14)
    _sec(inner, "추천 아이템 빌드", accent=CYAN).pack(fill="x", pady=(0, 8))
    grid = ctk.CTkFrame(inner, fg_color="transparent", corner_radius=0)
    grid.pack(fill="both", expand=True)
    for c in range(3):
        grid.grid_columnconfigure(c, weight=1, uniform="slot")
    for idx, name in enumerate(BUILD):
        r, c = divmod(idx, 3)
        slot = ctk.CTkFrame(grid, fg_color=ROW, border_width=1, border_color=BORDER_HI,
                            corner_radius=10)
        slot.grid(row=r, column=c, sticky="nsew", padx=6, pady=4)
        ctk.CTkLabel(slot, text=f"{idx + 1}", font=F(11, True), text_color=CYAN_SOFT).pack(
            side="left", padx=8
        )
        ctk.CTkLabel(slot, text=name, font=F(12), text_color=TEXT_BRIGHT, anchor="w").pack(
            side="left", fill="x", expand=True
        )


def build_status(root: ctk.CTk) -> None:
    y = TOP + 46 + GAP + 40 + GAP + 38 + GAP + 318 + GAP + 182 + GAP + 176 + GAP
    h = 20
    bar = ctk.CTkFrame(root, fg_color=PANEL, border_width=1, border_color=BORDER,
                       corner_radius=10, width=CONTENT_W, height=h)
    bar.pack_propagate(False)
    bar.place(x=SIDE, y=y)
    ctk.CTkLabel(bar, text="준비됨  ·  ARAM 아수라장  ·  스킨: 네온 아레나 (프로토타입)",
                 font=F(10), text_color=TEXT_MUTE).pack(side="left", padx=12)
    ctk.CTkLabel(bar, text="계정: —", font=F(10), text_color=TEXT_MUTE).pack(
        side="right", padx=12
    )


def main() -> int:
    smoke = "--smoke" in sys.argv
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    root = ctk.CTk()
    root.title("롤 실전 코치 — 네온 아레나 (프로토타입)")
    root.configure(fg_color=BG)
    root.geometry(f"{WIN_W}x{WIN_H}")
    root.minsize(WIN_W, WIN_H)
    root.resizable(False, False)
    root.attributes("-topmost", True)  # 미리보기 — 항상 위

    # 구운 그라데이션 배경 — 카드 사이/가장자리에 노출되는 유일한 그라데이션
    if BG_IMAGE.is_file():
        img = ctk.CTkImage(light_image=Image.open(BG_IMAGE), size=(WIN_W, WIN_H))
        bg = ctk.CTkLabel(root, text="", image=img, fg_color="transparent")
        bg.place(x=0, y=0)
        bg.lower()  # 모든 섹션 아래로

    build_header(root)
    build_tabs(root)
    build_input_hint(root)
    build_rarity(root)
    build_ai(root)
    build_build(root)
    build_status(root)

    if smoke:
        root.after(1500, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
