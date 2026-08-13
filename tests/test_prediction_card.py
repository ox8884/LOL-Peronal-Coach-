"""예측 카드·성적표 카드 렌더러 테스트."""

from __future__ import annotations

import time
from io import BytesIO

from PIL import Image

from lol_coach.analysis.prediction import Prediction
from lol_coach.gui.prediction_card import (
    prediction_card_bytes,
    receipt_card_bytes,
)


def _pred(prob: int = 58) -> Prediction:
    return Prediction(
        created_at_ms=int(time.time() * 1000),
        my_champ_id=103,
        ally_roster=(103, 1, 2, 3, 4),
        enemy_roster=(5, 6, 7, 8, 9),
        win_prob=prob,
        reasons=("앞라인 2명 우위", "내 최근 폼 핫 (최근 10판 승률 70%)"),
        sample_games=10,
        form_winrate=70.0,
    )


def _png_size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        return img.size


def test_prediction_card_valid_png() -> None:
    data = prediction_card_bytes(_pred(), champ_ko="오리아나", mode_label="ARAM Mayhem")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = _png_size(data)
    assert width == 960
    assert height > 400


def test_prediction_card_low_prob_renders() -> None:
    data = prediction_card_bytes(_pred(prob=30), champ_ko="아리", mode_label="ARAM")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_receipt_card_hit_and_miss() -> None:
    hit = receipt_card_bytes(
        _pred(prob=70), champ_ko="오리아나", mode_label="ARAM Mayhem",
        win=True, lesson="우세할 때는 한타 합류가 먼저다.",
    )
    miss = receipt_card_bytes(
        _pred(prob=70), champ_ko="오리아나", mode_label="ARAM Mayhem",
        win=False, lesson="다음 판은 앞라인과 붙어 다니자.",
    )
    assert hit[:8] == b"\x89PNG\r\n\x1a\n"
    assert miss[:8] == b"\x89PNG\r\n\x1a\n"
    # 적중/빗나감에 따라 높이가 비슷해야 함 (레이아웃 안정성)
    assert abs(_png_size(hit)[1] - _png_size(miss)[1]) <= 40


def test_receipt_card_colors(monkeypatch) -> None:
    from lol_coach.gui import prediction_card

    img = prediction_card.render_receipt_card(
        _pred(prob=70), champ_ko="아리", mode_label="ARAM", win=True, lesson="교훈"
    ).convert("RGB")
    w, h = img.size
    px = img.load()

    def near(c: tuple, t: tuple, tol: int = 40) -> bool:
        return all(abs(a - b) <= tol for a, b in zip(c, t, strict=False))

    green_hits = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if near(px[x, y], (76, 175, 125)):
                green_hits += 1
    assert green_hits > 0  # 적중 라벨/승률 색
