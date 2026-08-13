# LCU 키리스 전적 폴백 & API 키 안내 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Riot API 키가 없거나 만료돼도 롤 클라이언트(LCU) 로컬 API로 내 전적·복기·킬 지도를 표시하고, 만료 시 개인 키(Personal App) 안내를 제공한다.

**Architecture:** 순수 변환 레이어(`analysis/lcu_match.py`)가 LCU v3 DTO를 기존 `MatchSummary`/타임라인 v5 형태로 바꾸고, `lcu.py`에 전적 엔드포인트 메서드를 추가하며, `me_tab`이 Riot API 실패 시 LCU 경로로 폴백한다. 기존 렌더링·분석 코드는 전부 재사용.

**Tech Stack:** Python 3.11+, requests(LCU 루프백 HTTPS), CustomTkinter, pytest, uv. LCU `/lol-match-history/v1/...` 엔드포인트.

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-08-13-lcu-match-history-design.md`
- 커밋 메시지: 한국어 + `feat:`/`fix:`/`chore:` 프리픽스
- 코드 스타일: 한국어 docstring, `from __future__ import annotations`, ruff/mypy 통과 필수
- 테스트: `uv run pytest tests -x -q` / `uv run ruff check src tests` / `uv run mypy src`
- 폴백 순서: Riot API 우선 → 실패 시 LCU → LCU도 실패하면 기존 오류 안내
- LCU는 본인 계정만 · 클라이언트 실행 중에만 · `_get`은 404를 LCUError로 던지므로 `match_timeline`만 예외→None 변환
- 상태바 문구: "로컬 전적 모드 (롤 클라이언트 전적 · API 키 불필요)"
- GUI 변경은 사용자-facing → 릴리스 세트 필요 (Task 7)

---

### Task 1: analysis/lcu_match.py — 순수 변환 레이어

**Files:**
- Create: `src/lol_coach/analysis/lcu_match.py`
- Test: `tests/test_lcu_match.py`

**Interfaces:**
- Produces:
  - `match_id_for(game_id: int, platform: str = "kr") -> str` — `f"{platform.upper()}_{game_id}"`
  - `game_id_of(match_id: str) -> int | None` — `"KR_1234567890"` → 1234567890, 파싱 불가 시 None
  - `lcu_to_match_summary(dto: dict, *, my_summoner_name: str = "", platform: str = "kr", id_to_key=None) -> MatchSummary | None` — id_to_key는 `Callable[[int], str] | None` (챔피언 id→key, 없으면 `str(id)` 폴백)
  - `lcu_to_timeline_v5(dto: dict) -> dict` — v3 타임라인 → `{"info": {"frames": [...], "participants": [...], "frameInterval": n}}`
  - `build_local_form(lcu_client, count: int, profile: PlayerProfile) -> tuple[RecentForm | None, str]` — (성공 form, 실패 사유). lcu_client는 덕타이핑 (`current_summoner_name()`, `match_history(0, count)`, `match_detail(game_id)`) — 테스트에서 fake 주입
- Consumes: `MatchSummary`, `MatchPlayer`, `PlayerProfile`, `RecentForm`, `aggregate_form` (riot.models / riot.client)

- [ ] **Step 1: 테스트 작성 (실패 확인용)**

`tests/test_lcu_match.py`:

```python
from lol_coach.analysis.lcu_match import (
    build_local_form,
    game_id_of,
    lcu_to_match_summary,
    lcu_to_timeline_v5,
    match_id_for,
)

ME = "채니미#KR1"

PLAYERS = [
    {"participantId": 1, "teamId": 100, "championId": 103, "stats": {}},
    {"participantId": 2, "teamId": 100, "championId": 64, "stats": {}},
    {"participantId": 3, "teamId": 200, "championId": 238, "stats": {}},
    {"participantId": 4, "teamId": 200, "championId": 412, "stats": {}},
]

ME_STATS = {
    "kills": 10, "deaths": 2, "assists": 8,
    "totalMinionsKilled": 180, "neutralMinionsKilled": 20,
    "goldEarned": 12000, "totalDamageDealtToChampions": 25000,
    "visionScore": 18, "win": True, "gameDuration": 1800,
    "item0": 3089, "item1": 3157, "item2": 0,
    "spell1Id": 4, "spell2Id": 7,
    "perkPrimaryStyle": 8100, "perkSubStyle": 8300,
    "totalDamageTaken": 15000, "wardsPlaced": 10, "wardsKilled": 3,
    "detectorWardsPlaced": 2, "turretKills": 1, "inhibitorKills": 0,
    "firstBloodKill": True, "largestMultiKill": 2,
    "totalTimeSpentDead": 90, "dragonKills": 0, "baronKills": 0,
    "champLevel": 16,
}


def _dto(stats: dict | None = None) -> dict:
    players = []
    for p in PLAYERS:
        cp = dict(p)
        if p["participantId"] == 1:
            cp["stats"] = stats if stats is not None else ME_STATS
            cp["timeline"] = {"lane": "MID", "role": "SOLO"}
        else:
            cp["stats"] = {
                "kills": 0, "deaths": 0, "assists": 0,
                "totalMinionsKilled": 0, "neutralMinionsKilled": 0,
                "goldEarned": 0, "totalDamageDealtToChampions": 0,
                "visionScore": 0, "win": False, "gameDuration": 1800,
                "champLevel": 10,
            }
            cp["timeline"] = {"lane": "NONE", "role": "NONE"}
        players.append(cp)
    return {
        "gameId": 5614132333,
        "queueId": 420,
        "gameDuration": 1800,
        "gameCreation": 1785724798858,
        "gameVersion": "16.15.801.3452",
        "gameMode": "CLASSIC",
        "participantIdentities": [
            {"participantId": 1, "player": {"summonerName": "채니미"}},
            {"participantId": 2, "player": {"summonerName": "팀원1"}},
            {"participantId": 3, "player": {"summonerName": "적1"}},
            {"participantId": 4, "player": {"summonerName": "적2"}},
        ],
        "participants": players,
    }


def test_match_id_for_and_game_id_of() -> None:
    assert match_id_for(5614132333) == "KR_5614132333"
    assert match_id_for(5614132333, platform="na1") == "NA1_5614132333"
    assert game_id_of("KR_5614132333") == 5614132333
    assert game_id_of("NA1_123") == 123
    assert game_id_of("garbage") is None


def test_lcu_to_match_summary_maps_core_fields() -> None:
    ms = lcu_to_match_summary(_dto(), my_summoner_name="채니미")

    assert ms is not None
    assert ms.match_id == "KR_5614132333"
    assert ms.champion_id == 103
    assert ms.champion_name == "103"  # id_to_key 없으면 str(id) 폴백
    assert ms.role == "MIDDLE"
    assert ms.lane == "MID"
    assert ms.win is True
    assert ms.kills == 10 and ms.deaths == 2 and ms.assists == 8
    assert ms.cs == 200
    assert ms.gold == 12000
    assert ms.damage_to_champs == 25000
    assert ms.vision_score == 18
    assert ms.game_duration_s == 1800
    assert ms.queue_id == 420
    assert ms.game_version == "16.15.801.3452"
    assert ms.game_end_timestamp == 1785724798858
    assert ms.items[:2] == [3089, 3157]
    assert ms.summoner_spells == [4, 7]
    assert ms.primary_rune == 8100
    assert ms.champ_level == 16
    assert ms.first_blood is True
    assert ms.largest_multi_kill == 2
    assert ms.time_dead_s == 90
    assert ms.wards_placed == 10
    assert len(ms.ally_team) == 2 and len(ms.enemy_team) == 2
    assert any(p.is_me for p in ms.ally_team)


def test_lcu_to_match_summary_uses_id_to_key() -> None:
    ms = lcu_to_match_summary(
        _dto(),
        my_summoner_name="채니미",
        id_to_key=lambda cid: {103: "Ahri", 64: "LeeSin", 238: "Zed", 412: "Thresh"}[cid],
    )
    assert ms is not None
    assert ms.champion_name == "Ahri"
    assert {p.champion_name for p in ms.enemy_team} == {"Zed", "Thresh"}


def test_lcu_to_match_summary_returns_none_without_me() -> None:
    assert lcu_to_match_summary(_dto(), my_summoner_name="없는사람") is None
    assert lcu_to_match_summary({"gameId": 0}, my_summoner_name="채니미") is None


def test_lcu_to_timeline_v5_wraps_frames() -> None:
    dto = {
        "frameInterval": 60000,
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 500, "y": 500}},
                    "3": {"position": {"x": 7000, "y": 7000}},
                },
                "events": [
                    {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 7000, "y": 7000}},
                ],
            }
        ],
    }
    v5 = lcu_to_timeline_v5(dto)
    assert v5["info"]["frameInterval"] == 60000
    assert len(v5["info"]["frames"]) == 1
    assert v5["info"]["frames"][0]["events"][0]["type"] == "CHAMPION_KILL"


def test_lcu_timeline_feeds_killmap() -> None:
    from lol_coach.analysis.killmap import build_kill_map

    match = {
        "info": {
            "participants": [
                {"participantId": 1, "teamId": 100, "championId": 103, "championName": "Ahri"},
                {"participantId": 2, "teamId": 100, "championId": 64, "championName": "LeeSin"},
                {"participantId": 3, "teamId": 200, "championId": 238, "championName": "Zed"},
                {"participantId": 4, "teamId": 200, "championId": 412, "championName": "Thresh"},
            ]
        }
    }
    tl_dto = {
        "frameInterval": 60000,
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"position": {"x": 1000, "y": 1000}},
                    "2": {"position": {"x": 2000, "y": 1000}},
                    "3": {"position": {"x": 7000, "y": 7000}},
                    "4": {"position": {"x": 7100, "y": 6900}},
                },
                "events": [
                    {"type": "CHAMPION_KILL", "timestamp": 30000, "killerId": 3, "victimId": 1, "position": {"x": 1500, "y": 1500}},
                    {"type": "CHAMPION_KILL", "timestamp": 35000, "killerId": 1, "victimId": 4, "position": {"x": 6900, "y": 7000}},
                    {"type": "CHAMPION_KILL", "timestamp": 40000, "killerId": 4, "victimId": 2, "position": {"x": 4000, "y": 3000}},
                    {"type": "CHAMPION_KILL", "timestamp": 55000, "killerId": 3, "victimId": 1, "position": {"x": 7200, "y": 6800}},
                ],
            }
        ],
    }
    data = build_kill_map(lcu_to_timeline_v5(tl_dto), match, my_participant_id=1)
    assert len(data.my_deaths) == 2
    assert len(data.my_kills) == 1
    assert data.collapse is not None and data.collapse.timestamp == 55000


def test_build_local_form_collects_recent_matches() -> None:
    from types import SimpleNamespace

    from lol_coach.riot.models import PlayerProfile

    class FakeLCU:
        def current_summoner_name(self) -> str:
            return "채니미"

        def match_history(self, beg_index: int, end_index: int) -> list[dict]:
            assert beg_index == 0 and end_index == 15
            return [{"gameId": 1}, {"gameId": 2}, {"gameId": 0}]

        def match_detail(self, game_id: int):
            return _dto()

    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")
    form, err = build_local_form(FakeLCU(), 15, profile)
    assert err == ""
    assert form is not None and form.games == 2
    assert all(m.match_id in ("KR_1", "KR_2") for m in form.matches)


def test_build_local_form_reports_error_when_lcu_empty() -> None:
    from types import SimpleNamespace

    from lol_coach.riot.models import PlayerProfile

    class FakeLCU:
        def current_summoner_name(self) -> str:
            return "채니미"

        def match_history(self, beg_index: int, end_index: int) -> list[dict]:
            return []

        def match_detail(self, game_id: int):
            raise AssertionError("호출되면 안 됨")

    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")
    form, err = build_local_form(FakeLCU(), 15, profile)
    assert form is None
    assert "전적이 없습니다" in err
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_lcu_match.py -v`
Expected: FAIL (ModuleNotFoundError: lol_coach.analysis.lcu_match)

- [ ] **Step 3: 구현**

`src/lol_coach/analysis/lcu_match.py`:

```python
"""LCU 로컬 전적(v3 DTO) → 기존 모델 변환 (순수 레이어, GUI 의존 없음).

롤 클라이언트의 /lol-match-history/v1/... 응답은 match-v3 스타일 DTO다.
여기서 MatchSummary·killmap용 타임라인 형태로 바꿔 기존 렌더링·분석
코드를 그대로 재사용한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lol_coach.riot.client import aggregate_form
from lol_coach.riot.models import (
    MatchPlayer,
    MatchSummary,
    PlayerProfile,
    RecentForm,
)

_ROLE_MAP = {
    "MID": "MIDDLE",
    "MIDDLE": "MIDDLE",
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "BOTTOM": "BOTTOM",
    "BOT": "BOTTOM",
    "DUO_CARRY": "BOTTOM",
    "DUO_SUPPORT": "UTILITY",
    "SUPPORT": "UTILITY",
    "NONE": "UNKNOWN",
}


def match_id_for(game_id: int, platform: str = "kr") -> str:
    """LCU gameId → Riot 매치 ID 형식 (예: KR_5614132333)."""
    return f"{(platform or 'kr').upper()}_{int(game_id)}"


def game_id_of(match_id: str) -> int | None:
    """Riot 매치 ID("KR_123") → LCU gameId(123). 파싱 불가 시 None."""
    try:
        platform, _, game_id = str(match_id).partition("_")
        if not platform or not game_id:
            return None
        return int(game_id)
    except (TypeError, ValueError):
        return None


def _identity_map(dto: dict) -> dict[int, str]:
    out: dict[int, str] = {}
    for p in dto.get("participantIdentities") or []:
        if not isinstance(p, dict):
            continue
        player = p.get("player") or {}
        name = str(player.get("summonerName") or "")
        pid = int(p.get("participantId") or 0)
        if pid and name:
            out[pid] = name
    return out


def _num(stats: dict, key: str) -> int:
    try:
        return int(stats.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _player_from(
    p: dict,
    *,
    my_name: str,
    my_team_id: int,
    id_to_key: Callable[[int], str] | None,
) -> MatchPlayer:
    s = p.get("stats") or {}
    name = my_name
    return MatchPlayer(
        champion_name=(id_to_key(int(p.get("championId") or 0)) if id_to_key else str(p.get("championId") or 0)),
        champion_id=int(p.get("championId") or 0),
        role=str(p.get("timeline") or {}).get("lane") if isinstance(p.get("timeline"), dict) else "UNKNOWN",
        team_id=int(p.get("teamId") or 0),
        kills=_num(s, "kills"),
        deaths=_num(s, "deaths"),
        assists=_num(s, "assists"),
        cs=_num(s, "totalMinionsKilled") + _num(s, "neutralMinionsKilled"),
        gold=_num(s, "goldEarned"),
        damage_to_champs=_num(s, "totalDamageDealtToChampions"),
        vision_score=_num(s, "visionScore"),
        champ_level=_num(s, "champLevel"),
        is_me=bool(name == my_name),
        win=bool(s.get("win")),
    )


def lcu_to_match_summary(
    dto: dict,
    *,
    my_summoner_name: str = "",
    platform: str = "kr",
    id_to_key: Callable[[int], str] | None = None,
) -> MatchSummary | None:
    """LCU match DTO → MatchSummary. 본인 식별 불가면 None."""
    game_id = int(dto.get("gameId") or 0)
    if not game_id:
        return None
    participants = [p for p in (dto.get("participants") or []) if isinstance(p, dict)]
    if not participants:
        return None
    names = _identity_map(dto)
    if not my_summoner_name:
        return None
    me_p = next(
        (
            p
            for p in participants
            if names.get(int(p.get("participantId") or 0)) == my_summoner_name
        ),
        None,
    )
    if me_p is None:
        return None
    my_team = int(me_p.get("teamId") or 0)
    s = me_p.get("stats") or {}
    tl = me_p.get("timeline") if isinstance(me_p.get("timeline"), dict) else {}
    lane_raw = str(tl.get("lane") or "NONE").upper()

    ally: list[MatchPlayer] = []
    enemy: list[MatchPlayer] = []
    for p in participants:
        if int(p.get("participantId") or 0) == int(me_p.get("participantId") or 0):
            continue
        name = names.get(int(p.get("participantId") or 0), "")
        mp = _player_from(p, my_name=name, my_team_id=my_team, id_to_key=id_to_key)
        (ally if mp.team_id == my_team else enemy).append(mp)

    me_pid = int(me_p.get("participantId") or 0)
    team_kills = sum(a.kills for a in ally) + _num(s, "kills")
    kp = (
        (_num(s, "kills") + _num(s, "assists")) / team_kills
        if team_kills > 0
        else None
    )
    team_dmg = sum(a.damage_to_champs for a in ally) + _num(s, "totalDamageDealtToChampions")
    dmg_share = _num(s, "totalDamageDealtToChampions") / team_dmg if team_dmg > 0 else None

    return MatchSummary(
        match_id=match_id_for(game_id, platform=platform),
        champion_name=(id_to_key(int(me_p.get("championId") or 0)) if id_to_key else str(me_p.get("championId") or 0)),
        champion_id=int(me_p.get("championId") or 0),
        role=_ROLE_MAP.get(lane_raw, lane_raw if lane_raw else "UNKNOWN"),
        lane=lane_raw,
        win=bool(s.get("win")),
        kills=_num(s, "kills"),
        deaths=_num(s, "deaths"),
        assists=_num(s, "assists"),
        cs=_num(s, "totalMinionsKilled") + _num(s, "neutralMinionsKilled"),
        gold=_num(s, "goldEarned"),
        damage_to_champs=_num(s, "totalDamageDealtToChampions"),
        vision_score=_num(s, "visionScore"),
        game_duration_s=_num(s, "gameDuration") or int(dto.get("gameDuration") or 0),
        queue_id=int(dto.get("queueId") or 0),
        items=[_num(s, f"item{i}") for i in range(7) if _num(s, f"item{i}")],
        summoner_spells=[_num(s, "spell1Id"), _num(s, "spell2Id")],
        primary_rune=_num(s, "perkPrimaryStyle") or None,
        raw_participant={"participantId": me_pid},
        team_id=my_team,
        champ_level=_num(s, "champLevel"),
        damage_taken=_num(s, "totalDamageTaken"),
        kill_participation=kp,
        damage_share=dmg_share,
        wards_placed=_num(s, "wardsPlaced"),
        wards_killed=_num(s, "wardsKilled"),
        control_wards=_num(s, "detectorWardsPlaced"),
        turret_kills=_num(s, "turretKills"),
        first_blood=bool(s.get("firstBloodKill")),
        largest_multi_kill=_num(s, "largestMultiKill"),
        total_team_kills=team_kills,
        ally_team=ally,
        enemy_team=enemy,
        game_mode=str(dto.get("gameMode") or ""),
        game_version=str(dto.get("gameVersion") or ""),
        game_end_timestamp=int(dto.get("gameCreation") or 0),
        time_dead_s=_num(s, "totalTimeSpentDead"),
        dragon_takedowns=_num(s, "dragonKills"),
        baron_takedowns=_num(s, "baronKills"),
    )


def lcu_to_timeline_v5(dto: dict) -> dict:
    """LCU v3 타임라인 → killmap이 쓰는 v5 형태로 래핑."""
    return {
        "info": {
            "frameInterval": dto.get("frameInterval", 60000),
            "frames": dto.get("frames") or [],
            "participants": dto.get("participants") or [],
        }
    }


def build_local_form(
    lcu_client: Any,
    count: int,
    profile: PlayerProfile,
) -> tuple[RecentForm | None, str]:
    """LCU에서 최근 전적을 모아 RecentForm 구성. 실패 시 (None, 사유)."""
    try:
        my_name = lcu_client.current_summoner_name()
        games = lcu_client.match_history(0, count)
    except Exception as exc:
        return None, f"롤 클라이언트 전적 조회 실패: {exc}"
    if not games:
        return None, "롤 클라이언트에 저장된 전적이 없습니다 (클라이언트에서 전적을 확인해 보세요)."

    summaries: list[MatchSummary] = []
    for g in games:
        if not isinstance(g, dict):
            continue
        gid = int(g.get("gameId") or 0)
        if not gid:
            continue
        try:
            detail = lcu_client.match_detail(gid)
        except Exception:
            continue
        ms = lcu_to_match_summary(detail, my_summoner_name=my_name)
        if ms is not None:
            summaries.append(ms)
    if not summaries:
        return None, "로컬 전적을 불러오지 못했습니다 (본인 계정으로 로그인돼 있나요?)."
    return aggregate_form(profile, summaries), ""
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_lcu_match.py -v`
Expected: 8 passed

Run: `uv run ruff check src/lol_coach/analysis/lcu_match.py tests/test_lcu_match.py`
Expected: All checks passed

- [ ] **Step 5: 커밋**

```bash
git add src/lol_coach/analysis/lcu_match.py tests/test_lcu_match.py
git commit -m "feat: LCU v3 DTO → MatchSummary·타임라인 변환 레이어"
```

---

### Task 2: lcu.py — 전적 엔드포인트 메서드

**Files:**
- Modify: `src/lol_coach/lcu.py` (LCUClient 클래스에 메서드 추가, `parse_match_history` 순수 함수 추가)
- Test: `tests/test_lcu.py` (테스트 추가)

**Interfaces:**
- Produces: `LCUClient.current_summoner_name() -> str`, `LCUClient.match_history(beg_index=0, end_index=20) -> list[dict]`, `LCUClient.match_detail(game_id: int) -> dict`, `LCUClient.match_timeline(game_id: int) -> dict | None` (404/오류 → None), `parse_match_history(data: Any) -> list[dict]`
- Consumes: Task 1의 `build_local_form`이 위 메서드 사용 (덕타이핑)

- [ ] **Step 1: 테스트 추가**

`tests/test_lcu.py` 하단에 추가 (기존 import 확인 후):

```python
from lol_coach.lcu import LCUClient, parse_match_history


def test_parse_match_history_variants() -> None:
    nested = {"games": {"games": [{"gameId": 1}, {"gameId": 2}], "gameCount": 2}}
    assert [g["gameId"] for g in parse_match_history(nested)] == [1, 2]

    flat = {"games": [{"gameId": 3}]}
    assert [g["gameId"] for g in parse_match_history(flat)] == [3]

    assert parse_match_history({"games": {"games": []}}) == []
    assert parse_match_history({}) == []
    assert parse_match_history("bad") == []
    # gameId 없는 항목은 걸러낸다
    assert [g["gameId"] for g in parse_match_history({"games": [{"gameId": 0}, {"gameId": 5}]})] == [5]


def test_match_history_and_timeline_methods(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(self, path: str):
        calls.append(path)
        if path.startswith("/lol-match-history/v1/products"):
            return {"games": {"games": [{"gameId": 9}]}}
        if path.startswith("/lol-match-history/v1/games/9"):
            return {"gameId": 9, "participants": []}
        if path.startswith("/lol-match-history/v1/game-timelines/9"):
            return {"frames": []}
        raise AssertionError(f"unexpected path {path}")

    from lol_coach import lcu as lcu_mod

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert [g["gameId"] for g in client.match_history(0, 10)] == [9]
    assert client.match_detail(9)["gameId"] == 9
    assert client.match_timeline(9) == {"frames": []}


def test_match_timeline_returns_none_on_404(monkeypatch) -> None:
    from lol_coach import lcu as lcu_mod
    from lol_coach.lcu import LCUClient, LCUError

    def fake_get(self, path: str):
        raise LCUError("엔드포인트 없음(404): " + path)

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert client.match_timeline(9) is None


def test_current_summoner_name(monkeypatch) -> None:
    from lol_coach.lcu import LCUClient

    def fake_get(self, path: str):
        return {"displayName": "채니미"}

    client = LCUClient.__new__(LCUClient)
    monkeypatch.setattr(LCUClient, "_get", fake_get)

    assert client.current_summoner_name() == "채니미"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_lcu.py::test_parse_match_history_variants -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 구현**

`src/lol_coach/lcu.py`의 `champ_select` 메서드 뒤(클래스 끝)에 추가:

```python
    def current_summoner_name(self) -> str:
        """현재 로그인한 소환사 표시 이름 (로컬 전적 is_me 판정용)."""
        try:
            data = self._get("/lol-summoner/v1/current-summoner")
        except LCUError:
            return ""
        return str((data or {}).get("displayName") or "")

    def match_history(self, beg_index: int = 0, end_index: int = 20) -> list[dict]:
        """현재 계정의 최근 경기 목록 (클라이언트 캐시, 본인만)."""
        data = self._get(
            "/lol-match-history/v1/products/lol/current-summoner/matches"
            f"?begIndex={int(beg_index)}&endIndex={int(end_index)}"
        )
        return parse_match_history(data)

    def match_detail(self, game_id: int) -> dict:
        """경기 상세 (match-v3 스타일 DTO)."""
        data = self._get(f"/lol-match-history/v1/games/{int(game_id)}")
        if not isinstance(data, dict):
            raise LCUError("매치 상세 응답이 올바르지 않습니다")
        return data

    def match_timeline(self, game_id: int) -> dict | None:
        """타임라인 — 클라이언트 버전에 따라 404일 수 있어 None 폴백."""
        try:
            data = self._get(f"/lol-match-history/v1/game-timelines/{int(game_id)}")
        except LCUError:
            return None
        return data if isinstance(data, dict) else None
```

`parse_match_history`는 클래스 밖 모듈 레벨 함수로 `parse_champ_select` 옆에 추가:

```python
def parse_match_history(data: Any) -> list[dict]:
    """전적 목록 응답 파싱 — games.games 중첩/평면/빈 응답 방어."""
    if not isinstance(data, dict):
        return []
    games = data.get("games")
    if isinstance(games, dict):
        games = games.get("games")
    if not isinstance(games, list):
        return []
    return [g for g in games if isinstance(g, dict) and g.get("gameId")]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_lcu.py -v`
Expected: 기존 + 신규 5개 전부 passed

- [ ] **Step 5: 커밋**

```bash
git add src/lol_coach/lcu.py tests/test_lcu.py
git commit -m "feat: LCU 전적 엔드포인트 — 목록·상세·타임라인(프로빙)"
```

---

### Task 3: me_tab._load_me 폴백 통합

**Files:**
- Modify: `src/lol_coach/gui/me_tab.py` (`_load_me` 약 504-603행, 키 없음 분기 약 514-522행)
- Test: `tests/test_me_lcu_fallback.py` (신규 — 폴백 분기 순수 로직 중심)

**Interfaces:**
- Consumes: Task 1 `build_local_form`, Task 2 LCUClient 메서드
- Produces: `self._me_local_mode: bool` (세션 플래그 — Task 5가 사용), 상태바 "로컬 전적 모드 (롤 클라이언트 전적 · API 키 불필요)"

- [ ] **Step 1: 폴백 헬퍼 테스트**

`tests/test_me_lcu_fallback.py`:

```python
from types import SimpleNamespace

from lol_coach.analysis.lcu_match import build_local_form
from lol_coach.riot.models import PlayerProfile


def _fake_lcu(games: list[dict], details: dict[int, dict]):
    class FakeLCU:
        def current_summoner_name(self):
            return "채니미"

        def match_history(self, beg_index, end_index):
            return games

        def match_detail(self, game_id):
            return details[game_id]

    return FakeLCU()


def test_local_form_via_fake_lcu() -> None:
    dto = {
        "gameId": 7,
        "queueId": 420,
        "gameDuration": 1500,
        "gameCreation": 1785724798858,
        "gameVersion": "16.15",
        "gameMode": "CLASSIC",
        "participantIdentities": [
            {"participantId": 1, "player": {"summonerName": "채니미"}},
            {"participantId": 2, "player": {"summonerName": "적"}},
        ],
        "participants": [
            {
                "participantId": 1,
                "teamId": 100,
                "championId": 103,
                "timeline": {"lane": "MID", "role": "SOLO"},
                "stats": {
                    "kills": 3, "deaths": 5, "assists": 7,
                    "totalMinionsKilled": 120, "neutralMinionsKilled": 0,
                    "goldEarned": 9000, "totalDamageDealtToChampions": 18000,
                    "visionScore": 10, "win": False, "gameDuration": 1500,
                    "champLevel": 13,
                },
            },
            {
                "participantId": 2,
                "teamId": 200,
                "championId": 238,
                "timeline": {"lane": "MID", "role": "SOLO"},
                "stats": {
                    "kills": 8, "deaths": 2, "assists": 4,
                    "totalMinionsKilled": 150, "neutralMinionsKilled": 0,
                    "goldEarned": 12000, "totalDamageDealtToChampions": 24000,
                    "visionScore": 12, "win": True, "gameDuration": 1500,
                    "champLevel": 14,
                },
            },
        ],
    }
    lcu = _fake_lcu([{"gameId": 7}], {7: dto})
    profile = PlayerProfile(game_name="채니미", tag_line="KR1", puuid="", platform="kr")

    form, err = build_local_form(lcu, 15, profile)

    assert err == ""
    assert form is not None
    assert form.games == 1
    m = form.matches[0]
    assert m.match_id == "KR_7"
    assert m.win is False
    assert m.deaths == 5
    assert len(m.ally_team) == 0  # 본인 제외 아군 없음
    assert len(m.enemy_team) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_me_lcu_fallback.py -v`
Expected: FAIL (ModuleNotFoundError — 신규 테스트 파일이므로 실제로는 Task 1·2가 선행돼 통과할 수 있음. 이 경우 실패 확인 단계를 생략하고 Step 4로 진행)

- [ ] **Step 3: `_load_me` 수정**

`src/lol_coach/gui/me_tab.py`의 `_load_me`에서:

1. 키 없음 분기(약 514-522행) 교체:

```python
        key = self.api_key_var.get().strip()
        platform = self.platform_var.get().strip() or DEFAULT_PLATFORM
        if not key:
            # 키 없음 → 로컬 전적 모드로 즉시 시도
            self._load_me_local(count=None, platform=platform)
            return
```

기존 `platform = ...` 줄이 아래에 있으므로 중복 제거에 주의 — 원래 코드의
`platform = self.platform_var.get().strip() or DEFAULT_PLATFORM` 줄을 위로 올리고,
아래에 있던 기존 줄을 삭제한다.

2. `work()` 함수의 예외 분기 교체 (RiotAPIError/Exception 두 개 모두 LCU 폴백 시도):

```python
            except RiotAPIError as e:
                from lol_coach.gui.errors import format_user_error

                key_problem = getattr(e, "status_code", None) == 403

                def finish_riot_error() -> None:
                    self._load_me_local(count=count, platform=platform, key_problem=key_problem, fallback_msg=format_user_error(e))
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

                self._schedule_me_load(load_gen, finish_riot_error)
            except Exception as e:
                from lol_coach.gui.errors import format_user_error

                def finish_error() -> None:
                    self._load_me_local(count=count, platform=platform, fallback_msg=format_user_error(e))
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

                self._schedule_me_load(load_gen, finish_error)
```

3. 성공 경로에 `self._me_local_mode = False` 추가 (`self.riot = client` 줄 옆):

```python
                        self.riot = client
                        self._me_local_mode = False
                        self.profile = profile
```

- [ ] **Step 4: `_load_me_local` 메서드 추가**

`_me_err` 정의 바로 앞에 추가:

```python
    def _load_me_local(
        self,
        *,
        count: int | None,
        platform: str,
        key_problem: bool = False,
        fallback_msg: str = "",
    ) -> None:
        """Riot API 없이 LCU 로컬 전적으로 전적 로드 (폴백 경로).

        key_problem: 403 만료 등 키 문제로 넘어온 경우 (개인 키 안내 다이얼로그).
        """
        from lol_coach.analysis.lcu_match import build_local_form
        from lol_coach.lcu import LCUClient, LCUError
        from lol_coach.riot.models import PlayerProfile

        if count is None:
            try:
                count = int(self.count_var.get())
            except (TypeError, ValueError):
                count = 15
        count = min(max(count, 5), 50)
        load_gen = int(getattr(self, "_me_load_gen", 0)) + 1
        self._me_load_gen = load_gen
        name, tag = self.riot_id_var.get().split("#", 1)

        def work() -> None:
            local_err = ""
            form = None
            try:
                lcu = LCUClient()
                profile = PlayerProfile(
                    game_name=name.strip(),
                    tag_line=tag.strip(),
                    puuid="",
                    platform=platform,
                )
                form, local_err = build_local_form(lcu, count, profile)
            except LCUError as exc:
                local_err = str(exc)
            except Exception as exc:
                local_err = str(exc)

            def finish() -> None:
                try:
                    if form is not None:
                        self._me_local_mode = True
                        self.riot = None  # 로컬 모드 — Riot API 워처 중지/미시작
                        self.profile = PlayerProfile(
                            game_name=name.strip(),
                            tag_line=tag.strip(),
                            puuid="",
                            platform=platform,
                        )
                        self.form = form
                        self._me_form_full = form
                        self._last_ranks = []
                        from lol_coach.analysis.growth import load_growth

                        growth, practice = load_growth(
                            form, now_ms=int(time.time() * 1000)
                        )
                        self._growth_report = growth
                        self._practice_progress = practice
                        self._render_me(form, [])
                        self._prefetch_match_icons(form)
                        mode_text = "로컬 전적 모드 (롤 클라이언트 전적 · API 키 불필요)"
                        if key_problem:
                            mode_text += " — Riot API 키 문제로 전환됨"
                        self.status.configure(text=mode_text)
                        if key_problem:
                            self._maybe_show_personal_key_dialog()
                    else:
                        msg = local_err or fallback_msg or "전적을 불러오지 못했습니다."
                        self._me_err(msg)
                        if key_problem and not local_err:
                            self._maybe_show_personal_key_dialog()
                finally:
                    self._busy_set(False, self.me_btn, "전적 로드", key="me_load")

            self._schedule_me_load(load_gen, finish)

        threading.Thread(target=work, daemon=True).start()
```

- [ ] **Step 5: `_maybe_show_personal_key_dialog` 추가**

`_load_me_local` 바로 아래에 추가 (Task 4에서 호출되지 않도록 여기서 완결):

```python
    def _maybe_show_personal_key_dialog(self) -> None:
        """개인 키(Personal App) 안내 — 세션당 1회."""
        if getattr(self, "_personal_key_dialog_shown", False):
            return
        self._personal_key_dialog_shown = True
        try:
            from tkinter import messagebox

            messagebox.showinfo(
                "Riot API 키 안내",
                "개발용(Development) 키는 24시간마다 만료됩니다.\n\n"
                "developer.riotgames.com 에서 앱을 'Personal' 유형으로 등록하면\n"
                "만료 없이 장기간 사용할 수 있는 개인 키를 받을 수 있어요.\n\n"
                "지금은 키 없이도 롤 클라이언트 전적으로 계속 사용 중입니다.",
            )
        except Exception:
            pass
```

- [ ] **Step 6: 키 없음 시 기존 messagebox 제거 확인**

키 없음 분기가 `_load_me_local`로 대체됐으므로 기존 `messagebox.askyesno("API 키가 없어요", ...)` 블록이 완전히 제거됐는지 확인 (Step 3의 교체가 완료되면 없어야 함).

- [ ] **Step 7: 회귀 확인**

Run: `uv run pytest tests/test_me_lcu_fallback.py tests/test_lcu_match.py tests/test_lcu.py -v`
Expected: 전부 passed

Run: `uv run pytest tests -x -q; uv run ruff check src tests; uv run mypy src`
Expected: 전체 통과

- [ ] **Step 8: 커밋**

```bash
git add src/lol_coach/gui/me_tab.py tests/test_me_lcu_fallback.py
git commit -m "feat: API 키 없음·실패 시 LCU 로컬 전적 폴백 + 개인 키 다이얼로그"
```

---

### Task 4: 키 만료 안내 — 도움말·만료 힌트 개선

**Files:**
- Modify: `src/lol_coach/gui/api_help.py` (HELP_BODY 문구)
- Modify: `src/lol_coach/config.py` (`api_key_expiry_hint`)
- Test: `tests/test_api_key_age.py` (힌트 기대값 갱신)

**Interfaces:**
- Consumes: 없음 (Task 3의 다이얼로그는 이미 완결됨)
- Produces: 개인 키(Personal) 우선 안내가 담긴 HELP_BODY, 개인 키 기준 만료 힌트

- [ ] **Step 1: 테스트 갱신**

`tests/test_api_key_age.py`의 `test_api_key_expiry_hint_old`를 아래로 교체 (문구 변경 반영):

```python
def test_api_key_expiry_hint_old(monkeypatch) -> None:
    monkeypatch.setenv("RIOT_API_KEY_SAVED_AT", "2020-01-01T00:00:00Z")
    hint = config.api_key_expiry_hint()
    assert "재발급" in hint or "Personal" in hint
```

- [ ] **Step 2: api_help.py HELP_BODY 교체**

`src/lol_coach/gui/api_help.py`의 HELP_BODY 내 아래 두 블록을 정확히 교체:

① "④ 페이지에 보이는 키 종류 안내" 블록 (현재 텍스트):

```
④ 페이지에 보이는 키 종류 안내
   · Development API Key  /  Personal API Key
   · 둘 다 개인 연습·친구 공유용으로 쓰는 개발용 키입니다
   · 앱 등록(제품 승인) 없이 바로 쓸 수 있는 키를 고르세요
   · 화면에 "Personal API Key" 또는 "Development API Key" 가
     보이면 그것을 사용하면 됩니다
   · (Production / App Registration 키는 나중에 회사·서비스용)
```

교체 후:

```
④ 페이지에 보이는 키 종류 안내
   · Development API Key  /  Personal API Key
   · ★ Personal API Key 를 고르세요 — 만료 없이 장기 사용 가능
   · Development 키는 24시간마다 만료돼 매번 재발급해야 합니다
   · Personal 키가 안 보이면 [Register App]에서 Personal로
     등록 후 생성된 키를 사용하세요
   · (Production / App Registration 키는 나중에 회사·서비스용)
```

② "자주 하는 실수"의 만료 줄 (현재):

```
· 24시간이 지나 만료됨 → 같은 페이지에서 다시 발급(Regenerate)
```

교체 후:

```
· 24시간이 지나 만료됨 → Personal 키를 쓰면 다시 발급할 일이 없어요
```

③ "키 만료되면?" 섹션 (현재):

```
개발용 키는 보통 24시간마다 만료됩니다.
다시 developer.riotgames.com → Dashboard → 새 키 복사 →
앱의 [내 전적] 탭에서 API 키를 바꿔 저장하면 됩니다.
```

교체 후:

```
개발용 키는 보통 24시간마다 만료됩니다.
다시 developer.riotgames.com → Dashboard → 새 키 복사 →
앱의 [내 전적] 탭에서 API 키를 바꿔 저장하면 됩니다.

개인용(Personal) 키를 쓰면 만료 걱정이 없습니다.
또한 키가 없거나 만료돼도 이 앱은 롤 클라이언트(LCU) 로컬
전적 모드로 계속 사용할 수 있습니다 — 클라이언트만 켜져 있으면 됩니다.
```

- [ ] **Step 3: config.py 만료 힌트 개선**

`src/lol_coach/config.py`의 `api_key_expiry_hint`를 아래로 교체:

```python
def api_key_expiry_hint() -> str:
    """UI 상태바용 짧은 안내. 문제 없으면 빈 문자열."""
    age = api_key_age_seconds()
    if age is None:
        return ""
    hours = age / 3600.0
    if hours >= 24:
        return "⚠ Riot API 키가 24시간 경과 — 개발 키는 만료됐을 수 있음 · Personal 키 권장"
    if hours >= 22:
        left = max(0, 24 - hours)
        return f"⏳ 개발 키라면 약 {left:.1f}시간 후 만료 · Personal 키 권장"
    return ""
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_api_key_age.py -v; uv run pytest tests -x -q`
Expected: 전부 passed

Run: `uv run ruff check src tests; uv run mypy src`
Expected: clean

- [ ] **Step 5: 커밋**

```bash
git add src/lol_coach/gui/api_help.py src/lol_coach/config.py tests/test_api_key_age.py
git commit -m "feat: 개인 키(Personal) 안내 — 도움말·만료 힌트 개선"
```

---

### Task 5: 킬 지도·타임라인 LCU 폴백

**Files:**
- Modify: `src/lol_coach/analysis/lcu_match.py` (`try_local_timeline` 추가)
- Modify: `src/lol_coach/gui/me_tab.py` (`_tl_work` — 로컬 모드/실패 시 LCU 타임라인)
- Test: `tests/test_lcu_match.py` (테스트 추가)

**Interfaces:**
- Produces: `try_local_timeline(lcu_client, match_id: str) -> tuple[dict, dict] | None` — (타임라인 v5 dict, 매치 DTO) 또는 None. match_id → game_id 변환 후 `match_timeline`/`match_detail` 호출
- Consumes: Task 1 `game_id_of`/`lcu_to_timeline_v5`, Task 2 LCUClient 메서드, Task 3 `self._me_local_mode`

- [ ] **Step 1: 테스트 추가**

`tests/test_lcu_match.py`에 추가:

```python
from lol_coach.analysis.lcu_match import try_local_timeline


def test_try_local_timeline_returns_v5_and_match() -> None:
    from types import SimpleNamespace

    class FakeLCU:
        def match_timeline(self, game_id: int):
            assert game_id == 5614132333
            return {"frames": [], "frameInterval": 60000}

        def match_detail(self, game_id: int):
            return {"gameId": game_id, "participants": []}

    tl, match = try_local_timeline(FakeLCU(), "KR_5614132333")
    assert tl["info"]["frameInterval"] == 60000
    assert match["gameId"] == 5614132333


def test_try_local_timeline_none_when_no_endpoint() -> None:
    from types import SimpleNamespace

    class FakeLCU:
        def match_timeline(self, game_id: int):
            return None

        def match_detail(self, game_id: int):
            raise AssertionError("타임라인 없으면 상세도 호출하지 않음")

    assert try_local_timeline(FakeLCU(), "KR_5614132333") is None
    assert try_local_timeline(FakeLCU(), "not_a_match_id") is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_lcu_match.py::test_try_local_timeline_returns_v5_and_match -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: `try_local_timeline` 구현**

`src/lol_coach/analysis/lcu_match.py` 하단에 추가:

```python
def try_local_timeline(lcu_client: Any, match_id: str) -> tuple[dict, dict] | None:
    """LCU로 타임라인+매치 DTO 로드 (타임라인 엔드포인트 없으면 None)."""
    gid = game_id_of(match_id)
    if gid is None:
        return None
    try:
        tl = lcu_client.match_timeline(gid)
    except Exception:
        return None
    if tl is None:
        return None
    try:
        detail = lcu_client.match_detail(gid)
    except Exception:
        return None
    return lcu_to_timeline_v5(tl), detail
```

- [ ] **Step 4: `_tl_work` 전체 교체**

`me_tab.py`의 `_tl_work` 함수 **전체**를 아래로 교체한다 (함수 안 import 라인은
기존 것을 유지하되, 아래 구조에 맞게 try 블록 안에서만 사용한다):

```python
            def _tl_work() -> None:
                km = None
                lines, flow = [], {}
                minimap_pil = snapshot_pil = None
                caption = ""
                tl = raw = None
                try:
                    local_mode = bool(getattr(self, "_me_local_mode", False))
                    riot_local = getattr(self, "riot", None)
                    if not local_mode and riot_local is not None:
                        try:
                            tl = riot_local.get_match_timeline(match_id)
                            raw = riot_local.get_match(match_id)
                        except Exception:
                            tl = raw = None
                    if tl is None or raw is None:
                        from lol_coach.analysis.lcu_match import try_local_timeline
                        from lol_coach.lcu import LCUClient

                        pair = None
                        try:
                            pair = try_local_timeline(LCUClient(), match_id)
                        except Exception:
                            pair = None
                        if pair is not None:
                            tl, raw = pair
                    if tl is not None:
                        lines = timeline_brief(tl, my_participant_id=pid)
                        if raw is not None:
                            pid_team = {
                                p: pi.team_id
                                for p, pi in participant_index(raw).items()
                            }
                            flow = timeline_flow(
                                tl, my_participant_id=pid, pid_team=pid_team
                            )
                except Exception:
                    lines, flow = [], {}
                if tl is not None and raw is not None:
                    try:
                        km = build_kill_map(tl, raw, pid)
                        if km.my_kills or km.my_deaths:
                            base = map_pil(map_id_for_queue(m.queue_id), 512)
                            minimap_pil = render_kill_minimap(km, base, size=320)
                            if km.collapse is not None:
                                snapshot_pil = render_collapse_snapshot(
                                    km, base, size=340
                                )
                                caption = km.collapse.caption
                    except Exception:
                        km = None
                self.after(
                    0,
                    lambda ls=lines, fl=flow, g=gen: self._apply_timeline(
                        tl_row, ls, fl, gen=g
                    ),
                )
                self.after(
                    0,
                    lambda mp=minimap_pil, sp=snapshot_pil, cap=caption, g=gen: self._apply_killmap(
                        map_row,
                        mp,
                        sp,
                        cap,
                        kills_n=len(km.my_kills) if km else 0,
                        deaths_n=len(km.my_deaths) if km else 0,
                        gen=g,
                    ),
                )
```

기존 import 라인(`build_kill_map`, `map_id_for_queue`, `participant_index`,
`timeline_brief`, `timeline_flow`, `map_pil`, `render_*`)은 `_tl_work` 내부
try 블록 최상단에 그대로 유지한다 — 위 코드에서 참조하는 이름이 전부
기존 import와 일치하는지 확인 후 교체.

- [ ] **Step 5: 회귀 확인**

Run: `uv run pytest tests/test_lcu_match.py tests/test_killmap.py tests/test_review.py tests/test_map_render.py -v`
Expected: 전부 passed

Run: `uv run pytest tests -x -q; uv run ruff check src tests; uv run mypy src`
Expected: 전체 통과

- [ ] **Step 6: 커밋**

```bash
git add src/lol_coach/analysis/lcu_match.py src/lol_coach/gui/me_tab.py tests/test_lcu_match.py
git commit -m "feat: 킬 지도·타임라인 LCU 폴백 (로컬 모드·키 실패 시)"
```

---

### Task 6: 실측 검증 (클라이언트 켠 상태)

**Files:** 없음 (검증만)

- [ ] **Step 1: 프로브 스크립트 실행**

롤 클라이언트를 켠 상태에서 실행:

```bash
uv run python -c "from lol_coach.lcu import LCUClient, parse_match_history; lcu = LCUClient(); print('summoner:', lcu.current_summoner_name()); games = lcu.match_history(0, 5); print('games:', [(g.get('gameId'), g.get('queueId')) for g in games]); gid = games[0]['gameId'] if games else 0; d = lcu.match_detail(gid); print('detail keys:', sorted(d.keys())[:15]); print('participants:', len(d.get('participants') or []), '| identities:', len(d.get('participantIdentities') or [])); tl = lcu.match_timeline(gid); print('timeline:', type(tl), len((tl or {}).get('frames') or []), 'frames' if tl else '')"
```

Expected: 소환사명·게임 목록·상세 DTO·타임라인 존재 여부 출력. 출력을 `.superpowers/sdd/task-6-probe.md`에 기록.

- [ ] **Step 2: 어댑터 보정 (프로브 결과에 따라)**

- `match_history` 응답 구조가 `games.games`가 아니면 `parse_match_history` 보강
- `match_detail`의 participants에 `timeline.lane/role`·`championName` 존재 여부 확인 —
  `championName`이 있으면 `lcu_to_match_summary`가 id_to_key 대신 그 값을 우선 사용하도록 보강:
  `champion_name=p.get("championName") or (id_to_key(...) if id_to_key else str(id))`
- 타임라인 404면 폴백이 조용히 동작하는지 확인 (기존 동작 그대로)
- 보강했다면 `uv run pytest tests -x -q` + 커밋: `fix: LCU 실측 기반 응답 구조 보정`

- [ ] **Step 3: 키리스 E2E 확인**

`.env`에서 RIOT_API_KEY 제거(백업 후) → 앱 실행 → 내 전적 로드:
1. 전적 목록·복기·트렌드가 로컬 모드로 표시되는지
2. 상태바에 "로컬 전적 모드..." 문구 확인
3. 킬 지도가 타임라인 엔드포인트 존재 시 표시되는지
4. 키 복원 후 Riot API 경로로 돌아오는지

- [ ] **Step 4: 프로브 기록 커밋**

```bash
git add .superpowers/sdd/task-6-probe.md
git commit -m "docs: LCU 전적 폴백 실측 프로브 기록" 2>/dev/null || echo "기록 파일 gitignore됨 — 스킵"
```

(.superpowers는 gitignore 대상이므로 커밋 실패해도 무해 — 출력 확인만)

---

### Task 7: 릴리스 — v1.6.46

**Files:**
- Modify: `README.md`, `docs/features.html`, 버전 파일들

- [ ] **Step 1: README 릴리스 노트**

README 릴리스 노트 섹션 최상단에 추가 (기존 `### v1.6.45` 포맷 참고):

```markdown
### v1.6.46

- 🔌 **키 없는 로컬 전적 모드** — Riot API 키가 없거나 만료돼도 롤 클라이언트(LCU) 로컬 API로 내 전적·복기·트렌드가 그대로 동작 (타임라인 엔드포인트가 있으면 킬 지도까지)
- 🔑 **개인 키 안내** — 개발 키 만료(403) 시 Personal 앱 등록 안내 다이얼로그 + 도움말 개선 (개인 키는 24시간 만료 없음)
```

- [ ] **Step 2: features.html 반영**

`docs/features.html`의 전적 관련 기능 목록에 기존 `<li>` 패턴으로 추가:

```html
          <li><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#81C784" stroke-width="1.6" stroke-linecap="round"><path d="M4 12h16M12 4v16"/></svg><span><strong>키 없는 로컬 전적 모드 (v1.6.46)</strong> — Riot API 키 없이 롤 클라이언트 전적으로 내 전적·복기·트렌드 사용, 키 만료 시 <strong>Personal 키 안내</strong> 자동 제공</span></li>
```

- [ ] **Step 3: 버전 갱신**

Run: `uv run python scripts/release.py --version 1.6.46 --skip-build`
Expected: 버전 파일들 일괄 갱신 로그

- [ ] **Step 4: exe·인스톨러 재빌드**

Run: `powershell -File scripts/build_exe.ps1` → `dist\롤실전코치.exe`
Run: `powershell -File scripts/build_installer.ps1` → `installer_output\롤실전코치 Setup v1.6.46.exe`

- [ ] **Step 5: 최종 검증 후 커밋**

Run: `uv run pytest tests -q; uv run ruff check src tests; uv run mypy src`
Expected: 전부 통과

```bash
git add README.md docs/features.html pyproject.toml src/lol_coach/__init__.py 롤실전코치.iss BUILD.md uv.lock
git commit -m "feat: v1.6.46 키리스 로컬 전적 모드·개인 키 안내 릴리스"
```

---

## Self-Review 기록

- **스펙 커버리지**: 변환 레이어(Task 1), LCU 메서드(Task 2), _load_me 폴백(Task 3), 키 안내(Task 4), 킬 지도 폴백(Task 5), 실측 검증(Task 6), 릴리스(Task 7). "다른 소환사 검색은 키 필요" 제약은 폴백 경로가 본인 프로필(설정 값)만 사용하므로 충족.
- **타입 일관성**: `build_local_form(lcu_client, count, profile) -> tuple[RecentForm | None, str]` — Task 1 정의, Task 3 소비. `try_local_timeline(lcu_client, match_id) -> tuple[dict, dict] | None` — Task 5 정의·소비. `_me_local_mode` — Task 3 세팅, Task 5 읽기.
- **프로빙 불확실성**: 응답 구조 변형은 `parse_match_history`·`lcu_to_match_summary`가 방어적으로 처리하고, Task 6 Step 2에서 실측 보정 단계를 명시.
