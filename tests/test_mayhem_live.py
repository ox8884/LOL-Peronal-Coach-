"""blitz.mayhem_live — 라이브 챔피언별 증강 티어 단위 테스트 (오프라인)."""

from __future__ import annotations

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.blitz.mayhem_live import (
    LiveAugment,
    LiveMayhemTop,
    fetch_live_mayhem_top,
)

_PATCH = "16.17"


class FakeClient:
    """cached_get 만 구현한 가짜 BlitzClient — 미리 심은 응답으로 네트워크 대체."""

    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)

    def cached_get(self, key: str, *, allow_stale: bool = False) -> object | None:
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
