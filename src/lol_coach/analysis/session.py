"""오늘의 세션 리포트 — 하루 플레이 요약 (결정론적, LLM 불사용).

MatchSummary 리스트에서 "오늘(로컬 날짜)" 경기를 골라 승패·연승연패·
주력 챔피언·주의 신호를 한 장으로 요약한다. 환각 위험 없는 순수 계산.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dt_time

from lol_coach.riot.models import MatchSummary


@dataclass
class SessionReport:
    """하루 세션 집계 결과."""

    day: str = ""
    matches: list[MatchSummary] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    winrate: float = 0.0
    avg_kda: float = 0.0
    avg_deaths: float = 0.0
    top_champs: list[tuple[str, int, int]] = field(default_factory=list)  # (챔프, 판수, 승수)
    streak: int = 0  # +: 연승, -: 연패 (최신 기준), 0: 경기 없음
    best: MatchSummary | None = None
    worst: MatchSummary | None = None
    lines: list[str] = field(default_factory=list)  # 요약 라인 (위젯/복사 재사용)


def local_midnight_epoch(now_s: float | None = None) -> int:
    """로컬 타임존 기준 오늘 00:00 epoch 초."""
    dt = datetime.fromtimestamp(now_s) if now_s is not None else datetime.now()
    return int(datetime.combine(dt.date(), dt_time.min).timestamp())


def day_key(now_s: float | None = None) -> str:
    dt = datetime.fromtimestamp(now_s) if now_s is not None else datetime.now()
    return dt.strftime("%Y-%m-%d (%a)")


def filter_today(matches: list[MatchSummary], *, now_s: float | None = None) -> list[MatchSummary]:
    """game_end_timestamp(최종) 의 로컬 날짜가 오늘인 경기만."""
    midnight = local_midnight_epoch(now_s)
    ms = midnight * 1000
    return [m for m in matches if (m.game_end_timestamp or 0) >= ms]


def analyze_session(matches: list[MatchSummary], *, now_s: float | None = None) -> SessionReport:
    """오늘 경기 리스트 → SessionReport. (matches는 이미 오늘 필터 전체여도 됨 — 내부에서 재필터)"""
    rep = SessionReport(day=day_key(now_s))
    today = filter_today(matches, now_s=now_s)
    today.sort(key=lambda m: m.game_end_timestamp or 0)  # 과거 → 최신
    rep.matches = today
    n = len(today)
    if not n:
        return rep

    rep.wins = sum(1 for m in today if m.win)
    rep.losses = n - rep.wins
    rep.winrate = round(rep.wins * 100.0 / n, 1)
    kills = sum(m.kills for m in today)
    deaths = sum(m.deaths for m in today)
    assists = sum(m.assists for m in today)
    rep.avg_deaths = round(deaths / n, 1)
    rep.avg_kda = round((kills + assists) / max(deaths, 1), 2)

    champ_agg: dict[str, list[int]] = {}
    for m in today:
        g = champ_agg.setdefault(m.champion_name, [0, 0])
        g[0] += 1
        if m.win:
            g[1] += 1
    rep.top_champs = sorted(
        ((c, g[0], g[1]) for c, g in champ_agg.items()),
        key=lambda x: (-x[1], x[0]),
    )[:4]

    # 연속 스트릭 (최신 기준)
    streak = 0
    for m in reversed(today):
        if m.win:
            if streak < 0:
                break
            streak += 1
        else:
            if streak > 0:
                break
            streak -= 1
    rep.streak = streak

    def _kda(m: MatchSummary) -> float:
        return m.kills + m.assists - m.deaths

    won = [m for m in today if m.win]
    lost = [m for m in today if not m.win]
    rep.best = max(won, key=_kda, default=None)
    rep.worst = min(lost, key=_kda, default=None)

    lines: list[str] = []
    lines.append(f"{n}게임 {rep.wins}승 {rep.losses}패 · 승률 {rep.winrate}% · KDA {rep.avg_kda}")
    if rep.streak >= 2:
        lines.append(f"🔥 현재 {rep.streak}연승 흐름 — 컨디션 좋을 때 더 갈 타이밍")
    elif rep.streak <= -3:
        lines.append(f"⚠ {abs(rep.streak)}연패 중 — 휴식 한 판 사이에 넣는 것도 전략입니다")
    elif rep.streak <= -2:
        lines.append(f"⚠ {abs(rep.streak)}연패 중 — 다음 패배 전에 빌드/룬 점검 추천")
    if rep.top_champs:
        parts = []
        for c, g, w in rep.top_champs:
            parts.append(f"{c} {g}판 {w}승")
        lines.append("주력: " + ", ".join(parts))
    if rep.best is not None:
        b = rep.best
        lines.append(f"베스트: {b.champion_name} {b.kda_str} ({b.duration_min}분)")
    if rep.avg_deaths >= 6.5:
        lines.append(f"평균 사망 {rep.avg_deaths}회 — 초반 진입 타이밍과 시야를 점검해 보세요")
    rep.lines = lines
    return rep
