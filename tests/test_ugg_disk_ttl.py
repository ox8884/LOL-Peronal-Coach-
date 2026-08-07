"""u.gg 디스크 캐시 TTL / stale 폴백."""

from __future__ import annotations

import json
import time
from pathlib import Path

from lol_coach.ugg.client import UGGClient, _build_to_dict
from lol_coach.ugg.models import ChampionBuild


def _write_disk(client: UGGClient, key: str, ts: float) -> Path:
    build = ChampionBuild(
        champion="Ahri",
        role="MID",
        patch="15.1",
        win_rate=52.0,
        source_url="https://u.gg/test",
    )
    path = client._disk_cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": ts, "build": _build_to_dict(build)}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_disk_fresh_within_disk_ttl(tmp_path: Path) -> None:
    c = UGGClient(cache_ttl=1.0, disk_ttl=3600.0)
    c._disk_dir = tmp_path
    key = "build:ahri:summoners_rift:mid"
    _write_disk(c, key, time.time())
    got = c._disk_cache_get(key)
    assert got is not None
    assert got.champion == "Ahri"


def test_disk_expired_without_stale(tmp_path: Path) -> None:
    c = UGGClient(cache_ttl=1.0, disk_ttl=10.0)
    c._disk_dir = tmp_path
    key = "build:ahri:summoners_rift:mid"
    _write_disk(c, key, time.time() - 100)
    assert c._disk_cache_get(key) is None
    stale = c._disk_cache_get(key, allow_stale=True)
    assert stale is not None
