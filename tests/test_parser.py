"""blitz.gg 파서 테스트 — 빌드/카운터 인라인 스니펫 (네트워크 없음)."""

from __future__ import annotations

import pytest
from blitz_samples import BUILD_SAMPLE, COUNTER_SAMPLE

from lol_coach.blitz.models import BlitzError
from lol_coach.blitz.parser import (
    champion_slug,
    normalize_role,
    parse_build_html,
    parse_counters_html,
)


def test_parse_build_stats_and_runes() -> None:
    build = parse_build_html(
        BUILD_SAMPLE, champion="Ahri", role="mid", source_url="https://blitz.gg/x"
    )
    assert build.patch == "26.15"
    assert build.win_rate == 51.4
    assert build.pick_rate == 4.8
    assert build.ban_rate == 1.5
    assert build.matches == 137581
    assert build.runes.primary_tree == "Domination"
    assert build.runes.secondary_tree == "Sorcery"
    assert build.runes.keystone == "Electrocute"
    assert build.runes.primary_runes == [
        "Taste of Blood",
        "Grisly Mementos",
        "Ultimate Hunter",
    ]
    assert build.runes.secondary_runes == ["Manaflow Band", "Scorch"]
    assert build.runes.shards == ["Adaptive Force", "Health", "Ability Haste"]


def test_parse_build_skills_spells_items() -> None:
    build = parse_build_html(
        BUILD_SAMPLE, champion="Ahri", role="mid", source_url="https://blitz.gg/x"
    )
    assert build.skills.priority == ["Q", "W", "E"]
    assert build.skills.order_by_level[:6] == ["W", "Q", "E", "Q", "Q", "R"]
    assert build.summoner_spells == ["Flash", "Ignite"]
    # 신발은 boots 섹션으로 분리, 코어는 5개 제한
    assert build.core_items.items == ["Malignance", "Shadowflame", "Rabadon's Deathcap"]
    assert build.boots.items == ["Sorcerer's Shoes"]
    assert build.starting_items.items == ["Doran's Ring", "Health Potion"]
    assert len(build.situational) == 1
    assert build.situational[0].items == ["Void Staff", "Stormsurge"]


def test_parse_build_missing_data_raises() -> None:
    with pytest.raises(BlitzError):
        parse_build_html(
            "<html><body>nothing here</body></html>",
            champion="Ahri",
            role="mid",
            source_url="x",
        )


def test_parse_counters_direction_and_sort() -> None:
    rep = parse_counters_html(
        COUNTER_SAMPLE, enemy="Ahri", role="mid", source_url="https://blitz.gg/x"
    )
    # Score > 0 = 아리를 카운터하는 픽 (lane_counters), < 0 = 아리가 유리 (hard)
    assert [c.champion for c in rep.lane_counters] == ["Galio", "Anivia"]
    assert rep.lane_counters[0].gd15 == 38
    assert rep.lane_counters[0].matches == 2896
    assert rep.patch == "26.13"
    assert [c.champion for c in rep.hard_matchups] == ["Zed", "Katarina"]


def test_normalize_role_and_slug() -> None:
    assert normalize_role("middle") == "mid"
    assert normalize_role("SUPP") == "support"
    with pytest.raises(BlitzError):
        normalize_role("jungler")
    assert champion_slug("Renata Glasc") == "renata"
    assert champion_slug("Nunu & Willump") == "nunu"
    assert champion_slug("Wukong") == "monkeyking"
