"""blitz.gg 메타 데이터 모델 — SR 빌드/카운터 공용 (u.gg 모델의 후속)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class BlitzError(Exception):
    """blitz.gg fetch/파싱 실패 — 호출부에서 사용자 안내로 변환."""


@dataclass
class BuildSection:
    """Labeled build block with optional winrate / matches."""

    label: str
    items: list[str] = field(default_factory=list)
    win_rate: float | None = None
    matches: int | None = None
    note: str = ""


@dataclass
class RunePage:
    primary_tree: str = ""
    secondary_tree: str = ""
    keystone: str = ""
    primary_runes: list[str] = field(default_factory=list)
    secondary_runes: list[str] = field(default_factory=list)
    shards: list[str] = field(default_factory=list)
    win_rate: float | None = None
    matches: int | None = None

    def summary_lines(self) -> list[str]:
        lines = []
        if self.primary_tree or self.secondary_tree:
            lines.append(
                f"Trees: {self.primary_tree or '?'} + {self.secondary_tree or '?'}"
            )
        if self.keystone:
            lines.append(f"Keystone: {self.keystone}")
        if self.primary_runes:
            lines.append("Primary: " + " · ".join(self.primary_runes))
        if self.secondary_runes:
            lines.append("Secondary: " + " · ".join(self.secondary_runes))
        if self.shards:
            lines.append("Shards: " + " · ".join(self.shards))
        if self.win_rate is not None:
            m = f" ({self.matches:,} matches)" if self.matches else ""
            lines.append(f"Rune WR: {self.win_rate:.2f}%{m}")
        return lines


@dataclass
class SkillBuild:
    priority: list[str] = field(default_factory=list)  # e.g. ["Q","W","E"]
    order_by_level: list[str] = field(default_factory=list)  # 18 skills
    win_rate: float | None = None
    matches: int | None = None


@dataclass
class ChampionBuild:
    """Full meta snapshot for a champion + role from blitz.gg."""

    champion: str
    role: str
    patch: str
    tier: str = ""
    win_rate: float | None = None
    pick_rate: float | None = None
    ban_rate: float | None = None
    matches: int | None = None
    rank_filter: str = "Emerald+"
    source_url: str = ""
    # summoners_rift | aram
    mode: str = "summoners_rift"

    runes: RunePage = field(default_factory=RunePage)
    skills: SkillBuild = field(default_factory=SkillBuild)
    summoner_spells: list[str] = field(default_factory=list)
    summoner_spells_wr: float | None = None

    starting_items: BuildSection = field(
        default_factory=lambda: BuildSection(label="Starting Items")
    )
    core_items: BuildSection = field(
        default_factory=lambda: BuildSection(label="Core Items")
    )
    boots: BuildSection = field(default_factory=lambda: BuildSection(label="Boots"))
    situational: list[BuildSection] = field(default_factory=list)

    raw_notes: list[str] = field(default_factory=list)

    # 디스크 캐시 TTL 경과 후 폴백으로 반환될 때 표시용 (네트워크 실패 fallback)
    stale_cache: bool = False
    cache_age_s: float = 0.0

    def brief(self) -> str:
        wr = f"{self.win_rate:.2f}%" if self.win_rate is not None else "n/a"
        mode_tag = "ARAM" if self.mode == "aram" else self.role
        return (
            f"{self.champion} {mode_tag} | Patch {self.patch} | "
            f"Tier {self.tier or '?'} | WR {wr}"
        )


@dataclass
class CounterPick:
    champion: str  # English name from blitz.gg
    gd15: int  # gold diff @ 15 (blitz "Score" 컬럼)
    matches: int
    win_rate: float | None = None

    @property
    def gd15_str(self) -> str:
        sign = "+" if self.gd15 >= 0 else ""
        return f"{sign}{self.gd15}"


@dataclass
class CounterReport:
    enemy: str
    role: str
    patch: str
    source_url: str
    lane_counters: list[CounterPick] = field(default_factory=list)
    # weak against enemy (low GD15 / hard matchups) — optional
    hard_matchups: list[CounterPick] = field(default_factory=list)


def report_to_dict(report: CounterReport) -> dict:
    """CounterReport → JSON 직렬화 가능 dict (공용 캐시용)."""
    return {
        "enemy": report.enemy,
        "role": report.role,
        "patch": report.patch,
        "source_url": report.source_url,
        "lane_counters": [asdict(c) for c in report.lane_counters],
        "hard_matchups": [asdict(c) for c in report.hard_matchups],
    }


def pick_from_dict(data: Any) -> CounterPick:
    if not isinstance(data, dict):
        raise BlitzError("카운터 캐시 형식 오류")
    return CounterPick(
        champion=str(data.get("champion") or ""),
        gd15=int(data.get("gd15") or 0),
        matches=int(data.get("matches") or 0),
        win_rate=data.get("win_rate"),
    )


def report_from_dict(data: Any) -> CounterReport:
    if not isinstance(data, dict):
        raise BlitzError("카운터 캐시 형식 오류")
    return CounterReport(
        enemy=str(data.get("enemy") or ""),
        role=str(data.get("role") or ""),
        patch=str(data.get("patch") or ""),
        source_url=str(data.get("source_url") or ""),
        lane_counters=[pick_from_dict(c) for c in (data.get("lane_counters") or [])],
        hard_matchups=[pick_from_dict(c) for c in (data.get("hard_matchups") or [])],
    )
