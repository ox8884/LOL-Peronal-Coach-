"""아수라장 증강 실시간 판정 — 카드 렌더 · 자동입력 갱신 · 토스트/전송 흐름."""

from __future__ import annotations

import importlib
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from lol_coach.analysis.aram_mayhem import AugmentPick, AugmentRecord, MayhemAdvice
from lol_coach.static.augment_catalog import AugmentCatalog
from lol_coach.static.blitz_aram import BlitzAramCatalog
from lol_coach.static.ddragon import DataDragon

aram_mod = importlib.import_module("lol_coach.gui.aram_tab")


# ── _next_augment_fill (리롤 자동입력 갱신) ───────────────────


def test_tier_chip_label_distinguishes_general_and_champ() -> None:
    rec = SimpleNamespace(
        name_en="Warlock Juicebox",
        name_ko="마도사의 주스 상자",
        fallback_tier="S",
        rarity="gold",
    )
    general = AugmentPick(record=rec, tier="S", score=1, reason="전체 메타 S등급 · 지금 챔프 전용 순위는 아님")
    champ = AugmentPick(record=rec, tier="A", score=2, reason="Blitz.gg 골드 증강 1순위")
    assert aram_mod._tier_chip_label(general) == "일반 S"
    assert aram_mod._tier_chip_label(champ) == "이 챔프 A"


def test_next_fill_empty_input() -> None:
    assert aram_mod._next_augment_fill("", None, ["A", "B"]) == "A, B"


def test_next_fill_reroll_updates_previous_auto_fill() -> None:
    assert aram_mod._next_augment_fill("A, B", ("A", "B"), ["C", "D"]) == "C, D"


def test_next_fill_manual_edit_not_overwritten() -> None:
    assert aram_mod._next_augment_fill("A, B, 내가 쓴 것", ("A", "B"), ["C"]) is None


def test_next_fill_empty_augs_returns_none() -> None:
    assert aram_mod._next_augment_fill("", ("A",), []) is None


# ── 판정 카드 렌더 ──────────────────────────────────────────


def _record(name: str, rarity: str, tier: str) -> AugmentRecord:
    return AugmentRecord(
        id=f"test:{name}",
        name_en=name,
        name_ko=name,
        description_ko="테스트 효과 설명",
        rarity=rarity,
        fallback_tier=tier,
        aliases=(),
        image_candidates=(),
        sources=(),
        archetype_prefer=(),
        archetype_avoid=(),
    )


def _build_advice() -> MayhemAdvice:
    top = [
        AugmentPick(
            record=_record("Jeweled Gauntlet", "prismatic", "S"),
            tier="S",
            score=300.0,
            reason="프리즘 S티어",
        ),
        AugmentPick(
            record=_record("Back To Basics", "gold", "A"),
            tier="A",
            score=200.0,
            reason="골드 A티어",
        ),
    ]
    avoid = [
        AugmentPick(
            record=_record("집중 공격", "silver", "B"),
            tier="B",
            score=0.0,
            reason="실버 B티어 · 주의",
        )
    ]
    return MayhemAdvice(
        champ_ko="오리아나",
        patch="15.16",
        top_augments=top,
        avoid_augments=avoid,
    )


def test_augment_card_bytes_valid_png() -> None:
    from lol_coach.gui.augment_card import augment_card_bytes

    data = augment_card_bytes(_build_advice())
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(BytesIO(data)) as img:
        assert img.size[0] == 960
        assert img.size[1] > 300


def test_augment_card_empty_advice_renders() -> None:
    from lol_coach.gui.augment_card import augment_card_bytes

    data = augment_card_bytes(
        MayhemAdvice(champ_ko="아리", patch="", top_augments=[], avoid_augments=[])
    )
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


# ── 실시간 판정 흐름 (스레드 동기화 실행) ────────────────────


def _synced_trio() -> tuple[str, list[str]] | None:
    """카탈로그와 Blitz 티어가 모두 통과하는 챔피언+증강 3개를 찾는다."""
    catalog = AugmentCatalog()
    blitz = BlitzAramCatalog.packaged()
    for build in blitz.records:
        names = [n for tier in build.augment_tiers.values() for n in tier][:3]
        if not names:
            continue
        _valid, unknowns, _dup = catalog.resolve_many(names)
        if _valid and not unknowns:
            return build.champion, names
    return None


class SyncThread:
    """threading.Thread 대체 — start()에서 즉시 실행 (UI 마샬링 시뮬레이션)."""

    def __init__(self, target: Any, daemon: Any = None) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


def test_verdict_notifies_top_pick_and_sends_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trio = _synced_trio()
    if trio is None:
        pytest.skip("패키지 카탈로그에서 동기화된 증강 쌍을 찾지 못함")
    champ_key, augs = trio

    from lol_coach.analysis.aram_mayhem import MayhemCoach

    monkeypatch.setattr(aram_mod.threading, "Thread", SyncThread)

    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    champ_ko = dd.resolve_champion(champ_key)["name"]
    mayhem = MayhemCoach(dd)

    notifications: list[str] = []
    cards: list[MayhemAdvice] = []

    app = SimpleNamespace(
        aram_champ_var=SimpleNamespace(get=lambda: champ_ko),
        mayhem=mayhem,
        after=lambda ms, fn: fn(),
        _notify=lambda msg, level="info", ms=3800, **_k: notifications.append(msg),
        _send_augment_card=lambda adv: cards.append(adv),
    )
    app._resolve = lambda raw: (champ_key, champ_ko)
    app._parse_offered_augments = lambda raw: aram_mod.AramTabMixin._parse_offered_augments(
        app, raw
    )

    aram_mod.AramTabMixin._notify_augment_verdict(app, augs)

    assert notifications, "판정 토스트가 없습니다"
    assert any("증강 판정" in n for n in notifications), notifications
    assert cards, "판정 카드가 전달되지 않았습니다"
    assert cards[0].top_augments, "1순위 판정이 비어 있습니다"
    offered = {n.strip() for n in augs}
    assert cards[0].top_augments[0].name_ko in offered


def test_finish_offered_read_blank_asks_borderless() -> None:
    from lol_coach.analysis.augment_ocr import OfferedRead

    notes: list[str] = []
    summaries: list[tuple[str, list[str]]] = []
    status: list[str] = []
    app = SimpleNamespace(
        _notify=lambda msg, level="info", ms=3800, **_k: notes.append(msg),
        _push_summary=lambda title, lines: summaries.append((title, list(lines))),
        aram_status=SimpleNamespace(configure=lambda **kw: status.append(kw.get("text", ""))),
    )
    aram_mod.AramTabMixin._finish_offered_read(app, OfferedRead([], "blank"))
    assert notes and "테두리 없는 창" in notes[0]
    assert summaries and summaries[0][0] == "증강 인식 실패"
    assert status == ["증강 인식 실패"]


def test_finish_offered_read_partial_applies_two() -> None:
    from lol_coach.analysis.augment_ocr import OfferedRead

    notes: list[str] = []
    applied: list[list[str]] = []
    app = SimpleNamespace(
        _notify=lambda msg, level="info", ms=3800, **_k: notes.append(msg),
        _push_summary=lambda title, lines: None,
        aram_status=SimpleNamespace(configure=lambda **kw: None),
        _apply_offered_augments=lambda names: applied.append(list(names)),
    )
    aram_mod.AramTabMixin._finish_offered_read(
        app, OfferedRead(["보석 건틀릿", "기본으로"], "partial")
    )
    assert applied == [["보석 건틀릿", "기본으로"]]
    assert notes and "2장만 읽음" in notes[0]


def test_finish_offered_read_weak_match_does_not_apply() -> None:
    from lol_coach.analysis.augment_ocr import OfferedRead

    notes: list[str] = []
    applied: list[list[str]] = []
    app = SimpleNamespace(
        _notify=lambda msg, level="info", ms=3800, **_k: notes.append(msg),
        _push_summary=lambda title, lines: None,
        aram_status=SimpleNamespace(configure=lambda **kw: None),
        _apply_offered_augments=lambda names: applied.append(list(names)),
    )
    aram_mod.AramTabMixin._finish_offered_read(
        app, OfferedRead(["보석 건틀릿"], "weak_match")
    )
    assert applied == []
    assert notes and "앱 추천" in notes[0]


def test_verdict_skips_when_no_champ() -> None:
    app = SimpleNamespace(aram_champ_var=SimpleNamespace(get=lambda: ""))
    aram_mod.AramTabMixin._notify_augment_verdict(app, ["Jeweled Gauntlet"])
    # 예외 없이 즉시 반환


def test_verdict_skips_unknown_augments(monkeypatch: pytest.MonkeyPatch) -> None:
    from lol_coach.analysis.aram_mayhem import MayhemCoach

    monkeypatch.setattr(aram_mod.threading, "Thread", SyncThread)
    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    notifications: list[str] = []
    cards: list[MayhemAdvice] = []
    app = SimpleNamespace(
        aram_champ_var=SimpleNamespace(get=lambda: "아리"),
        mayhem=MayhemCoach(dd),
        after=lambda ms, fn: fn(),
        _notify=lambda msg, level="info", ms=3800, **_k: notifications.append(msg),
        _send_augment_card=lambda adv: cards.append(adv),
    )
    app._resolve = lambda raw: ("Ahri", "아리")
    app._parse_offered_augments = lambda raw: aram_mod.AramTabMixin._parse_offered_augments(
        app, raw
    )

    aram_mod.AramTabMixin._notify_augment_verdict(app, ["알 수 없는 증강 X"])

    assert notifications == []
    assert cards == []
