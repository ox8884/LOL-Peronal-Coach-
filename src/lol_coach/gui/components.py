"""롤 실전 코치 GUI — 디자인 토큰 & 스킨.

차콜 · 미드나이트 · 페이퍼 팔레트와 즉시 적용.
`theme_*.json` 이 없으면 팔레트에서 생성한다.
기능 변경 없이 스킨만 담당한다.
"""

from __future__ import annotations

import json
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from typing import Any

from lol_coach.gui.constants import FONT_UI
from lol_coach.riot.models import FormProvenance

SKINS: tuple[str, ...] = ("charcoal", "midnight", "paper")
DEFAULT_SKIN = "charcoal"
LIGHT_SKINS = frozenset({"paper"})
SKIN_SHORT = {"charcoal": "차콜", "midnight": "미드나이트", "paper": "페이퍼"}
SKIN_LABELS = {"charcoal": "차콜 · 차분한 다크", "midnight": "미드나이트 · 선명한 블루", "paper": "페이퍼 · 편안한 라이트"}
_SKIN_ALIASES = {
    **dict.fromkeys(("classic", "gold", "default", "aqua", "mint"), "charcoal"),
    **dict.fromkeys(("neon", "glass", "reference", "cyan", "ice", "violet", "purple", "ocean", "neon_arena", "teal"), "midnight"),
    **dict.fromkeys(("light", "sky", "cream", "blush", "white", "day", "bright"), "paper"),
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
        "TIER_S": warn,
        "TIER_A": accent,
        "TIER_B": green,
        "TIER_C": red,
        "TEXT": text,
        "TEXT_BRIGHT": text_bright,
        "TEXT_DIM": text_dim,
        "TEXT_MUTE": text_mute,
    }


_PALETTES: dict[str, dict[str, str]] = {
    "charcoal": _p(
        bg="#111416", panel="#191D20", card="#20262A", row="#252D32",
        row_hover="#303B41", border="#3B484F", input_bg="#151A1D", input_border="#64747D",
        accent="#8ED5C0", accent_hover="#ACE8D6", accent_soft="#B7E7DA", on_accent="#102B25",
        blue="#82B8F2", blue_soft="#B4D4F5", green="#7DD9A4", green_hover="#A0E9BF",
        red="#FF999F", red_hover="#FFC0C5", red_soft="#FFD0D4", purple="#C4AFF1", purple_hover="#D8C8FB",
        warn="#EAC681", text="#D6DFE3", text_bright="#F3F6F7", text_dim="#AFBDC4", text_mute="#9EAFB8",
    ),
    "midnight": _p(
        bg="#10151E", panel="#171F2B", card="#1F2A38", row="#243144",
        row_hover="#314158", border="#3E506A", input_bg="#141C28", input_border="#6D83A0",
        accent="#91BFFF", accent_hover="#B4D3FF", accent_soft="#C2DBFF", on_accent="#142C4A",
        blue="#88CFEA", blue_soft="#B6E4F5", green="#8CDAB8", green_hover="#ADEBD0",
        red="#FFA2AE", red_hover="#FFC6CD", red_soft="#FFD4DD", purple="#C8B5F4", purple_hover="#DFD0FF",
        warn="#F2CD92", text="#D5E0EE", text_bright="#F1F6FD", text_dim="#AFBFD4", text_mute="#9CADC6",
    ),
    "paper": _p(
        bg="#F1F3F5", panel="#FAFBFC", card="#FEFFFF", row="#E9EEF1",
        row_hover="#DCE5EB", border="#C6D1D9", input_bg="#FDFEFE", input_border="#73838F",
        accent="#275F89", accent_hover="#19496E", accent_soft="#244F70", on_accent="#F8FCFF",
        blue="#235FB2", blue_soft="#315E86", green="#237348", green_hover="#185C37",
        red="#B83249", red_hover="#942337", red_soft="#A33D50", purple="#7052A0", purple_hover="#583D87",
        warn="#865900", text="#344551", text_bright="#15232D", text_dim="#506473", text_mute="#566976",
    ),
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
            "macOS": {"family": FONT_UI, "size": 13, "weight": "normal"},
            "Windows": {"family": FONT_UI, "size": 13, "weight": "normal"},
            "Linux": {"family": FONT_UI, "size": 13, "weight": "normal"},
        },
    }


# 카드/행 공통 치수 (코드에서 카드 그릴 때 사용)
CARD_RADIUS = 16
CARD_BORDER = 1
ROW_RADIUS = 12
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

_ACTIVE_SKIN = DEFAULT_SKIN


def normalize_skin_name(raw: str | None) -> str:
    name = str(raw or DEFAULT_SKIN).strip().lower()
    name = _SKIN_ALIASES.get(name, name)
    return name if name in _PALETTES else DEFAULT_SKIN


def load_skin_name() -> str:
    """ui.json 의 ui_skin을 읽고 이전 스킨을 새 팔레트로 연결한다."""
    try:
        from lol_coach.config import load_ui_settings

        return normalize_skin_name(load_ui_settings().get("ui_skin", DEFAULT_SKIN))
    except Exception:
        return DEFAULT_SKIN


def ensure_theme_file(skin: str, *, force: bool = False) -> Path:
    """스킨용 theme JSON 경로. 없거나 force 시 팔레트로 (재)생성."""
    name = normalize_skin_name(skin)
    preferred = _GUI_DIR / f"theme_{name}.json"
    if force or not preferred.is_file():
        text = json.dumps(build_ctk_theme(_PALETTES[name]), ensure_ascii=True, indent=2)
        preferred.write_text(text, encoding="utf-8")
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


def recolor_widgets(root: Any, previous: str, current: str) -> None:
    """열린 CTk 창과 Tk 텍스트/그래프의 팔레트만 교체한다. 위젯과 데이터는 유지한다."""
    import tkinter as tk

    import customtkinter as ctk

    old = _PALETTES[normalize_skin_name(previous)]
    new = _PALETTES[normalize_skin_name(current)]
    colors = {value.lower(): new[key] for key, value in old.items()}

    def replace(value: Any) -> Any:
        if isinstance(value, str):
            return colors.get(value.lower(), value)
        if isinstance(value, (tuple, list)):
            return [replace(part) for part in value]
        return value

    ctk_options = (
        "fg_color", "bg_color", "border_color", "text_color", "text_color_disabled",
        "hover_color", "button_color", "button_hover_color", "progress_color",
        "placeholder_text_color", "checkmark_color", "selected_color", "selected_hover_color",
        "unselected_color", "unselected_hover_color", "scrollbar_button_color",
        "scrollbar_button_hover_color", "dropdown_fg_color", "dropdown_hover_color",
        "dropdown_text_color", "label_fg_color", "label_text_color",
    )
    native_options = (
        "background", "foreground", "activebackground", "activeforeground",
        "highlightbackground", "highlightcolor", "insertbackground",
        "selectbackground", "selectforeground", "disabledforeground",
    )
    pending = [root]
    updates: list[tuple[Any, dict[str, Any]]] = []
    text_tags: list[tuple[Any, str, dict[str, Any]]] = []
    canvas_items: list[tuple[Any, int, dict[str, Any]]] = []
    scrollers: list[Any] = []
    # 부모의 configure가 자식 배경을 바꾸기 전에 모든 원래 색을 읽는다.
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        if isinstance(widget, ctk.CTkScrollableFrame):
            scrollers.append(widget)
            continue
        options = ctk_options if isinstance(widget, (ctk.CTkBaseClass, ctk.CTk, ctk.CTkToplevel)) else native_options
        changed = {}
        for option in options:
            try:
                value = widget.cget(option)
            except (ValueError, tk.TclError, AttributeError):
                continue
            updated = replace(value)
            if updated != value:
                changed[option] = updated
        if changed:
            updates.append((widget, changed))
        if isinstance(widget, tk.Text):
            for tag in widget.tag_names():
                changed = {}
                for option in ("foreground", "background"):
                    value = widget.tag_cget(tag, option)
                    if replace(value) != value:
                        changed[option] = replace(value)
                if changed:
                    text_tags.append((widget, tag, changed))
        if isinstance(widget, tk.Canvas) and not isinstance(widget, ctk.CTkCanvas):
            for item in widget.find_all():
                changed = {}
                for option in ("fill", "outline"):
                    try:
                        value = widget.itemcget(item, option)
                    except tk.TclError:
                        continue
                    if replace(value) != value:
                        changed[option] = replace(value)
                if changed:
                    canvas_items.append((widget, item, changed))
    for widget, changed in updates:
        widget.configure(**changed)
    # ScrollableFrame은 CTkBaseClass가 아니므로 같은 dark 모드에서도 내부 Tk 배경을 맞춘다.
    for widget in scrollers:
        color = widget.cget("fg_color")
        if color == "transparent":
            color = widget.cget("bg_color")
        color = widget._apply_appearance_mode(color)
        tk.Frame.configure(widget, background=color)
        widget._parent_canvas.configure(background=color)
    for widget, tag, changed in text_tags:
        widget.tag_configure(tag, **changed)
    for widget, item, changed in canvas_items:
        widget.itemconfigure(item, **changed)


# import 시 기본 스킨
apply_skin(DEFAULT_SKIN)


def btn(fg: str, hover: str, text: str) -> dict[str, str]:
    return {"fg_color": fg, "hover_color": hover, "text_color": text}


def clear_image(widget: Any) -> None:
    """CTk 콜백과 Tk의 이미지 이름을 함께 비워 재사용·배율 변경을 허용한다."""
    import customtkinter as ctk

    if isinstance(widget, ctk.CTkLabel):
        # CTkLabel의 image=None은 native Label에 남은 PhotoImage 이름을 지우지 않는다.
        widget._label.configure(image="")
    widget.configure(image=None)


def release_images(parent: Any) -> None:
    """파괴할 하위 위젯을 CTkImage 캐시의 콜백에서 해제한다."""
    import customtkinter as ctk

    pending = list(parent.winfo_children())
    while pending:
        widget = pending.pop()
        if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton)) and widget.cget("image"):
            clear_image(widget)
        pending.extend(widget.winfo_children())


def surface_color(widget: Any) -> str:
    """위젯 위에 놓일 자식이 칠해야 하는 실제 배경색 (CTk 투명 체인 해석)."""
    import customtkinter as ctk

    while True:
        if isinstance(widget, ctk.CTkScrollableFrame):
            color = widget.cget("fg_color")
            nxt = widget.master.master.master
        elif isinstance(widget, (ctk.CTkBaseClass, ctk.CTk, ctk.CTkToplevel)):
            color = widget.cget("fg_color")
            nxt = widget.master
        else:
            return str(widget.cget("bg"))
        if color not in (None, "transparent"):
            if isinstance(color, (tuple, list)):
                color = color[1 if ctk.get_appearance_mode() == "Dark" else 0]
            return str(color)
        widget = nxt


@lru_cache(maxsize=64)
def _text_metrics(font: tuple, scale: float) -> tuple[tuple, int]:
    import tkinter.font as tkfont

    scaled = (font[0], -abs(round(font[1] * scale)), *font[2:])
    return scaled, tkfont.Font(font=scaled).metrics("linespace")


class TextLabel(tk.Label):
    """투명 배경 텍스트(+아이콘) — CTkLabel(네이티브 창 3개) 대신 창 1개.

    결과 화면처럼 텍스트가 많은 곳에서 생성·파괴 비용을 1/3로 줄인다.
    CTkLabel과 같은 픽셀 글꼴·최소 높이(28)·줄바꿈 폭을 쓴다.
    아이콘은 CTkImage를 받아 같은 배율의 PhotoImage로 그린다.
    """

    def __init__(
        self,
        master: Any,
        *,
        text: str = "",
        font: tuple = (FONT_UI, 12),
        text_color: str | None = None,
        wraplength: int = 0,
        anchor: Any = "w",
        justify: Any = "left",
        image: Any = None,
        compound: Any = "left",
        min_height: int = 28,
        **kw: Any,
    ) -> None:
        import customtkinter as ctk

        self._scale = ctk.ScalingTracker.get_widget_scaling(master)
        scaled, self._line = _text_metrics(tuple(font), self._scale)
        self._min_height = min_height
        super().__init__(
            master,
            text=text,
            font=scaled,
            fg=text_color or TEXT,
            bg=surface_color(master),
            wraplength=round(wraplength * self._scale),
            anchor=anchor,
            justify=justify,
            compound=compound,
            bd=0,
            padx=0,
            highlightthickness=0,
            **kw,
        )
        self.set_image(image)

    def configure(self, cnf: Any = None, **kw: Any) -> Any:
        """CTkLabel 호환: text_color, 배율 전 wraplength를 받는다."""
        if "text_color" in kw:
            kw["fg"] = kw.pop("text_color")
        if "wraplength" in kw:
            kw["wraplength"] = round(kw["wraplength"] * self._scale)
        if "font" in kw:
            kw["font"], self._line = _text_metrics(tuple(kw["font"]), self._scale)
        return super().configure(cnf, **kw)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "wraplength":
            return round(int(super().cget(key)) / self._scale)
        return super().cget("fg" if key == "text_color" else key)

    def set_image(self, image: Any) -> None:
        """CTkImage(또는 None)로 아이콘 교체. 같은 이미지면 Tk 호출을 건너뛴다."""
        import customtkinter as ctk

        photo = (
            image.create_scaled_photo_image(self._scale, ctk.get_appearance_mode().lower())
            if image is not None
            else ""
        )
        self._image = image  # PhotoImage는 CTkImage가 소유 — 라벨이 살아 있는 동안 유지
        if str(self.cget("image")) != str(photo):
            self.configure(image=photo)
        icon_h = round(image.cget("size")[1] * self._scale) if image is not None else 0
        pady = max(0, (round(self._min_height * self._scale) - max(self._line, icon_h)) // 2)
        if int(self.cget("pady")) != pady:
            self.configure(pady=pady)


def section_heading(parent: Any, title: str, row: int) -> None:
    """골드 바 + 제목 섹션 헤더 (Tk 기본 위젯 3개 — CTk로는 7개)."""
    import customtkinter as ctk

    from lol_coach.gui.constants import FS

    head = tk.Frame(parent, bg=surface_color(parent), highlightthickness=0)
    head.grid(row=row, column=0, sticky="ew", padx=10, pady=(16, 6))
    scale = ctk.ScalingTracker.get_widget_scaling(parent)
    tk.Frame(
        head, width=round(5 * scale), height=round(20 * scale), bg=GOLD, highlightthickness=0
    ).pack(side="left", padx=(0, round(10 * scale)))
    TextLabel(head, text=title, font=FS, text_color=TEXT_BRIGHT).pack(side="left")


def sync_text_bg(frame: Any, old: str, new: str) -> None:
    """CTkFrame 배경을 바꿀 때 CTk가 건드리지 않는 Tk 자식(TextLabel 등)도 맞춘다."""
    for child in frame.winfo_children():
        if type(child) in (TextLabel, tk.Frame) and child.cget("bg").lower() == old.lower():
            child.configure(bg=new)
            sync_text_bg(child, old, new)


def destroy_children_later(parent: Any) -> None:
    """하위 위젯을 즉시 레이아웃에서 빼고, 파괴는 유휴 시간에 하나씩 한다.

    CTk 위젯 파괴는 개당 수 ms라 필터·검색 재렌더가 수백 ms 멈췄다.
    숨긴 위젯은 그려지지 않으므로 새 내용이 바로 표시되고, 숨긴 상태의
    파괴는 보이는 상태보다 빠르다.
    """
    widgets = parent.winfo_children()
    if not widgets:
        return
    for w in widgets:
        manager = w.winfo_manager()
        if manager in ("grid", "pack", "place"):
            getattr(w, f"{manager}_forget")()
    root = parent._root()

    def step() -> None:
        while widgets:
            w = widgets.pop()
            if w.winfo_exists():
                w.destroy()
                break
        if widgets:
            root.after(1, step)

    root.after(1, step)


def tier(t: str) -> tuple[str, str]:
    key = (t or "").strip().split()[-1].upper() if (t or "").strip() else ""
    return {
        "S": (TIER_S, ON_GOLD),
        "A": (TIER_A, ON_GOLD),
        "B": (TIER_B, ON_GOLD),
        "C": (TIER_C, ON_GOLD),
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
