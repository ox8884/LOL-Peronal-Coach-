"""선택형 AI 코칭 카드·키·모델

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from lol_coach.config import (
    load_settings,
    save_llm_key,
    save_llm_model,
    save_llm_provider,
)
from lol_coach.gui import components as ui
from lol_coach.gui.ai_text import ai_key_points as _ai_key_points
from lol_coach.gui.ai_text import ai_lines as _ai_lines
from lol_coach.gui.constants import (
    AI_BODY,
    AI_SECTION,
    AI_SUMMARY,
    AI_TITLE,
)
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger

_log = get_logger("ai")


class AiMixin(MixinBase):
    def _ai_provider(self) -> str:
        from lol_coach import llm

        var = vars(self).get("llm_provider_var")
        raw = var.get().strip() if var is not None else ""
        return llm.normalize_provider(raw)

    def _ai_key(self) -> str:
        from lol_coach import llm

        manual = vars(self).get("llm_key_var")
        explicit = manual.get().strip() if manual is not None else ""
        return llm.resolve_api_key(explicit, provider=self._ai_provider())

    def _save_llm_key(self) -> None:
        from lol_coach import llm

        pid = self._ai_provider()
        save_llm_provider(pid)
        save_llm_key(self.llm_key_var.get(), provider=pid)
        save_llm_model(self.llm_model_var.get())
        self.settings = load_settings()
        self._refresh_ai_status()
        name = llm.get_provider(pid).name
        self.status.configure(text=f"{name} API 키 저장됨")

    def _on_llm_provider_change(self, pid: str) -> None:
        from lol_coach import llm

        prev = str(getattr(self, "_llm_provider_prev", "") or "")
        nxt = llm.normalize_provider(pid)
        if prev and prev != nxt:
            save_llm_key(self.llm_key_var.get(), provider=prev)
        self._llm_provider_prev = nxt
        save_llm_provider(nxt)
        self.llm_key_var.set(load_settings().llm_api_key)
        prov = llm.get_provider(nxt)
        if self.llm_model_var.get().strip() not in prov.models:
            self.llm_model_var.set(prov.default_model)
        save_llm_model(self.llm_model_var.get())
        self.settings = load_settings()
        self._refresh_ai_status()
        refresh = getattr(self, "_refresh_llm_provider_ui", None)
        if callable(refresh):
            refresh()

    def _test_llm_connection(self) -> None:
        """설정에 적은 API 키로 게이트웨이를 한 번 두드린다."""
        from lol_coach import llm

        self._save_llm_key()
        prov = llm.get_provider(self._ai_provider())
        lbl = getattr(self, "ai_status_lbl", None)
        if lbl is not None:
            try:
                lbl.configure(text=f"{prov.name} 연결 확인 중…", text_color=ui.TEXT_DIM)
            except Exception:
                pass

        def work() -> None:
            ok, msg = llm.probe_gateway(
                self._ai_key(),
                self._ai_model(),
                provider=prov.id,
            )

            def done() -> None:
                self._notify(msg, level="ok" if ok else "warn", ms=4200)
                self._refresh_ai_status()

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _start_openrouter_oauth(self) -> None:
        """브라우저에서 OpenRouter 로그인 → 키 저장."""
        from lol_coach import llm

        if getattr(self, "_llm_oauth_busy", False):
            self._notify("이미 브라우저 로그인을 기다리는 중입니다", level="warn", ms=2800)
            return
        self.llm_provider_var.set("openrouter")
        self._on_llm_provider_change("openrouter")
        self._llm_oauth_busy = True
        lbl = getattr(self, "ai_status_lbl", None)
        if lbl is not None:
            try:
                lbl.configure(text="브라우저에서 OpenRouter 로그인…", text_color=ui.TEXT_DIM)
            except Exception:
                pass
        self._notify("브라우저에서 OpenRouter 로그인을 완료하세요", level="ok", ms=4200)

        def work() -> None:
            ok, val = llm.run_openrouter_oauth()

            def done() -> None:
                self._llm_oauth_busy = False
                if ok:
                    self.llm_key_var.set(val)
                    self._save_llm_key()
                    self._notify("OpenRouter 연결됨", level="ok", ms=4200)
                else:
                    self._notify(val, level="warn", ms=5200)
                self._refresh_ai_status()

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _ai_model(self) -> str:
        from lol_coach import llm as _llm

        var = vars(self).get("llm_model_var")
        model = var.get().strip() if var is not None else ""
        if model:
            return model
        return _llm.get_provider(self._ai_provider()).default_model

    def _refresh_ai_status(self) -> None:
        from lol_coach import llm

        lbl = getattr(self, "ai_status_lbl", None)
        if lbl is None:
            return
        try:
            prov = llm.get_provider(self._ai_provider())
            if self._ai_key():
                manual = self.llm_key_var.get().strip()
                if manual:
                    src = "API 키"
                elif prov.detect_opencode:
                    src = "CLI 자동 감지"
                else:
                    src = "저장 키"
                lbl.configure(
                    text=f"✓ {prov.name} 활성 — {src} · {self._ai_model()}",
                    text_color=ui.GREEN,
                )
            else:
                lbl.configure(
                    text=f"{prov.name} API 키 없음 — 규칙 기반 결과",
                    text_color=ui.TEXT_DIM,
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
            frame,
            fg_color=ui.CARD,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        # 결과 목록 최상단 · 가로 풀
        card.grid(row=0, column=0, sticky="nsew", padx=6, pady=(4, 8))
        self._ai_header(card)
        ctk.CTkLabel(
            card,
            text="AI 상세 코칭 생성 중… (잠시만요)",
            font=AI_BODY,
            text_color=ui.TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=940,
        ).pack(fill="x", padx=12, pady=(8, 16))

        # llm.chat 기본 45s × 최대 3회 + 여유 — 너무 이른 UI 실패 방지
        from lol_coach import llm as _llm

        ui_timeout_ms = int((_llm.DEFAULT_TIMEOUT_S * _llm.DEFAULT_MAX_ATTEMPTS + 15) * 1000)

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

    def _apply_ai_card(self, card: Any, text: str | None, *, gen: int | None = None) -> None:
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
            key_points = _ai_key_points(text, limit=3)
            details = [line for line in lines if line not in key_points]
            if not details:
                details = list(lines)

            ctk.CTkLabel(
                card,
                text="상세 코칭",
                font=AI_SECTION,
                text_color=ui.GOLD,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(6, 4))

            # 큰 글씨 + 고정 높이 텍스트박스 (스크롤 가능, 가독성 최우선)
            body = "\n\n".join(f"• {line}" for line in details)
            # 줄 수에 따라 높이 (1~5코어 포함 시 여유 있게, 최대 640px)
            est_h = min(640, max(280, 48 + len(details) * 38))
            box = ctk.CTkTextbox(
                card,
                height=est_h,
                font=AI_BODY,
                fg_color=ui.PANEL,
                text_color=ui.TEXT_BRIGHT,
                border_width=1,
                border_color=ui.BORDER,
                corner_radius=ui.ROW_RADIUS,
                wrap="word",
                activate_scrollbars=True,
            )
            box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
            box.insert("1.0", body)
            box.configure(state="disabled")

            if key_points:
                ctk.CTkLabel(
                    card,
                    text="핵심 · " + "  |  ".join(key_points),
                    font=AI_SUMMARY,
                    text_color=ui.TEXT_DIM,
                    anchor="w",
                    justify="left",
                    wraplength=940,
                ).pack(fill="x", padx=12, pady=(0, 8))
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
            try:
                text = builder()
            except Exception as exc:
                _log.exception("AI 코칭 생성 준비 실패: %s", exc)
                text = None
            self.after(0, lambda: self._apply_ai_card(card, text, gen=gen))

        threading.Thread(target=work, daemon=True).start()

    def _ai_coach_lane(self, advice: Any, lane_ko: str, role: str, key: str) -> str | None:
        from lol_coach import llm
        from lol_coach.blitz.parser import ROLE_KO

        return llm.coach_lane(
            lane_ko,
            ROLE_KO.get(role, role),
            advice.counters,
            advice.patch,
            api_key=key,
            model=self._ai_model(),
            provider=self._ai_provider(),
        )

    def _ai_coach_comp(self, rep: Any, matchup: list[str], key: str) -> str | None:
        from lol_coach import llm

        core = list(getattr(rep, "core_items", None) or [])
        # blitz 코어가 3개 미만이면 상황템으로 3~5코어 보강
        if len(core) < 5:
            for item, _why in list(getattr(rep, "situational", None) or []):
                if item and item not in core:
                    core.append(item)
                if len(core) >= 5:
                    break
        # 코어 경로에 이미 포함된 신발 이름을 프롬프트에 별도 표기
        boot_keys = ("장화", "신발", "발걸음", "신속의", "아이오니아")
        boots = [n for n in core if any(k in n for k in boot_keys)]
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
            provider=self._ai_provider(),
            core_items=core[:5],
            boots=boots[:2],
        )

    def _ai_coach_aram(self, adv: Any, key: str) -> str | None:
        from lol_coach import llm

        fill = getattr(self, "_aram_live_fill", None)
        allies = [ko for _k, ko in fill.allies] if fill else []
        enemies = []
        if fill:
            enemies = [ko for _k, ko in fill.enemies_by_role.values()]
            enemies += [ko for _k, ko in fill.enemies_extra]
        fixed_top = getattr(adv, "fixed_top", None)
        fixed_parts: list[str] = []
        if fixed_top is not None:
            for label, picks in (
                ("실버", fixed_top.silver),
                ("골드", fixed_top.gold),
                ("프리즘", fixed_top.prismatic),
            ):
                names = ", ".join(f"{i}위 {pick.name_ko}" for i, pick in enumerate(picks, 1))
                fixed_parts.append(f"{label}: {names or '데이터 없음'}")
        offered = ", ".join(f"{p.name_ko}({p.tier or '?'})" for p in adv.top_augments[:5])
        augs = " | ".join(fixed_parts)
        if offered:
            augs += f" | 현재 제시: {offered}"
        if adv.avoid_augments:
            augs += " | 피할: " + ", ".join(p.name_ko for p in adv.avoid_augments[:3])
        slots = list(adv.core_slots or [])[:6]
        if slots:
            build = " → ".join(f"{i}코어 {n}" for i, n in enumerate(slots, 1))
        else:
            build = ""
        if adv.spells_line:
            build = (build + f" · 스펠 {adv.spells_line}").strip(" ·")
        return llm.coach_aram(
            adv.champ_ko,
            allies,
            enemies,
            augs,
            build,
            adv.patch,
            api_key=key,
            model=self._ai_model(),
            provider=self._ai_provider(),
        )

    def _ai_coach_review(self, m: Any, rev: Any, key: str) -> str | None:
        from lol_coach import llm

        return llm.coach_review(
            m, rev, api_key=key, model=self._ai_model(), provider=self._ai_provider()
        )
