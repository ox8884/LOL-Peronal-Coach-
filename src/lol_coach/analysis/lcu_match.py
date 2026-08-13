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


def _lane_of(p: dict) -> str:
    timeline = p.get("timeline")
    tl = timeline if isinstance(timeline, dict) else {}
    return str(tl.get("lane") or "NONE").upper()


def _role_of(lane_raw: str) -> str:
    return _ROLE_MAP.get(lane_raw, lane_raw if lane_raw else "UNKNOWN")


def _player_from(
    p: dict,
    *,
    name: str,
    me_name: str,
    id_to_key: Callable[[int], str] | None,
) -> MatchPlayer:
    s = p.get("stats") or {}
    champion_id = int(p.get("championId") or 0)
    lane_raw = _lane_of(p)
    return MatchPlayer(
        champion_name=(
            id_to_key(champion_id) if id_to_key else str(champion_id)
        ),
        champion_id=champion_id,
        role=_role_of(lane_raw),
        team_id=int(p.get("teamId") or 0),
        kills=_num(s, "kills"),
        deaths=_num(s, "deaths"),
        assists=_num(s, "assists"),
        cs=_num(s, "totalMinionsKilled") + _num(s, "neutralMinionsKilled"),
        gold=_num(s, "goldEarned"),
        damage_to_champs=_num(s, "totalDamageDealtToChampions"),
        vision_score=_num(s, "visionScore"),
        champ_level=_num(s, "champLevel"),
        is_me=bool(name == me_name),
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
    lane_raw = _lane_of(me_p)
    me_pid = int(me_p.get("participantId") or 0)

    ally: list[MatchPlayer] = []
    enemy: list[MatchPlayer] = []
    for p in participants:
        pid = int(p.get("participantId") or 0)
        name = my_summoner_name if pid == me_pid else names.get(pid, "")
        mp = _player_from(p, name=name, me_name=my_summoner_name, id_to_key=id_to_key)
        (ally if mp.team_id == my_team else enemy).append(mp)

    team_kills = sum(a.kills for a in ally)
    kp = (
        (_num(s, "kills") + _num(s, "assists")) / team_kills
        if team_kills > 0
        else None
    )
    team_dmg = sum(a.damage_to_champs for a in ally)
    dmg_share = (
        _num(s, "totalDamageDealtToChampions") / team_dmg if team_dmg > 0 else None
    )

    return MatchSummary(
        match_id=match_id_for(game_id, platform=platform),
        champion_name=(
            id_to_key(int(me_p.get("championId") or 0))
            if id_to_key
            else str(me_p.get("championId") or 0)
        ),
        champion_id=int(me_p.get("championId") or 0),
        role=_role_of(lane_raw),
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


def _detail_to_v5_match(detail: dict) -> dict:
    """LCU v3 match DTO → participant_index(v5)가 읽는 형태로 래핑."""
    return {"info": {"participants": detail.get("participants") or []}}


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
        if not isinstance(detail, dict):
            continue
        ms = lcu_to_match_summary({**detail, "gameId": gid}, my_summoner_name=my_name)
        if ms is not None:
            summaries.append(ms)
    if not summaries:
        return None, "로컬 전적을 불러오지 못했습니다 (본인 계정으로 로그인돼 있나요?)."
    return aggregate_form(profile, summaries), ""


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
    return lcu_to_timeline_v5(tl), _detail_to_v5_match(detail)
