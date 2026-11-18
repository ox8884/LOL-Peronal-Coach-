"""lol.ps 아수라장 자료 — 풀기, 추리기, 캐시, 브리핑 연결."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from lol_coach import lolps

LAYOUT = {"versionInfo": [
    {"description": "26.22", "patchDate": "2026-11-04", "isActive": True},
    {"description": "26.21", "patchDate": "2026-10-21", "isActive": True},
]}
PAGE = {
    "champions": [
        {"id": 804, "name": "유나라", "tier": "A", "status": "ok", "roles": ["marksman"]},
        {"id": 876, "name": "릴리아", "tier": "S", "status": "ok", "roles": ["fighter"]},
        {"id": 86, "name": "가렌", "tier": "C", "status": "ok", "roles": ["fighter"]},
    ],
    "augments": [
        {"id": 2135, "name": "바늘꽂이", "nameId": "ARAM_Pin", "rarity": "prismatic", "tier": "S",
         "description": "대못을 박습니다.", "roleFit": ["marksman"]},
        {"id": 1051, "name": "불을 밝혀", "nameId": "ARAM_Light", "rarity": "silver", "tier": "A",
         "description": "투사체를 발사합니다.", "roleFit": ["marksman"]},
        {"id": 3001, "name": "채움 골드", "nameId": "ARAM_Fill", "rarity": "gold", "tier": "S",
         "description": "채움용.", "roleFit": ["marksman"]},
        {"id": 3002, "name": "남의 골드", "nameId": "ARAM_Other", "rarity": "gold", "tier": "S",
         "description": "다른 역할.", "roleFit": ["tank"]},
    ],
    # 사이트 티어판의 자료 — 챔피언 + 빌드 유형별. 챔피언 목록의 tier 와 다를 수 있다 (가렌: C vs B)
    "roleTiers": [
        {"id": 86, "type": "ad_bruiser", "tier": "C", "perf": 30.1, "winRate": 46.0, "pickRate": 1.1},
        {"id": 804, "type": "ad", "tier": "A", "perf": 63.2, "winRate": 51.6, "pickRate": 7.2},
        {"id": 86, "type": "tank", "tier": "B", "perf": 50.5, "winRate": 50.2, "pickRate": 3.0},
        {"id": 876, "type": "ap_bruiser", "tier": "S", "perf": 71.1, "winRate": 53.6, "pickRate": 6.5},
    ],
}
DETAIL = {"detail": {
    "items": [3032, 3085, 3031, 3036, 3153, 3006],
    "spells": [[4, 6]],
    "good": [
        {"id": 2135, "rank": 1, "name": "바늘꽂이", "rarity": "prismatic", "description": "대못을 박습니다.",
         "items": [3032, 6672], "signatureItems": [2512]},
        {"id": 1051, "rank": 2, "name": "불을 밝혀", "rarity": "silver", "description": "투사체를 발사합니다.",
         "items": [3032], "signatureItems": []},
    ],
    "bad": [{"id": 1058, "name": "신비한 주먹", "rarity": "prismatic", "description": ""}],
    "overall": {"winRate": 51.5, "pickRate": 7.32},
}, "unavailable": [{"id": 2080, "name": "눈 폭발"}]}


@pytest.fixture
def site(monkeypatch, tmp_path):
    """네트워크 대신 고정 자료를 주고, 요청한 경로를 기록한다."""
    calls: list[str] = []
    state = SimpleNamespace(calls=calls, fail=False, layout=LAYOUT)

    def fetch(path: str, *, page_only: bool):
        calls.append(path)
        if state.fail:
            raise OSError("offline")
        return [None, state.layout, None, PAGE] if path == "" else [None, None, None, DETAIL]

    monkeypatch.setattr(lolps, "_fetch_nodes", fetch)
    monkeypatch.setattr(lolps, "cache_root", lambda: tmp_path)
    monkeypatch.setattr(lolps, "_refresh_later", lambda name, work: work())  # 뒤에서 받기를 그 자리에서
    lolps._mem.clear()
    yield state
    lolps._mem.clear()


def test_unflatten_follows_references_and_missing_values() -> None:
    # {"a": [1, "x"], "b": {"c": True}, "d": undefined, "when": Date}
    flat = [{"a": 1, "b": 4, "d": -1, "when": 6}, [2, 3], 1, "x", {"c": 5}, True, ["Date", "2026-11-04"]]
    assert lolps.unflatten(flat) == {"a": [1, "x"], "b": {"c": True}, "d": None, "when": "2026-11-04"}


def test_index_keeps_only_what_the_screen_needs(site) -> None:
    listing = lolps.index()
    assert listing is not None and listing["patch"] == "26.22"
    assert listing["champs"]["804"] == {
        "name": "유나라", "tier": "A", "roles": ["marksman"], "win": 51.6, "pick": 7.2,
    }
    assert listing["augments"]["2135"]["name_id"] == "ARAM_Pin"
    assert lolps.champion_tiers() is not None
    # 챔피언의 티어는 가장 좋은 빌드 유형의 티어 (가렌: 탱커 B, AD 브루저 C → B)
    assert lolps.champion_tiers()[2] == {804: 2, 876: 1, 86: 3}
    assert listing["champs"]["86"]["win"] == 50.2


def test_tier_board_matches_the_site_order_and_labels(site) -> None:
    board = lolps.tier_board()
    assert board is not None and board[0] == "26.22"
    # 티어 순, 같은 티어 안에서는 성능 점수 순 — 한 챔피언이 빌드 유형마다 따로 나온다
    assert board[2] == [
        (1, 876, "AP 브루저", 53.6),
        (2, 804, "AD 딜러", 51.6),
        (3, 86, "탱커", 50.2),
        (4, 86, "AD 브루저", 46.0),
    ]


def test_old_cache_format_is_fetched_again(site) -> None:
    lolps._save("index", {"patch": "26.22", "fetched": 9e12, "champs": {}, "augments": {}})  # v 없음
    assert lolps.index()["board"], "예전 형식 캐시는 버리고 다시 받는다"
    assert site.calls == [""]


def test_second_look_does_not_touch_the_network(site, tmp_path) -> None:
    first = lolps.champion(804)
    assert first is not None and first["items"][0] == 3032 and first["patch"] == "26.22"
    assert first["bad"][0]["name"] == "신비한 주먹" and first["unavailable"] == [2080]
    assert site.calls == ["", "/champion/804"]

    assert lolps.champion(804) == first  # 메모리
    lolps._mem.clear()
    assert lolps.champion(804)["items"] == first["items"]  # 디스크
    assert site.calls == ["", "/champion/804"], "한 번 받은 챔피언은 다시 받지 않는다"
    assert (tmp_path / "lolps" / "champ_804.json").stat().st_size < 4000


def test_new_patch_refetches_and_offline_keeps_the_old_copy(site) -> None:
    lolps.champion(804)
    # 목록이 오래되어 새로 받았더니 패치가 올랐다
    lolps._mem["index"]["fetched"] = time.time() - lolps.INDEX_TTL_S - 1
    site.layout = {"versionInfo": [{"description": "26.23", "patchDate": "2026-11-18", "isActive": True}]}
    assert lolps.index()["patch"] == "26.22"  # 지금 것을 먼저 주고
    assert lolps._mem["index"]["patch"] == "26.23"  # 뒤에서 새로 받아 둔다
    site.calls.clear()
    assert lolps.champion(804)["patch"] == "26.23"
    assert site.calls == ["/champion/804"], "패치가 바뀐 챔피언만 다시 받는다"

    site.fail = True
    lolps._mem["index"]["patch"] = "26.24"
    assert lolps.champion(804)["patch"] == "26.23", "받지 못하면 예전 자료를 준다"
    assert lolps.champion(999, network=False) is None


def test_prefetch_only_fetches_what_is_missing(site) -> None:
    lolps.champion(804)
    site.calls.clear()
    assert lolps.prefetch_all(pause_s=0) == 2
    assert site.calls == ["/champion/876", "/champion/86"]  # 좋은 티어부터
    site.calls.clear()
    assert lolps.prefetch_all(pause_s=0) == 0 and site.calls == []


def test_coach_builds_the_briefing_from_lolps(site) -> None:
    from lol_coach.analysis.aram_mayhem import MayhemCoach

    items = {3032: "윤 탈 야생화살", 3085: "루난의 허리케인", 3031: "무한의 대검", 3036: "도미닉 경의 인사",
             3153: "몰락한 왕의 검", 3006: "광전사의 군화", 6672: "크라켄 학살자", 2512: "핵심템"}
    dd = SimpleNamespace(
        ensure_loaded=lambda: None,
        resolve_champion=lambda name: {"id": "Yunara", "name": "유나라", "key": "804", "tags": ["Marksman"]},
        item_name=lambda item_id: items.get(item_id, ""),
    )
    coach = MayhemCoach(dd, lolps=lolps)  # type: ignore[arg-type]
    coach.loc = SimpleNamespace(ensure_loaded=lambda: None)
    coach._ability_lines = lambda key, tags: ["스킬 팁 1", "스킬 팁 2"]  # type: ignore[method-assign]
    coach._catalog = SimpleNamespace(get_by_name=lambda name: None)  # type: ignore[assignment]

    adv = coach.advise("유나라")

    assert adv.patch == "26.22" and adv.source is not None and adv.source.primary == "lol.ps 아수라장"
    assert adv.core_item_ids == [3032, 3085, 3031, 3036, 3153, 3006]
    assert adv.core_slots[0] == "윤 탈 야생화살" and adv.build is not None and adv.build.win_rate == 51.5
    assert [p.name_ko for p in adv.fixed_top.prismatic] == ["바늘꽂이"]
    assert [p.name_ko for p in adv.fixed_top.silver] == ["불을 밝혀"]
    # 추천에 골드가 없으면 전체 증강 티어에서 역할이 맞는 것만 채운다
    assert [p.name_ko for p in adv.fixed_top.gold] == ["채움 골드"]
    assert [p.name_ko for p in adv.avoid_augments] == ["신비한 주먹"]
    assert "핵심템" in adv.top_augments[0].reason and "크라켄 학살자" in adv.top_augments[0].reason
    assert adv.reroll is not None and adv.reroll.my_tier == 2
    assert adv.play_tips[:2] == ["스킬 팁 1", "스킬 팁 2"]
    assert coach.champion_tiers() == {804: 2, 876: 1, 86: 3}
