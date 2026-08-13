"""디스코드 복기 카드 렌더러 테스트 — 순수 PIL 합성 검증."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from lol_coach.analysis.review import MatchReview
from lol_coach.gui.review_card import render_review_card, review_card_bytes
from lol_coach.riot.models import MatchSummary


def _sample_match(**overrides: object) -> MatchSummary:
    kwargs: dict[str, object] = {
        "match_id": "KR_000000001",
        "champion_name": "Ahri",
        "champion_id": 103,
        "role": "MIDDLE",
        "lane": "MID",
        "win": True,
        "kills": 9,
        "deaths": 3,
        "assists": 12,
        "cs": 140,
        "gold": 11500,
        "damage_to_champs": 26000,
        "vision_score": 8,
        "game_duration_s": 1290,
        "queue_id": 450,
        "game_mode": "aram",
    }
    kwargs.update(overrides)
    return MatchSummary(**kwargs)  # type: ignore[arg-type]


def _sample_review() -> MatchReview:
    return MatchReview(
        win_loss_reasons=[
            "한타마다 궁극기로 상대 딜러를 먼저 묶었다",
            "상대 앞라인이 무너진 타이밍에 바로 밀어붙였다",
        ],
        good=["포킹 각을 잘 잡아 21분 전까지 무력화", "데스 3회로 생존 관리 안정적"],
        improve=["아이템 3코어 이후 존야 타이밍이 늦었다"],
        lesson="우세할 때는 탑 포탑보다 한타 합류가 먼저다.",
    )


def _png_size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        return img.size


def test_review_card_bytes_is_valid_png() -> None:
    data = review_card_bytes(_sample_match(), _sample_review())
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = _png_size(data)
    assert width == 1080
    assert height > 400


def test_review_card_with_minimap_and_collapse() -> None:
    minimap = Image.new("RGB", (320, 320), "#101820")
    collapse = Image.new("RGB", (300, 300), "#182330")
    image = render_review_card(
        _sample_match(),
        _sample_review(),
        minimap=minimap,
        collapse=collapse,
        collapse_caption="12분 30초 — 아군 3킬 붕괴",
    )
    assert image.size[0] == 1080
    # 붕괴 스냅샷이 있으면 카드가 더 길어진다
    assert image.size[1] > 700


def test_review_card_empty_review_fallbacks() -> None:
    data = review_card_bytes(
        _sample_match(),
        MatchReview(win_loss_reasons=[], good=[], improve=[], lesson=""),
    )
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_review_card_loss_renders() -> None:
    data = review_card_bytes(
        _sample_match(win=False, kills=1, deaths=8, assists=2),
        _sample_review(),
    )
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_sample_card_bytes_is_valid_png() -> None:
    from lol_coach.gui.review_card import sample_card_bytes

    data = sample_card_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = _png_size(data)
    assert width == 1080 and height > 300
