"""카운터픽 기반 라인전 팁 · 조합 유의점 (한국어)."""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.blitz.models import CounterPick, CounterReport
from lol_coach.blitz.parser import ROLE_KO
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer

# Data Dragon tags → 한글 성향
TAG_KO = {
    "Assassin": "암살자",
    "Fighter": "전사",
    "Mage": "마법사",
    "Marksman": "원거리 딜러",
    "Support": "서포터",
    "Tank": "탱커",
}


@dataclass
class DraftAdvice:
    enemy_ko: str
    role_ko: str
    patch: str
    counters: list[tuple[str, CounterPick]]  # (한글명, pick)
    lane_tips: list[str] = field(default_factory=list)
    comp_notes: list[str] = field(default_factory=list)
    source_url: str = ""
    stale_cache: bool = False
    cache_age_s: float = 0.0



class DraftCoach:
    def __init__(self, ddragon: DataDragon | None = None):
        self.dd = ddragon or DataDragon(language="ko_KR")
        self.loc = get_localizer()

    def _champ_data(self, name: str) -> dict | None:
        return self.dd.resolve_champion(name)

    def _tags(self, name: str) -> list[str]:
        c = self._champ_data(name)
        if not c:
            return []
        return list(c.get("tags") or [])


    def advise(self, report: CounterReport, top_n: int = 8) -> DraftAdvice:
        self.dd.ensure_loaded()
        self.loc.ensure_loaded()
        enemy_ko = self.loc.champion(report.enemy) or report.enemy
        role_key = report.role.strip().lower()
        role_ko = ROLE_KO.get(role_key, role_key)

        counters: list[tuple[str, CounterPick]] = []
        for c in report.lane_counters[:top_n]:
            ko = self.loc.champion(c.champion) or c.champion
            counters.append((ko, c))

        lane_tips = self._lane_tips(report.enemy, role_key, counters)
        comp_notes = self._comp_notes(report.enemy, role_key, counters)

        return DraftAdvice(
            enemy_ko=enemy_ko,
            role_ko=role_ko,
            patch=report.patch,
            counters=counters,
            lane_tips=lane_tips,
            comp_notes=comp_notes,
            source_url=report.source_url,
            stale_cache=report.stale_cache,
            cache_age_s=report.cache_age_s,
        )

    def _lane_tips(
        self,
        enemy: str,
        role: str,
        counters: list[tuple[str, CounterPick]],
    ) -> list[str]:
        enemy_ko = self.loc.champion(enemy) or enemy
        tags = set(self._tags(enemy))
        tips: list[str] = []

        # 공통
        tips.append(
            f"{enemy_ko} 상대 핵심: 3레벨·6레벨 타이밍을 미리 세고, "
            "상대 핵심 스킬 쿨일 때만 강하게 교환하세요."
        )

        if "Assassin" in tags:
            tips.append(
                "암살자형입니다. 부시·강가 시야를 챙기고, "
                "실명/속박/에어본 등 하드 CC가 없으면 무리한 올인을 피하세요."
            )
        if "Mage" in tags:
            tips.append(
                "스킬샷 마법사입니다. 미니언 뒤로 스킬을 빼 두고, "
                "한 방 콤보를 낭비한 직후가 반격 타이밍입니다."
            )
        if "Marksman" in tags:
            tips.append(
                "원거리 딜러입니다. 얼리 게임 사거리 싸움을 피하고, "
                "얼어붙은 말릭/판금 등 방어 템포를 빠르게 올리세요."
            )
        if "Tank" in tags or "Fighter" in tags:
            tips.append(
                "근거리 브루저/탱 성향입니다. 프리힛만 주고 길게 붙지 마세요. "
                "퍼센트 체력·방관 아이템 타이밍이 중요합니다."
            )
        if "Support" in tags and role in ("support", "supp", "utility", "adc", "bottom"):
            tips.append("봇 라인: 로밍 각을 읽고, 2레벨 싸움·대포 웨이브 타이밍을 지키세요.")

        if role in ("jungle", "jg"):
            tips.append(
                "정글: 상대 동선 예측이 우선입니다. "
                "초반 풀캠프보다 카운터 정글·갱 타이밍을 챙기세요."
            )
        elif role in ("mid", "middle"):
            tips.append(
                "미드: 우선권(우선 푸시)을 가져가면 시야·로밍이 열립니다. "
                "카운터픽은 초반 GD 우위를 눈덩이처럼 굴리세요."
            )
        elif role == "top":
            tips.append(
                "탑: 텔레포트·세트업보다 라인 주도권이 중요합니다. "
                "죽지 않는 교환으로 격차를 유지하세요."
            )

        if counters:
            top_name, top_c = counters[0]
            tips.append(
                f"1순위 카운터 {top_name}은(는) 15분 기준 골드 우위 "
                f"{top_c.gd15_str} 정도입니다. 초반 교환 승리를 눈덩이로 키우세요."
            )

        return tips[:5]

    def _comp_notes(
        self,
        enemy: str,
        role: str,
        counters: list[tuple[str, CounterPick]],
    ) -> list[str]:
        notes: list[str] = []
        enemy_ko = self.loc.champion(enemy) or enemy
        enemy_tags = set(self._tags(enemy))

        # Aggregate counter tags
        tag_count: dict[str, int] = {}
        for name, _ in counters[:6]:
            for t in self._tags(name):
                tag_count[t] = tag_count.get(t, 0) + 1

        if tag_count.get("Assassin", 0) >= 3:
            notes.append(
                "추천 카운터 중 암살자 비중이 높습니다. "
                "후반 한타 안정성을 위해 탱/이니시에이터가 팀에 있는지 확인하세요."
            )
        if tag_count.get("Mage", 0) >= 3:
            notes.append(
                "AP 카운터가 많습니다. 원딜·탑이 AP면 마법 저항 스택이 부담될 수 있습니다."
            )
        if tag_count.get("Marksman", 0) >= 2 and role in ("adc", "bottom"):
            notes.append("원딜 카운터 싸움입니다. 서폿 조합(하드 CC vs 힐/실드)이 승패를 가릅니다.")
        if tag_count.get("Tank", 0) + tag_count.get("Fighter", 0) >= 3:
            notes.append(
                "브루저/탱 카운터가 많습니다. 한타 진입은 안정적이나, "
                "원거리 포킹 조합이면 접근이 어려울 수 있습니다."
            )

        if "Assassin" in enemy_tags:
            notes.append(
                f"{enemy_ko}는 암살 각이 있습니다. 아군 스쿼시에 보호 스펠·시야를 배정하세요."
            )
        if "Tank" in enemy_tags:
            notes.append(
                f"{enemy_ko} 상대로는 방관/%체력 딜이 필요합니다. "
                "순수 누킹만 있는 조합은 후반이 답답해질 수 있습니다."
            )
        if "Mage" in enemy_tags and role in ("mid", "middle"):
            notes.append(
                "미드 메이지 구도: 정글과 타이밍 갱을 약속하면 라인전 우위가 오브젝트로 이어집니다."
            )

        if not notes:
            notes.append(
                "특정 카운터 하나에 올인하기보다, "
                "팀 조합(탱·이니시·원거리 딜) 균형을 보고 고르세요."
            )
        notes.append(
            "카운터픽도 숙련도가 낮으면 의미가 줄어듭니다. "
            "익숙한 픽 중 GD@15가 좋은 쪽을 고르는 게 실전적입니다."
        )
        return notes[:5]

    def matchup_tips(
        self,
        my_champ: str,
        enemy: str,
        role: str,
        gd15: int | None = None,
    ) -> list[str]:
        """내가 특정 카운터픽으로 적을 상대할 때 팁."""
        self.dd.ensure_loaded()
        self.loc.ensure_loaded()
        me = self.loc.champion(my_champ) or my_champ
        them = self.loc.champion(enemy) or enemy
        my_tags = set(self._tags(my_champ))
        en_tags = set(self._tags(enemy))
        tips: list[str] = []

        tips.append(
            f"【{me} vs {them}】 레벨 1~3 사거리·선공을 파악하고, 3·6 타이밍을 캘린더처럼 외우세요."
        )
        if gd15 is not None and gd15 > 0:
            tips.append(
                f"통계상 15분 골드 우위 약 {gd15:+d}. "
                "초반 작은 이득을 타워·전령으로 굴리는 게 목표입니다."
            )

        # Matchup archetypes
        if "Assassin" in en_tags and "Mage" in my_tags:
            tips.append(
                f"{them} 암살 각 주의. 실명/속박 없이 앞으로 나가지 말고, "
                "콤보 빠진 직후만 짧게 때리세요."
            )
        if "Mage" in en_tags and ("Assassin" in my_tags or "Fighter" in my_tags):
            tips.append(
                f"{them} 스킬샷을 미니언 뒤로 빼고, 한 방 콤보 쿨에 붙는 것이 기본 루트입니다."
            )
        if "Fighter" in en_tags or "Tank" in en_tags:
            tips.append(
                "길게 붙으면 손해입니다. 프리힛 2~3대 후 빼기, 체력 격차가 날 때만 올인하세요."
            )
        if "Marksman" in en_tags:
            tips.append(
                "사거리 싸움입니다. 부시·미니언을 끼고 접근하고, 얼리 방어 옵션을 빠르게 올리세요."
            )
        if "Assassin" in my_tags:
            tips.append(f"{me} 암살 패턴: 시야 없는 각·상대 핵심 스킬 빠진 뒤에만 들어가세요.")
        if "Mage" in my_tags:
            tips.append(
                f"{me} 포킹형이면 웨이브를 먼저 밀고 시야를 먹으세요. "
                "로밍 각은 대포 웨이브 이후가 안전합니다."
            )

        role = role.lower()
        if role in ("mid", "middle"):
            tips.append("미드: 우선권(우선 푸시) → 강가 시야 → 바텀/정글 합류 순서를 지키세요.")
        elif role == "top":
            tips.append(
                "탑: 텔레포트 싸움보다 라인 주도권이 우선. 죽지 않는 교환으로 격차를 유지하세요."
            )
        elif role in ("adc", "bottom"):
            tips.append("봇: 2레벨·대포 웨이브 타이밍을 서폿과 공유하세요.")
        elif role in ("support", "utility"):
            tips.append("서폿: 시야·로밍이 핵심. 원딜이 안전할 때만 강가로 움직이세요.")
        elif role in ("jungle",):
            tips.append("정글: 이 매치업이 유리하면 그 라인 캠프를 우선 챙기세요.")

        tips.append(f"라인전 후: {them}이(가) 실종되면 핑으로 알리고, 혼자 강가를 밀지 마세요.")
        return tips[:6]

