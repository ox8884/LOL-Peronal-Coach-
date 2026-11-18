"""아수라장 티어표 탭 — 전체 챔피언 티어 보드 (lol.ps 우선, 없으면 blitz.gg).

챔프 선택 전 참고 + 리롤 판단용. 티어 S(강)~C(약)를 먹의 농담으로 구분해
챔피언 아이콘 그리드로 표시한다.
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.aram_mayhem import tier_letter
from lol_coach.blitz.mayhem_live import fetch_mayhem_champion_tiers
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FS
from lol_coach.gui.types import MixinBase
from lol_coach.gui.virtual_rows import VirtualRows
from lol_coach.log import get_logger
from lol_coach.static.icons import champion_ctk

_log = get_logger("tierlist")

# 티어 → 표시 색
_TIER_COLOR = {1: ui.INK, 2: "#4A483F", 3: "#77746A", 4: "#A6A192", 5: "#CFCAB6"}


def _build_tierlist_rows(
    entries: list[tuple[Any, ...]], *, columns: int = 9
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
            text="페이지를 열면 lol.ps 아수라장 티어를 불러옵니다.",
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
        self._tierlist_status.configure(text="티어 조회 중…")

        def work() -> None:
            res: tuple[str, str, list[tuple[int, int, str]]] | None = None
            try:
                from lol_coach import lolps

                board = lolps.tier_board()
                if board is not None:
                    # lol.ps 티어판 그대로 — 빌드 유형마다 한 칸, 사이트와 같은 순서
                    res = (board[0], board[1], [(t, cid, build) for t, cid, build, _win in board[2]])
                    self._tierlist_source = "lol.ps"
                else:
                    blitz = fetch_mayhem_champion_tiers(client)
                    if blitz is not None:
                        res = (blitz[0], blitz[1], sorted((t, cid, "") for cid, t in blitz[2].items()))
                    self._tierlist_source = "blitz.gg"
            except Exception as exc:
                _log.info("티어표 조회 실패: %s", exc)
            entries: list[tuple[int, str, str, str]] = []  # (티어, 한글명, 챔피언 key, 빌드 유형)
            patch = updated = ""
            if res is not None:
                patch, updated, board_rows = res
                for tier, cid, build in board_rows:
                    try:
                        key = self.dd.champion_key(int(cid))
                        c = self.dd.resolve_champion(key)
                        ko = str(c["name"]) if c else key
                    except Exception:
                        key, ko = str(cid), str(cid)
                    entries.append((tier, ko, key, build))

            # 아이콘 선(先) 다운로드 — 메인 스레드는 네트워크 조회를 못 하므로
            # 캐시에 없던 챔피언(예: 닐라·렉사이)은 워커에서 미리 받아둔다.
            from lol_coach.static.icons import champion_pil

            for _tier, _ko, key, _build in entries:
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
        entries: list[tuple[Any, ...]],
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
            row_height=lambda row: 46 if row[0] == "header" else 88,
            render_row=lambda slot, row, _index: self._render_tier_row(slot, row),
            overscan=2,
        )
        virtual.grid(row=0, column=0, sticky="ew")
        virtual.set_items(rows)
        self._tierlist_rows = virtual
        try:
            self._tierlist_status.configure(
                text=f"{len(entries)}칸 · {getattr(self, '_tierlist_source', 'blitz.gg')} 티어판"
                " (빌드 유형마다 한 칸)"
            )
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
                # Tk 기본 위젯 3개 (CTk 로는 창 8개)
                scale = ctk.ScalingTracker.get_widget_scaling(slot)
                bar = tk.Frame(
                    header, width=round(14 * scale), height=round(20 * scale), highlightthickness=0
                )
                bar.pack(side="left", padx=(0, round(10 * scale)))
                title = ui.TextLabel(header, font=FS, padx=round(5 * scale))
                title.pack(side="left")
                count = ui.TextLabel(header, font=FM, text_color=ui.TEXT_DIM)
                count.pack(side="left")
                slot._tier_header = header
                slot._tier_header_parts = (bar, title, count)
            header.grid(row=0, column=0, sticky="ew", padx=6, pady=(14, 4))
            bar, title, count = slot._tier_header_parts
            bar.configure(bg=_TIER_COLOR[tier])
            # 1티어 제목에만 형광펜
            title.configure(text=tier_letter(tier), text_color=ui.INK,
                            bg=ui.YELLOW if tier == 1 else slot.cget("bg"))
            count.configure(text=f"  {payload}칸")
            return

        if header is not None:
            header.grid_remove()
        if grid is None:
            grid = tk.Frame(slot, bg=slot.cget("bg"), highlightthickness=0)
            slot._tier_grid = grid
            slot._tier_chips = []
            for i in range(9):
                grid.grid_columnconfigure(i, weight=1, uniform="tier")
                # 아이콘 위 + 이름 아래를 TextLabel 1개로 — 칩당 네이티브 창 4개 → 1개
                chip = ui.TextLabel(
                    grid,
                    font=FM,
                    anchor="center",
                    justify="center",
                    compound="top",
                    min_height=40,  # 아이콘 위아래 여백 — 이름과 빌드 유형 두 줄이 들어간다
                    bg=ui.ROW,
                    highlightthickness=1,
                    highlightbackground=ui.BORDER,
                    highlightcolor=ui.BORDER,
                    cursor="hand2",
                )
                chip.grid(row=0, column=i, sticky="nsew", padx=3, pady=3)
                chip.bind("<Button-1>", partial(self._tier_chip_click, slot, i))
                slot._tier_chips.append(chip)
        grid.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 4))
        slot._tier_payload = payload
        for i, chip in enumerate(slot._tier_chips):
            if i >= len(payload):
                chip.set_image(None)
                chip.grid_remove()
                continue
            _tier, ko, key, *rest = payload[i]
            build = rest[0] if rest else ""  # 빌드 유형이 없는 자료(blitz)도 받는다
            chip.grid()
            chip.set_image(champion_ctk(key, 28))
            label = f"{ko[:8]}\n{build}" if build else ko[:8]
            if chip.cget("text") != label:
                chip.configure(text=label)

    def _tier_chip_click(self, slot: Any, index: int, _event: Any = None) -> None:
        """티어표 챔피언 클릭 → 아수라장 브리핑으로 바로 이동."""
        payload = getattr(slot, "_tier_payload", ())
        if index >= len(payload):
            return
        ko = payload[index][1]
        self.tabs.set("ARAM 아수라장")
        self.aram_tab.aram_champ_var.set(ko)
        self.aram_tab._run_aram()
