"""ARAM Mayhem 코치 — offer-only 증강 판정, 카탈로그/abilities 연동 테스트."""

import pytest

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.blitz.models import BlitzError
from lol_coach.static.augment_catalog import AugmentCatalog
from lol_coach.static.blitz_aram import BlitzAramCatalog
from lol_coach.static.ddragon import DataDragon


@pytest.fixture
def coach() -> MayhemCoach:
    return MayhemCoach()


def test_advise_requires_offered_only(coach: MayhemCoach) -> None:
    """제시된 증강만 top/avoid에 들어가야 합니다."""
    adv = coach.advise(
        "Ahri",
        ["Jeweled Gauntlet", "Fey Magic", "Back To Basics", "Blade Waltz"],
    )
    offered_names = {"Jeweled Gauntlet", "Fey Magic", "Back To Basics", "Blade Waltz"}
    top_names = {p.name_en for p in adv.top_augments}
    avoid_names = {p.name_en for p in adv.avoid_augments}
    assert top_names <= offered_names
    assert avoid_names <= offered_names


def test_no_unoffered_recommendation(coach: MayhemCoach) -> None:
    """제시되지 않은 증강이 추천 목록에 절대 포함되지 않습니다."""
    adv = coach.advise("Ahri", ["Back To Basics"])
    assert len(adv.top_augments) <= 1
    assert all(p.name_en == "Back To Basics" for p in adv.top_augments)


def test_validation_unknown_and_duplicate(coach: MayhemCoach) -> None:
    """카탈로그에 없는 이름은 unknown, 중복은 duplicates로 보고됩니다."""
    adv = coach.advise(
        "Ahri",
        ["Jeweled Gauntlet", "보석 건틀릿", "unknown augment", "Fey Magic"],
    )
    assert "unknown augment" in adv.augment_validation.unknowns
    assert "보석 건틀릿" in adv.augment_validation.duplicates
    valid_ids = {r.id for r in adv.augment_validation.valid}
    assert "jeweled_gauntlet" in valid_ids
    assert "fey_magic" in valid_ids


def test_deterministic_order(coach: MayhemCoach) -> None:
    """동일 입력은 동일 순서를 반환합니다."""
    offered = ["Jeweled Gauntlet", "Fey Magic", "Back To Basics", "Blade Waltz"]
    a = coach.advise("Ahri", offered)
    b = coach.advise("Ahri", offered)
    assert [p.name_en for p in a.top_augments] == [p.name_en for p in b.top_augments]
    assert [p.name_en for p in a.avoid_augments] == [
        p.name_en for p in b.avoid_augments
    ]


def test_tips_invariants(coach: MayhemCoach) -> None:
    """팁은 3~5개, 2개 이상 스킬 참고, 1개 이상 제시 증강 언급."""
    adv = coach.advise(
        "Ahri",
        ["Jeweled Gauntlet", "Fey Magic", "Back To Basics", "Blade Waltz"],
    )
    assert 3 <= len(adv.play_tips) <= 5
    skill_refs = sum(1 for t in adv.play_tips if "쿨타임" in t or "활용" in t)
    assert skill_refs >= 2
    augment_refs = sum(
        1 for t in adv.play_tips if "추천 증강" in t or "주의" in t
    )
    assert augment_refs >= 1


def test_tips_have_no_generic_fallback_when_offered(coach: MayhemCoach) -> None:
    """증강이 제시된 경우 레거시 범용 문구는 남아 있지 않아야 합니다."""
    adv = coach.advise(
        "Ahri",
        ["Jeweled Gauntlet", "Fey Magic", "Back To Basics", "Blade Waltz"],
    )
    text = "\n".join(adv.play_tips)
    assert "'지금 한타에서 바로 세지는 것'" not in text
    assert "B티어·안 맞는 증강은 리롤" not in text


def test_source_info_visible(coach: MayhemCoach) -> None:
    """출처/패치/갱신일자가 노출됩니다."""
    adv = coach.advise("Ahri", ["Jeweled Gauntlet"])
    assert adv.source is not None
    assert "Blitz.gg" in adv.source.primary
    assert adv.source.primary_url == "https://blitz.gg/ko/lol/aram-mayhem-augments"
    assert adv.source.secondary_url == ""
    assert adv.source.patch
    assert adv.source.patch == "16.15"
    assert adv.source.updated_at


def test_build_fallback_labeled(coach: MayhemCoach) -> None:
    """Blitz 카탈로그에 없으면 빌드 정보 없음 안내와 함께 폴백을 반환합니다."""
    empty_blitz = BlitzAramCatalog(patch="16.15", updated_at="", records=())
    c = MayhemCoach(blitz=empty_blitz)
    adv = c.advise("Garen", [])
    assert adv.core_slots
    assert adv.build is not None
    assert adv.build_url == ""
    assert adv.top_augments
    assert any("전체 카탈로그 기준" in tip for tip in adv.play_tips)
    assert any("빌드 정보 없음" in tip for tip in adv.play_tips)


def test_blitz_build_used(coach: MayhemCoach) -> None:
    """Packaged Blitz 코어 순서가 빌드 정보로 사용됩니다."""
    expected = BlitzAramCatalog.packaged().get("Caitlyn")
    assert expected is not None
    adv = coach.advise("Caitlyn", [])

    assert adv.core_slots == [item.name_ko for item in expected.core_items[:5]]
    assert adv.build_url == expected.source_url
    assert adv.source is not None
    assert "Blitz.gg" in adv.source.primary


def test_champion_not_found(coach: MayhemCoach) -> None:
    with pytest.raises(BlitzError):
        coach.advise("NotAChampionXYZ", ["Jeweled Gauntlet"])


def test_resolve_offered_alias_and_korean(coach: MayhemCoach) -> None:
    """영문·한글·별칭을 모두 정규화해 동일 증강으로 처리합니다."""
    adv = coach.advise("Ahri", ["Jeweled Gauntlet", "보석 건틀릿"])
    assert len(adv.augment_validation.duplicates) == 1


def test_tank_avoid_glass_cannon(coach: MayhemCoach) -> None:
    """탱커에게 Glass Cannon은 회피로 잡혀야 합니다."""
    adv = coach.advise(
        "Garen",
        ["Goliath", "Glass Cannon", "Draw Your Sword", "Final Form", "Tank It Or Leave It", "Windspeaker's Blessing", "Blade Waltz"],
    )
    avoid_names = {p.name_en for p in adv.avoid_augments}
    assert "Glass Cannon" in avoid_names


def test_catalog_and_ddragon_apis_used() -> None:
    """카탈로그/ddragon public API가 모두 사용 가능합니다."""
    catalog = AugmentCatalog()
    rec = catalog.get_by_name("Jeweled Gauntlet")
    assert rec is not None
    assert rec.fallback_tier in {"S", "A", "B"}

    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    facts = dd.ability_facts("Ahri")
    assert facts["R"] is not None
    assert facts["R"]["cooldown"]
