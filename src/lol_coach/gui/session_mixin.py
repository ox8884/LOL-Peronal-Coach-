"""세션 리포트 탭 — 오늘 하루 플레이 요약 페이지.

Riot API에서 오늘(로컬 날짜) 경기를 직접 조회해 analysis.session 으로
요약한다. Riot 클라이언트가 없으면(키 미설정/로컬 모드) 이미 로드된
전적(self._me_form_full)에서 오늘 경기만 골라 보여준다.
"""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from lol_coach.analysis.session import SessionReport, analyze_session, local_midnight_epoch
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FNUM, FS
from lol_coach.riot.models import MatchSummary


class SessionMixin:
    """CoachApp 에 섞이는 세션 리포트 페이지 (self.t_session 소유)."""

    def _build_session(self) -> None:
        self._session_loaded = False
        t = self.t_session
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(
            t,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        top.grid_columnconfigure(0, weight=1)
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        ctk.CTkLabel(
            row,
            text="오늘의 세션",
            font=FS,
            text_color=ui.TEXT_BRIGHT,
            anchor="w",
        ).pack(side="left")
        self._session_date_lbl = ctk.CTkLabel(row, text="", font=FM, text_color=ui.TEXT_DIM)
        self._session_date_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            row,
            text="새로고침",
            width=80,
            height=28,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._load_session,
        ).pack(side="right")
        self._session_status = ctk.CTkLabel(
            top,
            text="페이지를 열면 오늘 경기를 불러옵니다.",
            font=FM,
            text_color=ui.TEXT_DIM,
            anchor="w",
        )
        self._session_status.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

        from customtkinter import CTkScrollableFrame

        self._session_body = CTkScrollableFrame(t, fg_color=ui.PANEL, corner_radius=12)
        self._session_body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self._session_body.grid_columnconfigure(0, weight=1)

    def _load_session(self) -> None:
        """오늘 경기 조회 → 렌더 (비동기)."""
        if self._is_busy("session_load"):
            return
        client = getattr(self, "riot", None)
        profile = getattr(self, "profile", None)
        form_full = getattr(self, "_me_form_full", None)
        if client is None or profile is None:
            # 로컬/프로필 미로드 — 이미 로드된 전적에서 오늘만 추출
            matches = list(form_full.matches) if form_full is not None else []
            self._render_session(analyze_session(matches), source="로드된 전적 기준")
            self._session_loaded = True
            return
        self._busy_set(True, None, "", key="session_load")
        self._session_status.configure(text="오늘 경기 조회 중…")

        def work() -> None:
            matches: list[MatchSummary] = []
            source = "Riot API 오늘 조회"
            try:
                start = local_midnight_epoch()
                ids = client.get_match_ids(profile.puuid, count=30, start_time=start)
                for mid in ids:
                    try:
                        raw = client.get_match(mid)
                        s = client.summarize_match(
                            raw,
                            profile.puuid,
                            game_name=profile.game_name,
                            tag_line=profile.tag_line,
                        )
                        if s is not None:
                            matches.append(s)
                    except Exception:
                        continue
            except Exception as exc:
                matches = []
                source = f"조회 실패: {exc}"
            # 보조: 이미 로드된 전적에 오늘 경기가 더 있으면 병합
            if form_full is not None:
                seen = {m.match_id for m in matches}
                matches += [m for m in form_full.matches if m.match_id not in seen]

            def finish() -> None:
                self._busy_set(False, None, "", key="session_load")
                self._render_session(analyze_session(matches), source=source)
                self._session_loaded = True

            self.after(0, finish)

        self._spawn_thread(work)

    def _kpi(
        self,
        parent: Any,
        row: int,
        col: int,
        value: str,
        label: str,
        color: str | None = None,
    ) -> None:
        """KPI 셀 — 큰 디스플레이 숫자 + 작은 라벨."""
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=row, column=col, sticky="ew", padx=8, pady=2)
        ctk.CTkLabel(cell, text=value, font=FNUM(24), text_color=color or ui.TEXT_BRIGHT).pack(
            anchor="w"
        )
        ctk.CTkLabel(cell, text=label, font=FM, text_color=ui.TEXT_DIM).pack(anchor="w")

    def _render_session(self, report: SessionReport, *, source: str = "") -> None:
        body = self._session_body
        self._clear(body)
        self._render_target = body
        try:
            self._session_date_lbl.configure(text=report.day)
        except Exception:
            pass
        r = 0
        if not report.matches:
            r = self._lbl(
                body,
                "오늘 기록된 경기가 없습니다.\n경기를 즐긴 뒤 새로고침을 눌러 주세요.",
                r,
                color=ui.TEXT_DIM,
                pady=12,
            )
            try:
                self._session_status.configure(text=f"{source} · 경기 없음")
            except Exception:
                pass
            return

        # KPI 행
        kpis = ctk.CTkFrame(body, fg_color=ui.ROW, corner_radius=ui.ROW_RADIUS)
        kpis.grid(row=r, column=0, sticky="ew", padx=6, pady=(8, 4))
        r += 1
        kpis.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._kpi(kpis, 0, 0, str(len(report.matches)), "게임")
        self._kpi(
            kpis,
            0,
            1,
            f"{report.wins}승 {report.losses}패",
            "전적",
            color=ui.GREEN if report.wins >= report.losses else ui.RED_SOFT,
        )
        self._kpi(kpis, 0, 2, f"{report.winrate}%", "승률")
        self._kpi(kpis, 0, 3, f"{report.avg_kda}", "평균 KDA")

        for line in report.lines[1:]:  # 첫 줄은 KPI가 대체
            r = self._lbl(body, line, r, pady=2, wrap=640)
        if report.worst is not None:
            w = report.worst
            r = self._sec(body, "다시 보면 좋은 경기", r)
            r = self._lbl(
                body,
                f"{w.champion_name} {w.kda_str} · {w.duration_min}분 — "
                "복기 카드에서 원인을 확인해 보세요.",
                r,
                color=ui.TEXT,
                pady=2,
                wrap=640,
            )
            ctk.CTkButton(
                body,
                text="복기 열기",
                width=90,
                height=28,
                font=FM,
                **ui.btn(*ui.BTN_SECONDARY),
                command=lambda m=w: (
                    self._select_nav("내 전적"),
                    self.me_tab.show_match(m),
                ),
            ).grid(row=r, column=0, sticky="w", padx=10, pady=6)
            r += 1
        # 요약 → 미니 위젯에도 푸시 (인게임 오버레이용)
        try:
            self._push_summary(f"오늘 세션 · {report.day}", report.lines)
        except Exception:
            pass
        try:
            self._session_status.configure(text=f"{source} · {len(report.matches)}경기")
        except Exception:
            pass
