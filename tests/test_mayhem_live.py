"""blitz.mayhem_live — 라이브 챔피언별 증강 티어 단위 테스트 (오프라인)."""

from __future__ import annotations

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.blitz.mayhem_live import (
    LiveAugment,
    LiveItem,
    LiveMayhemTop,
    fetch_live_mayhem_top,
)

_PATCH = "16.17"


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


def test_advise_live_path_completes_regression(monkeypatch) -> None:
    """회귀: 라이브 경로에서 build_url 미정의 NameError가 났던 버그.

    advise() 가 예외 없이 advice 를 반환하고, 빌드 출처·코어가 채워진다.
    """
    from lol_coach.analysis.aram_mayhem import MayhemCoach

    class FakeBlitz:
        """cached_get 만 구현한 최소 블리츠 클라이언트 (네트워크 없음)."""

        def __init__(self, data: dict[str, object]) -> None:
            self.data = data

        def cached_get(self, key, *, allow_stale=False):
            return self.data.get(key)

        def cached_set(self, key, val):
            self.data[key] = val

    coach = MayhemCoach(blitz_client=FakeBlitz(_canned_full_for_ahri()))
    adv = coach.advise("아리")

    assert adv.build_url  # NameError 회귀 — 출처가 채워져야 한다
    assert adv.patch == _PATCH
    assert adv.core_slots and len(adv.core_slots) >= 3
    assert [p.name_ko for p in adv.fixed_top.prismatic]
