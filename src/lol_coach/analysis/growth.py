from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from lol_coach.analysis.cardfont import card_font as _card_font
from lol_coach.config import PROJECT_ROOT
from lol_coach.modes import is_aram_queue
from lol_coach.riot.models import RecentForm

DAY_MS = 24 * 60 * 60 * 1000
GROWTH_HISTORY_PATH = PROJECT_ROOT / "growth_history.json"


@dataclass(frozen=True, slots=True)
class MatchRecord:
    match_id: str
    ended_at_ms: int
    win: bool
    kills: int
    deaths: int
    assists: int
    cs_per_min: float
    cs10: int | None
    duration_s: int
    queue_id: int

    @property
    def kda(self) -> float:
        return round((self.kills + self.assists) / max(1, self.deaths), 2)


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    games: int
    winrate: float
    avg_kda: float
    avg_deaths: float
    avg_cs_per_min: float


@dataclass(frozen=True, slots=True)
class WeeklyGrowth:
    current: PeriodMetrics
    previous: PeriodMetrics
    winrate_delta: float | None
    kda_delta: float | None
    deaths_delta: float | None
    cs_delta: float | None


@dataclass(frozen=True, slots=True)
class HabitSignal:
    key: str
    label: str
    sample_games: int
    winrate: float
    detail: str
    severity: str


@dataclass(frozen=True, slots=True)
class PracticeProgress:
    action_key: str
    threshold: int
    assigned_at_ms: int
    graded_games: int
    successes: int
    completion_rate: float


@dataclass(frozen=True, slots=True)
class GrowthReport:
    weekly: WeeklyGrowth
    habits: tuple[HabitSignal, ...]


@dataclass(frozen=True, slots=True)
class PlaystyleAxis:
    key: str
    label: str
    score: int
    high_label: str
    low_label: str


@dataclass(frozen=True, slots=True)
class PlaystyleDiagnosis:
    name: str
    code: str
    sample_games: int
    axes: tuple[PlaystyleAxis, ...]


def records_from_form(form: RecentForm) -> list[MatchRecord]:
    return [
        MatchRecord(
            match_id=match.match_id,
            ended_at_ms=int(match.game_end_timestamp or 0),
            win=bool(match.win),
            kills=int(match.kills),
            deaths=int(match.deaths),
            assists=int(match.assists),
            cs_per_min=float(match.cs_per_min),
            cs10=match.cs10,
            duration_s=int(match.game_duration_s),
            queue_id=int(match.queue_id),
        )
        for match in form.matches
        if match.match_id
    ]


def _record_from_json(raw: dict[str, object]) -> MatchRecord | None:
    try:
        cs10_raw = raw.get("cs10")
        return MatchRecord(
            match_id=str(raw["match_id"]),
            ended_at_ms=_as_int(raw.get("ended_at_ms")),
            win=bool(raw.get("win")),
            kills=_as_int(raw.get("kills")),
            deaths=_as_int(raw.get("deaths")),
            assists=_as_int(raw.get("assists")),
            cs_per_min=_as_float(raw.get("cs_per_min")),
            cs10=_as_int(cs10_raw) if cs10_raw is not None else None,
            duration_s=_as_int(raw.get("duration_s")),
            queue_id=_as_int(raw.get("queue_id")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (str, int, float)) else 0


def _as_float(value: object) -> float:
    return float(value) if isinstance(value, (str, int, float)) else 0.0


def _read_payload(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "profiles": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("profiles"), dict):
        return {"version": 1, "profiles": {}}
    return raw


def _profile_payload(payload: dict[str, object], puuid: str) -> dict[str, object]:
    profiles = payload["profiles"]
    if not isinstance(profiles, dict):
        profiles = {}
        payload["profiles"] = profiles
    profile = profiles.get(puuid)
    if not isinstance(profile, dict):
        profile = {"matches": []}
        profiles[puuid] = profile
    return profile


def _write_payload(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _stored_records(profile: dict[str, object]) -> list[MatchRecord]:
    raw_matches = profile.get("matches")
    if not isinstance(raw_matches, list):
        return []
    records: list[MatchRecord] = []
    for raw in raw_matches:
        if isinstance(raw, dict):
            parsed = _record_from_json(raw)
            if parsed is not None:
                records.append(parsed)
    return records


def merge_match_history(
    form: RecentForm,
    *,
    path: Path = GROWTH_HISTORY_PATH,
) -> list[MatchRecord]:
    payload = _read_payload(path)
    profile = _profile_payload(payload, form.profile.puuid)
    records = {record.match_id: record for record in _stored_records(profile)}
    records.update({record.match_id: record for record in records_from_form(form)})
    merged = sorted(records.values(), key=lambda record: record.ended_at_ms, reverse=True)[:500]
    profile["riot_id"] = form.profile.riot_id
    profile["platform"] = form.profile.platform
    profile["matches"] = [asdict(record) for record in merged]
    _write_payload(payload, path)
    return merged


def _period(records: list[MatchRecord]) -> PeriodMetrics:
    if not records:
        return PeriodMetrics(0, 0.0, 0.0, 0.0, 0.0)
    games = len(records)
    return PeriodMetrics(
        games=games,
        winrate=round(100 * sum(record.win for record in records) / games, 1),
        avg_kda=round(sum(record.kda for record in records) / games, 2),
        avg_deaths=round(sum(record.deaths for record in records) / games, 2),
        avg_cs_per_min=round(sum(record.cs_per_min for record in records) / games, 2),
    )


def _delta(current: float, previous: float, has_previous: bool) -> float | None:
    return round(current - previous, 2) if has_previous else None


def _habit(
    key: str,
    label: str,
    records: list[MatchRecord],
    *,
    baseline_winrate: float,
    context: str,
) -> HabitSignal | None:
    if len(records) < 3:
        return None
    winrate = round(100 * sum(record.win for record in records) / len(records), 1)
    gap = round(winrate - baseline_winrate, 1)
    severity = "bad" if winrate <= 40 or gap <= -10 else "good" if gap >= 10 else "info"
    return HabitSignal(
        key=key,
        label=label,
        sample_games=len(records),
        winrate=winrate,
        detail=f"{context} {len(records)}판 승률 {winrate:.1f}% · 전체 대비 {gap:+.1f}%p",
        severity=severity,
    )


def _habit_signals(records: list[MatchRecord]) -> tuple[HabitSignal, ...]:
    dated = [record for record in records if record.ended_at_ms > 0]
    if len(dated) < 3:
        return ()
    baseline = _period(dated).winrate
    chronological = sorted(dated, key=lambda record: record.ended_at_ms)
    loss_requeues: list[MatchRecord] = []
    for previous, current in zip(chronological, chronological[1:], strict=False):
        current_start = current.ended_at_ms - current.duration_s * 1000
        queue_gap = current_start - previous.ended_at_ms
        if not previous.win and 0 <= queue_gap <= 20 * 60 * 1000:
            loss_requeues.append(current)

    local_night = [
        record for record in dated if datetime.fromtimestamp(record.ended_at_ms / 1000).hour < 5
    ]
    long_games = [record for record in dated if record.duration_s >= 35 * 60]
    candidates = (
        _habit(
            "loss_requeue",
            "패배 후 빠른 재큐",
            loss_requeues,
            baseline_winrate=baseline,
            context="패배 후 20분 내 다시 시작한",
        ),
        _habit(
            "late_night",
            "새벽 큐",
            local_night,
            baseline_winrate=baseline,
            context="현지 시각 00~05시 종료",
        ),
        _habit(
            "long_game",
            "장기전 체질",
            long_games,
            baseline_winrate=baseline,
            context="35분 이상 경기",
        ),
    )
    return tuple(signal for signal in candidates if signal is not None)


def analyze_growth(records: list[MatchRecord], *, now_ms: int) -> GrowthReport:
    current_records = [
        record for record in records if now_ms - 7 * DAY_MS < record.ended_at_ms <= now_ms
    ]
    previous_records = [
        record
        for record in records
        if now_ms - 14 * DAY_MS < record.ended_at_ms <= now_ms - 7 * DAY_MS
    ]
    current = _period(current_records)
    previous = _period(previous_records)
    has_previous = previous.games > 0
    weekly = WeeklyGrowth(
        current=current,
        previous=previous,
        winrate_delta=_delta(current.winrate, previous.winrate, has_previous),
        kda_delta=_delta(current.avg_kda, previous.avg_kda, has_previous),
        deaths_delta=_delta(current.avg_deaths, previous.avg_deaths, has_previous),
        cs_delta=_delta(current.avg_cs_per_min, previous.avg_cs_per_min, has_previous),
    )
    return GrowthReport(weekly=weekly, habits=_habit_signals(records))


def diagnose_playstyle(records: list[MatchRecord]) -> PlaystyleDiagnosis | None:
    sr = [record for record in records if not is_aram_queue(record.queue_id)]
    if len(sr) < 8:
        return None
    period = _period(sr)
    avg_kills = sum(record.kills for record in sr) / len(sr)
    avg_cs10_values = [record.cs10 for record in sr if record.cs10 is not None]
    avg_cs10 = (
        sum(avg_cs10_values) / len(avg_cs10_values)
        if avg_cs10_values
        else period.avg_cs_per_min * 10
    )
    win_values = [1.0 if record.win else 0.0 for record in sr]
    win_mean = sum(win_values) / len(win_values)
    variance = sum((value - win_mean) ** 2 for value in win_values) / len(win_values)
    axes = (
        PlaystyleAxis(
            "combat",
            "교전",
            min(100, round(avg_kills / 8 * 100)),
            "교전형",
            "운영형",
        ),
        PlaystyleAxis(
            "risk",
            "리스크",
            min(100, round(period.avg_deaths / 8 * 100)),
            "과감형",
            "안정형",
        ),
        PlaystyleAxis(
            "variance",
            "기복",
            min(100, round(variance * 400)),
            "롤러코스터",
            "일관형",
        ),
        PlaystyleAxis(
            "farm",
            "파밍",
            min(100, round(avg_cs10 / 80 * 100)),
            "성장형",
            "합류형",
        ),
    )
    code = "".join("H" if axis.score >= 55 else "L" for axis in axes)
    combat = axes[0].high_label if axes[0].score >= 55 else axes[0].low_label
    risk = axes[1].high_label if axes[1].score >= 55 else axes[1].low_label
    return PlaystyleDiagnosis(
        name=f"{risk} {combat}",
        code=code,
        sample_games=len(sr),
        axes=axes,
    )


def _practice_from_json(raw: object) -> PracticeProgress | None:
    if not isinstance(raw, dict):
        return None
    try:
        return PracticeProgress(
            action_key=str(raw["action_key"]),
            threshold=int(raw["threshold"]),
            assigned_at_ms=int(raw["assigned_at_ms"]),
            graded_games=0,
            successes=0,
            completion_rate=0.0,
        )
    except (KeyError, TypeError, ValueError):
        return None


def sync_practice_progress(
    form: RecentForm,
    *,
    path: Path = GROWTH_HISTORY_PATH,
    now_ms: int,
) -> PracticeProgress | None:
    from lol_coach.analysis.trends import analyze_trends

    records = merge_match_history(form, path=path)
    payload = _read_payload(path)
    profile = _profile_payload(payload, form.profile.puuid)
    practice = _practice_from_json(profile.get("practice"))
    target = analyze_trends(form).practice_target
    if practice is None and target is not None:
        practice = PracticeProgress(
            action_key=target.action_key,
            threshold=target.threshold,
            assigned_at_ms=now_ms,
            graded_games=0,
            successes=0,
            completion_rate=0.0,
        )
        profile["practice"] = {
            "action_key": practice.action_key,
            "threshold": practice.threshold,
            "assigned_at_ms": practice.assigned_at_ms,
        }
        _write_payload(payload, path)
        return practice
    if practice is None:
        return None

    graded = [
        record
        for record in records
        if record.ended_at_ms > practice.assigned_at_ms and not is_aram_queue(record.queue_id)
    ]
    successes = sum(record.deaths < practice.threshold for record in graded)
    completion = round(100 * successes / len(graded), 1) if graded else 0.0
    return PracticeProgress(
        action_key=practice.action_key,
        threshold=practice.threshold,
        assigned_at_ms=practice.assigned_at_ms,
        graded_games=len(graded),
        successes=successes,
        completion_rate=completion,
    )


def load_growth(
    form: RecentForm,
    *,
    path: Path = GROWTH_HISTORY_PATH,
    now_ms: int,
) -> tuple[GrowthReport, PracticeProgress | None]:
    practice = sync_practice_progress(form, path=path, now_ms=now_ms)
    payload = _read_payload(path)
    profile = _profile_payload(payload, form.profile.puuid)
    return analyze_growth(_stored_records(profile), now_ms=now_ms), practice


def _formatted_delta(value: float | None, *, suffix: str = "") -> str:
    if value is None:
        return "이전 주 표본 없음"
    return f"{value:+.1f}{suffix}"


def growth_share_lines(
    riot_id: str,
    report: GrowthReport,
    practice: PracticeProgress | None,
) -> list[str]:
    weekly = report.weekly
    lines = [
        f"{riot_id} · 주간 성장 리포트",
        f"이번 주 {weekly.current.games}판 · 승률 {weekly.current.winrate:.1f}% "
        f"({_formatted_delta(weekly.winrate_delta, suffix='%p')})",
        f"KDA {weekly.current.avg_kda:.2f} ({_formatted_delta(weekly.kda_delta)}) · "
        f"평균 데스 {weekly.current.avg_deaths:.1f} ({_formatted_delta(weekly.deaths_delta)})",
    ]
    if practice is not None:
        if practice.graded_games:
            lines.append(
                f"숙제 달성률 {practice.completion_rate:.1f}% · "
                f"{practice.successes}/{practice.graded_games}판 성공"
            )
        else:
            lines.append("숙제 배정됨 · 다음 소환사의 협곡부터 자동 채점")
    lines.extend(signal.detail for signal in report.habits[:2])
    return lines


def render_growth_card(
    riot_id: str,
    report: GrowthReport,
    practice: PracticeProgress | None,
    path: str | Path,
) -> Path:
    lines = growth_share_lines(riot_id, report, practice)
    width = 1080
    height = 260 + len(lines) * 74
    image = Image.new("RGB", (width, height), "#0A0E14")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (48, 48, width - 48, height - 48),
        radius=28,
        fill="#121A24",
        outline="#2A3B50",
        width=2,
    )
    draw.rectangle((48, 48, 62, height - 48), fill="#C8AA6E")
    title_font = _card_font(38, bold=True)
    body_font = _card_font(26)
    draw.text((96, 82), lines[0], font=title_font, fill="#E8ECF2")
    y = 164
    for line in lines[1:]:
        draw.text((96, y), line, font=body_font, fill="#C9D4E0")
        y += 74
    draw.text(
        (96, height - 92),
        "롤 실전 코치 · Riot Match-V5 기반",
        font=_card_font(20),
        fill="#7B8BA0",
    )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return output
