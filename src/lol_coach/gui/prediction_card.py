"""승패 예측 카드 + 예측 성적표 카드 PNG 렌더러.

게임 시작 시 예측 카드, 게임 종료 시 성적표(예측 vs 결과) 카드.
GUI 위젯에 의존하지 않는 순수 PIL 합성 (워커 스레드 안전).
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from lol_coach.analysis.cardfont import card_font, wrap_text
from lol_coach.analysis.prediction import Prediction
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


def _ellipsize(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _header(draw: ImageDraw.ImageDraw, title: str, sub: str) -> None:
    draw.text((56, 50), title, font=card_font(36, bold=True), fill=TEXT)
    draw.text((56, 104), sub, font=card_font(22, bold=True), fill=GOLD)


def _canvas(title: str, sub: str, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
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
    _header(draw, title, sub)
    return image, draw


def _footer(draw: ImageDraw.ImageDraw, height: int, text: str) -> None:
    w = draw.textlength(text, font=card_font(16))
    draw.text(((WIDTH - w) / 2, height - 50), text, font=card_font(16), fill=DIM)


def render_prediction_card(
    pred: Prediction,
    *,
    champ_ko: str,
    mode_label: str,
) -> Image.Image:
    """게임 시작 — 승률 예측 카드."""
    prob = max(0, min(100, pred.win_prob))
    reason_font = card_font(18)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    reason_lines: list[str] = []
    for r in pred.reasons[:3]:
        reason_lines.extend(wrap_text(probe, r, reason_font, WIDTH - 120))

    height = 200 + 150 + len(reason_lines) * 28 + 70
    image, draw = _canvas(
        "승패 예측",
        f"{_ellipsize(champ_ko, 24)} · {_ellipsize(mode_label, 20)}",
        height,
    )

    # 승률 숫자 + 바
    big = card_font(64, bold=True)
    draw.text((56, 180), f"{prob}%", font=big, fill=GREEN if prob >= 50 else RED)
    label = "승리 예상" if prob >= 50 else "패배 예상"
    draw.text((56, 268), label, font=card_font(20), fill=DIM)

    bar_x, bar_y, bar_w, bar_h = 56, 320, WIDTH - 112, 26
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
        radius=13,
        fill="#0F1620",
        outline=BORDER,
        width=2,
    )
    fill_w = int(bar_w * prob / 100)
    if fill_w > 6:
        color = GREEN if prob >= 50 else RED
        draw.rounded_rectangle(
            (bar_x + 2, bar_y + 2, bar_x + fill_w - 2, bar_y + bar_h - 2),
            radius=11,
            fill=color,
        )

    y = 380
    draw.text((56, y), "근거", font=card_font(24, bold=True), fill=GOLD)
    y += 40
    for line in reason_lines:
        draw.text((56, y), line, font=reason_font, fill=BODY)
        y += 28

    _footer(draw, height, "롤 실전 코치 · 조합 + 내 폼 기반 결정적 계산")
    return image


def render_receipt_card(
    pred: Prediction,
    *,
    champ_ko: str,
    mode_label: str,
    win: bool,
    lesson: str,
) -> Image.Image:
    """게임 종료 — 예측 vs 결과 성적표 카드."""
    prob = max(0, min(100, pred.win_prob))
    predicted_win = prob >= 50
    hit = predicted_win == win

    reason_font = card_font(18)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    reason_lines: list[str] = []
    for r in pred.reasons[:2]:
        reason_lines.extend(wrap_text(probe, r, reason_font, WIDTH - 120))
    lesson_lines = wrap_text(
        probe,
        lesson or "오늘의 한 판에서 얻은 것 하나를 기록하세요.",
        card_font(20),
        WIDTH - 120,
    )

    height = 200 + 120 + len(reason_lines) * 28 + 40 + len(lesson_lines) * 30 + 100
    image, draw = _canvas(
        "예측 성적표",
        f"{_ellipsize(champ_ko, 24)} · {_ellipsize(mode_label, 20)}",
        height,
    )

    # 예측 vs 결과
    draw.text((56, 180), f"예측 {prob}%", font=card_font(34, bold=True), fill=BODY)
    result_text = "승리" if win else "패배"
    result_color = GREEN if win else RED
    draw.text(
        (56, 232),
        f"결과 {result_text}",
        font=card_font(34, bold=True),
        fill=result_color,
    )
    verdict = "✓ 적중" if hit else "✗ 빗나감"
    v_color = GREEN if hit else RED
    v_font = card_font(40, bold=True)
    v_w = draw.textlength(verdict, font=v_font)
    draw.rounded_rectangle(
        (WIDTH - 56 - v_w - 48, 190, WIDTH - 56, 246),
        radius=14,
        fill="#0F1620",
        outline=v_color,
        width=2,
    )
    draw.text((WIDTH - 56 - v_w - 24, 198), verdict, font=v_font, fill=v_color)

    y = 300
    if reason_lines:
        draw.text((56, y), "예측 근거", font=card_font(24, bold=True), fill=GOLD)
        y += 40
        for line in reason_lines:
            draw.text((56, y), line, font=reason_font, fill=BODY)
            y += 28
        y += 12

    draw.text((56, y), "이 판 한마디", font=card_font(24, bold=True), fill=GOLD)
    y += 40
    for line in lesson_lines:
        draw.text((56, y), line, font=card_font(20), fill=TEXT)
        y += 30

    _footer(draw, height, "롤 실전 코치 · 예측 성적표")
    return image


def prediction_card_bytes(
    pred: Prediction,
    *,
    champ_ko: str,
    mode_label: str,
) -> bytes:
    image = render_prediction_card(pred, champ_ko=champ_ko, mode_label=mode_label)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def receipt_card_bytes(
    pred: Prediction,
    *,
    champ_ko: str,
    mode_label: str,
    win: bool,
    lesson: str,
) -> bytes:
    image = render_receipt_card(
        pred, champ_ko=champ_ko, mode_label=mode_label, win=win, lesson=lesson
    )
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
