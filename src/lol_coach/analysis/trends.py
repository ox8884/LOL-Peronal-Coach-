"""최근 전적 트렌드 — 승률·KDA·데스·CS 패턴 요약.

네트워크 없이 ``RecentForm`` 만으로 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.riot.models import MatchSummary, RecentForm


@dataclass
class TrendLine:
    label: str
    detail: str
    severity: str = "info"  # info | good | warn | bad


@dataclass
class TrendReport:
    games: int
    recent_wr: float  # 최근 N (최대 5)
    older_wr: float | None
    avg_kda: float
    avg_deaths: float
    avg_cs_per_min: float
    avg_cs10: float | None
    lines: list[TrendLine] = field(default_factory=list)
    focus_note: str = ""
    # 최근 경기 승패 시퀀스 (True=승), 화면 표시용 최대 15
    win_sequence: list[bool] = field(default_factory=list)
    # 최근 경기 KDA 시퀀스 (스파크라인용)
    kda_sequence: list[float] = field(default_factory=list)


def _wr(matches: list[MatchSummary]) -> float:
    if not matches:
        return 0.0
    wins = sum(1 for m in matches if m.win)
    return round(100.0 * wins / len(matches), 1)


def _avg(nums: list[float]) -> float:
    if not nums:
        return 0.0
    return round(sum(nums) / len(nums), 2)


def analyze_trends(form: RecentForm, *, recent_n: int = 5) -> TrendReport:
    """최근 경기 트렌드 리포트."""
    matches = list(form.matches)
    games = len(matches)
    if games == 0:
        return TrendReport(
            games=0,
            recent_wr=0.0,
            older_wr=None,
            avg_kda=0.0,
            avg_deaths=0.0,
            avg_cs_per_min=0.0,
            avg_cs10=None,
            lines=[TrendLine("전적 없음", "경기를 불러오면 트렌드가 표시됩니다.")],
        )

    n = min(recent_n, games)
    recent = matches[:n]
    older = matches[n:] if games > n else []

    recent_wr = _wr(recent)
    older_wr = _wr(older) if older else None
    avg_kda = _avg([m.kda_ratio for m in matches])
    avg_deaths = _avg([float(m.deaths) for m in matches])
    avg_cspm = _avg([m.cs_per_min for m in matches])
    cs10s = [float(m.cs10) for m in matches if m.cs10 is not None]
    avg_cs10 = _avg(cs10s) if cs10s else None

    lines: list[TrendLine] = []

    # 승률 추세
    if older_wr is not None:
        delta = round(recent_wr - older_wr, 1)
        if delta >= 12:
            lines.append(
                TrendLine(
                    "상승 흐름",
                    f"최근 {n}판 승률 {recent_wr}% (이전 {older_wr}% · +{delta}%p)",
                    "good",
                )
            )
        elif delta <= -12:
            lines.append(
                TrendLine(
                    "하락 주의",
                    f"최근 {n}판 승률 {recent_wr}% (이전 {older_wr}% · {delta}%p)",
                    "bad",
                )
            )
        else:
            lines.append(
                TrendLine(
                    "승률 유지",
                    f"최근 {n}판 {recent_wr}% · 이전 {older_wr}% (변화 {delta:+.1f}%p)",
                    "info",
                )
            )
    else:
        lines.append(
            TrendLine("최근 승률", f"최근 {n}판 승률 {recent_wr}%", "info")
        )

    # 데스 패턴
    if avg_deaths >= 7.5:
        lines.append(
            TrendLine(
                "데스 과다",
                f"평균 데스 {avg_deaths:.1f} — 라인 교환·로밍 타이밍을 줄여 보세요",
                "bad",
            )
        )
    elif avg_deaths <= 3.5 and games >= 3:
        lines.append(
            TrendLine(
                "생존 양호",
                f"평균 데스 {avg_deaths:.1f} — 한타·합류 선택이 안정적입니다",
                "good",
            )
        )
    else:
        lines.append(
            TrendLine("평균 데스", f"{avg_deaths:.1f} / 게임", "info")
        )

    # KDA
    if avg_kda >= 3.5:
        lines.append(
            TrendLine("KDA 우수", f"평균 KDA {avg_kda:.2f}", "good")
        )
    elif avg_kda < 2.0:
        lines.append(
            TrendLine(
                "KDA 개선 여지",
                f"평균 KDA {avg_kda:.2f} — 솔킬 욕심보다 합류·시야를 우선",
                "warn",
            )
        )
    else:
        lines.append(TrendLine("평균 KDA", f"{avg_kda:.2f}", "info"))

    # CS
    if avg_cs10 is not None:
        if avg_cs10 < 55:
            lines.append(
                TrendLine(
                    "CS@10 낮음",
                    f"평균 CS@10 {avg_cs10:.0f} — 웨이브 관리·디나이를 의식해 보세요",
                    "warn",
                )
            )
        elif avg_cs10 >= 75:
            lines.append(
                TrendLine(
                    "CS@10 양호",
                    f"평균 CS@10 {avg_cs10:.0f}",
                    "good",
                )
            )
        else:
            lines.append(
                TrendLine("CS@10", f"평균 {avg_cs10:.0f}", "info")
            )
    lines.append(
        TrendLine("CS/분", f"평균 {avg_cspm:.1f}", "info")
    )

    # 연패/연승
    streak = 0
    if matches:
        first = matches[0].win
        for m in matches:
            if m.win == first:
                streak += 1
            else:
                break
        if streak >= 3:
            if first:
                lines.insert(
                    0,
                    TrendLine(
                        f"{streak}연승 중",
                        "페이스 유지 — 무리한 다이브만 피하세요",
                        "good",
                    ),
                )
            else:
                lines.insert(
                    0,
                    TrendLine(
                        f"{streak}연패 중",
                        "한 판 쉬거나 주력 챔프로 리셋하는 것도 방법입니다",
                        "bad",
                    ),
                )

    focus_note = ""
    if form.champion_stats:
        top = max(form.champion_stats.values(), key=lambda c: (c.games, c.winrate))
        if top.games >= 3:
            focus_note = (
                f"가장 많이 한 챔프: {top.champion_name} "
                f"({top.games}판 · 승률 {top.winrate}%)"
            )

    win_seq = [bool(m.win) for m in matches[:15]]
    kda_seq = [float(m.kda_ratio) for m in matches[:15]]

    return TrendReport(
        games=games,
        recent_wr=recent_wr,
        older_wr=older_wr,
        avg_kda=avg_kda,
        avg_deaths=avg_deaths,
        avg_cs_per_min=avg_cspm,
        avg_cs10=avg_cs10,
        lines=lines,
        focus_note=focus_note,
        win_sequence=win_seq,
        kda_sequence=kda_seq,
    )
