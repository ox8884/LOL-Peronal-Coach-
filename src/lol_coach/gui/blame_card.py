"""팀운 정산 카드 PNG 렌더러 — 이 판 누구 탓 % (3분해 바)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from lol_coach.analysis.blame import BlameReport
from lol_coach.analysis.cardfont import card_font, wrap_text
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

_BARS = (
    ("나", "me_pct", GREEN),
    ("팀", "team_pct", "#6FA8DC"),
    ("상대", "enemy_pct", RED),
)


def _ellipsize(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def render_blame_card(report: BlameReport, *, champ_ko: str) -> Image.Image:
    """3분해 바 + 판정 한마디 카드."""
    title = "이 판 누구 탓" if report.is_loss else "이 판 승리 공신"
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    line_font = card_font(18)
    lines: list[str] = []
    for r in report.lines:
        lines.extend(wrap_text(probe, r, line_font, WIDTH - 120))

    height = 200 + 130 + len(lines) * 28 + 70
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

    draw.text((56, 50), title, font=card_font(36, bold=True), fill=TEXT)
    sub = _ellipsize(champ_ko, 24)
    draw.text(
        (56, 104),
        f"{sub} · {'패배' if report.is_loss else '승리'}",
        font=card_font(22, bold=True),
        fill=RED if report.is_loss else GREEN,
    )

    # 3분해 바
    y = 170
    for label, attr, color in _BARS:
        pct = getattr(report, attr)
        draw.text((56, y), label, font=card_font(24, bold=True), fill=TEXT)
        pct_txt = f"{pct}%"
        pct_w = draw.textlength(pct_txt, font=card_font(22, bold=True))
        draw.text((WIDTH - 56 - pct_w, y), pct_txt, font=card_font(22, bold=True), fill=color)
        y += 38
        bar_x, bar_w, bar_h = 56, WIDTH - 112, 20
        draw.rounded_rectangle(
            (bar_x, y, bar_x + bar_w, y + bar_h),
            radius=10,
            fill="#0F1620",
            outline=BORDER,
            width=2,
        )
        fill_w = int(bar_w * pct / 100)
        if fill_w > 4:
            draw.rounded_rectangle(
                (bar_x + 2, y + 2, bar_x + fill_w - 2, y + bar_h - 2),
                radius=8,
                fill=color,
            )
        y += 36

    # 판정 한마디
    y += 8
    verdict = report.verdict
    draw.text((56, y), "판정", font=card_font(24, bold=True), fill=GOLD)
    y += 40
    for line in wrap_text(probe, verdict, card_font(24, bold=True), WIDTH - 120):
        draw.text((56, y), line, font=card_font(24, bold=True), fill=TEXT)
        y += 34
    y += 8

    for line in lines:
        draw.text((56, y), line, font=line_font, fill=DIM)
        y += 28

    footer = "롤 실전 코치 · KDA + 데미지 비중 기반 상대 점수 분해"
    fw = draw.textlength(footer, font=card_font(16))
    draw.text(((WIDTH - fw) / 2, height - 50), footer, font=card_font(16), fill=DIM)
    return image


def blame_card_bytes(report: BlameReport, *, champ_ko: str) -> bytes:
    image = render_blame_card(report, champ_ko=champ_ko)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
