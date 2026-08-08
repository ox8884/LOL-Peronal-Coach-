"""전적 트렌드 미니 시각화 — Canvas 없이 CTk 프레임 바로 구성.

외부 차트 라이브러리 없이 승패 칩 + KDA 막대만 그린다.
"""

from __future__ import annotations

from typing import Any

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FCH, FM


def pack_flow_chart(parent: Any, flow: dict) -> Any:
    """경기 흐름 차트 — 분당 골드 격차 막대 + 내 CS 라인 + 데스 마커.

    Canvas 외부 라이브러리 없이 그린다 (데이터 부족 시 None).
    """
    import tkinter as tk

    import customtkinter as ctk

    minutes = flow.get("minutes") or []
    diffs = flow.get("gold_diff") or []
    css = flow.get("my_cs") or []
    if len(minutes) < 2 or not diffs:
        return None
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        wrap,
        text="경기 흐름 — 골드 격차(±) · 내 CS · 💀",
        font=FCH,
        text_color=ui.TEXT_DIM,
        anchor="w",
    ).pack(fill="x", padx=2, pady=(0, 2))
    w, h = 460, 130
    canvas = tk.Canvas(wrap, width=w, height=h, bg=ui.PANEL, highlightthickness=0)
    canvas.pack(fill="x", padx=2)
    n = len(minutes)
    max_abs = max([abs(d) for d in diffs] + [1])
    max_cs = max(css + [1])
    mid = h // 2
    bw = w / n
    for i, d in enumerate(diffs):
        bar_h = int((h / 2 - 6) * abs(d) / max_abs)
        x0 = i * bw + 2
        x1 = (i + 1) * bw - 2
        color = ui.GREEN if d >= 0 else ui.RED
        y0 = mid - bar_h if d >= 0 else mid
        canvas.create_rectangle(x0, y0, x1, y0 + bar_h, fill=color, outline="")
    if len(css) > 1:
        pts = [
            (i * bw + bw / 2, h - 4 - (h - 8) * c / max_cs)
            for i, c in enumerate(css)
        ]
        canvas.create_line(pts, fill=ui.GOLD, width=2)
    canvas.create_line(0, mid, w, mid, fill=ui.BORDER)
    for dm in flow.get("deaths") or []:
        if dm < minutes[0] or dm > minutes[-1]:
            continue
        i = dm - minutes[0]
        x = (i + 0.5) * bw
        canvas.create_text(x, 6, text="💀", font=("Malgun Gothic", 9))
    return wrap


def pack_win_streak_bar(
    parent: Any,
    wins: list[bool],
    *,
    max_n: int = 15,
) -> Any:
    """최근 승패를 색 칩으로 표시 (왼쪽=최신)."""
    import customtkinter as ctk

    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        wrap, text="최근 결과", font=FCH, text_color=ui.TEXT_DIM, anchor="w"
    ).pack(fill="x", padx=2, pady=(0, 2))
    row = ctk.CTkFrame(wrap, fg_color="transparent")
    row.pack(fill="x")
    seq = list(wins)[:max_n]
    if not seq:
        ctk.CTkLabel(row, text="—", font=FM, text_color=ui.TEXT_MUTE).pack(side="left")
        return wrap
    for w in seq:
        chip = ctk.CTkLabel(
            row,
            text="W" if w else "L",
            width=18,
            height=18,
            corner_radius=4,
            font=("Malgun Gothic", 9, "bold"),
            fg_color=ui.GREEN if w else ui.RED,
            text_color=ui.ON_GOLD if w else "#FFFFFF",
        )
        chip.pack(side="left", padx=1, pady=1)
    return wrap


def pack_kda_bars(
    parent: Any,
    kdas: list[float],
    *,
    max_n: int = 12,
    bar_max_h: int = 36,
) -> Any:
    """KDA 막대 (왼쪽=최신)."""
    import customtkinter as ctk

    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    ctk.CTkLabel(
        wrap, text="KDA 추이", font=FCH, text_color=ui.TEXT_DIM, anchor="w"
    ).pack(fill="x", padx=2, pady=(4, 2))
    row = ctk.CTkFrame(wrap, fg_color=ui.ROW, corner_radius=8, height=bar_max_h + 12)
    row.pack(fill="x", padx=0, pady=0)
    row.pack_propagate(False)
    seq = list(kdas)[:max_n]
    if not seq:
        return wrap
    peak = max(seq) if max(seq) > 0 else 1.0
    peak = max(peak, 1.0)
    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(side="left", padx=6, pady=6)
    for k in seq:
        h = max(4, int(bar_max_h * min(k / peak, 1.0)))
        col = ui.GREEN if k >= 3.0 else (ui.WARN if k >= 2.0 else ui.RED_SOFT)
        bar = ctk.CTkFrame(inner, width=10, height=h, corner_radius=3, fg_color=col)
        bar.pack(side="left", padx=1, anchor="s")
        bar.pack_propagate(False)
    return wrap
