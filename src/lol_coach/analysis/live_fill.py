"""인게임 Spectator 데이터 → 협곡/ARAM 입력 필드 매핑."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
from typing import Any

from lol_coach.modes import ARAM_QUEUES, SR_QUEUES
from lol_coach.riot.models import LiveGame
from lol_coach.static.ddragon import DataDragon

# Summoner spell Smite
_SMITE = 11

_ROLE_ORDER = ("top", "jungle", "mid", "adc", "support")


@dataclass
class LiveFillResult:
    """자동 입력용 파싱 결과."""

    my_champ_key: str
    my_champ_ko: str
    my_team_id: int
    queue_id: int
    game_mode: str
    is_aram: bool
    is_sr: bool
    # role_key → (champ_key, champ_ko)
    enemies_by_role: dict[str, tuple[str, str]] = field(default_factory=dict)
    # 포지션 추정 실패 시 남은 적 챔프
    enemies_extra: list[tuple[str, str]] = field(default_factory=list)
    allies: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""


def _champ_info(dd: DataDragon, champion_id: int) -> tuple[str, str, list[str]]:
    dd.ensure_loaded()
    c = dd._champions_by_id.get(int(champion_id))
    if not c:
        return str(champion_id), f"챔피언#{champion_id}", []
    tags = list(c.get("tags") or [])
    return c["id"], c["name"], tags


def _role_score(tags: list[str], spell1: int, spell2: int, role: str) -> int:
    if spell1 == _SMITE or spell2 == _SMITE:
        return 1000 if role == "jungle" else -1000

    tag_set = set(tags)
    score = 0
    if role == "support" and "Support" in tag_set:
        score += 120
    if role == "adc" and "Marksman" in tag_set:
        score += 100
    if role == "mid":
        if "Assassin" in tag_set:
            score += 90
        if "Mage" in tag_set:
            score += 70
        if "Fighter" in tag_set:
            score += 15
    if role == "top":
        if "Fighter" in tag_set:
            score += 60
        if "Tank" in tag_set:
            score += 50
        if "Assassin" in tag_set:
            score += 20
    if role == "jungle":
        if "Fighter" in tag_set:
            score += 35
        if "Assassin" in tag_set:
            score += 25
        if "Tank" in tag_set:
            score += 20
    if role == "support" and "Mage" in tag_set:
        score += 20
    return score


def _assign_roles(enemies: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    assignable = enemies[: len(_ROLE_ORDER)]
    if not assignable:
        return {}

    role_orders = permutations(_ROLE_ORDER, len(assignable))
    best_roles = max(
        role_orders,
        key=lambda roles: sum(
            _role_score(enemy["tags"], enemy["spell1"], enemy["spell2"], role)
            for enemy, role in zip(assignable, roles, strict=True)
        ),
    )
    return {
        role: (enemy["key"], enemy["ko"])
        for enemy, role in zip(assignable, best_roles, strict=True)
    }


def parse_live_game(
    game: LiveGame,
    dd: DataDragon,
    *,
    my_puuid: str | None = None,
) -> LiveFillResult:
    """LiveGame → 자동입력 구조."""
    qid = int(game.game_queue_config_id or 0)
    mode = (game.game_mode or "").upper()
    is_aram = qid in ARAM_QUEUES or mode in ("ARAM", "KINGPORO")
    is_sr = (not is_aram) and (
        qid in SR_QUEUES or mode in ("CLASSIC", "ODIN", "URF", "DOOMBOTSTEEMO")
    )
    # 큐 불명확하면 맵으로 추정
    if not is_aram and not is_sr:
        if game.map_id == 12:  # Howling Abyss
            is_aram = True
        else:
            is_sr = True

    my_team = game.my_team_id
    my_cid = game.my_champion_id
    if my_team is None or my_cid is None:
        # puuid 로 재탐색
        for p in game.participants:
            if my_puuid and p.get("puuid") == my_puuid:
                my_team = int(p.get("teamId") or 0)
                my_cid = int(p.get("championId") or 0)
                break
    if my_team is None:
        my_team = 100
    if not my_cid:
        raise ValueError("내 챔피언 정보를 찾지 못했습니다.")

    my_key, my_ko, _ = _champ_info(dd, int(my_cid))

    enemies_raw: list[dict[str, Any]] = []
    allies: list[tuple[str, str]] = []
    for p in game.participants:
        cid = int(p.get("championId") or 0)
        if not cid:
            continue
        key, ko, tags = _champ_info(dd, cid)
        tid = int(p.get("teamId") or 0)
        if tid == my_team:
            if key != my_key:
                allies.append((key, ko))
            continue
        enemies_raw.append(
            {
                "key": key,
                "ko": ko,
                "tags": tags,
                "spell1": int(p.get("spell1Id") or 0),
                "spell2": int(p.get("spell2Id") or 0),
            }
        )

    by_role = _assign_roles(enemies_raw)
    leftover = [
        (enemy["key"], enemy["ko"])
        for enemy in enemies_raw[len(_ROLE_ORDER) :]
    ]

    note_parts = []
    if is_aram:
        note_parts.append("칼바람/아수라장 인게임")
    elif is_sr:
        note_parts.append("소환사 협곡 인게임")
    else:
        note_parts.append(f"모드 {mode or qid}")
    note_parts.append("포지션은 스펠·챔프 태그 추정(부정확할 수 있음)")

    return LiveFillResult(
        my_champ_key=my_key,
        my_champ_ko=my_ko,
        my_team_id=int(my_team),
        queue_id=qid,
        game_mode=mode,
        is_aram=is_aram,
        is_sr=is_sr,
        enemies_by_role=by_role,
        enemies_extra=leftover,
        allies=allies,
        note=" · ".join(note_parts),
    )
