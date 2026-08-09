"""Regression tests for the Luna review findings."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from blitz_samples import BUILD_SAMPLE, COUNTER_SAMPLE

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.blitz.client import BlitzClient, _build_to_dict
from lol_coach.blitz.models import BlitzError, ChampionBuild


def _write_cache(client: BlitzClient, key: str, payload: object, ts: float | None = None) -> None:
    path = client._disk_cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": time.time() if ts is None else ts, "payload": payload}),
        encoding="utf-8",
    )


def test_meta_aram_prints_catalog_items() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "lol_coach", "meta", "Ahri", "--mode", "aram"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "악의" in result.stdout
    assert "마법사의 신발" in result.stdout


def test_blitz_package_exports_public_types() -> None:
    from lol_coach.blitz import BlitzClient as ExportedClient
    from lol_coach.blitz import ChampionBuild as ExportedBuild

    assert ExportedClient is BlitzClient
    assert ExportedBuild is ChampionBuild


def test_malformed_counter_cache_refetches(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    _write_cache(
        client,
        "counters:ahri:mid",
        {
            "enemy": "Ahri",
            "role": "mid",
            "patch": "26.13",
            "source_url": "x",
            "lane_counters": [
                {"champion": "Galio", "gd15": "not-a-number", "matches": 2896}
            ],
            "hard_matchups": [],
        },
    )
    calls: list[str] = []
    monkeypatch.setattr(
        client,
        "fetch_html",
        lambda url: calls.append(url) or COUNTER_SAMPLE,
    )

    report = client.get_counters("Ahri", "mid")

    assert calls
    assert report.lane_counters[0].champion == "Galio"


def test_incomplete_build_cache_refetches(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    _write_cache(client, "build:ahri:mid", {"champion": "Ahri"})
    calls: list[str] = []
    monkeypatch.setattr(
        client,
        "fetch_html",
        lambda url: calls.append(url) or BUILD_SAMPLE,
    )

    build = client.get_champion_build("Ahri", "mid")

    assert calls
    assert build.patch == "26.15"


def test_use_cache_false_does_not_return_stale_cache(tmp_path, monkeypatch) -> None:
    client = BlitzClient(cache_ttl=0.01, disk_ttl=60)
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    _write_cache(
        client,
        "build:ahri:mid",
        _build_to_dict(ChampionBuild("Ahri", "mid", "26.15")),
        ts=time.time() - 1,
    )
    monkeypatch.setattr(
        client,
        "fetch_html",
        lambda url: (_ for _ in ()).throw(BlitzError("network unavailable")),
    )

    with pytest.raises(BlitzError, match="network unavailable"):
        client.get_champion_build("Ahri", "mid", use_cache=False)


def test_counter_limit_and_min_matches_apply_to_cached_results(tmp_path, monkeypatch) -> None:
    client = BlitzClient()
    monkeypatch.setattr(client, "_disk_dir", tmp_path)
    monkeypatch.setattr(client, "fetch_html", lambda url: COUNTER_SAMPLE)

    limited = client.get_counters("Ahri", "mid", limit=1, min_matches=800)
    strict = client.get_counters("Ahri", "mid", limit=10, min_matches=2000)

    assert len(limited.lane_counters) == 1
    assert [pick.champion for pick in strict.lane_counters] == ["Galio"]


def test_missing_blitz_aram_build_uses_classic_fallback() -> None:
    coach = object.__new__(MayhemCoach)

    assert coach._fallback_cores({"Mage"}) == [
        "루덴의 메아리",
        "그림자불꽃",
        "라바돈의 죽음모자",
        "공허의 지팡이",
        "존야의 모래시계",
    ]


class _FakeResponse:
    def __init__(
        self,
        url: str,
        text: str,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.text = text
        self.status_code = status_code
        self.headers = headers or {"Content-Length": str(len(text.encode()))}
        self.encoding = "utf-8"
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")
        return None

    def iter_content(self, chunk_size: int = 64 * 1024):
        raw = self.text.encode()
        for start in range(0, len(raw), chunk_size):
            yield raw[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def get(self, url: str, *, timeout: float, **kwargs: object) -> _FakeResponse:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_fetch_rejects_redirect_to_untrusted_host() -> None:
    client = BlitzClient()
    client._session = _FakeSession(
        response=_FakeResponse(
            "https://blitz.gg/lol/champions/Ahri/build",
            "",
            status_code=302,
            headers={"Location": "http://127.0.0.1:8000/private"},
        )
    )

    with pytest.raises(BlitzError, match="리디렉션|주소"):
        client.fetch_html("https://blitz.gg/lol/champions/Ahri/build?role=MID")


def test_fetch_rejects_oversized_response() -> None:
    client = BlitzClient()
    client._session = _FakeSession(
        response=_FakeResponse(
            "https://blitz.gg/lol/champions/Ahri/build",
            "x" * (5 * 1024 * 1024 + 1),
        )
    )

    with pytest.raises(BlitzError, match="너무 큽니다"):
        client.fetch_html("https://blitz.gg/lol/champions/Ahri/build?role=MID")


def test_fetch_does_not_expose_raw_network_exception() -> None:
    client = BlitzClient()
    client._session = _FakeSession(error=RuntimeError("internal.example/token"))

    with pytest.raises(BlitzError) as exc_info:
        client.fetch_html("https://blitz.gg/lol/champions/Ahri/build?role=MID")

    assert "internal.example" not in str(exc_info.value)
