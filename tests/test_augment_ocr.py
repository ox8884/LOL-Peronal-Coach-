from types import SimpleNamespace

from lol_coach.analysis.augment_ocr import (
    active_player_level,
    is_augment_level,
    match_catalog_names,
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


def test_active_player_level_and_thresholds() -> None:
    assert active_player_level({}) == 0
    assert active_player_level({"activePlayer": {"level": 7}}) == 7
    assert is_augment_level(3) is True
    assert is_augment_level(4) is False
