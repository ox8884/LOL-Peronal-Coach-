"""챔피언 시너지 통계 — 내가 같이 뛴 아군 챔피언별 승률.

``MatchPlayer.champion_name`` (ally_team) 기반.
듀오 파트너(소환사)가 아닌 챔피언 시너지를 본다 — "이 챔피언과 같이하면 승률 N%".
"""

from __future__ import annotations

from dataclasses import dataclass

from lol_coach.riot.models import RecentForm


@dataclass(frozen=True, slots=True)
class ChampionSynergy:
    champion_name: str  # Data Dragon key (Ahri, Jinx, ...)
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


@dataclass(frozen=True, slots=True)
class SynergyReport:
    allies: list[ChampionSynergy]  # 같이 한 아군 챔피언 (승률 순)
    enemies: list[ChampionSynergy]  # 상대한 적 챔피언 (승률 낮은 순 = 까다로운 상대)
    total_with_data: int = 0  # ally_team 데이터가 있는 매치 수


def analyze_synergies(
    form: RecentForm,
    *,
    min_games: int = 2,
    limit: int = 6,
) -> SynergyReport:
    """아군 챔피언 시너지 + 적 챔피언 카운터 통계.

    아군: 내가 같이 뛴 챔피언 → 승률 높은 순.
    적군: 내가 상대한 챔피언 → 승률 낮은 순 (내가 약한 상대).
    """
    ally_bag: dict[str, dict[str, int]] = {}
    enemy_bag: dict[str, dict[str, int]] = {}
    total = 0

    for m in form.matches:
        allies = list(m.ally_team or [])
        enemies = list(m.enemy_team or [])
        if not allies and not enemies:
            continue
        total += 1

        # 아군 시너지 (is_me 제외)
        seen_a: set[str] = set()
        for p in allies:
            if getattr(p, "is_me", False):
                continue
            cname = (p.champion_name or "").strip()
            if not cname or cname in seen_a:
                continue
            seen_a.add(cname)
            if cname not in ally_bag:
                ally_bag[cname] = {"games": 0, "wins": 0}
            ally_bag[cname]["games"] += 1
            if m.win:
                ally_bag[cname]["wins"] += 1

        # 적 카운터
        seen_e: set[str] = set()
        for p in enemies:
            cname = (p.champion_name or "").strip()
            if not cname or cname in seen_e:
                continue
            seen_e.add(cname)
            if cname not in enemy_bag:
                enemy_bag[cname] = {"games": 0, "wins": 0}
            enemy_bag[cname]["games"] += 1
            if m.win:
                enemy_bag[cname]["wins"] += 1

    allies = [
        ChampionSynergy(
            champion_name=name,
            games=d["games"],
            wins=d["wins"],
        )
        for name, d in ally_bag.items()
        if d["games"] >= min_games
    ]
    # 아군: 승률 높은 순 → 게임 수 순
    allies.sort(key=lambda s: (-s.winrate, -s.games, s.champion_name))

    enemies = [
        ChampionSynergy(
            champion_name=name,
            games=d["games"],
            wins=d["wins"],
        )
        for name, d in enemy_bag.items()
        if d["games"] >= min_games
    ]
    # 적군: 내 승률 낮은 순 (까다로운 상대) → 게임 수 순
    enemies.sort(key=lambda s: (s.winrate, -s.games, s.champion_name))

    return SynergyReport(
        allies=allies[:limit],
        enemies=enemies[:limit],
        total_with_data=total,
    )
