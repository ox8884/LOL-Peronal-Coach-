"""듀오/파티 통계 — 최근 전적에서 같이 뛴 아군 집계.

``MatchPlayer.riot_id`` 가 채워진 매치에서만 동작한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.riot.models import RecentForm


def _norm(rid: str) -> str:
    return (rid or "").strip().lower().replace(" ", "")


@dataclass
class DuoPartner:
    riot_id: str
    games: int
    wins: int

    @property
    def losses(self) -> int:
        return self.games - self.wins

    @property
    def winrate(self) -> float:
        if self.games <= 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)


@dataclass
class DuoReport:
    partners: list[DuoPartner] = field(default_factory=list)
    total_with_any: int = 0  # 아군 riot_id 가 있는 매치 수


def analyze_duos(
    form: RecentForm,
    *,
    min_games: int = 2,
    limit: int = 8,
) -> DuoReport:
    """같이 뛴 횟수 ≥ min_games 인 파트너를 게임 수·승률 순으로 반환."""
    me = _norm(form.profile.riot_id)
    # key -> (display, games, wins)
    bag: dict[str, tuple[str, int, int]] = {}
    matches_with_ids = 0

    for m in form.matches:
        allies = list(m.ally_team or [])
        if not allies:
            continue
        seen: set[str] = set()
        had_id = False
        for p in allies:
            if getattr(p, "is_me", False):
                continue
            rid = (p.riot_id or "").strip()
            key = _norm(rid)
            if not key or key == me:
                continue
            had_id = True
            if key in seen:
                continue
            seen.add(key)
            display, games, wins = bag.get(key, (rid, 0, 0))
            games += 1
            if m.win:
                wins += 1
            bag[key] = (display or rid, games, wins)
        if had_id:
            matches_with_ids += 1

    partners = [
        DuoPartner(riot_id=display, games=games, wins=wins)
        for _k, (display, games, wins) in bag.items()
        if games >= min_games
    ]
    partners.sort(key=lambda p: (-p.games, -p.winrate, p.riot_id.lower()))
    return DuoReport(partners=partners[:limit], total_with_any=matches_with_ids)
