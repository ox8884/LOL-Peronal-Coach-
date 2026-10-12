"""내 전적 복기 패널 — 네이티브 창 수·플레이스홀더 교체·칼바람 오브젝트·증강 워커."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import customtkinter as ctk
from PIL import Image

from lol_coach.gui import me_detail_mixin as mod
from lol_coach.gui.app import CoachApp
from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.riot.models import MatchObjectives, MatchPlayer, MatchSummary
from lol_coach.static.mayhem_augments import AugmentMeta

_Thread = threading.Thread  # mod.threading 은 전역 모듈 — 패치 전 원본 보관


class _Loc:
    def ensure_loaded(self) -> None:
        pass

    def champion(self, v: str) -> str:
        return v

    role = mode = champion


class _Host(MeDetailMixin, ctk.CTkFrame):
    _clear = CoachApp._clear
    _keep_icon = CoachApp._keep_icon
    _lbl = CoachApp._lbl
    _sec = CoachApp._sec
    _row_frame = CoachApp._row_frame


def _fake_ctk(_key, size):
    im = Image.new("RGB", (size, size), "#888888")
    return ctk.CTkImage(light_image=im, dark_image=im, size=(size, size))


def _match(queue_id: int = 420) -> MatchSummary:
    items = [1001, 3020, 3089, 3157, 3135, 3165, 3340]

    def player(i: int) -> MatchPlayer:
        return MatchPlayer(
            "Ahri", 103, "MIDDLE", 100, 1, 2, 3, 100, 9000, 15000, 20, 15,
            items=list(items), riot_id=f"p{i}#KR1", is_me=i == 0,
        )

    m = MatchSummary(
        match_id="KR_1", champion_name="Ahri", champion_id=103, role="MIDDLE",
        lane="MIDDLE", win=True, kills=5, deaths=2, assists=7, cs=180, gold=10000,
        damage_to_champs=20000, vision_score=20, game_duration_s=1500,
        queue_id=queue_id, game_end_timestamp=1,
    )
    m.items = list(items)
    m.summoner_spells = [4, 14]
    m.primary_rune = 8112
    m.ally_team = [player(i) for i in range(5)]
    m.enemy_team = [player(i) for i in range(5, 10)]
    m.obj = MatchObjectives()
    return m


def _host(monkeypatch, root, m: MatchSummary) -> tuple[_Host, list]:
    workers: list = []
    monkeypatch.setattr(mod, "champion_ctk", _fake_ctk)
    monkeypatch.setattr(mod, "item_ctk", _fake_ctk)
    monkeypatch.setattr(mod, "item_pil", lambda i, size: Image.new("RGB", (size, size)))
    # 합성 이미지 캐시의 CTkImage는 테스트마다 새 Tk 루트에 묶인다
    monkeypatch.setattr(mod, "_item_strip_mem", {})
    monkeypatch.setattr(
        mod.threading, "Thread",
        lambda target, args=(), **kw: SimpleNamespace(start=lambda: workers.append((target, args))),
    )
    host = _Host(root)
    host._icon_refs = []
    host._render_target = None
    host.loc = _Loc()
    host.dd = SimpleNamespace(
        item_names=lambda ids: [str(i) for i in ids],
        spell_name=lambda _s: "점멸",
        rune_name=lambda _r: "감전",
    )
    host.form = SimpleNamespace(matches=[m], provenance=None)
    host.status = ctk.CTkLabel(root, text="")
    host._notify = lambda *a, **k: None
    host._push_summary = lambda *a, **k: None
    host._ai_key = lambda: ""
    host._match_index_of = lambda _m: 0
    host.me_detail = ctk.CTkScrollableFrame(root, width=480, height=400)
    host.me_detail.pack()
    return host, workers


def _count(w) -> int:
    return sum(1 + _count(c) for c in w.winfo_children())


def _texts(host) -> list[str]:
    out = []
    for w in host.me_detail.winfo_children():
        try:
            out.append(str(w.cget("text")))
        except Exception:
            pass
    return out


def test_match_detail_native_window_budget_and_placeholders(monkeypatch) -> None:
    root = ctk.CTk()
    m = _match()
    host, _workers = _host(monkeypatch, root, m)
    try:
        host._show_match_detail(m)
        root.update()
        # 이전 구현은 같은 경기에서 402개 — 선수 줄마다 아이템 칸·프레임이 창을 만들었다
        assert _count(host.me_detail) < 150
        sr_row = next(
            w.grid_info()["row"] for w in host.me_detail.winfo_children()
            if _texts_of(w) == "주문 불러오는 중…"
        )
        skill_row = next(
            w.grid_info()["row"] for w in host.me_detail.winfo_children()
            if _texts_of(w) == "스킬 불러오는 중…"
        )
        gen = host._me_detail_gen
        host._apply_skill_order(skill_row - 1, ["Q", "W", "E"], gen=gen)
        pil = Image.new("RGB", (28, 28))
        host._apply_spells_rune(sr_row, [(4, pil), (14, pil)], pil, [4, 14], 8112, gen=gen)
        root.update()
        texts = _texts(host)
        assert "스킬 불러오는 중…" not in texts and "Q W E" in texts
        assert "주문 불러오는 중…" not in texts
        # 주문 칸이 제목 행과 겹치지 않고 플레이스홀더 자리에 들어간다
        assert len(host.me_detail.grid_slaves(row=sr_row)) == 1
    finally:
        root.destroy()


def _texts_of(w) -> str:
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def test_aram_match_hides_rift_objectives(monkeypatch) -> None:
    root = ctk.CTk()
    try:
        for queue_id, rift in ((420, True), (450, False), (2400, False)):
            m = _match(queue_id)
            host, _workers = _host(monkeypatch, root, m)
            host._show_match_detail(m)
            joined = " ".join(_texts(host))
            assert ("드래곤" in joined) is rift
            assert ("와드" in joined) is rift
            assert "포탑" in joined
            host.destroy()
    finally:
        root.destroy()


def test_augments_load_off_ui_thread_names_first(monkeypatch) -> None:
    root = ctk.CTk()
    m = _match(2400)
    m.augment_ids = [1, 2]
    host, workers = _host(monkeypatch, root, m)
    lcu_threads: list = []

    class _LCU:
        @staticmethod
        def is_client_running() -> bool:
            lcu_threads.append(threading.current_thread())
            return True

    metas = [AugmentMeta(1, "마법 미사일", "gold", "/a.png"), AugmentMeta(2, "속도", "", "")]
    monkeypatch.setattr(mod, "resolve_display", lambda ids, names: metas)
    monkeypatch.setattr("lol_coach.lcu.LCUClient", _LCU)
    icon = Image.new("RGB", (30, 30))
    monkeypatch.setattr(mod, "_augment_image", lambda meta, lcu=None: icon if lcu else None)
    try:
        host._show_match_detail(m)
        assert lcu_threads == [], "UI 스레드에서 LCU 연결을 확인하면 안 됩니다"
        assert "증강 불러오는 중…" in _texts(host)
        target, args = next(w for w in workers if getattr(w[0], "__name__", "") == "_load_augments")
        posted: list = []
        host.after = lambda _ms, fn: posted.append(fn)  # mainloop 없이 워커 → UI 전달을 흉내
        worker = _Thread(target=target, args=args)
        worker.start()
        worker.join()
        assert lcu_threads and lcu_threads[0] is not threading.main_thread()
        posted.pop(0)()  # 이름 칩 먼저
        assert [c.cget("text") for c in host._me_aug_chips] == ["마법 미사일", "속도"]
        assert not host._me_aug_chips[0].cget("image")
        for fn in posted:
            fn()
        root.update()
        assert "증강 불러오는 중…" not in _texts(host)
        chips = host._me_aug_chips
        assert [c.cget("text") for c in chips] == ["마법 미사일", "속도"]
        assert chips[0].cget("image") and chips[1].cget("image")
    finally:
        root.destroy()


def test_aug_chip_text_shows_champion_tier_when_known() -> None:
    from types import SimpleNamespace

    from lol_coach.gui.me_detail_mixin import _aug_chip_text

    meta = SimpleNamespace(id=1026, name="속전속결")
    assert _aug_chip_text(meta, {1026: 1}) == "속전속결\n이 챔프 1티어"
    assert _aug_chip_text(meta, {}) == "속전속결"
    assert _aug_chip_text(SimpleNamespace(id=0, name="Typhoon"), {1026: 1}) == "Typhoon"
