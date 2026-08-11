"""ARAM 아수라장 — 증강 추천 · 회피 · ARAM 아이템 빌드 (룬 없음).

이 모듈은 수동으로 제시된 증강 이름/기록만을 대상으로 합니다.
추천은 Blitz 카탈로그의 공식 한글 사실(등급, 희귀도, 챔프 성향 시너지/주의)과
Data Dragon 스킬 정보를 조합해 생성되며, 제시되지 않은 증강은 절대
추천하지 않습니다. ARAM 코어 아이템은 Blitz 패키지 데이터를 우선 사용하고,
데이터가 없을 때 일반 폴백으로 보완하며 출처를 명확히 표기합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lol_coach.blitz.models import BlitzError, BuildSection, ChampionBuild
from lol_coach.static.augment_catalog import AugmentCatalog, AugmentRecord
from lol_coach.static.blitz_aram import BlitzAramBuild, BlitzAramCatalog
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer

# 수동 티어 폴백 — 카탈로그에 기록이 없는 증강만 보완용으로 사용.
# 신규 API는 packaged catalog를 1차 근거로 삼습니다.
# 데이터 소스: lol_coach/data/aram_mayhem_fallback_tiers.json (단일 소스)
_FALLBACK_TIERS_RESOURCE = "aram_mayhem_fallback_tiers.json"


def _load_fallback_tiers() -> dict[str, dict[str, list[str]]]:
    """패키지 데이터에서 폴팩 티어 표 로드."""
    import importlib.resources
    import json

    from lol_coach.log import get_logger

    try:
        ref = importlib.resources.files("lol_coach.data").joinpath(
            _FALLBACK_TIERS_RESOURCE
        )
        with ref.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:  # pragma: no cover
        get_logger("aram_mayhem").warning("폴팩 티어 로드 실패: %s", exc)
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for rarity, buckets in raw.items():
        if not isinstance(buckets, dict):
            continue
        out[rarity] = {
            tier: [str(n) for n in names]
            for tier, names in buckets.items()
            if isinstance(names, list)
        }
    return out


_FALLBACK_TIERS: dict[str, dict[str, list[str]]] = _load_fallback_tiers()

# 카탈로그에 rarity/fallback_tier가 없는 레코드를 위해 _FALLBACK_TIERS에서 찾아 보강.
_RARITY_BY_NAME: dict[str, str] = {}
_TIER_BY_NAME: dict[str, str] = {}
for _rarity, _buckets in _FALLBACK_TIERS.items():
    for _tier, _names in _buckets.items():
        for _name in _names:
            _RARITY_BY_NAME.setdefault(_name, _rarity)
            _TIER_BY_NAME.setdefault(_name, _tier)

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
        return self.record.rarity or _RARITY_BY_NAME.get(self.record.name_en, "")

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


@dataclass
class MayhemAdvice:
    champ_ko: str
    patch: str
    champ_key: str = ""  # Data Dragon id (Ahri) — 아이콘용
    top_augments: list[AugmentPick] = field(default_factory=list)
    avoid_augments: list[AugmentPick] = field(default_factory=list)
    build: ChampionBuild | None = None
    core_slots: list[str] = field(default_factory=list)
    spells_line: str = ""
    skill_line: str = ""
    play_tips: list[str] = field(default_factory=list)
    source_url: str = ""
    build_url: str = ""
    augment_validation: AugmentValidation = field(
        default_factory=lambda: AugmentValidation([], [], [])
    )
    source: SourceInfo | None = None


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
    ):
        self.dd = ddragon or DataDragon(language="ko_KR")
        self.loc = get_localizer()
        self.catalog = catalog or AugmentCatalog()
        if blitz is not None:
            self.blitz: BlitzAramCatalog | None = blitz
        else:
            try:
                self.blitz = BlitzAramCatalog.packaged()
            except (FileNotFoundError, OSError, ValueError):
                self.blitz = None

    def _record_tier(self, rec: AugmentRecord) -> str:
        if rec.fallback_tier:
            return rec.fallback_tier
        return _TIER_BY_NAME.get(rec.name_en, "")

    def _record_rarity(self, rec: AugmentRecord) -> str:
        if rec.rarity:
            return rec.rarity
        return _RARITY_BY_NAME.get(rec.name_en, "")

    def _load_tiers(self) -> dict[str, dict[str, list[str]]]:
        """Packaged catalog를 1차 티어 테이블로 사용합니다."""
        buckets: dict[str, dict[str, list[str]]] = {
            "prismatic": {},
            "gold": {},
            "silver": {},
            "": {},
        }
        for rec in self.catalog.records:
            rarity = self._record_rarity(rec)
            tier = self._record_tier(rec)
            if not tier:
                continue
            buckets.setdefault(rarity, {}).setdefault(tier, []).append(rec.name_en)
        # catalog에 정보가 없는 증강만 레거시 폴백으로 보강
        for rarity, rb in _FALLBACK_TIERS.items():
            for tier, names in rb.items():
                bucket = buckets.setdefault(rarity, {})
                existing = set(sum(bucket.values(), []))
                bucket.setdefault(tier, []).extend(
                    n for n in names if n not in existing
                )
        return buckets

    def resolve_offered(
        self,
        offered: list[str],
        *,
        strict: bool = False,
    ) -> AugmentValidation:
        """사용자가 수동 제시한 증강 이름을 카탈로그로 정규화·중복 제거."""
        records, unknowns, duplicates = self.catalog.resolve_many(
            offered, strict=strict
        )
        return AugmentValidation(
            valid=list(records), unknowns=unknowns, duplicates=duplicates
        )

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
                lines.append(
                    f"궁극기 {name} 쿨타임 {cd} — 증강 쿨감/지속 효과와 연계하세요."
                )
            elif slot in ("Q", "W", "E"):
                # 투사처이나 돌진기를 우선
                lowered = (desc or "").lower()
                if any(k in lowered for k in ("미사일", "발사", "돌진", "구체", "파도")):
                    lines.append(f"{name}({slot}) 활용 빈도를 높이는 증강이 유리합니다.")
                elif cd:
                    lines.append(f"{name}({slot}) 쿨타임 {cd} — 쿨감/연계 증강을 고려하세요.")
        return lines

    def _skill_priority_line(self, build: ChampionBuild | None) -> str:
        if build and build.skills.priority:
            return " › ".join(build.skills.priority)
        return ""

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

        # 1) Data Dragon 기반 구체적 스킬/운영 참고 2개 이상
        ability_tips = self._ability_lines(key, tags)
        tips.extend(ability_tips[:2])

        # 2) 제시된 증강 중 추천 시너지/주의 1개 이상
        if top:
            pick = top[0]
            tips.append(
                f"추천 증강: {pick.name_ko} — {pick.reason}"
            )
        if avoid:
            bad = avoid[0]
            tips.append(f"주의: {bad.name_ko} — {bad.reason}")

        if has_offered_augments:
            tips.append(
                f"{ko}: 제시된 증강 안에서 S/A 등급·챔프 성향 시너지를 우선으로 고르세요."
            )
        else:
            tips.append(
                f"{ko}: 아래 추천은 전체 카탈로그 기준입니다. 실제 선택지가 보이면 입력해 비교하세요."
            )
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

        # 4) 항상 포함하는 기본 지침
        tips.append(
            "아수라장은 리롤보다 '지금 제시된 것 중 가장 세지는 것'을 고르는 게 우선입니다."
        )

        # 3~5개로 제한
        return tips[:5]

    def _blitz_augment_picks(self, build: BlitzAramBuild) -> list[AugmentPick]:
        """Return Blitz's champion-specific tier order without rescoring it."""
        tier_labels = (
            ("prismatic", "S", "프리즘"),
            ("gold", "A", "골드"),
            ("silver", "B", "실버"),
        )
        picks: list[AugmentPick] = []
        for tier_key, chip_tier, tier_label in tier_labels:
            for index, name_ko in enumerate(build.augment_tiers.get(tier_key, ())):
                record = self.catalog.get_by_name(name_ko)
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
                        score=float(100 - index),
                        reason=f"Blitz.gg {tier_label} 증강 {index + 1}순위",
                    )
                )
        return picks

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
    ) -> MayhemAdvice:
        """챔피언과 수동 제시된 증강 목록을 받아 ARAM Mayhem 코칭을 반환합니다.

        Args:
            champion: 챔피언 이름/키 (한글·영문 모두 가능).
            offered_augments: 사용자가 제시한 증강 이름 리스트. 비어 있으면
                증강 추천 없이 빌드/팁만 제공합니다.
        """
        self.dd.ensure_loaded()
        self.loc.ensure_loaded()

        c = self.dd.resolve_champion(champion)
        if not c:
            raise BlitzError(f"챔피언을 찾을 수 없습니다: {champion}")
        key, ko = c["id"], c["name"]
        tags = set(c.get("tags") or [])

        validation = self.resolve_offered(offered_augments or [])
        blitz_build: BlitzAramBuild | None = (
            self.blitz.get(key) if self.blitz is not None else None
        )
        if blitz_build is not None and blitz_build.augment_tiers:
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
                ranked = [
                    pick
                    for pick in blitz_picks
                    if _norm_aug(pick.name_ko) in offered_names
                ]
                top_ids = {pick.record.id for pick in ranked}
                avoid = self._avoid_offered(validation.valid, tags, top_ids)
            else:
                ranked = blitz_picks
                avoid = []
        else:
            candidates = validation.valid or list(self.catalog.records)
            ranked = self._rank_offered(candidates, tags)
            top_ids = {p.record.id for p in ranked[:5]}
            avoid = self._avoid_offered(candidates, tags, top_ids)

        build_failure = ""
        if blitz_build is not None:
            core_slots = [item.name_ko for item in blitz_build.core_items[:5]]
            spells_line = ""
            skill_line = ""
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
            # Blitz 카탈로그 누락 — 클래식 폴백 (빌드/스펠/스킬 라인 없음)
            build_failure = "Blitz 카탈로그에 이 챔피언 빌드가 없습니다"
            core_slots, spells_line, skill_line, build_url = (
                self._fallback_cores(tags),
                "",
                "",
                "",
            )
            build = ChampionBuild(
                champion=ko,
                role="aram",
                patch="",
                mode="aram",
                core_items=BuildSection(label="Core Items", items=core_slots),
            )

        patch = (
            blitz_build.patch if blitz_build is not None else self.catalog.patch or ""
        )
        tips = self._make_tips(ko, key, tags, ranked, avoid, has_offered_augments=bool(validation.valid))
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
            secondary=(
                "정적 클래식 폴백 (실시간 빌드 없음)"
                if blitz_build is None
                else ""
            ),
            secondary_url="",
            patch=patch,
            updated_at=self.catalog.updated_at,
        )

        advice = MayhemAdvice(
            champ_ko=ko,
            patch=patch,
            champ_key=key,
            top_augments=ranked[:5],
            avoid_augments=avoid,
            build=build,
            core_slots=core_slots,
            spells_line=spells_line,
            skill_line=skill_line,
            play_tips=tips,
            source_url=self.BLITZ_PAGE,
            build_url=build_url,
            augment_validation=validation,
            source=source,
        )
        return advice

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
