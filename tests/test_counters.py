"""blitz 카운터 클라이언트 — fetch → 캐시 저장/재사용."""

from __future__ import annotations

import pytest
from blitz_samples import COUNTER_SAMPLE

from lol_coach.blitz.client import BlitzClient
from lol_coach.blitz.models import BlitzError, CounterPick, CounterReport, report_to_dict


def test_get_counters_caches_after_fetch(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    monkeypatch.setattr(client, "fetch_html", lambda url: COUNTER_SAMPLE)
    rep = client.get_counters("Ahri", "mid")
    assert rep.lane_counters[0].champion == "Galio"
    assert rep.lane_counters[0].gd15 == 38
    # 캐시 저장 확인 (fetch 호출 없이 재조회)
    monkeypatch.setattr(
        client, "fetch_html", lambda url: (_ for _ in ()).throw(AssertionError("캐시 사용"))
    )
    again = client.get_counters("Ahri", "mid")
    assert again.lane_counters[0].champion == "Galio"


def test_get_counters_stale_fallback(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    client.cached_set(
        "counters:ahri:mid",
        report_to_dict(
            CounterReport(
                enemy="Ahri",
                role="mid",
                patch="",
                source_url="x",
                lane_counters=[CounterPick("Galio", 38, 2896)],
            )
        ),
    )
    client._cache.clear()
    monkeypatch.setattr(
        client, "fetch_html", lambda url: (_ for _ in ()).throw(BlitzError("blocked"))
    )
    got = client.get_counters("Ahri", "mid")
    assert got.lane_counters[0].champion == "Galio"


def test_get_counters_no_cache_raises(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    monkeypatch.setattr(
        client, "fetch_html", lambda url: (_ for _ in ()).throw(BlitzError("blocked"))
    )
    with pytest.raises(BlitzError):
        client.get_counters("Ahri", "mid")
