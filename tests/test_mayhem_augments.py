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


def test_icon_bytes_for_caches_lcu_failures(monkeypatch, tmp_path) -> None:
    """실패한 LCU 에셋은 TTL 동안 다시 요청하지 않는다 (복기 클릭마다 타임아웃 반복 방지)."""
    import lol_coach.config as config
    import lol_coach.static.mayhem_augments as ma

    monkeypatch.setattr(config, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(ma, "_icon_failures", {})
    calls = []

    class _LCU:
        def _get_raw(self, path):
            calls.append(path)
            raise RuntimeError("404")

    meta = ma.AugmentMeta(id=77, name="x", rarity="", icon_path="/a.png")
    assert ma.icon_bytes_for(meta, _LCU()) is None
    assert ma.icon_bytes_for(meta, _LCU()) is None
    assert calls == ["/a.png"]


def test_icon_comes_from_the_web_when_the_client_is_off(monkeypatch, tmp_path) -> None:
    """롤 클라이언트가 꺼져 있어도 게임 아이콘을 받고, 다음부터는 디스크에서 바로 준다."""
    import lol_coach.config as config
    import lol_coach.static.mayhem_augments as ma

    monkeypatch.setattr(config, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(ma, "_icon_failures", {})
    asked: list[str] = []
    monkeypatch.setattr(ma, "_download_icon", lambda path: asked.append(path) or b"PNG")
    meta = ma.AugmentMeta(
        id=3058, name="간지럼 괴물", rarity="gold",
        icon_path="/lol-game-data/assets/ASSETS/UX/Kiwi/Augments/Icons/TickleMonster_small.png",
    )
    assert ma.cached_icon_bytes(3058) is None
    assert ma.icon_bytes_for(meta, None) == b"PNG"
    assert ma.icon_bytes_for(meta, None) == b"PNG" and len(asked) == 1
    assert ma.cached_icon_bytes(3058) == b"PNG"


def test_meta_by_name_prefers_the_aram_mayhem_icon() -> None:
    import lol_coach.static.mayhem_augments as ma

    ma._mem_catalog = _parse_catalog([
        {"id": 1, "nameTRA": "강력한 방패", "augmentSmallIconPath": "/x/Cherry/Augments/Icons/a.png"},
        {"id": 1314, "nameTRA": "강력한 방패", "augmentSmallIconPath": "/x/Kiwi/Augments/Icons/a.png"},
    ])
    try:
        meta = ma.meta_by_name("강력한 방패")
        assert meta is not None and meta.id == 1314
        assert ma.meta_by_name("없는 증강") is None
    finally:
        ma._mem_catalog = None


def test_augment_texts_are_fetched_once_per_patch(monkeypatch, tmp_path) -> None:
    import lol_coach.config as config
    import lol_coach.static.mayhem_augments as ma

    monkeypatch.setattr(config, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(ma, "_texts_mem", {})
    monkeypatch.setattr(ma, "_texts_fail_at", 0.0)
    calls: list[str] = []

    def fetch(patch: str):
        calls.append(patch)
        return {1314: ("3초 동안 40–100의 적응형 능력치", "자세히")}

    monkeypatch.setattr(ma, "_fetch_texts", fetch)
    assert ma.augment_texts("16.23.1")[1314][0].startswith("3초")
    assert ma.augment_texts("16.23.1")[1314][1] == "자세히"
    ma._texts_mem.clear()
    assert ma.augment_texts("16.23.1", network=False)[1314][1] == "자세히"  # 디스크
    assert calls == ["16.23"]
    # 새 패치 자료를 받지 못하면 가장 최근에 받아 둔 것을 준다
    monkeypatch.setattr(ma, "_fetch_texts", lambda patch: None)
    assert ma.augment_texts("16.24.1")[1314][1] == "자세히"


def test_tooltip_drops_in_game_counters_and_flavor() -> None:
    import lol_coach.static.mayhem_augments as ma

    text = "피해를 입힙니다.<br><br><rules>입힌 피해량: ?</rules><flavorText>빵야!</flavorText>"
    assert ma._strip_tooltip(text) == "피해를 입힙니다.<br><br>"


def test_corrupt_fresh_catalog_forces_refetch(monkeypatch, tmp_path) -> None:
    """쓰기 중 종료로 깨진(그러나 mtime 은 새) 카탈로그는 7일 기다리지 않고 재다운로드."""
    import json

    import lol_coach.config as config
    import lol_coach.static.mayhem_augments as ma

    monkeypatch.setattr(config, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(ma, "_mem_catalog", None)
    path = ma._catalog_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[{"id": 1133, "nameTRA": "마법', encoding="utf-8")  # 잘린 JSON
    calls = []

    def fetch() -> bool:
        calls.append(1)
        path.write_text(json.dumps([{"id": 1133, "nameTRA": "마법 미사일"}]), encoding="utf-8")
        return True

    monkeypatch.setattr(ma, "_fetch_catalog_file", fetch)
    assert ma.load_catalog()[1133].name == "마법 미사일"
    assert calls == [1]
