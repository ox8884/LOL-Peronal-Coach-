"""ddragon 공용 디스크 캐시 + DataDragon/i18n/카운터 캐시 연결 검증."""

from __future__ import annotations

import json
import time
from hashlib import sha1
from types import SimpleNamespace

import pytest

from lol_coach.static import ddragon_cache
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import KoreanLocalizer


class FakeResp:
    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


def _no_network(*_a, **_k):
    raise AssertionError("네트워크 접근 금지 (캐시로만 동작해야 함)")


def _minimal_ddragon_cache(monkeypatch, tmp_path, ver: str = "15.12") -> None:
    """DataDragon/i18n 이 오프라인으로 쓸 수 있는 최소 캐시를 심는다."""
    monkeypatch.setattr(ddragon_cache, "_root", lambda: tmp_path)
    ddragon_cache.write_cache("versions", [ver])
    for lang, name in (("ko_KR", "아리"), ("en_US", "Ahri")):
        ddragon_cache.write_cache(
            f"{ver}:{lang}:champion",
            {
                "data": {
                    "Ahri": {"id": "Ahri", "key": "103", "name": name, "tags": ["Mage"]}
                }
            },
        )
        ddragon_cache.write_cache(f"{ver}:{lang}:item", {"data": {}})
        ddragon_cache.write_cache(f"{ver}:{lang}:summoner", {"data": {}})
        ddragon_cache.write_cache(f"{ver}:{lang}:runesReforged", [])


def test_get_json_roundtrip_network_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ddragon_cache, "_root", lambda: tmp_path)
    calls: list[str] = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResp({"data": {"k": 1}})

    session = SimpleNamespace(get=fake_get)
    first = ddragon_cache.get_json(session, "http://x/1", "alpha", timeout=3)
    second = ddragon_cache.get_json(session, "http://x/1", "alpha", timeout=3)
    assert first == second == {"data": {"k": 1}}
    assert len(calls) == 1


def test_get_json_stale_fallback_and_raise(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ddragon_cache, "_root", lambda: tmp_path)
    # 8일 전 데이터 (데이터 TTL 7일 초과)
    p = ddragon_cache._path("alpha")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"ts": time.time() - 8 * 86400, "body": {"old": 1}}),
        encoding="utf-8",
    )
    session = SimpleNamespace(get=_no_network)
    # 네트워크 실패 시 stale 캐시 반환
    assert ddragon_cache.get_json(session, "http://x", "alpha", timeout=3) == {"old": 1}
    # 캐시도 없으면 예외 전파
    with pytest.raises(AssertionError):
        ddragon_cache.get_json(session, "http://x", "nope", timeout=3)


def test_get_json_expired_fresh_ttl_misses(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ddragon_cache, "_root", lambda: tmp_path)
    # versions.json 은 12시간 TTL — 13시간 지나면 재조회
    p = ddragon_cache._path("versions")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"ts": time.time() - 13 * 3600, "body": ["15.12"]}),
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_get(url, timeout):
        calls.append(url)
        return FakeResp(["15.13"])

    session = SimpleNamespace(get=fake_get)
    assert ddragon_cache.get_json(session, "http://v", "versions", timeout=3) == ["15.13"]
    assert len(calls) == 1


def test_ddragon_offline_from_cache(tmp_path, monkeypatch) -> None:
    _minimal_ddragon_cache(monkeypatch, tmp_path)
    dd = DataDragon()
    dd._loc = SimpleNamespace(ensure_loaded=lambda: None)  # type: ignore[attr-defined]
    dd.session.get = _no_network  # type: ignore[method-assign]
    dd.ensure_loaded()
    assert dd.champion_name(103) == "아리"
    assert dd.resolve_champion("Ahri") is not None


def test_localizer_offline_from_cache(tmp_path, monkeypatch) -> None:
    _minimal_ddragon_cache(monkeypatch, tmp_path)
    ddragon_cache.write_cache(
        "15.12:ko_KR:item", {"data": {"1001": {"name": "속도의 장화"}}}
    )
    ddragon_cache.write_cache(
        "15.12:en_US:item", {"data": {"1001": {"name": "Boots of Speed"}}}
    )
    loc = KoreanLocalizer()
    loc.session.get = _no_network  # type: ignore[method-assign]
    loc.ensure_loaded()
    assert loc.item("Boots of Speed") == "속도의 장화"


def test_counters_cache_roundtrip(tmp_path, monkeypatch) -> None:
    from lol_coach.ugg.client import UGGClient, UGGError
    from lol_coach.ugg.counters import (
        CounterClient,
        CounterPick,
        CounterReport,
        _report_to_dict,
    )

    ugg = UGGClient()
    monkeypatch.setattr(ugg, "_disk_dir", tmp_path)
    cc = CounterClient(ugg)
    rep = CounterReport(
        enemy="Ahri",
        role="mid",
        patch="15.1",
        source_url="https://u.gg/x",
        lane_counters=[CounterPick("Leblanc", 250, 12000, 53.1)],
        hard_matchups=[CounterPick("Yasuo", -120, 9000)],
    )
    ugg.cached_set("counters:ahri:mid", _report_to_dict(rep))
    ugg._cache = {}  # 메모리 비우고 디스크 경로 검증
    monkeypatch.setattr(
        ugg, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(UGGError("blocked"))
    )
    got = cc.get_counters("Ahri", "mid")
    assert got.lane_counters[0].champion == "Leblanc"
    assert got.lane_counters[0].gd15 == 250
    assert got.lane_counters[0].win_rate == 53.1
    assert got.hard_matchups[0].champion == "Yasuo"


def test_counters_fetch_then_cached(tmp_path, monkeypatch) -> None:
    from lol_coach.ugg.client import UGGClient
    from lol_coach.ugg.counters import CounterClient

    ugg = UGGClient()
    monkeypatch.setattr(ugg, "_disk_dir", tmp_path)
    cc = CounterClient(ugg)
    html = (
        "Patch 15.1\nBest Lane Counters vs Ahri\n"
        "Leblanc\n+250 GD15\n12,000\ngames\n"
    )
    monkeypatch.setattr(ugg, "fetch_html", lambda *a, **k: html)
    rep = cc.get_counters("Ahri", "mid")
    assert rep.lane_counters and rep.lane_counters[0].champion == "Leblanc"
    cached = ugg.cached_get("counters:ahri:mid")
    assert cached and cached["lane_counters"][0]["champion"] == "Leblanc"


def test_scrape_item_names_cached(tmp_path, monkeypatch) -> None:
    from lol_coach.analysis.aram_mayhem import MayhemCoach
    from lol_coach.ugg.client import UGGClient

    ugg = UGGClient()
    monkeypatch.setattr(ugg, "_disk_dir", tmp_path)
    coach = MayhemCoach(ugg=ugg, ddragon=DataDragon())
    url = "https://u.gg/lol/champions/aram/ahri-aram"
    key = "aram_items:" + sha1(url.encode("utf-8")).hexdigest()[:12]
    ugg.cached_set(key, ["리안드리의 고통", "존야의 모래시계"])
    ugg._cache = {}
    monkeypatch.setattr(ugg, "fetch_html", _no_network)
    assert coach._scrape_item_names(url) == ["리안드리의 고통", "존야의 모래시계"]
