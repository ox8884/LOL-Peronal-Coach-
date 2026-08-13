"""이 판 누구 탓 % — 배분 모델·카드 테스트."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from lol_coach.analysis.blame import analyze_blame, player_score
from lol_coach.gui.blame_card import blame_card_bytes
from lol_coach.riot.models import MatchPlayer, MatchSummary


def _player(
    *,
    champ: str = "Ahri",
    champ_id: int = 103,
    kills: int,
    deaths: int,
    assists: int,
    dmg: int,
    is_me: bool = False,
) -> MatchPlayer:
    return MatchPlayer(
        champion_name=champ,
        champion_id=champ_id,
        role="MIDDLE",
        team_id=100,
        kills=kills,
        deaths=deaths,
        assists=assists,
        cs=100,
        gold=10000,
        damage_to_champs=dmg,
        vision_score=5,
        champ_level=18,
        is_me=is_me,
    )


def _match(
    *,
    win: bool,
    me: tuple[int, int, int, int],
    allies: list[tuple[int, int, int, int]],
    enemies: list[tuple[int, int, int, int]],
) -> MatchSummary:
    my_k, my_d, my_a, my_dmg = me
    ally_team = [
        _player(is_me=True, kills=my_k, deaths=my_d, assists=my_a, dmg=my_dmg)
    ] + [
        _player(
            champ=f"C{i}",
            champ_id=100 + i,
            kills=k,
            deaths=d,
            assists=a,
            dmg=dmg,
        )
        for i, (k, d, a, dmg) in enumerate(allies, 1)
    ]
    enemy_team = [
        _player(
            champ=f"E{i}",
            champ_id=200 + i,
            kills=k,
            deaths=d,
            assists=a,
            dmg=dmg,
        )
        for i, (k, d, a, dmg) in enumerate(enemies, 1)
    ]
    return MatchSummary(
        match_id="KR_TEST",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MID",
        win=win,
        kills=my_k,
        deaths=my_d,
        assists=my_a,
        cs=120,
        gold=12000,
        damage_to_champs=my_dmg,
        vision_score=6,
        game_duration_s=1200,
        queue_id=450,
        ally_team=ally_team,
        enemy_team=enemy_team,
    )


# ── 모델 ──────────────────────────────────────────────────


def test_player_score_weights_damage_share() -> None:
    assert player_score(_player(kills=5, deaths=5, assists=5, dmg=500), 1000) > 0
    assert (
        player_score(_player(kills=5, deaths=5, assists=5, dmg=500), 1000)
        > player_score(_player(kills=5, deaths=5, assists=5, dmg=0), 1000)
    )


def test_team_was_heavy_when_i_played_well() -> None:
    m = _match(
        win=False,
        me=(10, 2, 8, 40000),
        allies=[(2, 10, 3, 8000)] * 4,
        enemies=[(9, 4, 9, 25000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    assert report.team_pct >= 55
    assert report.me_pct < 25
    assert "팀 탓" in report.verdict
    assert report.me_pct + report.team_pct + report.enemy_pct == 100


def test_i_was_the_problem() -> None:
    m = _match(
        win=False,
        me=(1, 10, 2, 5000),
        allies=[(8, 4, 9, 20000)] * 4,
        enemies=[(6, 5, 7, 18000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    assert report.me_pct >= 40
    assert "내 탓" in report.verdict
    assert report.me_pct + report.team_pct + report.enemy_pct == 100


def test_enemy_stomped_us_together() -> None:
    m = _match(
        win=False,
        me=(3, 8, 4, 9000),
        allies=[(3, 9, 4, 8000)] * 4,
        enemies=[(12, 3, 10, 30000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    assert "같이 무너" in report.verdict


def test_win_carry_narrative() -> None:
    m = _match(
        win=True,
        me=(14, 2, 10, 45000),
        allies=[(4, 6, 8, 12000)] * 4,
        enemies=[(5, 7, 6, 15000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    assert "캐리" in report.verdict
    assert report.me_pct >= 40


def test_insufficient_sample_returns_none() -> None:
    m = _match(
        win=False,
        me=(5, 5, 5, 10000),
        allies=[(2, 10, 3, 8000)],  # 팀원 1명뿐
        enemies=[(9, 4, 9, 25000)] * 5,
    )
    assert analyze_blame(m) is None


def test_blame_is_deterministic() -> None:
    m = _match(
        win=False,
        me=(10, 2, 8, 40000),
        allies=[(2, 10, 3, 8000)] * 4,
        enemies=[(9, 4, 9, 25000)] * 5,
    )
    a = analyze_blame(m)
    b = analyze_blame(m)
    assert a == b


# ── 카드 ──────────────────────────────────────────────────


def test_blame_card_bytes_valid_png() -> None:
    m = _match(
        win=False,
        me=(10, 2, 8, 40000),
        allies=[(2, 10, 3, 8000)] * 4,
        enemies=[(9, 4, 9, 25000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    data = blame_card_bytes(report, champ_ko="오리아나")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(BytesIO(data)) as img:
        assert img.size[0] == 960
        assert img.size[1] > 400


def test_blame_card_win_variant() -> None:
    m = _match(
        win=True,
        me=(14, 2, 10, 45000),
        allies=[(4, 6, 8, 12000)] * 4,
        enemies=[(5, 7, 6, 15000)] * 5,
    )
    report = analyze_blame(m)
    assert report is not None
    data = blame_card_bytes(report, champ_ko="아리")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
