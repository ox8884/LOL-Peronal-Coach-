from __future__ import annotations

import customtkinter as ctk
from PIL import Image

from lol_coach.gui.app import CoachApp
from lol_coach.gui.tierlist_mixin import TierListMixin


class _TierRenderHost(TierListMixin, ctk.CTkFrame):
    _clear = CoachApp._clear
    _keep_icon = CoachApp._keep_icon

    def __init__(self, master) -> None:
        ctk.CTkFrame.__init__(self, master, fg_color="transparent")


def test_tierlist_173_champions_use_bounded_reusable_rows(monkeypatch) -> None:
    root = ctk.CTk()

    from lol_coach.gui import tierlist_mixin

    def fake_champion_ctk(_key: str, size: int):
        image = Image.new("RGB", (size, size), "#ffffff")
        return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))

    monkeypatch.setattr(tierlist_mixin, "champion_ctk", fake_champion_ctk)
    root.geometry("900x560")
    host = _TierRenderHost(root)
    host._icon_refs = []
    host._render_target = None
    host._tierlist_meta = ctk.CTkLabel(root, text="")
    host._tierlist_status = ctk.CTkLabel(root, text="")
    host._tierlist_body = ctk.CTkScrollableFrame(root, width=820, height=360)
    host._tierlist_body.pack(fill="both", expand=True)
    entries = [(index % 5 + 1, f"챔프 {index}", f"Champ{index}") for index in range(173)]

    try:
        TierListMixin._render_tierlist(host, "16.19", "2026-10-04", entries)
        root.update_idletasks()
        root.update()

        rows = host._tierlist_rows
        assert rows is not None
        initial_slots = tuple(rows._slots)
        initial_children = [child for slot in initial_slots for child in slot.winfo_children()]
        initial_icon_refs = len(host._icon_refs)
        viewport_rows = host._tierlist_body._parent_canvas.winfo_height()
        assert rows.row_count < len(entries)
        assert rows.slot_count <= (viewport_rows // 68) + 4
        assert rows.slot_count < len(entries)

        host._tierlist_body._parent_canvas.yview_moveto(1.0)
        root.update_idletasks()
        root.update()

        assert rows.visible_indices[-1] == rows.row_count - 1
        assert set(rows._slots).issubset(initial_slots)
        assert rows.slot_count < len(entries)
        assert len(host._icon_refs) == initial_icon_refs
        assert all(child.winfo_exists() for child in initial_children), "스크롤마다 카드 위젯을 파괴하지 않습니다"
        for scale in (1.3, 0.9, 1.0):
            ctk.set_widget_scaling(scale)
            root.after(100, root.quit)
            root.mainloop()
            root.update_idletasks()
            assert rows.winfo_height() == round(rows.total_height * scale)
            assert int(rows.cget("height")) == round(rows.total_height * scale)
    finally:
        root.destroy()
        ctk.set_widget_scaling(1.0)
