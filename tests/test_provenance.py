from lol_coach.gui.components import provenance_label
from lol_coach.riot.client import aggregate_form
from lol_coach.riot.models import MatchSummary, PlayerProfile


def _match(match_id: str, game_version: str) -> MatchSummary:
    return MatchSummary(
        match_id=match_id,
        champion_name="Ahri",
        champion_id=1,
        role="MIDDLE",
        lane="MIDDLE",
        win=True,
        kills=5,
        deaths=2,
        assists=7,
        cs=180,
        gold=10_000,
        damage_to_champs=20_000,
        vision_score=20,
        game_duration_s=1_500,
        queue_id=420,
        game_version=game_version,
    )


def test_recent_form_exposes_structured_provenance_context() -> None:
    profile = PlayerProfile(
        game_name="Jay",
        tag_line="KR1",
        puuid="PUUID",
        platform="kr",
    )

    form = aggregate_form(
        profile,
        [_match("KR-1", "15.1"), _match("KR-2", "15.1")],
    )

    provenance = form.provenance

    assert provenance.source == "Riot Match-V5"
    assert provenance.patches == ("15.1",)
    assert provenance.sample_count == 2
    assert provenance.freshness == "unknown"
    assert "표본 부족" in provenance_label(provenance)
