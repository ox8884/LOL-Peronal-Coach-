"""Immutable, packaged ARAM Mayhem augment catalog with provenance.

The catalog is loaded from ``lol_coach.data.aram_mayhem_augments.json``,
a resource bundled with the application.  All runtime callers resolve augment
names through :class:`AugmentCatalog` rather than hard-coding strings.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RESOURCE_NAME = "aram_mayhem_augments.json"
_PACKAGE = "lol_coach.data"

# Riot-first / Wiki-fallback / community source kinds allowed in the JSON schema.
_SOURCE_KINDS = frozenset(
    {"riot_data", "riot_patch_notes", "ugg", "league_wiki", "aram_mayhem", "blitz"}
)
_RARITIES = frozenset({"", "prismatic", "gold", "silver"})
_TIERS = frozenset({"", "S", "A", "B"})


def _norm_name(name: str) -> str:
    """Canonical name normalisation used for aliases and runtime lookup.

    Mirrors the historical ``_norm_aug`` helper from ``aram_mayhem.py`` so that
    every legacy string continues to resolve.
    """
    s = (name or "").strip()
    for src, dst in (
        ("\u2019", "'"),
        ("\u2018", "'"),
        ("\u2032", "'"),
        ("`", "'"),
        ("\u00a0", " "),
    ):
        s = s.replace(src, dst)
    return re.sub(r"\s+", " ", s).strip()


def _id_from_name(name: str) -> str:
    """Deterministic record id from an English augment name."""
    s = name.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if s.endswith("_s"):
        s = s[:-2]
    return s


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    """A verified image source for a single augment.

    ``url`` is the exact location known to serve the original asset.
    ``kind`` must be one of the provenance kinds allowed by the schema.
    ``size`` is the verified native width/height in pixels (>=128).
    """

    url: str
    kind: str
    size: int


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Evidence / provenance entry for a catalog record."""

    kind: str
    url: str
    retrieved_at: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class AugmentRecord:
    """Strict, immutable augment record."""

    id: str
    name_en: str
    name_ko: str
    description_ko: str
    rarity: str
    fallback_tier: str
    aliases: tuple[str, ...]
    image_candidates: tuple[ImageCandidate, ...]
    sources: tuple[SourceRecord, ...]
    archetype_prefer: tuple[str, ...]
    archetype_avoid: tuple[str, ...]

    @property
    def canonical_name(self) -> str:
        return self.name_en


class CatalogError(ValueError):
    """Raised when the packaged catalog fails validation."""


class AugmentCatalog:
    """In-memory ARAM Mayhem augment catalog loaded from package resources.

    The catalog is immutable after construction.  Lookup methods return copies
    or lightweight views; callers cannot mutate the internal index.
    """

    def __init__(self, raw: dict[str, Any] | None = None) -> None:
        data = raw if raw is not None else self._load_json()
        schema_version = data.get("schema_version")
        if schema_version != 1:
            raise CatalogError(f"unsupported catalog schema version: {schema_version!r}")
        self._patch: str = data.get("patch", "")
        self._updated_at: str = data.get("updated_at", "")
        records = [self._parse_record(r) for r in data.get("augments", [])]
        self._records: tuple[AugmentRecord, ...] = tuple(records)
        self._by_id: dict[str, AugmentRecord] = {}
        self._by_name_en: dict[str, AugmentRecord] = {}
        self._by_name_ko: dict[str, AugmentRecord] = {}
        self._by_alias: dict[str, AugmentRecord] = {}
        self._build_index()

    @classmethod
    def _load_json(cls) -> dict[str, Any]:
        ref = importlib.resources.files(_PACKAGE) / _RESOURCE_NAME
        return json.loads(ref.read_text(encoding="utf-8"))

    @classmethod
    def from_file(cls, path: str | Path) -> AugmentCatalog:
        """Load a catalog from a local JSON file (used by the refresh script)."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(raw)

    @classmethod
    def validate_file(cls, path: str | Path) -> list[str]:
        """Validate a catalog file and return a list of human-readable errors."""
        errors: list[str] = []
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            return [f"cannot parse JSON: {exc}"]
        if raw.get("schema_version") != 1:
            errors.append(f"unsupported schema version {raw.get('schema_version')!r}")
        augments = raw.get("augments", [])
        if not isinstance(augments, list):
            errors.append("'augments' must be a list")
            return errors

        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for idx, rec in enumerate(augments):
            prefix = f"augments[{idx}]"
            if not isinstance(rec, dict):
                errors.append(f"{prefix} is not an object")
                continue
            rid = rec.get("id", "")
            if not rid:
                errors.append(f"{prefix} missing id")
            elif rid in seen_ids:
                errors.append(f"duplicate id {rid!r}")
            seen_ids.add(rid)

            name_en = rec.get("name_en", "")
            if not name_en:
                errors.append(f"{prefix} missing name_en")
            nname = _norm_name(name_en)
            if nname and nname in seen_names:
                errors.append(f"duplicate normalized name_en {name_en!r}")
            seen_names.add(nname)

            expected_id = _id_from_name(name_en)
            if rid and rid != expected_id:
                errors.append(
                    f"{prefix} id {rid!r} does not match expected id {expected_id!r}"
                )

            rarity = rec.get("rarity", "")
            if rarity and rarity not in _RARITIES:
                errors.append(f"{prefix} invalid rarity {rarity!r}")
            tier = rec.get("fallback_tier", "")
            if tier and tier not in _TIERS:
                errors.append(f"{prefix} invalid fallback_tier {tier!r}")

            for cand in rec.get("image_candidates", []):
                if not isinstance(cand, dict):
                    errors.append(f"{prefix} image candidate is not an object")
                    continue
                kind = cand.get("kind", "")
                if kind not in _SOURCE_KINDS:
                    errors.append(
                        f"{prefix} image candidate has unsupported kind {kind!r}"
                    )
                size = cand.get("size", 0)
                # The per-rarity generic placeholder's native resolution is
                # 64px; every augment with unique art must clear 128px.
                min_size = (
                    64
                    if "genericabilityaugmenticon" in str(cand.get("url", ""))
                    else 128
                )
                if not isinstance(size, int) or size < min_size:
                    errors.append(
                        f"{prefix} image candidate size must be >={min_size}px (got {size!r})"
                    )
                url = cand.get("url", "")
                if not url or not url.startswith(("http://", "https://")):
                    errors.append(f"{prefix} image candidate missing valid url")

            for src in rec.get("sources", []):
                if not isinstance(src, dict):
                    errors.append(f"{prefix} source is not an object")
                    continue
                kind = src.get("kind", "")
                if kind not in _SOURCE_KINDS:
                    errors.append(f"{prefix} source has unsupported kind {kind!r}")

        return errors

    @staticmethod
    def _parse_record(rec: dict[str, Any]) -> AugmentRecord:
        images = tuple(
            ImageCandidate(
                url=str(c["url"]),
                kind=str(c["kind"]),
                size=int(c["size"]),
            )
            for c in rec.get("image_candidates", [])
        )
        sources = tuple(
            SourceRecord(
                kind=str(s["kind"]),
                url=str(s["url"]),
                retrieved_at=str(s.get("retrieved_at", "")),
                note=str(s.get("note", "")),
            )
            for s in rec.get("sources", [])
        )
        return AugmentRecord(
            id=str(rec["id"]),
            name_en=str(rec["name_en"]),
            name_ko=str(rec.get("name_ko", "")),
            description_ko=str(rec.get("description_ko", "")),
            rarity=str(rec.get("rarity", "")),
            fallback_tier=str(rec.get("fallback_tier", "")),
            aliases=tuple(str(a) for a in rec.get("aliases", [])),
            image_candidates=images,
            sources=sources,
            archetype_prefer=tuple(str(a) for a in rec.get("archetype_prefer", [])),
            archetype_avoid=tuple(str(a) for a in rec.get("archetype_avoid", [])),
        )

    def _build_index(self) -> None:
        for rec in self._records:
            if rec.id in self._by_id:
                raise CatalogError(f"duplicate augment id: {rec.id}")
            self._by_id[rec.id] = rec

            def _register_name(name: str, target: dict[str, AugmentRecord]) -> None:
                key = _norm_name(name)
                if not key:
                    return
                if key in target:
                    raise CatalogError(f"duplicate augment name key: {key}")
                target[key] = rec  # noqa: B023 — 즉시 호출되는 클로저라 지연 바인딩 문제 없음

            _register_name(rec.name_en, self._by_name_en)
            _register_name(rec.name_ko, self._by_name_ko)
            for alias in rec.aliases:
                _register_name(alias, self._by_alias)

    @property
    def patch(self) -> str:
        return self._patch

    @property
    def updated_at(self) -> str:
        return self._updated_at

    @property
    def records(self) -> tuple[AugmentRecord, ...]:
        """All catalog records, immutable tuple."""
        return self._records

    def get_by_id(self, rid: str) -> AugmentRecord | None:
        return self._by_id.get(rid)

    def get_by_name(self, name: str) -> AugmentRecord | None:
        """Look up by English or Korean canonical name, then aliases."""
        key = _norm_name(name)
        return (
            self._by_name_en.get(key)
            or self._by_name_ko.get(key)
            or self._by_alias.get(key)
        )

    def resolve_many(
        self,
        names: Iterable[str],
        *,
        strict: bool = False,
    ) -> tuple[list[AugmentRecord], list[str], list[str]]:
        """Resolve an iterable of user-entered augment names.

        Returns ``(records, unknowns, duplicates)``.  Duplicates are reported as
        the later occurrence strings that were ignored.  When ``strict`` is
        ``True``, any unknown or empty input raises :class:`CatalogError`.
        """
        records: list[AugmentRecord] = []
        seen: set[str] = set()
        unknowns: list[str] = []
        duplicates: list[str] = []
        for raw in names:
            token = _norm_name(raw)
            if not token:
                continue
            rec = self.get_by_name(token)
            if rec is None:
                unknowns.append(raw)
                if strict:
                    raise CatalogError(f"unknown augment: {raw!r}")
                continue
            if rec.id in seen:
                duplicates.append(raw)
                continue
            seen.add(rec.id)
            records.append(rec)
        return records, unknowns, duplicates

    def suggestions(self, prefix: str, *, limit: int = 8) -> list[AugmentRecord]:
        """Return up to ``limit`` records whose English or Korean name starts
        with ``prefix`` (case-insensitive, normalised)."""
        key = _norm_name(prefix).lower()
        if not key:
            return []
        out: list[AugmentRecord] = []
        for rec in self._records:
            if any(
                _norm_name(n).lower().startswith(key)
                for n in (rec.name_en, rec.name_ko, *rec.aliases)
            ):
                out.append(rec)
                if len(out) >= limit:
                    break
        return out

    def candidate_urls_for(
        self,
        name_or_id: str,
        *,
        kinds_order: tuple[str, ...] = ("riot_data", "riot_patch_notes", "ugg", "league_wiki", "aram_mayhem"),
    ) -> list[str]:
        """Ordered exact image candidate URLs for an augment (Riot-first)."""
        rec = self.get_by_name(name_or_id) or self.get_by_id(name_or_id)
        if rec is None:
            return []
        order = {k: i for i, k in enumerate(kinds_order)}
        sorted_cands = sorted(
            rec.image_candidates,
            key=lambda c: (order.get(c.kind, len(order)), -c.size),
        )
        return [c.url for c in sorted_cands]
