"""롤 실전 코치 GUI — 디자인 토큰 & 공통 컴포넌트.

`theme.json` / `theme_neon.json` 과 맞춘 팔레트.
스킨: classic (골드·현행) | neon (레퍼런스 네온 글래스).
기능 변경 없이 스킨만 담당한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ── 스킨 정의 ───────────────────────────────────────────────────────
SKIN_CLASSIC = "classic"
SKIN_NEON = "neon"
SKINS = (SKIN_CLASSIC, SKIN_NEON)
DEFAULT_SKIN = SKIN_CLASSIC

SKIN_LABELS = {
    SKIN_CLASSIC: "클래식 (골드) — 지금 쓰던 스타일",
    SKIN_NEON: "네온 글래스 — 레퍼런스 스타일 실험",
}

_GUI_DIR = Path(__file__).resolve().parent

# classic = 현재 배포 팔레트 (되돌리기용 원본)
_PALETTE_CLASSIC: dict[str, Any] = {
    "BG": "#0A0E14",
    "PANEL": "#121A24",
    "CARD": "#16202C",
    "ROW": "#18232F",
    "ROW_HOVER": "#1F2C3B",
    "BORDER": "#1E2A3A",
    "INPUT_BG": "#0D1520",
    "INPUT_BORDER": "#23303F",
    "GOLD": "#C8AA6E",
    "GOLD_HOVER": "#DCC08A",
    "GOLD_SOFT": "#E8DCC8",
    "ON_GOLD": "#0A0E14",
    "BLUE": "#4DA3FF",
    "BLUE_SOFT": "#8FBEFF",
    "GREEN": "#31C48D",
    "GREEN_HOVER": "#27A678",
    "RED": "#F05252",
    "RED_HOVER": "#D64545",
    "RED_SOFT": "#FF8A8A",
    "PURPLE": "#A78BFA",
    "PURPLE_HOVER": "#8B6FE8",
    "WARN": "#FFB74D",
    "TIER_S": "#FFD700",
    "TIER_A": "#4DA3FF",
    "TIER_B": "#31C48D",
    "TIER_C": "#F05252",
    "TEXT": "#C9D4E0",
    "TEXT_BRIGHT": "#E8ECF2",
    "TEXT_DIM": "#7B8BA0",
    "TEXT_MUTE": "#5A6B80",
}

# neon = 레퍼런스 톤을 과장 (차이를 분명히) — GOLD* 는 시안 액센트 별칭
_PALETTE_NEON: dict[str, Any] = {
    "BG": "#02040a",
    "PANEL": "#070e1c",
    "CARD": "#0a1228",
    "ROW": "#0e1830",
    "ROW_HOVER": "#162848",
    "BORDER": "#00b4d8",
    "INPUT_BG": "#050a16",
    "INPUT_BORDER": "#1a4a7a",
    "GOLD": "#00d4ff",  # 강렬한 시안
    "GOLD_HOVER": "#5cefff",
    "GOLD_SOFT": "#a5f3fc",
    "ON_GOLD": "#02040a",
    "BLUE": "#38bdf8",
    "BLUE_SOFT": "#7dd3fc",
    "GREEN": "#34d399",
    "GREEN_HOVER": "#10b981",
    "RED": "#f87171",
    "RED_HOVER": "#ef4444",
    "RED_SOFT": "#fca5a5",
    "PURPLE": "#a78bfa",
    "PURPLE_HOVER": "#7c3aed",
    "WARN": "#fbbf24",
    "TIER_S": "#fde047",
    "TIER_A": "#00d4ff",
    "TIER_B": "#34d399",
    "TIER_C": "#f87171",
    "TEXT": "#d0e8ff",
    "TEXT_BRIGHT": "#f0f8ff",
    "TEXT_DIM": "#6a8ab0",
    "TEXT_MUTE": "#4a6a90",
}

_PALETTES = {
    SKIN_CLASSIC: _PALETTE_CLASSIC,
    SKIN_NEON: _PALETTE_NEON,
}

# 모듈 레벨 토큰 (import 시 classic 으로 채움 — apply_skin 이 덮어씀)
BG = PANEL = CARD = ROW = ROW_HOVER = BORDER = INPUT_BG = INPUT_BORDER = ""
GOLD = GOLD_HOVER = GOLD_SOFT = ON_GOLD = ""
BLUE = BLUE_SOFT = GREEN = GREEN_HOVER = RED = RED_HOVER = RED_SOFT = ""
PURPLE = PURPLE_HOVER = WARN = ""
TIER_S = TIER_A = TIER_B = TIER_C = ""
TEXT = TEXT_BRIGHT = TEXT_DIM = TEXT_MUTE = ""
BTN_PRIMARY: tuple[str, str, str] = ("", "", "")
BTN_SECONDARY: tuple[str, str, str] = ("", "", "")
BTN_TERTIARY: tuple[str, str, str] = ("", "", "")
BTN_SUCCESS: tuple[str, str, str] = ("", "", "")
BTN_PURPLE: tuple[str, str, str] = ("", "", "")
BTN_DANGER: tuple[str, str, str] = ("", "", "")

_ACTIVE_SKIN = SKIN_CLASSIC


def load_skin_name() -> str:
    """ui.json 의 ui_skin (없으면 classic)."""
    try:
        from lol_coach.config import load_ui_settings

        raw = str(load_ui_settings().get("ui_skin", DEFAULT_SKIN) or DEFAULT_SKIN)
        name = raw.strip().lower()
        if name in ("gold", "classic", "default"):
            return SKIN_CLASSIC
        if name in ("neon", "glass", "reference"):
            return SKIN_NEON
        return name if name in SKINS else DEFAULT_SKIN
    except Exception:
        return DEFAULT_SKIN


def resolve_theme_path(skin: str | None = None) -> Path:
    """스킨별 CTk theme JSON 경로."""
    name = skin or load_skin_name()
    if name == SKIN_NEON:
        p = _GUI_DIR / "theme_neon.json"
        if p.is_file():
            return p
    classic = _GUI_DIR / "theme_classic.json"
    if classic.is_file():
        return classic
    return _GUI_DIR / "theme.json"


def active_skin() -> str:
    return _ACTIVE_SKIN


def apply_skin(skin: str | None = None) -> str:
    """팔레트·버튼 토큰을 스킨에 맞게 모듈 전역에 적용. 적용된 스킨 이름 반환."""
    global _ACTIVE_SKIN
    global BG, PANEL, CARD, ROW, ROW_HOVER, BORDER, INPUT_BG, INPUT_BORDER
    global GOLD, GOLD_HOVER, GOLD_SOFT, ON_GOLD
    global BLUE, BLUE_SOFT, GREEN, GREEN_HOVER, RED, RED_HOVER, RED_SOFT
    global PURPLE, PURPLE_HOVER, WARN
    global TIER_S, TIER_A, TIER_B, TIER_C
    global TEXT, TEXT_BRIGHT, TEXT_DIM, TEXT_MUTE
    global BTN_PRIMARY, BTN_SECONDARY, BTN_TERTIARY, BTN_SUCCESS, BTN_PURPLE, BTN_DANGER

    name = (skin or load_skin_name()).strip().lower()
    if name not in SKINS:
        name = DEFAULT_SKIN
    pal = _PALETTES[name]
    _ACTIVE_SKIN = name

    BG = pal["BG"]
    PANEL = pal["PANEL"]
    CARD = pal["CARD"]
    ROW = pal["ROW"]
    ROW_HOVER = pal["ROW_HOVER"]
    BORDER = pal["BORDER"]
    INPUT_BG = pal["INPUT_BG"]
    INPUT_BORDER = pal["INPUT_BORDER"]
    GOLD = pal["GOLD"]
    GOLD_HOVER = pal["GOLD_HOVER"]
    GOLD_SOFT = pal["GOLD_SOFT"]
    ON_GOLD = pal["ON_GOLD"]
    BLUE = pal["BLUE"]
    BLUE_SOFT = pal["BLUE_SOFT"]
    GREEN = pal["GREEN"]
    GREEN_HOVER = pal["GREEN_HOVER"]
    RED = pal["RED"]
    RED_HOVER = pal["RED_HOVER"]
    RED_SOFT = pal["RED_SOFT"]
    PURPLE = pal["PURPLE"]
    PURPLE_HOVER = pal["PURPLE_HOVER"]
    WARN = pal["WARN"]
    TIER_S = pal["TIER_S"]
    TIER_A = pal["TIER_A"]
    TIER_B = pal["TIER_B"]
    TIER_C = pal["TIER_C"]
    TEXT = pal["TEXT"]
    TEXT_BRIGHT = pal["TEXT_BRIGHT"]
    TEXT_DIM = pal["TEXT_DIM"]
    TEXT_MUTE = pal["TEXT_MUTE"]

    BTN_PRIMARY = (GOLD, GOLD_HOVER, ON_GOLD)
    BTN_SECONDARY = (PANEL, ROW_HOVER, GOLD_SOFT)
    BTN_TERTIARY = (INPUT_BG, ROW_HOVER, TEXT_DIM)
    BTN_SUCCESS = (GREEN, GREEN_HOVER, ON_GOLD)
    BTN_PURPLE = (PURPLE, PURPLE_HOVER, ON_GOLD)
    BTN_DANGER = (RED, RED_HOVER, "#FFFFFF")
    return name


# import 시 기본 스킨 로드 (테스트·early import 안전)
apply_skin(DEFAULT_SKIN)


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
