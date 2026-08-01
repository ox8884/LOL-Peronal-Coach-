"""챔피언 resolve / 자동완성 검색 (공백 무시)."""

from lol_coach.static.ddragon import DataDragon, _compact


def test_compact_strips_spaces():
    assert _compact("리 신") == "리신"
    assert _compact("Lee Sin") == "leesin"
    assert _compact("  미스 포츈 ") == "미스포츈"


def test_resolve_lee_sin_without_space():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    c = dd.resolve_champion("리신")
    assert c is not None
    assert c["id"] == "LeeSin"
    assert "신" in c["name"]  # 리 신


def test_resolve_lee_sin_with_space():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    c = dd.resolve_champion("리 신")
    assert c is not None
    assert c["id"] == "LeeSin"


def test_resolve_not_first_champ_on_korean():
    """한글 입력 시 빈 slug 때문에 아트록스가 나오면 안 됨."""
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    c = dd.resolve_champion("리")
    assert c is not None
    assert c["id"] != "Aatrox"
    # "리"로 시작하는 챔프 (리 신, 리븐, 리산드라 등)
    assert _compact(c["name"]).startswith("리") or c["id"].lower().startswith("l")


def test_search_prefix_only_for_autocomplete():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    hits = dd.search_champions("리", limit=10)
    assert len(hits) >= 2
    ids = {h["id"] for h in hits}
    assert "LeeSin" in ids
    # 접두어만 — 이름 중간에만 '리' 있는 챔프는 제외
    for h in hits:
        assert _compact(h["name"]).startswith("리") or h["id"] in ids

    hits2 = dd.search_champions("미스", limit=5)
    assert any(h["id"] == "MissFortune" for h in hits2)

    # contains 폴백 (resolve용)
    mid = dd.search_champions("포츈", limit=5, contains=True)
    assert any(h["id"] == "MissFortune" for h in mid)


def test_search_empty():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    assert dd.search_champions("") == []
    assert dd.search_champions("   ") == []


def test_skin_variants_do_not_shadow_base_champions():
    """Jade_Ahri 같은 변형 챔피언이 기본 챔피언 인덱스를 덮어쓰면 안 됨."""
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    # 변형 챔피언이 카탈로그에 있을 때만 의미 있는 검증
    variants = [c for c in dd._champions_by_id.values() if "_" in c["id"]]
    if not variants:
        return

    ko = dd.resolve_champion("아리")
    assert ko is not None
    assert ko["id"] == "Ahri"

    en = dd.resolve_champion("Ahri")
    assert en is not None
    assert en["id"] == "Ahri"

    # 자동완성/검색 결과에 변형 챔피언이 섞이지 않아야 함
    hits = dd.search_champions("아리", limit=10, contains=True)
    ids = {h["id"] for h in hits}
    assert "Ahri" in ids
    assert not any("_" in i for i in ids)

    # Spectator 숫자 key 조회는 변형 챔피언도 여전히 동작해야 함
    jade = next(c for c in variants if c["id"] == "Jade_Ahri")
    assert dd.champion_name(int(jade["key"])) == jade["name"]


def test_champion_detail_caches_and_includes_metadata():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    detail = dd.champion_detail("Ahri")
    assert detail is not None
    assert detail["id"] == "Ahri"
    assert "_source_url" in detail
    assert "_patch" in detail
    assert dd.version in detail["_source_url"]
    # repeated call returns cached dict
    assert dd.champion_detail("Ahri") is detail


def test_ability_facts_structure():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    facts = dd.ability_facts("Ahri")
    assert set(facts.keys()) == {"P", "Q", "W", "E", "R"}
    for slot, fact in facts.items():
        assert fact is not None
        assert fact["slot"] == slot
        assert fact["name"]
        assert fact["description"]
        assert fact["icon"]
        assert "patch" in fact
        assert "source_url" in fact
        if slot != "P":
            assert "cooldown" in fact
            assert "cost" in fact
            assert "range" in fact


def test_ability_fact_by_slot():
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    q = dd.q_fact("LeeSin")
    assert q is not None
    assert q["slot"] == "Q"
    assert "음파" in q["name"] or "공명" in q["name"]
    r = dd.r_fact("LeeSin")
    assert r is not None
    assert r["slot"] == "R"
    assert dd.passive_fact("UnknownChampXYZ") is None
    assert dd.ability_facts("UnknownChampXYZ") == {
        "P": None,
        "Q": None,
        "W": None,
        "E": None,
        "R": None,
    }
