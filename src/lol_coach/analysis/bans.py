"""밴 추천 — 내 챔프를 카운터하는 픽 우선.

u.gg 카운터 페이지: ``get_counters(내챔프, 롤)`` 의 상위 GD@15 픽 =
상대가 잡으면 라인전이 어려운 챔프 → 밴 후보.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.ugg.counters import CounterClient, CounterPick, CounterReport


@dataclass
class BanSuggestion:
    champion: str
    gd15: int
    matches: int
    reason: str

    @property
    def gd15_str(self) -> str:
        sign = "+" if self.gd15 >= 0 else ""
        return f"{sign}{self.gd15}"


@dataclass
class BanReport:
    my_champ: str
    role: str
    patch: str
    source_url: str
    bans: list[BanSuggestion] = field(default_factory=list)


def ban_report_from_counters(
    report: CounterReport,
    *,
    my_champ: str,
    limit: int = 5,
) -> BanReport:
    """이미 가져온 CounterReport(적=내 챔프) → 밴 리스트."""
    bans: list[BanSuggestion] = []
    for c in report.lane_counters[:limit]:
        tip = (
            "초반 압박 강함"
            if c.gd15 >= 300
            else ("라인 우위" if c.gd15 >= 150 else "소폭 불리 매치업")
        )
        bans.append(
            BanSuggestion(
                champion=c.champion,
                gd15=c.gd15,
                matches=c.matches,
                reason=f"{my_champ} 상대로 GD@15 {c.gd15_str} · {tip}",
            )
        )
    return BanReport(
        my_champ=my_champ,
        role=report.role,
        patch=report.patch,
        source_url=report.source_url,
        bans=bans,
    )


def get_ban_suggestions(
    client: CounterClient,
    my_champ: str,
    role: str = "mid",
    *,
    limit: int = 5,
    min_matches: int = 600,
) -> BanReport:
    """내 챔프 기준 밴 후보 조회."""
    report = client.get_counters(
        my_champ, role=role, limit=limit, min_matches=min_matches
    )
    return ban_report_from_counters(report, my_champ=my_champ, limit=limit)


def merge_lcu_bans(
    ban_report: BanReport,
    already_banned_en: list[str],
) -> BanReport:
    """이미 밴된 챔프는 목록에서 뒤로 표시(이유 접두)."""
    banned = {b.lower().replace(" ", "") for b in already_banned_en}
    kept: list[BanSuggestion] = []
    deferred: list[BanSuggestion] = []
    for b in ban_report.bans:
        key = b.champion.lower().replace(" ", "")
        if key in banned:
            deferred.append(
                BanSuggestion(
                    champion=b.champion,
                    gd15=b.gd15,
                    matches=b.matches,
                    reason="이미 밴됨 · " + b.reason,
                )
            )
        else:
            kept.append(b)
    ban_report.bans = kept + deferred
    return ban_report
