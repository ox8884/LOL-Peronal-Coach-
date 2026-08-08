"""통합 설정 창 — AI · 알림/복기 · 화면 배율 · 단축키 · API 키."""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.gui.constants import AI_MODELS, FONT_SCALE_CHOICES, FM, FS, FU


class SettingsDialog(ctk.CTkToplevel):
    """메인 앱 설정 모달. app 의 StringVar/BooleanVar 를 그대로 바인딩한다."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.title("설정 — 롤 실전 코치")
        self.geometry("520x640")
        self.minsize(480, 560)
        self.transient(app)
        try:
            self.grab_set()
        except Exception:
            pass

        root = ctk.CTkScrollableFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=14, pady=12)
        root.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            root, text="설정", font=("Malgun Gothic", 18, "bold"), text_color=ui.GOLD_SOFT
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        r = 1
        r = self._section(root, r, "🎨 UI 스킨")
        r = self._build_skin(root, r)

        r = self._section(root, r, "🤖 AI 코칭")
        r = self._build_ai(root, r)

        r = self._section(root, r, "🔔 알림 · 복기")
        r = self._build_notify(root, r)

        r = self._section(root, r, "🖥 화면")
        r = self._build_display(root, r)

        r = self._section(root, r, "⌨ 단축키")
        r = self._build_hotkeys(root, r)

        r = self._section(root, r, "🔑 Riot API 키")
        r = self._build_api(root, r)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            foot,
            text="닫기",
            width=100,
            height=34,
            font=FU,
            **ui.btn(*ui.BTN_PRIMARY),
            command=self.destroy,
        ).pack(side="right")

        try:
            app._refresh_ai_status()
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(50, self._focus_self)

    def _focus_self(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _section(self, parent: Any, row: int, title: str) -> int:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=row, column=0, sticky="ew", pady=(12, 4))
        bar = ctk.CTkFrame(head, width=3, height=14, corner_radius=2, fg_color=ui.GOLD)
        bar.pack(side="left", padx=(0, 8))
        bar.pack_propagate(False)
        ctk.CTkLabel(head, text=title, font=FU, text_color=ui.GOLD_SOFT).pack(side="left")
        return row + 1

    def _card(self, parent: Any, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent,
            fg_color=ui.PANEL,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 4))
        card.grid_columnconfigure(1, weight=1)
        return card

    def _build_skin(self, parent: Any, row: int) -> int:
        """여러 스킨 중 선택 — 누르면 즉시 적용 (재시작 없음)."""
        from lol_coach.gui.components import (
            SKIN_LABELS,
            SKIN_SHORT,
            SKINS,
            active_skin,
            load_skin_name,
        )

        card = self._card(parent, row)
        cur = active_skin()
        self._skin_var = tk.StringVar(value=cur)
        self._skin_status = ctk.CTkLabel(
            card,
            text=f"지금 적용: {SKIN_LABELS.get(cur, cur)}\n클릭하면 바로 바뀝니다 (재시작 없음)",
            font=FM,
            text_color=ui.GOLD_SOFT,
            anchor="w",
            justify="left",
        )

        def _pick(skin: str) -> None:
            self._skin_var.set(skin)
            # 메인 앱이 UI를 다시 그리고 설정 창을 다시 연다
            try:
                self.app._apply_skin_live(skin)
            except Exception as exc:
                self.app._notify(f"스킨 적용 실패: {exc}", level="error")

        ctk.CTkLabel(
            card,
            text="다크 · 밝은 스킨을 눌러 바로 비교할 수 있습니다.\n"
            "클래식 = 예전 골드 UI.",
            font=FS,
            text_color=ui.TEXT_DIM,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        labels = [SKIN_LABELS[s] for s in SKINS]
        label_to_id = {SKIN_LABELS[s]: s for s in SKINS}
        cur_label = SKIN_LABELS.get(cur, SKIN_LABELS[SKINS[0]])
        self._skin_menu_var = tk.StringVar(value=cur_label)

        def _on_menu(choice: str) -> None:
            sid = label_to_id.get(choice)
            if sid:
                _pick(sid)

        ctk.CTkOptionMenu(
            card,
            variable=self._skin_menu_var,
            values=labels,
            width=360,
            height=34,
            font=FU,
            command=_on_menu,
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(4, 6))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        for i, sid in enumerate(SKINS):
            r, c = divmod(i, 2)
            is_on = sid == cur
            ctk.CTkButton(
                grid,
                text=SKIN_SHORT.get(sid, sid) + (" ✓" if is_on else ""),
                height=30,
                font=FM,
                **ui.btn(*(ui.BTN_PRIMARY if is_on else ui.BTN_SECONDARY)),
                command=lambda s=sid: _pick(s),
            ).grid(row=r, column=c, sticky="ew", padx=(0, 6), pady=3)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        self._skin_status.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 10))
        return row + 1

    def _build_ai(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        ctk.CTkLabel(card, text="AI 키", font=FU, width=80, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ctk.CTkEntry(
            card,
            textvariable=app.llm_key_var,
            font=FM,
            height=30,
            show="•",
            placeholder_text="opencode-go 키 (비우면 자동 감지)",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 4))
        ctk.CTkButton(
            card,
            text="저장",
            width=56,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=app._save_llm_key,
        ).grid(row=0, column=2, padx=(0, 12), pady=(10, 4))

        ctk.CTkLabel(card, text="모델", font=FU, width=80, anchor="w").grid(
            row=1, column=0, sticky="w", padx=12, pady=4
        )
        from lol_coach import llm as _llm

        cur = app.llm_model_var.get() or _llm.DEFAULT_MODEL
        values = list(AI_MODELS)
        if cur not in values:
            values.insert(0, cur)
        ctk.CTkOptionMenu(
            card,
            variable=app.llm_model_var,
            values=values,
            width=220,
            height=30,
            font=FM,
            command=lambda _v: app._save_llm_key(),
        ).grid(row=1, column=1, sticky="w", padx=(0, 8), pady=4)

        app.ai_status_lbl = ctk.CTkLabel(
            card, text="", font=FM, text_color=ui.TEXT_DIM, anchor="w"
        )
        app.ai_status_lbl.grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 10)
        )
        return row + 1

    def _build_notify(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        opts = [
            (
                app.game_end_notify_var,
                "게임 종료 알림 (소리 · 작업표시줄)",
                app._on_game_end_notify_toggle,
            ),
            (
                app.game_end_auto_review_var,
                "게임 종료 시 자동 복기 (패널 열기)",
                app._on_game_end_auto_review_toggle,
            ),
            (
                app.auto_open_latest_var,
                "전적 로드 시 최근 1판 자동 복기",
                app._on_auto_open_latest_toggle,
            ),
        ]
        for i, (var, text, cmd) in enumerate(opts):
            ctk.CTkCheckBox(
                card,
                text=text,
                variable=var,
                font=FU,
                command=cmd,
            ).grid(row=i, column=0, sticky="w", padx=12, pady=(8 if i == 0 else 4, 4 if i < 2 else 10))
        return row + 1

    def _build_display(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        ctk.CTkLabel(card, text="화면 배율", font=FU, width=80, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=12
        )
        scale_vals = list(FONT_SCALE_CHOICES)
        cur = f"{getattr(app, '_font_scale', 1.0):.1f}"
        if cur not in scale_vals:
            scale_vals.insert(0, cur)
        if not hasattr(app, "font_scale_var") or app.font_scale_var is None:
            app.font_scale_var = tk.StringVar(value=cur)
        else:
            app.font_scale_var.set(cur)
        ctk.CTkOptionMenu(
            card,
            variable=app.font_scale_var,
            values=scale_vals,
            width=80,
            height=30,
            font=FM,
            command=app._set_font_scale,
        ).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=12)
        ctk.CTkLabel(
            card,
            text="일부 글자는 다시 그리면 반영됩니다",
            font=FS,
            text_color=ui.TEXT_DIM,
        ).grid(row=0, column=2, sticky="w", padx=(0, 12))
        return row + 1

    def _build_hotkeys(self, parent: Any, row: int) -> int:
        card = self._card(parent, row)
        lines = [
            "Ctrl+Shift+W  —  미니 위젯 토글 (게임 중에도, Windows)",
            "앱 내 동일 단축키 — 전역 등록 실패 시에도 동작",
        ]
        for i, line in enumerate(lines):
            ctk.CTkLabel(
                card,
                text=line,
                font=FM,
                text_color=ui.TEXT,
                anchor="w",
            ).grid(
                row=i,
                column=0,
                sticky="w",
                padx=12,
                pady=(10 if i == 0 else 2, 10 if i == len(lines) - 1 else 2),
            )
        return row + 1

    def _build_api(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        # 내 전적 탭과 같은 api_key_var 공유
        if not hasattr(app, "api_key_var"):
            from lol_coach.config import load_settings

            app.api_key_var = tk.StringVar(value=load_settings().riot_api_key or "")
        ctk.CTkLabel(card, text="API 키", font=FU, width=80, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ctk.CTkEntry(
            card,
            textvariable=app.api_key_var,
            font=FM,
            height=30,
            show="•",
            placeholder_text="RGAPI-…",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 4))
        ctk.CTkButton(
            card,
            text="❓ 도움말",
            width=72,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=app._show_api_help,
        ).grid(row=0, column=2, padx=(0, 12), pady=(10, 4))
        ctk.CTkButton(
            card,
            text="키 저장",
            width=72,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._save_api_key,
        ).grid(row=1, column=2, padx=(0, 12), pady=(0, 10))
        ctk.CTkLabel(
            card,
            text="키는 이 PC .env 에만 저장 · 전적 로드 시 내 전적 탭 값 사용",
            font=FS,
            text_color=ui.TEXT_DIM,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        return row + 1

    def _save_api_key(self) -> None:
        from lol_coach.config import load_settings, save_api_key

        app = self.app
        key = (app.api_key_var.get() or "").strip()
        try:
            save_api_key(key)
            app.settings = load_settings()
            app._notify("Riot API 키 저장됨", level="ok", ms=2200)
        except Exception as exc:
            app._notify(f"API 키 저장 실패: {exc}", level="error")


def open_settings(app: Any) -> SettingsDialog:
    """이미 열린 설정 창이 있으면 앞으로, 없으면 새로."""
    existing = getattr(app, "_settings_win", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return existing
        except Exception:
            pass
    win = SettingsDialog(app)
    app._settings_win = win

    def _clear(_: Any = None) -> None:
        if getattr(app, "_settings_win", None) is win:
            app._settings_win = None

    win.bind("<Destroy>", _clear)
    return win
