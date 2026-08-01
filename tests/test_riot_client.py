import pytest

from lol_coach.config import InvalidPlatformError
from lol_coach.riot.client import RiotClient


@pytest.mark.parametrize(
    ("platform", "region"),
    [
        ("attacker.example#", None),
        ("na1", "attacker.example#"),
    ],
)
def test_riot_client_rejects_untrusted_routing_hosts(
    platform: str,
    region: str | None,
) -> None:
    with pytest.raises(InvalidPlatformError):
        RiotClient("RGAPI-test-only", platform=platform, region=region)


def test_set_platform_syncs_region() -> None:
    client = RiotClient("RGAPI-test-only", platform="na1")
    assert client.region == "americas"
    client.set_platform("kr")
    assert client.platform == "kr"
    assert client.region == "asia"
    with pytest.raises(InvalidPlatformError):
        client.set_platform("attacker.example#")


def test_default_region_public_api() -> None:
    assert RiotClient.default_region("kr") == "asia"
    # 하위 호환 별칭도 동일 결과
    assert RiotClient._default_region("kr") == "asia"


def _fake_match(match_id: str) -> dict:
    return {"metadata": {"matchId": match_id}, "info": {"participants": []}}


def test_match_disk_cache_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """매치 payload는 디스크에 캐시되고 두 번째 조회는 네트워크를 타지 않는다."""
    monkeypatch.setattr(
        "lol_coach.riot.client._cache_base", lambda: tmp_path
    )
    client = RiotClient("RGAPI-test-only", platform="na1")
    calls: list[str] = []

    def fake_get(url: str, params=None):
        calls.append(url)
        mid = url.rsplit("/", 1)[-1]
        return _fake_match(mid)

    monkeypatch.setattr(client, "_get", fake_get)
    first = client.get_match("KR_12345")
    assert first["metadata"]["matchId"] == "KR_12345"
    assert len(calls) == 1
    second = client.get_match("KR_12345")
    assert second == first
    assert len(calls) == 1  # 캐시 히트


def test_match_cache_disabled_skips_writes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lol_coach.riot.client._cache_base", lambda: tmp_path)
    client = RiotClient("RGAPI-test-only", platform="na1", use_cache=False)
    monkeypatch.setattr(client, "_get", lambda url, params=None: _fake_match("X_1"))
    client.get_match("X_1")
    assert not list(tmp_path.rglob("*.json"))


def test_collect_summaries_parallel_order_and_filter(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """병렬 수집도 ID 순서·큐 필터·조기 종료 규칙을 유지한다."""
    client = RiotClient("RGAPI-test-only", platform="na1", use_cache=False)
    from types import SimpleNamespace

    def fake_summary(mid: str, puuid: str):
        # 짝수 ID만 큐 450, 홀수는 420
        n = int(mid.split("_")[1])
        return SimpleNamespace(match_id=mid, queue_id=450 if n % 2 == 0 else 420)

    monkeypatch.setattr(client, "_summary_or_none", fake_summary)
    ids = [f"KR_{i}" for i in range(20)]

    all_matches = client._collect_summaries(ids, "puuid", count=10, queues=None)
    assert [m.match_id for m in all_matches] == ids[:10]  # 순서 유지 + count 제한

    aram_only = client._collect_summaries(ids, "puuid", count=3, queues={450})
    assert [m.match_id for m in aram_only] == ["KR_0", "KR_2", "KR_4"]
    assert all(m.queue_id == 450 for m in aram_only)


def test_league_entries_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RiotClient("RGAPI-test-only", platform="kr")
    payload = [
        {
            "queueType": "RANKED_SOLO_5x5",
            "tier": "GOLD",
            "rank": "II",
            "leaguePoints": 57,
            "wins": 40,
            "losses": 35,
        }
    ]
    monkeypatch.setattr(client, "_get", lambda url, params=None: payload)
    ranks = client.get_league_entries("puuid")
    assert len(ranks) == 1
    r = ranks[0]
    assert r.tier == "GOLD"
    assert r.rank == "II"
    assert r.league_points == 57
    assert r.games == 75
    assert r.winrate == round(100 * 40 / 75, 1)


def test_league_entries_unranked(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RiotClient("RGAPI-test-only", platform="kr")
    monkeypatch.setattr(client, "_get", lambda url, params=None: [])
    assert client.get_league_entries("puuid") == []
