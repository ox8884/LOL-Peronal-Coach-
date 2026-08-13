"""승패 예측 모델·저장소 테스트."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lol_coach.analysis.prediction import (
    Prediction,
    add_prediction,
    consume_prediction,
    load_predictions,
    predict_game,
)
from lol_coach.static.ddragon import DataDragon


@pytest.fixture(scope="module")
def dd() -> DataDragon:
    d = DataDragon(language="ko_KR")
    d.ensure_loaded()
    return d


def _ids_by_tag(dd: DataDragon, tag: str, n: int) -> list[int]:
    out: list[int] = []
    for cid, ch in (getattr(dd, "_champions_by_id", {}) or {}).items():
        if tag in (ch.get("tags") or []):
            out.append(int(cid))
        if len(out) >= n:
            break
    return out


def _roster(
    dd: DataDragon,
    *,
    tanks: int = 0,
    fighters: int = 0,
    mages: int = 0,
    marksmen: int = 0,
    supports: int = 0,
    assassins: int = 0,
) -> list[int]:
    ids: list[int] = []
    for tag, n in (
        ("Tank", tanks),
        ("Fighter", fighters),
        ("Mage", mages),
        ("Marksman", marksmen),
        ("Support", supports),
        ("Assassin", assassins),
    ):
        ids.extend(_ids_by_tag(dd, tag, n))
    return ids


def _participants(ally: list[int], enemy: list[int]) -> list[dict]:
    out: list[dict] = []
    for cid in ally:
        out.append({"championId": cid, "teamId": 100})
    for cid in enemy:
        out.append({"championId": cid, "teamId": 200})
    return out


# ── 모델 ──────────────────────────────────────────────────


def test_mirror_comps_are_even(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=1, fighters=1, mages=2, marksmen=1)
    enemy = _roster(dd, tanks=1, fighters=1, mages=2, marksmen=1)
    pred = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=None,
        form_sample=0,
    )
    assert pred.win_prob == 50


def test_frontline_advantage_shifts_probability(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=2, fighters=1, mages=1, marksmen=1)
    enemy = _roster(dd, tanks=0, fighters=0, mages=3, marksmen=2)
    pred = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=None,
        form_sample=0,
    )
    assert pred.win_prob > 50
    assert any("앞라인" in r for r in pred.reasons)


def test_full_ap_enemy_is_flagged(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=1, mages=2, marksmen=2)
    enemy = _roster(dd, mages=4, supports=1)
    pred = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=None,
        form_sample=0,
    )
    assert any("풀 AP" in r for r in pred.reasons)


def test_hot_form_raises_probability_and_is_reported(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=1, mages=2, marksmen=2)
    enemy = _roster(dd, tanks=1, mages=2, marksmen=2)
    base = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=None,
        form_sample=0,
    )
    hot = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=70.0,
        form_sample=10,
    )
    assert hot.win_prob > base.win_prob
    assert hot.form_winrate == 70.0
    assert hot.sample_games == 10
    assert any("폼" in r for r in hot.reasons)


def test_small_form_sample_is_ignored(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=1, mages=2, marksmen=2)
    enemy = _roster(dd, tanks=1, mages=2, marksmen=2)
    pred = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=90.0,
        form_sample=4,
    )
    assert pred.form_winrate is None
    assert pred.sample_games == 0
    assert not any("폼" in r for r in pred.reasons)


def test_probability_is_clamped(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=3, fighters=2)
    enemy = _roster(dd, mages=4, supports=1)
    pred = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=100.0,
        form_sample=50,
    )
    assert 20 <= pred.win_prob <= 80


def test_prediction_is_deterministic(dd: DataDragon) -> None:
    ally = _roster(dd, tanks=2, mages=2, marksmen=1)
    enemy = _roster(dd, tanks=0, mages=3, marksmen=2)
    a = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=60.0,
        form_sample=8,
    )
    b = predict_game(
        dd,
        my_champ_id=ally[0],
        my_team_id=100,
        participants=_participants(ally, enemy),
        form_winrate=60.0,
        form_sample=8,
    )
    assert a == b


# ── 저장소 ────────────────────────────────────────────────


def _pred(
    *,
    ally: tuple[int, ...] = (1, 2, 3),
    enemy: tuple[int, ...] = (4, 5, 6),
    prob: int = 55,
    created_at_ms: int | None = None,
) -> Prediction:
    return Prediction(
        created_at_ms=created_at_ms or int(time.time() * 1000),
        my_champ_id=ally[0],
        ally_roster=ally,
        enemy_roster=enemy,
        win_prob=prob,
        reasons=("테스트 근거",),
    )


def test_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    add_prediction(path, _pred(prob=61))
    loaded = load_predictions(path)
    assert len(loaded) == 1
    assert loaded[0].win_prob == 61
    assert loaded[0].signature == ((1, 2, 3), (4, 5, 6))


def test_consume_matches_by_roster_and_removes(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    add_prediction(path, _pred(ally=(1, 2, 3), enemy=(4, 5, 6)))
    add_prediction(path, _pred(ally=(7, 8, 9), enemy=(10, 11, 12)))

    got = consume_prediction(path, ally_roster=(1, 2, 3), enemy_roster=(4, 5, 6))
    assert got is not None and got.win_prob == 55
    # 소비된 건 사라진다
    remaining = load_predictions(path)
    assert len(remaining) == 1
    assert remaining[0].signature == ((7, 8, 9), (10, 11, 12))
    # 같은 로스터 재소비 → 없음
    assert consume_prediction(path, ally_roster=(1, 2, 3), enemy_roster=(4, 5, 6)) is None


def test_consume_wrong_roster_returns_none_and_keeps(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    add_prediction(path, _pred(ally=(1, 2, 3), enemy=(4, 5, 6)))
    assert consume_prediction(path, ally_roster=(9, 9, 9), enemy_roster=(4, 5, 6)) is None
    assert len(load_predictions(path)) == 1


def test_add_prunes_stale(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    old = int(time.time() * 1000) - 7 * 60 * 60 * 1000
    add_prediction(path, _pred(created_at_ms=old))
    add_prediction(path, _pred(ally=(7, 8, 9), enemy=(10, 11, 12)))
    remaining = load_predictions(path)
    assert len(remaining) == 1
    assert remaining[0].signature == ((7, 8, 9), (10, 11, 12))


def test_load_corrupt_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_predictions(path) == []
    path.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    assert load_predictions(path) == []
