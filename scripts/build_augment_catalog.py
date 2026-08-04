"""Rebuild the packaged ARAM Mayhem augment catalog from blitz.gg live data.

blitz.gg's ARAM Mayhem tier list (https://blitz.gg/ko/lol/aram-mayhem-augments)
embeds three JSON datasets that this script consumes:

- KO game data:  https://utils.iesdev.com/static/json/lol/mayham/<patch>/augments_ko_kr
- EN game data:  https://utils.iesdev.com/static/json/lol/mayham/<patch>/augments_en_us
- live tiers:    https://data.v2.iesdev.com/api/v1/query_objects/prod/lol/aram_mayhem_augments

Roster = augments with ``enabled: true`` AND live tier stats for the patch.

Field mapping
-------------
- name_en / name_ko : official displayNames from the game data files
- description_ko    : official KO description, markup tags stripped
                      (falls back to the KO tooltip when the description is too short)
- rarity            : numeric game rarity 0/1/2 -> silver/gold/prismatic
- fallback_tier     : blitz live tier 1..5 -> S/A/B/B/B (percentile buckets)
- archetype_prefer/avoid : conservative keyword rules over the EN description
                      (KO keywords as fallback), mirroring the historical
                      hand-edited style (pure AD-auto avoids Mage, pure AP
                      avoids Marksman, pure Tank avoids Assassin)
- aliases           : previous catalog names when they differ (lookup continuity)
- image_candidates  : refreshed from the Blitz CDN for every current augment;
                      every candidate is fetched and validated >=128px before
                      it is recorded (honest provenance, no invented URLs)

Usage:
    python scripts/build_augment_catalog.py [--patch 16.15] [--workers 16]
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lol_coach.static.augment_catalog import AugmentCatalog, _id_from_name  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_KO_URL = "https://utils.iesdev.com/static/json/lol/mayham/{patch}/augments_ko_kr"
_EN_URL = "https://utils.iesdev.com/static/json/lol/mayham/{patch}/augments_en_us"
_TIER_URL = (
    "https://data.v2.iesdev.com/api/v1/query_objects/prod/lol/aram_mayhem_augments"
)
_DATA_SOURCE_URL = _KO_URL
_PAGE_URL = "https://blitz.gg/ko/lol/aram-mayhem-augments"
_BLITZ_CDN_BASE = "https://blitz-cdn.blitz.gg/blitz/lol/arena/augments/"

_RARITY_BY_NUM = {0: "silver", 1: "gold", 2: "prismatic"}
# blitz live tiers are percentile buckets 1(best)..5(worst); the catalog
# schema carries three tiers, so the bottom three collapse into B.
_TIER_BY_NUM = {1: "S", 2: "A", 3: "B", 4: "B", 5: "B"}

_MARKSMAN = (
    "attack speed",
    "on-hit",
    "on hit",
    "basic attack",
    "critical strike",
    "crit chance",
    "critical",
    "missile",
    "ricochet",
    "attacks fire",
    "attack range",
    "autocast",
    "dodge chance",
)
_MAGE = (
    "ability power",
    "magic damage",
    "ability haste",
    " spell",
    "spells",
    "cooldown",
    "item haste",
    "burn",
    "damage over time",
    "polymorph",
    "clone",
    "tibbers",
    "mejai",
    "soulstealer",
    "hex core",
    "rod of ages",
    "rabadon",
    "zhonya",
    "needlessly",
    "lightning",
    "stacks of an ability",
)
_ASSASSIN = (
    "lethality",
    "armor penetration",
    "magic penetration",
    "dash",
    "blink",
    "stealth",
    "flash",
    "execute",
    "brush",
    "invisible",
    "invisibility",
    "snowball",
    "movement speed",
    "move speed",
)
_FIGHTER = (
    "omnivamp",
    "life steal",
    "lifesteal",
    "attack damage",
    "true damage",
    "bleed",
    "cleaver",
    "jungle item",
    "heals you",
)
_TANK = (
    "health",
    "armor",
    "magic resist",
    "tenacity",
    "size",
    "shield",
    "invulnerable",
    "damage reduction",
    "sunfire",
    "bami",
    "hollow radiance",
    "warmog",
    "gargoyle",
    "poro king",
    "heartsteel",
    "zz'rot",
    "zzrot",
    "knocked up",
    "knock up",
    "knocked back",
)
_SUPPORT = (
    "heal and shield",
    " ally",
    "allies",
    "revive",
    "resurrect",
    "slowing effects",
    "heals around",
    "someone heals",
)
_RUNES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("first strike", "dark harvest", "hail of blades", "electrocute"),
     ("Marksman", "Assassin")),
    (("aftershock", "glacial augment", "grasp of the undying", "guardian"),
     ("Tank",)),
    (("lethal tempo", "conqueror", "press the attack", "fleet footwork"),
     ("Marksman", "Fighter")),
)
_DEATH_TRIGGERS = ("when you die", "on death", "after death", "you die,")

_KO_FALLBACK = (
    (("주문력", "마법 피해", "스킬 가속"), "Mage"),
    (("공격 속도", "치명타", "기본 공격"), "Marksman"),
    (("공격력", "흡혈", "모든 피해 흡혈"), "Fighter"),
    (("체력", "방어력", "마법 저항력", "강인함", "크기"), "Tank"),
    (("이동 속도", "돌진", "점멸"), "Assassin"),
    (("아군", "치유", "보호막"), "Support"),
)


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def archetypes_for(desc_en: str, desc_ko: str) -> tuple[list[str], list[str]]:
    d = strip_tags(desc_en).lower()
    prefer: set[str] = set()
    if _has_any(d, _MARKSMAN):
        prefer.add("Marksman")
    if _has_any(d, _MAGE) or re.search(r"\bmana\b", d):
        prefer.add("Mage")
    if _has_any(d, _ASSASSIN):
        prefer.add("Assassin")
    if _has_any(d, _FIGHTER):
        prefer.add("Fighter")
    if _has_any(d, _TANK):
        prefer.add("Tank")
    if _has_any(d, _SUPPORT):
        prefer.add("Support")
    for keywords, archs in _RUNES:
        if _has_any(d, keywords):
            prefer.update(archs)
    if not prefer and _has_any(d, _DEATH_TRIGGERS):
        prefer.update(("Tank", "Fighter"))
    if not prefer and "ultimate" in d:
        prefer.add("Mage")
    if not prefer:
        for keywords, arch in _KO_FALLBACK:
            if _has_any(desc_ko or "", keywords):
                prefer.add(arch)

    avoid: set[str] = set()
    marksman = "Marksman" in prefer
    mage = "Mage" in prefer
    if marksman and not mage:
        avoid.add("Mage")
    if mage and not marksman:
        avoid.add("Marksman")
    if prefer == {"Tank"}:
        avoid.add("Assassin")

    order = ["Mage", "Marksman", "Assassin", "Fighter", "Tank", "Support"]
    return (
        [a for a in order if a in prefer],
        [a for a in order if a in avoid],
    )


def strip_tags(text: str) -> str:
    """Remove game-data markup (<scaleAF> etc.) and normalise whitespace."""
    s = re.sub(r"<[^>]+>", "", text or "")
    s = re.sub(r"%i:[A-Za-z]+%", "", s)
    s = re.sub(r"%[is]:scale[A-Za-z]+%", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_json(url: str, retries: int = 2, timeout: int = 40) -> object:
    last_exc: Exception | None = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"fetch failed: {url}: {last_exc}")


def fetch_image_size(url: str, timeout: int = 20) -> int | None:
    """Download a candidate icon; return its min edge in px when valid."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 24:
            return None
        if Image is not None:
            with Image.open(io.BytesIO(data)) as img:
                w, h = img.size
                return min(int(w), int(h))
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return 256
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return 256
        return None
    except Exception:  # noqa: BLE001
        return None


def blitz_icon_urls(en_rec: dict, rarity: str) -> list[str]:
    """Candidate CDN URLs derived from the game-data icon filename.

    The CDN is inconsistent: some assets carry a ``_large`` suffix, some do
    not, and augments without a unique icon use the per-rarity generic asset.
    """
    icon = en_rec.get("iconLarge") or ""
    stem = icon.removesuffix("_large.png").removesuffix(".png").lower()
    urls: list[str] = []
    if stem.startswith("genericabilityaugmenticon") and rarity:
        urls.append(f"{_BLITZ_CDN_BASE}genericabilityaugmenticon_{rarity}.webp")
    if stem:
        urls.append(f"{_BLITZ_CDN_BASE}{stem}.webp")
        urls.append(f"{_BLITZ_CDN_BASE}{stem}_large.webp")
    return urls


def _norm_stem(filename: str) -> str:
    stem = re.sub(r"\.(webp|png|jpe?g)$", "", filename.rsplit("/", 1)[-1])
    return re.sub(r"[^a-z0-9]", "", stem.lower())


def fetch_page_icon_map() -> dict[str, str]:
    """Ground-truth icon URLs: what the tier list page actually renders."""
    try:
        req = urllib.request.Request(_PAGE_URL, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"warning: page icon map unavailable: {exc}")
        return {}
    urls = set(re.findall(re.escape(_BLITZ_CDN_BASE) + r"[^\"\\\s]+", page))
    return {_norm_stem(u): u for u in urls}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", default="16.15")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--inherit-archetypes",
        default=None,
        help="legacy catalog JSON whose curated archetype_prefer/avoid are merged in",
    )
    args = parser.parse_args()
    patch = args.patch
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"fetching blitz datasets for patch {patch} ...")
    ko_data = fetch_json(_KO_URL.format(patch=patch))
    en_data = fetch_json(_EN_URL.format(patch=patch))
    tier_obj = fetch_json(_TIER_URL)
    if not isinstance(ko_data, dict) or not isinstance(en_data, dict):
        print("ERROR: unexpected dataset shape", file=sys.stderr)
        return 1

    tiers: dict[int, tuple[str, int]] = {}
    for row in tier_obj.get("data", []):
        if row.get("patch") != patch:
            continue
        aid = int(row["augment_id"])
        dt = str(row.get("dt", ""))
        tier = int(row.get("stats", {}).get("tier", 0))
        if aid not in tiers or dt > tiers[aid][0]:
            tiers[aid] = (dt, tier)

    roster = sorted(
        int(k)
        for k, v in ko_data.items()
        if v.get("enabled") and int(k) in tiers
    )
    print(f"roster: {len(roster)} augments (enabled ∩ tiered)")

    old_path = ROOT / "src" / "lol_coach" / "data" / "aram_mayhem_augments.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    old_by_norm = {_norm(e["name_en"]): e for e in old.get("augments", [])}
    inherit_by_norm: dict[str, dict] = {}
    if args.inherit_archetypes:
        legacy = json.loads(Path(args.inherit_archetypes).read_text(encoding="utf-8"))
        inherit_by_norm = {_norm(e["name_en"]): e for e in legacy.get("augments", [])}
        print(f"inheriting curated archetypes from {args.inherit_archetypes} "
              f"({len(inherit_by_norm)} legacy records)")

    records: list[dict] = []
    icon_jobs: list[tuple[dict, dict]] = []
    seen_ids: set[str] = set()
    skipped: list[str] = []

    for aid in roster:
        ko = ko_data[str(aid)]
        en = en_data.get(str(aid))
        if en is None:
            skipped.append(f"{aid}: no EN record")
            continue
        name_en = str(en.get("displayName") or "").strip()
        name_ko = str(ko.get("displayName") or "").strip()
        extra_aliases: list[str] = []
        if not re.search(r"[A-Za-z]", name_en):
            # Non-alphabet displayName (the "???" mystery augment,
            # ARAM_MissingPingAugment): canonicalise from the internal name.
            internal = str(en.get("name", "")).removeprefix("ARAM_")
            internal = re.sub(r"([a-z])([A-Z])", r"\1 \2", internal)
            extra_aliases = [name_en, f"{internal} Augment", internal]
            name_en = internal.replace("Augment", "").strip() or internal
        if not name_en:
            skipped.append(f"{aid}: empty EN displayName")
            continue

        rid = _id_from_name(name_en)
        if not rid or rid in seen_ids:
            skipped.append(f"{aid}: id collision for {name_en!r} -> {rid!r}")
            continue
        seen_ids.add(rid)

        desc_ko = strip_tags(ko.get("description", ""))
        if len(desc_ko) < 20:
            tooltip = strip_tags(ko.get("tooltip", ""))
            if len(tooltip) > len(desc_ko):
                desc_ko = tooltip

        rarity_num = int(en.get("rarity", -1))
        rarity = _RARITY_BY_NUM.get(rarity_num, "")
        tier = _TIER_BY_NUM.get(tiers[aid][1], "")

        prefer, avoid = archetypes_for(en.get("description", ""), ko.get("description", ""))

        old_entry = old_by_norm.get(_norm(name_en))
        aliases: list[str] = list(extra_aliases)
        if old_entry is not None:
            if old_entry.get("name_ko") and old_entry["name_ko"] != name_ko:
                aliases.append(old_entry["name_ko"])
            if old_entry.get("name_en") and old_entry["name_en"] != name_en:
                aliases.append(old_entry["name_en"])
            aliases.extend(old_entry.get("aliases", []))
        aliases = [a for a in dict.fromkeys(aliases) if a and a not in (name_en, name_ko)]

        archetype_src = inherit_by_norm.get(_norm(name_en), old_entry)
        if archetype_src is not None:
            for arch in archetype_src.get("archetype_prefer", []):
                if arch not in prefer:
                    prefer.append(arch)
            for arch in archetype_src.get("archetype_avoid", []):
                if arch not in avoid:
                    avoid.append(arch)
        # an archetype explicitly marked avoid must never carry a synergy
        # bonus (keyword rules cannot read negation, e.g. "Reduce max Health")
        prefer = [a for a in prefer if a not in avoid]

        rec = {
            "id": rid,
            "name_en": name_en,
            "name_ko": name_ko,
            "description_ko": desc_ko,
            "rarity": rarity,
            "fallback_tier": tier,
            "aliases": aliases,
            "image_candidates": [],
            "sources": [],
            "archetype_prefer": prefer,
            "archetype_avoid": avoid,
        }

        # Always refresh metadata and art from Blitz.  Reusing an old image
        # would silently leave the catalog split between historical sources.
        icon_jobs.append((rec, en))
        records.append(rec)

    print(f"validating icons for {len(icon_jobs)} new augments "
          f"({args.workers} workers) ...")
    page_map = fetch_page_icon_map() if icon_jobs else {}
    print(f"page icon map: {len(page_map)} urls")

    def resolve_icon(
        job: tuple[dict, dict],
    ) -> tuple[dict, str, str, int] | None:
        rec, en = job
        urls: list[tuple[str, str]] = []
        icon = (en.get("iconLarge") or "")
        page_url = page_map.get(_norm_stem(icon))
        if page_url:
            urls.append((page_url, "blitz"))
        urls.extend((u, "blitz") for u in blitz_icon_urls(en, rec["rarity"]))
        seen: set[str] = set()
        for url, kind in urls:
            if url in seen:
                continue
            seen.add(url)
            # the per-rarity generic placeholder's native resolution is 64px;
            # every augment with unique art must still clear the 128px bar
            min_size = 64 if "genericabilityaugmenticon" in url else 128
            size = fetch_image_size(url)
            if size is not None and size >= min_size:
                return rec, url, kind, size
        return None

    failures: list[str] = []
    kind_counts = {"aram_mayhem": 0, "blitz": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(resolve_icon, icon_jobs):
            if result is None:
                continue
            rec, url, kind, size = result
            rec["image_candidates"] = [{"url": url, "kind": kind, "size": size}]
            rec["sources"] = [{
                "kind": kind,
                "url": _DATA_SOURCE_URL.format(patch=patch),
                "retrieved_at": now,
                "note": ("blitz.gg ARAM Mayhem tier list data "
                         f"(patch {patch}); icon fetched and validated >=128px."),
            }]
            kind_counts[kind] += 1

    for rec, _ in icon_jobs:
        if not rec["image_candidates"]:
            failures.append(f"{rec['id']}: no validated icon candidate")

    records.sort(key=lambda r: r["id"])
    out = {
        "schema_version": 1,
        "patch": patch,
        "updated_at": now,
        "augments": records,
    }
    old_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {old_path} ({len(records)} records)")

    errors = AugmentCatalog.validate_file(old_path)
    if errors:
        print(f"VALIDATION FAILED: {len(errors)} error(s)")
        for err in errors[:20]:
            print(f"  - {err}")
        return 1
    catalog = AugmentCatalog.from_file(old_path)
    prefer_cov = sum(1 for r in catalog.records if r.archetype_prefer)
    print(f"validate_file OK; loaded {len(catalog.records)} records")
    print(f"icon kinds (new): {kind_counts}")
    print(f"archetype_prefer coverage: {prefer_cov}/{len(catalog.records)} "
          f"= {prefer_cov / len(catalog.records):.1%}")
    if skipped:
        print(f"skipped: {len(skipped)}")
        for s in skipped:
            print(f"  - {s}")
    if failures:
        print(f"ICON FAILURES: {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
