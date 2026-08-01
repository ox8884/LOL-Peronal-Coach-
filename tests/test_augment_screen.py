"""증강 화면 인식 — 합성 이미지 매칭 테스트 (numpy 필요, mss 불요)."""

import pytest

np = pytest.importorskip("numpy")
from PIL import Image  # noqa: E402 — numpy skip 이후 import 의도적 지연

from lol_coach.analysis.augment_screen import match_augments  # noqa: E402


def _icon(color: tuple[int, int, int], inner: tuple[int, int, int]) -> Image.Image:
    """뚜렷한 2색 패턴의 가짜 증강 아이콘."""
    img = Image.new("RGB", (48, 48), color)
    # 중앙 4분면을 다른 색으로 — 아이콘마다 고유 패턴
    for y in range(12, 36):
        for x in range(12, 36):
            img.putpixel((x, y), inner)
    return img


def _dark_screen(w: int = 800, h: int = 500) -> Image.Image:
    img = Image.new("RGB", (w, h), (18, 20, 24))
    # 노이즈성 배경 블록 (오탐 유도용)
    for y in range(0, h, 40):
        for x in range(0, w, 40):
            shade = 20 + (x * 7 + y * 3) % 25
            for dy in range(min(38, h - y)):
                for dx in range(min(38, w - x)):
                    img.putpixel((x + dx, y + dy), (shade, shade, shade + 4))
    return img


def test_match_finds_pasted_icons() -> None:
    icon_a = _icon((200, 60, 40), (250, 200, 60))
    icon_b = _icon((60, 90, 210), (140, 230, 250))
    icon_c = _icon((90, 200, 90), (240, 250, 240))

    screen = _dark_screen()
    screen.paste(icon_a.resize((72, 72)), (120, 200))
    screen.paste(icon_b.resize((72, 72)), (320, 200))

    templates = {"AugA": icon_a, "AugB": icon_b, "AugC": icon_c}
    hits = match_augments(screen, templates, threshold=0.90, box_sizes=(72,))

    names = [h.name for h in hits]
    assert "AugA" in names
    assert "AugB" in names
    assert "AugC" not in names

    # 위치가 대략 맞아야 함
    ha = next(h for h in hits if h.name == "AugA")
    assert abs(ha.box[0] - 120) <= 12
    assert abs(ha.box[1] - 200) <= 12


def test_match_empty_templates() -> None:
    assert match_augments(_dark_screen(), {}) == []


def test_match_no_false_positive_on_blank() -> None:
    icon_a = _icon((200, 60, 40), (250, 200, 60))
    hits = match_augments(
        _dark_screen(), {"AugA": icon_a}, threshold=0.95, box_sizes=(72,)
    )
    assert hits == []
