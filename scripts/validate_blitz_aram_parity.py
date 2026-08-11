"""Validate packaged Blitz ARAM tiers against the app's displayed order."""

from __future__ import annotations

import json
from typing import Any

from lol_coach.analysis.aram_mayhem import MayhemCoach

_TIERS = ("prismatic", "gold", "silver")


def build_report() -> dict[str, Any]:
    coach = MayhemCoach()
    catalog = coach.blitz
    records = catalog.records if catalog is not None else ()
    mismatches: list[dict[str, Any]] = []
    missing_tiers: list[str] = []
    unknown_names: dict[str, list[str]] = {}

    for build in records:
        if any(not build.augment_tiers.get(tier) for tier in _TIERS):
            missing_tiers.append(build.champion)
        expected = [
            name
            for tier in _TIERS
            for name in build.augment_tiers.get(tier, ())
        ][:5]
        advice = coach.advise(build.champion)
        actual = [pick.name_ko for pick in advice.top_augments]
        if actual != expected:
            mismatches.append(
                {
                    "champion": build.champion,
                    "expected": expected,
                    "actual": actual,
                }
            )
        unknown = [
            name
            for tier in _TIERS
            for name in build.augment_tiers.get(tier, ())
            if coach.catalog.get_by_name(name) is None
        ]
        if unknown:
            unknown_names[build.champion] = unknown

    return {
        "patch": catalog.patch if catalog is not None else "",
        "champions": len(records),
        "missing_tier_records": missing_tiers,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "unknown_catalog_names": unknown_names,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return int(
        bool(
            report["missing_tier_records"]
            or report["mismatch_count"]
            or report["unknown_catalog_names"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
