"""blitz 디스크 캐시 — TTL 만료/네트워크 실패 시 stale 폴백."""

from __future__ import annotations

import json
import time

import pytest

from lol_coach.blitz.client import BlitzClient, _build_to_dict
from lol_coach.blitz.models import BlitzError, ChampionBuild


def _seed(client: BlitzClient, key: str, build: ChampionBuild, ts: float) -> None:
    path = client._disk_cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": ts, "payload": _build_to_dict(build)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build() -> ChampionBuild:
    return ChampionBuild(
        champion="Ahri", role="mid", patch="26.15", win_rate=51.4, source_url="x"
    )


def test_disk_fresh_within_disk_ttl(tmp_path) -> None:
    client = BlitzClient(cache_ttl=1.0, disk_ttl=3600.0)
    client._disk_dir = tmp_path
    client.cached_set("build:ahri:mid", _build_to_dict(_build()))
    client._cache = {}
    got = client.get_champion_build("Ahri", "mid")
    assert got.champion == "Ahri"
    assert got.win_rate == 51.4


def test_disk_expired_network_fail_stale_fallback(tmp_path) -> None:
    client = BlitzClient(cache_ttl=1.0, disk_ttl=10.0)
    client._disk_dir = tmp_path
    _seed(client, "build:ahri:mid", _build(), time.time() - 100)
    client._cache = {}

    def boom(*_a, **_k):
        raise BlitzError("blocked")

    client.fetch_html = boom
    got = client.get_champion_build("Ahri", "mid")
    assert got.stale_cache is True
    assert got.cache_age_s > 90
    assert got.champion == "Ahri"


def test_no_cache_network_fail_raises(tmp_path) -> None:
    client = BlitzClient(cache_ttl=1.0, disk_ttl=10.0)
    client._disk_dir = tmp_path

    def boom(*_a, **_k):
        raise BlitzError("blocked")

    client.fetch_html = boom
    with pytest.raises(BlitzError):
        client.get_champion_build("Ahri", "mid")
