"""개인 전적 + u.gg 메타 → 간결한 맞춤 코칭."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lol_coach.blitz.models import ChampionBuild
from lol_coach.display import (
    footer,
    header,
    join_items,
    line,
    pct,
    rank_filter_ko,
    result_ko,
    skill_priority_ko,
    wr_short,
)
from lol_coach.riot.models import MatchSummary
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import KoreanLocalizer, get_localizer


@dataclass
class CoachReport:
    champion: str
    role: str
    meta: ChampionBuild
    my_games: list[MatchSummary] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    natural_language: str = ""
    localizer: KoreanLocalizer | None = None

    def render(self) -> str:
        loc = self.localizer or get_localizer()
        loc.ensure_loaded()
        m = self.meta
        champ = loc.champion(self.champion) or self.champion
        is_aram = m.mode == "aram"
        mode_tag = "칼바람" if is_aram else (loc.role(self.role) or self.role)
        tier = m.tier or "?"
        wr = pct(m.win_rate, 1)
        pr = pct(m.pick_rate, 1)

        lines: list[str] = []
        lines.extend(header(f"{champ} · {mode_tag} · 패치 {m.patch}"))

        # 한 줄 요약
        summary = f"티어 {tier}  |  승률 {wr}  |  픽 {pr}"
        if m.ban_rate is not None:
            summary += f"  |  밴 {pct(m.ban_rate, 1)}"
        lines.append(f"  {summary}")
        if not is_aram and m.rank_filter:
            lines.append(f"  구간  {rank_filter_ko(m.rank_filter)}")
        lines.append("")

        # 빌드
        lines.append("  ▸ 추천 빌드")
        if m.runes.keystone or m.runes.primary_tree:
            tree = " + ".join(
                x
                for x in (
                    loc.rune(m.runes.primary_tree) if m.runes.primary_tree else "",
                    loc.rune(m.runes.secondary_tree) if m.runes.secondary_tree else "",
                )
                if x
            )
            keystone = loc.rune(m.runes.keystone) if m.runes.keystone else "—"
            lines.append(line("룬", f"{keystone}" + (f"  ({tree})" if tree else "")))
            main = " · ".join(loc.runes(m.runes.primary_runes))
            sub = " · ".join(loc.runes(m.runes.secondary_runes))
            if main:
                lines.append(line("", main))
            if sub:
                lines.append(line("", f"서브  {sub}"))
            shards = " · ".join(loc.runes(m.runes.shards))
            if shards:
                lines.append(line("파편", shards))

        if m.skills.priority:
            sk = skill_priority_ko(m.skills.priority)
            extra = wr_short(m.skills.win_rate, m.skills.matches)
            lines.append(line("스킬", sk + (f"  ({extra})" if extra else "")))

        if m.summoner_spells:
            sp = " + ".join(loc.spells(m.summoner_spells))
            extra = wr_short(m.summoner_spells_wr)
            lines.append(line("스펠", sp + (f"  ({extra})" if extra else "")))

        core = loc.items(m.core_items.items)
        if core:
            extra = wr_short(m.core_items.win_rate, m.core_items.matches)
            lines.append(
                line("코어", join_items(core) + (f"  ({extra})" if extra else ""))
            )
        boots = loc.items(m.boots.items)
        if boots:
            lines.append(line("신발", join_items(boots)))
        start = loc.items(m.starting_items.items)
        if start:
            lines.append(line("시작", join_items(start, sep=" + ")))

        # 시추에이셔널 — 이름 있는 것만, 최대 2줄
        situ_n = 0
        for sec, label in (
            (m.situational[0] if len(m.situational) > 0 else None, "4코어"),
            (m.situational[1] if len(m.situational) > 1 else None, "5코어"),
        ):
            if not sec:
                continue
            items = loc.items(sec.items)
            if not items:
                continue
            extra = wr_short(sec.win_rate, sec.matches)
            lines.append(
                line(label, join_items(items, sep=" / ") + (f"  ({extra})" if extra else ""))
            )
            situ_n += 1

        lines.append("")

        # 내 전적
        lines.append(f"  ▸ 내 최근 {champ}")
        if not self.my_games:
            if is_aram:
                lines.append(
                    "  최근 칼바람 데이터가 부족합니다. 메타 빌드 위주로 추천합니다."
                )
            else:
                lines.append(
                    "  최근 해당 챔피언 데이터가 부족합니다. 메타 빌드 위주로 추천합니다."
                )
        else:
            wins = sum(1 for g in self.my_games if g.win)
            n = len(self.my_games)
            avg_kda = sum(g.kda_ratio for g in self.my_games) / n
            avg_dmg = sum(g.damage_to_champs for g in self.my_games) / n
            avg_cspm = sum(g.cs_per_min for g in self.my_games) / n
            if is_aram:
                lines.append(
                    f"  {n}게임  {wins}승 {n - wins}패  |  "
                    f"KDA {avg_kda:.2f}  |  평균 딜 {int(avg_dmg):,}"
                )
            else:
                lines.append(
                    f"  {n}게임  {wins}승 {n - wins}패  |  "
                    f"KDA {avg_kda:.2f}  |  CS/분 {avg_cspm:.1f}"
                )
            mode_counts = Counter(g.mode_label for g in self.my_games)
            if any("ARAM" in k for k in mode_counts):
                mix = " · ".join(
                    f"{loc.mode(k)} {v}" for k, v in mode_counts.most_common()
                )
                lines.append(f"  ({mix})")
            # 최근 5경기만
            for g in self.my_games[:5]:
                mark = result_ko(g.win)
                ctx = (
                    loc.mode(g.mode_label)
                    if "ARAM" in g.mode_label
                    else loc.role(g.role)
                )
                if is_aram:
                    lines.append(
                        f"    [{mark}] {g.kda_str}  딜 {g.damage_to_champs:,}  {ctx}"
                    )
                else:
                    lines.append(
                        f"    [{mark}] {g.kda_str}  CS {g.cs}({g.cs_per_min}/분)  {ctx}"
                    )

        # 코칭 (최대 3개, 중복 문구 제거)
        if self.advice:
            lines.append("")
            lines.append("  ▸ 코칭")
            seen: set[str] = set()
            # 「내 최근」에 이미 쓴 데이터 부족 문구는 코칭에서 생략
            skip_prefix = "최근 "
            idx = 1
            for tip in self.advice:
                if tip in seen:
                    continue
                if tip.startswith(skip_prefix) and "데이터가 부족" in tip:
                    continue
                seen.add(tip)
                lines.append(f"  {idx}. {tip}")
                idx += 1
                if idx > 3:
                    break

        lines.append(footer())
        return "\n".join(lines)


class CoachEngine:
    def __init__(self, ddragon: DataDragon | None = None):
        self.dd = ddragon or DataDragon(language="ko_KR")
        self.loc = get_localizer()

    def _champ_ko(self, name: str) -> str:
        return self.loc.champion(name) or name

    def _items_ko(self, items: list[str]) -> list[str]:
        return self.loc.items(items)

    def compare(
        self,
        meta: ChampionBuild,
        my_games: list[MatchSummary],
        role: str,
    ) -> CoachReport:
        self.loc.ensure_loaded()
        self.dd.ensure_loaded()
        is_aram = meta.mode == "aram" or role.upper() == "ARAM"
        report = CoachReport(
            champion=meta.champion,
            role=role,
            meta=meta,
            my_games=my_games,
            localizer=self.loc,
        )

        keystone = (
            self.loc.rune(meta.runes.keystone) if meta.runes.keystone else ""
        )
        spells = self.loc.spells(meta.summoner_spells)
        core = self._items_ko(meta.core_items.items)
        tips: list[str] = []

        # ── 데이터 없음 (안내 문구는 render의 「내 최근」에 표시) ──
        if not my_games:
            build_bits = []
            if keystone:
                build_bits.append(f"룬 {keystone}")
            if meta.skills.priority:
                build_bits.append("스킬 " + " › ".join(meta.skills.priority))
            if core:
                build_bits.append("코어 " + " → ".join(core[:5]))
            if spells:
                build_bits.append("스펠 " + " + ".join(spells))
            if build_bits:
                tips.append("이번 판: " + " / ".join(build_bits))
            if is_aram:
                tips.append(
                    "한타 생존이 우선입니다. 포킹 때 체력을 아끼고, "
                    "표식은 한타 시작·추노에만 쓰세요."
                )
            else:
                tips.append(
                    "1~3코어는 메타 루트를 우선 고정하고, "
                    "4~5코어는 상대 조합 보고 방어·관통 옵션으로 분기하세요."
                )
            report.advice = tips[:3]
            report.natural_language = self._one_liner(meta, None)
            return report

        wins = sum(1 for g in my_games if g.win)
        n = len(my_games)
        my_wr = 100.0 * wins / n
        avg_kda = sum(g.kda_ratio for g in my_games) / n
        avg_cspm = sum(g.cs_per_min for g in my_games) / n
        avg_deaths = sum(g.deaths for g in my_games) / n
        avg_dmg = sum(g.damage_to_champs for g in my_games) / n
        mayhem_n = sum(1 for g in my_games if g.mode_label == "ARAM Mayhem")

        # ── 승률 비교 ──
        if meta.win_rate is not None:
            if my_wr + 4 < meta.win_rate:
                tips.append(
                    f"최근 승률 {my_wr:.0f}%로 메타({meta.win_rate:.1f}%)보다 낮습니다. "
                    f"{keystone or '메타 룬'} + "
                    f"{' → '.join(core[:5]) or '코어 아이템'} 루트를 맞춰 보세요."
                )
            elif my_wr > meta.win_rate + 6:
                tips.append(
                    f"최근 승률 {my_wr:.0f}%로 좋습니다. "
                    "지금 템포를 유지하되 코어 완성 타이밍만 점검하세요."
                )

        if is_aram:
            tips.extend(
                self._aram_tips(
                    avg_kda, avg_deaths, avg_dmg, mayhem_n, n, spells, core
                )
            )
        else:
            if avg_cspm < 5.5 and role.upper() in (
                "MIDDLE",
                "MID",
                "TOP",
                "BOTTOM",
                "ADC",
            ):
                tips.append(
                    f"CS/분 {avg_cspm:.1f}로 낮습니다. "
                    "웨이브 정리 후 백 타이밍을 일정하게 가져가면 코어가 빨라집니다."
                )
            if avg_deaths >= 6:
                tips.append(
                    f"평균 데스 {avg_deaths:.1f}. "
                    "솔킬 각을 줄이면 승률이 바로 반응합니다."
                )
            if avg_kda < 2.0:
                tips.append(
                    f"KDA {avg_kda:.2f}. 킬 욕심보다 위치 선정이 먼저입니다."
                )
            elif avg_kda >= 3.5 and my_wr < 55:
                tips.append(
                    "전투 지표는 좋은데 승률이 아쉽습니다. "
                    "오브젝트·타워로 이득을 전환하는 습관을 들이세요."
                )

        # 아이템 비교
        if core:
            player_items: Counter[str] = Counter()
            for g in my_games:
                for iid in g.items:
                    name = self.dd.item_name(iid)
                    if name:
                        player_items[name] += 1
            if player_items:
                top = {n for n, _ in player_items.most_common(5)}
                overlap = set(core) & top
                if not overlap:
                    tips.append(
                        f"최근 빌드가 메타 코어({', '.join(core[:5])})와 다릅니다. "
                        "1~3코어만이라도 맞춰 보세요."
                    )

        if not tips:
            tips.append(
                f"큰 문제는 없어 보입니다. {keystone or '메타 룬'}과 "
                f"{' → '.join(core[:5]) or '코어'} 루트를 기준으로 유지하세요."
            )

        report.advice = tips[:4]
        report.natural_language = self._one_liner(
            meta, {"wr": my_wr, "kda": avg_kda, "n": n}
        )
        return report

    def _aram_tips(
        self,
        avg_kda: float,
        avg_deaths: float,
        avg_dmg: float,
        mayhem_n: int,
        n: int,
        spells: list[str],
        core: list[str],
    ) -> list[str]:
        tips: list[str] = []
        if mayhem_n:
            tips.append(
                f"아수라장 {mayhem_n}/{n}판 포함. "
                "오그먼트에 맞춰 딜/탱 비중만 조절하고, 코어 골격은 유지하세요."
            )
        if avg_deaths >= 7:
            tips.append(
                f"평균 데스 {avg_deaths:.1f}로 높습니다. "
                "포킹 페이즈에 체력을 아끼고, 한타 전 부시를 확인하세요."
            )
        if avg_kda < 2.0:
            tips.append(
                "칼바람은 킬보다 한타 생존·광역 기여가 중요합니다. "
                "앞라인 너머에서 스킬만 빼고 죽지 마세요."
            )
        if avg_dmg < 15000 and n >= 3:
            tips.append(
                f"평균 딜 {int(avg_dmg):,}. "
                f"{' → '.join(core[:3]) or '코어'} 완성 후 포킹 쿨을 비우세요."
            )
        if spells and not tips:
            tips.append(
                f"스펠은 {' + '.join(spells)} 고정. "
                "표식은 한타 시작·추노에만 쓰세요."
            )
        return tips

    def _one_liner(
        self,
        meta: ChampionBuild,
        stats: dict | None,
    ) -> str:
        champ = self._champ_ko(meta.champion)
        keystone = (
            self.loc.rune(meta.runes.keystone) if meta.runes.keystone else "메타 룬"
        )
        core = self._items_ko(meta.core_items.items)
        core_s = " → ".join(core[:5]) if core else "메타 코어"
        if stats is None:
            if meta.mode == "aram":
                return (
                    f"{champ} 칼바람은 {keystone} + {core_s}로 가져가고, "
                    "한타 생존을 최우선으로 하세요."
                )
            return (
                f"{champ}은(는) {keystone} + {core_s} 루트가 무난합니다. "
                "1~3코어는 메타 고정, 4~5코어는 매치업 보고 방어·관통으로 분기하세요."
            )
        return (
            f"요약: 데스 줄이기 · {keystone} 고정 · {core_s} 정렬 — "
            "이 세 가지만 지켜도 체감이 달라집니다."
        )
