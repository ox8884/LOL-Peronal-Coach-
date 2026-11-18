"""아수라장 결과 화면.

왼쪽 단(`AramSide`) — 챔피언, 지금 할 것(벤치 잡기·리롤·유지), 벤치/적 조합.
오른쪽 낱장(`AramResultView`) — 추천 증강, 아이템 구매 순서, 실전 팁, 상세.
한 번 만든 칸은 다음 챔피언에서도 재사용한다 (위젯 재생성 없음).
"""

from __future__ import annotations

import re
import tkinter as tk
from functools import lru_cache, partial
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.aram_mayhem import AugmentTierTop, MayhemAdvice, tier_letter
from lol_coach.gui import components as ui
from lol_coach.gui import tooltip
from lol_coach.gui.constants import FB, FH, FM, FNUM, FONT_UI, FU
from lol_coach.static.icons import champion_ctk, champion_splash_ctk, item_ctk, item_name_ctk

SIDE_W = 372  # 왼쪽 단 너비 (배율 1 기준 px)
ART_H = 196
_RARITIES = (("실버", ui.SILVER), ("골드", ui.RARITY_GOLD), ("프리즘", ui.PRISM))


def _text(label: Any, text: str) -> None:
    if label.cget("text") != text:
        label.configure(text=text)


@lru_cache(maxsize=1024)
def _fit(text: str, size: int, width: int, lines: int) -> str:
    """`width` px 폭에서 `lines` 줄을 넘는 글은 말줄임표로 자른다 (전체는 툴팁).

    한글은 글자 크기만큼, 영문·숫자·기호는 그 절반쯤 차지한다고 보고 센다.
    """
    budget = width * lines * 0.86  # 줄바꿈으로 버려지는 자투리 몫
    used = 0.0
    for i, ch in enumerate(text):
        used += size * (0.95 if ord(ch) > 0x2E7F else 0.52)
        if used > budget:
            return text[: max(1, i - 1)].rstrip() + "…"
    return text


def _icon_ready(icon: Any) -> bool:
    return icon is not None and not icon.cget("light_image").info.get("lol_coach_placeholder")


class _AugmentSlot(tk.Frame):
    """증강 한 칸. 1순위는 크게, 이름에 형광펜."""

    def __init__(self, parent: Any, tab: Any, rank: int) -> None:
        bg = ui.surface_color(parent)
        super().__init__(parent, bg=bg, highlightthickness=0)
        self.tab, self.rank, self.pick = tab, rank, None
        top = rank == 1
        self._desc_size = FB[1] if top else FM[1]
        self._desc_lines = 2  # 세 열의 행 높이를 맞춘다 (전체는 칸에 마우스를 올리면)
        self._width = 220  # 칸 전체 폭 (배율 1 기준) — <Configure> 에서 실제 값으로
        self._taken = 100 if top else 72  # 이름 옆의 순위 숫자 + 아이콘 + 여백
        self.grid_columnconfigure(2, weight=1)
        ui.TextLabel(
            self, text=str(rank), font=FNUM(30 if top else 20), anchor="center", min_height=0,
            text_color=ui.INK if top else ui.TEXT_MUTE, width=2,
        ).grid(row=0, column=0, sticky="n", pady=(10 if top else 9, 0))
        side = 52 if top else 34
        self.icon = ctk.CTkLabel(self, text="", width=side, height=side, corner_radius=0,
                                 fg_color=ui.INK, font=(FONT_UI, 14, "bold"))
        self.icon._tile_color = ui.INK  # 증강 아이콘은 밝은 선화라 먹색 바탕 위에 둔다
        self.icon.grid(row=0, column=1, sticky="n", padx=(2, 10), pady=(10, 0))
        self.name = ui.TextLabel(
            self, font=(FONT_UI, 17 if top else 14, "bold"), text_color=ui.INK, min_height=0,
            wraplength=self._width - self._taken, bg=ui.YELLOW if top else bg,
            padx=5 if top else 0,
        )
        self.name.grid(row=0, column=2, sticky="w", pady=(10, 0))
        self.desc = ui.TextLabel(
            self, font=FB if top else FM, text_color=ui.TEXT if top else ui.TEXT_DIM,
            min_height=0, anchor="nw", wraplength=self._width - 6,
            height=2,  # 한 줄짜리 설명도 두 줄 자리를 차지해 세 열의 행이 나란하다
        )
        self.desc.grid(row=1, column=0, columnspan=3, sticky="ew", padx=(3, 0), pady=(7, 10))
        tk.Frame(self, bg=ui.BORDER, height=1, highlightthickness=0).grid(
            row=2, column=0, columnspan=3, sticky="ew"
        )
        self.bind("<Configure>", self._resize, add="+")
        self.tips = [
            tooltip.ToolTip(w, self.full_text, wrap=360)
            for w in (self, self.icon, self.name, self.desc)
        ]

    def _resize(self, event: Any) -> None:
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        width = max(140, round(event.width / scale))
        if width != self._width:
            self._width = width
            self.name.configure(wraplength=width - self._taken)
            self.desc.configure(wraplength=width - 6)
            if self.pick is not None:
                _text(self.desc, _fit(self.pick.desc, self._desc_size, width - 6, self._desc_lines))

    def full_text(self) -> str:
        p = self.pick
        return f"{p.name_ko}\n\n{p.desc}\n\n{p.reason}" if p else ""

    def show(self, pick: Any) -> None:
        for tip in self.tips:
            if tip is not None:
                tip.hide()
        self.pick = pick
        if pick is None:
            ui.clear_image(self.icon)
            _text(self.icon, "")
            self.grid_remove()
            return
        self.grid()
        _text(self.name, pick.name_ko)
        _text(self.desc, _fit(pick.desc, self._desc_size, self._width - 6, self._desc_lines))
        size = 44 if self.rank == 1 else 28
        self.tab._update_aram_icon(self.icon, partial(self.tab._augment_icon, pick, size), pick=pick)


class AugmentBoard(tk.Frame):
    """희귀도 3열 × 순위 3칸."""

    def __init__(self, parent: Any, tab: Any) -> None:
        bg = ui.surface_color(parent)
        super().__init__(parent, bg=bg, highlightthickness=0)
        self.slots: list[_AugmentSlot] = []
        self.empty: list[Any] = []
        for index, (title, color) in enumerate(_RARITIES):
            self.grid_columnconfigure(index, weight=1, uniform="rarity")
            column = tk.Frame(self, bg=bg, highlightthickness=0)
            column.grid(row=0, column=index, sticky="nsew", padx=(0, 18 if index < 2 else 0))
            column.grid_columnconfigure(0, weight=1)
            head = tk.Frame(column, bg=bg, highlightthickness=0)
            head.grid(row=0, column=0, sticky="ew")
            # 희귀도는 색과 글자를 함께 쓴다
            ui.TextLabel(
                head, text=title, font=(FONT_UI, 12, "bold"), text_color=ui.INK, bg=color,
                padx=10, min_height=24, anchor="center",
            ).pack(side="left")
            tk.Frame(head, bg=color, height=3, highlightthickness=0).pack(
                side="left", fill="x", expand=True, padx=(8, 0)
            )
            empty = ui.TextLabel(column, text="추천 데이터 없음", font=FU, text_color=ui.TEXT_DIM,
                                 anchor="center")
            empty.grid(row=1, column=0, pady=12)
            self.empty.append(empty)
            for rank in range(1, 4):
                slot = _AugmentSlot(column, tab, rank)
                slot.grid(row=rank + 1, column=0, sticky="ew")
                self.slots.append(slot)
        self.source = ui.TextLabel(self, font=FM, text_color=ui.TEXT_MUTE, wraplength=620)
        self.source.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        # 고르면 안 되는 증강 — 세 개 중 하나를 고를 때 걸러 낼 이름들
        self.avoid = ui.TextLabel(self, font=(FONT_UI, 13, "bold"), text_color=ui.RED, min_height=0,
                                  wraplength=620)
        self.avoid.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.avoid.grid_remove()
        self.bind("<Configure>", self._wrap_avoid, add="+")

    def _wrap_avoid(self, event: Any) -> None:
        width = max(200, round(event.width / ctk.ScalingTracker.get_widget_scaling(self)) - 8)
        if self.avoid.cget("wraplength") != width:
            self.avoid.configure(wraplength=width)

    def show_avoid(self, names: list[str]) -> None:
        if names:
            _text(self.avoid, "피할 증강   " + "  ·  ".join(names))
            self.avoid.grid()
        else:
            self.avoid.grid_remove()

    def show(self, fixed: AugmentTierTop, source: str) -> None:
        for col, picks in enumerate((fixed.silver, fixed.gold, fixed.prismatic)):
            self.empty[col].grid_remove() if picks else self.empty[col].grid()
            for row in range(3):
                self.slots[col * 3 + row].show(picks[row] if row < len(picks) else None)
        hint = "칸에 마우스를 올리면 전체 효과가 보입니다"
        _text(self.source, f"{source}  ·  {hint}" if source else hint)


class _ItemSlot(tk.Frame):
    """아이템 한 칸 — 사는 순서 숫자, 아이콘, 이름."""

    def __init__(self, parent: Any, index: int) -> None:
        bg = ui.surface_color(parent)
        super().__init__(parent, bg=bg, highlightthickness=0)
        ui.TextLabel(self, text=str(index + 1), font=FNUM(26), text_color=ui.INK, anchor="center",
                     min_height=0).pack()
        self.icon = ctk.CTkLabel(self, text="", width=52, height=52, corner_radius=0)
        self.icon.pack(pady=(3, 5))
        self.name = ui.TextLabel(self, font=(FONT_UI, 13, "bold"), text_color=ui.INK, min_height=0,
                                 height=2, wraplength=110, anchor="n", justify="center")
        self.name.pack(fill="x", padx=2)
        self.tip = tooltip.ToolTip(self.name, lambda: self.name.cget("text"))
        self.bind("<Configure>", self._wrap_name, add="+")

    def _wrap_name(self, event: Any) -> None:
        width = max(60, round(event.width / ctk.ScalingTracker.get_widget_scaling(self)) - 8)
        if self.name.cget("wraplength") != width:
            self.name.configure(wraplength=width)


class _CompareRow(tk.Frame):
    """먹색 칸 안의 비교 한 줄 — 아이콘, 이름, 티어, 설명."""

    def __init__(self, parent: Any, scale: float) -> None:
        super().__init__(parent, bg=ui.INK, highlightthickness=0)
        tk.Frame(self, bg=ui.INK_RULE, height=max(2, round(2 * scale)), highlightthickness=0).pack(
            fill="x"
        )
        self.icon = ui.TextLabel(self, bg=ui.INK, min_height=0)
        self.icon.pack(side="left", pady=round(8 * scale))
        self.name = ui.TextLabel(self, font=(FONT_UI, 15, "bold"), bg=ui.INK, min_height=0)
        self.name.pack(side="left", padx=(round(10 * scale), round(10 * scale)))
        self.tier = ui.TextLabel(self, font=FNUM(28), bg=ui.INK, min_height=0)
        self.tier.pack(side="left")
        self.note = ui.TextLabel(self, font=FM, text_color=ui.ON_INK_DIM, bg=ui.INK, min_height=0)
        self.note.pack(side="right")

    def set(self, icon: Any, name: str, tier: str, note: str, *, strong: bool) -> None:
        self.icon.set_image(icon)
        self.name.configure(text=name, text_color=ui.ON_INK if strong else ui.ON_INK_DIM)
        self.tier.configure(text=tier, text_color=ui.YELLOW if strong else ui.ON_INK_DIM)
        _text(self.note, note)


class AramSide(tk.Frame):
    """왼쪽 단 — 챔피언, 지금 할 것, 벤치(밴픽 중) 또는 적 조합(게임 중)."""

    CHIPS = 10

    def __init__(self, parent: Any, tab: Any, *, stacked: bool = False) -> None:
        """stacked=True 는 좁은 창용 — 챔피언과 답을 위쪽 가로 띠로 놓아 아래 낱장이 전체 폭을 쓴다."""
        self._board = ui.surface_color(parent)
        super().__init__(parent, bg=self._board, highlightthickness=0)
        self.tab = tab
        self.stacked = stacked
        scale = self._scale = ctk.ScalingTracker.get_widget_scaling(parent)

        def px(value: int) -> int:
            return round(value * scale)

        self._art_size = (252, 138) if stacked else (SIDE_W, ART_H)
        top = tk.Frame(self, bg=self._board, highlightthickness=0) if stacked else self
        if stacked:
            top.pack(fill="x")
        self._top = top
        # 1) 챔피언 — 일러스트 아래 먹색 이름판
        plate = tk.Frame(top, bg=ui.INK, highlightthickness=0)
        plate.pack(side="left", fill="y") if stacked else plate.pack(fill="x")
        self.art = ctk.CTkLabel(plate, text="", width=self._art_size[0], height=self._art_size[1],
                                corner_radius=0, fg_color=ui.INK, text_color=ui.INK_RULE, font=FH(40))
        self.art._tile_color = ui.INK
        self.art.pack()
        name_row = tk.Frame(plate, bg=ui.INK, highlightthickness=0)
        name_row.pack(fill="x", padx=px(14 if stacked else 16), pady=(px(6), px(10)))
        self.champion = ui.TextLabel(name_row, font=FH(30 if stacked else 40), text_color=ui.ON_INK,
                                     bg=ui.INK, min_height=0)
        self.champion.pack(side="left")
        self.tier = ui.TextLabel(name_row, font=(FONT_UI, 13, "bold"), text_color=ui.INK,
                                 bg=ui.YELLOW, padx=px(8), min_height=24)
        change = ui.TextLabel(name_row, text="바꾸기", font=FB, text_color=ui.ON_INK_DIM, bg=ui.INK,
                              cursor="hand2", min_height=0)
        change.pack(side="right", anchor="s", pady=(0, px(8)))
        change.bind("<Button-1>", lambda _e: tab._back_to_aram_pick())
        change.bind("<Enter>", lambda _e: change.configure(text_color=ui.YELLOW))
        change.bind("<Leave>", lambda _e: change.configure(text_color=ui.ON_INK_DIM))
        tooltip.ToolTip(change, lambda: "다른 챔피언을 직접 고릅니다")

        # 2) 지금 할 것 — 화면에서 가장 크고 가장 진한 한 줄.
        #    좁은 창에서는 답(왼쪽)과 비교 줄(오른쪽)을 나란히 놓아 띠 높이를 줄인다.
        self.now = tk.Frame(top, bg=ui.INK, highlightthickness=0)
        said = tk.Frame(self.now, bg=ui.INK, highlightthickness=0)
        told = tk.Frame(self.now, bg=ui.INK, highlightthickness=0)
        if stacked:
            said.pack(side="left", anchor="n")
            told.pack(side="left", fill="x", expand=True, anchor="n", pady=(px(8), px(8)))
        else:
            said.pack(fill="x")
            told.pack(fill="x")
        wrap = 300 if stacked else SIDE_W - 40
        self.headline = ui.TextLabel(said, font=FH(52), text_color=ui.YELLOW, bg=ui.INK,
                                     wraplength=wrap, min_height=0)
        self.subline = ui.TextLabel(said, font=(FONT_UI, 18, "bold"), text_color=ui.ON_INK,
                                    bg=ui.INK, wraplength=wrap, min_height=0)
        self.rows = [_CompareRow(told, scale) for _ in range(3)]
        self.hint = ui.TextLabel(said, font=FM, text_color=ui.ON_INK_DIM, bg=ui.INK,
                                 wraplength=wrap, min_height=0)

        # 3) 벤치 / 적 조합
        self.strip = tk.Frame(self, bg=self._board, highlightthickness=px(3),
                              highlightbackground=ui.INK)
        head = tk.Frame(self.strip, bg=self._board, highlightthickness=0)
        if stacked:
            head.pack(side="left", padx=(px(12), px(4)))
        else:
            head.pack(fill="x", padx=px(12), pady=(px(7), 0))
        self.strip_title = ui.TextLabel(head, font=(FONT_UI, 14, "bold"), text_color=ui.INK,
                                        min_height=0)
        self.strip_title.pack(side="left")
        self.strip_note = ui.TextLabel(head, font=FM, text_color=ui.TEXT_DIM, min_height=0)
        self.strip_note.pack(side="left", padx=(px(8), 0))
        chip_row = tk.Frame(self.strip, bg=self._board, highlightthickness=0)
        if stacked:
            chip_row.pack(side="left", padx=px(8), pady=px(7))
        else:
            chip_row.pack(fill="x", padx=px(10), pady=(px(6), px(9)))
        self.chips = [
            ui.TextLabel(chip_row, font=FNUM(24), text_color=ui.INK, min_height=0, padx=px(3))
            for _ in range(self.CHIPS)
        ]
        self.strip_text = ui.TextLabel(self.strip, font=FM, text_color=ui.TEXT, min_height=0,
                                       wraplength=SIDE_W - 34)
        self._missing: set[tuple[str, int]] = set()
        self._advice: Any = None
        self._adv: MayhemAdvice | None = None
        self._placed: tuple[bool, bool] = (False, False)

    def _place(self, now: bool, strip: bool) -> None:
        """먹색 칸·벤치 줄을 순서대로 다시 놓는다 (보일 것만)."""
        if (now, strip) == self._placed:
            return
        self._placed = (now, strip)
        gap = (round(14 * self._scale), 0)
        self.now.pack_forget()
        self.strip.pack_forget()
        if now and self.stacked:
            self.now.pack(side="left", fill="both", expand=True, padx=gap)
        elif now:
            self.now.pack(fill="x", pady=gap)
        if strip:
            self.strip.pack(fill="x", pady=gap)

    # ── 아이콘 ──
    def _champ_icon(self, key: str, size: int) -> Any:
        icon = champion_ctk(key, size)
        if not _icon_ready(icon):
            self._missing.add((key, size))
        return icon

    def _fetch_missing(self) -> None:
        """캐시에 없던 챔피언 아이콘을 받아 온 뒤 한 번 다시 그린다."""
        spawn = getattr(self.tab, "_spawn_thread", None)
        if not self._missing or spawn is None:
            return
        todo, self._missing = self._missing, set()

        def work() -> None:
            from lol_coach.static.icons import champion_pil

            for key, size in todo:
                champion_pil(key, size)
            self.tab.after(0, self._redraw)

        spawn(work)

    def _redraw(self) -> None:
        if self.winfo_exists() and self._adv is not None:
            self.show_advice(self._advice, self._adv, refetch=False)

    def _champ(self, cid: int) -> tuple[str, str]:
        dd = self.tab.dd
        return dd.champion_key(cid), dd.champion_name(cid)

    # ── 표시 ──
    def show(self, adv: MayhemAdvice) -> None:
        _text(self.champion, adv.champ_ko)
        key = adv.champ_key or adv.champ_ko
        self.tab._update_aram_icon(self.art, partial(champion_splash_ctk, key, *self._art_size))
        self.show_advice(adv.reroll, adv)

    def show_advice(self, advice: Any, adv: MayhemAdvice, *, refetch: bool = True) -> None:
        """벤치·리롤 조언 갱신 — 밴픽 중엔 벤치가 바뀔 때마다 불린다."""
        self._advice, self._adv = advice, adv
        kind = getattr(advice, "kind", "")
        my_tier = getattr(advice, "my_tier", None)
        if my_tier:
            win = getattr(adv.build, "win_rate", None)
            # 좁은 띠의 이름판에는 티어만 — 승률은 옆의 비교 줄에 있다
            _text(
                self.tier,
                f"{tier_letter(my_tier)}티어" + (f" · 승률 {win}%" if win and not self.stacked else ""),
            )
            self.tier.pack(side="left", padx=(round(12 * self._scale), 0), anchor="s",
                           pady=(0, round(8 * self._scale)))
        else:
            self.tier.pack_forget()

        me_key = adv.champ_key or adv.champ_ko
        me_tier = f"{tier_letter(my_tier)}티어" if my_tier else ""
        me_icon = self._champ_icon(me_key, 44)
        wins: dict[int, float] = getattr(advice, "win_rates", None) or {}
        my_win = wins.get(getattr(advice, "my_id", 0))
        me_note = f"지금 · 승률 {my_win}%" if my_win else "지금 내 챔피언"
        rows: list[tuple[Any, str, str, str, bool]] = []
        hint = ""
        # 답은 한 단어 — 잡을 챔피언 이름 하나, 리롤, 유지. 나머지는 아랫줄과 비교 줄로 보낸다.
        if kind == "bench":
            for cid in advice.picks[:2]:
                key, name = self._champ(cid)
                tier = dict(advice.bench).get(cid)
                note = f"벤치 · 승률 {wins[cid]}%" if wins.get(cid) else "벤치에 있음"
                rows.append(
                    (self._champ_icon(key, 44), name, f"{tier_letter(tier)}티어" if tier else "", note, True)
                )
            headline, sub = rows[0][1], "벤치에서 잡기"
            rows.append((me_icon, adv.champ_ko, me_tier, me_note, False))
        elif kind == "reroll":
            headline, sub = "리롤", f"남은 리롤 {advice.rerolls}번"
            rows.append((me_icon, adv.champ_ko, me_tier, me_note, False))
        elif kind == "keep":
            headline = "유지"
            sub = "벤치에 더 좋은 챔피언이 없습니다" if advice.bench else "지금 챔피언 그대로"
            rows.append((me_icon, adv.champ_ko, me_tier, me_note, True))
        else:
            # 밴픽 밖 — 가장 먼저 노릴 증강을 답으로 보여 준다
            best = adv.top_augments[0] if adv.top_augments else None
            headline, sub = (best.name_ko, "가장 먼저 노릴 증강") if best is not None else ("", "")
            if kind != "info" and advice is not None and advice.actions:
                headline, sub = advice.actions[0], ""  # 구조화 정보가 없는 조언은 문구 그대로
            elif best is not None:
                hint = "밴픽이 시작되면 벤치와 비교해 지금 할 것을 알려 드립니다."
        # 내 챔피언이 답일 때만 이름판의 티어 칩이 노랗다
        on = kind == "keep"
        self.tier.configure(
            bg=ui.YELLOW if on else ui.INK, text_color=ui.INK if on else ui.ON_INK_DIM,
            highlightthickness=0 if on else 1, highlightbackground=ui.ON_INK_DIM,
        )
        size = (84 if len(headline) <= 3 else 68 if len(headline) <= 5 else 56 if len(headline) <= 7
                else 44 if len(headline) <= 10 else 32)
        if self.stacked:
            size = min(size, 68 if len(headline) <= 4 else 52 if len(headline) <= 5 else 40)
        pad = round(20 * self._scale)
        for widget in (self.headline, self.subline, *self.rows, self.hint):
            widget.pack_forget()
        if headline:
            self.headline.configure(text=headline, font=FH(size))
            self.headline.pack(anchor="w", padx=pad, pady=(round(10 * self._scale), 0))
        if sub:
            _text(self.subline, sub)
            self.subline.pack(anchor="w", padx=pad, pady=(0, round(12 * self._scale)))
        for row, data in zip(self.rows, rows, strict=False):
            row.set(data[0], data[1], data[2], data[3], strong=data[4])
            row.pack(fill="x", padx=pad)
        if hint:
            _text(self.hint, hint)
            self.hint.pack(anchor="w", padx=pad, pady=(0, round(14 * self._scale)))
        self._place(bool(headline or rows), self._fill_strip(advice, adv))
        if refetch:
            self._fetch_missing()

    def _fill_strip(self, advice: Any, adv: MayhemAdvice) -> bool:
        """벤치(밴픽 중) 또는 적 조합(게임 중) 줄을 채운다. 보일 내용이 있으면 True."""
        bench = tuple(getattr(advice, "bench", ()) or ())
        enemies = list(getattr(adv, "enemy_keys", ()) or ())
        chips: list[tuple[Any, str, bool]] = []
        text = ""
        if bench:
            title, note = "벤치", "바꿀 수 있는 챔피언 · 글자는 아수라장 티어"
            picks = set(getattr(advice, "picks", ()))
            wins = getattr(advice, "win_rates", None) or {}
            for cid, tier in sorted(bench, key=lambda b: (b[1] or 9, -(wins.get(b[0]) or 0), b[0])):
                key, _name = self._champ(cid)
                chips.append(
                    (self._champ_icon(key, 40), f" {tier_letter(tier)}" if tier else " -", cid in picks)
                )
        elif enemies:
            title, note = "적 조합", ""
            chips = [(self._champ_icon(key, 40), "", False) for key in enemies]
            text = adv.adaptive_build_note or ""
        else:
            return False
        _text(self.strip_title, title)
        _text(self.strip_note, note)
        for chip, data in zip(self.chips, chips + [None] * self.CHIPS, strict=False):
            if data is None:
                chip.pack_forget()
                continue
            icon, label, hit = data
            chip.set_image(icon)
            chip.configure(text=label, bg=ui.INK if hit else self._board,
                           text_color=ui.YELLOW if hit else ui.INK)
            chip.pack(side="left", padx=(0, round(8 * self._scale)))
        if text:
            _text(self.strip_text, text)
            self.strip_text.pack(anchor="w", padx=round(12 * self._scale),
                                 pady=(0, round(9 * self._scale)))
        else:
            self.strip_text.pack_forget()
        return True


class AramResultView(ctk.CTkFrame):
    """오른쪽 낱장의 결과. `side_parent` 가 없으면 왼쪽 단을 위에 쌓는다."""

    def __init__(
        self, parent: Any, tab: Any, side_parent: Any = None, *, stacked: bool = False
    ) -> None:
        super().__init__(parent, fg_color="transparent")
        self.tab = tab
        self.advice: MayhemAdvice | None = None
        self.expanded = False
        self.details: Any = None
        self._detail_labels: list[Any] = []
        self._detail_rows: list[Any] = []
        self._detail_icons: list[Any] = []
        self._pending: str | None = None
        self._ai_pending: str | None = None
        self._details_advice: MayhemAdvice | None = None
        self._scroll_y = 0.0
        self.grid_columnconfigure(0, weight=1)
        self.side = AramSide(side_parent if side_parent is not None else self, tab, stacked=stacked)
        if side_parent is not None:
            self.side.pack(fill="x")
        else:
            self.side.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        self.champion = self.side.champion
        self.freshness = self._label(1, color=ui.WARN)
        self._heading(2, "추천 증강")
        # 출처는 제목 줄 오른쪽에 — 세로 한 줄을 아낀다
        self.aug_meta = ui.TextLabel(self, font=FM, text_color=ui.TEXT_MUTE, min_height=0)
        self.aug_meta.grid(row=2, column=0, sticky="e", padx=10, pady=(16, 0))
        self.board = AugmentBoard(self, tab)
        self.board.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 4))
        self.board.source.grid_remove()
        self._heading(4, "아이템 구매 순서")
        self.stale = ui.TextLabel(
            self, font=(FONT_UI, 12, "bold"), text_color=ui.RED, padx=8, min_height=24,
            highlightthickness=2, highlightbackground=ui.RED,
        )
        self.stale.grid(row=4, column=0, sticky="e", padx=10, pady=(14, 0))
        build = tk.Frame(self, bg=ui.surface_color(self), highlightthickness=0)
        build.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 4))
        self.items = []
        for i in range(6):
            build.grid_columnconfigure(i, weight=1, uniform="build")
            slot = _ItemSlot(build, i)
            slot.grid(row=0, column=i, sticky="nsew")
            self.items.append(slot)
        self.secondary = self._label(6, color=ui.TEXT_MUTE)
        self.adaptive = self._label(7, color=ui.WARN)
        self._heading(8, "실전 팁")
        tips = tk.Frame(self, bg=ui.surface_color(self), highlightthickness=0)
        tips.grid(row=9, column=0, sticky="ew", padx=10, pady=(2, 6))
        self.tips: list[Any] = []
        for i in range(3):
            tips.grid_columnconfigure(i, weight=1, uniform="tip")
            cell = tk.Frame(tips, bg=tips.cget("bg"), highlightthickness=0)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0, 18 if i < 2 else 0))
            tk.Frame(cell, bg=ui.INK, height=3, highlightthickness=0).pack(fill="x")
            label = ui.TextLabel(cell, font=FB, text_color=ui.TEXT, min_height=0, anchor="nw",
                                 wraplength=230)
            label.pack(fill="x", pady=(7, 0))
            cell.bind("<Configure>", partial(self._wrap_tip, label), add="+")
            self.tips.append(label)
        self.toggle = ctk.CTkButton(self, text="상세 추천과 조합 펼치기", anchor="w", height=34, font=FU,
                                    **ui.btn(*ui.BTN_SECONDARY), command=self.toggle_details)
        self.toggle.grid(row=10, column=0, sticky="ew", padx=10, pady=(12, 4))
        self.ai_host = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.ai_host.grid_columnconfigure(0, weight=1)
        self.source = self._label(13)

    def _wrap_tip(self, label: Any, event: Any) -> None:
        width = max(120, round(event.width / ctk.ScalingTracker.get_widget_scaling(self)))
        if label.cget("wraplength") != width:
            label.configure(wraplength=width)

    def _label(self, row: int, color: Any = None) -> Any:
        label = ui.TextLabel(self, font=FM, text_color=color or ui.TEXT_DIM, wraplength=650)
        label.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
        return label

    def _heading(self, row: int, text: str) -> None:
        ui.section_heading(self, text, row)

    @staticmethod
    def _optional(label: Any, text: str) -> None:
        _text(label, text)
        label.grid() if text else label.grid_remove()

    def suspend(self) -> None:
        canvas = getattr(self.master, "_parent_canvas", None)
        if canvas is not None and self.winfo_ismapped():
            self._scroll_y = canvas.canvasy(0)
        if self._ai_pending is not None:
            self.after_cancel(self._ai_pending)
            self._ai_pending = None
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
        for slot in self.board.slots:
            for tip in slot.tips:
                if tip is not None:
                    tip.hide()
        for item in self.items:
            if item.tip is not None:
                item.tip.hide()
        self.tab._clear(self.ai_host)
        self.ai_host.grid_remove()

    def show_reroll(self, reroll: Any) -> None:
        """벤치·리롤 조언 — 밴픽 중엔 폴마다 왼쪽 단만 갱신한다."""
        if self.advice is not None:
            self.side.show_advice(reroll, self.advice)

    @staticmethod
    def _stale_note(adv: MayhemAdvice) -> str:
        """아이템 데이터가 증강 데이터보다 오래됐으면 몇 패치 전인지 알린다."""
        items = getattr(adv.build, "patch", "") or ""
        if not items or not adv.patch or items == adv.patch:
            return ""
        try:
            (a_major, a_minor), (i_major, i_minor) = (
                tuple(int(part) for part in value.split(".")[:2]) for value in (adv.patch, items)
            )
        except ValueError:
            return f"아이템 데이터는 패치 {items} 기준"
        behind = a_minor - i_minor if a_major == i_major else 0
        return f"아이템 데이터는 패치 {items} 기준" + (f" — {behind}패치 전" if behind > 0 else "")

    def show(self, adv: MayhemAdvice) -> None:
        self.suspend()
        self.advice = adv
        self._details_advice = None
        self.side.show(adv)
        self._optional(self.freshness, self.tab._aram_freshness_banner(adv))
        self.board.show(adv.fixed_top, adv.augment_source)
        self.board.show_avoid([pick.name_ko for pick in adv.avoid_augments[:5]])
        for i, slot in enumerate(self.items):
            if slot.tip is not None:
                slot.tip.hide()
            name = adv.core_slots[i] if i < len(adv.core_slots) else "상황 아이템"
            _text(slot.name, name)
            iid = adv.core_item_ids[i] if i < len(adv.core_item_ids) else None
            loader = partial(item_ctk, iid, 52) if iid is not None else partial(item_name_ctk, name, 52)
            self.tab._update_aram_icon(slot.icon, loader)
        stale = self._stale_note(adv)
        self._optional(self.stale, stale)
        _text(self.aug_meta, adv.augment_source)
        # 2026-10-04T23:16:00+00:00 같은 원본 시각은 날짜만 남긴다
        secondary = re.sub(r"(\d{4}-\d{2}-\d{2})T[\d:.+-]+", r"\1", adv.source.secondary if adv.source else "")
        self._optional(self.secondary, "" if stale else secondary)  # 딱지가 같은 말을 한다
        self._optional(self.adaptive, f"상황 빌드 — {adv.adaptive_build_note}" if adv.adaptive_build_note else "")
        # 증강 보드와 겹치는 "추천 증강: …" 줄은 빼고 앞의 세 가지만
        tips = [
            t for t in adv.play_tips if not t.startswith("추천 증강") and "카탈로그 기준" not in t
        ][:3]
        for label, tip in zip(self.tips, tips + [""] * 3, strict=False):
            _text(label, tip)
        meta = []
        if adv.source:
            for prefix, value in (("패치", adv.source.patch), ("갱신", adv.source.updated_at), ("출처", adv.source.primary)):
                if value:
                    meta.append(f"{prefix} {value}")
        if not meta:
            meta.append(f"출처  {adv.source_url}")
        if adv.build_url:
            meta.append(f"빌드 출처  {adv.build_url}")
        _text(self.source, "  ·  ".join(meta))
        # 먼저 핵심 내용을 그린 뒤 상세/선택형 AI 작업을 처리한다.
        if self.details is not None and self.expanded:
            self.details.configure(height=max(1, self.details.winfo_height() / self._get_widget_scaling()))
            self.details.grid_propagate(False)
            for label in self._detail_labels:
                _text(label, "")
            for icon in self._detail_icons:
                ui.clear_image(icon)
                _text(icon, "")
        self._pending = self.after(1, self._after_core)

    def _after_core(self) -> None:
        self._pending = None
        adv = self.advice
        if adv is None:
            return
        if self.expanded:
            self._fill_details()
        key = self.tab._ai_key()
        if key:
            # 밴픽 벤치 스왑이 연달아 오면 마지막 챔피언만 AI 요청 (버려질 요청 비용 방지)
            self._ai_pending = self.after(1200, lambda: self._start_ai(adv, key))
        canvas = getattr(self.master, "_parent_canvas", None)
        if canvas is not None:
            self.update_idletasks()
            bounds = canvas.bbox("all")
            if bounds and bounds[3] > 0:
                canvas.yview_moveto(self._scroll_y / bounds[3])

    def _start_ai(self, adv: MayhemAdvice, key: str) -> None:
        self._ai_pending = None
        if self.advice is not adv:
            return
        self.ai_host.grid(row=12, column=0, sticky="ew")
        self.tab._maybe_ai(self.ai_host, lambda on_delta=None: self.tab._ai_coach_aram(adv, key, on_delta=on_delta))

    def toggle_details(self) -> None:
        self.expanded = not self.expanded
        _text(self.toggle, "상세 추천과 조합 접기" if self.expanded else "상세 추천과 조합 펼치기")
        if self.expanded:
            self._fill_details()
        elif self.details is not None:
            self.details.grid_remove()

    def _fill_details(self) -> None:
        adv = self.advice
        if adv is None:
            return
        if self.details is None:
            self.details = ctk.CTkFrame(self, fg_color="transparent")
            self.details.grid_columnconfigure(0, weight=1)
        self.details.grid(row=11, column=0, sticky="ew", padx=10)
        if self._details_advice is adv:
            return
        picks: dict[int, Any] = {}
        head = (FONT_UI, 15, "bold")
        lines: list[tuple[str, Any, Any]] = [("메타 증강 추천", ui.INK, head),
            ("「일반 S」는 전체 메타, 「이 챔프 S」는 선택한 챔피언 전용 순위입니다.", ui.TEXT_DIM, FM)]
        lines += [(f"시너지  {s}", ui.BLUE_SOFT, FM) for s in adv.synergy_lines]
        for i, pick in enumerate(adv.top_augments, 1):
            picks[len(lines)] = pick
            lines.append((f"{i}. {pick.name_ko} — {pick.desc}\n({pick.reason})", ui.TEXT, FB))
        for pick in adv.avoid_augments:
            picks[len(lines)] = pick
            lines.append((f"피하기  {pick.name_ko} — {pick.desc}\n({pick.reason})", ui.RED_SOFT, FB))
        comp = getattr(adv, "comp_lines", []) or []
        if comp:
            lines.append(("조합 위협과 시너지", ui.INK, head))
            for line in comp:
                kind = getattr(line, "kind", "note")
                prefix, color = {"threat": ("위협  ", ui.RED_SOFT), "synergy": ("시너지  ", ui.GREEN)}.get(kind, ("", ui.TEXT_DIM))
                lines.append((prefix + getattr(line, "text", str(line)), color, FB))
        lines.append(("실전 팁 전체", ui.INK, head))
        lines += [(t, ui.TEXT, FB) for t in adv.play_tips]
        for i, (text, color, font) in enumerate(lines):
            if i == len(self._detail_labels):
                row = tk.Frame(self.details, bg=ui.surface_color(self.details), highlightthickness=0)
                row.grid_columnconfigure(1, weight=1)
                icon = ctk.CTkLabel(row, text="", width=32, height=32, corner_radius=0)
                icon._tile_color = ui.INK
                icon.grid(row=0, column=0, padx=(0, 8), sticky="n")
                label = ui.TextLabel(row, wraplength=620)
                label.grid(row=0, column=1, sticky="ew")
                self._detail_rows.append(row)
                self._detail_icons.append(icon)
                self._detail_labels.append(label)
            label = self._detail_labels[i]
            label.configure(text=text, text_color=color, font=font)
            self._detail_rows[i].grid(row=i, column=0, sticky="ew", pady=(12, 4) if font == head else 3)
            icon = self._detail_icons[i]
            if i in picks:
                pick = picks[i]
                icon.grid()
                self.tab._update_aram_icon(icon, partial(self.tab._augment_icon, pick, 32), pick=pick)
            else:
                ui.clear_image(icon)
                _text(icon, "")
                icon.grid_remove()
        for i in range(len(lines), len(self._detail_rows)):
            _text(self._detail_labels[i], "")
            ui.clear_image(self._detail_icons[i])
            _text(self._detail_icons[i], "")
            self._detail_rows[i].grid_remove()
        self._details_advice = adv
        self.details.grid_propagate(True)
        self.tab._schedule_aram_icon_fill()

    def destroy(self) -> None:
        self.suspend()
        ui.release_images(self)
        super().destroy()
