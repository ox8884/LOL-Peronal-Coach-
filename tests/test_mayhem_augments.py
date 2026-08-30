"""static.mayhem_augments — 아수라장 증강 메타데이터 단위 테스트."""

from __future__ import annotations

from lol_coach.analysis.lcu_match import lcu_to_match_summary
from lol_coach.static.mayhem_augments import _parse_catalog, resolve_display


def _dto(stats_extra: dict | None = None) -> dict:
    stats = {
        "kills": 5,
        "deaths": 3,
        "assists": 8,
        "totalMinionsKilled": 60,
        "neutralMinionsKilled": 10,
        "goldEarned": 12000,
        "totalDamageDealtToChampions": 20000,
        "visionScore": 15,
        "gameDuration": 900,
        "win": True,
    }
    stats.update(stats_extra or {})
    return {
        "gameId": 123,
        "queueId": 2400,
        "gameMode": "ARAM",
        "gameCreation": 1700000000000,
        "participantIdentities": [
            {"participantId": 1, "player": {"gameName": "나", "tagLine": "KR1", "puuid": "pu1"}},
            {"participantId": 2, "player": {"gameName": "상대", "tagLine": "KR1", "puuid": "pu2"}},
        ],
        "participants": [
            {
                "participantId": 1,
                "championId": 100,
                "teamId": 100,
                "timeline": {"lane": "NONE"},
                "stats": stats,
            },
            {
                "participantId": 2,
                "championId": 200,
                "teamId": 200,
                "timeline": {"lane": "NONE"},
                "stats": dict(stats, win=False),
            },
        ],
    }


def test_lcu_dto_augment_ids_parsed() -> None:
    dto = _dto(
        {
            "playerAugment1": 1133,
            "playerAugment2": 2083,
            "playerAugment3": 0,
            "playerAugment4": 2062,
        }
    )
    m = lcu_to_match_summary(dto, my_puuid="pu1")
    assert m is not None
    assert m.augment_ids == [1133, 2083, 2062]


def test_lcu_dto_without_augments_is_empty() -> None:
    m = lcu_to_match_summary(_dto(), my_puuid="pu1")
    assert m is not None
    assert m.augment_ids == []


def test_parse_catalog_maps_korean_names() -> None:
    raw = [
        {
            "id": 1133,
            "augmentNameId": "ARAM_MagicMissile",
            "nameTRA": "마법 미사일",
            "rarity": "kGold",
            "augmentSmallIconPath": "/lol-game-data/assets/ASSETS/Maps/Particles/Kiwi/MagicMissile_small.png",
        },
        {
            "id": 2062,
            "nameTRA": "메아리 시전",
            "rarity": "kPrismatic",
            "augmentSmallIconPath": "",
        },
        {"id": 0, "nameTRA": "무효"},
        {"nameTRA": "ID 없음"},
    ]
    cat = _parse_catalog(raw)
    assert set(cat) == {1133, 2062}
    assert cat[1133].name == "마법 미사일"
    assert cat[1133].rarity == "gold"
    assert cat[1133].icon_path.endswith("MagicMissile_small.png")
    assert cat[2062].rarity == "prismatic"


def test_resolve_display_prefers_catalog_then_names() -> None:
    raw = [
        {"id": 1133, "nameTRA": "마법 미사일", "rarity": "kGold", "augmentSmallIconPath": ""},
    ]
    import lol_coach.static.mayhem_augments as ma

    ma._mem_catalog = _parse_catalog(raw)
    try:
        out = resolve_display([1133, 999999], ["Fireball"])
        assert [a.name for a in out] == ["마법 미사일", "Fireball"]
        assert out[1].rarity == ""  # V5 이름 기반은 등급 없음
    finally:
        ma._mem_catalog = None
