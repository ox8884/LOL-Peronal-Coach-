from __future__ import annotations

from lol_coach.gui.tierlist_mixin import _build_tierlist_rows
from lol_coach.gui.virtual_rows import visible_row_range


def test_visible_row_range_only_includes_viewport_and_overscan() -> None:
    heights = (60,) * 50

    assert visible_row_range(heights, scroll_top=0, viewport_height=180, overscan=2) == (
        0,
        5,
    )
    assert visible_row_range(heights, scroll_top=600, viewport_height=180, overscan=2) == (
        8,
        15,
    )


def test_tierlist_rows_pack_champions_without_creating_one_row_per_champion() -> None:
    entries = [(tier, f"챔프 {i}", f"Champ{i}") for i, tier in enumerate([1] * 40 + [2] * 40)]

    rows = _build_tierlist_rows(entries, columns=9)
    chip_rows = [row[2] for row in rows if row[0] == "chips"]

    assert sum(len(group) for group in chip_rows) == len(entries)
    assert all(len(group) <= 9 for group in chip_rows)
    assert len(rows) < len(entries)
    assert [row[1] for row in rows if row[0] == "header"] == [1, 2]


def test_virtual_rows_reuses_bounded_slots_with_real_tk() -> None:
    import customtkinter as ctk

    root = ctk.CTk()

    from lol_coach.gui.virtual_rows import VirtualRows

    root.geometry("320x220")
    host = ctk.CTkScrollableFrame(root, width=300, height=180)
    host.pack(fill="both", expand=True)
    configured_height = host._parent_canvas.cget("height")
    rendered: list[tuple[int, int]] = []

    def render(slot, item: int, index: int) -> None:
        label = getattr(slot, "_test_label", None)
        if label is None:
            label = ctk.CTkLabel(slot, text="")
            label.grid(row=0, column=0, sticky="ew")
            slot.grid_columnconfigure(0, weight=1)
            slot._test_label = label
        label.configure(text=str(item))
        rendered.append((index, item))

    rows = VirtualRows(
        host,
        row_height=40,
        render_row=render,
        overscan=1,
    )
    rows.grid(row=0, column=0, sticky="ew")
    rows.set_items(list(range(50)))
    root.update_idletasks()
    root.update()

    try:
        assert host._parent_canvas.cget("height") == configured_height, "논리 목록 높이로 실제 스크롤 창 높이를 덮어쓰면 안 됩니다"
        initial_slots = tuple(rows._slots)
        viewport_rows = (host._parent_canvas.winfo_height() + 39) // 40
        assert rows.slot_count <= viewport_rows + 2
        assert rows.slot_count < 50

        before = dict(rows._active)
        rendered.clear()
        host._parent_canvas.yview_moveto(80 / rows.total_height)
        root.update()
        overlap = set(before) & set(rows._active)
        assert overlap
        assert all(rows._active[index] is before[index] for index in overlap)
        assert not (overlap & {index for index, _ in rendered}), "남아 있는 행을 다시 그리지 않습니다"
        allocated_slots = tuple(rows._slots)

        host._parent_canvas.yview_moveto(1.0)
        root.update_idletasks()
        root.update()

        assert rows.visible_indices[-1] == 49
        assert rows.slot_count <= viewport_rows + 2
        assert set(initial_slots).issubset(rows._slots)
        assert set(rows._slots).issubset(allocated_slots)
        assert any(index >= 45 for index, _item in rendered)
        ctk.set_widget_scaling(1.3)
        root.update()
        for index, slot in rows._active.items():
            assert slot.winfo_height() == 52
            assert slot.winfo_y() == round(index * 40 * 1.3)
        assert int(host._parent_canvas.cget("height")) == round(int(configured_height) * 1.3)
        rows.set_items([])
        root.update()
        assert rows.visible_indices == ()
        assert not any(slot.winfo_ismapped() for slot in rows._slots)
        callback = host._parent_canvas.cget("yscrollcommand")
        rows.destroy()
        assert not root.tk.call("info", "commands", callback), "목록 재로드 후 canvas 콜백이 목록을 보유하면 안 됩니다"
    finally:
        root.destroy()
        ctk.set_widget_scaling(1.0)
