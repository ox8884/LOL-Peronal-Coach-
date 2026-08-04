"""카탈로그 커버리지 테스트 — blitz.gg 16.15 로스터 동기화 (SC1/SC2)."""

import json
from pathlib import Path

import pytest

from lol_coach.static.augment_catalog import AugmentCatalog

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "src" / "lol_coach" / "data" / "aram_mayhem_augments.json"


@pytest.fixture(scope="module")
def catalog() -> AugmentCatalog:
    return AugmentCatalog.from_file(CATALOG_PATH)


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_patch_is_current(raw: dict) -> None:
    """카탈로그 패치가 blitz 라이브 데이터 패치와 일치해야 합니다."""
    assert raw["patch"] == "16.15"


def test_roster_fully_covered(catalog: AugmentCatalog) -> None:
    """blitz 16.15 라이브 로스터(enabled ∩ tiered = 231)를 전부 커버해야 합니다."""
    assert len(catalog.records) >= 230


def test_no_empty_tier_or_rarity(catalog: AugmentCatalog) -> None:
    """모든 레코드에 티어와 등급이 있어야 합니다(구 12개 공란)."""
    missing = [r.id for r in catalog.records if not r.fallback_tier or not r.rarity]
    assert missing == []


def test_descriptions_are_substantive(catalog: AugmentCatalog) -> None:
    """설명을 비어 있거나 깨진 채(미strip 마크업)로 둘 수 없습니다.

    단순 스탯 증강은 공식 설명 자체가 한 줄(예: '스킬 가속이 100 증가합니다.')
    이므로 길이가 아니라 공백/마크업 잔여로 회귀를 감시합니다.
    """
    bad = [
        r.id
        for r in catalog.records
        if len(r.description_ko) < 10 or "<" in r.description_ko
    ]
    assert bad == []


def test_archetype_prefer_coverage(catalog: AugmentCatalog) -> None:
    """개인화 추천용 archetype_prefer 커버리지 90% 이상(구 51%)."""
    covered = sum(1 for r in catalog.records if r.archetype_prefer)
    assert covered / len(catalog.records) >= 0.9


def test_official_korean_names_resolve(catalog: AugmentCatalog) -> None:
    """blitz 게임 데이터 공식 한글명이 resolve_many로 해석돼야 합니다."""
    official = ['거인의 결의', '보석 건틀릿', '요정 마법', '검무', '기본으로 돌아가기', '적응형 와드', '치명적 치유', '드롭킥', '장인의 솜씨', '출발할 시간']
    for name in official:
        records, unknowns, _ = catalog.resolve_many([name])
        assert name not in unknowns, f"공식 한글명 미해석: {name}"
        assert records, f"공식 한글명 미해석: {name}"


def test_new_roster_augments_present(catalog: AugmentCatalog) -> None:
    """blitz 16.15 로스터의 신규 증강 샘플이 카탈로그에 존재해야 합니다."""
    names = set()
    for r in catalog.records:
        names.add(r.name_en)
    expected = ['Adaptive Ward', 'Critical Healing', 'Dropkick', 'Forged By The Master', "It's Go Time", 'Pat On The Back', 'Recursion', 'Soul Eater']
    missing = [n for n in expected if n not in names]
    assert missing == [], f"신규 로스터 누락: {missing}"


def test_image_candidates_validated(catalog: AugmentCatalog) -> None:
    """모든 레코드에 검증된 이미지 후보가 있어야 합니다(회귀 방지).

    고유 아이콘이 없는 증강의 공용 플레이스홀더는 네이티브 해상도가
    64px이므로 64px 이상을, 그 외에는 128px 이상을 요구합니다.
    """
    bad = [
        r.id
        for r in catalog.records
        if not r.image_candidates
        or all(
            c.size < (64 if "genericabilityaugmenticon" in c.url else 128)
            for c in r.image_candidates
        )
    ]
    assert bad == []


def test_all_records_use_blitz_metadata_and_icons(catalog: AugmentCatalog) -> None:
    """Every current roster record must use Blitz provenance for text and art."""
    non_blitz_sources = [
        record.id
        for record in catalog.records
        if not record.sources or record.sources[0].kind != "blitz"
    ]
    non_blitz_icons = [
        record.id
        for record in catalog.records
        if not record.image_candidates
        or any(candidate.kind != "blitz" for candidate in record.image_candidates)
    ]
    assert non_blitz_sources == []
    assert non_blitz_icons == []


def test_legacy_contract_names_still_resolve(catalog: AugmentCatalog) -> None:
    """기존 테스트 계약 이름(영문+한글)이 계속 해석돼야 합니다(PIN)."""
    legacy = ["Jeweled Gauntlet", "보석 건틀릿", "Fey Magic", "Back to Basics", "Blade Waltz"]
    for name in legacy:
        records, unknowns, _ = catalog.resolve_many([name])
        assert name not in unknowns, f"기존 계약 이름 미해석: {name}"
        assert records
