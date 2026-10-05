"""ddragon 공용 디스크 캐시 + DataDragon/i18n/카운터 캐시 연결 검증."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from lol_coach.static import ddragon_cache
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import KoreanLocalizer


class FakeResp:
    def __init__(self, body: object) -> None:
        self._body = body
        self._raw = json.dumps(body).encode("utf-8")
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [
            self._raw[offset : offset + chunk_size]
            for offset in range(0, len(self._raw), chunk_size)
        ]


def _no_network(*_a, **_k):
    raise AssertionError("네트워크 접근 금지 (캐시로만 동작해야 함)")


@pytest.fixture(autouse=True)
def _clear_mem_cache():
    """모듈 수준 메모리 캐시를 테스트 간에 비운다 (디스크 시나리오 격리)."""
    ddragon_cache._MEM.clear()
    yield
    ddragon_cache._MEM.clear()


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

    def fake_get(url, timeout, **_kwargs):
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

    def fake_get(url, timeout, **_kwargs):
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


@pytest.mark.parametrize("factory", [DataDragon, KoreanLocalizer])
def test_new_instance_refreshes_expired_version(factory, tmp_path, monkeypatch) -> None:
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    instance = factory()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return FakeResp(["16.18.1"])

    instance.session.get = get
    assert instance.version == "16.17.1"
    assert instance.version == "16.17.1"
    assert calls == []
    ddragon_cache._MEM["versions"]["ts"] -= ddragon_cache.VERSION_TTL_S + 1
    assert instance.version == "16.17.1"
    assert calls == []
    restarted = factory()
    restarted.session.get = get
    assert restarted.version == "16.18.1"
    assert len(calls) == 1


@pytest.mark.parametrize("factory", [DataDragon, KoreanLocalizer])
def test_loaded_lookups_keep_patch_until_new_instance(factory, tmp_path, monkeypatch) -> None:
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    for lang in ("ko_KR", "en_US"):
        ddragon_cache.write_cache(
            f"16.17.1:{lang}:item", {"data": {"1001": {"name": "이전 아이템"}}}
        )
    instance = factory()
    instance.session.get = _no_network
    if isinstance(instance, DataDragon):
        instance._loc = SimpleNamespace(ensure_loaded=lambda: None, item=lambda _: "")
    instance.ensure_loaded()
    if isinstance(instance, DataDragon):
        instance._details["Ahri"] = {"_patch": "16.17.1"}

    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.18.1")
    for lang in ("ko_KR", "en_US"):
        ddragon_cache.write_cache(f"16.18.1:{lang}:champion", {"data": {}})
        ddragon_cache.write_cache(
            f"16.18.1:{lang}:item", {"data": {"1002": {"name": "새 아이템"}}}
        )
    instance.ensure_loaded()
    assert instance.version == "16.17.1"
    if isinstance(instance, DataDragon):
        assert instance.item_name(1001) == "이전 아이템"
        assert instance.resolve_champion("Ahri") is not None
        assert instance._details["Ahri"]["_patch"] == "16.17.1"
    else:
        assert instance.item(1001) == "이전 아이템"
        assert instance.champion("Ahri") == "아리"

    restarted = factory()
    restarted.session.get = _no_network
    if isinstance(restarted, DataDragon):
        restarted._loc = instance._loc
    restarted.ensure_loaded()
    assert restarted.version == "16.18.1"
    if isinstance(restarted, DataDragon):
        assert restarted.item_name(1002) == "새 아이템"
        assert restarted.item_meta(1001) is None
        assert restarted.resolve_champion("Ahri") is None
        assert restarted._details == {}
    else:
        assert restarted.item(1002) == "새 아이템"
        assert restarted.item(1001) == ""
        assert restarted.champion("Ahri") != "아리"


@pytest.mark.parametrize("factory", [DataDragon, KoreanLocalizer])
def test_loaded_ui_lookups_never_recheck_expired_cache(factory, tmp_path, monkeypatch):
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    for lang in ("ko_KR", "en_US"):
        ddragon_cache.write_cache(
            f"16.17.1:{lang}:item", {"data": {"1001": {"name": "아이템"}}}
        )
    instance = factory()
    instance.session.get = _no_network
    if isinstance(instance, DataDragon):
        instance._loc = SimpleNamespace(ensure_loaded=lambda: None)
    instance.ensure_loaded()
    for entry in ddragon_cache._MEM.values():
        entry["ts"] -= ddragon_cache.DATA_TTL_S + 1
    monkeypatch.setattr(ddragon_cache, "get_json", _no_network)
    instance.ensure_loaded()
    assert instance.version == "16.17.1"
    if isinstance(instance, DataDragon):
        assert instance.resolve_champion("Ahri")["key"] == "103"
        assert instance.item_name(1001) == "아이템"
        assert instance.item_meta(1001)["name"] == "아이템"
    else:
        assert instance.champion("Ahri") == "아리"
        assert instance.item(1001) == "아이템"


def test_stale_version_is_pinned_without_refreshing_timestamp(tmp_path, monkeypatch):
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    ddragon_cache._MEM["versions"]["ts"] -= ddragon_cache.VERSION_TTL_S + 1
    old_ts = ddragon_cache._MEM["versions"]["ts"]
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        raise OSError("offline")

    dd = DataDragon()
    dd.session.get = get
    for _ in range(10):
        assert dd.version == "16.17.1"
    assert len(calls) == 1
    assert ddragon_cache.read_cache("versions", allow_stale=True)["ts"] == old_ts
    assert dd.version == "16.17.1"
    assert len(calls) == 1


@pytest.mark.parametrize("body", [[], {"error": "unavailable"}, [None]])
def test_invalid_version_response_preserves_stale_cache(body, tmp_path, monkeypatch):
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    ddragon_cache._MEM["versions"]["ts"] -= ddragon_cache.VERSION_TTL_S + 1
    session = SimpleNamespace(get=lambda *a, **kw: FakeResp(body))
    assert ddragon_cache.get_json(session, "https://example.invalid", "versions", timeout=1) == ["16.17.1"]
    assert ddragon_cache.read_cache("versions", allow_stale=True)["body"] == ["16.17.1"]


def test_champion_detail_keeps_patch_of_requested_url(tmp_path, monkeypatch):
    _minimal_ddragon_cache(monkeypatch, tmp_path, "16.17.1")
    dd = DataDragon()
    dd._loc = SimpleNamespace(ensure_loaded=lambda: None)

    def get(url, **kwargs):
        assert "/16.17.1/" in url
        ddragon_cache.write_cache("versions", ["16.18.1"])
        return FakeResp({"data": {"Ahri": {"id": "Ahri", "name": "아리"}}})

    dd.session.get = get
    detail = dd.champion_detail("Ahri")
    assert detail["_patch"] == "16.17.1"
    assert "/16.17.1/" in detail["_source_url"]
