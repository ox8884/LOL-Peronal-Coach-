"""아수라장 증강 실시간 판정 카드 PNG 렌더러.

LCU가 제시 증강 목록을 읽는 순간 호출된다. 제시된 증강 중
1~3순위와 회피 목록을 한 장의 카드로 합성해 디스코드로 보낸다.
GUI 위젯에 의존하지 않는 순수 PIL 합성 (워커 스레드 안전).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from lol_coach.analysis.aram_mayhem import MayhemAdvice
from lol_coach.analysis.cardfont import card_font, wrap_text
from lol_coach.gui.review_card import (
    BG,
    BODY,
    BORDER,
    DIM,
    GOLD,
    GREEN,
    PANEL,
    RED,
    TEXT,
)

WIDTH = 960

_RANK_LABEL = {0: "1순위 선택", 1: "2순위", 2: "3순위"}
_RANK_COLOR = {0: GREEN, 1: "#6FA8DC", 2: BODY}
_RARITY_KO = {"prismatic": "프리즘", "gold": "골드", "silver": "실버"}


def _rarity_ko(rarity: str) -> str:
    return _RARITY_KO.get((rarity or "").lower(), rarity or "기타")


def _ellipsize(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def render_augment_card(advice: MayhemAdvice) -> Image.Image:
    """제시 증강 판정 카드 합성 — 1~3순위 + 회피 + 패치 정보."""
    champ = _ellipsize(advice.champ_ko or "?", 20)
    patch = _ellipsize(advice.patch or "", 16)
    tops = list(advice.top_augments[:3])
    avoids = list(advice.avoid_augments[:2])

    title_font = card_font(36, bold=True)
    name_font = card_font(24, bold=True)
    body_font = card_font(18)
    reason_font = card_font(16)

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rows_h = 0
    for _i, pick in enumerate(tops):
        desc_w = wrap_text(probe, pick.desc, body_font, WIDTH - 260)
        reason_w = wrap_text(probe, pick.reason, reason_font, WIDTH - 260)
        rows_h += 36 + len(desc_w) * 26 + (len(reason_w) * 24 if reason_w else 0) + 24
    if not tops:
        rows_h = 90
    avoid_h = 0
    if avoids:
        avoid_h = 30
        for pick in avoids:
            reason_w = wrap_text(probe, pick.reason, reason_font, WIDTH - 260)
            avoid_h += 28 + (len(reason_w) * 24 if reason_w else 0) + 16

    height = 190 + rows_h + avoid_h + 70
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

    # 헤더
    draw.text((56, 50), "아수라장 증강 판정", font=title_font, fill=TEXT)
    sub = f"{champ}"
    if patch:
        sub += f" · 패치 {patch}"
    draw.text((56, 104), sub, font=card_font(22, bold=True), fill=GOLD)

    y = 158
    if tops:
        for i, pick in enumerate(tops):
            rank = _RANK_LABEL[i]
            color = _RANK_COLOR[i]
            draw.text((56, y), rank, font=name_font, fill=color)
            chip = f"{_rarity_ko(pick.rarity)}"
            if pick.tier:
                chip += f" · {pick.tier}"
            chip_w = draw.textlength(chip, font=reason_font) + 16
            draw.rounded_rectangle(
                (WIDTH - 56 - chip_w, y + 4, WIDTH - 56, y + 28),
                radius=12,
                fill="#0F1620",
                outline=GOLD,
                width=1,
            )
            draw.text(
                (WIDTH - 56 - chip_w + 8, y + 8),
                chip,
                font=reason_font,
                fill=GOLD,
            )
            y += 38
            draw.text(
                (56, y),
                _ellipsize(pick.name_ko, 30),
                font=name_font,
                fill=TEXT,
            )
            y += 34
            for line in wrap_text(probe, pick.desc, body_font, WIDTH - 260)[:2]:
                draw.text((56, y), line, font=body_font, fill=BODY)
                y += 26
            for line in wrap_text(probe, pick.reason, reason_font, WIDTH - 260)[:2]:
                draw.text((56, y), line, font=reason_font, fill=DIM)
                y += 24
            y += 22
    else:
        draw.text(
            (56, y + 20),
            "제시된 증강을 판정할 데이터가 없습니다.",
            font=body_font,
            fill=DIM,
        )

    if avoids:
        y += 8
        draw.text((56, y), "⚠️ 회피 권장", font=name_font, fill=RED)
        y += 34
        for pick in avoids:
            line = f"{_ellipsize(pick.name_ko, 24)} — {_ellipsize(pick.reason, 60)}"
            for wrapped in wrap_text(probe, line, reason_font, WIDTH - 260)[:2]:
                draw.text((56, y), wrapped, font=reason_font, fill="#E0A94F")
                y += 24
            y += 14

    footer = "롤 실전 코치 · LCU 제시 증강 실시간 판정"
    footer_w = draw.textlength(footer, font=card_font(16))
    draw.text(
        ((WIDTH - footer_w) / 2, height - 50),
        footer,
        font=card_font(16),
        fill=DIM,
    )
    return image


def augment_card_bytes(advice: MayhemAdvice) -> bytes:
    """판정 카드 → PNG 바이트."""
    image = render_augment_card(advice)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
