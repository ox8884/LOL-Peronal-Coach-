"""blitz.gg 파서 테스트용 인라인 HTML 샘플 (네트워크 없음)."""

from __future__ import annotations

BUILD_SAMPLE = """
<html><body>
  Patch 26.15
  Win rate 51.4% Pick rate 4.8% Ban rate 1.5% Matches 137,581
  <div class="rune-tree primary-tree">
    <div class="tree-option active"><img alt="Domination"/></div>
    <div class="tree-row keystone-row">
      <div class="rune-container"><img class="rune-img active" alt="Electrocute"/></div>
      <div class="rune-container"><img class="rune-img" alt="Dark Harvest"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Taste of Blood"/></div>
      <div class="rune-container"><img class="rune-img" alt="Cheap Shot"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Grisly Mementos"/></div>
      <div class="rune-container"><img class="rune-img" alt="Deep Ward"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Ultimate Hunter"/></div>
      <div class="rune-container"><img class="rune-img" alt="Treasure Hunter"/></div>
    </div>
  </div>
  <div class="rune-tree">
    <div class="tree-option active"><img alt="Sorcery"/></div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Manaflow Band"/></div>
      <div class="rune-container"><img class="rune-img" alt="Nimbus Cloak"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Scorch"/></div>
      <div class="rune-container"><img class="rune-img" alt="Gathering Storm"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Adaptive Force"/></div>
      <div class="rune-container"><img class="rune-img" alt="Attack Speed"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Health"/></div>
      <div class="rune-container"><img class="rune-img" alt="Armor"/></div>
    </div>
    <div class="tree-row">
      <div class="rune-container"><img class="rune-img active" alt="Ability Haste"/></div>
      <div class="rune-container"><img class="rune-img" alt="Move Speed"/></div>
    </div>
  </div>
  <div class="skill-order">Ability Max Order 64% 37,301 games Q W E 1 W 2 Q 3 E 4 Q 5 Q 6 R 7 Q 8 W 9 Q 10 W 11 R 12 Q 13 E 14 W 15 E 16 R 17 E 18 E</div>
  <img src="https://blitz-cdn.blitz.gg/blitz/lol/summoner-spells/4.webp" alt=""/>
  <img src="https://blitz-cdn.blitz.gg/blitz/lol/summoner-spells/14.webp" alt=""/>
  <div class="items-group">Starting Items <img class="item-img" alt="Doran's Ring"/><img class="item-img" alt="Health Potion"/></div>
  <div class="items-group">Build Order <img class="item-img" alt="Lost Chapter"/><img class="item-img" alt="Malignance"/></div>
  <div class="items-group">Completed Items <img class="item-img" alt="Malignance"/><img class="item-img" alt="Sorcerer's Shoes"/><img class="item-img" alt="Shadowflame"/><img class="item-img" alt="Rabadon's Deathcap"/></div>
  <div class="items-group">Situational Items <img class="item-img" alt="Void Staff"/><img class="item-img" alt="Stormsurge"/></div>
</body></html>
"""

COUNTER_SAMPLE = """
<html><body>
  Patch: 26.13
  <table>
    <thead><tr><th>Champion</th><th>Score</th><th>Games</th></tr></thead>
    <tbody>
      <tr><td><div class="cell left"><a class="champion">Galio</a></div></td><td>38</td><td>2,896</td></tr>
      <tr><td><div class="cell left"><a class="champion">Anivia</a></div></td><td>36</td><td>1,867</td></tr>
      <tr><td><div class="cell left"><a class="champion">Katarina</a></div></td><td>-19</td><td>4,999</td></tr>
      <tr><td><div class="cell left"><a class="champion">Zed</a></div></td><td>-25</td><td>3,000</td></tr>
    </tbody>
  </table>
</body></html>
"""
