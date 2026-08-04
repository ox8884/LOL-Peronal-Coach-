"""롤 실전 코치 GUI — 디자인 토큰 & 공통 컴포넌트.

`theme.json`(CTk 커스텀 컬러 테마)과 함께 쓰는 토큰 상수와
카드·섹션 헤더·등급 칩 등 작은 조립 헬퍼.
기능 변경 없이 스킨만 담당한다. 팔레트는 docs/concepts/README.md 와 동일.
"""

from __future__ import annotations

from typing import Any

# ── 색상 토큰 (theme.json과 동일한 팔레트) ──────────────────────────
BG = "#0A0E14"
PANEL = "#121A24"
CARD = "#16202C"
ROW = "#18232F"
ROW_HOVER = "#1F2C3B"
BORDER = "#1E2A3A"
INPUT_BG = "#0D1520"
INPUT_BORDER = "#23303F"

GOLD = "#C8AA6E"
GOLD_HOVER = "#DCC08A"
GOLD_SOFT = "#E8DCC8"
ON_GOLD = "#0A0E14"

BLUE = "#4DA3FF"
BLUE_SOFT = "#8FBEFF"
GREEN = "#31C48D"
GREEN_HOVER = "#27A678"
RED = "#F05252"
RED_HOVER = "#D64545"
RED_SOFT = "#FF8A8A"
PURPLE = "#A78BFA"
PURPLE_HOVER = "#8B6FE8"
WARN = "#FFB74D"

TIER_S = "#FFD700"
TIER_A = "#4DA3FF"
TIER_B = "#31C48D"
TIER_C = "#F05252"

TEXT = "#C9D4E0"
TEXT_BRIGHT = "#E8ECF2"
TEXT_DIM = "#7B8BA0"
TEXT_MUTE = "#5A6B80"

# ── 버튼 변형 (fg, hover, text) ─────────────────────────────────────
BTN_PRIMARY = (GOLD, GOLD_HOVER, ON_GOLD)
BTN_SECONDARY = (PANEL, ROW_HOVER, GOLD_SOFT)
BTN_TERTIARY = (INPUT_BG, ROW_HOVER, TEXT_DIM)
BTN_SUCCESS = (GREEN, GREEN_HOVER, ON_GOLD)
BTN_PURPLE = (PURPLE, PURPLE_HOVER, ON_GOLD)
BTN_DANGER = (RED, RED_HOVER, "#FFFFFF")


def btn(fg: str, hover: str, text: str) -> dict[str, str]:
    """버튼 configure kwargs — fg/hover/텍스트 색 한 벌."""
    return {"fg_color": fg, "hover_color": hover, "text_color": text}


def tier(t: str) -> tuple[str, str]:
    """등급(S/A/B/C) → (칩 배경색, 칩 텍스트색)."""
    return {
        "S": (TIER_S, ON_GOLD),
        "A": (TIER_A, ON_GOLD),
        "B": (TIER_B, ON_GOLD),
        "C": (TIER_C, "#FFFFFF"),
    }.get(t.upper(), (TEXT_DIM, "#FFFFFF"))


def tier_chip(parent: Any, t: str, *, font: Any = None, width: int = 26) -> Any:
    """등급 배지 라벨 (pack으로 배치)."""
    bg, fg = tier(t)
    return ctk_label(parent, t, font=font, fg_color=bg, text_color=fg, width=width)


def ctk_label(
    parent: Any,
    text: str,
    *,
    font: Any = None,
    fg_color: str | None = None,
    text_color: str | None = None,
    width: int | None = None,
    corner_radius: int = 6,
    **kw: Any,
) -> Any:
    """CTkLabel — 칩처럼 쓰기 좋게 fg/radius 기본값 제공."""
    import customtkinter as ctk

    return ctk.CTkLabel(
        parent,
        text=text,
        font=font,
        fg_color=fg_color if fg_color is not None else "transparent",
        text_color=text_color if text_color is not None else TEXT,
        corner_radius=corner_radius,
        width=width,
        **kw,
    )
