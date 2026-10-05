from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from PIL import Image

from lol_coach.gui.app import CoachApp
from lol_coach.gui.me_detail_mixin import MeDetailMixin
from lol_coach.gui.me_tab import MeTabMixin
from lol_coach.riot.client import aggregate_form
from lol_coach.riot.models import MatchSummary, PlayerProfile


class _Localizer:
    def champion(self, value: str) -> str:
        return value

    def mode(self, value: str) -> str:
        return value

    def role(self, value: str) -> str:
        return value


class _MeRenderHost(MeTabMixin, MeDetailMixin, ctk.CTkFrame):
    _clear = CoachApp._clear
    _keep_icon = CoachApp._keep_icon
    _lbl = CoachApp._lbl
    _sec = CoachApp._sec

    def __init__(self, master) -> None:
        ctk.CTkFrame.__init__(self, master, fg_color="transparent")

    def _should_auto_open_latest(self) -> bool:
        return False


def _match(index: int) -> MatchSummary:
    return MatchSummary(
        match_id=f"match-{index}",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MIDDLE",
        win=index % 2 == 0,
        kills=5,
        deaths=2,
        assists=7,
        cs=180,
        gold=10_000,
        damage_to_champs=20_000,
        vision_score=20,
        game_duration_s=1500,
        queue_id=420,
        game_end_timestamp=index,
    )


def test_me_match_history_uses_bounded_visible_slots_and_keeps_selection_identity(monkeypatch) -> None:
    ctk.set_widget_scaling(1.3)
    root = ctk.CTk()

    def fake_champion_ctk(_name: str, size: int):
        image = Image.new("RGB", (size, size), "#ffffff")
        return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))

    monkeypatch.setattr("lol_coach.gui.me_tab.champion_ctk", fake_champion_ctk)

    root.geometry("720x560")
    host = _MeRenderHost(root)
    host._icon_refs = []
    host._render_target = None
    host.loc = _Localizer()
    host._me_search_var = tk.StringVar(root, value="")
    host._me_queue_filter = None
    host._me_result_filter = True
    host._last_ranks = []
    profile = PlayerProfile("Player", "KR1", "puuid", "kr")
    form = aggregate_form(profile, [_match(i) for i in range(50)])
    host._me_form_full = form
    host.rank_lbl = ctk.CTkLabel(root, text="")
    host.status = ctk.CTkLabel(root, text="")
    host.me_matches = ctk.CTkScrollableFrame(root, width=420, height=300)
    host.me_detail = ctk.CTkScrollableFrame(root, width=420, height=300)
    host.me_champs = ctk.CTkScrollableFrame(root, width=420, height=150)
    host.me_matches.pack(fill="both", expand=True)

    try:
        MeTabMixin._render_me(host, form)
        root.update_idletasks()
        root.update()

        rows = host._me_match_rows
        assert rows is not None
        initial_slots = tuple(rows._slots)
        initial_icon_refs = len(host._icon_refs)
        viewport_rows = (host.me_matches._parent_canvas.winfo_height() // 60) + 1
        assert rows.slot_count <= viewport_rows + 4
        assert rows.row_count == 25
        assert rows.slot_count < rows.row_count
        assert len(host._me_match_btns) == len(rows.visible_indices)
        assert rows.winfo_y() > 0
        assert abs(float(rows._get_widget_scaling()) - 1.3) < 0.01
        assert host._me_match_btns[0][1].cget("image")

        def assert_visible_buttons() -> None:
            assert rows.visible_indices
            assert all(
                slot.winfo_ismapped() and slot._me_match_button.winfo_ismapped()
                for slot, _index in zip(
                    rows._slots[: len(rows.visible_indices)],
                    rows.visible_indices,
                    strict=True,
                )
            )
            assert len(host._me_match_btns) == len(rows.visible_indices)
            assert all(button.cget("text") for _match_id, button in host._me_match_btns)

        for fraction in (0.5, 1.0):
            host.me_matches._parent_canvas.yview_moveto(fraction)
            root.update_idletasks()
            root.update()
            assert_visible_buttons()

        assert rows.visible_indices[-1] == 24
        assert set(initial_slots).issubset(set(rows._slots))
        assert host._me_match_btns[-1][0] == "match-0"
        assert len(host._icon_refs) == initial_icon_refs

        shown: list[str] = []
        host._show_match_detail = lambda match: shown.append(match.match_id)
        host._me_match_btns[-1][1].invoke()
        assert shown == ["match-0"]

        MeDetailMixin._highlight_match_btn(host, "match-0")
        assert host._me_match_btns[-1][1].cget("border_width") == 1
    finally:
        root.destroy()
        ctk.set_widget_scaling(1.0)
