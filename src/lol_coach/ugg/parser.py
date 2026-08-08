"""Parse u.gg champion build HTML into structured meta data."""

from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, Tag

from lol_coach.ugg.models import (
    BuildSection,
    ChampionBuild,
    RunePage,
    SkillBuild,
)

_WR_RE = re.compile(
    r"(?P<label>Win Rate|Pick Rate|Ban Rate)\s*(?P<val>\d+(?:\.\d+)?)\s*%",
    re.I,
)
_MATCHES_RE = re.compile(r"([\d,]+)\s*Matches", re.I)
_PCT_MATCHES_RE = re.compile(
    r"(?P<wr>\d+(?:\.\d+)?)\s*%\s*WR\s*(?:\(|)?\s*(?P<m>[\d,]+)\s*Matches",
    re.I,
)
_TIER_RE = re.compile(r"\bTier\s+([SABCD][+\-]?)\b", re.I)
_PATCH_RE = re.compile(r"Patch\s*(\d+\.\d+)", re.I)
_RANK_RE = re.compile(r"(Emerald\s*\+|Diamond\s*\+|Platinum\s*\+|Master\s*\+|Overall|All Ranks)", re.I)


def _clean_rune_name(alt: str) -> str:
    alt = alt.strip()
    for prefix in (
        "The Keystone ",
        "The Rune Tree ",
        "The Rune ",
        "The ",
        "Shard ",
    ):
        if alt.startswith(prefix):
            alt = alt[len(prefix) :]
    if alt.endswith(" Shard"):
        alt = alt[: -len(" Shard")]
    return alt.strip()


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if t:
                return t
    return ""


def _parse_section_stats(text: str) -> tuple[float | None, int | None]:
    m = _PCT_MATCHES_RE.search(text)
    if m:
        return float(m.group("wr")), int(m.group("m").replace(",", ""))
    wr_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*WR", text, re.I)
    match_m = _MATCHES_RE.search(text)
    return (
        float(wr_m.group(1)) if wr_m else None,
        int(match_m.group(1).replace(",", "")) if match_m else None,
    )


def _imgs_alts(node: Tag | None) -> list[str]:
    if not node:
        return []
    out: list[str] = []
    for img in node.find_all("img"):
        alt = str(img.get("alt") or "").strip()
        if alt:
            out.append(alt)
    return out


def _active_rune_alts(soup: BeautifulSoup) -> list[str]:
    """Collect alts for perks marked perk-active / shard-active (deduped order)."""
    seen: set[str] = set()
    ordered: list[str] = []
    # Prefer the first recommended-build_runes block only
    root = soup.select_one(".recommended-build_runes") or soup
    for sel in (".perk-active img", ".shard-active img", "div.perk-active img"):
        for img in root.select(sel):
            alt = str(img.get("alt") or "").strip()
            if not alt:
                continue
            name = _clean_rune_name(alt)
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    # Also trees from headers
    trees = []
    for img in root.select(".rune-tree_header img, .rune-image-container img"):
        alt = str(img.get("alt") or "").strip()
        if "Tree" in alt or "Rune Tree" in alt:
            trees.append(_clean_rune_name(alt))
    return trees[:2] + ordered


def _parse_runes(soup: BeautifulSoup) -> RunePage:
    page = RunePage()
    block = soup.select_one(".recommended-build_runes")
    text = block.get_text(" ", strip=True) if block else ""
    wr, matches = _parse_section_stats(text)
    page.win_rate = wr
    page.matches = matches

    names = _active_rune_alts(soup)
    # First two tree names often appear from headers
    tree_like = []
    rune_like = []
    shard_like = []
    keystone = ""

    # Re-scan with class context for better classification
    root = block or soup
    for img in root.select("img"):
        alt = str(img.get("alt") or "").strip()
        if not alt:
            continue
        parent = img.parent
        classes = " ".join(parent.get("class") or []) if parent else ""
        name = _clean_rune_name(alt)
        if "Tree" in alt:
            if name not in tree_like:
                tree_like.append(name)
            continue
        if "shard" in classes:
            if "shard-active" in classes and name not in shard_like:
                shard_like.append(name)
            continue
        if "perk-active" in classes:
            if "keystone" in classes and not keystone:
                keystone = name
            elif name not in rune_like and name != keystone:
                rune_like.append(name)

    if not tree_like and names:
        # fallback from names list
        pass

    page.primary_tree = tree_like[0] if tree_like else ""
    page.secondary_tree = tree_like[1] if len(tree_like) > 1 else ""
    page.keystone = keystone
    # primary runes = first 3 non-keystone actives, secondary = rest
    if keystone and keystone in rune_like:
        rune_like = [r for r in rune_like if r != keystone]
    page.primary_runes = rune_like[:3]
    page.secondary_runes = rune_like[3:5]
    page.shards = shard_like[:3]
    return page


def _parse_skills(soup: BeautifulSoup) -> SkillBuild:
    skills = SkillBuild()
    prio = soup.select_one(".skill-priority")
    if prio:
        text = prio.get_text(" ", strip=True)
        wr, matches = _parse_section_stats(text)
        skills.win_rate = wr
        skills.matches = matches
        # "Skill Priority Q W E"
        m = re.search(r"Skill Priority\s+([QWER])\s+([QWER])\s+([QWER])", text, re.I)
        if m:
            skills.priority = [m.group(1).upper(), m.group(2).upper(), m.group(3).upper()]
        else:
            letters = re.findall(r"\b([QWE])\b", text)
            # first three unique order of appearance for priority
            seen = []
            for L in letters:
                if L not in seen:
                    seen.append(L)
            skills.priority = seen[:3]

    # Skill path: rows Q/W/E/R with level numbers
    path_block = soup.select_one(".skill-path-container") or soup.select_one(
        ".skill-order"
    )
    order: dict[int, str] = {}
    if path_block:
        for row in path_block.select(".skill-order-row, .skill-path-block, tr"):
            row_text = row.get_text(" ", strip=True)
            letter_m = re.match(r"^([QWERP])\b", row_text)
            if not letter_m:
                # try skill-row-label
                label = row.select_one(".skill-row-label, .skill-label, .skill-name")
                if label:
                    lt = label.get_text(" ", strip=True)
                    letter_m = re.search(r"\b([QWER])\b", lt)
            if not letter_m:
                continue
            letter = letter_m.group(1).upper()
            if letter == "P":
                continue
            levels = [int(x) for x in re.findall(r"\b(\d{1,2})\b", row_text)]
            for lv in levels:
                if 1 <= lv <= 18:
                    order[lv] = letter

    if order:
        skills.order_by_level = [order.get(i, "?") for i in range(1, 19)]
    return skills


def _looks_like_item_img(img: Tag) -> bool:
    src = (str(img.get("src") or "")) + " " + (str(img.get("data-src") or ""))
    if re.search(r"/item/\d+\.(?:png|webp)", src, re.I):
        return True
    # some builds use bigbrain CDN item paths without numeric id in alt-only mode
    return "/item/" in src.lower()


def _item_names_from_node(node: Tag | None, *, require_item_src: bool = False) -> list[str]:
    """Extract item names from img alts and visible text cues."""
    if not node:
        return []
    names: list[str] = []
    for img in node.find_all("img"):
        alt = str(img.get("alt") or "").strip()
        if not alt:
            continue
        if require_item_src and not _looks_like_item_img(img):
            continue
        # skip non-items
        low = alt.lower()
        if any(
            k in low
            for k in (
                "rune",
                "keystone",
                "shard",
                "tree",
                "summoner",
                "spell",
                "passive",
                "emerald",
                "diamond",
                "rank",
                "probuild",
            )
        ):
            continue
        # champion skill alts look like "Ahri's Q: ..."
        if re.search(r"'s [QWERP]:", alt):
            continue
        # bare champion portrait alts (no item path) — skip unless src is item
        if not _looks_like_item_img(img) and " " not in alt and alt[:1].isupper():
            # likely a champion name like "Veigar"
            continue
        # UI blurb text sometimes ends up as fake "item" alts
        if any(
            junk in low
            for junk in (
                "build this",
                "every game",
                "best for",
                "options after",
            )
        ):
            continue
        if alt not in names:
            names.append(alt)
    return names


def _parse_items(soup: BeautifulSoup) -> tuple[BuildSection, BuildSection, BuildSection, list[BuildSection]]:
    starting = BuildSection(label="Starting Items")
    core = BuildSection(label="Core Items")
    boots = BuildSection(label="Boots")
    situational: list[BuildSection] = []

    start_node = soup.select_one(".starting-items")
    if start_node:
        text = start_node.get_text(" ", strip=True)
        wr, matches = _parse_section_stats(text)
        starting.win_rate = wr
        starting.matches = matches
        starting.items = _item_names_from_node(start_node)
        # U.GG sometimes only renders empty item-img placeholders server-side.
        # Capture trailing note text if present.
        if "Best for most matchups" in text:
            starting.note = "Best for most matchups"

    core_node = soup.select_one(".core-items")
    if core_node:
        text = core_node.get_text(" ", strip=True)
        wr, matches = _parse_section_stats(text)
        core.win_rate = wr
        core.matches = matches
        core.items = _item_names_from_node(core_node)
        # Boots name often appears as plain text in core section
        # e.g. "Crimson Lucidity Quest Reward"
        leftover = re.sub(
            r"Core Items|\d+(?:\.\d+)?%\s*WR|[\d,]+\s*Matches|"
            r"Build this every game|Best for most matchups",
            "",
            text,
            flags=re.I,
        ).strip()
        if leftover and not core.items:
            parts = [p.strip() for p in re.split(r"\s{2,}|\|", leftover) if p.strip()]
            for p in parts:
                if not p or p in core.items:
                    continue
                if any(
                    junk in p.lower()
                    for junk in ("build this", "every game", "options after")
                ):
                    continue
                if any(
                    b in p.lower()
                    for b in (
                        "lucidity",
                        "greaves",
                        "boots",
                        "treads",
                        "mercurial",
                        "ionian",
                        "berserker",
                        "sorcerer",
                        "plated",
                        "shoes",
                    )
                ):
                    boots.items.append(p)
                else:
                    core.items.append(p)

    # Situational 4th/5th/6th
    for cls, label in (
        ("item-options-1", "4th Item Options"),
        ("item-options-2", "5th Item Options"),
        ("item-options-3", "6th Item Options"),
    ):
        node = soup.select_one(f".{cls}")
        if not node:
            continue
        text = node.get_text(" ", strip=True)
        section = BuildSection(label=label, items=_item_names_from_node(node))
        wr, matches = _parse_section_stats(text)
        section.win_rate = wr
        section.matches = matches
        # multiple WR lines → keep first as headline
        situational.append(section)

    # Fallback: only imgs that are clearly item assets (avoid matchup champs)
    if not core.items:
        rec = soup.select_one(".champion-recommended-build") or soup
        for name in _item_names_from_node(rec, require_item_src=True):
            if name not in core.items:
                core.items.append(name)
            if len(core.items) >= 3:
                break

    if boots.items:
        boots.note = "From core build path"
    return starting, core, boots, situational


def _parse_summoners(soup: BeautifulSoup) -> tuple[list[str], float | None]:
    spells: list[str] = []
    wr = None

    # Prefer direct alt tags (most reliable on u.gg SSR)
    for img in soup.find_all("img"):
        alt = str(img.get("alt") or "").strip()
        if alt.lower().startswith("summoner spell"):
            name = alt.replace("Summoner Spell", "").strip()
            if name and name not in spells:
                spells.append(name)
        elif re.search(r"/spell/Summoner", str(img.get("src") or ""), re.I):
            name = alt or (str(img.get("src") or "")).rsplit("/", 1)[-1]
            name = re.sub(r"Summoner|\.webp|\.png", "", name, flags=re.I).strip()
            if name and name not in spells:
                spells.append(name)

    # WR near the label
    for el in soup.find_all(string=re.compile(r"^\s*Summoner Spells\s*$", re.I)):
        parent = el.find_parent()
        block = parent
        for _ in range(4):
            if block is None:
                break
            text = block.get_text(" ", strip=True)
            if "WR" in text:
                wr, _ = _parse_section_stats(text)
                break
            block = block.find_parent()
        if wr is not None:
            break

    return spells[:2], wr


def parse_champion_build_html(
    html: str,
    *,
    champion: str,
    role: str,
    source_url: str = "",
) -> ChampionBuild:
    """Parse a u.gg champion build page HTML document."""
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text(" ", strip=True)

    patch = ""
    m = _PATCH_RE.search(full_text)
    if m:
        patch = m.group(1)
    # title fallback
    title = soup.title.get_text() if soup.title else ""
    if not patch:
        m = _PATCH_RE.search(title)
        if m:
            patch = m.group(1)

    tier = ""
    tm = _TIER_RE.search(full_text)
    if tm:
        tier = tm.group(1).upper()

    rates: dict[str, float] = {}
    # Prefer the champion overview block.
    # SR:  "Tier S Win Rate 50.89% ... Pick ... Ban ... Matches"
    # ARAM: "Tier S Win Rate 52.44% Rank 34/173 Pick Rate 9.9% Matches 40,543" (often no ban)
    overview = re.search(
        r"Tier\s+[SABCD][+\-]?\s+"
        r"Win Rate\s*(?P<wr>\d+(?:\.\d+)?)\s*%\s*"
        r"(?:Rank\s+\d+\s*/\s*\d+\s*)?"
        r"Pick Rate\s*(?P<pr>\d+(?:\.\d+)?)\s*%\s*"
        r"(?:Ban Rate\s*(?P<br>\d+(?:\.\d+)?)\s*%\s*)?"
        r"Matches\s*(?P<m>[\d,]+)",
        full_text[:4000],
        re.I,
    )
    if overview:
        rates["win rate"] = float(overview.group("wr"))
        rates["pick rate"] = float(overview.group("pr"))
        if overview.group("br") is not None:
            rates["ban rate"] = float(overview.group("br"))
        matches = int(overview.group("m").replace(",", ""))
    else:
        # first occurrence of each label only (avoid PLUS personal stats later)
        for label in ("win rate", "pick rate", "ban rate"):
            m_rate = re.search(
                rf"{label}\s*(\d+(?:\.\d+)?)\s*%", full_text[:3000], re.I
            )
            if m_rate:
                rates[label] = float(m_rate.group(1))
        matches = None
        head = full_text[:2500]
        mm = re.search(r"Matches\s*([\d,]+)", head, re.I)
        if not mm:
            mm = _MATCHES_RE.search(head)
        if mm:
            matches = int(mm.group(1).replace(",", ""))

    rank_filter = "Emerald+"
    rm = _RANK_RE.search(full_text[:2000])
    if rm:
        rank_filter = re.sub(r"\s+", " ", rm.group(1)).strip()

    runes = _parse_runes(soup)
    skills = _parse_skills(soup)
    starting, core, boots, situational = _parse_items(soup)
    spells, spells_wr = _parse_summoners(soup)

    # Header summary item (e.g. Blackfire Torch) — only real item CDN paths
    if len(core.items) < 1:
        for img in soup.select("img"):
            alt = str(img.get("alt") or "").strip()
            if alt and _looks_like_item_img(img) and alt not in core.items:
                core.items.append(alt)
            if len(core.items) >= 3:
                break

    build = ChampionBuild(
        champion=champion,
        role=role,
        patch=patch or "unknown",
        tier=tier,
        win_rate=rates.get("win rate"),
        pick_rate=rates.get("pick rate"),
        ban_rate=rates.get("ban rate"),
        matches=matches,
        rank_filter=rank_filter,
        source_url=source_url,
        runes=runes,
        skills=skills,
        summoner_spells=spells,
        summoner_spells_wr=spells_wr,
        starting_items=starting,
        core_items=core,
        boots=boots,
        situational=situational,
    )
    return build
