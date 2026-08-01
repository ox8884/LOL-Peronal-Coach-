"""전적 요약 포맷터 (간결 한국어)."""

from __future__ import annotations

from lol_coach.display import footer, header, line, platform_ko, result_ko
from lol_coach.riot.models import MatchSummary, RecentForm
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer


def format_recent_form(form: RecentForm, dd: DataDragon | None = None) -> str:
    loc = get_localizer()
    loc.ensure_loaded()
    _ = dd  # optional

    p = form.profile
    lines: list[str] = []
    lines.extend(header(f"최근 전적 · {p.riot_id}"))
    lines.append(
        f"  {form.games}게임  {form.wins}승 {form.losses}패 ({form.winrate}%)  |  "
        f"KDA {form.avg_kda}  |  CS/분 {form.avg_cs_per_min}"
    )
    if p.summoner_level is not None:
        lines.append(f"  레벨 {p.summoner_level}  ·  {platform_ko(p.platform)}")
    lines.append("")

    if form.mode_stats:
        lines.append("  ▸ 모드별")
        order = {
            "Ranked Solo": 0,
            "Ranked Flex": 1,
            "Normal Draft": 2,
            "Normal Blind": 3,
            "ARAM": 10,
            "ARAM Mayhem": 11,
        }
        for ms in sorted(
            form.mode_stats.values(),
            key=lambda m: (order.get(m.label, 50), -m.games),
        ):
            lines.append(
                line(
                    loc.mode(ms.label),
                    f"{ms.games}G  {ms.wins}승/{ms.losses}패  {ms.winrate}%  "
                    f"KDA {ms.avg_kda}",
                    width=8,
                )
            )
        lines.append("")

    lines.append("  ▸ 최근 경기")
    if not form.matches:
        lines.append("  경기 없음")
    for i, m in enumerate(form.matches, 1):
        mark = result_ko(m.win)
        champ = loc.champion(m.champion_name) or m.champion_name
        ctx = (
            loc.mode(m.mode_label)
            if "ARAM" in m.mode_label
            else loc.role(m.role)
        )
        lines.append(
            f"  {i:2}. [{mark}] {champ} · {ctx}  "
            f"{m.kda_str}  CS {m.cs}  딜 {m.damage_to_champs:,}"
        )

    if form.champion_stats:
        lines.append("")
        lines.append("  ▸ 챔피언별")
        for c in sorted(
            form.champion_stats.values(),
            key=lambda x: (-x.games, -x.winrate),
        ):
            name = loc.champion(c.champion_name) or c.champion_name
            lines.append(
                line(
                    name,
                    f"{c.games}G  {c.winrate}%  KDA {c.avg_kda}",
                    width=8,
                )
            )

    lines.append(footer())
    return "\n".join(lines)


def format_match_items(m: MatchSummary, dd: DataDragon) -> str:
    names = dd.item_names(m.items)
    return " → ".join(names) if names else "(아이템 없음)"
