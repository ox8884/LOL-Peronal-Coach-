"""Lightweight data models for Riot API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlayerProfile:
    game_name: str
    tag_line: str
    puuid: str
    platform: str
    summoner_id: str | None = None
    account_id: str | None = None
    profile_icon_id: int | None = None
    summoner_level: int | None = None

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


@dataclass
class MatchPlayer:
    """매치 참가자 한 명 (팀 조합 표시용)."""

    champion_name: str
    champion_id: int
    role: str
    team_id: int  # 100 blue / 200 red
    kills: int
    deaths: int
    assists: int
    cs: int
    gold: int
    damage_to_champs: int
    vision_score: int
    champ_level: int
    items: list[int] = field(default_factory=list)
    riot_id: str = ""
    is_me: bool = False
    win: bool = False

    @property
    def kda_str(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"


@dataclass
class SideObjectives:
    dragons: int = 0
    barons: int = 0
    towers: int = 0
    inhibitors: int = 0
    heralds: int = 0
    grubs: int = 0  # void grubs / horde


@dataclass
class MatchObjectives:
    ally: SideObjectives = field(default_factory=SideObjectives)
    enemy: SideObjectives = field(default_factory=SideObjectives)


@dataclass
class MatchSummary:
    match_id: str
    champion_name: str
    champion_id: int
    role: str  # TOP / JUNGLE / MIDDLE / BOTTOM / UTILITY / UNKNOWN
    lane: str
    win: bool
    kills: int
    deaths: int
    assists: int
    cs: int  # totalMinionsKilled + neutralMinionsKilled
    gold: int
    damage_to_champs: int
    vision_score: int
    game_duration_s: int
    queue_id: int
    items: list[int] = field(default_factory=list)
    summoner_spells: list[int] = field(default_factory=list)
    primary_rune: int | None = None
    skill_order: list[str] = field(default_factory=list)  # e.g. ["Q","W",...]
    raw_participant: dict[str, Any] = field(default_factory=dict, repr=False)
    # 상세 복기용
    team_id: int = 100
    champ_level: int = 0
    damage_taken: int = 0
    kill_participation: float | None = None  # 0~1 or percent
    damage_share: float | None = None
    gold_per_min: float | None = None
    wards_placed: int = 0
    wards_killed: int = 0
    control_wards: int = 0
    turret_kills: int = 0
    first_blood: bool = False
    largest_multi_kill: int = 0
    solo_kills: int = 0
    total_team_kills: int = 0
    ally_team: list[MatchPlayer] = field(default_factory=list)
    enemy_team: list[MatchPlayer] = field(default_factory=list)
    obj: MatchObjectives | None = None
    game_mode: str = ""
    game_version: str = ""
    # 심화 복기 (challenges / participant)
    time_dead_s: int = 0
    damage_to_objectives: int = 0
    damage_to_buildings: int = 0
    cs10: int | None = None  # lane minions first 10 min
    gold_lead_lane: int | None = None  # early/laning gold advantage vs opponent
    vision_adv_lane: float | None = None
    plates: int = 0
    dragon_takedowns: int = 0
    baron_takedowns: int = 0
    herald_takedowns: int = 0
    epic_steals: int = 0
    jungle_cs_10: float | None = None
    scuttle_kills: int = 0
    dpm: float | None = None
    team_early_surrender: bool = False
    enemy_team_kills: int = 0
    ally_gold_total: int = 0
    enemy_gold_total: int = 0

    @property
    def kda_ratio(self) -> float:
        if self.deaths == 0:
            return float(self.kills + self.assists)
        return round((self.kills + self.assists) / self.deaths, 2)

    @property
    def kda_str(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def cs_per_min(self) -> float:
        minutes = max(self.game_duration_s / 60.0, 1e-6)
        return round(self.cs / minutes, 1)

    @property
    def duration_min(self) -> float:
        return round(self.game_duration_s / 60.0, 1)

    @property
    def mode_label(self) -> str:
        from lol_coach.modes import display_mode_for_queue

        return display_mode_for_queue(self.queue_id)

    @property
    def mode_key(self) -> str:
        from lol_coach.modes import mode_for_queue

        return mode_for_queue(self.queue_id)


@dataclass
class ChampionStats:
    champion_name: str
    games: int = 0
    wins: int = 0
    kills: float = 0.0
    deaths: float = 0.0
    assists: float = 0.0
    cs: float = 0.0
    roles: dict[str, int] = field(default_factory=dict)

    @property
    def winrate(self) -> float:
        if self.games == 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)

    @property
    def avg_kda(self) -> float:
        if self.games == 0:
            return 0.0
        d = self.deaths / self.games
        if d == 0:
            return round((self.kills + self.assists) / self.games, 2)
        return round((self.kills + self.assists) / self.games / d, 2)

    @property
    def avg_cs(self) -> float:
        if self.games == 0:
            return 0.0
        return round(self.cs / self.games, 1)

    @property
    def primary_role(self) -> str:
        if not self.roles:
            return "UNKNOWN"
        return max(self.roles, key=self.roles.get)


@dataclass
class ModeBucketStats:
    """Aggregate stats for one mode bucket (e.g. ARAM Mayhem)."""

    label: str
    games: int = 0
    wins: int = 0
    avg_kda: float = 0.0
    avg_cs_per_min: float = 0.0
    avg_damage: float = 0.0

    @property
    def losses(self) -> int:
        return self.games - self.wins

    @property
    def winrate(self) -> float:
        if self.games == 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)


@dataclass
class RecentForm:
    profile: PlayerProfile
    matches: list[MatchSummary]
    wins: int
    losses: int
    avg_kda: float
    avg_cs_per_min: float
    role_counts: dict[str, int]
    champion_stats: dict[str, ChampionStats]
    mode_stats: dict[str, ModeBucketStats] = field(default_factory=dict)

    @property
    def games(self) -> int:
        return len(self.matches)

    @property
    def winrate(self) -> float:
        if self.games == 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)


@dataclass
class RankInfo:
    """League V4 ranked entry for one queue."""

    queue_type: str  # RANKED_SOLO_5x5 / RANKED_FLEX_SR
    tier: str  # GOLD, PLATINUM ...
    rank: str  # I, II, III, IV
    league_points: int = 0
    wins: int = 0
    losses: int = 0
    hot_streak: bool = False
    veteran: bool = False
    fresh_blood: bool = False

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def winrate(self) -> float:
        if self.games == 0:
            return 0.0
        return round(100.0 * self.wins / self.games, 1)

    @classmethod
    def from_api(cls, entry: dict[str, Any]) -> RankInfo:
        return cls(
            queue_type=str(entry.get("queueType") or ""),
            tier=str(entry.get("tier") or ""),
            rank=str(entry.get("rank") or ""),
            league_points=int(entry.get("leaguePoints") or 0),
            wins=int(entry.get("wins") or 0),
            losses=int(entry.get("losses") or 0),
            hot_streak=bool(entry.get("hotStreak")),
            veteran=bool(entry.get("veteran")),
            fresh_blood=bool(entry.get("freshBlood")),
        )


@dataclass
class LiveGame:
    game_id: int
    game_mode: str
    game_type: str
    map_id: int
    game_queue_config_id: int
    game_start_time: int
    game_length: int
    participants: list[dict[str, Any]]
    my_champion_id: int | None = None
    my_team_id: int | None = None
    observers_key: str | None = None
