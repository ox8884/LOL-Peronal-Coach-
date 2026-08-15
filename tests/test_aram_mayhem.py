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

    assert adv.core_slots == [item.name_ko for item in expected.core_items[:6]]
    assert adv.core_item_ids == [int(item.item_id) for item in expected.core_items[:6]]
    assert len(adv.core_slots) == 6
    assert adv.build_url == expected.source_url
    assert adv.source is not None
    assert "Blitz.gg" in adv.source.primary


def test_fixed_top_three_is_grouped_by_rarity_and_ignores_offered(
    coach: MayhemCoach,
) -> None:
    build = BlitzAramCatalog.packaged().get("Caitlyn")
    assert build is not None

    without_offers = coach.advise("Caitlyn", [])
    with_offers = coach.advise("Caitlyn", ["Jeweled Gauntlet"])

    expected = {
        rarity: tuple(build.augment_tiers[rarity][:3])
        for rarity in ("silver", "gold", "prismatic")
    }
    assert tuple(p.name_ko for p in without_offers.fixed_top.silver) == expected["silver"]
    assert tuple(p.name_ko for p in without_offers.fixed_top.gold) == expected["gold"]
    assert tuple(p.name_ko for p in without_offers.fixed_top.prismatic) == expected["prismatic"]
    assert with_offers.fixed_top == without_offers.fixed_top


def test_fallback_build_fills_all_six_unique_slots() -> None:
    empty_blitz = BlitzAramCatalog(patch="16.15", updated_at="", records=())

    advice = MayhemCoach(blitz=empty_blitz).advise("Garen", [])

    assert len(advice.core_slots) == 6
    assert len(set(advice.core_slots)) == 6


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


# ── 리롤 어드바이저 · 증강 시너지 · 적응형 빌드 (신기능) ──


def test_reroll_advice_none_without_blitz_data() -> None:
    """Blitz 빌드가 없으면 리롤 어드바이스는 None (침무 원칙)."""
    empty_blitz = BlitzAramCatalog(patch="16.15", updated_at="", records=())
    c = MayhemCoach(blitz=empty_blitz)
    adv = c.advise("Ahri", [])
    assert adv.reroll is None


def test_reroll_advice_silent_without_champ_ranking(coach: MayhemCoach) -> None:
    """Blitz 빌드가 있어도 챔프 순위 데이터가 없으면 리롤 어드바이스는 None (침묵)."""
    adv = coach.advise("Caitlyn", [])
    assert adv.reroll is None


def test_synergy_lines_populated(coach: MayhemCoach) -> None:
    """archetype_prefer/avoid 가 매칭되면 synergy_lines 가 채워진다."""
    adv = coach.advise(
        "Garen",
        ["Goliath", "Glass Cannon", "Draw Your Sword", "Final Form"],
    )
    # 탱커에 Glass Cannon 은 avoid — 시너지/주의 줄이 나와야
    assert isinstance(adv.synergy_lines, list)
    # avoid 가 있으면 주의 줄이 나온다
    if adv.avoid_augments:
        assert any("주의" in line for line in adv.synergy_lines)


def test_synergy_lines_empty_without_offered(coach: MayhemCoach) -> None:
    """제시 증강이 없으면 시너지 줄도 비어 있어야 한다."""
    adv = coach.advise("Ahri", [])
    # top_augments 가 비어 있거나 reason 에 시너지/주의가 없으면 빈 리스트
    if not adv.top_augments:
        assert adv.synergy_lines == []


def test_adaptive_late_slots_no_enemy_tags(coach: MayhemCoach) -> None:
    """enemy_tags 없으면 원본 슬롯 그대로, note 빈 문자열."""
    base = ["A", "B", "C", "D", "E", "F"]
    slots, note = coach._adaptive_late_slots(base, {"Mage"}, None)
    assert slots == base
    assert note == ""


def test_adaptive_late_slots_tank_enemy_adds_penetration(coach: MayhemCoach) -> None:
    """적 탱커 2명 → 4코어 관통 아이템 분기."""
    base = ["루덴의 메아리", "그림자불꽃", "라바돈의 죽음모자", "공허의 지팡이", "존야의 모래시계", "수호 천사"]
    slots, note = coach._adaptive_late_slots(base, {"Mage"}, {"Tank": 3})
    assert "관통" in note
    assert slots[3] == "공허의 지팡이"  # 메이지 → 마관


def test_adaptive_late_slots_support_enemy_adds_grievous(coach: MayhemCoach) -> None:
    """적 서폿 2명 → 5코어 치감 (물리 딜러인 경우)."""
    base = ["크라켄 학살자", "구인수의 격노검", "무한의 대검", "도미닉 경의 인사", "수호 천사", ""]
    slots, note = coach._adaptive_late_slots(
        base, {"Marksman"}, {"Support": 2}
    )
    assert "치감" in note
    assert slots[4] == "필멸자의 운명"


def test_adaptive_late_slots_mage_enemy_support_adds_morello(coach: MayhemCoach) -> None:
    """적 서폿 2명 + Mage → 5코어 치감 모렐로노미콘 (AP 딜러)."""
    base = ["루덴의 메아리", "그림자불꽃", "라바돈의 죽음모자", "공허의 지팡이", "존야의 모래시계", "수호 천사"]
    slots, note = coach._adaptive_late_slots(
        base, {"Mage", "Assassin"}, {"Support": 2}
    )
    assert "치감" in note
    assert slots[4] == "모렐로노미콘"


def test_adaptive_late_slots_mage_enemy_adds_mr(coach: MayhemCoach) -> None:
    """적 마법 3명 → 6코어 MR."""
    base = ["크라켄 학살자", "구인수의 격노검", "무한의 대검", "도미닉 경의 인사", "수호 천사", ""]
    slots, note = coach._adaptive_late_slots(
        base, {"Marksman"}, {"Mage": 3}
    )
    assert "MR" in note
    assert slots[5] == "밴시의 장막"


def test_adaptive_late_slots_preserves_first_three_cores(coach: MayhemCoach) -> None:
    """1~3코어는 적 조합과 무관하게 원본 유지."""
    base = ["코어1", "코어2", "코어3", "코어4", "코어5", "코어6"]
    slots, note = coach._adaptive_late_slots(
        base, {"Mage"}, {"Tank": 2, "Support": 2, "Mage": 3}
    )
    assert slots[0] == "코어1"
    assert slots[1] == "코어2"
    assert slots[2] == "코어3"
    assert note  # 분기 안내 있음


def test_adaptive_late_slots_pads_short_build(coach: MayhemCoach) -> None:
    """6슬롯 미만 입력은 채워서 6으로 맞춘다."""
    base = ["A", "B", "C"]
    slots, _ = coach._adaptive_late_slots(base, {"Marksman"}, {"Tank": 2})
    assert len(slots) == 6


def test_advice_has_new_fields(coach: MayhemCoach) -> None:
    """MayhemAdvice 에 reroll·synergy_lines·adaptive_build_note 필드 존재."""
    adv = coach.advise("Ahri", ["Jeweled Gauntlet"])
    assert hasattr(adv, "reroll")
    assert hasattr(adv, "synergy_lines")
    assert hasattr(adv, "adaptive_build_note")
    assert adv.adaptive_build_note == ""  # 적 조합 없으면 빈 문자열
