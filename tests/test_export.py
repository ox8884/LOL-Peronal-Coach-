"""전적 CSV/JSON 납품 테스트."""

import csv
import json

from lol_coach.analysis.export import export_matches_csv, export_matches_json
from lol_coach.riot.models import MatchSummary, PlayerProfile, RecentForm


def _match(win: bool = True) -> MatchSummary:
    return MatchSummary(
        match_id="KR_1",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MID",
        win=win,
        kills=8,
        deaths=2,
        assists=9,
        cs=210,
        gold=12500,
        damage_to_champs=23000,
        vision_score=22,
        game_duration_s=1800,
        queue_id=420,
        kill_participation=0.55,
        damage_share=0.3,
    )


def _form() -> RecentForm:
    return RecentForm(
        profile=PlayerProfile(
            game_name="테스터", tag_line="KR1", puuid="p", platform="kr"
        ),
        matches=[_match(True), _match(False)],
        wins=1,
        losses=1,
        avg_kda=8.5,
        avg_cs_per_min=7.0,
        role_counts={"MIDDLE": 2},
        champion_stats={},
    )


def test_export_csv(tmp_path) -> None:
    out = export_matches_csv(_form(), tmp_path / "m.csv")
    assert out.exists()
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["champion"] == "Ahri"
    assert rows[0]["win"] == "승"
    assert rows[1]["win"] == "패"
    assert rows[0]["kill_participation"] == "55.0"
    assert rows[0]["damage_share"] == "30.0"


def test_export_json(tmp_path) -> None:
    out = export_matches_json(_form(), tmp_path / "m.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"]["riot_id"] == "테스터#KR1"
    assert data["summary"]["games"] == 2
    assert len(data["matches"]) == 2
    assert data["matches"][0]["match_id"] == "KR_1"


def test_export_creates_parent_dirs(tmp_path) -> None:
    out = export_matches_csv(_form(), tmp_path / "deep" / "nested" / "m.csv")
    assert out.exists()
