"""롤 실전 코치 GUI — 디자인 토큰 (공략본).

연한 버터색 판 위에 종이 낱장, 먹색 띠와 괘선.
진한 노랑은 답·선택·1순위 형광펜에만 쓴다. 팔레트는 하나다.
`theme.json` 은 팔레트에서 생성한다.
"""

from __future__ import annotations

import json
import tempfile
import tkinter as tk
from functools import lru_cache
from pathlib import Path
from typing import Any

from lol_coach.gui.constants import FONT_UI
from lol_coach.riot.models import FormProvenance

_GUI_DIR = Path(__file__).resolve().parent

# ── 팔레트 ──────────────────────────────────────────────────────────
# 판·낱장
BG = "#F1E3A8"  # 판 (창 바탕)
PANEL = "#FBF8EE"  # 낱장 (종이)
CARD = PANEL
ROW = "#F2EEDD"  # 낱장 위의 행
ROW_HOVER = "#E8E2CA"
BORDER = "#CFCAB6"  # 가는 괘선
INPUT_BG = "#FFFFFF"
INPUT_BORDER = "#111111"
# 먹·노랑
INK = "#111111"  # 띠·굵은 괘선·주 버튼
INK_HOVER = "#34332D"
INK_RULE = "#4A4943"  # 먹 위의 괘선
ON_INK = "#FFFFFF"
ON_INK_DIM = "#C9C7BC"
YELLOW = "#FFD400"  # 답·선택·1순위에만
YELLOW_HOVER = "#FFE04D"
# 기존 코드 호환 이름 — 낱장 위 강조는 먹, 그 위 글자는 흰색.
# 노랑은 답·선택·1순위에만 쓰므로 여기에 넣지 않는다 (선택은 BTN_SELECTED).
GOLD = INK
GOLD_HOVER = INK_HOVER
GOLD_SOFT = "#23221E"
ON_GOLD = ON_INK
# 의미색 (낱장 위 글자로 4.5:1 이상)
BLUE = "#1C57C8"
BLUE_SOFT = "#2C5AA8"
GREEN = "#0B6B3A"
GREEN_HOVER = "#085A30"
RED = "#BB241A"
RED_HOVER = "#A51F15"
RED_SOFT = "#B03A2E"
PURPLE = "#6A35E0"
PURPLE_HOVER = "#5527BD"
WARN = "#8A5A00"
# 증강 희귀도 (칩 바탕 — 글자는 먹)
SILVER = "#C3CAD3"
RARITY_GOLD = "#F0A800"
PRISM = "#B99BFF"
ME_ROW = "#FFF0A3"  # 여러 사람 중 나 — 연한 형광펜
# 글자
TEXT = "#23221E"
TEXT_BRIGHT = INK
TEXT_DIM = "#4A483F"
TEXT_MUTE = "#5E5C53"

# 버튼 변형 (바탕, 호버, 글자)
BTN_PRIMARY: tuple[str, str, str] = (INK, INK_HOVER, ON_INK)
BTN_SECONDARY: tuple[str, str, str] = (PANEL, ROW_HOVER, INK)
BTN_TERTIARY: tuple[str, str, str] = (ROW, ROW_HOVER, TEXT_DIM)
BTN_SUCCESS: tuple[str, str, str] = (GREEN, GREEN_HOVER, "#FFFFFF")
BTN_PURPLE: tuple[str, str, str] = (PURPLE, PURPLE_HOVER, "#FFFFFF")
BTN_DANGER: tuple[str, str, str] = (RED, RED_HOVER, "#FFFFFF")
BTN_SELECTED: tuple[str, str, str] = (YELLOW, YELLOW_HOVER, INK)
BTN_BAND: tuple[str, str, str] = (INK, INK_HOVER, ON_INK_DIM)  # 먹색 띠 위의 조용한 버튼

# 모서리는 전부 직각, 선은 1px
CARD_RADIUS = 0
CARD_BORDER = 1
ROW_RADIUS = 0
ROW_BORDER = 1


def build_ctk_theme() -> dict[str, Any]:
    """팔레트 → CustomTkinter theme.json 구조."""

    def c(color: str) -> list[str]:
        return [color, color]

    return {
        "CTk": {"fg_color": c(BG)},
        "CTkToplevel": {"fg_color": c(BG)},
        "CTkFrame": {
            "corner_radius": 0,
            "border_width": 0,  # 투명/중첩 프레임에 선이 생기지 않게
            "fg_color": c(CARD),
            "top_fg_color": c(PANEL),
            "border_color": c(BORDER),
        },
        "CTkButton": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": c(INK),
            "hover_color": c(INK_HOVER),
            "border_color": c(INK),
            "text_color": c(ON_INK),
            "text_color_disabled": c("#8E8C82"),
        },
        "CTkLabel": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": "transparent",
            "border_color": c(BORDER),
            "text_color": c(TEXT),
        },
        "CTkEntry": {
            "corner_radius": 0,
            "border_width": 1,
            "fg_color": c(INPUT_BG),
            "border_color": c(INPUT_BORDER),
            "text_color": c(INK),
            "text_color_disabled": c(TEXT_MUTE),
            "placeholder_text_color": c("#6B695F"),
        },
        "CTkCheckBox": {
            "corner_radius": 0,
            "border_width": 2,
            "fg_color": c(INK),
            "border_color": c(INK),
            "hover_color": c(INK_HOVER),
            "checkmark_color": c(YELLOW),
            "text_color": c(TEXT),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkSwitch": {
            "corner_radius": 0,
            "border_width": 0,
            "button_length": 0,
            "fg_color": c("#B8B29B"),
            "progress_color": c(INK),
            "button_color": c("#FFFFFF"),
            "button_hover_color": c(YELLOW),
            "text_color": c(TEXT),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkRadioButton": {
            "corner_radius": 1000,
            "border_width_checked": 6,
            "border_width_unchecked": 2,
            "fg_color": c(INK),
            "border_color": c(INK),
            "hover_color": c(INK_HOVER),
            "text_color": c(TEXT),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkProgressBar": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": c(ROW_HOVER),
            "progress_color": c(INK),
            "border_color": c(BORDER),
        },
        "CTkSlider": {
            "corner_radius": 0,
            "button_corner_radius": 0,
            "border_width": 0,
            "button_length": 0,
            "fg_color": c("#B8B29B"),
            "progress_color": c(INK),
            "button_color": c(INK),
            "button_hover_color": c(INK_HOVER),
        },
        "CTkOptionMenu": {
            "corner_radius": 0,
            "fg_color": c(ROW),
            "button_color": c(BORDER),
            "button_hover_color": c(ROW_HOVER),
            "text_color": c(INK),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkComboBox": {
            "corner_radius": 0,
            "border_width": 1,
            "fg_color": c(INPUT_BG),
            "border_color": c(INPUT_BORDER),
            "button_color": c(BORDER),
            "button_hover_color": c(ROW_HOVER),
            "text_color": c(INK),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkScrollbar": {
            "corner_radius": 1000,
            "border_spacing": 5,
            "fg_color": "transparent",
            "button_color": c("#D2CCB5"),
            "button_hover_color": c(INK),
        },
        "CTkSegmentedButton": {
            "corner_radius": 0,
            "border_width": 0,
            "fg_color": c(ROW),
            "selected_color": c(YELLOW),
            "selected_hover_color": c(YELLOW_HOVER),
            "unselected_color": c(ROW),
            "unselected_hover_color": c(ROW_HOVER),
            "text_color": c(INK),
            "text_color_disabled": c(TEXT_MUTE),
        },
        "CTkTextbox": {
            "corner_radius": 0,
            "border_width": 1,
            "fg_color": c(INPUT_BG),
            "border_color": c(INPUT_BORDER),
            "text_color": c(TEXT),
            "scrollbar_button_color": c("#D2CCB5"),
            "scrollbar_button_hover_color": c(INK),
        },
        "CTkScrollableFrame": {"label_fg_color": c(PANEL)},
        "DropdownMenu": {
            "fg_color": c(PANEL),
            "hover_color": c(YELLOW),
            "text_color": c(INK),
        },
        "CTkFont": {
            "macOS": {"family": FONT_UI, "size": 13, "weight": "normal"},
            "Windows": {"family": FONT_UI, "size": 13, "weight": "normal"},
            "Linux": {"family": FONT_UI, "size": 13, "weight": "normal"},
        },
    }


def theme_path() -> Path:
    """CTk theme JSON 경로 — 팔레트와 다르면 다시 쓴다.

    설치 폴더에 쓸 수 없으면(Program Files) 임시 폴더에 만든다.
    """
    text = json.dumps(build_ctk_theme(), ensure_ascii=True, indent=2)
    path = _GUI_DIR / "theme.json"
    try:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "lol_coach_theme.json"
        fallback.write_text(text, encoding="utf-8")
        return fallback


def ink_titlebar(window: Any) -> None:
    """창 제목 표시줄을 먹색으로 (Windows 11). 지원하지 않으면 그대로 둔다."""
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
        for attr, color in ((35, 0x00111111), (36, 0x00FFFFFF)):  # 캡션·글자 (COLORREF = BGR)
            value = ctypes.c_int(color)
            dwm(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def pointer_inside(widget: Any) -> bool:
    """마우스가 아직 위젯(자식 포함) 위에 있는지 — Leave 이벤트에서 자식 이동을 걸러낸다."""
    try:
        x, y = widget.winfo_pointerxy()
        left, top = widget.winfo_rootx(), widget.winfo_rooty()
        return left <= x < left + widget.winfo_width() and top <= y < top + widget.winfo_height()
    except tk.TclError:
        return False


def btn(fg: str, hover: str, text: str) -> dict[str, Any]:
    """CTkButton 색·모양. 종이색 버튼은 선으로 경계를 준다."""
    style: dict[str, Any] = {
        "fg_color": fg, "hover_color": hover, "text_color": text, "corner_radius": 0,
    }
    if fg == PANEL:
        style.update(border_width=1, border_color=INK)
    elif fg == ROW:
        style.update(border_width=1, border_color=BORDER)
    return style


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
        # bg·테두리(highlight*)는 호출부가 덮어쓸 수 있다 — 칩/카드도 창 1개로
        kw.setdefault("bg", surface_color(master))
        kw.setdefault("bd", 0)
        kw.setdefault("padx", 0)
        kw.setdefault("highlightthickness", 0)
        super().__init__(
            master,
            text=text,
            font=scaled,
            fg=text_color or TEXT,
            wraplength=round(wraplength * self._scale),
            anchor=anchor,
            justify=justify,
            compound=compound,
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
            return round(self.winfo_pixels(super().cget(key)) / self._scale)
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
        if self.winfo_pixels(self.cget("pady")) != pady:
            self.configure(pady=pady)


_HEAD_SWAP = str.maketrans({"—": "-", "–": "-", "·": "/", "→": ">", "「": "'", "」": "'"})


def head_text(text: str) -> str:
    """제목 글꼴(Black Han Sans)에 없는 기호를 있는 것으로 바꾼다 (다른 글꼴이 섞여 보이지 않게)."""
    return text.translate(_HEAD_SWAP)


def section_heading(parent: Any, title: str, row: int) -> None:
    """먹색 네모 + 제목 섹션 헤더 (Tk 기본 위젯 3개 — CTk로는 7개)."""
    import customtkinter as ctk

    from lol_coach.gui.constants import FS

    head = tk.Frame(parent, bg=surface_color(parent), highlightthickness=0)
    head.grid(row=row, column=0, sticky="ew", padx=10, pady=(18, 6))
    side = round(13 * ctk.ScalingTracker.get_widget_scaling(parent))
    tk.Frame(head, width=side, height=side, bg=INK, highlightthickness=0).pack(
        side="left", padx=(0, round(side * 0.7))
    )
    TextLabel(head, text=head_text(title), font=FS, text_color=INK).pack(side="left")


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
    # 등급은 무게로 말한다 — S 먹 바탕, A 노랑, B·C 는 종이 농담
    return {
        "S": (INK, YELLOW),
        "A": (YELLOW, INK),
        "B": (ROW_HOVER, INK),
        "C": (ROW, TEXT_MUTE),
    }.get(key, (ROW, TEXT_MUTE))


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
    corner_radius: int = 0,
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
