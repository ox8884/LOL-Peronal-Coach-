from pathlib import Path

from lol_coach.static.blitz_aram import BlitzAramCatalog, parse_blitz_aram_page

ROOT = Path(__file__).resolve().parents[1]
BUILDS_PATH = ROOT / "src" / "lol_coach" / "data" / "blitz_aram_builds.json"


def test_parser_keeps_blitz_completed_item_order() -> None:
    html = """
    <section class="items">
      <div class="items-group"><h3>시작 아이템</h3>
        <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/1038.webp" alt="B.F. 대검">
      </div>
      <div class="items-group"><h3>완성 아이템</h3>
        <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/3031.webp" alt="무한의 대검">
        <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/3094.webp" alt="고속 연사포">
        <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/6676.webp" alt="징수의 총">
      </div>
      <div class="items-group"><h3>상황별 아이템</h3>
        <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/3036.webp" alt="도미닉 경의 인사">
      </div>
    </section>
    """

    build = parse_blitz_aram_page(
        html,
        champion="Caitlyn",
        patch="16.15",
        source_url="https://blitz.gg/ko/lol/champions/Caitlyn/aram-mayhem",
    )

    assert [item.name_ko for item in build.core_items] == [
        "무한의 대검",
        "고속 연사포",
        "징수의 총",
    ]
    assert all(item.icon_url.startswith("https://blitz-cdn.blitz.gg/") for item in build.core_items)


def test_packaged_catalog_covers_current_champions() -> None:
    catalog = BlitzAramCatalog.from_file(BUILDS_PATH)
    assert len(catalog.records) >= 160

    caitlyn = catalog.get("Caitlyn")
    assert caitlyn is not None
    assert caitlyn.patch == "16.15"
    assert caitlyn.source_url.endswith("/Caitlyn/aram-mayhem")
    assert len(caitlyn.core_items) >= 3
    assert all(item.name_ko for item in caitlyn.core_items)
    assert all(item.icon_url.startswith("https://blitz-cdn.blitz.gg/") for item in caitlyn.core_items)


FIXTURE = Path(__file__).parent / "fixtures" / "blitz_masteryi_aram.html"


def test_parse_champion_specific_augment_tiers() -> None:
    build = parse_blitz_aram_page(
        FIXTURE.read_text(encoding="utf-8"),
        champion="MasterYi",
        patch="16.15",
        source_url="https://blitz.gg/ko/lol/champions/MasterYi/aram-mayhem",
    )

    assert build.augment_tiers == {
        "prismatic": ("신비한 주먹", "기본으로 돌아가기"),
        "gold": ("시작부터 끝까지", "치명적인 공격"),
        "silver": ("육중한 힘", "능수능란"),
    }
    assert [item.name_ko for item in build.core_items] == ["징수의 총", "광전사의 군화"]
