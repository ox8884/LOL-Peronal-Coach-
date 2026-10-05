"""아수라장 결과 한 화면을 재사용하고 긴 설명은 펼칠 때 만든다."""

from __future__ import annotations

from functools import partial
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.aram_mayhem import AugmentTierTop, MayhemAdvice
from lol_coach.gui import components as ui
from lol_coach.gui import tooltip
from lol_coach.gui.constants import FB, FM, FONT_UI, FS, FU
from lol_coach.static.icons import champion_ctk, item_ctk, item_name_ctk


def _text(label: Any, text: str) -> None:
    if label.cget("text") != text:
        label.configure(text=text)


class _AugmentSlot(ctk.CTkFrame):
    def __init__(self, parent: Any, tab: Any, rank: int) -> None:
        super().__init__(parent, fg_color=ui.ROW, corner_radius=8, border_width=0)
        self.tab, self.rank, self.pick = tab, rank, None
        self.grid_columnconfigure(1, weight=1)
        self.icon = ctk.CTkLabel(self, text="", width=36, height=36, corner_radius=6)
        self.icon.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="n")
        self.name = ctk.CTkLabel(self, text="", font=(FONT_UI, 13, "bold"),
                                 text_color=ui.TEXT_BRIGHT, anchor="w", justify="left", wraplength=130)
        self.name.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(7, 0))
        self.desc = ctk.CTkLabel(self, text="", font=FB, text_color=ui.TEXT_DIM,
                                 height=30, anchor="nw", justify="left", wraplength=130)
        self.desc.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
        self.bind("<Configure>", self._resize, add="+")
        self.tips = [tooltip.ToolTip(w, self.full_text, wrap=360) for w in (self, self.icon, self.name, self.desc)]

    def _resize(self, event: Any) -> None:
        width = max(80, round(event.width / self._get_widget_scaling()) - 66)
        if self.name.cget("wraplength") != width:
            self.name.configure(wraplength=width)
            self.desc.configure(wraplength=width)

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
        _text(self.name, f"{self.rank}  {pick.name_ko}")
        desc = pick.desc
        if "?" in desc:
            desc = "효과 보기 · 일부 수치 미제공"
        elif len(desc) > 26:
            desc = desc[:25].rstrip() + "…"
        _text(self.desc, desc)
        self.tab._update_aram_icon(self.icon, partial(self.tab._augment_icon, pick, 36), pick=pick)


class AugmentBoard(ctk.CTkFrame):
    def __init__(self, parent: Any, tab: Any) -> None:
        super().__init__(parent, fg_color="transparent")
        self.slots: list[_AugmentSlot] = []
        self.empty: list[Any] = []
        for index, (title, color) in enumerate((("실버", ui.TEXT_DIM), ("골드", ui.GOLD), ("프리즘", ui.BLUE_SOFT))):
            self.grid_columnconfigure(index, weight=1, uniform="rarity")
            column = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            column.grid(row=0, column=index, sticky="nsew", padx=(0, 8 if index < 2 else 0))
            column.grid_columnconfigure(0, weight=1)
            ctk.CTkFrame(column, height=2, fg_color=color, corner_radius=0).grid(row=0, column=0, sticky="ew")
            ctk.CTkLabel(column, text=title, font=FS, text_color=color, anchor="w").grid(row=1, column=0, sticky="ew", pady=(6, 8))
            empty = ctk.CTkLabel(column, text="추천 데이터 없음", font=FU, text_color=ui.TEXT_DIM)
            empty.grid(row=2, column=0, pady=12)
            self.empty.append(empty)
            for rank in range(1, 4):
                slot = _AugmentSlot(column, tab, rank)
                slot.grid(row=rank + 1, column=0, sticky="ew", pady=(0, 6))
                self.slots.append(slot)
        self.source = ctk.CTkLabel(self, text="", font=FM, text_color=ui.TEXT_MUTE, anchor="w", justify="left", wraplength=620)
        self.source.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 0))

    def show(self, fixed: AugmentTierTop, source: str) -> None:
        for col, picks in enumerate((fixed.silver, fixed.gold, fixed.prismatic)):
            self.empty[col].grid_remove() if picks else self.empty[col].grid()
            for row in range(3):
                self.slots[col * 3 + row].show(picks[row] if row < len(picks) else None)
        _text(self.source, f"{source}  ·  마우스를 올려 전체 효과 보기" if source else "마우스를 올려 전체 효과 보기")


class _ItemSlot(ctk.CTkFrame):
    def __init__(self, parent: Any, index: int) -> None:
        super().__init__(parent, fg_color=ui.ROW, corner_radius=8, border_width=0)
        ctk.CTkLabel(self, text=f"0{index + 1}", font=FM, text_color=ui.TEXT_DIM).pack(pady=(4, 0))
        self.icon = ctk.CTkLabel(self, text="", width=40, height=40, corner_radius=6)
        self.icon.pack(pady=(2, 5))
        self.name = ctk.CTkLabel(self, text="", font=FB, text_color=ui.TEXT_BRIGHT, height=36, wraplength=85)
        self.name.pack(fill="x", padx=4, pady=(0, 8))
        self.tip = tooltip.ToolTip(self.name, lambda: self.name.cget("text"))


class AramResultView(ctk.CTkFrame):
    def __init__(self, parent: Any, tab: Any) -> None:
        super().__init__(parent, fg_color="transparent")
        self.tab = tab
        self.advice: MayhemAdvice | None = None
        self.expanded = False
        self.details: Any = None
        self._detail_labels: list[Any] = []
        self._detail_rows: list[Any] = []
        self._detail_icons: list[Any] = []
        self._pending: str | None = None
        self._details_advice: MayhemAdvice | None = None
        self._scroll_y = 0.0
        self.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(12, 4))
        self.portrait = ctk.CTkLabel(head, text="", width=56, height=56)
        self.portrait.pack(side="left", padx=(0, 14))
        identity = ctk.CTkFrame(head, fg_color="transparent")
        identity.pack(side="left")
        self.champion = ctk.CTkLabel(identity, text="", font=(FONT_UI, 22, "bold"), text_color=ui.TEXT_BRIGHT)
        self.champion.pack(anchor="w")
        self.patch = ctk.CTkLabel(identity, text="", font=FU, text_color=ui.TEXT_DIM)
        self.patch.pack(anchor="w")
        ctk.CTkButton(head, text="챔피언 변경", width=100, height=32, font=FB,
                      **ui.btn(*ui.BTN_SECONDARY), command=tab._back_to_aram_pick).pack(side="right")
        self.freshness = self._label(1, color=ui.WARN)
        self.reroll = self._label(2)
        self._heading(3, "추천 증강")
        self.board = AugmentBoard(self, tab)
        self.board.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        self._heading(5, "아이템 구매 순서")
        build = ctk.CTkFrame(self, fg_color="transparent")
        build.grid(row=6, column=0, sticky="ew", padx=10, pady=(0, 6))
        self.items = []
        for i in range(6):
            build.grid_columnconfigure(i, weight=1, uniform="build")
            slot = _ItemSlot(build, i)
            slot.grid(row=0, column=i, sticky="nsew", padx=(0, 6 if i < 5 else 0))
            self.items.append(slot)
        self.secondary = self._label(7, color=ui.TEXT_MUTE)
        self.adaptive = self._label(8, color=ui.WARN)
        self.toggle = ctk.CTkButton(self, text="▸ 상세 추천 · 조합 · 실전 팁", anchor="w", height=34, font=FU,
                                   **ui.btn(*ui.BTN_SECONDARY), command=self.toggle_details)
        self.toggle.grid(row=9, column=0, sticky="ew", padx=10, pady=(10, 4))
        self.ai_host = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.ai_host.grid_columnconfigure(0, weight=1)
        self.source = self._label(12)

    def _label(self, row: int, color: Any = None) -> Any:
        label = ctk.CTkLabel(self, text="", font=FM, text_color=color or ui.TEXT_DIM, anchor="w", justify="left", wraplength=650)
        label.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
        return label

    def _heading(self, row: int, text: str) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", padx=10, pady=(16, 6))
        ctk.CTkFrame(head, width=5, height=20, corner_radius=2, fg_color=ui.GOLD).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(head, text=text, font=FS, text_color=ui.TEXT_BRIGHT).pack(side="left")

    @staticmethod
    def _optional(label: Any, text: str) -> None:
        _text(label, text)
        label.grid() if text else label.grid_remove()

    def suspend(self) -> None:
        canvas = getattr(self.master, "_parent_canvas", None)
        if canvas is not None and self.winfo_ismapped():
            self._scroll_y = canvas.canvasy(0)
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

    def show(self, adv: MayhemAdvice) -> None:
        self.suspend()
        self.advice = adv
        self._details_advice = None
        _text(self.champion, adv.champ_ko)
        _text(self.patch, f"아수라장 브리핑  ·  증강 패치 {adv.patch or '미확인'}")
        self.tab._update_aram_icon(self.portrait, partial(champion_ctk, adv.champ_key or adv.champ_ko, 56))
        self._optional(self.freshness, self.tab._aram_freshness_banner(adv))
        reroll = adv.reroll
        self._optional(self.reroll, "🎲 " + " ".join(reroll.actions) if reroll and reroll.actions else "")
        if reroll:
            self.reroll.configure(text_color=ui.RED_SOFT if reroll.tier == "B" else ui.GREEN)
        self.board.show(adv.fixed_top, adv.augment_source)
        for i, slot in enumerate(self.items):
            if slot.tip is not None:
                slot.tip.hide()
            name = adv.core_slots[i] if i < len(adv.core_slots) else "상황 아이템"
            _text(slot.name, name)
            iid = adv.core_item_ids[i] if i < len(adv.core_item_ids) else None
            loader = partial(item_ctk, iid, 40) if iid is not None else partial(item_name_ctk, name, 40)
            self.tab._update_aram_icon(slot.icon, loader)
        self._optional(self.secondary, adv.source.secondary if adv.source else "")
        self._optional(self.adaptive, f"🔧 상황 빌드 — {adv.adaptive_build_note}" if adv.adaptive_build_note else "")
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
            self.ai_host.grid(row=11, column=0, sticky="ew")
            self.tab._maybe_ai(self.ai_host, lambda on_delta=None: self.tab._ai_coach_aram(adv, key, on_delta=on_delta))
        canvas = getattr(self.master, "_parent_canvas", None)
        if canvas is not None:
            self.update_idletasks()
            bounds = canvas.bbox("all")
            if bounds and bounds[3] > 0:
                canvas.yview_moveto(self._scroll_y / bounds[3])

    def toggle_details(self) -> None:
        self.expanded = not self.expanded
        _text(self.toggle, ("▾" if self.expanded else "▸") + " 상세 추천 · 조합 · 실전 팁")
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
        self.details.grid(row=10, column=0, sticky="ew", padx=10)
        if self._details_advice is adv:
            return
        picks: dict[int, Any] = {}
        lines: list[tuple[str, Any, Any]] = [("메타 증강 추천", ui.TEXT_BRIGHT, FS),
            ("「일반 S」는 전체 메타, 「이 챔프 S」는 선택한 챔피언 전용 순위입니다.", ui.TEXT_DIM, FM)]
        lines += [(f"✦ {s}", ui.BLUE_SOFT, FM) for s in adv.synergy_lines]
        for i, pick in enumerate(adv.top_augments, 1):
            picks[len(lines)] = pick
            lines.append((f"{i}. {pick.name_ko} — {pick.desc}\n({pick.reason})", ui.TEXT, FB))
        for pick in adv.avoid_augments:
            picks[len(lines)] = pick
            lines.append((f"✕ {pick.name_ko} — {pick.desc}\n({pick.reason})", ui.RED_SOFT, FB))
        comp = getattr(adv, "comp_lines", []) or []
        if comp:
            lines.append(("조합 위협 · 시너지", ui.TEXT_BRIGHT, FS))
            for line in comp:
                kind = getattr(line, "kind", "note")
                prefix, color = {"threat": ("⚠ ", ui.RED_SOFT), "synergy": ("✦ ", ui.GREEN)}.get(kind, ("· ", ui.TEXT_DIM))
                lines.append((prefix + getattr(line, "text", str(line)), color, FB))
        lines.append(("실전 팁", ui.TEXT_BRIGHT, FS))
        lines += [(f"·  {t}", ui.TEXT, FB) for t in adv.play_tips]
        for i, (text, color, font) in enumerate(lines):
            if i == len(self._detail_labels):
                row = ctk.CTkFrame(self.details, fg_color="transparent")
                row.grid_columnconfigure(1, weight=1)
                icon = ctk.CTkLabel(row, text="", width=32, height=32, corner_radius=6)
                icon.grid(row=0, column=0, padx=(0, 8), sticky="n")
                label = ctk.CTkLabel(row, text="", anchor="w", justify="left", wraplength=620)
                label.grid(row=0, column=1, sticky="ew")
                self._detail_rows.append(row)
                self._detail_icons.append(icon)
                self._detail_labels.append(label)
            label = self._detail_labels[i]
            label.configure(text=text, text_color=color, font=font)
            self._detail_rows[i].grid(row=i, column=0, sticky="ew", pady=(10, 4) if font == FS else 3)
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
