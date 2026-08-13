"""상대 정찰 — 리드 칩 로직·오케스트레이션 테스트."""

from __future__ import annotations

import time
from pathlib import Path

from lol_coach.analysis.scouting import (
    PlayerScout,
    ScoutChip,
    ScoutingReport,
    build_scouting_report,
    scout_player,
    scouting_headline,
)

DAY_MS = 24 * 60 * 60 * 1000
MIN_MS = 60 * 1000


def _match(
    *,
    puuid: str,
    win: bool,
    champ: str,
    ended_at_ms: int,
    match_id: str = "",
) -> dict:
    return {
        "metadata": {"matchId": match_id or puuid + str(ended_at_ms)},
        "info": {
            "gameEndTimestamp": ended_at_ms,
            "queueId": 450,
            "participants": [
                {
                    "puuid": puuid,
                    "win": win,
                    "championName": champ,
                },
                {
                    "puuid": "other",
                    "win": not win,
                    "championName": "X",
                },
            ],
        },
    }


# ── C1: 칩 로직 ──────────────────────────────────────────


def test_scout_requires_sample_gate() -> None:
    now = int(time.time() * 1000)
    matches = [
        _match(puuid="p1", win=True, champ="Ahri", ended_at_ms=now - MIN_MS),
        _match(puuid="p1", win=False, champ="Ahri", ended_at_ms=now - 2 * MIN_MS),
    ]
    scout = scout_player("적1", "p1", matches, now_ms=now)
    assert scout.chips == ()
    assert scout.sample_games == 2


def test_scout_today_queue_chip() -> None:
    now = int(time.time() * 1000)
    matches = [
        _match(puuid="p1", win=True, champ="A", ended_at_ms=now - 10 * MIN_MS),
        _match(puuid="p1", win=False, champ="B", ended_at_ms=now - 40 * MIN_MS),
        _match(puuid="p1", win=False, champ="C", ended_at_ms=now - 90 * MIN_MS),
    ]
    scout = scout_player("적1", "p1", matches, now_ms=now)
    assert any("오늘" in c.text and "3판째" in c.text for c in scout.chips)
    assert any("1승" in c.text and "2패" in c.text for c in scout.chips)


def test_scout_bangkyu_chip() -> None:
    now = int(time.time() * 1000)
    matches = [
        _match(puuid="p1", win=False, champ="A", ended_at_ms=now - 15 * MIN_MS),
        _match(puuid="p1", win=True, champ="B", ended_at_ms=now - 60 * MIN_MS),
        _match(puuid="p1", win=True, champ="C", ended_at_ms=now - 2 * 60 * MIN_MS),
    ]
    scout = scout_player("적1", "p1", matches, now_ms=now)
    assert any("빡큐" in c.text for c in scout.chips)


def test_scout_no_bangkyu_after_win_or_later() -> None:
    now = int(time.time() * 1000)
    # 마지막 판이 승리 → 빡큐 아님
    win_last = [
        _match(puuid="p1", win=True, champ="A", ended_at_ms=now - 15 * MIN_MS),
        _match(puuid="p1", win=True, champ="B", ended_at_ms=now - 60 * MIN_MS),
        _match(puuid="p1", win=True, champ="C", ended_at_ms=now - 2 * 60 * MIN_MS),
    ]
    assert not any("빡큐" in c.text for c in scout_player("적1", "p1", win_last, now_ms=now).chips)
    # 패배였지만 25분 전 → 빡큐 아님
    old_loss = [
        _match(puuid="p1", win=False, champ="A", ended_at_ms=now - 25 * MIN_MS),
        _match(puuid="p1", win=True, champ="B", ended_at_ms=now - 60 * MIN_MS),
        _match(puuid="p1", win=True, champ="C", ended_at_ms=now - 2 * 60 * MIN_MS),
    ]
    assert not any("빡큐" in c.text for c in scout_player("적1", "p1", old_loss, now_ms=now).chips)


def test_scout_one_trick_chip() -> None:
    now = int(time.time() * 1000)
    matches = [
        _match(puuid="p1", win=True, champ="Ahri", ended_at_ms=now - (i + 1) * 60 * MIN_MS)
        for i in range(5)
    ]
    scout = scout_player("적1", "p1", matches, now_ms=now)
    assert any("원챔" in c.text and "Ahri" in c.text for c in scout.chips)


def test_scout_hot_and_cold_chips() -> None:
    now = int(time.time() * 1000)
    hot = [
        _match(puuid="p1", win=(i < 4), champ=f"C{i}", ended_at_ms=now - (i + 1) * 60 * MIN_MS)
        for i in range(5)
    ]
    cold = [
        _match(puuid="p1", win=(i >= 4), champ=f"C{i}", ended_at_ms=now - (i + 1) * 60 * MIN_MS)
        for i in range(5)
    ]
    assert any("핫" in c.text for c in scout_player("적1", "p1", hot, now_ms=now).chips)
    assert any("콜드" in c.text for c in scout_player("적1", "p1", cold, now_ms=now).chips)


def test_scout_deterministic_order() -> None:
    now = int(time.time() * 1000)
    matches = [
        _match(puuid="p1", win=(i < 3), champ=f"C{i}", ended_at_ms=now - (i + 1) * 60 * MIN_MS)
        for i in range(5)
    ]
    a = scout_player("적1", "p1", matches, now_ms=now)
    b = scout_player("적1", "p1", matches, now_ms=now)
    assert a == b


# ── C2: 오케스트레이션 + 캐시 ────────────────────────────


class FakeClient:
    def __init__(self, fail_puuids: set[str] | None = None) -> None:
        self.ids_calls: list[str] = []
        self.match_calls: list[str] = []
        self.fail = fail_puuids or set()
        self._now = int(time.time() * 1000)

    def get_match_ids(self, puuid: str, count: int = 5) -> list[str]:
        self.ids_calls.append(puuid)
        if puuid in self.fail:
            raise RuntimeError("429")
        return [f"{puuid}-{i}" for i in range(count)]

    def get_match(self, match_id: str) -> dict:
        self.match_calls.append(match_id)
        puuid, i = match_id.rsplit("-", 1)
        now = self._now
        return _match(
            puuid=puuid,
            win=(int(i) % 2 == 0),
            champ=f"C{int(i)}",
            ended_at_ms=now - (int(i) + 1) * 60 * MIN_MS,
            match_id=match_id,
        )


def _participants(n: int = 10, my_puuid: str = "me") -> list[dict]:
    out = []
    for i in range(n):
        team = 100 if i < 5 else 200
        out.append(
            {
                "puuid": my_puuid if i == 0 else f"p{i}",
                "riotId": f"닉{i}#KR1",
                "championId": 100 + i,
                "teamId": team,
            }
        )
    return out


def test_build_report_scans_others_and_caches(tmp_path: Path) -> None:
    client = FakeClient()
    cache = tmp_path / "scout_cache.json"
    now = int(time.time() * 1000)
    participants = _participants()

    report = build_scouting_report(
        client,
        participants,
        "me",
        cache_path=cache,
        now_ms=now,
        pacing_s=0.0,
    )
    assert report.scanned == 9
    assert report.skipped == 0
    assert len(report.enemy) == 5 and len(report.ally) == 4
    assert len(client.ids_calls) == 9  # 나 자신 제외
    assert len(client.match_calls) == 9 * 5  # C4: 리스트 10 이하 · 상세 9×5 이하

    # 두 번째 실행 — 캐시 TTL 내 → 리스트 호출 0
    client2 = FakeClient()
    report2 = build_scouting_report(
        client2,
        participants,
        "me",
        cache_path=cache,
        now_ms=now + 5 * MIN_MS,
        pacing_s=0.0,
    )
    assert client2.ids_calls == []
    assert report2.scanned == 9


def test_build_report_skips_failed_players(tmp_path: Path) -> None:
    client = FakeClient(fail_puuids={"p3", "p8"})
    cache = tmp_path / "scout_cache.json"
    now = int(time.time() * 1000)

    report = build_scouting_report(
        client,
        _participants(),
        "me",
        cache_path=cache,
        now_ms=now,
        pacing_s=0.0,
    )
    assert report.scanned == 7
    assert report.skipped == 2


def test_build_report_cache_expiry_refetches(tmp_path: Path) -> None:
    client = FakeClient()
    cache = tmp_path / "scout_cache.json"
    now = int(time.time() * 1000)

    build_scouting_report(client, _participants(), "me", cache_path=cache, now_ms=now, pacing_s=0.0)
    client2 = FakeClient()
    build_scouting_report(
        client2,
        _participants(),
        "me",
        cache_path=cache,
        now_ms=now + 31 * 60 * MIN_MS,
        pacing_s=0.0,
    )
    assert len(client2.ids_calls) == 9  # TTL 만료 → 재조회


def test_build_report_prefers_riot_id_over_missing_summoner_name(tmp_path: Path) -> None:
    client = FakeClient()
    participants = [
        {"puuid": "me", "riotId": "나#KR1", "championId": 1, "teamId": 100},
        {
            "puuid": "p1",
            "riotId": "적#KR1",
            "riotIdGameName": "적",
            "riotIdTagline": "KR1",
            "championId": 103,
            "teamId": 200,
        },
    ]
    report = build_scouting_report(
        client,
        participants,
        "me",
        cache_path=tmp_path / "scout_cache.json",
        now_ms=int(time.time() * 1000),
        pacing_s=0.0,
    )
    assert report.scanned == 1
    assert report.enemy[0].summoner_name == "적#KR1"
    assert "?" not in report.enemy[0].summoner_name


def test_build_report_name_falls_back_to_champion_id(tmp_path: Path) -> None:
    client = FakeClient()
    participants = [
        {"puuid": "me", "championId": 1, "teamId": 100},
        {"puuid": "p1", "championId": 103, "teamId": 200},
    ]
    report = build_scouting_report(
        client,
        participants,
        "me",
        cache_path=tmp_path / "scout_cache.json",
        now_ms=int(time.time() * 1000),
        pacing_s=0.0,
    )
    assert report.enemy[0].summoner_name == "#103"


def test_build_report_aborts_remaining_on_match_429(tmp_path: Path) -> None:
    from lol_coach.riot.client import RiotAPIError

    class LimitClient(FakeClient):
        def get_match(self, match_id: str) -> dict:
            raise RiotAPIError(429, "rate", "/match")

    client = LimitClient()
    report = build_scouting_report(
        client,
        _participants(),
        "me",
        cache_path=tmp_path / "scout_cache.json",
        now_ms=int(time.time() * 1000),
        pacing_s=0.0,
    )
    assert client.match_calls == []
    assert report.scanned == 1  # 첫 플레이어는 상세 0건이어도 스캔으로 집계
    assert report.skipped == 8


def test_scouting_headline_summary() -> None:

    def scout(name: str, chips: tuple[ScoutChip, ...]) -> PlayerScout:
        return PlayerScout(
            summoner_name=name, champion_id=1, team_id=200, chips=chips, sample_games=5
        )

    danger = ScoutingReport(
        enemy=(scout("A", (ScoutChip(kind="danger", text="빡큐"),)),),
        ally=(),
        scanned=1,
        skipped=0,
    )
    assert "빡큐" in scouting_headline(danger) or "위험" in scouting_headline(danger)
