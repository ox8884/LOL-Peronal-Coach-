"""킬·데스 지도 — 타임라인 → 공간적 복기 데이터 (GUI 의존 없음).

Match-V5 타임라인의 이벤트는 ``info.events``가 아니라 프레임마다
``frames[i].events``로 내장되어 있다. 팀/챔피언 판정은 타임라인에
없으므로 매치 DTO에서 participantId 색인을 만들어 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

MAP_SR = 11
MAP_ARAM = 12

_KILL_WINDOW_MS = 30_000
_MIN_COLLAPSE_KILLS = 3


@dataclass(frozen=True, slots=True)
class ParticipantInfo:
    team_id: int
    champion_id: int
    champion_name: str


@dataclass(frozen=True, slots=True)
class KillEvent:
    timestamp: int
    killer_id: int
    victim_id: int
    x: float
    y: float
    killer_champ_id: int
    victim_champ_id: int
    killer_team: int
    victim_team: int


@dataclass(frozen=True, slots=True)
class SnapshotPlayer:
    participant_id: int
    champion_name: str
    x: float
    y: float
    team: int
    alive: bool


@dataclass
class CollapseSnapshot:
    timestamp: int
    winning_team: int
    kill_count: int
    players: list[SnapshotPlayer]
    caption: str


@dataclass
class KillMapData:
    my_kills: list[KillEvent]
    my_deaths: list[KillEvent]
    collapse: CollapseSnapshot | None = None
    my_team: int = 0
    total_kills: int = 0
    bounds: tuple[float, float, float, float] = (0.0, 1.0, 0.0, 1.0)


def flatten_events(info: dict) -> list[dict]:
    """프레임별 events를 병합·timestamp 정렬 (Match-V5 표준 구조)."""
    out: list[dict] = []
    for f in info.get("frames") or []:
        out.extend(f.get("events") or [])
    out.sort(key=lambda e: int(e.get("timestamp") or 0))
    return out


def participant_index(match: dict) -> dict[int, ParticipantInfo]:
    """매치 DTO → participantId → (팀, 챔피언) 색인."""
    out: dict[int, ParticipantInfo] = {}
    for p in (match.get("info") or {}).get("participants") or []:
        pid = int(p.get("participantId") or 0)
        if not pid:
            continue
        out[pid] = ParticipantInfo(
            team_id=int(p.get("teamId") or 0),
            champion_id=int(p.get("championId") or 0),
            champion_name=str(p.get("championName") or ""),
        )
    return out


def _make_kill_event(
    ev: dict, index: dict[int, ParticipantInfo]
) -> KillEvent | None:
    pos = ev.get("position")
    if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
        return None
    killer = int(ev.get("killerId") or 0)
    victim = int(ev.get("victimId") or 0)
    k_info = index.get(killer)
    v_info = index.get(victim)
    return KillEvent(
        timestamp=int(ev.get("timestamp") or 0),
        killer_id=killer,
        victim_id=victim,
        x=float(pos["x"]),
        y=float(pos["y"]),
        killer_champ_id=k_info.champion_id if k_info else 0,
        victim_champ_id=v_info.champion_id if v_info else 0,
        killer_team=k_info.team_id if k_info else 0,
        victim_team=v_info.team_id if v_info else 0,
    )


def build_kill_map(
    timeline: dict,
    match: dict,
    my_participant_id: int | None,
) -> KillMapData:
    """타임라인 + 매치 DTO → 내 킬/데스와 전체 킬 목록."""
    info = timeline.get("info") or {}
    index = participant_index(match)
    me = int(my_participant_id or 0)
    my_team = index[me].team_id if me and me in index else 0

    my_kills: list[KillEvent] = []
    my_deaths: list[KillEvent] = []
    total = 0
    for ev in flatten_events(info):
        if str(ev.get("type") or "") != "CHAMPION_KILL":
            continue
        ke = _make_kill_event(ev, index)
        if ke is None:
            continue
        total += 1
        if me and ke.victim_id == me:
            my_deaths.append(ke)
        if me and ke.killer_id == me:
            my_kills.append(ke)

    return KillMapData(
        my_kills=my_kills,
        my_deaths=my_deaths,
        my_team=my_team,
        total_kills=total,
    )
