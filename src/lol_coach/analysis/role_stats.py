"""포지션별 통계 — 최근 전적에서 역할별 승률·KDA·CS 집계.

``MatchSummary.role`` (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY/UNKNOWN) 기반.
SR 큐(솔로랭크/자유랭크/일반) 매치만 집계 — ARAM은 역할이 무의미.
"""

from __future__ import annotations

from dataclasses import dataclass

from lol_coach.riot.models import RecentForm

# SR 큐 ID (ARAM 제외)
_SR_QUEUES = {420, 440, 430, 400}

# 포지션 표시 순서
_ROLE_ORDER = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "UNKNOWN")

_ROLE_KO = {
    "TOP": "탑",
    "JUNGLE": "정글",
    "MIDDLE": "미드",
    "BOTTOM": "원딜",
    "UTILITY": "서포터",
    "UNKNOWN": "기타",
}


@dataclass(frozen=True, slots=True)
class RoleStat:
    role: str
    role_ko: str
    games: int
    wins: int
    avg_kda: float
    avg_cs: float
    avg_deaths: float

    @property
    def losses(self) -> int:
        return self.games - self.wins

    @property
    def winrate(self) -> float:
        if self.games <= 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)


def analyze_role_stats(form: RecentForm, *, sr_only: bool = True) -> list[RoleStat]:
    """포지션별 통계 반환 (게임 수 역순).

    sr_only=True면 SR 큐만, False면 전체.
    """
    bag: dict[str, dict[str, int | float]] = {}

    for m in form.matches:
        if sr_only and m.queue_id not in _SR_QUEUES:
            continue
        role = m.role or "UNKNOWN"
        if role not in bag:
            bag[role] = {"games": 0, "wins": 0, "kda": 0.0, "cs": 0, "deaths": 0}
        b = bag[role]
        b["games"] += 1
        if m.win:
            b["wins"] += 1
        b["kda"] += m.kda_ratio
        b["cs"] += m.cs
        b["deaths"] += m.deaths

    stats: list[RoleStat] = []
    for role in _ROLE_ORDER:
        if role not in bag:
            continue
        b = bag[role]
        g = int(b["games"])
        stats.append(
            RoleStat(
                role=role,
                role_ko=_ROLE_KO.get(role, role),
                games=g,
                wins=int(b["wins"]),
                avg_kda=round(b["kda"] / max(g, 1), 2),
                avg_cs=round(b["cs"] / max(g, 1), 1),
                avg_deaths=round(b["deaths"] / max(g, 1), 1),
            )
        )

    # 게임 수 역순
    stats.sort(key=lambda s: -s.games)
    return stats
