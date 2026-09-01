"""blitz.gg SR 빌드/카운터 페이지 파싱 → 공용 모델 (네트워크 없음, 순수 함수).

페이지 구조 (2026 기준):
- 빌드: ``div.items-group`` 4종(시작/빌드순서/완성/상황) + ``div.rune-tree`` 2개
  (선택 룬은 ``img.rune-img.active``) + ``div.skill-order`` + 소환사 스펠 CDN id
- 카운터: ``tr > td`` 3컬럼 (Champion / Score(=GD@15) / Games)
"""

from __future__ import annotations

import re
from typing import Any

from lol_coach.blitz.models import (
    BlitzError,
    BuildSection,
    ChampionBuild,
    CounterPick,
    CounterReport,
    RunePage,
    SkillBuild,
)

ROLE_QUERY = {
    "top": "top",
    "jungle": "jungle",
    "jg": "jungle",
    "mid": "mid",
    "middle": "mid",
    "adc": "adc",
    "bottom": "adc",
    "bot": "adc",
    "support": "support",
    "supp": "support",
    "utility": "support",
}

ROLE_KO = {
    "top": "탑",
    "jungle": "정글",
    "mid": "미드",
    "middle": "미드",
    "adc": "원딜",
    "bottom": "원딜",
    "support": "서폿",
}

# 소환사 스펠 id → 영문 이름 (Riot 공식 고정 id)
_SPELL_ID_TO_EN = {
    1: "Cleanse",
    3: "Exhaust",
    4: "Flash",
    6: "Ghost",
    7: "Heal",
    11: "Smite",
    12: "Teleport",
    13: "Clarity",
    14: "Ignite",
    21: "Barrier",
    30: "To the King",
    31: "Poro Toss",
    32: "Mark",
    39: "Snowball",
}

_RUNE_TREE_NAMES = ("Precision", "Domination", "Sorcery", "Resolve", "Inspiration")
_CHAMPION_SLUG_ALIASES = {
    "wukong": "monkeyking",
    "renataglasc": "renata",
    "nunuwillump": "nunu",
}
_SHARD_NAMES = {
    "Adaptive Force",
    "Attack Speed",
    "Ability Haste",
    "Skill Haste",
    "Armor",
    "Magic Resist",
    "Health",
    "Health Scaling",
    "Move Speed",
    "Tenacity and Slow Resist",
}
_BOOT_HINTS = (
    "Boots",
    "Shoes",
    "Treads",
    "Steelcaps",
    "Greaves",
    "Slippers",
    "Mobility",
    "Swiftness",
)


def normalize_role(role: str) -> str:
    """역할 별칭 → 소문자 표준 (mid/adc/...). URL 변환은 호출부에서 대문자화."""
    key = role.strip().lower()
    if key not in ROLE_QUERY:
        raise BlitzError(f"알 수 없는 포지션 '{role}'. 사용: top, jungle, mid, adc, support")
    return ROLE_QUERY[key]


def champion_slug(name: str) -> str:
    """챔피언 이름 → blitz URL slug (소문자 영숫자)."""
    slug = re.sub(r"[^a-z0-9]", "", name.strip().lower().replace("'", ""))
    return _CHAMPION_SLUG_ALIASES.get(slug, slug)


def _stat(txt: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"\s*([\d.]+)%", txt, re.I)
    return float(m.group(1)) if m else None


def _parse_tree(tree: Any) -> tuple[str, list[str], list[str], list[str]]:
    """rune-tree div → (tree_name, keystone+primary picks, secondary picks, shards).

    반환 순서: 트리 이름, 일반 픽(첫 픽 = 키스톤), 세컨더리 픽, 샤드 3종.
    """
    name = ""
    tree_name_values: list[str] = []
    for option in tree.select(
        "div.tree-option.active, "
        "div.tree-option[aria-selected='true'], "
        "[data-state='active'][data-tree]"
    ):
        for attr in ("aria-label", "data-tree", "data-name", "title"):
            value = str(option.get(attr) or "").strip()
            if value:
                tree_name_values.append(value)
        for img in option.select("img[alt], img[title]"):
            for attr in ("alt", "title"):
                value = str(img.get(attr) or "").strip()
                if value:
                    tree_name_values.append(value)
    for value in tree_name_values:
        for known in _RUNE_TREE_NAMES:
            if value.casefold() == known.casefold():
                name = known
                break
        if name:
            break
    regular: list[str] = []
    shards: list[str] = []
    for row in tree.select("div.tree-row"):
        row_names = [
            str(img.get("alt") or "").strip()
            for cont in row.select("div.rune-container")
            for img in [cont.select_one("img.rune-img")]
            if img is not None
        ]
        if not row_names:
            continue
        if any(rn in _SHARD_NAMES for rn in row_names):
            for cont in row.select("div.rune-container"):
                img = cont.select_one("img.rune-img")
                if img is not None and "active" in (img.get("class") or []):
                    shards.append(str(img.get("alt") or "").strip())
            continue
        for cont in row.select("div.rune-container"):
            img = cont.select_one("img.rune-img")
            if img is not None and "active" in (img.get("class") or []):
                regular.append(str(img.get("alt") or "").strip())
    return name, regular, [], shards


_SPELL_SRC_RE = re.compile(r"summoner-spells/(\d+)\.webp", re.I)


def _parse_spells(soup: Any) -> list[str]:
    spells: list[str] = []
    # 문서 전체 <img>(수천 개) 대신 스펠 이미지 스코프만 순회
    for img in soup.select("img[src*='summoner-spells']"):
        m = _SPELL_SRC_RE.search(str(img.get("src") or ""))
        if not m:
            continue
        en = _SPELL_ID_TO_EN.get(int(m.group(1)))
        if en and en not in spells:
            spells.append(en)
    return spells[:2]


def _parse_skills(soup: Any) -> SkillBuild:
    skills = SkillBuild()
    el = soup.select_one("div.skill-order")
    if el is None:
        return skills
    text = el.get_text(" ", strip=True)
    m = re.search(r"\b([QWER])\s+([QWER])\s+([QWER])\b", text)
    if m:
        skills.priority = [m.group(1), m.group(2), m.group(3)]
    pairs = re.findall(r"(\d+)\s+([QWER])", text)
    if pairs:
        skills.order_by_level = [s for _, s in sorted(pairs, key=lambda x: int(x[0]))][:18]
    return skills


_ITEM_GROUP_LABELS = (
    "Starting Items",
    "Build Order",
    "Completed Items",
    "Situational Items",
    "Boots",
)


def _parse_items(soup: Any) -> tuple[BuildSection, BuildSection, BuildSection, list[BuildSection]]:
    """아이템 그룹 → (starting, core, boots, situational)."""
    starting = BuildSection(label="Starting Items")
    core = BuildSection(label="Core Items")
    boots = BuildSection(label="Boots")
    situational: list[BuildSection] = []
    for group in soup.select("div.items-group"):
        head = group.get_text(" ", strip=True)[:40]
        title = ""
        for known in _ITEM_GROUP_LABELS:
            if head.lower().startswith(known.lower()):
                title = known
                break
        if not title:
            continue
        items = [
            str(img.get("alt") or "").strip()
            for img in group.select("img.item-img")
            if str(img.get("alt") or "").strip()
        ]
        if title == "Starting Items":
            starting.items = items
        elif title == "Completed Items":
            core.items = [it for it in items if not any(h in it for h in _BOOT_HINTS)][:5]
            boots.items = [it for it in items if any(h in it for h in _BOOT_HINTS)]
        elif title == "Situational Items":
            situational.append(BuildSection(label="Situational Items", items=items))
        elif title == "Boots" and not boots.items:
            boots.items = items
    return starting, core, boots, situational


def parse_build_html(
    html: str,
    *,
    champion: str,
    role: str,
    source_url: str,
) -> ChampionBuild:
    """blitz.gg 빌드 페이지 → ChampionBuild (룬·스펠·스킬·아이템·통계)."""
    from bs4 import BeautifulSoup  # 파서 체인은 첫 파싱 때만 로드

    soup = BeautifulSoup(html, "lxml")
    txt = soup.get_text(" ", strip=True)

    win_rate = _stat(txt, "Win rate")
    pick_rate = _stat(txt, "Pick rate")
    ban_rate = _stat(txt, "Ban rate")
    matches: int | None = None
    m = re.search(r"Matches\s*([\d,]+)", txt, re.I)
    if m:
        matches = int(m.group(1).replace(",", ""))
    patch = ""
    m = re.search(r"Patch\s*:?\s*(\d+\.\d+)", txt, re.I)
    if m:
        patch = m.group(1)

    runes = RunePage()
    trees = soup.select("div.rune-tree")
    if trees:
        name, picks, _sec, shards = _parse_tree(trees[0])
        runes.primary_tree = name
        if picks:
            runes.keystone = picks[0]
            runes.primary_runes = picks[1:4]
        runes.shards = shards
        if len(trees) > 1:
            name2, picks2, _sec2, shards2 = _parse_tree(trees[1])
            runes.secondary_tree = name2
            runes.secondary_runes = picks2[:2]
            if not runes.shards and shards2:
                runes.shards = shards2

    starting, core, boots, situational = _parse_items(soup)

    if not core.items and not runes.keystone:
        raise BlitzError(
            f"blitz.gg에서 {champion} 빌드 데이터를 찾지 못했습니다. "
            "챔피언 이름/포지션을 확인하세요."
        )

    return ChampionBuild(
        champion=champion,
        role=role,
        patch=patch,
        win_rate=win_rate,
        pick_rate=pick_rate,
        ban_rate=ban_rate,
        matches=matches,
        source_url=source_url,
        runes=runes,
        skills=_parse_skills(soup),
        summoner_spells=_parse_spells(soup),
        starting_items=starting,
        core_items=core,
        boots=boots,
        situational=situational,
    )


def parse_counters_html(
    html: str,
    *,
    enemy: str,
    role: str,
    source_url: str,
    min_matches: int = 800,
) -> CounterReport:
    """blitz.gg 카운터 표 → CounterReport (Score = GD@15, Games = 매치 수)."""
    from bs4 import BeautifulSoup  # 파서 체인은 첫 파싱 때만 로드

    soup = BeautifulSoup(html, "lxml")
    txt = soup.get_text(" ", strip=True)
    patch_match = re.search(r"\bPatch\s*:?\s*(\d+\.\d+)", txt, re.I)
    picks: list[CounterPick] = []
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        name = tds[0].get_text(" ", strip=True)
        try:
            score = int(tds[1].get_text(" ", strip=True).replace(",", ""))
            games = int(tds[2].get_text(" ", strip=True).replace(",", ""))
        except ValueError:
            continue
        if not name or score == 0 or games < min_matches:
            continue
        picks.append(CounterPick(champion=name, gd15=score, matches=games))
    if not picks:
        raise BlitzError(
            f"blitz.gg에서 {enemy} 카운터 데이터를 찾지 못했습니다. "
            "챔피언 이름/포지션을 확인하세요."
        )
    good = sorted([p for p in picks if p.gd15 > 0], key=lambda c: (-c.gd15, -c.matches))
    hard = sorted([p for p in picks if p.gd15 < 0], key=lambda c: (c.gd15, -c.matches))
    return CounterReport(
        enemy=enemy,
        role=role,
        patch=patch_match.group(1) if patch_match else "",
        source_url=source_url,
        lane_counters=good,
        hard_matchups=hard,
    )
