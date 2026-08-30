"""Fetch every champion's ordered ARAM Mayhem core build from Blitz.gg."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from lol_coach.static.blitz_aram import BlitzAramBuild, parse_blitz_aram_page

_BLITZ_URL = "https://blitz.gg/ko/lol/champions/{champion}/aram-mayhem"
_DDRAGON_VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"
_DDRAGON_CHAMPIONS = (
    "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
)
_USER_AGENT = "lol-coach-blitz-aram-refresh/1.0"
_DEFAULT_OUTPUT = Path("src/lol_coach/data/blitz_aram_builds.json")


def _get_json(url: str, timeout: float) -> dict[str, Any] | list[Any]:
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _champion_keys(timeout: float) -> list[str]:
    versions = _get_json(_DDRAGON_VERSIONS, timeout)
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("Data Dragon versions response is empty")
    version = str(versions[0])
    payload = _get_json(_DDRAGON_CHAMPIONS.format(version=version), timeout)
    champions = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(champions, dict):
        raise RuntimeError("Data Dragon champion response is invalid")
    return sorted(
        str(key)
        for key in champions
        if not str(key).startswith("Jade_")
    )


def _fetch_one(champion: str, patch: str, timeout: float) -> BlitzAramBuild:
    url = _BLITZ_URL.format(champion=champion)
    response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    html = response.content.decode("utf-8", errors="replace")
    return parse_blitz_aram_page(
        html,
        champion=champion,
        patch=patch,
        source_url=url,
    )


def _to_raw(build: BlitzAramBuild) -> dict[str, Any]:
    return {
        "champion": build.champion,
        "patch": build.patch,
        "source_url": build.source_url,
        "core_items": [
            {
                "item_id": item.item_id,
                "name_ko": item.name_ko,
                "icon_url": item.icon_url,
            }
            for item in build.core_items
        ],
        "augment_tiers": {
            tier: list(names) for tier, names in build.augment_tiers.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh packaged Blitz ARAM Mayhem champion builds"
    )
    parser.add_argument("--patch", default="", help="비우면 현재 패치로 자동 판별")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be positive")

    champions = _champion_keys(args.timeout)
    print(f"fetching Blitz ARAM builds for {len(champions)} champions (patch {args.patch}) ...")
    records: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_fetch_one, champion, args.patch, args.timeout): champion
            for champion in champions
        }
        for future in as_completed(futures):
            champion = futures[future]
            try:
                records[champion] = _to_raw(future.result())
            except Exception as exc:
                failures.append(f"{champion}: {exc}")
                print(f"FAILED {champion}: {exc}")

    if failures:
        print(f"aborting: {len(failures)} champion pages failed", file=sys.stderr)
        return 2
    output = {
        "schema_version": 2,
        "source": "https://blitz.gg/ko/lol/champions/{champion}/aram-mayhem",
        "patch": args.patch,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builds": [records[champion] for champion in champions],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} ({len(champions)} champions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
