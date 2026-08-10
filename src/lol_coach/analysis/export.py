"""최근 전적(RecentForm)을 CSV/JSON 파일로 내보내기.

GUI(파일 대화상자)와 CLI(export 명령)가 공용으로 사용한다.
"""

from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path

from lol_coach.riot.models import MatchSummary, RecentForm

_CSV_COLUMNS = [
    "match_id",
    "mode",
    "queue_id",
    "champion",
    "role",
    "win",
    "kills",
    "deaths",
    "assists",
    "kda",
    "cs",
    "cs_per_min",
    "gold",
    "damage",
    "vision",
    "duration_min",
    "kill_participation",
    "damage_share",
    "game_version",
]


def _csv_safe(value: object) -> object:
    """Excel 수식 주입 방지 — = + - @ 로 시작하는 문자열 앞에 작은따옴표."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _match_row(m: MatchSummary) -> dict:
    return {
        "match_id": m.match_id,
        "mode": m.mode_label,
        "queue_id": m.queue_id,
        "champion": m.champion_name,
        "role": m.role,
        "win": "승" if m.win else "패",
        "kills": m.kills,
        "deaths": m.deaths,
        "assists": m.assists,
        "kda": m.kda_ratio,
        "cs": m.cs,
        "cs_per_min": m.cs_per_min,
        "gold": m.gold,
        "damage": m.damage_to_champs,
        "vision": m.vision_score,
        "duration_min": m.duration_min,
        "kill_participation": (
            round(m.kill_participation * 100, 1)
            if m.kill_participation is not None and m.kill_participation <= 1.5
            else m.kill_participation
        ),
        "damage_share": (
            round(m.damage_share * 100, 1) if m.damage_share is not None else ""
        ),
        "game_version": m.game_version,
    }


def export_matches_csv(form: RecentForm, path: str | Path) -> Path:
    """최근 경기 목록 → CSV (엑셀 호환 utf-8-sig)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for m in form.matches:
            writer.writerow({k: _csv_safe(v) for k, v in _match_row(m).items()})
    return out


def export_matches_json(form: RecentForm, path: str | Path) -> Path:
    """최근 경기 + 챔프별 집계 → JSON."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": {
            "riot_id": form.profile.riot_id,
            "platform": form.profile.platform,
            "puuid": form.profile.puuid,
        },
        "summary": {
            "games": form.games,
            "wins": form.wins,
            "losses": form.losses,
            "winrate": form.winrate,
            "avg_kda": form.avg_kda,
            "avg_cs_per_min": form.avg_cs_per_min,
        },
        "champion_stats": [
            dataclasses.asdict(c) for c in form.champion_stats.values()
        ],
        "matches": [_match_row(m) for m in form.matches],
    }
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out
