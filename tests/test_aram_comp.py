"""ARAM 조합 태그 요약 테스트."""

from __future__ import annotations

from lol_coach.analysis.aram_comp import analyze_aram_comp


class _FakeDD:
    def ensure_loaded(self) -> None:
        return None

    def __init__(self) -> None:
        self._champions_by_id = {
            1: {"id": "Ahri", "name": "아리", "tags": ["Mage", "Assassin"]},
            2: {"id": "Malphite", "name": "말파이트", "tags": ["Tank"]},
            3: {"id": "Zed", "name": "제드", "tags": ["Assassin"]},
            4: {"id": "Talon", "name": "탈론", "tags": ["Assassin"]},
            5: {"id": "Lux", "name": "럭스", "tags": ["Mage", "Support"]},
        }


def test_enemy_assassins_threat() -> None:
    rep = analyze_aram_comp(
        _FakeDD(),  # type: ignore[arg-type]
        allies=[("Ahri", "아리"), ("Malphite", "말파이트")],
        enemies=[("Zed", "제드"), ("Talon", "탈론"), ("Lux", "럭스")],
        my_key="Ahri",
    )
    texts = " ".join(x.text for x in rep.lines)
    assert "암살" in texts
    assert any(x.kind == "threat" for x in rep.lines)


def test_empty_still_has_note() -> None:
    rep = analyze_aram_comp(
        _FakeDD(),  # type: ignore[arg-type]
        allies=[],
        enemies=[],
    )
    assert rep.lines
