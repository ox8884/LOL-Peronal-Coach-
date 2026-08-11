"""Packaged Blitz ARAM Mayhem champion build data and HTML parser."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

_ITEM_ID_RE = re.compile(r"/item/(\d+)\.webp(?:[?#]|$)", re.I)
_CORE_LABELS = ("완성 아이템", "completed items")
_AUGMENT_TIERS = {
    "프리즘 증강": "prismatic",
    "prismatic": "prismatic",
    "골드 증강": "gold",
    "gold": "gold",
    "실버 증강": "silver",
    "silver": "silver",
}


def _champion_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


@dataclass(frozen=True, slots=True)
class BlitzAramItem:
    """One completed item shown in Blitz's ordered ARAM build group."""

    item_id: str
    name_ko: str
    icon_url: str


@dataclass(frozen=True, slots=True)
class BlitzAramBuild:
    """One champion's current Blitz ARAM Mayhem build."""

    champion: str
    patch: str
    source_url: str
    core_items: tuple[BlitzAramItem, ...]
    augment_tiers: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _parse_item(img: Tag) -> BlitzAramItem | None:
    src = str(img.get("src") or "").strip()
    name = str(img.get("alt") or "").strip()
    match = _ITEM_ID_RE.search(src)
    if not match or not name:
        return None
    return BlitzAramItem(item_id=match.group(1), name_ko=name, icon_url=src)


def parse_blitz_aram_page(
    html: str,
    *,
    champion: str,
    patch: str,
    source_url: str,
) -> BlitzAramBuild:
    """Extract ordered completed items from one Blitz ARAM page."""
    soup = BeautifulSoup(html, "lxml")
    core_items: list[BlitzAramItem] = []
    seen_ids: set[str] = set()
    for group in soup.select("div.items-group"):
        group_title = group.get_text(" ", strip=True).lower()
        if not any(label in group_title for label in _CORE_LABELS):
            continue
        for img in group.select("img.item-img"):
            item = _parse_item(img)
            if item is None or item.item_id in seen_ids:
                continue
            seen_ids.add(item.item_id)
            core_items.append(item)
    if not core_items:
        raise ValueError(f"Blitz ARAM core items not found for {champion}")
    augment_tiers: dict[str, tuple[str, ...]] = {}
    for rarity in soup.select("section.augments div.rarity"):
        rarity_title = rarity.select_one(".rarity-name")
        if rarity_title is None:
            continue
        tier = _AUGMENT_TIERS.get(rarity_title.get_text(" ", strip=True).lower())
        if tier is None:
            continue
        names: list[str] = []
        for img in rarity.select("img.augment-img"):
            name = str(img.get("alt") or "").strip()
            if name and name not in names:
                names.append(name)
        if names:
            augment_tiers[tier] = tuple(names)
    return BlitzAramBuild(
        champion=champion,
        patch=patch,
        source_url=source_url,
        core_items=tuple(core_items),
        augment_tiers=augment_tiers,
    )


def _build_from_raw(raw: dict[str, Any]) -> BlitzAramBuild:
    items = tuple(
        BlitzAramItem(
            item_id=str(item["item_id"]),
            name_ko=str(item["name_ko"]),
            icon_url=str(item["icon_url"]),
        )
        for item in raw.get("core_items", [])
    )
    if not items:
        raise ValueError(f"Blitz ARAM record has no core items: {raw.get('champion')!r}")
    return BlitzAramBuild(
        champion=str(raw["champion"]),
        patch=str(raw["patch"]),
        source_url=str(raw["source_url"]),
        core_items=items,
        augment_tiers={
            str(tier): tuple(str(name) for name in names)
            for tier, names in (raw.get("augment_tiers") or {}).items()
            if isinstance(names, list)
        },
    )


@dataclass(frozen=True, slots=True)
class BlitzAramCatalog:
    """Immutable packaged lookup for all champion ARAM Mayhem builds."""

    patch: str
    updated_at: str
    records: tuple[BlitzAramBuild, ...]

    @classmethod
    def from_file(cls, path: Path) -> BlitzAramCatalog:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = tuple(_build_from_raw(record) for record in raw.get("builds", []))
        if not records:
            raise ValueError("Blitz ARAM catalog is empty")
        return cls(
            patch=str(raw.get("patch", "")),
            updated_at=str(raw.get("updated_at", "")),
            records=records,
        )

    @classmethod
    def packaged(cls) -> BlitzAramCatalog:
        path = Path(__file__).resolve().parents[1] / "data" / "blitz_aram_builds.json"
        return cls.from_file(path)

    def get(self, champion: str) -> BlitzAramBuild | None:
        key = _champion_key(champion)
        return next(
            (record for record in self.records if _champion_key(record.champion) == key),
            None,
        )
