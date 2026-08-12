"""킬·데스 지도 이미지 합성 + 확대 팝업."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw, ImageFont

from lol_coach.analysis.killmap import KillMapData, game_to_pixel

BLUE = (56, 132, 255, 255)
RED = (230, 70, 70, 255)
WHITE = (255, 255, 255, 255)
DARK_BG = (22, 26, 34, 255)


def _number_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(13)
    except TypeError:  # Pillow < 10
        return ImageFont.load_default()


def _draw_marker(
    d: ImageDraw.ImageDraw,
    px: int,
    py: int,
    n: int,
    color: tuple[int, int, int, int],
    *,
    cross: bool,
) -> None:
    r = 13
    d.ellipse(
        [px - r, py - r, px + r, py + r],
        fill=(*color[:3], 70),
        outline=color,
        width=2,
    )
    if cross:
        d.line([px - 5, py - 5, px + 5, py + 5], fill=color, width=2)
        d.line([px - 5, py + 5, px + 5, py - 5], fill=color, width=2)
    font = _number_font()
    d.text((px + 9, py - 17), str(n), fill=WHITE, font=font)


def render_kill_minimap(
    data: KillMapData,
    base: Image.Image,
    size: int = 320,
) -> Image.Image:
    """내 킬(파랑 원+번호)·내 데스(빨강 X+번호)를 맵 위에 합성."""
    if base is None:
        img = Image.new("RGBA", (size, size), DARK_BG)
    else:
        img = base.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(img)
    for i, k in enumerate(data.my_deaths, 1):
        px, py = game_to_pixel(k.x, k.y, data.bounds, size)
        _draw_marker(d, px, py, i, RED, cross=True)
    for i, k in enumerate(data.my_kills, 1):
        px, py = game_to_pixel(k.x, k.y, data.bounds, size)
        _draw_marker(d, px, py, i, BLUE, cross=False)
    return img


def render_collapse_snapshot(
    data: KillMapData,
    base: Image.Image,
    size: int = 340,
) -> Image.Image | None:
    """붕괴 시점 10인 위치 — 챔피언 아이콘 원형 마커 (사망자는 어둡게)."""
    if data.collapse is None:
        return None
    from lol_coach.static.icons import champion_pil

    if base is None:
        img = Image.new("RGBA", (size, size), DARK_BG)
    else:
        img = base.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(img)
    icon_size = 26
    for p in data.collapse.players:
        px, py = game_to_pixel(p.x, p.y, data.bounds, size)
        ring = BLUE if p.team == data.my_team else RED
        d.ellipse(
            [px - 16, py - 16, px + 16, py + 16],
            fill=(*ring[:3], 60),
            outline=ring,
            width=2,
        )
        icon: Image.Image | None = None
        if p.champion_name:
            try:
                icon = champion_pil(p.champion_name, icon_size)
            except Exception:
                icon = None
        if icon is None:
            icon = Image.new("RGBA", (icon_size, icon_size), (*ring[:3], 200))
        icon = icon.convert("RGBA").resize(
            (icon_size, icon_size), Image.Resampling.LANCZOS
        )
        if not p.alive:
            icon = icon.convert("L").convert("RGBA")
            icon.putalpha(120)
        img.paste(icon, (px - icon_size // 2, py - icon_size // 2), icon)
    return img


def show_map_popup(
    parent: Any,
    *,
    minimap_img: Image.Image,
    snapshot_img: Image.Image | None = None,
    caption: str = "",
) -> None:
    """확대 지도 Toplevel — 이미 열려 있으면 닫고 새로 연다."""
    try:
        import customtkinter as ctk

        from lol_coach.gui.constants import FM
        from lol_coach.static.icons import to_ctk
    except Exception:
        return
    old = getattr(parent, "_killmap_popup", None)
    if old is not None:
        try:
            if old.winfo_exists():
                old.destroy()
        except Exception:
            pass
    win = ctk.CTkToplevel(parent)
    win.title("킬·데스 지도")
    parent._killmap_popup = win
    top = ctk.CTkFrame(win, fg_color="transparent")
    top.pack(fill="both", expand=True, padx=10, pady=10)

    keep = getattr(parent, "_keep_icon", lambda i: i)
    img1 = to_ctk(minimap_img, 520)
    if img1 is not None:
        lbl1 = ctk.CTkLabel(top, image=img1, text="")
        lbl1.pack(side="left", padx=(0, 10))
        keep(img1)
        ctk.CTkLabel(
            top,
            text="파랑: 내 킬 · 빨강 X: 내 데스 (번호 = 순서)",
            font=FM,
        ).pack(anchor="w", pady=(4, 0))
    if snapshot_img is not None:
        col = ctk.CTkFrame(top, fg_color="transparent")
        col.pack(side="left", fill="y")
        if caption:
            ctk.CTkLabel(col, text=caption, font=FM, wraplength=260).pack(
                anchor="w"
            )
        img2 = to_ctk(snapshot_img, 280)
        if img2 is not None:
            ctk.CTkLabel(col, image=img2, text="").pack(pady=(6, 0))
            keep(img2)
        ctk.CTkLabel(
            col,
            text="어두운 아이콘 = 교전 중 전사",
            font=FM,
        ).pack(anchor="w", pady=(4, 0))
