from pathlib import Path

from lol_coach.analysis.aram_mayhem import MayhemCoach
from lol_coach.static.blitz_aram import BlitzAramCatalog, parse_blitz_aram_page

FIXTURE = Path(__file__).parent / "fixtures" / "blitz_masteryi_aram.html"


def test_master_yi_app_order_matches_packaged_blitz() -> None:
    build = parse_blitz_aram_page(
        FIXTURE.read_text(encoding="utf-8"),
        champion="MasterYi",
        patch="16.15",
        source_url="https://blitz.gg/ko/lol/champions/MasterYi/aram-mayhem",
    )
    catalog = BlitzAramCatalog(
        patch="16.15",
        updated_at="fixture",
        records=(build,),
    )

    advice = MayhemCoach(blitz=catalog).advise("Master Yi")

    expected = (
        list(build.augment_tiers["prismatic"])
        + list(build.augment_tiers["gold"])
        + list(build.augment_tiers["silver"])
    )[:5]
    actual = [pick.name_ko for pick in advice.top_augments]

    assert actual == expected


def test_all_packaged_champions_match_blitz_augment_order() -> None:
    coach = MayhemCoach()
    mismatches: list[str] = []

    for build in coach.blitz.records if coach.blitz is not None else ():
        advice = coach.advise(build.champion)
        expected = (
            list(build.augment_tiers.get("prismatic", ()))
            + list(build.augment_tiers.get("gold", ()))
            + list(build.augment_tiers.get("silver", ()))
        )[:5]
        actual = [pick.name_ko for pick in advice.top_augments]
        if actual != expected:
            mismatches.append(f"{build.champion}: {actual!r} != {expected!r}")

    assert not mismatches, "\n".join(mismatches)
