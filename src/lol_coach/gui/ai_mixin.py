"""선택형 AI 코칭 카드·키·모델

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from lol_coach.config import load_settings, save_llm_key, save_llm_model
from lol_coach.gui import components as ui
from lol_coach.gui.ai_text import ai_key_points as _ai_key_points
from lol_coach.gui.ai_text import ai_lines as _ai_lines
from lol_coach.gui.constants import (
    AI_BODY,
    AI_SECTION,
    AI_SUMMARY,
    AI_TITLE,
)


class AiMixin:
    def _ai_key(self) -> str:
        from lol_coach import llm

        manual = vars(self).get("llm_key_var")
        explicit = manual.get().strip() if manual is not None else ""
        return llm.resolve_api_key(explicit)


    def _save_llm_key(self) -> None:
        from lol_coach.config import save_llm_key, save_llm_model

        save_llm_key(self.llm_key_var.get())
        save_llm_model(self.llm_model_var.get())
        self.settings = load_settings()
        self._refresh_ai_status()
        self.status.configure(text="AI 코칭 설정 저장됨")


    def _ai_model(self) -> str:
        from lol_coach import llm as _llm

        var = vars(self).get("llm_model_var")
        model = var.get().strip() if var is not None else ""
        return model or _llm.DEFAULT_MODEL


    def _refresh_ai_status(self) -> None:
        try:
            if self._ai_key():
                manual = self.llm_key_var.get().strip()
                src = "수동 키" if manual else "자동 감지 (opencode)"
                self.ai_status_lbl.configure(
                    text=f"✓ AI 코칭 활성 — {src} · {self._ai_model()}",
                    text_color=ui.GREEN,
                )
            else:
                self.ai_status_lbl.configure(
                    text="AI 미설정 — 규칙 기반 결과", text_color=ui.TEXT_DIM
                )
        except Exception:
            pass


    def _ai_header(self, card: Any) -> None:
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 2))
        bar = ctk.CTkFrame(head, width=3, height=18, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 8))
        bar.pack_propagate(False)
        ctk.CTkLabel(
            head,
            text="🤖 AI 코칭",
            font=AI_TITLE,
            text_color=ui.GOLD_SOFT,
        ).pack(side="left")


    def _append_ai_card(self, frame: Any) -> Any:
        """결과 맨 위에 골드 보더 AI 카드 삽입 (스크롤 없이 바로 보이게)."""
        for w in frame.winfo_children():
            info = w.grid_info()
            row = info.get("row")
            if row is not None:
                try:
                    w.grid_configure(row=int(row) + 1)
                except Exception:
                    pass
        card = ctk.CTkFrame(
            frame, fg_color=ui.CARD, corner_radius=12, border_width=2, border_color=ui.GOLD
        )
        card.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 6))
        self._ai_header(card)
        ctk.CTkLabel(
            card,
            text="AI 코칭 생성 중…",
            font=AI_SUMMARY,
            text_color=ui.TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=920,
        ).pack(fill="x", padx=12, pady=(2, 10))

        # llm.chat 기본 45s × 최대 3회 + 여유 — 너무 이른 UI 실패 방지
        from lol_coach import llm as _llm

        ui_timeout_ms = int(
            (_llm.DEFAULT_TIMEOUT_S * _llm.DEFAULT_MAX_ATTEMPTS + 15) * 1000
        )

        def _timeout() -> None:
            try:
                if not card.winfo_exists():
                    return
                # 아직 생성 중이면 안내만 (늦은 성공 응답이 덮어쓸 수 있음)
                gen = getattr(card, "_ai_gen", None)
                if gen is not None and gen != self._ai_gen:
                    return
                self._apply_ai_card(card, None, gen=gen)
            except Exception:
                pass

        card._ai_timeout_id = self.after(ui_timeout_ms, _timeout)
        return card


    def _push_ai_to_widget(self, text: str) -> None:
        """AI 코칭 결과를 미니 위젯 요약에 추가 (스크롤 없이 바로 확인)."""
        try:
            lines = list(self._last_summary_lines)
            lines.append("")
            lines.append("🤖 AI 코칭 · 핵심")
            lines += [f"• {line}" for line in _ai_key_points(text)]
            self._push_summary(self._last_summary_title, lines)
        except Exception:
            pass


    def _apply_ai_card(
        self, card: Any, text: str | None, *, gen: int | None = None
    ) -> None:
        """AI 카드 내용 채우기 — 실패/빈 결과면 안내만 남긴다."""
        if card is None:
            return
        # 더 최신 요청이 있으면 늦은 응답 무시
        if gen is not None and gen != getattr(self, "_ai_gen", gen):
            return
        card_gen = getattr(card, "_ai_gen", None)
        if card_gen is not None and gen is not None and card_gen != gen:
            return
        try:
            if not card.winfo_exists():
                return
        except Exception:
            return
        timeout_id = getattr(card, "_ai_timeout_id", None)
        if timeout_id is not None:
            try:
                self.after_cancel(timeout_id)
            except Exception:
                pass
            card._ai_timeout_id = None
        for w in card.winfo_children():
            w.destroy()
        self._ai_header(card)
        if text:
            lines = _ai_lines(text)
            # 핵심은 짧게(최대 3), 상세 본문이 화면의 주인공
            key_points = _ai_key_points(text, limit=3)
            details = [line for line in lines if line not in key_points]
            # 상세가 비면 전체 줄을 본문으로
            if not details:
                details = list(lines)

            # 1) 상세 코칭 (큰 글씨 · 넉넉한 줄간격)
            ctk.CTkLabel(
                card,
                text="상세 코칭",
                font=AI_SECTION,
                text_color=ui.GOLD,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(4, 4))
            for line in details:
                ctk.CTkLabel(
                    card,
                    text=f"• {line}",
                    font=AI_BODY,
                    text_color=ui.TEXT_BRIGHT,
                    anchor="w",
                    justify="left",
                    wraplength=920,
                ).pack(fill="x", padx=14, pady=4)

            # 2) 핵심 요약은 아래에 작게
            if key_points:
                ctk.CTkLabel(
                    card,
                    text="핵심 한줄",
                    font=AI_SECTION,
                    text_color=ui.GOLD_SOFT,
                    anchor="w",
                ).pack(fill="x", padx=12, pady=(10, 2))
                for line in key_points:
                    ctk.CTkLabel(
                        card,
                        text=f"· {line}",
                        font=AI_SUMMARY,
                        text_color=ui.TEXT_DIM,
                        anchor="w",
                        justify="left",
                        wraplength=920,
                    ).pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(card, text="", font=AI_SUMMARY).pack(pady=(0, 6))
            self._push_ai_to_widget(text)
        else:
            ctk.CTkLabel(
                card,
                text="AI 코칭 생성 실패 — 규칙 기반 결과를 참고하세요 (키·네트워크·게이트웨이 확인)",
                font=AI_SUMMARY,
                text_color=ui.TEXT_DIM,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(2, 10))


    def _maybe_ai(self, frame: Any, builder: Any) -> None:
        """LLM 키가 있으면 AI 카드 부착 + 백그라운드 생성, 없으면 무시."""
        key = self._ai_key()
        if not key:
            return
        self._ai_gen += 1
        gen = self._ai_gen
        card = self._append_ai_card(frame)
        card._ai_gen = gen

        def work() -> None:
            text = builder()
            self.after(0, lambda: self._apply_ai_card(card, text, gen=gen))

        threading.Thread(target=work, daemon=True).start()


    def _ai_coach_lane(self, advice: Any, lane_ko: str, role: str, key: str) -> str | None:
        from lol_coach import llm
        from lol_coach.ugg.counters import ROLE_KO

        return llm.coach_lane(
            lane_ko,
            ROLE_KO.get(role, role),
            advice.counters,
            advice.patch,
            api_key=key,
            model=self._ai_model(),
        )


    def _ai_coach_comp(self, rep: Any, matchup: list[str], key: str) -> str | None:
        from lol_coach import llm

        return llm.coach_comp(
            rep.my_champ_ko,
            rep.my_role,
            rep.enemy_team,
            rep.counters,
            rep.threats,
            rep.midgame,
            rep.situational,
            rep.patch,
            api_key=key,
            model=self._ai_model(),
        )


    def _ai_coach_aram(self, adv: Any, key: str) -> str | None:
        from lol_coach import llm

        fill = getattr(self, "_aram_live_fill", None)
        allies = [ko for _k, ko in fill.allies] if fill else []
        enemies = []
        if fill:
            enemies = [ko for _k, ko in fill.enemies_by_role.values()]
            enemies += [ko for _k, ko in fill.enemies_extra]
        augs = ", ".join(f"{p.name_ko}({p.tier or '?'})" for p in adv.top_augments[:5])
        if adv.avoid_augments:
            augs += " | 피할: " + ", ".join(p.name_ko for p in adv.avoid_augments[:3])
        build = " → ".join(adv.core_slots[:5]) or ""
        if adv.spells_line:
            build += f" · 스펠 {adv.spells_line}"
        return llm.coach_aram(
            adv.champ_ko,
            allies,
            enemies,
            augs,
            build,
            adv.patch,
            api_key=key,
            model=self._ai_model(),
        )


    def _ai_coach_review(self, m: Any, rev: Any, key: str) -> str | None:
        from lol_coach import llm

        return llm.coach_review(m, rev, api_key=key, model=self._ai_model())

