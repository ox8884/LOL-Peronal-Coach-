"""정찰 카드 렌더 + 게임 시작 후크 테스트."""

from __future__ import annotations

import importlib
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from lol_coach.analysis.scouting import (
    PlayerScout,
    ScoutChip,
    ScoutingReport,
)
from lol_coach.static.ddragon import DataDragon

live_mod = importlib.import_module("lol_coach.gui.live_mixin")


def _report() -> ScoutingReport:
    enemy = PlayerScout(
        summoner_name="위험한원딜",
        champion_id=22,  # Ashe
        team_id=200,
        chips=(
            ScoutChip(kind="danger", text="방금 패배 후 재큐 — 빡큐 위험"),
            ScoutChip(kind="cold", text="최근 5판 1승 — 폼 콜드"),
        ),
        sample_games=5,
    )
    ally = PlayerScout(
        summoner_name="우리탑",
        champion_id=86,  # Garen
        team_id=100,
        chips=(ScoutChip(kind="hot", text="최근 5판 4승 — 폼 핫"),),
        sample_games=5,
    )
    return ScoutingReport(enemy=(enemy,), ally=(ally,), scanned=2, skipped=0)


def test_scouting_card_bytes_valid_png() -> None:
    from lol_coach.gui.scouting_card import scouting_card_bytes

    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    data = scouting_card_bytes(_report(), dd)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(BytesIO(data)) as img:
        assert img.size[0] == 960
        assert img.size[1] > 300


def test_scouting_card_colors() -> None:
    from lol_coach.gui.scouting_card import render_scouting_card

    dd = DataDragon(language="ko_KR")
    dd.ensure_loaded()
    img = render_scouting_card(_report(), dd).convert("RGB")
    w, h = img.size
    px = img.load()

    def near(c: tuple, t: tuple, tol: int = 40) -> bool:
        return all(abs(a - b) <= tol for a, b in zip(c, t, strict=False))

    red = green = gold = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            c = px[x, y]
            if near(c, (224, 91, 91)):
                red += 1
            elif near(c, (76, 175, 125)):
                green += 1
            elif near(c, (200, 170, 110)):
                gold += 1
    assert red > 0  # danger 칩
    assert green > 0  # hot 칩
    assert gold > 0  # 액센트 바


def test_game_started_hands_off_to_scouting(monkeypatch) -> None:
    """_on_game_started가 정찰을 호출한다 (위임 계약)."""
    called: list = []
    app = SimpleNamespace(
        _game_start_label=lambda game: "칼바람·아수라장 · 내 챔피언 아리",
        _live_notification_blocked=False,
        _game_start_notify_on=lambda: False,
        status=SimpleNamespace(configure=lambda **kw: None),
        _push_summary=lambda title, lines: None,
        _start_game_end_watcher=lambda: None,
        _predict_game_start=lambda game: None,
        _scout_game_start=lambda game: called.append(game),
    )
    game = SimpleNamespace(game_id=1)
    live_mod.LiveMixin._on_game_started(app, game)
    assert called == [game]


def test_scout_game_start_toasts_headline(monkeypatch) -> None:
    """정찰 완료 시 토스트 + 디스코드 카드 경로."""

    class SyncThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    import threading as real_threading

    monkeypatch.setattr(real_threading, "Thread", SyncThread)

    from lol_coach.analysis import scouting as sc_mod

    report = _report()
    monkeypatch.setattr(sc_mod, "build_scouting_report", lambda *a, **k: report)
    monkeypatch.setattr(sc_mod, "scouting_headline", lambda r: "적 1명 빡큐·위험 신호")

    notifications: list = []
    cards: list = []
    app = SimpleNamespace(
        profile=SimpleNamespace(puuid="me"),
        riot=object(),
        after=lambda ms, fn: fn(),
        _notify=lambda msg, level="info", ms=3800: notifications.append(msg),
        _send_scouting_card=lambda r: cards.append(r),
    )
    game = SimpleNamespace(participants=[{"puuid": "p1"}])

    live_mod.LiveMixin._scout_game_start(app, game)
    assert notifications and "빡큐" in notifications[0]
    assert cards == [report]
