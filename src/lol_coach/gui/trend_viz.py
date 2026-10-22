"""전적 트렌드 미니 시각화 — tk.Canvas 에 직접 그린다.

외부 차트 라이브러리 없이, 위젯(네이티브 창) 수를 최소로 유지한다.
"""

from __future__ import annotations

from typing import Any

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FCH, FM, FONT_UI


def pack_flow_chart(parent: Any, flow: dict) -> Any:
    """경기 흐름 차트 — 분당 골드 격차 막대 + 내 CS 라인 + 데스 마커.

    Canvas 외부 라이브러리 없이 그린다 (데이터 부족 시 None).
    """
    import tkinter as tk

    minutes = flow.get("minutes") or []
    diffs = flow.get("gold_diff") or []
    css = flow.get("my_cs") or []
    if len(minutes) < 2 or not diffs:
        return None
    wrap = _titled_wrap(parent, "경기 흐름 — 골드 격차(±) · 내 CS · 💀", (0, 2))
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
        pts = [(i * bw + bw / 2, h - 4 - (h - 8) * c / max_cs) for i, c in enumerate(css)]
        canvas.create_line(pts, fill=ui.GOLD, width=2)
    canvas.create_line(0, mid, w, mid, fill=ui.BORDER)
    for dm in flow.get("deaths") or []:
        if dm < minutes[0] or dm > minutes[-1]:
            continue
        i = dm - minutes[0]
        x = (i + 0.5) * bw
        canvas.create_text(x, 6, text="💀", font=(FONT_UI, 9))
    return wrap


def _titled_wrap(parent: Any, title: str, pady: Any) -> Any:
    """투명 tk.Frame + 제목 TextLabel (CTkFrame+CTkLabel 창 5개 → 2개)."""
    import tkinter as tk

    wrap = tk.Frame(parent, bg=ui.surface_color(parent), highlightthickness=0)
    ui.TextLabel(wrap, text=title, font=FCH, text_color=ui.TEXT_DIM, min_height=20).pack(
        fill="x", padx=2, pady=pady
    )
    return wrap


def _scale(widget: Any) -> float:
    import customtkinter as ctk

    return float(ctk.ScalingTracker.get_widget_scaling(widget))


def pack_win_streak_bar(
    parent: Any,
    wins: list[bool],
    *,
    max_n: int = 15,
) -> Any:
    """최근 승패를 색 칩으로 표시 (왼쪽=최신). 칩은 Canvas 1개에 그린다."""
    import tkinter as tk

    wrap = _titled_wrap(parent, "최근 결과", (0, 2))
    seq = list(wins)[:max_n]
    if not seq:
        ui.TextLabel(wrap, text="—", font=FM, text_color=ui.TEXT_MUTE).pack(anchor="w")
        return wrap
    sc = _scale(parent)
    size, gap = round(18 * sc), round(2 * sc)
    canvas = tk.Canvas(
        wrap,
        width=len(seq) * (size + gap),
        height=size + gap,
        bg=ui.surface_color(parent),
        highlightthickness=0,
    )
    canvas.pack(anchor="w")
    font = (FONT_UI, -round(9 * sc), "bold")
    for i, w in enumerate(seq):
        x0 = i * (size + gap) + 1
        canvas.create_rectangle(
            x0, 1, x0 + size, 1 + size, fill=ui.GREEN if w else ui.RED, outline=""
        )
        canvas.create_text(
            x0 + size / 2, 1 + size / 2, text="W" if w else "L", font=font, fill=ui.ON_GOLD
        )
    return wrap


def pack_kda_bars(
    parent: Any,
    kdas: list[float],
    *,
    max_n: int = 12,
    bar_max_h: int = 36,
) -> Any:
    """KDA 막대 (왼쪽=최신). 막대는 Canvas 1개에 그린다."""
    import tkinter as tk

    wrap = _titled_wrap(parent, "KDA 추이", (4, 2))
    sc = _scale(parent)
    max_h = round(bar_max_h * sc)
    canvas = tk.Canvas(wrap, height=max_h + round(12 * sc), bg=ui.ROW, highlightthickness=0)
    canvas.pack(fill="x")
    seq = list(kdas)[:max_n]
    if not seq:
        return wrap
    peak = max(max(seq), 1.0)
    pad, bw, gap = round(6 * sc), round(10 * sc), round(2 * sc)
    base = pad + max_h
    for i, k in enumerate(seq):
        h = max(round(4 * sc), int(max_h * min(k / peak, 1.0)))
        col = ui.GREEN if k >= 3.0 else (ui.WARN if k >= 2.0 else ui.RED_SOFT)
        x0 = pad + i * (bw + gap)
        canvas.create_rectangle(x0, base - h, x0 + bw, base, fill=col, outline="")
    return wrap


def pack_trend_chart(
    parent: Any,
    kdas: list[float],
    wins: list[bool],
    cs_per_mins: list[float],
    *,
    max_n: int = 20,
) -> Any:
    """KDA + CS/분 추이 차트 (왼쪽=최신). 승패는 배경 칩.

    Canvas 기반 라인 차트 — KDA(녹색) + CS/분(금색) 두 라인.
    승패는 배경 칩으로 표시.
    """
    import tkinter as tk

    seq_kda = list(kdas)[:max_n]
    seq_win = list(wins)[:max_n]
    seq_cs = list(cs_per_mins)[:max_n]
    n = max(len(seq_kda), len(seq_win), len(seq_cs))
    if n < 2:
        return None

    wrap = _titled_wrap(parent, "성장 추이", (4, 2))

    w, h = 300, 110
    pad_l, pad_r, pad_t, pad_b = 24, 8, 8, 16
    chart_w = w - pad_l - pad_r
    chart_h = h - pad_t - pad_b

    canvas = tk.Canvas(wrap, width=w, height=h, bg=ui.PANEL, highlightthickness=0)
    canvas.pack(fill="x", padx=2)

    # 승패 배경 칩
    bw = chart_w / n
    for i, win in enumerate(seq_win):
        x0 = pad_l + i * bw
        color = ui.GREEN if win else ui.RED
        # 승패 색상을 25% 농도로 채우기
        canvas.create_rectangle(
            x0,
            pad_t,
            x0 + bw,
            pad_t + chart_h,
            fill=color,
            outline="",
            stipple="gray25",
        )

    # Y축 라벨
    canvas.create_text(
        pad_l - 4,
        pad_t + 4,
        text="KDA/CS분",
        font=(FONT_UI, 7),
        fill=ui.TEXT_MUTE,
        anchor="ne",
    )
    canvas.create_text(
        pad_l - 4,
        h - pad_b - 2,
        text="0",
        font=(FONT_UI, 7),
        fill=ui.TEXT_MUTE,
        anchor="ne",
    )

    # KDA 라인 (녹색)
    if len(seq_kda) >= 2:
        peak_kda = max(max(seq_kda), 3.0)
        pts_kda = [
            (
                pad_l + i * bw + bw / 2,
                pad_t + chart_h - (chart_h - 4) * min(k / peak_kda, 1.0),
            )
            for i, k in enumerate(seq_kda)
        ]
        canvas.create_line(pts_kda, fill=ui.GREEN, width=2, smooth=True)

    # CS/분 라인 (금색)
    if len(seq_cs) >= 2:
        peak_cs = max(max(seq_cs), 5.0)
        pts_cs = [
            (
                pad_l + i * bw + bw / 2,
                pad_t + chart_h - (chart_h - 4) * min(c / peak_cs, 1.0),
            )
            for i, c in enumerate(seq_cs)
        ]
        canvas.create_line(pts_cs, fill=ui.GOLD, width=2, smooth=True)

    # 범례
    canvas.create_text(
        w - pad_r,
        pad_t + 2,
        text="● KDA  ● CS/분",
        font=(FONT_UI, 7),
        fill=ui.TEXT_MUTE,
        anchor="ne",
    )

    return wrap
