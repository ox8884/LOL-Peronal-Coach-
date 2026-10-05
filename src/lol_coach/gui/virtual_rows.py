"""Small viewport-only row renderer for CustomTkinter scroll hosts.

The host keeps the normal CustomTkinter scrollbar and canvas.  This component
only owns a bounded set of child slots and moves them over the logical row
coordinates as the canvas scrolls.
"""

from __future__ import annotations

import tkinter as tk
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

T = TypeVar("T")
RowHeight = int | Callable[[T], int]
RenderRow = Callable[[tk.Frame, T, int], None]
VisibleRows = Callable[[list[tuple[int, T, tk.Frame]]], None]


def visible_row_range(
    heights: Sequence[int],
    *,
    scroll_top: float,
    viewport_height: int,
    overscan: int = 2,
) -> tuple[int, int]:
    """Return the logical row interval needed for one viewport."""
    if not heights:
        return 0, 0

    offsets = [0]
    for height in heights:
        offsets.append(offsets[-1] + max(1, int(height)))
    top = max(0.0, float(scroll_top))
    bottom = top + max(1, int(viewport_height))
    first = min(len(heights) - 1, max(0, bisect_right(offsets, top) - 1))
    end = bisect_left(offsets, bottom)
    end = max(first + 1, min(len(heights), end))
    margin = max(0, int(overscan))
    return max(0, first - margin), min(len(heights), end + margin)


class VirtualRows(tk.Frame):
    """Render only the rows intersecting a scroll host's viewport.

    ``render_row`` receives a stable slot frame, the current item, and its
    logical index.  Consumers may reuse child widgets inside that slot; the
    slot itself is reused when the viewport moves.
    """

    def __init__(
        self,
        master: Any,
        *,
        row_height: RowHeight,
        render_row: RenderRow,
        scroll_host: Any | None = None,
        overscan: int = 2,
        on_visible_rows: VisibleRows | None = None,
    ) -> None:
        self._scroll_host = scroll_host or master
        super().__init__(master, bg=tk.Frame.cget(self._scroll_host, "bg"), highlightthickness=0)
        canvas = getattr(self._scroll_host, "_parent_canvas", None)
        if canvas is None:
            raise TypeError("VirtualRows requires a CTkScrollableFrame scroll host")
        self._scroll_canvas: Any = canvas
        self._scrollbar = getattr(self._scroll_host, "_scrollbar", None)
        self._original_yscrollcommand = self._scroll_canvas.cget("yscrollcommand")
        self._row_height = row_height
        self._render_row = render_row
        self._overscan = max(0, int(overscan))
        self._on_visible_rows = on_visible_rows
        self._items: tuple[Any, ...] = ()
        self._heights: tuple[int, ...] = ()
        self._offsets: tuple[int, ...] = (0,)
        self._slots: list[tk.Frame] = []
        self._active: dict[int, tk.Frame] = {}
        self._visible_indices: tuple[int, ...] = ()
        self._layout_scale = 0.0
        self._refresh_after: str | None = None
        self._scroll_canvas_configure_binding = self._scroll_canvas.bind(
            "<Configure>", self._on_canvas_configure, add="+"
        )
        # Register on this component so reloading the list releases the callback.
        self._scroll_canvas.configure(yscrollcommand=self.register(self._on_scroll))
        self.grid_columnconfigure(0, weight=1)
        self.grid_propagate(False)

    def _get_widget_scaling(self) -> float:
        return float(self._scroll_host._get_widget_scaling())

    @property
    def slot_count(self) -> int:
        return len(self._slots)

    @property
    def row_count(self) -> int:
        return len(self._items)

    @property
    def total_height(self) -> int:
        return self._offsets[-1]

    @property
    def visible_indices(self) -> tuple[int, ...]:
        return self._visible_indices

    def set_items(self, items: Sequence[T]) -> None:
        self._items = tuple(items)
        heights: list[int] = []
        for item in self._items:
            height = self._row_height(item) if callable(self._row_height) else self._row_height
            heights.append(max(1, int(height)))
        self._heights = tuple(heights)
        offsets = [0]
        for height in self._heights:
            offsets.append(offsets[-1] + height)
        self._offsets = tuple(offsets)
        self.configure(height=max(1, round(self.total_height * self._get_widget_scaling())))
        self._visible_indices = ()
        self._active = {}
        self._schedule_refresh()

    def refresh(self) -> None:
        """Refresh slot placement after a geometry or scroll change."""
        self._refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_after is not None:
            try:
                self.after_cancel(self._refresh_after)
            except Exception:
                pass
        try:
            self._refresh_after = self.after_idle(self._refresh)
        except Exception:
            self._refresh_after = None
            self._refresh()

    def _on_canvas_configure(self, _event: Any) -> None:
        self._schedule_refresh()

    def _on_scroll(self, first: str | float, last: str | float) -> None:
        self._refresh()
        try:
            if self._scrollbar is not None:
                self._scrollbar.set(first, last)
        except Exception:
            pass

    def _refresh(self) -> None:
        if self._refresh_after is not None:
            self.after_cancel(self._refresh_after)
        self._refresh_after = None
        if not self.winfo_exists():
            return
        if not self._items:
            for slot in self._slots:
                slot.place_forget()
            self._active = {}
            self._visible_indices = ()
            self._notify_visible([])
            return

        scale = max(0.01, float(self._get_widget_scaling()))
        viewport_height = max(1, int(round(self._scroll_canvas.winfo_height() / scale)))
        canvas_top = float(self._scroll_canvas.canvasy(0))
        component_top = float(self.winfo_y())
        scroll_top = max(0.0, (canvas_top - component_top) / scale)
        start, end = visible_row_range(
            self._heights,
            scroll_top=scroll_top,
            viewport_height=viewport_height,
            overscan=self._overscan,
        )
        indices = tuple(range(start, end))
        scale_changed = scale != self._layout_scale
        if indices == self._visible_indices and not scale_changed:
            return
        if scale_changed:
            self.configure(height=max(1, round(self.total_height * scale)))
            self._layout_scale = scale
        kept = {index: self._active[index] for index in indices if index in self._active}
        free = [slot for slot in self._slots if slot not in kept.values()]
        for index in indices:
            if index in kept:
                if scale_changed:
                    kept[index].configure(height=round(self._heights[index] * scale))
                    kept[index].place(y=round(self._offsets[index] * scale))
                continue
            if free:
                slot = free.pop(0)
            else:
                slot = tk.Frame(self, bg=self.cget("bg"), highlightthickness=0)
                slot.grid_propagate(False)
            kept[index] = slot
            slot.configure(height=round(self._heights[index] * scale))
            slot.place(
                x=0,
                y=round(self._offsets[index] * scale),
                relwidth=1,
            )
            self._render_row(slot, self._items[index], index)
        for slot in free:
            slot.place_forget()
        self._active = kept
        self._slots = [kept[index] for index in indices] + free
        self._visible_indices = indices
        self._notify_visible(
            [
                (index, self._items[index], slot)
                for slot, index in zip(self._slots, indices, strict=False)
            ]
        )

    def _notify_visible(self, rows: list[tuple[int, T, tk.Frame]]) -> None:
        if self._on_visible_rows is not None:
            self._on_visible_rows(rows)

    def destroy(self) -> None:
        try:
            if self._refresh_after is not None:
                self.after_cancel(self._refresh_after)
                self._refresh_after = None
            if self._scroll_canvas_configure_binding:
                self._scroll_canvas.unbind("<Configure>", self._scroll_canvas_configure_binding)
            self._scroll_canvas.configure(yscrollcommand=self._original_yscrollcommand)
        except Exception:
            pass
        super().destroy()
