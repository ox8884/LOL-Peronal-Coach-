"""ARAM 조합 위협·시너지 요약 (태그 기반, 네트워크 없음).

인게임/수동으로 모은 아군·적 챔프 키로 간단한 조합 코칭 줄을 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.static.ddragon import DataDragon


@dataclass
class CompLine:
    kind: str  # threat | synergy | note
    text: str


@dataclass
class AramCompReport:
    ally_tags: dict[str, int] = field(default_factory=dict)
    enemy_tags: dict[str, int] = field(default_factory=dict)
    lines: list[CompLine] = field(default_factory=list)


def _tags_for(dd: DataDragon, keys: list[str]) -> dict[str, int]:
    dd.ensure_loaded()
    counts: dict[str, int] = {}
    by_id = getattr(dd, "_champions_by_id", {}) or {}
    by_key: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for ch in by_id.values():
        kid = str(ch.get("id", "")).lower().replace(" ", "")
        if kid:
            by_key[kid] = ch
        nm = str(ch.get("name", "")).strip()
        if nm:
            by_name[nm] = ch
            by_name[nm.lower()] = ch
    for k in keys:
        if not k:
            continue
        compact = k.lower().replace(" ", "")
        c = by_key.get(compact) or by_name.get(k) or by_name.get(k.lower())
        if not c:
            continue
        for t in c.get("tags") or []:
            counts[t] = counts.get(t, 0) + 1
    return counts


def analyze_aram_comp(
    dd: DataDragon,
    *,
    allies: list[tuple[str, str]],
    enemies: list[tuple[str, str]],
    my_key: str = "",
) -> AramCompReport:
    """(champ_key, champ_ko) 목록 → 조합 요약."""
    ally_keys = [k for k, _ in allies] + ([my_key] if my_key else [])
    # unique preserve order
    seen: set[str] = set()
    ak: list[str] = []
    for k in ally_keys:
        lk = k.lower()
        if lk in seen:
            continue
        seen.add(lk)
        ak.append(k)
    ek = [k for k, _ in enemies]

    ally_tags = _tags_for(dd, ak)
    enemy_tags = _tags_for(dd, ek)
    lines: list[CompLine] = []

    # 적 위협
    if enemy_tags.get("Assassin", 0) >= 2:
        lines.append(
            CompLine(
                "threat",
                f"적 암살자 {enemy_tags['Assassin']} — 존야·밴시·수호천사 타이밍을 아껴 두세요",
            )
        )
    if enemy_tags.get("Tank", 0) >= 2:
        lines.append(
            CompLine(
                "threat",
                f"적 탱커 {enemy_tags['Tank']} — %체력·관통·공속 절단 아이템이 효율적",
            )
        )
    if enemy_tags.get("Mage", 0) >= 3:
        lines.append(
            CompLine(
                "threat",
                "적 마법 화력 밀집 — MR·헤르메스·밴시 우선을 고려",
            )
        )
    if enemy_tags.get("Marksman", 0) >= 2:
        lines.append(
            CompLine(
                "threat",
                "적 원딜 복수 — 암살·돌진으로 백라인을 노리거나 전면 압박",
            )
        )
    if enemy_tags.get("Support", 0) >= 2:
        lines.append(
            CompLine(
                "threat",
                "적 유틸/힐 서폿 다수 — 처형·치유 감소 아이템 효율↑",
            )
        )

    # 아군 시너지
    if ally_tags.get("Tank", 0) >= 1 and ally_tags.get("Mage", 0) >= 2:
        lines.append(
            CompLine(
                "synergy",
                "아군 탱커+마법 화력 — 전면에서 시간 끌며 포킹/스킬 난사 각",
            )
        )
    if ally_tags.get("Assassin", 0) >= 2:
        lines.append(
            CompLine(
                "synergy",
                "아군 암살 비중 높음 — 한타보다 잘라먹기·측면 진입이 유리",
            )
        )
    if ally_tags.get("Marksman", 0) >= 2:
        lines.append(
            CompLine(
                "synergy",
                "아군 원딜 복수 — 보호막·이니시로 딜러를 살리는 한타 구도",
            )
        )
    if ally_tags.get("Fighter", 0) >= 2 and ally_tags.get("Tank", 0) == 0:
        lines.append(
            CompLine(
                "synergy",
                "아군 전사 위주·탱 부족 — 너무 깊게 들어가지 말고 난전 유도",
            )
        )

    # 균형 노트
    if not lines:
        lines.append(
            CompLine(
                "note",
                "특별한 태그 편중은 없음 — 표준 칼바람: 전면 유지 + 포킹/이니시 균형",
            )
        )

    # 인원 체크
    if len(ek) >= 3:
        lines.append(
            CompLine(
                "note",
                f"적 {len(ek)}명 · 아군 인식 {len(ak)}명 기준 요약 (픽 변동 시 다시 브리핑)",
            )
        )

    return AramCompReport(ally_tags=ally_tags, enemy_tags=enemy_tags, lines=lines)
