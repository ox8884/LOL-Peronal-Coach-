from types import SimpleNamespace

from lol_coach.analysis.augment_ocr import (
    OcrLine,
    active_player_level,
    image_is_blank,
    is_augment_level,
    match_catalog_names,
    parse_ocr_payload,
    pick_offered_from_lines,
)


def test_match_catalog_names_picks_longest_hits() -> None:
    records = [
        SimpleNamespace(id="a", name_ko="보석 건틀릿", name_en="Jeweled Gauntlet", aliases=()),
        SimpleNamespace(id="b", name_ko="기본으로", name_en="Back to Basics", aliases=()),
        SimpleNamespace(id="c", name_ko="칼날 왈츠", name_en="Blade Waltz", aliases=()),
        SimpleNamespace(id="d", name_ko="무관", name_en="XX", aliases=()),
    ]
    text = "보석 건틀릿\n기본으로\n칼날 왈츠"
    assert match_catalog_names(text, records) == ["보석 건틀릿", "기본으로", "칼날 왈츠"]


def test_match_catalog_names_ignores_short_noise() -> None:
    records = [SimpleNamespace(id="a", name_ko="은", name_en="Ag", aliases=())]
    assert match_catalog_names("은은한 빛", records) == []


def test_pick_offered_from_lines_uses_three_columns() -> None:
    records = [
        SimpleNamespace(id="a", name_ko="보석 건틀릿", name_en="Jeweled Gauntlet", aliases=()),
        SimpleNamespace(id="b", name_ko="기본으로", name_en="Back to Basics", aliases=()),
        SimpleNamespace(id="c", name_ko="칼날 왈츠", name_en="Blade Waltz", aliases=()),
    ]
    lines = [
        OcrLine("보석 건틀릿", x=40, y=80, w=120, h=28),
        OcrLine("기본으로", x=300, y=82, w=110, h=27),
        OcrLine("칼날 왈츠", x=560, y=79, w=130, h=29),
    ]
    assert pick_offered_from_lines(lines, records, width=720) == [
        "보석 건틀릿",
        "기본으로",
        "칼날 왈츠",
    ]


def test_pick_offered_ignores_stacked_app_board() -> None:
    """앱 실버 TOP 3처럼 한 열에 쌓인 이름은 한 장만 나온다."""
    records = [
        SimpleNamespace(id="a", name_ko="보석 건틀릿", name_en="Jeweled Gauntlet", aliases=()),
        SimpleNamespace(id="b", name_ko="기본으로", name_en="Back to Basics", aliases=()),
        SimpleNamespace(id="c", name_ko="칼날 왈츠", name_en="Blade Waltz", aliases=()),
    ]
    lines = [
        OcrLine("실버 TOP 3", x=520, y=40, w=140, h=16),
        OcrLine("1. 보석 건틀릿", x=520, y=70, w=160, h=18),
        OcrLine("2. 기본으로", x=520, y=96, w=150, h=18),
        OcrLine("3. 칼날 왈츠", x=520, y=122, w=150, h=18),
    ]
    assert pick_offered_from_lines(lines, records, width=720) == ["보석 건틀릿"]


def test_parse_ocr_payload_json_and_plain() -> None:
    text, lines = parse_ocr_payload(
        '{"text":"보석 건틀릿","lines":[{"t":"보석 건틀릿","x":10,"y":20,"w":80,"h":16}]}'
    )
    assert text == "보석 건틀릿"
    assert len(lines) == 1
    assert lines[0].h == 16
    plain, plain_lines = parse_ocr_payload("보석 건틀릿")
    assert plain == "보석 건틀릿"
    assert plain_lines[0].text == "보석 건틀릿"


def test_image_is_blank_detects_black_and_keeps_content() -> None:
    from PIL import Image

    black = Image.new("RGB", (200, 120), (0, 0, 0))
    content = Image.new("RGB", (200, 120), (20, 20, 20))
    for x in range(20, 180):
        content.putpixel((x, 60), (220, 210, 80))
    assert image_is_blank(black) is True
    assert image_is_blank(content) is False


def test_active_player_level_and_thresholds() -> None:
    assert active_player_level({}) == 0
    assert active_player_level({"activePlayer": {"level": 7}}) == 7
    assert is_augment_level(3) is True
    assert is_augment_level(4) is False
