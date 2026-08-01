"""u.gg meta build data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildSection:
    """A labeled build block with optional winrate / matches."""

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
    """Full meta snapshot for a champion + role/mode from u.gg."""

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
    boots: BuildSection = field(
        default_factory=lambda: BuildSection(label="Boots")
    )
    situational: list[BuildSection] = field(default_factory=list)

    raw_notes: list[str] = field(default_factory=list)

    def brief(self) -> str:
        wr = f"{self.win_rate:.2f}%" if self.win_rate is not None else "n/a"
        mode_tag = "ARAM" if self.mode == "aram" else self.role
        return (
            f"{self.champion} {mode_tag} | Patch {self.patch} | "
            f"Tier {self.tier or '?'} | WR {wr}"
        )
