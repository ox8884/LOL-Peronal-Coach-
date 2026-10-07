"""아수라장 티어표 탭 — 전체 173챔피언의 blitz.gg 실시간 티어 보드.

챔프 선택 전 참고 + 리롤 판단용. 티어 1(강)~5(약)를 색으로 구분해
챔피언 아이콘 그리드로 표시한다.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

from lol_coach.blitz.mayhem_live import fetch_mayhem_champion_tiers
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FS
from lol_coach.gui.types import MixinBase
from lol_coach.gui.virtual_rows import VirtualRows
from lol_coach.log import get_logger
from lol_coach.static.icons import champion_ctk

_log = get_logger("tierlist")

# 티어 → 표시 색
_TIER_COLOR = {1: ui.GOLD, 2: ui.BLUE_SOFT, 3: ui.TEXT_BRIGHT, 4: ui.TEXT_DIM, 5: ui.TEXT_MUTE}


def _build_tierlist_rows(
    entries: list[tuple[int, str, str]], *, columns: int = 9
) -> list[tuple[str, int, Any]]:
    """Flatten tier groups into header/champion rows for viewport rendering."""
    rows: list[tuple[str, int, Any]] = []
    for tier in (1, 2, 3, 4, 5):
        group = [entry for entry in entries if entry[0] == tier]
        if not group:
            continue
        rows.append(("header", tier, len(group)))
        for start in range(0, len(group), max(1, columns)):
            rows.append(("chips", tier, group[start : start + max(1, columns)]))
    return rows


class TierListMixin(MixinBase):
    """CoachApp 에 섞이는 아수라장 티어표 페이지 (self.t_tierlist 소유)."""

    def _build_tierlist(self) -> None:
        self._tierlist_loaded = False
        t = self.t_tierlist
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        from customtkinter import CTkScrollableFrame

        card = ctk.CTkFrame(
            t,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        card.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        ctk.CTkLabel(
            head,
            text="아수라장 티어표",
            font=FS,
            text_color=ui.TEXT_BRIGHT,
            anchor="w",
        ).pack(side="left")
        self._tierlist_meta = ctk.CTkLabel(head, text="", font=FM, text_color=ui.TEXT_DIM)
        self._tierlist_meta.pack(side="left", padx=10)
        ctk.CTkButton(
            head,
            text="새로고침",
            width=80,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._load_tierlist,
        ).pack(side="right")
        self._tierlist_status = ctk.CTkLabel(
            card,
            text="페이지를 열면 blitz.gg 실시간 티어를 불러옵니다.",
            font=FM,
            text_color=ui.TEXT_DIM,
            anchor="w",
        )
        self._tierlist_status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        self._tierlist_body = CTkScrollableFrame(t, fg_color=ui.PANEL, corner_radius=12)
        self._tierlist_body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._tierlist_body.grid_columnconfigure(0, weight=1)

    def _load_tierlist(self) -> None:
        """전체 챔피언 티어 조회 → 렌더 (비동기)."""
        if self._is_busy("tierlist_load"):
            return
        client = getattr(self, "blitz", None)
        self._busy_set(True, None, "", key="tierlist_load")
        self._tierlist_status.configure(text="blitz.gg 티어 조회 중…")

        def work() -> None:
            res = None
            try:
                res = fetch_mayhem_champion_tiers(client)
            except Exception as exc:
                _log.info("티어표 조회 실패: %s", exc)
            entries: list[tuple[int, str, str]] = []  # (티어, 한글명, 챔피언 key)
            patch = updated = ""
            if res is not None:
                patch, updated, tiers = res
                for cid, tier in tiers.items():
                    try:
                        key = self.dd.champion_key(int(cid))
                        c = self.dd.resolve_champion(key)
                        ko = str(c["name"]) if c else key
                    except Exception:
                        key, ko = str(cid), str(cid)
                    entries.append((tier, ko, key))
            entries.sort(key=lambda e: (e[0], e[1]))

            # 아이콘 선(先) 다운로드 — 메인 스레드는 네트워크 조회를 못 하므로
            # 캐시에 없던 챔피언(예: 닐라·렉사이)은 워커에서 미리 받아둔다.
            from lol_coach.static.icons import champion_pil

            for _tier, _ko, key in entries:
                try:
                    champion_pil(key, 28)
                except Exception:
                    continue

            def finish() -> None:
                self._busy_set(False, None, "", key="tierlist_load")
                self._render_tierlist(patch, updated, entries)
                self._tierlist_loaded = True

            self.after(0, finish)

        self._spawn_thread(work)

    def _render_tierlist(
        self,
        patch: str,
        updated: str,
        entries: list[tuple[int, str, str]],
    ) -> None:
        body = self._tierlist_body
        self._clear(body)
        self._tierlist_rows = None
        self._render_target = body
        if not entries:
            self._lbl(
                body,
                "티어를 불러오지 못했습니다.\n네트워크를 확인하고 새로고침을 눌러 주세요.",
                0,
                color=ui.TEXT_DIM,
                pady=12,
            )
            try:
                self._tierlist_status.configure(text="조회 실패")
            except Exception:
                pass
            return
        try:
            self._tierlist_meta.configure(text=f"패치 {patch} · 데이터 {updated}")
        except Exception:
            pass
        rows = _build_tierlist_rows(entries)
        virtual = VirtualRows(
            body,
            row_height=lambda row: 46 if row[0] == "header" else 78,
            render_row=lambda slot, row, _index: self._render_tier_row(slot, row),
            overscan=2,
        )
        virtual.grid(row=0, column=0, sticky="ew")
        virtual.set_items(rows)
        self._tierlist_rows = virtual
        try:
            self._tierlist_status.configure(text=f"{len(entries)}챔프 · blitz.gg 실시간 티어")
        except Exception:
            pass

    def _render_tier_row(self, slot: Any, row: tuple[str, int, Any]) -> None:
        """Reuse the header or nine champion chips inside a viewport slot."""
        slot.grid_columnconfigure(0, weight=1)
        kind, tier, payload = row
        header = getattr(slot, "_tier_header", None)
        grid = getattr(slot, "_tier_grid", None)
        if kind == "header":
            if grid is not None:
                ui.release_images(grid)
                grid.grid_remove()
            if header is None:
                header = tk.Frame(slot, bg=slot.cget("bg"), highlightthickness=0)
                bar = ctk.CTkFrame(header, width=5, height=20, corner_radius=2)
                bar.pack(side="left", padx=(0, 10))
                bar.pack_propagate(False)
                title = ctk.CTkLabel(header, text="", font=FS, anchor="w")
                title.pack(side="left")
                count = ctk.CTkLabel(header, text="", font=FM, text_color=ui.TEXT_DIM)
                count.pack(side="left")
                slot._tier_header = header
                slot._tier_header_parts = (bar, title, count)
            header.grid(row=0, column=0, sticky="ew", padx=6, pady=(14, 4))
            bar, title, count = slot._tier_header_parts
            bar.configure(fg_color=_TIER_COLOR[tier])
            title.configure(text=f"티어 {tier}", text_color=_TIER_COLOR[tier])
            count.configure(text=f"  {payload}챔프")
            return

        if header is not None:
            header.grid_remove()
        if grid is None:
            grid = tk.Frame(slot, bg=slot.cget("bg"), highlightthickness=0)
            slot._tier_grid = grid
            slot._tier_chips = []
            for i in range(9):
                grid.grid_columnconfigure(i, weight=1, uniform="tier")
                chip = ctk.CTkFrame(grid, fg_color=ui.ROW, corner_radius=ui.ROW_RADIUS,
                                    border_width=ui.CARD_BORDER, border_color=ui.BORDER)
                chip.grid(row=0, column=i, sticky="nsew", padx=3, pady=3)
                # 아이콘·이름을 Tk 라벨로 — 칩당 네이티브 창 8개 → 4개
                icon = ui.TextLabel(chip, anchor="center")
                icon.pack(pady=(6, 0))
                name = ui.TextLabel(chip, font=FM, anchor="center", justify="center")
                name.pack(pady=(0, 6))
                slot._tier_chips.append((chip, icon, name))
        grid.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 4))
        for i, (chip, icon, name) in enumerate(slot._tier_chips):
            if i >= len(payload):
                icon.set_image(None)
                chip.grid_remove()
                continue
            _tier, ko, key = payload[i]
            chip.grid()
            icon.set_image(champion_ctk(key, 28))
            if name.cget("text") != ko[:8]:
                name.configure(text=ko[:8])
