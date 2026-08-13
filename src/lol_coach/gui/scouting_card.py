"""10인 정찰 카드 PNG 렌더러 — 리드 칩 요약 (디스코드 전송용)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from lol_coach.analysis.cardfont import card_font, wrap_text
from lol_coach.analysis.scouting import ScoutingReport
from lol_coach.gui.review_card import (
    BG,
    BORDER,
    DIM,
    GOLD,
    GREEN,
    PANEL,
    RED,
    TEXT,
)

WIDTH = 960

_KIND_COLOR = {
    "danger": RED,
    "warn": "#E0A94F",
    "hot": GREEN,
    "cold": "#6FA8DC",
    "info": DIM,
}
_KIND_LABEL = {"danger": "위험", "warn": "주의", "hot": "핫", "cold": "콜드", "info": ""}


def _ellipsize(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _champ_ko(dd, champion_id: int) -> str:
    try:
        return dd.champion_name(int(champion_id)) or "?"
    except Exception:
        return "?"


def render_scouting_card(report: ScoutingReport, dd) -> Image.Image:
    """적 우선 리드 칩 카드."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    name_font = card_font(24, bold=True)
    chip_font = card_font(18)

    rows: list[tuple[str, tuple]] = []
    for side_label, scouts in (("적", report.enemy), ("아군", report.ally)):
        for s in scouts:
            header = (
                f"{side_label} · {_champ_ko(dd, s.champion_id)} ({_ellipsize(s.summoner_name, 16)})"
            )
            rows.append((header, s.chips))

    content_h = 0
    for _h, chips in rows:
        content_h += 40
        if chips:
            content_h += len(chips) * 28 + 6
        else:
            content_h += 26
    height = 190 + content_h + 70
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (24, 24, WIDTH - 24, height - 24),
        radius=28,
        fill=PANEL,
        outline=BORDER,
        width=2,
    )
    draw.rectangle((24, 24, 38, height - 24), fill=GOLD)

    draw.text((56, 50), "10인 정찰 — 리드 칩", font=card_font(36, bold=True), fill=TEXT)
    draw.text(
        (56, 104),
        f"정찰 {report.scanned}명 · 건너뜀 {report.skipped}명",
        font=card_font(20),
        fill=DIM,
    )

    y = 160
    for header, chips in rows:
        draw.rectangle((56, y + 6, 60, y + 30), fill=GOLD)
        draw.text((72, y), header, font=name_font, fill=TEXT)
        y += 40
        if chips:
            for chip in chips:
                color = _KIND_COLOR.get(chip.kind, DIM)
                label = _KIND_LABEL.get(chip.kind, "")
                prefix = f"[{label}] " if label else ""
                for line in wrap_text(probe, prefix + chip.text, chip_font, WIDTH - 130):
                    draw.text((72, y), line, font=chip_font, fill=color)
                    y += 28
            y += 6
        else:
            draw.text((72, y), "표본 부족 — 말할 것 없음", font=chip_font, fill=DIM)
            y += 26

    footer = "롤 실전 코치 · 최근 5판 기준 결정적 계산 · 표본 3판 미만 침묵"
    fw = draw.textlength(footer, font=card_font(16))
    draw.text(((WIDTH - fw) / 2, height - 50), footer, font=card_font(16), fill=DIM)
    return image


def scouting_card_bytes(report: ScoutingReport, dd) -> bytes:
    image = render_scouting_card(report, dd)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
