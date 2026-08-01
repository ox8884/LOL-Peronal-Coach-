"""한국어 CLI 출력 공통 포맷 (간결 버전)."""

from __future__ import annotations

import re

BAR = "─" * 42


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}%"


def games(n: int | None) -> str:
    if n is None:
        return "—"
    if n >= 10000:
        return f"{n/10000:.1f}만 게임".replace(".0만", "만")
    return f"{n:,}게임"


def wr_short(win_rate: float | None, matches: int | None = None) -> str:
    """52.4% (6.8천)"""
    if win_rate is None:
        return ""
    s = pct(win_rate, 1)
    if matches is not None and matches > 0:
        if matches >= 10000:
            s += f" · {matches/10000:.1f}만".replace(".0만", "만")
        elif matches >= 1000:
            s += f" · {matches/1000:.1f}천".replace(".0천", "천")
        else:
            s += f" · {matches}"
    return s


def header(title: str) -> list[str]:
    return [BAR, f"  {title}", BAR]


def footer() -> str:
    return BAR


def line(label: str, value: str, width: int = 6) -> str:
    return f"  {label:<{width}} {value}"


def join_items(items: list[str], sep: str = " → ") -> str:
    cleaned = [x for x in items if x and x.strip()]
    return sep.join(cleaned) if cleaned else ""


def skill_priority_ko(priority: list[str]) -> str:
    if not priority:
        return "—"
    return " › ".join(priority)


def platform_ko(platform: str) -> str:
    mapping = {
        "na1": "북미",
        "kr": "한국",
        "euw1": "EUW",
        "eun1": "EUNE",
        "br1": "브라질",
        "jp1": "일본",
        "oc1": "오세아니아",
    }
    return mapping.get(platform.lower(), platform.upper())


def rank_filter_ko(text: str) -> str:
    if not text:
        return "전체"
    pairs = [
        (r"emerald\s*\+", "에메랄드+"),
        (r"diamond\s*\+", "다이아+"),
        (r"platinum\s*\+|plat\s*\+", "플래티넘+"),
        (r"gold\s*\+", "골드+"),
        (r"master\s*\+", "마스터+"),
        (r"overall|all\s*ranks?", "전체"),
        (r"칼바람", "칼바람"),
    ]
    low = text.lower()
    for pat, ko in pairs:
        if re.search(pat, low, re.I) or re.search(pat, text):
            return ko
    if re.search(r"[가-힣]", text):
        return text
    return text


def result_ko(win: bool) -> str:
    return "승" if win else "패"


QUEUE_KO = {
    "RANKED_SOLO_5x5": "솔로 랭크",
    "RANKED_FLEX_SR": "자유 랭크",
}

TIER_KO = {
    "IRON": "아이언",
    "BRONZE": "브론즈",
    "SILVER": "실버",
    "GOLD": "골드",
    "PLATINUM": "플래티넘",
    "EMERALD": "에메랄드",
    "DIAMOND": "다이아몬드",
    "MASTER": "마스터",
    "GRANDMASTER": "그랜드마스터",
    "CHALLENGER": "챌린저",
}


def rank_line(ranks: list) -> str:
    """RankInfo 리스트 → 한국어 한 줄 요약."""
    parts: list[str] = []
    order = {"RANKED_SOLO_5x5": 0, "RANKED_FLEX_SR": 1}
    for r in sorted(ranks, key=lambda x: order.get(x.queue_type, 9)):
        q = QUEUE_KO.get(r.queue_type, r.queue_type)
        tier = TIER_KO.get(r.tier.upper(), r.tier.title())
        parts.append(
            f"{q} {tier} {r.rank} {r.league_points}LP "
            f"({r.wins}승 {r.losses}패 · {r.winrate}%)"
        )
    return "  🏅 " + "  |  ".join(parts) if parts else ""
