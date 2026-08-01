from lol_coach.ugg.parser import parse_champion_build_html

SAMPLE = """
<html><head><title>Ahri Build - Patch 26.13</title></head>
<body>
<h1>Ahri Build for Mid, Emerald + Patch 26.13</h1>
<div>Tier S Win Rate 50.89% Rank 14 / 54 Pick Rate 8.9% Ban Rate 3.3% Matches 221,324</div>
<div class="recommended-build_runes">
  Ahri Mid Build 51.52% WR (17,239 Matches)
  <div class="rune-tree_header"><img alt="The Rune Tree Domination" /></div>
  <div class="perk keystone perk-active"><img alt="The Keystone Electrocute" /></div>
  <div class="perk perk-active"><img alt="The Rune Taste of Blood" /></div>
  <div class="perk perk-active"><img alt="The Rune Grisly Mementos" /></div>
  <div class="perk perk-active"><img alt="The Rune Ultimate Hunter" /></div>
  <div class="rune-tree_header"><img alt="The Rune Tree Sorcery" /></div>
  <div class="perk perk-active"><img alt="The Rune Manaflow Band" /></div>
  <div class="perk perk-active"><img alt="The Rune Scorch" /></div>
  <div class="shard shard-active"><img alt="The Attack Speed Shard" /></div>
  <div class="shard shard-active"><img alt="The Adaptive Force Shard" /></div>
  <div class="shard shard-active"><img alt="The Health Shard" /></div>
</div>
<div class="skill-priority">Skill Priority Q W E 51.63% WR 120,235 Matches</div>
<div class="skill-path-container">
  <div class="skill-order-row">Q 2 4 5 7 9</div>
  <div class="skill-order-row">W 1 8 10 12 13</div>
  <div class="skill-order-row">E 3 14 15 17 18</div>
  <div class="skill-order-row">R 6 11 16</div>
</div>
<div class="core-items">Core Items 54.83% WR 10,062 Matches
  <img alt="Blackfire Torch" src="https://example/item/2503.png" />
</div>
<div class="starting-items">Starting Items 51.02% WR 217,488 Matches Best for most matchups</div>
</body></html>
"""


def test_parse_basic_stats_and_runes():
    build = parse_champion_build_html(SAMPLE, champion="Ahri", role="MIDDLE")
    assert build.patch == "26.13"
    assert build.tier == "S"
    assert build.win_rate == 50.89
    assert build.pick_rate == 8.9
    assert build.ban_rate == 3.3
    assert build.matches == 221324
    assert build.runes.keystone == "Electrocute"
    assert build.runes.primary_tree == "Domination"
    assert build.runes.secondary_tree == "Sorcery"
    assert "Taste of Blood" in build.runes.primary_runes
    assert build.skills.priority == ["Q", "W", "E"]
    assert build.core_items.items
    assert "Blackfire Torch" in build.core_items.items
