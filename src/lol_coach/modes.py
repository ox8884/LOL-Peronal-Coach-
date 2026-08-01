"""Game mode helpers (Summoner's Rift vs ARAM / ARAM Mayhem)."""

from __future__ import annotations

# Riot queue IDs (https://static.developer.riotgames.com/docs/lol/queues.json)
QUEUE_RANKED_SOLO = 420
QUEUE_RANKED_FLEX = 440
QUEUE_NORMAL_DRAFT = 400
QUEUE_NORMAL_BLIND = 430
QUEUE_ARAM = 450
QUEUE_ARAM_CLASH = 720
QUEUE_ARAM_MAYHEM = 2400

MODE_SUMMONERS_RIFT = "summoners_rift"
MODE_ARAM = "aram"

MODE_ALIASES = {
    "summoners_rift": MODE_SUMMONERS_RIFT,
    "sr": MODE_SUMMONERS_RIFT,
    "rift": MODE_SUMMONERS_RIFT,
    "ranked": MODE_SUMMONERS_RIFT,
    "aram": MODE_ARAM,
    "aram_mayhem": MODE_ARAM,
    "mayhem": MODE_ARAM,
    "howling_abyss": MODE_ARAM,
    "ha": MODE_ARAM,
}

# Queues treated as Summoner's Rift for profile grouping
SR_QUEUES = {
    400,
    420,
    430,
    440,
    700,  # Clash
    900,  # URFish variants sometimes appear
    1020,
    1400,  # Ultimate Spellbook etc. — still Rift map family
}

ARAM_QUEUES = {
    QUEUE_ARAM,
    QUEUE_ARAM_CLASH,
    QUEUE_ARAM_MAYHEM,
    100,  # Butcher's Bridge ARAM
    65,  # legacy
}

QUEUE_LABELS = {
    QUEUE_RANKED_SOLO: "Ranked Solo",
    QUEUE_RANKED_FLEX: "Ranked Flex",
    QUEUE_NORMAL_DRAFT: "Normal Draft",
    QUEUE_NORMAL_BLIND: "Normal Blind",
    QUEUE_ARAM: "ARAM",
    QUEUE_ARAM_CLASH: "ARAM Clash",
    QUEUE_ARAM_MAYHEM: "ARAM Mayhem",
    100: "ARAM (Bridge)",
    700: "Clash",
}


def normalize_mode(mode: str) -> str:
    key = mode.strip().lower().replace("-", "_").replace(" ", "_")
    # 한글 별칭
    ko_aliases = {
        "칼바람": MODE_ARAM,
        "아수라장": MODE_ARAM,
        "협곡": MODE_SUMMONERS_RIFT,
        "소환사의협곡": MODE_SUMMONERS_RIFT,
        "랭크": MODE_SUMMONERS_RIFT,
    }
    if key in ko_aliases:
        return ko_aliases[key]
    if key not in MODE_ALIASES:
        raise ValueError(
            f"알 수 없는 모드 '{mode}'. 사용: summoners_rift | aram "
            f"(또는 칼바람 / 협곡)"
        )
    return MODE_ALIASES[key]


def mode_label(mode: str) -> str:
    m = normalize_mode(mode)
    if m == MODE_ARAM:
        return "칼바람 · 아수라장"
    return "소환사의 협곡"


def queue_label(queue_id: int) -> str:
    if queue_id in QUEUE_LABELS:
        return QUEUE_LABELS[queue_id]
    if queue_id in ARAM_QUEUES:
        return f"ARAM ({queue_id})"
    if queue_id in SR_QUEUES:
        return f"Summoner's Rift ({queue_id})"
    return f"Queue {queue_id}"


def mode_for_queue(queue_id: int) -> str:
    """Map a queue id → coarse mode bucket."""
    if queue_id == QUEUE_ARAM_MAYHEM:
        return "aram_mayhem"
    if queue_id in ARAM_QUEUES:
        return "aram"
    if queue_id in SR_QUEUES or queue_id in (
        QUEUE_RANKED_SOLO,
        QUEUE_RANKED_FLEX,
        QUEUE_NORMAL_DRAFT,
        QUEUE_NORMAL_BLIND,
    ):
        return "summoners_rift"
    # Heuristic: unknown Howling Abyss-ish ids sometimes appear
    if queue_id in (450, 720, 2400, 100):
        return "aram"
    return "other"


def display_mode_for_queue(queue_id: int) -> str:
    """Human label for a single match."""
    if queue_id == QUEUE_ARAM_MAYHEM:
        return "ARAM Mayhem"
    if queue_id in ARAM_QUEUES:
        return "ARAM"
    if mode_for_queue(queue_id) == "summoners_rift":
        return QUEUE_LABELS.get(queue_id, "Summoner's Rift")
    return queue_label(queue_id)


def queues_for_mode(mode: str) -> set[int] | None:
    """
    Queues to include when filtering history for a mode.
    None = no queue filter (all).
    """
    m = normalize_mode(mode)
    if m == MODE_ARAM:
        return set(ARAM_QUEUES)
    if m == MODE_SUMMONERS_RIFT:
        return set(SR_QUEUES) | {
            QUEUE_RANKED_SOLO,
            QUEUE_RANKED_FLEX,
            QUEUE_NORMAL_DRAFT,
            QUEUE_NORMAL_BLIND,
        }
    return None


def is_aram_queue(queue_id: int) -> bool:
    return queue_id in ARAM_QUEUES or queue_id == QUEUE_ARAM_MAYHEM
