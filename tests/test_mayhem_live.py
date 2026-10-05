"""blitz.mayhem_live — 라이브 챔피언별 증강 티어 단위 테스트 (오프라인)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.blitz.mayhem_live import (
    LiveAugment,
    LiveItem,
    LiveMayhemTop,
    fetch_live_build_order,
    fetch_live_mayhem_top,
    fetch_mayhem_champion_tiers,
)

_PATCH = "16.19"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("This suite must not access the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    monkeypatch.setattr("requests.sessions.Session.request", no_network)


@pytest.fixture
def offline_coach(monkeypatch):
    dd = SimpleNamespace(
        ensure_loaded=lambda: None,
        resolve_champion=lambda _: {"id": "Ahri", "key": "103", "name": "아리", "tags": ["Mage"]},
        item_id_for_name=lambda _: None,
        item_meta=lambda _: None,
        ability_facts=lambda _: {},
    )
    monkeypatch.setattr(
        "lol_coach.analysis.aram_mayhem.get_localizer",
        lambda: SimpleNamespace(ensure_loaded=lambda: None),
    )
    return MayhemCoach(ddragon=dd, blitz_client=FakeClient(_canned_full_for_ahri()))


class FakeClient:
    """cached_get 만 구현한 가짜 BlitzClient — 미리 심은 응답으로 네트워크 대체."""

    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)
        self.disk_ttl = 72 * 3600.0

    def cached_get(
        self, key: str, *, allow_stale: bool = False, ttl: float | None = None
    ) -> object | None:
        return self.data.get(key)

    def cached_set(self, key: str, val: object) -> None:
        self.data[key] = val


def _canned() -> dict[str, object]:
    game = {
        str(aid): {
            "id": aid,
            "name": f"AUG_{aid}",
            "displayName": name,
            "rarity": rarity,
            "enabled": True,
            "description": f"<b>{name}</b> 설명",
        }
        for aid, name, rarity in (
            (101, "프리즘증강일", 2),
            (102, "골드증강일", 1),
            (103, "실버증강일", 0),
        )
    }
    game["999"] = {"id": 999, "name": "DISABLED", "displayName": "비활성", "enabled": False}
    return {
        "mayhem_champions": {"data": [{"patch": _PATCH}]},
        f"mayhem_gamedata:{_PATCH}": game,
        f"mayhem_champ:103:{_PATCH}": {
            "data": [
                {
                    "champion_id": "103",
                    "dt": "2026-08-28",
                    "patch": _PATCH,
                    "data": {
                        "augments": {"101": {"tier": 2}, "102": {"tier": 1}, "103": {"tier": 3}},
                        "items": {},
                        "tier": 2,
                    },
                }
            ]
        },
    }


def test_fetch_live_mayhem_top_parses_and_sorts() -> None:
    top = fetch_live_mayhem_top("103", client=FakeClient(_canned()))
    assert top is not None
    assert top.patch == _PATCH
    assert top.updated == "2026-08-28"
    # 티어 오름차순 정렬
    assert [a.name_ko for a in top.top("prismatic")] == ["프리즘증강일"]
    assert [a.name_ko for a in top.top("gold")] == ["골드증강일"]
    assert [a.name_ko for a in top.top("silver")] == ["실버증강일"]
    # disabled 는 제외
    assert all(
        "비활성" not in a.name_ko for r in ("prismatic", "gold", "silver") for a in top.top(r)
    )


def test_fetch_live_mayhem_top_none_on_bad_payload() -> None:
    assert fetch_live_mayhem_top("", client=FakeClient({})) is None
    # 챔피언 데이터 없음
    canned = {
        "mayhem_champions": {"data": [{"patch": _PATCH}]},
        f"mayhem_gamedata:{_PATCH}": {"1": {"displayName": "x", "rarity": 1}},
    }
    assert fetch_live_mayhem_top("999", client=FakeClient(canned)) is None


def test_live_augment_ties_match_page_order_regardless_of_json_order() -> None:
    canned = _canned()
    game = canned[f"mayhem_gamedata:{_PATCH}"]
    game["99"] = dict(game["101"], id=99, displayName="같은 티어 앞 증강")
    tiers = canned[f"mayhem_champ:103:{_PATCH}"]["data"][0]["data"]["augments"]
    tiers["99"] = {"tier": 2}
    live = fetch_live_mayhem_top("103", client=FakeClient(canned))
    assert live is not None
    assert [pick.augment_id for pick in live.top("prismatic")] == [99, 101]


def test_live_augment_top_and_picks_shape() -> None:
    live = LiveMayhemTop(
        patch=_PATCH,
        updated="2026-08-28",
        by_rarity={
            "prismatic": (
                LiveAugment(11, "프2", "AUG2", "prismatic", 2),
                LiveAugment(10, "프1", "AUG1", "prismatic", 1),
            ),
            "gold": (LiveAugment(20, "골1", "AUGG", "gold", 1),),
            "silver": (),
        },
    )
    coach = MayhemCoach.__new__(MayhemCoach)  # __init__ 네트워크 로드 생략
    coach.catalog = type("C", (), {"get_by_name": lambda self, n: None})()

    top = coach._live_augment_top(live)
    assert [p.name_ko for p in top.prismatic] == ["프1", "프2"]  # 티어 1 먼저
    assert top.gold and not top.silver

    picks = coach._live_augment_picks(live)
    assert picks[0].record.rarity == "prismatic"
    assert picks[0].record.fallback_tier in {"S", "A", "B"}
    assert picks[0].score > picks[1].score  # 프리즘이 골드/실버보다 앞선다


def _canned_with_items() -> dict[str, object]:
    canned = dict(_canned())
    champ = canned[f"mayhem_champ:103:{_PATCH}"]
    row = champ["data"][0]
    row["data"] = {
        "augments": {"101": {"tier": 1}},
        "items": {
            "6653": {"tier": 1},  # 완성템 3000g
            "4645": {"tier": 2},  # 완성템 3200g
            "1082": {"tier": 1},  # 마법사의 신발 (Boots, depth 2, 1100g)
        },
    }
    return canned


def test_live_items_sorted_by_tier() -> None:
    top = fetch_live_mayhem_top("103", client=FakeClient(_canned_with_items()))
    assert top is not None
    assert [it.item_id for it in top.items] == [6653, 1082, 4645]  # 티어 오름차순(안정 정렬)


def test_live_core_items_filters_components_and_boots() -> None:
    from lol_coach.analysis.aram_mayhem import MayhemCoach

    coach = MayhemCoach.__new__(MayhemCoach)

    class FakeItem:
        def __init__(self, item_id: int) -> None:
            self.item_id = item_id

    class FakeDD:
        def item_id_for_name(self, name: str) -> int | None:
            return None

        def item_meta(self, item_id: int) -> dict | None:
            return {
                6653: {
                    "name": "리안드리의 고통",
                    "tags": ["Mage"],
                    "depth": 3,
                    "gold": {"total": 3000, "purchasable": True},
                    "maps": {"12": True},
                },
                4645: {
                    "name": "그림자불꽃",
                    "tags": ["Mage"],
                    "depth": 3,
                    "gold": {"total": 3200, "purchasable": True},
                    "maps": {"12": True},
                },
                1082: {
                    "name": "마법사의 신발",
                    "tags": ["Boots"],
                    "depth": 2,
                    "gold": {"total": 1100, "purchasable": True},
                    "maps": {"12": True},
                },
                1033: {
                    "name": "재생의 팔찌",
                    "tags": [],
                    "depth": 1,
                    "gold": {"total": 300, "purchasable": True},
                    "maps": {"12": True},
                },
                3075: {
                    "name": "가시 갑옷",
                    "tags": ["Tank"],
                    "depth": 3,
                    "gold": {"total": 2700, "purchasable": True},
                    "maps": {"12": True},
                },
            }.get(item_id)

    coach.dd = FakeDD()
    from lol_coach.blitz.mayhem_live import LiveItem

    live = LiveMayhemTop(
        patch=_PATCH,
        updated="2026-08-28",
        items=(
            LiveItem(1082, 1),  # 신발 — 3번째 슬롯에 삽입
            LiveItem(1033, 1),  # 재료(depth 1) — 제외
            LiveItem(3075, 1),  # 완성템
            LiveItem(4645, 2),
            LiveItem(6653, 1),
        ),
    )
    out = coach._live_core_items(live, tags=set())
    assert out is not None
    names, ids = out
    # 티어→싼 순 정렬 후 신발이 3번째 슬롯(구매 순서 관행)에 삽입,
    # 4개뿐이면 태그 폴백 코어로 6슬롯을 채운다
    assert names[:4] == ["가시 갑옷", "리안드리의 고통", "마법사의 신발", "그림자불꽃"]
    assert ids[:4] == [3075, 6653, 1082, 4645]
    assert len(names) == 6  # 폴백 코어로 6슬롯 완성


def test_live_core_items_none_when_insufficient() -> None:
    from lol_coach.analysis.aram_mayhem import MayhemCoach

    coach = MayhemCoach.__new__(MayhemCoach)

    class FakeItem:
        def __init__(self, item_id: int) -> None:
            self.item_id = item_id

    class FakeDD:
        def item_meta(self, item_id: int) -> dict | None:
            return {
                6653: {
                    "name": "리안드리의 고통",
                    "tags": [],
                    "depth": 3,
                    "gold": {"total": 3000, "purchasable": True},
                    "maps": {"12": True},
                }
            }.get(item_id)

    coach.dd = FakeDD()
    live = LiveMayhemTop(patch=_PATCH, updated="", items=(LiveItem(6653, 1),))
    assert coach._live_core_items(live, tags=set()) is None


def _canned_full_for_ahri() -> dict[str, object]:
    """advise() 통합 경로용 — 아리 라이브 티어 + 완성 아이템."""
    canned = dict(_canned_with_items())
    champ = canned[f"mayhem_champ:103:{_PATCH}"]
    row = champ["data"][0]
    row["data"]["augments"] = {"101": {"tier": 1}, "102": {"tier": 2}, "103": {"tier": 3}}
    return canned


def test_advise_live_path_completes_regression(offline_coach) -> None:
    """회귀: 라이브 경로에서 build_url 미정의 NameError가 났던 버그.

    advise() 가 예외 없이 advice 를 반환하고, 빌드 출처·코어가 채워진다.
    """
    adv = offline_coach.advise("아리")

    assert adv.build_url  # NameError 회귀 — 출처가 채워져야 한다
    assert adv.patch == _PATCH
    assert adv.core_slots and len(adv.core_slots) >= 3
    assert [p.name_ko for p in adv.fixed_top.prismatic]


@pytest.mark.parametrize("field,value", [("patch", "16.16"), ("patch", ""), ("champion_id", "99")])
def test_live_top_rejects_different_or_unknown_provenance(field, value):
    canned = _canned()
    canned[f"mayhem_champ:103:{_PATCH}"]["data"][0][field] = value
    assert fetch_live_mayhem_top("103", client=FakeClient(canned)) is None


def test_packaged_items_keep_their_source_with_live_augments(offline_coach):
    from lol_coach.static.blitz_aram import BlitzAramBuild, BlitzAramCatalog, BlitzAramItem

    offline_coach.blitz = BlitzAramCatalog(
        patch="16.15", updated_at="2026-07-30", records=(
            BlitzAramBuild("Ahri", "16.15", "https://example.invalid/snapshot", tuple(
                BlitzAramItem(str(i), f"아이템{i}", "") for i in range(1, 7)
            )),
        ),
    )
    adv = offline_coach.advise("아리")
    assert adv.patch == _PATCH
    assert adv.build.patch == "16.15"
    assert adv.build.source_url == "https://example.invalid/snapshot"
    assert "스냅샷" in adv.build.core_items.note
    assert "16.15" in adv.source.secondary
    assert "2026-07-30" in adv.source.secondary
    assert "실시간" not in adv.augment_source
    assert adv.source.updated_at == "2026-08-28"
    assert [p.name_ko for p in adv.top_augments] == ["프리즘증강일", "골드증강일", "실버증강일"]


@pytest.mark.parametrize("live_patch", ["16.19", "16.20"])
def test_item_purchase_order_uses_snapshot_unless_live_patch_is_newer(
    offline_coach, monkeypatch, live_patch,
):
    from dataclasses import replace

    expected = offline_coach.advise("아리", use_live=False)
    live = fetch_live_mayhem_top("103", client=FakeClient(_canned()))
    assert live is not None
    ids = [11001, 11002, 11003, 11004, 11005, 12001]
    metadata = {
        item_id: {
            "name": f"라이브 아이템{item_id}", "depth": 3,
            "gold": {"total": 3000 + i, "purchasable": True},
            "tags": ["Boots"] if item_id == 12001 else [],
            "maps": {"12": True},
        }
        for i, item_id in enumerate(ids)
    }
    monkeypatch.setattr(offline_coach.dd, "item_meta", metadata.get)
    live = replace(live, patch=live_patch, items=tuple(LiveItem(i, 1) for i in ids))
    monkeypatch.setattr(
        "lol_coach.blitz.mayhem_live.fetch_live_mayhem_top", lambda *a, **kw: live,
    )
    adv = offline_coach.advise("아리")
    if live_patch == "16.19":
        assert adv.build.patch == expected.build.patch
        assert adv.core_item_ids == expected.core_item_ids
        assert "스냅샷" in adv.build.core_items.note
    else:
        assert adv.build.patch == live_patch
        assert adv.core_item_ids == [11001, 11002, 12001, 11003, 11004, 11005]
        assert "티어 근사" in adv.build.core_items.note


def test_page_without_augments_falls_back_without_assertion(offline_coach, monkeypatch):
    # No verified snapshot is available for this champion.
    from lol_coach.static.blitz_aram import BlitzAramCatalog

    offline_coach.blitz = BlitzAramCatalog(patch="", updated_at="", records=())
    monkeypatch.setattr(
        "lol_coach.blitz.mayhem_live.fetch_live_all",
        lambda *a, **kw: (None, (["가", "나", "다"], [1, 2, 3])),
    )
    adv = offline_coach.advise("아리")
    assert adv.build.patch == ""
    assert adv.core_item_ids == [1, 2, 3]
    assert "패치 미확인" in adv.build.core_items.note


@pytest.mark.parametrize("stale", [False, True])
def test_old_live_cache_cannot_replace_current_snapshot(offline_coach, stale):
    expected = offline_coach.advise("아리", use_live=False)
    old_patch = "16.17"
    data = {
        key.replace(_PATCH, old_patch): value
        for key, value in _canned_full_for_ahri().items()
    }
    data["mayhem_champions"]["data"][0]["patch"] = old_patch
    data[f"mayhem_champ:103:{old_patch}"]["data"][0]["patch"] = old_patch
    data[f"mayhem_page:Ahri:{old_patch}"] = {
        "patch": old_patch,
        "core_items": [{"name_ko": f"이전{i}", "item_id": i} for i in range(1, 7)],
    }

    class OldClient(FakeClient):
        def cached_get(self, key, *, allow_stale=False, ttl=None):
            return super().cached_get(key) if not stale or allow_stale else None

    offline_coach._blitz_client = OldClient(data)
    actual = offline_coach.advise("아리")
    assert actual.patch == expected.patch
    assert actual.fixed_top == expected.fixed_top
    assert actual.core_item_ids == expected.core_item_ids
    assert actual.build.patch == expected.build.patch


def test_snapshot_build_does_not_download_unverified_page(offline_coach, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lol_coach.blitz.mayhem_live.fetch_live_build_order",
        lambda *a, **kw: calls.append(a) or (["이전"], [1]),
    )
    actual = offline_coach.advise("아리")
    assert actual.patch == _PATCH
    assert calls == []


def test_newer_live_patch_can_update_augments(offline_coach, monkeypatch):
    from dataclasses import replace

    live = fetch_live_mayhem_top("103", client=FakeClient(_canned()))
    assert live is not None
    newer = replace(live, patch="16.20")
    monkeypatch.setattr(
        "lol_coach.blitz.mayhem_live.fetch_live_mayhem_top", lambda *a, **kw: newer,
    )
    actual = offline_coach.advise("아리")
    assert actual.patch == "16.20"
    assert actual.top_augments[0].name_ko == "프리즘증강일"


def test_page_cache_refreshes_before_stale_fallback():
    class PageClient(FakeClient):
        def cached_get(self, key, *, allow_stale=False, ttl=None):
            return super().cached_get(key) if allow_stale else None

        def fetch_html(self, url):
            return '<div class="items-group">완성 아이템' + ''.join(
                f'<img class="item-img" src="/item/{i}.webp" alt="새{i}">'
                for i in (4, 5, 6)
            ) + '</div>'

    client = PageClient({f"mayhem_page:Ahri:{_PATCH}": {
        "patch": _PATCH,
        "core_items": [{"item_id": i, "name_ko": f"이전{i}"} for i in (1, 2, 3)],
    }})
    assert fetch_live_build_order("Ahri", client=client, patch=_PATCH) == (["새4", "새5", "새6"], [4, 5, 6])


def test_champion_tiers_do_not_mix_patches():
    client = FakeClient({"mayhem_champions": {"data": [
        {"patch": "16.17", "dt": "2026-08-28", "champion_id": "103", "stats": {"tier": 2}},
        {"patch": "16.16", "dt": "2026-08-14", "champion_id": "86", "stats": {"tier": 1}},
        {"patch": "", "champion_id": "99", "stats": {"tier": 1}},
    ]}})
    assert fetch_mayhem_champion_tiers(client) == ("16.17", "2026-08-28", {103: 2})


@pytest.mark.parametrize("failure", ["offline", "partial"])
def test_page_stale_cache_remains_available_on_failure(failure):
    class PageClient(FakeClient):
        def cached_get(self, key, *, allow_stale=False, ttl=None):
            return super().cached_get(key) if allow_stale else None

        def fetch_html(self, url):
            if failure == "offline":
                raise OSError("offline")
            return '<div class="items-group">완성 아이템<img class="item-img" src="/item/4.webp" alt="일부4"></div>'

    client = PageClient({f"mayhem_page:Ahri:{_PATCH}": {
        "patch": _PATCH,
        "core_items": [{"item_id": i, "name_ko": f"이전{i}"} for i in (1, 2, 3)],
    }})
    assert fetch_live_build_order("Ahri", client=client, patch=_PATCH) == (["이전1", "이전2", "이전3"], [1, 2, 3])


def test_live_augment_metadata_replaces_packaged_metadata(offline_coach):
    known = offline_coach.catalog.get_by_name("Jeweled Gauntlet")
    assert known is not None
    live = LiveAugment(123, known.name_ko, known.name_en, "silver", 2, "새 패치 설명")
    record = offline_coach._live_augment_record(live)
    assert record.id == known.id
    assert record.rarity == "silver"
    assert record.description_ko == "새 패치 설명"
