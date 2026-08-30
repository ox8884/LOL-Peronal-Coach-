"""아수라장 티어표 탭 — 전체 173챔피언의 blitz.gg 실시간 티어 보드.

챔프 선택 전 참고 + 리롤 판단용. 티어 1(강)~5(약)를 색으로 구분해
챔피언 아이콘 그리드로 표시한다.
"""

from __future__ import annotations

import customtkinter as ctk

from lol_coach.blitz.mayhem_live import fetch_mayhem_champion_tiers
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FS
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger
from lol_coach.static.icons import champion_ctk

_log = get_logger("tierlist")

# 티어 → 표시 색
_TIER_COLOR = {1: ui.GOLD, 2: ui.BLUE_SOFT, 3: ui.TEXT_BRIGHT, 4: ui.TEXT_DIM, 5: ui.TEXT_MUTE}


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
        r = 0
        columns = 9
        for tier in (1, 2, 3, 4, 5):
            group = [e for e in entries if e[0] == tier]
            if not group:
                continue
            head = ctk.CTkFrame(body, fg_color="transparent")
            head.grid(row=r, column=0, sticky="ew", padx=6, pady=(14, 4))
            r += 1
            bar = ctk.CTkFrame(
                head, width=5, height=20, corner_radius=2, fg_color=_TIER_COLOR[tier]
            )
            bar.pack(side="left", padx=(0, 10))
            bar.pack_propagate(False)
            ctk.CTkLabel(
                head,
                text=f"티어 {tier}",
                font=FS,
                text_color=_TIER_COLOR[tier],
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(head, text=f"  {len(group)}챔프", font=FM, text_color=ui.TEXT_DIM).pack(
                side="left"
            )
            grid = ctk.CTkFrame(body, fg_color="transparent")
            grid.grid(row=r, column=0, sticky="ew", padx=6, pady=(0, 4))
            r += 1
            for i, (_tier, ko, key) in enumerate(group):
                grid.grid_columnconfigure(i % columns, weight=1, uniform="tier")
                chip = ctk.CTkFrame(
                    grid,
                    fg_color=ui.ROW,
                    corner_radius=ui.ROW_RADIUS,
                    border_width=ui.CARD_BORDER,
                    border_color=ui.BORDER,
                )
                chip.grid(row=i // columns, column=i % columns, sticky="nsew", padx=3, pady=3)
                ic = self._keep_icon(champion_ctk(key, 28))
                if ic:
                    ctk.CTkLabel(chip, image=ic, text="").pack(pady=(6, 0))
                ctk.CTkLabel(chip, text=ko[:8], font=FM, text_color=ui.TEXT).pack(pady=(0, 6))
        try:
            self._tierlist_status.configure(text=f"{len(entries)}챔프 · blitz.gg 실시간 티어")
        except Exception:
            pass
