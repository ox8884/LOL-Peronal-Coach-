"""롤 실전 코치 GUI — 디자인 토큰 & 스킨.

스킨: classic(골드) + 시안/퍼플 계열 여러 종.
`theme_*.json` 이 없으면 팔레트에서 생성한다.
기능 변경 없이 스킨만 담당한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lol_coach.riot.models import FormProvenance

# ── 스킨 ID ─────────────────────────────────────────────────────────
SKIN_CLASSIC = "classic"
SKIN_NEON = "neon"
SKIN_AQUA = "aqua"
SKIN_ICE = "ice"
SKIN_VIOLET = "violet"
SKIN_OCEAN = "ocean"
SKIN_MINT = "mint"
# 밝은 스킨
SKIN_LIGHT = "light"
SKIN_SKY = "sky"
SKIN_CREAM = "cream"
SKIN_BLUSH = "blush"

SKINS: tuple[str, ...] = (
    SKIN_CLASSIC,
    SKIN_NEON,
    SKIN_AQUA,
    SKIN_ICE,
    SKIN_VIOLET,
    SKIN_OCEAN,
    SKIN_MINT,
    SKIN_LIGHT,
    SKIN_SKY,
    SKIN_CREAM,
    SKIN_BLUSH,
)
DEFAULT_SKIN = SKIN_CLASSIC

# 라이트 모드 스킨 (CTk appearance_mode = light)
LIGHT_SKINS: frozenset[str] = frozenset({SKIN_LIGHT, SKIN_SKY, SKIN_CREAM, SKIN_BLUSH})

# 설정 UI · 헤더 배지용
SKIN_LABELS: dict[str, str] = {
    SKIN_CLASSIC: "클래식 (골드) — 기존 다크",
    SKIN_NEON: "네온 시안 — 강렬한 글래스",
    SKIN_AQUA: "아쿠아 — 부드러운 청록",
    SKIN_ICE: "아이스 — 차가운 하늘색",
    SKIN_VIOLET: "바이올렛 — 퍼플 네온",
    SKIN_OCEAN: "오션 — 깊은 블루",
    SKIN_MINT: "민트 — 청록 다크",
    SKIN_LIGHT: "라이트 — 밝은 화이트",
    SKIN_SKY: "스카이 — 밝은 하늘",
    SKIN_CREAM: "크림 — 밝은 웜톤",
    SKIN_BLUSH: "블러시 — 밝은 라벤더",
}
SKIN_SHORT: dict[str, str] = {
    SKIN_CLASSIC: "클래식",
    SKIN_NEON: "네온",
    SKIN_AQUA: "아쿠아",
    SKIN_ICE: "아이스",
    SKIN_VIOLET: "바이올렛",
    SKIN_OCEAN: "오션",
    SKIN_MINT: "민트",
    SKIN_LIGHT: "라이트",
    SKIN_SKY: "스카이",
    SKIN_CREAM: "크림",
    SKIN_BLUSH: "블러시",
}

# 구버전 별칭
_SKIN_ALIASES = {
    "gold": SKIN_CLASSIC,
    "default": SKIN_CLASSIC,
    "glass": SKIN_NEON,
    "reference": SKIN_NEON,
    "cyan": SKIN_NEON,
    "purple": SKIN_VIOLET,
    "teal": SKIN_AQUA,
    "white": SKIN_LIGHT,
    "day": SKIN_LIGHT,
    "bright": SKIN_LIGHT,
}

_GUI_DIR = Path(__file__).resolve().parent


def _p(
    *,
    bg: str,
    panel: str,
    card: str,
    row: str,
    row_hover: str,
    border: str,
    input_bg: str,
    input_border: str,
    accent: str,
    accent_hover: str,
    accent_soft: str,
    on_accent: str,
    blue: str = "#38bdf8",
    blue_soft: str = "#7dd3fc",
    green: str = "#34d399",
    green_hover: str = "#10b981",
    red: str = "#f87171",
    red_hover: str = "#ef4444",
    red_soft: str = "#fca5a5",
    purple: str = "#a78bfa",
    purple_hover: str = "#7c3aed",
    warn: str = "#fbbf24",
    text: str = "#d0e8ff",
    text_bright: str = "#f0f8ff",
    text_dim: str = "#6a8ab0",
    text_mute: str = "#4a6a90",
) -> dict[str, str]:
    """팔레트 dict — GOLD* 는 스킨 액센트 별칭(기존 코드 호환)."""
    return {
        "BG": bg,
        "PANEL": panel,
        "CARD": card,
        "ROW": row,
        "ROW_HOVER": row_hover,
        "BORDER": border,
        "INPUT_BG": input_bg,
        "INPUT_BORDER": input_border,
        "GOLD": accent,
        "GOLD_HOVER": accent_hover,
        "GOLD_SOFT": accent_soft,
        "ON_GOLD": on_accent,
        "BLUE": blue,
        "BLUE_SOFT": blue_soft,
        "GREEN": green,
        "GREEN_HOVER": green_hover,
        "RED": red,
        "RED_HOVER": red_hover,
        "RED_SOFT": red_soft,
        "PURPLE": purple,
        "PURPLE_HOVER": purple_hover,
        "WARN": warn,
        "TIER_S": "#fde047",
        "TIER_A": accent,
        "TIER_B": green,
        "TIER_C": red,
        "TEXT": text,
        "TEXT_BRIGHT": text_bright,
        "TEXT_DIM": text_dim,
        "TEXT_MUTE": text_mute,
    }


_PALETTE_CLASSIC = _p(
    bg="#0A0E14",
    panel="#121A24",
    card="#16202C",
    row="#18232F",
    row_hover="#1F2C3B",
    border="#1E2A3A",
    input_bg="#0D1520",
    input_border="#23303F",
    accent="#C8AA6E",
    accent_hover="#DCC08A",
    accent_soft="#E8DCC8",
    on_accent="#0A0E14",
    blue="#4DA3FF",
    blue_soft="#8FBEFF",
    green="#31C48D",
    green_hover="#27A678",
    red="#F05252",
    red_hover="#D64545",
    red_soft="#FF8A8A",
    purple="#A78BFA",
    purple_hover="#8B6FE8",
    warn="#FFB74D",
    text="#C9D4E0",
    text_bright="#E8ECF2",
    text_dim="#7B8BA0",
    text_mute="#5A6B80",
)

# 보더(BORDER)는 액센트보다 한 톤 죽여 선이 깔끔하게 보이게 함
_PALETTE_NEON = _p(
    bg="#02040a",
    panel="#070e1c",
    card="#0a1228",
    row="#0e1830",
    row_hover="#162848",
    border="#1a3558",
    input_bg="#050a16",
    input_border="#243d62",
    accent="#00d4ff",
    accent_hover="#5cefff",
    accent_soft="#a5f3fc",
    on_accent="#02040a",
    purple="#a78bfa",
    purple_hover="#7c3aed",
)

_PALETTE_AQUA = _p(
    bg="#041210",
    panel="#0a1c1a",
    card="#0e2422",
    row="#12302c",
    row_hover="#1a403a",
    border="#1a4540",
    input_bg="#061816",
    input_border="#245850",
    accent="#2dd4bf",
    accent_hover="#5eead4",
    accent_soft="#99f6e4",
    on_accent="#042f2e",
    purple="#5eead4",
    purple_hover="#14b8a6",
)

_PALETTE_ICE = _p(
    bg="#030712",
    panel="#0b1224",
    card="#111b33",
    row="#152244",
    row_hover="#1c2e58",
    border="#1e3a5c",
    input_bg="#070e1c",
    input_border="#2a4a72",
    accent="#7dd3fc",
    accent_hover="#bae6fd",
    accent_soft="#e0f2fe",
    on_accent="#0c1a2e",
    purple="#93c5fd",
    purple_hover="#60a5fa",
)

_PALETTE_VIOLET = _p(
    bg="#0a0614",
    panel="#140a22",
    card="#1a0f30",
    row="#22143c",
    row_hover="#2e1a52",
    border="#3a2a58",
    input_bg="#100818",
    input_border="#4a3570",
    accent="#a78bfa",
    accent_hover="#c4b5fd",
    accent_soft="#ede9fe",
    on_accent="#1e0a3c",
    purple="#c084fc",
    purple_hover="#9333ea",
    blue="#818cf8",
)

_PALETTE_OCEAN = _p(
    bg="#020617",
    panel="#0a1628",
    card="#0f1e38",
    row="#152a48",
    row_hover="#1c365c",
    border="#1e3a5c",
    input_bg="#061018",
    input_border="#2a4a72",
    accent="#3b82f6",
    accent_hover="#60a5fa",
    accent_soft="#bfdbfe",
    on_accent="#0a1628",
    purple="#6366f1",
    purple_hover="#4f46e5",
)

_PALETTE_MINT = _p(
    bg="#03140f",
    panel="#0a1f18",
    card="#0f2a20",
    row="#143528",
    row_hover="#1c4634",
    border="#1a4034",
    input_bg="#061a12",
    input_border="#245040",
    accent="#34d399",
    accent_hover="#6ee7b7",
    accent_soft="#d1fae5",
    on_accent="#022c22",
    purple="#6ee7b7",
    purple_hover="#10b981",
)

# ── 밝은 스킨 (라이트 배경 + 진한 텍스트) ─────────────────────────
_PALETTE_LIGHT = _p(
    bg="#f4f7fb",
    panel="#ffffff",
    card="#ffffff",
    row="#eef3f9",
    row_hover="#e2ebf5",
    border="#d0d8e4",
    input_bg="#ffffff",
    input_border="#c5cedb",
    accent="#0284c7",
    accent_hover="#0ea5e9",
    accent_soft="#0369a1",
    on_accent="#ffffff",
    blue="#2563eb",
    blue_soft="#60a5fa",
    green="#059669",
    green_hover="#047857",
    red="#dc2626",
    red_hover="#b91c1c",
    red_soft="#f87171",
    purple="#7c3aed",
    purple_hover="#6d28d9",
    warn="#d97706",
    text="#334155",
    text_bright="#0f172a",
    text_dim="#64748b",
    text_mute="#94a3b8",
)

_PALETTE_SKY = _p(
    bg="#eef8ff",
    panel="#f8fcff",
    card="#ffffff",
    row="#e8f4fc",
    row_hover="#dceef9",
    border="#c5e0f5",
    input_bg="#ffffff",
    input_border="#b8d9f0",
    accent="#0ea5e9",
    accent_hover="#38bdf8",
    accent_soft="#0369a1",
    on_accent="#ffffff",
    purple="#6366f1",
    purple_hover="#4f46e5",
    text="#0c4a6e",
    text_bright="#082f49",
    text_dim="#0369a1",
    text_mute="#7aa8c8",
)

_PALETTE_CREAM = _p(
    bg="#faf6ef",
    panel="#fffdf8",
    card="#ffffff",
    row="#f5efe4",
    row_hover="#ebe3d4",
    border="#e5d8c4",
    input_bg="#ffffff",
    input_border="#ddd0ba",
    accent="#c4893a",
    accent_hover="#d4a05a",
    accent_soft="#8b5e2b",
    on_accent="#ffffff",
    purple="#b45309",
    purple_hover="#92400e",
    green="#65a30d",
    green_hover="#4d7c0f",
    text="#44403c",
    text_bright="#1c1917",
    text_dim="#78716c",
    text_mute="#a8a29e",
)

_PALETTE_BLUSH = _p(
    bg="#faf5ff",
    panel="#fdfaff",
    card="#ffffff",
    row="#f5eefc",
    row_hover="#efe4fa",
    border="#e4d8f5",
    input_bg="#ffffff",
    input_border="#dccff0",
    accent="#8b5cf6",
    accent_hover="#a78bfa",
    accent_soft="#6d28d9",
    on_accent="#ffffff",
    purple="#a855f7",
    purple_hover="#9333ea",
    blue="#818cf8",
    text="#4c1d95",
    text_bright="#2e1065",
    text_dim="#6d28d9",
    text_mute="#9b7ec8",
)

_PALETTES: dict[str, dict[str, str]] = {
    SKIN_CLASSIC: _PALETTE_CLASSIC,
    SKIN_NEON: _PALETTE_NEON,
    SKIN_AQUA: _PALETTE_AQUA,
    SKIN_ICE: _PALETTE_ICE,
    SKIN_VIOLET: _PALETTE_VIOLET,
    SKIN_OCEAN: _PALETTE_OCEAN,
    SKIN_MINT: _PALETTE_MINT,
    SKIN_LIGHT: _PALETTE_LIGHT,
    SKIN_SKY: _PALETTE_SKY,
    SKIN_CREAM: _PALETTE_CREAM,
    SKIN_BLUSH: _PALETTE_BLUSH,
}


def build_ctk_theme(pal: dict[str, str]) -> dict[str, Any]:
    """팔레트 → CustomTkinter theme.json 구조.

    모든 스킨 공통 기하학 (라운드·보더 두께)을 통일해 선이 들쭉날쭉하지 않게 한다.
    기본 Frame 은 보더 0 — 카드만 코드에서 border_width=1 로 그림.
    """
    bg = pal["BG"]
    panel = pal["PANEL"]
    card = pal["CARD"]
    border = pal["BORDER"]
    input_bg = pal["INPUT_BG"]
    input_border = pal["INPUT_BORDER"]
    accent = pal["GOLD"]
    accent_h = pal["GOLD_HOVER"]
    soft = pal["GOLD_SOFT"]
    on_a = pal["ON_GOLD"]
    text = pal["TEXT"]
    bright = pal["TEXT_BRIGHT"]
    dim = pal["TEXT_MUTE"]
    row_h = pal["ROW_HOVER"]
    # 전 스킨 공통 치수
    r_frame = 12
    r_ctrl = 10
    r_pill = 12
    return {
        "CTk": {"fg_color": [bg, bg]},
        "CTkToplevel": {"fg_color": [bg, bg]},
        "CTkFrame": {
            "corner_radius": r_frame,
            "border_width": 0,  # 투명/중첩 프레임에 선이 생기지 않게
            "fg_color": [card, card],
            "top_fg_color": [panel, panel],
            "border_color": [border, border],
        },
        "CTkButton": {
            "corner_radius": r_ctrl,
            "border_width": 0,
            "fg_color": [accent, accent],
            "hover_color": [accent_h, accent_h],
            "border_color": [border, border],
            "text_color": [on_a, on_a],
            "text_color_disabled": [dim, dim],
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": "transparent",
            "border_color": [border, border],
            "text_color": [text, text],
        },
        "CTkEntry": {
            "corner_radius": r_ctrl,
            "border_width": 1,
            "fg_color": [input_bg, input_bg],
            "border_color": [input_border, input_border],
            "text_color": [bright, bright],
            "text_color_disabled": [dim, dim],
            "placeholder_text_color": [dim, dim],
        },
        "CTkCheckBox": {
            "corner_radius": 6,
            "border_width": 2,
            "fg_color": [accent, accent],
            "border_color": [input_border, input_border],
            "hover_color": [accent_h, accent_h],
            "checkmark_color": [on_a, on_a],
            "text_color": [text, text],
            "text_color_disabled": [dim, dim],
        },
        "CTkSwitch": {
            "corner_radius": 1000,
            "border_width": 0,
            "button_length": 0,
            "fg_color": [row_h, row_h],
            "progress_color": [accent, accent],
            "button_color": [soft, soft],
            "button_hover_color": [bright, bright],
            "text_color": [text, text],
            "text_color_disabled": [dim, dim],
        },
        "CTkRadioButton": {
            "corner_radius": 1000,
            "border_width_checked": 6,
            "border_width_unchecked": 2,
            "fg_color": [accent, accent],
            "border_color": [input_border, input_border],
            "hover_color": [accent_h, accent_h],
            "text_color": [text, text],
            "text_color_disabled": [dim, dim],
        },
        "CTkProgressBar": {
            "corner_radius": 1000,
            "border_width": 0,
            "fg_color": [row_h, row_h],
            "progress_color": [accent, accent],
            "border_color": [border, border],
        },
        "CTkSlider": {
            "corner_radius": 1000,
            "button_corner_radius": 1000,
            "border_width": 0,
            "button_length": 0,
            "fg_color": [row_h, row_h],
            "progress_color": [accent, accent],
            "button_color": [accent, accent],
            "button_hover_color": [accent_h, accent_h],
        },
        "CTkOptionMenu": {
            "corner_radius": r_ctrl,
            "fg_color": [panel, panel],
            "button_color": [border, border],
            "button_hover_color": [row_h, row_h],
            "text_color": [soft, soft],
            "text_color_disabled": [dim, dim],
        },
        "CTkComboBox": {
            "corner_radius": r_ctrl,
            "border_width": 1,
            "fg_color": [input_bg, input_bg],
            "border_color": [input_border, input_border],
            "button_color": [border, border],
            "button_hover_color": [row_h, row_h],
            "text_color": [bright, bright],
            "text_color_disabled": [dim, dim],
        },
        "CTkScrollbar": {
            "corner_radius": 1000,
            "border_spacing": 4,
            "fg_color": "transparent",
            "button_color": [border, border],
            "button_hover_color": [accent, accent],
        },
        "CTkSegmentedButton": {
            "corner_radius": r_pill,
            "border_width": 0,
            "fg_color": [panel, panel],
            "selected_color": [accent, accent],
            "selected_hover_color": [accent_h, accent_h],
            "unselected_color": [panel, panel],
            "unselected_hover_color": [row_h, row_h],
            "text_color": [on_a, on_a],
            "text_color_disabled": [dim, dim],
        },
        "CTkTextbox": {
            "corner_radius": r_ctrl,
            "border_width": 1,
            "fg_color": [input_bg, input_bg],
            "border_color": [input_border, input_border],
            "text_color": [text, text],
            "scrollbar_button_color": [border, border],
            "scrollbar_button_hover_color": [accent, accent],
        },
        "CTkScrollableFrame": {"label_fg_color": [panel, panel]},
        "DropdownMenu": {
            "fg_color": [panel, panel],
            "hover_color": [row_h, row_h],
            "text_color": [text, text],
        },
        "CTkFont": {
            "macOS": {"family": "Malgun Gothic", "size": 13, "weight": "normal"},
            "Windows": {"family": "Malgun Gothic", "size": 13, "weight": "normal"},
            "Linux": {"family": "Malgun Gothic", "size": 13, "weight": "normal"},
        },
    }


# 카드/행 공통 치수 (코드에서 카드 그릴 때 사용)
CARD_RADIUS = 12
CARD_BORDER = 1
ROW_RADIUS = 10
ROW_BORDER = 1


# 모듈 레벨 토큰
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


def normalize_skin_name(raw: str | None) -> str:
    name = str(raw or DEFAULT_SKIN).strip().lower()
    name = _SKIN_ALIASES.get(name, name)
    return name if name in _PALETTES else DEFAULT_SKIN


def load_skin_name() -> str:
    """ui.json 의 ui_skin (없으면 classic)."""
    try:
        from lol_coach.config import load_ui_settings

        return normalize_skin_name(load_ui_settings().get("ui_skin", DEFAULT_SKIN))
    except Exception:
        return DEFAULT_SKIN


def ensure_theme_file(skin: str, *, force: bool = False) -> Path:
    """스킨용 theme JSON 경로. 없거나 force 시 팔레트로 (재)생성."""
    name = normalize_skin_name(skin)
    if name == SKIN_CLASSIC:
        preferred = _GUI_DIR / "theme_classic.json"
        # 레거시 theme.json 도 동기화
        legacy = _GUI_DIR / "theme.json"
    else:
        preferred = _GUI_DIR / f"theme_{name}.json"
        legacy = None
    if force or not preferred.is_file():
        pal = _PALETTES[name]
        text = json.dumps(build_ctk_theme(pal), ensure_ascii=False, indent=2)
        preferred.write_text(text, encoding="utf-8")
        if legacy is not None:
            try:
                legacy.write_text(text, encoding="utf-8")
            except Exception:
                pass
    return preferred


def regenerate_all_theme_files() -> list[Path]:
    """모든 스킨 theme_*.json 을 팔레트에서 다시 씀."""
    out: list[Path] = []
    for sid in SKINS:
        out.append(ensure_theme_file(sid, force=True))
    return out


def resolve_theme_path(skin: str | None = None) -> Path:
    """스킨별 CTk theme JSON 경로."""
    return ensure_theme_file(skin or load_skin_name())


def active_skin() -> str:
    return _ACTIVE_SKIN


def is_light_skin(skin: str | None = None) -> bool:
    """밝은 스킨 여부 (CTk appearance_mode=light)."""
    return normalize_skin_name(skin or _ACTIVE_SKIN) in LIGHT_SKINS


def appearance_mode_for(skin: str | None = None) -> str:
    return "light" if is_light_skin(skin) else "dark"


def apply_skin(skin: str | None = None) -> str:
    """팔레트·버튼 토큰을 스킨에 맞게 모듈 전역에 적용."""
    global _ACTIVE_SKIN
    global BG, PANEL, CARD, ROW, ROW_HOVER, BORDER, INPUT_BG, INPUT_BORDER
    global GOLD, GOLD_HOVER, GOLD_SOFT, ON_GOLD
    global BLUE, BLUE_SOFT, GREEN, GREEN_HOVER, RED, RED_HOVER, RED_SOFT
    global PURPLE, PURPLE_HOVER, WARN
    global TIER_S, TIER_A, TIER_B, TIER_C
    global TEXT, TEXT_BRIGHT, TEXT_DIM, TEXT_MUTE
    global BTN_PRIMARY, BTN_SECONDARY, BTN_TERTIARY, BTN_SUCCESS, BTN_PURPLE, BTN_DANGER

    name = normalize_skin_name(skin or load_skin_name())
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

    # 테마 파일 보장 (패키징·실행 모두)
    try:
        ensure_theme_file(name)
    except Exception:
        pass
    return name


# import 시 기본 스킨
apply_skin(DEFAULT_SKIN)


def btn(fg: str, hover: str, text: str) -> dict[str, str]:
    return {"fg_color": fg, "hover_color": hover, "text_color": text}


def tier(t: str) -> tuple[str, str]:
    key = (t or "").strip().split()[-1].upper() if (t or "").strip() else ""
    return {
        "S": (TIER_S, ON_GOLD),
        "A": (TIER_A, ON_GOLD),
        "B": (TIER_B, ON_GOLD),
        "C": (TIER_C, "#FFFFFF"),
    }.get(key, (TEXT_DIM, "#FFFFFF"))


def tier_chip(parent: Any, t: str, *, font: Any = None, width: int = 26) -> Any:
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


def provenance_label(provenance: FormProvenance | None) -> str:
    """집계 카드에 표시할 출처·패치·표본·신선도 요약."""
    if provenance is None:
        return "데이터 신뢰도: 확인 불가"
    if not provenance.patches:
        patch = "알 수 없음"
    elif len(provenance.patches) == 1:
        patch = provenance.patches[0]
    else:
        patch = "혼합 패치"
    age = provenance.age if provenance.age != "unknown" else "알 수 없음"
    freshness = provenance.freshness if provenance.freshness != "unknown" else "확인 필요"
    sample = f"표본 {provenance.sample_count}판"
    if provenance.sample_count < 3:
        sample += " · 표본 부족"
    return (
        f"출처 {provenance.source} · 패치 {patch} · "
        f"{sample} · 데이터 시점 {age} · "
        f"신선도 {freshness}"
    )
