"""챔피언 풀 진단 판정 테스트."""

from types import SimpleNamespace

from lol_coach.analysis.pool import diagnose_pool
from lol_coach.riot.models import ChampionStats


def _form(champ_stats: dict[str, ChampionStats], games: int = 30, wins: int = 15):
    return SimpleNamespace(
        games=games,
        wins=wins,
        losses=games - wins,
        winrate=round(100.0 * wins / games, 1),
        champion_stats=champ_stats,
    )


def _stats(name: str, games: int, wins: int, kda: float = 2.5) -> ChampionStats:
    cs = ChampionStats(champion_name=name)
    cs.games = games
    cs.wins = wins
    # avg_kda 계산용 누적 (deaths=1/g 가정)
    cs.kills = kda * games / 2
    cs.assists = kda * games / 2
    cs.deaths = games
    return cs


def test_focus_verdict_for_strong_champion() -> None:
    form = _form(
        {
            "Ahri": _stats("Ahri", games=10, wins=9),  # 90% > 전체 50% + 마진
            "Zed": _stats("Zed", games=10, wins=4),
        },
        games=20,
        wins=13,  # 전체 65% → Ahri 보정 (9+2.5)/(10+5)=76.7 ≥ 70
    )
    # 전체 승률보다 확실히 높은 챔프만 집중
    report = diagnose_pool(form)
    by_name = {e.champion_name: e for e in report.entries}
    assert by_name["Ahri"].verdict == "집중"
    assert by_name["Ahri"].adjusted_wr > by_name["Zed"].adjusted_wr


def test_drop_verdict_for_low_winrate() -> None:
    form = _form(
        {"Yasuo": _stats("Yasuo", games=8, wins=1)},  # 12.5% → 보정 26.9 < 45
        games=8,
        wins=1,
    )
    report = diagnose_pool(form)
    entry = report.entries[0]
    assert entry.verdict == "정리 검토"
    assert entry.adjusted_wr < 45.0


def test_small_sample_is_not_judged() -> None:
    form = _form({"Lux": _stats("Lux", games=2, wins=2)}, games=2, wins=2)
    report = diagnose_pool(form)
    assert report.entries[0].verdict == "표본 부족"


def test_average_champion_keeps() -> None:
    form = _form(
        {"Jinx": _stats("Jinx", games=10, wins=5)},  # 보정 50 ≈ 전체 50
        games=10,
        wins=5,
    )
    report = diagnose_pool(form)
    assert report.entries[0].verdict == "유지"


def test_focus_and_drop_shortcuts() -> None:
    form = _form(
        {
            "Ahri": _stats("Ahri", 10, 9),
            "Yasuo": _stats("Yasuo", 10, 1),
            "Jinx": _stats("Jinx", 10, 5),
        },
        games=30,
        wins=15,
    )
    report = diagnose_pool(form)
    assert {e.champion_name for e in report.focus} == {"Ahri"}
    assert {e.champion_name for e in report.drop} == {"Yasuo"}
