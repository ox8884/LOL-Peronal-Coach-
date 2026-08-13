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
_MARGIN = 0.03


def map_id_for_queue(queue_id: int) -> int:
    """queueId → 미니맵 이미지 id (11=협곡, 12=칼바람·아수라장)."""
    from lol_coach.modes import is_aram_queue

    return MAP_ARAM if is_aram_queue(int(queue_id or 0)) else MAP_SR


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
    """프레임별 events(및 구버전 탑레벨 events)를 병합·timestamp 정렬."""
    out: list[dict] = []
    for f in info.get("frames") or []:
        out.extend(f.get("events") or [])
    out.extend(info.get("events") or [])
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


def _make_kill_event(ev: dict, index: dict[int, ParticipantInfo]) -> KillEvent | None:
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
    """타임라인 + 매치 DTO → 내 킬/데스와 전체 킬 목록, 붕괴 스냅샷."""
    info = timeline.get("info") or {}
    index = participant_index(match)
    me = int(my_participant_id or 0)
    my_team = index[me].team_id if me and me in index else 0

    my_kills: list[KillEvent] = []
    my_deaths: list[KillEvent] = []
    all_kills: list[KillEvent] = []
    for ev in flatten_events(info):
        if str(ev.get("type") or "") != "CHAMPION_KILL":
            continue
        ke = _make_kill_event(ev, index)
        if ke is None:
            continue
        all_kills.append(ke)
        if me and ke.victim_id == me:
            my_deaths.append(ke)
        if me and ke.killer_id == me:
            my_kills.append(ke)

    collapse = _find_collapse(all_kills, index, info, my_team) if all_kills else None
    return KillMapData(
        my_kills=my_kills,
        my_deaths=my_deaths,
        collapse=collapse,
        my_team=my_team,
        total_kills=len(all_kills),
        bounds=compute_bounds(info),
    )


def compute_bounds(info: dict) -> tuple[float, float, float, float]:
    """프레임 10인 좌표 + 킬 좌표 min/max + 3% 여백.

    데이터가 없으면 (0, 1, 0, 1) 안전 기본값.
    """
    xs: list[float] = []
    ys: list[float] = []
    for f in info.get("frames") or []:
        for pf in (f.get("participantFrames") or {}).values():
            pos = pf.get("position")
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                xs.append(float(pos["x"]))
                ys.append(float(pos["y"]))
        for ev in f.get("events") or []:
            pos = ev.get("position")
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                xs.append(float(pos["x"]))
                ys.append(float(pos["y"]))
    if not xs:
        return (0.0, 1.0, 0.0, 1.0)
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    pad_x = max(_MARGIN * (x1 - x0), 1.0)
    pad_y = max(_MARGIN * (y1 - y0), 1.0)
    return (x0 - pad_x, x1 + pad_x, y0 - pad_y, y1 + pad_y)


def game_to_pixel(
    x: float,
    y: float,
    bounds: tuple[float, float, float, float],
    size: int,
) -> tuple[int, int]:
    """게임 좌표 → 이미지 픽셀. y축은 이미지 방향(아래로 증가)에 맞춰 플립."""
    x0, x1, y0, y1 = bounds
    fx = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
    fy = (y - y0) / (y1 - y0) if y1 > y0 else 0.0
    fx = min(max(fx, 0.0), 1.0)
    fy = min(max(fy, 0.0), 1.0)
    span = 1.0 - 2 * _MARGIN
    px = int((_MARGIN + fx * span) * size)
    py = int(size - (_MARGIN + fy * span) * size)
    return px, py


def _find_collapse(
    kills: list[KillEvent],
    index: dict[int, ParticipantInfo],
    info: dict,
    my_team: int,
) -> CollapseSnapshot | None:
    """30초 내 같은 팀 3킬+ 전투 중 최다 킬(동률이면 늦은 시점)을 붕괴로 판정."""
    best: tuple[int, int, int, int] | None = None  # (킬 수, 종료 시점, 시작 시점, 팀)
    for i, first in enumerate(kills):
        team = first.killer_team
        if team not in (100, 200):
            continue
        window = [first]
        for later in kills[i + 1 :]:
            if later.timestamp - first.timestamp > _KILL_WINDOW_MS:
                break
            if later.killer_team == team:
                window.append(later)
        if len(window) < _MIN_COLLAPSE_KILLS:
            continue
        cand = (len(window), window[-1].timestamp, first.timestamp, team)
        if best is None or cand[:2] > best[:2]:
            best = cand

    if best is None:
        return None
    count, end_ts, start_ts, team = best

    # 생존자 위치: 붕괴 종료 시점에 가장 가까운 프레임 (사양: "타임스탬프에 가장 가까운 프레임")
    frames = info.get("frames") or []
    best_frame: dict | None = None
    best_dist = 1 << 62
    for f in frames:
        dist = abs(int(f.get("timestamp") or 0) - end_ts)
        if dist < best_dist:
            best_dist = dist
            best_frame = f
    dead = {k.victim_id for k in kills if start_ts <= k.timestamp <= end_ts}
    players: list[SnapshotPlayer] = []
    pfs = (best_frame or {}).get("participantFrames") or {}
    for pid_s, pf in pfs.items():
        pid = int(pid_s)
        pos = pf.get("position") or {}
        x, y = float(pos.get("x", 0) or 0), float(pos.get("y", 0) or 0)
        alive = pid not in dead
        if not alive:
            for k in reversed(kills):
                if k.victim_id == pid:
                    x, y = k.x, k.y
                    break
        pi = index.get(pid)
        players.append(
            SnapshotPlayer(
                participant_id=pid,
                champion_name=pi.champion_name if pi else "",
                x=x,
                y=y,
                team=pi.team_id if pi else 0,
                alive=alive,
            )
        )
    players.sort(key=lambda p: p.participant_id)

    mm, ss = end_ts // 60000, (end_ts % 60000) // 1000
    side = "아군" if team == my_team else "적군"
    other = "적군" if team == my_team else "아군"
    return CollapseSnapshot(
        timestamp=end_ts,
        winning_team=team,
        kill_count=count,
        players=players,
        caption=f"{mm}분 {ss}초 — {side}이 {count}킬 ({other} 붕괴)",
    )
