"""선택형 AI 코칭 카드·키·모델

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from typing import Any

import customtkinter as ctk

from lol_coach.config import (
    load_settings,
    save_llm_settings,
)
from lol_coach.gui import components as ui
from lol_coach.gui.ai_text import ai_key_points as _ai_key_points
from lol_coach.gui.ai_text import ai_lines as _ai_lines
from lol_coach.gui.constants import (
    AI_BODY,
    AI_SUMMARY,
    AI_TITLE,
)
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger

_log = get_logger("ai")
_AI_REQUEST: ContextVar[tuple[str, str, str] | None] = ContextVar("ai_request", default=None)


class AiMixin(MixinBase):
    def _ai_request_settings(self) -> tuple[str, str, str]:
        snapshot = _AI_REQUEST.get()
        if snapshot is not None:
            return snapshot
        settings = self.settings
        return settings.llm_base_url, settings.llm_api_key, settings.llm_model

    def _ai_provider(self) -> str:
        return "custom"

    def _ai_key(self) -> str:
        base, key, model = self._ai_request_settings()
        return key if base and model else ""

    def _ai_model(self) -> str:
        return self._ai_request_settings()[2]

    def _save_llm(self) -> bool:
        """설정 창의 세 필드를 함께 저장. 실패하면 런타임 설정을 유지한다."""
        try:
            save_llm_settings(
                vars(self)["llm_base_url_var"].get(),
                self.llm_key_var.get(), self.llm_model_var.get(),
            )
        except ValueError as exc:
            self._notify(str(exc), level="warn", ms=4200)
            return False
        except Exception:
            self._notify("AI 설정을 저장하지 못했습니다", level="warn", ms=4200)
            return False
        self.settings = load_settings()
        self._ai_gen = int(getattr(self, "_ai_gen", 0)) + 1
        vars(self)["llm_base_url_var"].set(self.settings.llm_base_url)
        self._refresh_ai_status()
        self.status.configure(text="AI 설정 저장됨")
        return True

    def _save_llm_key(self) -> bool:
        return self._save_llm()

    def _test_llm_connection(self) -> None:
        """입력값을 메인 스레드에서 고정해 /models만 확인한다. 설정은 저장하지 않는다."""
        from lol_coach import llm

        snapshot = (
            vars(self)["llm_base_url_var"].get(),
            self.llm_key_var.get(), self.llm_model_var.get(),
        )
        lbl = getattr(self, "ai_status_lbl", None)
        if lbl is not None:
            lbl.configure(text="AI 서버 연결 확인 중…", text_color=ui.TEXT_DIM)
        request_id = int(vars(self).get("_llm_probe_id", 0)) + 1
        vars(self)["_llm_probe_id"] = request_id

        def work() -> None:
            base, key, model = snapshot
            ok, msg = llm.probe_gateway(key, model, base_url=base, provider="custom")

            def done() -> None:
                current = (
                    vars(self)["llm_base_url_var"].get(),
                    self.llm_key_var.get(), self.llm_model_var.get(),
                )
                if current != snapshot or vars(self).get("_llm_probe_id") != request_id:
                    return
                self._notify(msg, level="ok" if ok else "warn", ms=4200)
                self._refresh_ai_status()

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _refresh_ai_status(self) -> None:
        lbl = getattr(self, "ai_status_lbl", None)
        if lbl is None:
            return
        try:
            base, key, model = self._ai_request_settings()
            if base and key and model:
                lbl.configure(text=f"AI 설정 저장됨 · {model}", text_color=ui.GREEN)
            else:
                lbl.configure(text="AI 설정 필요 — 규칙 기반 결과", text_color=ui.TEXT_DIM)
        except Exception:
            pass

    def _ai_header(self, card: Any) -> None:
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(6, 2))
        bar = ctk.CTkFrame(head, width=4, height=16, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 10))
        bar.pack_propagate(False)
        ctk.CTkLabel(
            head,
            text="🤖 AI 코칭",
            font=AI_TITLE,
            text_color=ui.GOLD_SOFT,
        ).pack(side="left")

    @staticmethod
    def _wrap_dynamic(label: ctk.CTkLabel, pad: int = 28) -> None:
        """라벨 wraplength 를 실제 위젯 폭에 맞춰 동적 갱신.

        하드코딩 wraplength=940 은 패널이 좁을 때 텍스트 우측 절단을 유발한다.
        <Configure> 바인딩으로 위젯이 리사이즈될 때마다 wraplength 를 재계산.
        """

        def _on_config(_event: Any) -> None:
            try:
                w = label.winfo_width()
                if w > pad:
                    label.configure(wraplength=w - pad)
            except Exception:
                pass

        label.bind("<Configure>", _on_config)

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
        card.grid(row=0, column=0, sticky="nsew", padx=6, pady=(2, 4))
        self._ai_header(card)
        loading = ctk.CTkLabel(
            card,
            text="AI 상세 코칭 생성 중… (잠시만요)",
            font=AI_BODY,
            text_color=ui.TEXT_DIM,
            anchor="w",
            justify="left",
        )
        loading.pack(fill="x", padx=10, pady=(4, 8))
        self._wrap_dynamic(loading)
        # 스트리밍 델타가 이 라벨에 점진 표시된다 (_apply_ai_card 시 파괴)
        card._ai_stream_lbl = loading

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
        if self.__dict__.get("_overlay_active", False):
            return  # 게임 중 오버레이 보호 — 위젯은 증강 TOP3 유지 (탭에서 확인)
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

            # 단일 스크롤 가능한 텍스트박스 (전체 콘텐츠 표시)
            total_lines = len(key_points) * 2 + len(details) + 6
            est_h = min(380, max(200, 24 + total_lines * 22))
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
            box.pack(fill="both", expand=True, padx=10, pady=(4, 8))

            # 텍스트 태그로 가독성 향상 — 섹션 헤더(골드 굵게) / 구분선 / 본문
            # CTkTextbox 가 tkinter.Text 를 _textbox 로 랩핑 — 없으면 태그 없이 일반 텍스트
            inner = getattr(box, "_textbox", None)
            if inner is not None:
                inner.tag_configure(
                    "header", foreground=ui.GOLD, font=(AI_BODY[0], AI_BODY[1] + 1, "bold")
                )
                inner.tag_configure("divider", foreground=ui.BORDER)
                inner.tag_configure("bullet", foreground=ui.TEXT_BRIGHT, lmargin1=18, lmargin2=18)
                inner.tag_configure("keypoint", foreground=ui.GOLD_SOFT, lmargin1=18, lmargin2=18)

                def _insert(tag: str, text_line: str) -> None:
                    inner.insert("end", text_line + "\n", tag)

                if key_points:
                    _insert("header", "⭐ 핵심 포인트")
                    for kp in key_points:
                        _insert("keypoint", f"• {kp}")
                    _insert("divider", "────────────────────")
                    inner.insert("end", "\n")
                _insert("header", "📋 상세 코칭")
                inner.insert("end", "\n")
                for line in details:
                    _insert("bullet", f"• {line}")
                # 끝 빈 줄 제거
                inner.delete("end-1c linestart", "end")
            else:
                # 폴백 — 태그 없이 일반 텍스트
                parts: list[str] = []
                if key_points:
                    parts.append("⭐ 핵심 포인트")
                    parts.extend(f"• {kp}" for kp in key_points)
                    parts.append("────────────────────")
                parts.append("📋 상세 코칭")
                parts.extend(f"• {line}" for line in details)
                box.insert("1.0", "\n".join(parts))
            box.configure(state="disabled")

            self._push_ai_to_widget(text)
        else:
            fail = ctk.CTkLabel(
                card,
                text="AI 코칭 생성 실패 — 규칙 기반 결과를 참고하세요 (키·네트워크·게이트웨이 확인)",
                font=AI_SUMMARY,
                text_color=ui.TEXT_DIM,
                anchor="w",
                justify="left",
            )
            fail.pack(fill="x", padx=10, pady=(4, 8))
            self._wrap_dynamic(fail)

    def _maybe_ai(self, frame: Any, builder: Any) -> None:
        """LLM 키가 있으면 AI 카드 부착 + 백그라운드 생성, 없으면 무시.

        ``builder`` 는 ``on_delta`` 키워드 인자를 받아 스트리밍 델타를
        전달하는 계약 — 첫 토큰부터 카드에 점진 표시된다.
        """
        snapshot = self._ai_request_settings()
        if not all(snapshot):
            return
        self._ai_gen += 1
        gen = self._ai_gen
        card = self._append_ai_card(frame)
        card._ai_gen = gen

        # 델타마다 Tk 마샬링하면 이벤트 큐가 넘친다 — 150ms/80자로 스로틀
        throttle = {"t": 0.0, "n": 0}

        def _stream_sink(partial: str) -> None:
            import time as _t

            now = _t.monotonic()
            if now - throttle["t"] < 0.15 and len(partial) - throttle["n"] < 80:
                return
            throttle["t"] = now
            throttle["n"] = len(partial)
            self.after(0, lambda p=partial: self._stream_ai_partial(card, gen, p))

        def work() -> None:
            token = _AI_REQUEST.set(snapshot)
            try:
                text = builder(on_delta=_stream_sink)
            except Exception as exc:
                _log.warning("AI 코칭 생성 준비 실패 (%s)", type(exc).__name__)
                text = None
            finally:
                _AI_REQUEST.reset(token)
            self.after(0, lambda: self._apply_ai_card(card, text, gen=gen))

        threading.Thread(target=work, daemon=True).start()

    def _stream_ai_partial(self, card: Any, gen: int, partial: str) -> None:
        """스트리밍 생성 중 — 로딩 라벨에 최신 부분 텍스트를 표시한다 (메인 스레드)."""
        if gen != getattr(self, "_ai_gen", gen):
            return
        try:
            if not card.winfo_exists():
                return
            lbl = getattr(card, "_ai_stream_lbl", None)
            if lbl is None or not lbl.winfo_exists():
                return
            text = (partial or "").strip()
            if not text:
                return
            # 길면 뒷부분만 — 생성 중 텍스트는 흘러가는 티커 역할
            lines = [ln for ln in text.splitlines() if ln.strip()]
            shown = " ".join(lines[-3:])[-360:]
            lbl.configure(text=f"🤖 생성 중… {shown}")
        except Exception:
            pass

    def _ai_coach_lane(
        self, advice: Any, lane_ko: str, role: str, key: str, on_delta: Any = None
    ) -> str | None:
        from lol_coach import llm
        from lol_coach.blitz.parser import ROLE_KO

        base, saved_key, model = self._ai_request_settings()
        return llm.coach_lane(
            lane_ko,
            ROLE_KO.get(role, role),
            advice.counters,
            advice.patch,
            api_key=saved_key,
            model=model,
            provider="custom",
            base_url=base,
            on_delta=on_delta,
        )

    def _ai_coach_comp(
        self, rep: Any, matchup: list[str], key: str, on_delta: Any = None
    ) -> str | None:
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
        base, saved_key, model = self._ai_request_settings()
        return llm.coach_comp(
            rep.my_champ_ko,
            rep.my_role,
            rep.enemy_team,
            rep.counters,
            rep.threats,
            rep.midgame,
            rep.situational,
            rep.patch,
            api_key=saved_key,
            model=model,
            provider="custom",
            base_url=base,
            core_items=core[:5],
            boots=boots[:2],
            on_delta=on_delta,
        )

    def _ai_coach_aram(self, adv: Any, key: str, on_delta: Any = None) -> str | None:
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
        valid = list(adv.augment_validation.valid) if adv.augment_validation else []
        offered = ", ".join(rec.name_ko for rec in valid) if valid else ""
        recs = ", ".join(f"{p.name_ko}({p.tier or '?'})" for p in adv.top_augments[:5])
        augs = " | ".join(fixed_parts)
        if recs:
            augs += f" | 추천: {recs}"
        if offered:
            augs += f" | 현재 제시: {offered}"
        if adv.avoid_augments:
            augs += " | 피할: " + ", ".join(p.name_ko for p in adv.avoid_augments[:3])
        base, saved_key, model = self._ai_request_settings()
        return llm.coach_aram(
            adv.champ_ko,
            allies,
            enemies,
            augs,
            adv.patch,
            api_key=saved_key,
            model=model,
            provider="custom",
            base_url=base,
            on_delta=on_delta,
        )

    def _ai_coach_review(self, m: Any, rev: Any, key: str, on_delta: Any = None) -> str | None:
        from lol_coach import llm

        base, saved_key, model = self._ai_request_settings()
        return llm.coach_review(
            m, rev, api_key=saved_key, model=model, provider="custom", base_url=base,
            on_delta=on_delta,
        )
