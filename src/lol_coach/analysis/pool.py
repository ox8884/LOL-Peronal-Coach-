"""챔피언 풀 진단 — 최근 전적 기반 집중/유지/정리 추천.

표본이 적을 때 승률이 과도하게 흔들리는 것을 막기 위해
베이지안 보정(사전 50% / 5게임)을 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.riot.models import ChampionStats, RecentForm

# 판정 임계값
_MIN_GAMES_CONFIDENT = 5  # 이 표본 이상이면 확신 판정
_FOCUS_MARGIN = 5.0  # 전체 승률 대비 +이만큼이면 집중
_FOCUS_FLOOR = 55.0  # 보정 승률 절대 하한 (전체가 낮아도 이 이상이어야 집중)
_DROP_WR = 45.0  # 보정 승률이 이 값 미만이면 정리 후보
_PRIOR_GAMES = 5.0  # 베이지안 사전 게임 수
_PRIOR_WR = 0.5


@dataclass
class PoolEntry:
    champion_name: str
    games: int
    wins: int
    winrate: float  # 실측 %
    adjusted_wr: float  # 보정 %
    avg_kda: float
    verdict: str  # 집중 / 유지 / 표본 부족 / 정리 검토
    reason: str


@dataclass
class PoolReport:
    total_games: int
    overall_wr: float
    entries: list[PoolEntry] = field(default_factory=list)

    @property
    def focus(self) -> list[PoolEntry]:
        return [e for e in self.entries if e.verdict == "집중"]

    @property
    def drop(self) -> list[PoolEntry]:
        return [e for e in self.entries if e.verdict == "정리 검토"]


def _adjusted_wr(wins: int, games: int) -> float:
    return round(100.0 * (wins + _PRIOR_GAMES * _PRIOR_WR) / (games + _PRIOR_GAMES), 1)


def _judge(stats: ChampionStats, overall_wr: float) -> tuple[str, str]:
    games, wins = stats.games, stats.wins
    adj = _adjusted_wr(wins, games)
    kda = stats.avg_kda

    if games < 3:
        return "표본 부족", f"{games}게임 — 판단엔 최소 3게임 필요"
    if games >= _MIN_GAMES_CONFIDENT and adj >= _FOCUS_FLOOR and adj >= overall_wr + _FOCUS_MARGIN:
        return (
            "집중",
            f"보정 승률 {adj}% (전체 평균 +{round(adj - overall_wr, 1)}%p) — 가장 믿을 만한 픽",
        )
    if adj < _DROP_WR:
        hint = "KDA는 괜찮지만 " if kda >= 3.0 else ""
        return (
            "정리 검토",
            f"보정 승률 {adj}% — {hint}승리로 안 이어집니다. "
            "다른 챔프에 시간을 쓰는 편이 나을 수 있어요",
        )
    return "유지", f"보정 승률 {adj}% — 평균권, 그대로 가져가도 됩니다"


def diagnose_pool(form: RecentForm) -> PoolReport:
    overall = form.winrate
    entries: list[PoolEntry] = []
    for stats in sorted(form.champion_stats.values(), key=lambda c: (-c.games, -c.winrate)):
        verdict, reason = _judge(stats, overall)
        entries.append(
            PoolEntry(
                champion_name=stats.champion_name,
                games=stats.games,
                wins=stats.wins,
                winrate=stats.winrate,
                adjusted_wr=_adjusted_wr(stats.wins, stats.games),
                avg_kda=stats.avg_kda,
                verdict=verdict,
                reason=reason,
            )
        )
    return PoolReport(total_games=form.games, overall_wr=overall, entries=entries)
