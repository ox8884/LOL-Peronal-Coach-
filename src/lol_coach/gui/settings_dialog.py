"""통합 설정 창 — AI · 알림/복기 · 화면 배율 · 단축키 · API 키."""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FONT_SCALE_CHOICES, FONT_UI, FS, FU


class SettingsDialog(ctk.CTkToplevel):
    """메인 앱 설정 모달. app 의 StringVar/BooleanVar 를 그대로 바인딩한다."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.title("설정 — 롤 실전 코치")
        self.geometry("540x720")
        self.minsize(500, 600)
        self.transient(app)
        # 부모 창 근처에 배치 (보조 모니터에서도 부모 옆에 뜨도록)
        self._position_near_parent(app)
        try:
            self.grab_set()
        except Exception:
            pass

        root = ctk.CTkScrollableFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=14, pady=12)
        root.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(root, text="설정", font=(FONT_UI, 18, "bold"), text_color=ui.GOLD_SOFT).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        r = 1
        r = self._section(root, r, "화면 스타일")
        r = self._build_skin(root, r)

        r = self._section(root, r, "미니 위젯")
        r = self._build_widget(root, r)

        r = self._section(root, r, "AI 연결")
        r = self._build_ai(root, r)

        r = self._section(root, r, "알림 · 복기")
        r = self._build_notify(root, r)

        r = self._section(root, r, "디스코드 복기 카드")
        r = self._build_discord(root, r)

        r = self._section(root, r, "화면 배율")
        r = self._build_display(root, r)

        r = self._section(root, r, "단축키")
        r = self._build_hotkeys(root, r)

        r = self._section(root, r, "Riot API 키")
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

    def _position_near_parent(self, app: Any) -> None:
        """부모 창 중앙에 겹치도록 배치 (다중 모니터 대응).

        winfo_screenwidth/height 는 주 모니터 해상도만 반환하므로
        클램프하지 않고 부모 창 위치 기반으로만 배치한다.
        """
        try:
            app.update_idletasks()
            px = app.winfo_x()
            py = app.winfo_y()
            pw = app.winfo_width()
            ph = app.winfo_height()
            w, h = 540, 720
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
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
        card = self._card(parent, row)
        ctk.CTkLabel(
            card, text="눈에 편한 화면을 고르세요. 선택하면 바로 적용됩니다.",
            font=FM, text_color=ui.TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 10))
        self._skin_buttons = {}
        for column, skin in enumerate(ui.SKINS):
            card.grid_columnconfigure(column, weight=1, uniform="skin")
            button = ctk.CTkButton(
                card, text=ui.SKIN_SHORT[skin], height=44, width=100, font=FU,
                command=lambda sid=skin: self._pick_skin(sid),
            )
            button.grid(row=1, column=column, sticky="ew", padx=6, pady=(0, 8))
            self._skin_buttons[skin] = button
        self._skin_status = ctk.CTkLabel(card, text="", font=FM, text_color=ui.TEXT_DIM, anchor="w")
        self._skin_status.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 10))
        self._sync_skin_selection()
        return row + 1

    def _pick_skin(self, skin: str) -> None:
        try:
            self.app._apply_skin_live(skin)
            self._sync_skin_selection()
        except Exception:
            self.app._notify("화면 스타일을 적용하지 못했습니다. 다시 선택해 주세요.", level="error")

    def _sync_skin_selection(self) -> None:
        for skin, button in self._skin_buttons.items():
            selected = skin == ui.active_skin()
            button.configure(
                text=ui.SKIN_SHORT[skin] + (" ✓" if selected else ""),
                **ui.btn(*(ui.BTN_PRIMARY if selected else ui.BTN_SECONDARY)),
            )
        self._skin_status.configure(text=f"적용 중 · {ui.SKIN_LABELS[ui.active_skin()]}")

    def _build_ai(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        card.grid_columnconfigure(1, weight=1)
        self._models_seq = 0
        self._ai_traces: list[tuple[Any, str]] = []
        self._ai_endpoint = (app.llm_base_url_var.get().strip().rstrip("/"), app.llm_key_var.get().strip())
        ctk.CTkLabel(card, text="Custom AI Provider", font=FU, text_color=ui.TEXT_BRIGHT, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 3)
        )
        ctk.CTkLabel(
            card, text="OpenAI 호환 서버를 연결하세요. 주소에는 /v1 등 API 경로를 포함합니다.",
            font=FM, text_color=ui.TEXT_DIM, anchor="w", justify="left", wraplength=420,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        for r, label in ((2, "Base URL"), (3, "API 키"), (4, "모델")):
            ctk.CTkLabel(card, text=label, font=FM, anchor="w").grid(row=r, column=0, sticky="w", padx=12, pady=5)
        self._ai_url_entry = ctk.CTkEntry(
            card, textvariable=app.llm_base_url_var, font=FM, height=34,
            placeholder_text="https://your-server.example/v1",
        )
        self._ai_url_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=5)
        self._ai_key_entry = ctk.CTkEntry(card, textvariable=app.llm_key_var, font=FM, height=34, show="•")
        self._ai_key_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=5)
        self._ai_model_menu = ctk.CTkComboBox(card, variable=app.llm_model_var, values=[], font=FM, height=34)
        self._ai_model_menu.grid(row=4, column=1, sticky="ew", padx=(0, 8), pady=5)
        self._ai_models_button = ctk.CTkButton(
            card, text="모델 불러오기", width=100, height=34, font=FM,
            **ui.btn(*ui.BTN_SECONDARY), command=self._load_ai_models,
        )
        self._ai_models_button.grid(row=4, column=2, padx=(0, 12), pady=5)
        self._models_status = ctk.CTkLabel(
            card, text="목록에서 선택하거나 모델 ID를 직접 입력할 수 있습니다.",
            font=FM, text_color=ui.TEXT_DIM, anchor="w", justify="left", wraplength=420,
        )
        self._models_status.grid(row=5, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 8))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 6))
        ctk.CTkButton(actions, text="설정 저장", width=106, height=34, font=FU,
                      **ui.btn(*ui.BTN_PRIMARY), command=app._save_llm_key).pack(side="left")
        ctk.CTkButton(actions, text="연결 확인", width=96, height=34, font=FM,
                      **ui.btn(*ui.BTN_SECONDARY), command=app._test_llm_connection).pack(side="left", padx=8)
        app.ai_status_lbl = self._ai_status_label = ctk.CTkLabel(
            card, text="", font=FM, text_color=ui.TEXT_DIM, anchor="w", justify="left", wraplength=420,
        )
        app.ai_status_lbl.grid(row=7, column=0, columnspan=3, sticky="ew", padx=12, pady=(0, 12))
        for var in (app.llm_base_url_var, app.llm_key_var):
            self._ai_traces.append((var, var.trace_add("write", self._on_ai_endpoint_edit)))
        return row + 1

    def _on_ai_endpoint_edit(self, *_args: Any) -> None:
        current = (self.app.llm_base_url_var.get().strip().rstrip("/"), self.app.llm_key_var.get().strip())
        if current == self._ai_endpoint:
            return
        self._ai_endpoint = current
        self._models_seq += 1
        self._ai_model_menu.configure(values=[])
        self._ai_models_button.configure(state="normal", text="모델 불러오기")
        self._models_status.configure(text="연결 정보가 바뀌었습니다. 모델 목록을 다시 불러오세요.", text_color=ui.TEXT_DIM)

    def _load_ai_models(self) -> None:
        from lol_coach import llm

        url = self.app.llm_base_url_var.get().strip()
        key = self.app.llm_key_var.get().strip()
        self._models_seq += 1
        sequence = self._models_seq
        self._ai_models_button.configure(state="disabled", text="불러오는 중…")
        self._models_status.configure(text="서버에서 모델 목록을 확인하고 있습니다.", text_color=ui.TEXT_DIM)

        def work() -> None:
            try:
                models = llm.list_models(api_key=key, base_url=url)
                error = "" if models else "서버에서 반환한 모델이 없습니다. 모델 ID를 직접 입력해 주세요."
            except Exception:
                models = []
                error = "모델 목록을 불러오지 못했습니다. 주소·키를 확인하거나 모델 ID를 직접 입력해 주세요."
            self.app.after(0, lambda: self._finish_ai_models(sequence, models, error))

        self.app._spawn_thread(work)

    def _finish_ai_models(self, sequence: int, models: list[str], error: str) -> None:
        if not self.winfo_exists() or sequence != self._models_seq:
            return
        self._ai_models_button.configure(state="normal", text="모델 불러오기")
        self._ai_model_menu.configure(values=models)
        self._models_status.configure(
            text=error or f"{len(models)}개 모델을 불러왔습니다. 사용할 모델을 선택하고 저장하세요.",
            text_color=ui.TEXT_DIM if error else ui.GREEN,
        )

    def destroy(self) -> None:
        for var, trace in getattr(self, "_ai_traces", []):
            var.trace_remove("write", trace)
        self._ai_traces = []
        if getattr(self.app, "ai_status_lbl", None) is getattr(self, "_ai_status_label", None):
            self.app.ai_status_lbl = None
        super().destroy()

    def _build_notify(self, parent: Any, row: int) -> int:
        app = self.app
        card = self._card(parent, row)
        opts = [
            (
                app.game_end_notify_var,
                "게임 종료 알림 (소리 · 작업표시줄)",
                app.me_tab._on_game_end_notify_toggle,
            ),
            (
                app.game_start_notify_var,
                "게임 시작 알림 (소리 · 상태바 · 위젯)",
                app.me_tab._on_game_start_notify_toggle,
            ),
            (
                app.game_end_auto_review_var,
                "게임 종료 시 자동 복기 (패널 열기)",
                app.me_tab._on_game_end_auto_review_toggle,
            ),
            (
                app.auto_open_latest_var,
                "전적 로드 시 최근 1판 자동 복기",
                app.me_tab._on_auto_open_latest_toggle,
            ),
            (
                app.boot_auto_load_var,
                "부팅 시 마지막 전적 자동 로드 (게임 시작 자동 브리핑은 전적 로드 후 켜짐)",
                app.me_tab._on_boot_auto_load_toggle,
            ),
            (
                app.mayhem_overlay_var,
                "게임 중 증강 추천 오버레이 (아수라장 · 위젯)",
                app.me_tab._on_mayhem_overlay_toggle,
            ),
        ]
        for i, (var, text, cmd) in enumerate(opts):
            ctk.CTkCheckBox(
                card,
                text=text,
                variable=var,
                font=FU,
                command=cmd,
            ).grid(
                row=i, column=0, sticky="w", padx=12, pady=(8 if i == 0 else 4, 4 if i < 2 else 10)
            )
        return row + 1

    def _build_discord(self, parent: Any, row: int) -> int:
        """디스코드 웹훅 — 게임 종료 복기 카드 자동 전송 설정."""
        app = self.app
        card = self._card(parent, row)
        ctk.CTkLabel(card, text="웹훅 URL", font=FU, width=80, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ctk.CTkEntry(
            card,
            textvariable=app.discord_webhook_var,
            font=FM,
            height=30,
            show="•",
            placeholder_text="https://discord.com/api/webhooks/…",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 4))
        ctk.CTkButton(
            card,
            text="저장",
            width=56,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._save_discord_webhook,
        ).grid(row=0, column=2, padx=(0, 12), pady=(10, 4))
        ctk.CTkLabel(
            card,
            text=(
                "디스코드 채널 설정 → 연동 → 웹후크에서 주소 복사.\n"
                "저장하면 게임이 끝날 때마다 카드가 이 채널로 옵니다."
            ),
            font=FM,
            text_color=ui.TEXT_DIM,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        ctk.CTkButton(
            card,
            text="테스트 카드 전송",
            width=128,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=self._send_test_card,
        ).grid(row=1, column=2, padx=(0, 12), pady=(0, 10))
        ctk.CTkCheckBox(
            card,
            text="게임 종료 시 디스코드로 복기 카드 자동 전송",
            variable=app.discord_review_var,
            font=FU,
            command=app.me_tab._on_discord_review_toggle,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 12))
        return row + 1

    def _show_api_help(self, app: Any) -> None:
        """API 키 도움말 — 탭 믹스인이 아니라 api_help 모듈로 직접 연다."""
        from lol_coach.gui.api_help import open_api_key_help

        open_api_key_help(app)

    def _save_discord_webhook(self) -> None:
        from lol_coach.config import discord_webhook_url, set_discord_webhook
        from lol_coach.notify.discord import DiscordWebhookError, validate_webhook_url

        app = self.app
        url = (app.discord_webhook_var.get() or "").strip()
        app.discord_webhook_var.set(url)
        if not url:
            set_discord_webhook("")
            app._notify("디스코드 웹훅 해제됨 — 자동 전송 없음", level="info", ms=2600)
            return
        try:
            validate_webhook_url(url)
        except DiscordWebhookError as exc:
            app._notify(f"주소가 올바르지 않습니다: {exc}", level="error", ms=5200)
            return
        set_discord_webhook(url)
        app.discord_webhook_var.set(discord_webhook_url())
        app._notify("디스코드 웹훅 저장됨 — 게임이 끝나면 카드가 도착합니다", level="ok", ms=3000)

    def _send_test_card(self) -> None:
        import threading

        from lol_coach.config import discord_webhook_url
        from lol_coach.gui.review_card import sample_card_bytes
        from lol_coach.notify.discord import post_card

        app = self.app
        url = discord_webhook_url()
        if not url:
            app._notify("웹훅 URL을 먼저 저장하세요", level="warn", ms=2800)
            return
        app._notify("디스코드 테스트 카드 전송 중…", level="info", ms=2000)

        def work() -> None:
            try:
                png = sample_card_bytes()
                post_card(
                    url,
                    title="연결 테스트 — 복기 카드",
                    description=(
                        "웹훅 연결 확인용 샘플 카드입니다. "
                        "게임이 끝나면 이 형태로 복기 카드가 도착합니다."
                    ),
                    png_bytes=png,
                    footer="롤 실전 코치 · 테스트",
                )
                app.after(
                    0,
                    lambda: app._notify(
                        "📮 테스트 카드 전송 완료 — 디스코드 확인", level="ok", ms=3000
                    ),
                )
            except Exception as exc:
                app.after(
                    0,
                    lambda e=exc: app._notify(f"전송 실패: {e}", level="error", ms=5200),
                )

        threading.Thread(target=work, daemon=True).start()

    def _build_widget(self, parent: Any, row: int) -> int:
        card = self._card(parent, row)
        self.widget_switch = ctk.CTkSwitch(
            card, text="미니 위젯 표시", font=FU,
            variable=self.app.widget_visible_var,
            command=lambda: self.app._set_widget_visible(bool(self.app.widget_visible_var.get())),
        )
        self.widget_switch.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))
        ctk.CTkLabel(
            card, text="끄면 게임 중에도 자동으로 열리지 않습니다.\n클릭 통과 중에는 위젯 상단에서 해제·닫기를 누르세요.",
            font=FS, text_color=ui.TEXT_DIM, justify="left", anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))
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
            command=lambda: self._show_api_help(app),
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
