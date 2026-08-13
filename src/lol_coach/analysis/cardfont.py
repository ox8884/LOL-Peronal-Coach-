"""카드 PNG 렌더 공용 헬퍼 — 한글 폰트 · 너비 기준 줄바꿈 (tkinter 의존 없음).

성장 카드(growth.py)와 디스코드 복기 카드(gui/review_card.py)가
같은 폰트 규칙을 쓰도록 단일 출처를 유지한다.
"""

from __future__ import annotations

from PIL import ImageDraw, ImageFont

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/malgunbd.ttf",  # bold — 맑은 고딕 Bold
    "C:/Windows/Fonts/malgun.ttf",  # regular — 맑은 고딕
    "arial.ttf",
)


def card_font(
    size: int,
    *,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """한국어 렌더 가능 폰트를 순서대로 시도하고, 없으면 기본 폰트."""
    candidates = _FONT_CANDIDATES if bold else (_FONT_CANDIDATES[1], _FONT_CANDIDATES[2])
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """픽셀 너비 기준 줄바꿈 — 공백 우선, 없으면 문자 단위 분할."""
    if not text:
        return [""]
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        current = ""
        for ch in raw:
            if draw.textlength(current + ch, font=font) > max_width and current:
                # 공백 우선 분할 — 단어 중간에서 끊기지 않게 최근 공백 탐색
                space = current.rfind(" ")
                if space > len(current) - 10 and space > 0:
                    lines.append(current[:space])
                    current = current[space + 1 :]
                else:
                    lines.append(current)
                    current = ""
            current += ch
        if current:
            lines.append(current)
    return lines
