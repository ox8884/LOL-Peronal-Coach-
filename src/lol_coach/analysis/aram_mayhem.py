"""ARAM 아수라장 — 증강 추천 · 회피 · ARAM 아이템 빌드 (룬 없음).

이 모듈은 수동으로 제시된 증강 이름/기록만을 대상으로 합니다.
추천은 Blitz 카탈로그의 공식 한글 사실(등급, 희귀도, 챔프 성향 시너지/주의)과
Data Dragon 스킬 정보를 조합해 생성되며, 제시되지 않은 증강은 절대
추천하지 않습니다. ARAM 코어 아이템은 Blitz 패키지 데이터를 우선 사용하고,
데이터가 없을 때 일반 폴백으로 보완하며 출처를 명확히 표기합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from lol_coach.blitz.models import BlitzError, BuildSection, ChampionBuild
from lol_coach.static.augment_catalog import AugmentCatalog, AugmentRecord
from lol_coach.static.blitz_aram import BlitzAramBuild, BlitzAramCatalog
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer

# blitz 카탈로그 지연 로드 센티널 — None(없음 확인됨)과 구별
_UNSET = object()

_RARITY_LABEL: dict[str, str] = {
    "prismatic": "프리즘",
    "gold": "골드",
    "silver": "실버",
    "": "기타",
}

_TIER_BASE: dict[str, float] = {"S": 3.0, "A": 2.0, "B": 0.5, "": 0.0}
_TIER_LABEL: dict[str, str] = {"S": "S", "A": "A", "B": "B", "": "?"}


def _norm_aug(en: str) -> str:
    """유니코드 아포스트로피/공백 정규화 (카탈로그·아이콘 키 일치용)."""
    s = (en or "").strip()
    for a, b in (
        ("\u2019", "'"),  # ’
        ("\u2018", "'"),  # ‘
        ("\u2032", "'"),
        ("`", "'"),
        ("\u00a0", " "),
    ):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class AugmentPick:
    """한 개의 제시된 증강에 대한 판정 정보."""

    record: AugmentRecord
    tier: str
    score: float
    reason: str

    @property
    def name_en(self) -> str:
        return self.record.name_en

    @property
    def name_ko(self) -> str:
        return self.record.name_ko or self.record.name_en

    @property
    def desc(self) -> str:
        return self.record.description_ko or "효과 확인 후 선택"

    @property
    def rarity(self) -> str:
        return self.record.rarity

    @property
    def label(self) -> str:
        return f"{self.name_ko} — {self.desc}"


@dataclass
class AugmentValidation:
    """사용자가 제시한 증강 목록의 검증 결과."""

    valid: list[AugmentRecord]
    unknowns: list[str]
    duplicates: list[str]


@dataclass
class SourceInfo:
    """출처·신선도 정보."""

    primary: str
    primary_url: str
    secondary: str
    secondary_url: str
    patch: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AugmentTierTop:
    silver: tuple[AugmentPick, ...] = ()
    gold: tuple[AugmentPick, ...] = ()
    prismatic: tuple[AugmentPick, ...] = ()


@dataclass
class RerollAdvice:
    """리롤 결정 어드바이저 — 챔프 티어·내 풀 표본 기반.

    표본·데이터 부족이면 침묵(actions=빈 리스트)한다 (정찰 칩 원칙 동일).
    """

    tier: str  # S/A/B — 챔프의 아수라장 티어 (Blitz 챔프별 순위 기반)
    champ_rank: int  # Blitz 챔프별 순위(1부터) 또는 0(데이터 없음)
    champ_total: int  # 전체 챔프 수(티어 표 기준)
    actions: list[str] = field(default_factory=list)


@dataclass
class MayhemAdvice:
    champ_ko: str
    patch: str
    champ_key: str = ""  # Data Dragon id (Ahri) — 아이콘용
    fixed_top: AugmentTierTop = field(default_factory=AugmentTierTop)
    top_augments: list[AugmentPick] = field(default_factory=list)
    avoid_augments: list[AugmentPick] = field(default_factory=list)
    build: ChampionBuild | None = None
    core_slots: list[str] = field(default_factory=list)
    core_item_ids: list[int | None] = field(default_factory=list)
    play_tips: list[str] = field(default_factory=list)
    source_url: str = ""
    build_url: str = ""
    augment_validation: AugmentValidation = field(
        default_factory=lambda: AugmentValidation([], [], [])
    )
    source: SourceInfo | None = None
    reroll: RerollAdvice | None = None
    synergy_lines: list[str] = field(default_factory=list)
    adaptive_build_note: str = ""
    augment_source: str = ""  # 증강 TOP 데이터 출처·시점 (보드 하단 표기)


class MayhemCoach:
    """ARAM Mayhem 증강 코치.

    `advise`는 반드시 수동으로 제시된 증강 이름 리스트를 받습니다.
    제시되지 않은 증강은 추천·회피 목록에 포함되지 않습니다.
    """

    BLITZ_PAGE = "https://blitz.gg/ko/lol/aram-mayhem-augments"
    CATALOG_SOURCE = "Blitz.gg ARAM Mayhem 한국어 증강·아이템 카탈로그"

    def __init__(
        self,
        ddragon: DataDragon | None = None,
        catalog: AugmentCatalog | None = None,
        blitz: BlitzAramCatalog | None = None,
        blitz_client: Any | None = None,
    ):
        self.dd = ddragon or DataDragon(language="ko_KR")
        self.loc = get_localizer()
        # 카탈로그(패키지 JSON 556KB 파싱)는 첫 advise 까지 미룬다 —
        # 앱 생성 경로(CoachApp.__init__)에서 첫 창 표시가 늦어지는 것 방지
        self._catalog: AugmentCatalog | None = catalog
        self._blitz_cat: BlitzAramCatalog | None | object = blitz if blitz is not None else _UNSET
        # 라이브 챔피언별 증강 티어 조회용 (BlitzClient 공용 캐시 재사용)
        self._blitz_client = blitz_client

    @property
    def catalog(self) -> AugmentCatalog:
        if self._catalog is None:
            self._catalog = AugmentCatalog()
        return self._catalog

    @catalog.setter
    def catalog(self, value: AugmentCatalog) -> None:
        self._catalog = value

    @property
    def blitz(self) -> BlitzAramCatalog | None:
        if self._blitz_cat is _UNSET:
            try:
                self._blitz_cat = BlitzAramCatalog.packaged()
            except (FileNotFoundError, OSError, ValueError):
                self._blitz_cat = None
        assert self._blitz_cat is not _UNSET
        return self._blitz_cat  # type: ignore[return-value]

    @blitz.setter
    def blitz(self, value: BlitzAramCatalog | None) -> None:
        self._blitz_cat = value

    def _record_tier(self, rec: AugmentRecord) -> str:
        return rec.fallback_tier

    def _record_rarity(self, rec: AugmentRecord) -> str:
        return rec.rarity

    def resolve_offered(
        self,
        offered: list[str],
        *,
        strict: bool = False,
    ) -> AugmentValidation:
        """사용자가 수동 제시한 증강 이름을 카탈로그로 정규화·중복 제거."""
        records, unknowns, duplicates = self.catalog.resolve_many(offered, strict=strict)
        return AugmentValidation(valid=list(records), unknowns=unknowns, duplicates=duplicates)

    def _score_record(
        self,
        rec: AugmentRecord,
        tags: set[str],
    ) -> tuple[float, str]:
        tier = self._record_tier(rec)
        base = _TIER_BASE.get(tier, 0.0)
        prefer = set(rec.archetype_prefer) & tags
        avoid = set(rec.archetype_avoid) & tags
        bonus = 1.5 * len(prefer) - 2.0 * len(avoid)
        score = base + bonus

        rarity_label = _RARITY_LABEL.get(self._record_rarity(rec), "")
        parts = [f"{rarity_label} {_TIER_LABEL.get(tier, '?')}티어".strip()]
        if prefer:
            parts.append(f"{ko_tag_list(prefer)} 시너지")
        if avoid:
            parts.append(f"{ko_tag_list(avoid)} 주의")
        reason = " · ".join(parts)
        return score, reason

    def _rank_offered(
        self,
        offered: list[AugmentRecord],
        tags: set[str],
    ) -> list[AugmentPick]:
        """제시된 증강 중에서만 순위를 매깁니다(결정적 동점 처리)."""
        picks = self._score_all_offered(offered, tags)
        picks.sort(key=lambda p: (-p.score, self._rarity_rank(p.rarity), (p.name_en or "").lower()))
        return picks

    @staticmethod
    def _rarity_rank(rarity: str) -> int:
        return {"prismatic": 0, "gold": 1, "silver": 2}.get(rarity, 3)

    def _score_all_offered(
        self,
        offered: list[AugmentRecord],
        tags: set[str],
    ) -> list[AugmentPick]:
        """제시된 모든 증강에 점수를 매깁니다."""
        picks: list[AugmentPick] = []
        for rec in offered:
            score, reason = self._score_record(rec, tags)
            picks.append(
                AugmentPick(
                    record=rec,
                    tier=self._record_tier(rec),
                    score=score,
                    reason=reason,
                )
            )
        return picks

    def _avoid_offered(
        self,
        offered: list[AugmentRecord],
        tags: set[str],
        top_ids: set[str],
    ) -> list[AugmentPick]:
        """제시된 증강 중 챔프 성향과 충돌하거나 등급이 낮은 항목을 회피로 꼽습니다.

        top 5 안에 들어간 B/성향충돌 항목은 이미 추천 목록에 노출되므로
        회피 목록에서는 제외합니다. 나머지 중에서 B등급 또는 챔프 성향과
        충돌하는 항목만 회피로 분류합니다.
        """
        picks: list[AugmentPick] = []
        for rec in offered:
            if rec.id in top_ids:
                continue
            tier = self._record_tier(rec)
            avoid = set(rec.archetype_avoid) & tags
            score, reason = self._score_record(rec, tags)
            if tier == "B" or avoid:
                picks.append(
                    AugmentPick(
                        record=rec,
                        tier=tier,
                        score=score,
                        reason=reason,
                    )
                )
        # 동점/순서: 등급 낮음(B) 우선 → 성향 충돌 → 그 외; 이름순 안정화
        picks.sort(
            key=lambda p: (
                0 if p.tier == "B" else 1,
                0 if "주의" in p.reason else 1,
                -p.score,
                (p.name_en or "").lower(),
            )
        )
        return picks[:5]

    def _ability_lines(self, key: str, tags: set[str]) -> list[str]:
        """Data Dragon 스킬 정보에서 챔프 특성에 맞는 2개 이상의 구체적 참고를 뽑습니다."""
        facts = self.dd.ability_facts(key)
        lines: list[str] = []
        if not facts:
            return lines

        # 우선순위: 궁극기는 대부분 의미 있음 → Q/W/E 중 쿨타임이 있는 공격 스킬
        slots = ["R", "Q", "W", "E", "P"]
        for slot in slots:
            if len(lines) >= 2:
                break
            f = facts.get(slot)
            if not f:
                continue
            name = f.get("name", "")
            if not name:
                continue
            cd = f.get("cooldown", "")
            desc = f.get("description", "")
            if slot == "P" and ("Marksman" in tags or "Mage" in tags):
                lines.append(f"{name}(P) 평타·스킬 교환에 활용하세요.")
            elif slot == "R":
                lines.append(f"궁극기 {name} 쿨타임 {cd} — 증강 쿨감/지속 효과와 연계하세요.")
            elif slot in ("Q", "W", "E"):
                # 투사처이나 돌진기를 우선
                lowered = (desc or "").lower()
                if any(k in lowered for k in ("미사일", "발사", "돌진", "구체", "파도")):
                    lines.append(f"{name}({slot}) 활용 빈도를 높이는 증강이 유리합니다.")
                elif cd:
                    lines.append(f"{name}({slot}) 쿨타임 {cd} — 쿨감/연계 증강을 고려하세요.")
        return lines

    def _make_tips(
        self,
        ko: str,
        key: str,
        tags: set[str],
        top: list[AugmentPick],
        avoid: list[AugmentPick],
        *,
        has_offered_augments: bool,
    ) -> list[str]:
        """3~5개의 구체적 팁. >=2개 스킬/운영 참고, >=1개 제시 증강 언급."""
        tips: list[str] = []

        # 0) 제시 상태 안내 (맥락 — 잘림에서 보호하기 위해 선두 배치)
        if has_offered_augments:
            tips.append(f"{ko}: 제시된 증강 안에서 S/A 등급·챔프 성향 시너지를 우선으로 고르세요.")
        else:
            tips.append(
                f"{ko}: 아래 추천은 전체 카탈로그 기준입니다. 실제 선택지가 보이면 입력해 비교하세요."
            )

        # 1) Data Dragon 기반 구체적 스킬/운영 참고 2개 이상
        ability_tips = self._ability_lines(key, tags)
        tips.extend(ability_tips[:2])

        # 2) 제시된 증강 중 추천 시너지/주의 1개 이상
        if top:
            pick = top[0]
            tips.append(f"추천 증강: {pick.name_ko} — {pick.reason}")
        if avoid:
            bad = avoid[0]
            tips.append(f"주의: {bad.name_ko} — {bad.reason}")

        # 3) 역할별 기본 행동 지침
        if "Marksman" in tags:
            tips.append("원거리 딜러는 사거리·생존 우선, 앞라인 뒤에서 평타를 유지하세요.")
        elif "Tank" in tags or "Fighter" in tags:
            tips.append("전선 챔프는 생존·이니시 증강이 팀 기여도를 가장 크게 올립니다.")
        elif "Assassin" in tags:
            tips.append("암살자는 표식(눈덩이) 타고 후방으로 진입한 뒤 궁극기로 마무리하세요.")
        elif "Mage" in tags:
            tips.append("메이지는 포킹 쿨을 비우며 철벽 뒤 위치를 유지하세요.")
        elif "Support" in tags:
            tips.append("서포터는 버프·회복 증강과 팀원 생존 스킬 우선 순위로 삼으세요.")

        # 3~5개로 제한
        return tips[:5]

    def _blitz_augment_picks(self, build: BlitzAramBuild) -> list[AugmentPick]:
        """Return Blitz's champion-specific tier order without rescoring it."""
        tier_labels = (
            ("prismatic", "S", "프리즘"),
            ("gold", "A", "골드"),
            ("silver", "B", "실버"),
        )
        # 티어 간 스코어 충돌 방지 (프리즘 > 골드 > 실버 오프셋)
        tier_score_base = {"prismatic": 300.0, "gold": 200.0, "silver": 100.0}
        picks: list[AugmentPick] = []
        for tier_key, chip_tier, tier_label in tier_labels:
            for index, name_ko in enumerate(build.augment_tiers.get(tier_key, ())):
                record = self.catalog.get_by_name(name_ko)
                if record is not None and record.rarity != tier_key:
                    # 사이트 티어 버킷이 카탈로그 등급과 다르면 사이트 배치를 따른다
                    record = replace(record, rarity=tier_key)
                if record is None:
                    record = AugmentRecord(
                        id=f"blitz:{_norm_aug(name_ko)}",
                        name_en=name_ko,
                        name_ko=name_ko,
                        description_ko="Blitz.gg 챔피언별 추천",
                        rarity=tier_key,
                        fallback_tier=tier_key,
                        aliases=(),
                        image_candidates=(),
                        sources=(),
                        archetype_prefer=(),
                        archetype_avoid=(),
                    )
                picks.append(
                    AugmentPick(
                        record=record,
                        tier=chip_tier,
                        score=tier_score_base[tier_key] - index,
                        reason=f"Blitz.gg {tier_label} 증강 {index + 1}순위",
                    )
                )
        return picks

    def _reroll_advice(
        self,
        key: str,
        ko: str,
        blitz_build: BlitzAramBuild | None,
    ) -> RerollAdvice | None:
        """리롤 결정 칩 — 실제 ARAM 챔프 순위 데이터가 없으므로 항상 None (침묵).

        시그니처는 향후 데이터 소스 연동을 위해 유지한다.
        """
        # 향후 진짜 ARAM 챔프 티어/순위 데이터 소스가 추가되면 구현 예정.
        # 현재 Blitz 빌드는 챔프 강도 신호를 주지 않아 리롤 판단이 불가 → 침묵.
        return None

    def _synergy_lines(
        self,
        tags: set[str],
        top: list[AugmentPick],
        avoid: list[AugmentPick],
    ) -> list[str]:
        """추천·회피 증강의 시너지 근거를 한글 줄로 — archetype_prefer/avoid 노출.

        top/avoid 의 reason 에 이미 'X 시너지'/'X 주의' 가 들어 있으므로
        그것을 한 줄로 정리한다. 데이터 없으면 빈 리스트.
        """
        lines: list[str] = []
        for pick in top[:3]:
            if "시너지" in pick.reason or "주의" in pick.reason:
                lines.append(f"{pick.name_ko} — {pick.reason}")
        for pick in avoid[:2]:
            if "주의" in pick.reason:
                lines.append(f"{pick.name_ko} — {pick.reason}")
        return lines[:5]

    def _fixed_augment_top(self, build: BlitzAramBuild | None) -> AugmentTierTop:
        if build is None:
            return AugmentTierTop()
        picks = self._blitz_augment_picks(build)
        return AugmentTierTop(
            silver=tuple(pick for pick in picks if pick.rarity == "silver")[:3],
            gold=tuple(pick for pick in picks if pick.rarity == "gold")[:3],
            prismatic=tuple(pick for pick in picks if pick.rarity == "prismatic")[:3],
        )

    def _fallback_boot(self, tags: set[str]) -> str:
        """챔프 태그 기준 기본 신발."""
        if "Marksman" in tags:
            return "광전사의 군화"
        if "Tank" in tags or "Fighter" in tags:
            return "헤르메스의 발걸음"
        if "Assassin" in tags or "Support" in tags:
            return "명석함의 아이오니아 장화"
        return "마법사의 신발"

    def _complete_core_slots(
        self,
        primary: list[str],
        tags: set[str],
    ) -> list[str]:
        boots = self._fallback_boot(tags)
        slots: list[str] = []
        for item in [*primary, *self._fallback_cores(tags), boots]:
            if item and item not in slots:
                slots.append(item)
            if len(slots) == 6:
                break
        return slots

    def analyze(
        self,
        champion: str,
        offered_augments: list[str] | None = None,
    ) -> MayhemAdvice:
        """`advise` 별칭 — GUI/레거시 호출 호환."""
        return self.advise(champion, offered_augments=offered_augments)

    def advise(
        self,
        champion: str,
        offered_augments: list[str] | None = None,
        *,
        use_live: bool = True,
    ) -> MayhemAdvice:
        """챔피언과 수동 제시된 증강 목록을 받아 ARAM Mayhem 코칭을 반환합니다.

        Args:
            champion: 챔피언 이름/키 (한글·영문 모두 가능).
            offered_augments: 사용자가 제시한 증강 이름 리스트. 비어 있으면
                증강 추천 없이 빌드/팁만 제공합니다.
            use_live: False면 네트워크 없이 패키지 스냅샷만으로 즉시 반환
                (빠른 첫 렌더 → 라이브 재렌더 패턴용).
        """
        self.dd.ensure_loaded()
        self.loc.ensure_loaded()

        c = self.dd.resolve_champion(champion)
        if not c:
            raise BlitzError(f"챔피언을 찾을 수 없습니다: {champion}")
        key, ko = c["id"], c["name"]
        tags = set(c.get("tags") or [])

        validation = self.resolve_offered(offered_augments or [])
        blitz_build: BlitzAramBuild | None = self.blitz.get(key) if self.blitz is not None else None

        # ── 챔피언 맞춤 증강 TOP: blitz.gg 라이브 티어 우선, 실패 시 패키지 스냅샷 ──
        live_top = None
        page_core: tuple[list[str], list[int]] | None = None
        if use_live and self._blitz_client is not None:
            # 증강 티어 + 사이트 빌드 순서를 병렬 조회 (지연 절반)
            try:
                from lol_coach.blitz.mayhem_live import fetch_live_all

                live_top, page_core = fetch_live_all(
                    key, str(c.get("key") or ""), client=self._blitz_client
                )
            except Exception:
                live_top = None
                page_core = None
        augment_source = ""
        if live_top is not None:
            blitz_picks = self._live_augment_picks(live_top)
            fixed_top = self._live_augment_top(live_top, picks=blitz_picks)
            augment_source = (
                f"blitz.gg 실시간 챔피언 티어 · 패치 {live_top.patch} · 데이터 {live_top.updated}"
            )
        else:
            fixed_top = self._fixed_augment_top(blitz_build)
            if blitz_build is not None and blitz_build.augment_tiers:
                augment_source = (
                    f"blitz.gg 스냅샷 · 패치 {blitz_build.patch}"
                    f" · 데이터 {str(self.catalog.updated_at)[:10]}"
                )

        if blitz_build is not None and blitz_build.augment_tiers:
            if live_top is None:
                blitz_picks = self._blitz_augment_picks(blitz_build)
            if validation.valid:
                offered_names = {
                    name
                    for record in validation.valid
                    for name in (
                        _norm_aug(record.name_ko),
                        _norm_aug(record.name_en),
                    )
                }
                ranked = [pick for pick in blitz_picks if _norm_aug(pick.name_ko) in offered_names]
                top_ids = {pick.record.id for pick in ranked}
                avoid = self._avoid_offered(validation.valid, tags, top_ids)
            else:
                ranked = blitz_picks
                avoid = []
        else:
            candidates = validation.valid or list(self.catalog.records)
            ranked = self._rank_offered(candidates, tags)
            top_ids = {p.record.id for p in ranked[:5]}
            avoid = self._avoid_offered(validation.valid, tags, top_ids)

        build_failure = ""
        # 1순위: blitz.gg 챔피언 페이지의 '완성 아이템' 순서 (사이트 그대로)
        if use_live and live_top is not None and self._blitz_client is not None:
            try:
                from lol_coach.blitz.mayhem_live import fetch_live_build_order

                if page_core is None:
                    page_core = fetch_live_build_order(
                        key,
                        client=self._blitz_client,
                        patch=live_top.patch if live_top is not None else "",
                    )
            except Exception:
                page_core = None
        # 2순위: 티어 데이터 근사(티어 → 싼 순), 3순위: 패키지 스냅샷
        live_core: tuple[list[str], list[int]] | None = None
        core_item_ids: list[int | None]
        live = live_top
        if page_core is None and live is not None:
            live_core = self._live_core_items(live, tags)
        if page_core is not None:
            page_slots, page_item_ids = page_core
            core_slots = list(page_slots)
            core_item_ids = list(page_item_ids)
            assert live is not None
            build_url = f"https://blitz.gg/ko/lol/champions/{key}/aram-mayhem"
            build = ChampionBuild(
                champion=ko,
                role="aram",
                patch=live.patch,
                source_url=build_url,
                mode="aram",
                core_items=BuildSection(label="Core Items", items=core_slots),
            )
        elif live_core is not None:
            # _live_core_items 가 6슬롯(구매 순서·신발 포함)을 완성해 준다
            live_slots, live_item_ids = live_core
            core_slots = list(live_slots)
            core_item_ids = list(live_item_ids)
            assert live is not None
            build_url = self.BLITZ_PAGE
            build = ChampionBuild(
                champion=ko,
                role="aram",
                patch=live.patch,
                source_url=build_url,
                mode="aram",
                core_items=BuildSection(label="Core Items", items=core_slots),
            )
        elif blitz_build is not None:
            core_slots = self._complete_core_slots(
                [item.name_ko for item in blitz_build.core_items], tags
            )
            ids_by_name = {item.name_ko: int(item.item_id) for item in blitz_build.core_items}
            core_item_ids = [
                ids_by_name.get(name) or self.dd.item_id_for_name(name) for name in core_slots
            ]
            build_url = blitz_build.source_url
            build = ChampionBuild(
                champion=ko,
                role="aram",
                patch=blitz_build.patch,
                source_url=build_url,
                mode="aram",
                core_items=BuildSection(label="Core Items", items=core_slots),
            )
        else:
            # Blitz 카탈로그 누락 — 클래식 폴백 (코어 빌드만)
            build_failure = "Blitz 카탈로그에 이 챔피언 빌드가 없습니다"
            core_slots, build_url = (
                self._complete_core_slots([], tags),
                "",
            )
            build = ChampionBuild(
                champion=ko,
                role="aram",
                patch="",
                mode="aram",
                core_items=BuildSection(label="Core Items", items=core_slots),
            )
            core_item_ids = [self.dd.item_id_for_name(name) for name in core_slots]

        patch = blitz_build.patch if blitz_build is not None else self.catalog.patch or ""
        if live_top is not None:
            patch = live_top.patch
        tips = self._make_tips(
            ko, key, tags, ranked, avoid, has_offered_augments=bool(validation.valid)
        )
        if blitz_build is None and build_failure:
            # 카탈로그 폴백 안내와 병합하거나 마지막 팁을 대체 (5개 제한 유지)
            note = f"(빌드 정보 없음 — {build_failure})"
            merged = False
            for i, tip in enumerate(tips):
                if "전체 카탈로그 기준" in tip:
                    tips[i] = f"{tip} {note}"
                    merged = True
                    break
            if not merged:
                tips = tips[:4] + [note]

        source = SourceInfo(
            primary=self.CATALOG_SOURCE,
            primary_url=self.BLITZ_PAGE,
            secondary=("정적 클래식 폴백 (실시간 빌드 없음)" if blitz_build is None else ""),
            secondary_url="",
            patch=patch,
            updated_at=(live_top.updated if live_top is not None else self.catalog.updated_at),
        )

        advice = MayhemAdvice(
            champ_ko=ko,
            patch=patch,
            champ_key=key,
            fixed_top=fixed_top,
            top_augments=ranked[:5],
            avoid_augments=avoid,
            build=build,
            core_slots=core_slots,
            core_item_ids=core_item_ids,
            play_tips=tips,
            source_url=self.BLITZ_PAGE,
            build_url=build_url,
            augment_validation=validation,
            source=source,
            reroll=self._reroll_advice(key, ko, blitz_build),
            synergy_lines=self._synergy_lines(tags, ranked, avoid),
            augment_source=augment_source,
        )
        return advice

    def _live_augment_record(self, aug: Any) -> AugmentRecord:
        """라이브 증강 → 카탈로그 레코드 (제시 증강 판정·렌더 공용).

        한글명이 패키지 카탈로그에 있으면 그 레코드를 재사용해
        영문명·아이콘 후보를 그대로 쓴다.
        """
        try:
            known = self.catalog.get_by_name(aug.name_ko)
        except Exception:
            known = None
        if known is not None:
            return known
        tier_chip = {1: "S", 2: "A", 3: "B", 4: "B", 5: "B"}.get(int(aug.tier), "B")
        desc = re.sub(r"<[^>]+>", "", aug.description_ko or "")
        desc = re.sub(r"\?{2,}", "", desc)  # 게임데이터 플레이스홀더(??) 제거
        desc = re.sub(r"\s+", " ", desc).strip()
        if len(desc) > 160:
            desc = desc[:159] + "…"
        return AugmentRecord(
            id=f"live:{aug.augment_id}",
            name_en=aug.name_en or str(aug.augment_id),
            name_ko=aug.name_ko,
            description_ko=desc or "blitz.gg 실시간 챔피언별 티어",
            rarity=aug.rarity,
            fallback_tier=tier_chip,
            aliases=(),
            image_candidates=(),
            sources=(),
            archetype_prefer=(),
            archetype_avoid=(),
        )

    def _live_augment_picks(self, live: Any) -> list[AugmentPick]:
        """라이브 챔피언 티어 전체 → AugmentPick (프리즘>골드>실버, 티어 1이 먼저)."""
        base = {"prismatic": 300.0, "gold": 200.0, "silver": 100.0}
        chip = {"prismatic": "S", "gold": "A", "silver": "B"}
        picks: list[AugmentPick] = []
        for rarity in ("prismatic", "gold", "silver"):
            for index, aug in enumerate(live.by_rarity.get(rarity, ())):
                picks.append(
                    AugmentPick(
                        record=self._live_augment_record(aug),
                        tier=chip[rarity],
                        score=base[rarity] + (6 - aug.tier) - index * 0.01,
                        reason=f"blitz.gg 실시간 티어 {aug.tier} ({rarity})",
                    )
                )
        picks.sort(key=lambda pick: pick.score, reverse=True)
        return picks

    def _live_core_items(
        self, live: Any, tags: set[str]
    ) -> tuple[list[str], list[int]] | None:
        """라이브 아이템 티어 → 구매 순서로 정렬된 6슬롯 (이름, 아이템 ID).

        - 완성템( depth>=2 · 2500골드 이상 · 구매 가능 · 칼바람 사용 )만 코어로
        - 정렬은 티어 오름 → 골드 오름 (싼 것이 먼저 산다 = 1슬롯이 첫 코어)
        - 신발은 라이브 티어 최선의 것을 3번째 슬롯에 배치 (구매 순서 관행)
        - 완성템이 3개 미만이면 데이터 신뢰 부족 → None (패키지 경로 폴백)
        - 이름 역조회는 아레나 변형 아이템(223xxx 등)과 한글명이 겹쳐 오탐할 수
          있어, API가 준 item_id 를 그대로 사용한다.
        """
        cores: list[tuple[int, int, str, int]] = []  # (티어, 골드, 이름, id)
        boot: tuple[int, int, str, int] | None = None  # (티어, 골드, 이름, id)
        for it in live.items:
            meta = self.dd.item_meta(it.item_id) or {}
            gold = meta.get("gold") or {}
            maps = meta.get("maps") or {}
            if maps and maps.get("12") is False:
                continue
            if not gold.get("purchasable", True):
                continue
            name = str(meta.get("name") or "").strip()
            if not name:
                continue
            total = int(gold.get("total") or 0)
            item_tags = set(meta.get("tags") or [])
            if "Boots" in item_tags:
                cand = (it.tier, total, name, it.item_id)
                if boot is None or (cand[0], cand[1]) < (boot[0], boot[1]):
                    boot = cand
                continue
            try:
                depth = int(meta.get("depth") or 0)
            except (TypeError, ValueError):
                depth = 0
            if depth < 2 or total < 2500:
                continue
            if all(name != n for _, _g, n, _i in cores):
                cores.append((it.tier, total, name, it.item_id))
        if len(cores) < 3:
            return None

        cores.sort(key=lambda t: (t[0], t[1]))  # 티어 → 싼 순 (구매 순서 근사)
        picked = cores[:5]
        boot_entry = boot or (99, 0, self._fallback_boot(tags), 0)

        names = [name for _, _g, name, _i in picked]
        ids = [item_id for _, _g, _n, item_id in picked]
        # 신발은 3번째 슬롯 (1·2코어 이후 첫 귀환 즈음에 사는 관행)
        names.insert(min(2, len(names)), boot_entry[2])
        ids.insert(min(2, len(ids)), boot_entry[3])

        # 코어가 5개 미만이면 태그 기반 폴백 코어로 채운다
        if len(names) < 6:
            for name in self._fallback_cores(tags):
                if name not in names:
                    names.append(name)
                    ids.append(self.dd.item_id_for_name(name) or 0)
                if len(names) == 6:
                    break
        return names[:6], ids[:6]

    def _live_augment_top(self, live: Any, picks: list[AugmentPick] | None = None) -> AugmentTierTop:
        """라이브 데이터 → 희귀도별 TOP 3 보드.

        picks 를 이미 계산해 둔 호출부(advise)는 재계산 비용을 피하도록 전달한다.
        """
        if picks is None:
            picks = self._live_augment_picks(live)
        return AugmentTierTop(
            silver=tuple(p for p in picks if p.record.rarity == "silver")[:3],
            gold=tuple(p for p in picks if p.record.rarity == "gold")[:3],
            prismatic=tuple(p for p in picks if p.record.rarity == "prismatic")[:3],
        )

    def _adaptive_late_slots(
        self,
        base_slots: list[str],
        tags: set[str],
        enemy_tags: dict[str, int] | None,
    ) -> tuple[list[str], str]:
        """적 조합에 따라 빌드 후반(4~6슬롯)을 분기한다.

        - enemy_tags 가 없으면 원본 그대로 (note 빈 문자열).
        - 기존 1~3코어는 건드리지 않고 4~6슬롯만 상황템으로 교체한다.
        - 교체는 챔프 성향과 일관되게: 메이지→마관/존야, 원딜→관통/수호,
          탱/전사→체력/방어, 암살→관통.
        반환: (완성 6슬롯, 분기 안내 문장).
        """
        if not enemy_tags:
            return base_slots, ""
        slots = list(base_slots)
        # 4~6 인덱스 존재 확인 (부족하면 빈 문자열로 채움)
        while len(slots) < 6:
            slots.append("")
        note_parts: list[str] = []

        # 적 탱커 2+ → %관통/마관 우선
        if enemy_tags.get("Tank", 0) >= 2:
            if "Mage" in tags:
                slots[3] = "공허의 지팡이"
            else:
                slots[3] = "도미닉 경의 인사"
            note_parts.append(f"적 탱커 {enemy_tags['Tank']}명 → 4코어 관통")
        # 적 힐/서폿 2+ → 치감
        if enemy_tags.get("Support", 0) >= 2 and (
            "Marksman" in tags or "Fighter" in tags or "Assassin" in tags or "Mage" in tags
        ):
            if "Mage" in tags:
                slots[4] = "모렐로노미콘"
            else:
                slots[4] = "필멸자의 운명"
            note_parts.append("적 힐/서폿 2명 → 5코어 치감")
        # 적 마법 3+ → MR
        if enemy_tags.get("Mage", 0) >= 3:
            if "Marksman" in tags or "Assassin" in tags:
                slots[5] = "밴시의 장막"
            else:
                slots[5] = "대자연의 힘"
            note_parts.append(f"적 마법 {enemy_tags['Mage']}명 → 6코어 MR")
        # 적 암살 2+ → 생존
        elif enemy_tags.get("Assassin", 0) >= 2:
            slots[5] = "수호 천사"
            note_parts.append(f"적 암살 {enemy_tags['Assassin']}명 → 6코어 수호천사")

        # 빈 슬롯은 원본 유지 (분기 안 된 슬롯)
        out: list[str] = []
        for i, s in enumerate(slots[:6]):
            out.append(s if s else (base_slots[i] if i < len(base_slots) else "상황 아이템 선택"))
        note = " · ".join(note_parts) if note_parts else ""
        return out, note

    def _fallback_cores(self, tags: set[str]) -> list[str]:
        """Blitz ARAM 빌드가 없을 때 사용하는 결정적 정적 코어 목록."""
        if "Marksman" in tags:
            return [
                "크라켄 학살자",
                "구인수의 격노검",
                "무한의 대검",
                "도미닉 경의 인사",
                "수호 천사",
            ]
        if "Tank" in tags:
            return [
                "태양불꽃 방패",
                "가시 갑옷",
                "대자연의 힘",
                "워모그의 갑옷",
                "강철의 솔라리 펜던트",
            ]
        if "Fighter" in tags and "Mage" not in tags:
            return [
                "삼위일체",
                "스테락의 도전",
                "죽음의 무도",
                "가시 갑옷",
                "수호 천사",
            ]
        if "Assassin" in tags and "Mage" not in tags:
            return [
                "요우무의 유령검",
                "기회",
                "세릴다의 원한",
                "밤의 끝자락",
                "수호 천사",
            ]
        if "Support" in tags and "Mage" not in tags:
            return [
                "월석 재생기",
                "구원",
                "미카엘의 축복",
                "강철의 솔라리 펜던트",
                "대자연의 힘",
            ]
        return [
            "루덴의 메아리",
            "그림자불꽃",
            "라바돈의 죽음모자",
            "공허의 지팡이",
            "존야의 모래시계",
        ]


def ko_tag_list(tags: set[str]) -> str:
    """태그 집합을 한글 라벨로 연결."""
    mapping = {
        "Mage": "메이지",
        "Marksman": "원거리 딜러",
        "Assassin": "암살자",
        "Fighter": "전사",
        "Tank": "탱커",
        "Support": "서포터",
    }
    return "/".join(mapping.get(t, t) for t in sorted(tags))
