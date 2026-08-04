"""챔피언 자동완성 — 인라인 Frame + Windows IME 조합 문자열.

한글은 스페이스/화살표로 '확정'되기 전엔 Entry.get()/StringVar 가 비어 있다.
그래서 Windows ImmGetCompositionString 으로 조합 중 글자를 읽어
한 글자 입력 즉시 검색한다. UI 는 form 안 고정 Frame (Toplevel 없음).
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.static.ddragon import DataDragon

_FONT = ("Malgun Gothic", 12)

# Windows IMM
_GCS_COMPSTR = 0x0008
_GCS_RESULTSTR = 0x0800


class ChampionAutocomplete:
    def __init__(
        self,
        master: ctk.CTk | ctk.CTkToplevel | tk.Misc,
        entry: ctk.CTkEntry,
        var: tk.StringVar,
        dd: DataDragon,
        *,
        list_parent: ctk.CTkBaseClass | tk.Misc | None = None,
        keep_icon: Callable[[Any], Any] | None = None,
        on_select: Callable[[str, str], None] | None = None,
        limit: int = 8,
        icon_size: int = 32,
    ) -> None:
        self.master = master
        self.entry = entry
        self.var = var
        self.dd = dd
        self.keep_icon = keep_icon or (lambda x: x)
        self.on_select = on_select
        self.limit = limit
        self.icon_size = icon_size

        self._inner = getattr(entry, "_entry", None)

        parent = list_parent if list_parent is not None else entry.master
        self._panel = ctk.CTkFrame(
            parent,
            corner_radius=8,
            fg_color=ui.PANEL,
            border_width=1,
            border_color=ui.GOLD,
        )
        self._panel_visible = False
        self._list_box = ctk.CTkFrame(self._panel, fg_color="transparent")
        self._list_box.pack(fill="both", expand=True, padx=4, pady=4)

        self._rows: list[dict[str, Any]] = []
        self._sel = 0
        self._shown_q = ""
        self._committed: str | None = None
        self._choosing = False
        self._icons: list[Any] = []
        self._icon_gen = 0
        self._job: str | None = None
        self._gen = 0
        self._poll_job: str | None = None
        self._poll_gen = 0
        self._skip_ime = False  # 백스페이스 직후 IME 잔상 무시
        self._focused = False

        var.trace_add("write", self._on_var)

        widgets = [entry]
        if self._inner is not None:
            widgets.append(self._inner)
        for w in widgets:
            # KeyPress: IME 조합 시작/진행 시에도 발생
            w.bind("<KeyPress>", self._on_key, add="+")
            w.bind("<KeyRelease>", self._on_key, add="+")
            w.bind("<Down>", self._on_down, add="+")
            w.bind("<Up>", self._on_up, add="+")
            w.bind("<Return>", self._on_return, add="+")
            w.bind("<KP_Enter>", self._on_return, add="+")
            w.bind("<Escape>", self._on_escape, add="+")
            w.bind("<Tab>", self._on_tab, add="+")
            w.bind("<FocusIn>", self._on_focus_in, add="+")
            w.bind("<FocusOut>", self._on_focus_out, add="+")

    # ── public ───────────────────────────────────────────────────────

    @property
    def panel(self) -> ctk.CTkFrame:
        return self._panel

    @property
    def _popup(self) -> Any:
        return self._panel if self._panel_visible and self._rows else None

    def hide(self) -> None:
        self._cancel_job()
        self._clear_list()
        self._shown_q = ""
        if self._panel_visible:
            try:
                self._panel.grid_remove()
            except Exception:
                try:
                    self._panel.pack_forget()
                except Exception:
                    pass
            self._panel_visible = False

    def is_open(self) -> bool:
        return bool(self._panel_visible and self._rows)

    # ── after (검색 1개 + 포커스 폴링 1개) ────────────────────────────

    def _cancel_job(self) -> None:
        self._gen += 1
        job = self._job
        self._job = None
        if job is not None:
            try:
                self.master.after_cancel(job)
            except Exception:
                pass

    def _schedule(self, delay_ms: int = 10) -> None:
        self._cancel_job()
        gen = self._gen

        def _run() -> None:
            self._job = None
            if gen != self._gen:
                return
            try:
                self._apply()
            except Exception:
                pass

        try:
            self._job = self.master.after(delay_ms, _run)
        except Exception:
            try:
                self._apply()
            except Exception:
                pass

    def _start_poll(self) -> None:
        self._stop_poll()
        self._focused = True
        self._poll_gen += 1
        gen = self._poll_gen

        def _tick() -> None:
            self._poll_job = None
            if gen != self._poll_gen or not self._focused or self._choosing:
                return
            try:
                self._apply()
            except Exception:
                pass
            if gen == self._poll_gen and self._focused:
                try:
                    # 조합 중 글자 변화를 잡기 위한 가벼운 폴링 (UI 재생성 최소화는 _apply 내부)
                    self._poll_job = self.master.after(60, _tick)
                except Exception:
                    pass

        try:
            self._poll_job = self.master.after(60, _tick)
        except Exception:
            pass

    def _stop_poll(self) -> None:
        self._focused = False
        self._poll_gen += 1
        job = self._poll_job
        self._poll_job = None
        if job is not None:
            try:
                self.master.after_cancel(job)
            except Exception:
                pass

    # ── Windows IME ──────────────────────────────────────────────────

    def _hwnds(self) -> list[int]:
        out: list[int] = []
        for w in (self._inner, self.entry, self.master):
            if w is None:
                continue
            try:
                hid = int(w.winfo_id())
                if hid and hid not in out:
                    out.append(hid)
            except Exception:
                continue
        return out

    def _ime_comp(self) -> str:
        """조합 중인 한글 (미확정). 실패 시 빈 문자열."""
        if sys.platform != "win32":
            return ""
        try:
            import ctypes

            imm32 = ctypes.windll.imm32
            for hwnd in self._hwnds():
                himc = imm32.ImmGetContext(hwnd)
                if not himc:
                    continue
                try:
                    size = imm32.ImmGetCompositionStringW(
                        himc, _GCS_COMPSTR, None, 0
                    )
                    if not size or int(size) <= 0:
                        # 방금 확정된 결과 문자열
                        size = imm32.ImmGetCompositionStringW(
                            himc, _GCS_RESULTSTR, None, 0
                        )
                        if not size or int(size) <= 0:
                            continue
                        buf = ctypes.create_unicode_buffer(int(size) // 2 + 2)
                        imm32.ImmGetCompositionStringW(
                            himc, _GCS_RESULTSTR, buf, size
                        )
                        return (buf.value or "").strip()
                    buf = ctypes.create_unicode_buffer(int(size) // 2 + 2)
                    imm32.ImmGetCompositionStringW(
                        himc, _GCS_COMPSTR, buf, size
                    )
                    return (buf.value or "").strip()
                finally:
                    imm32.ImmReleaseContext(hwnd, himc)
        except Exception:
            return ""
        return ""

    def _committed_text(self) -> str:
        """Entry 에 이미 확정된 텍스트."""
        if self._inner is not None:
            try:
                return str(self._inner.get())
            except Exception:
                pass
        try:
            return str(self.entry.get())
        except Exception:
            pass
        try:
            return str(self.var.get())
        except Exception:
            return ""

    def _text(self) -> str:
        """검색용 문자열 = 확정 텍스트 + (필요 시) IME 조합 중 글자."""
        base = self._committed_text()
        base_s = base.strip() if base else ""

        if self._skip_ime:
            return base_s

        comp = self._ime_comp()
        if not comp:
            return base_s

        # 위젯이 비어 있고 조합만 있으면 → 첫 글자 입력 중
        if not base_s:
            return comp

        # 이미 확정 텍스트에 포함돼 있으면 중복 방지
        if base_s.endswith(comp) or comp in base_s:
            return base_s

        return (base_s + comp).strip()

    # ── events ───────────────────────────────────────────────────────

    def _on_var(self, *_a: Any) -> None:
        if self._choosing:
            return
        self._skip_ime = False
        self._schedule(5)

    def _on_key(self, event: tk.Event | None = None) -> None:  # type: ignore[type-arg]
        if self._choosing:
            return
        keysym = getattr(event, "keysym", "") if event else ""
        if keysym in (
            "Up",
            "Down",
            "Return",
            "KP_Enter",
            "Escape",
            "Tab",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Hangul",
            "Hanja",
        ):
            return

        if keysym in ("BackSpace", "Delete"):
            # 삭제 시 확정 텍스트 우선 (IME 잔상으로 목록이 안 사라지는 것 방지)
            self._skip_ime = True
            self._schedule(0)

            gen = self._gen

            def _after_del() -> None:
                if gen != self._gen or self._choosing:
                    return
                self._skip_ime = True
                try:
                    self._apply()
                except Exception:
                    pass

            try:
                self.master.after(25, _after_del)
            except Exception:
                pass
            return

        self._skip_ime = False
        # 즉시 + Imm 조합 반영 대기 (15/40ms). _schedule 은 이전 예약만 취소.
        self._schedule(0)
        gen = self._gen

        def _again() -> None:
            if gen != self._gen or self._choosing:
                return
            try:
                self._apply()
            except Exception:
                pass

        try:
            self.master.after(15, _again)
            self.master.after(40, _again)
        except Exception:
            pass

    def _on_focus_in(self, _e: Any = None) -> None:
        self._start_poll()
        self._schedule(10)

    def _on_focus_out(self, _e: Any = None) -> None:
        self._stop_poll()
        # 목록 클릭 여유
        try:
            self.master.after(150, self._maybe_hide_on_blur)
        except Exception:
            pass

    def _maybe_hide_on_blur(self) -> None:
        if self._choosing or self._focused:
            return
        # 포커스가 패널 버튼으로 간 경우 유지
        try:
            focus = self.master.focus_get()
            if focus is not None and str(focus).startswith(str(self._panel)):
                return
        except Exception:
            pass
        # 입력 중이면 목록 유지, 비었으면 닫기
        if not self._text():
            self.hide()

    def _on_down(self, _e: Any = None) -> str:
        if not self.is_open():
            self._apply()
            return "break"
        if self._rows:
            self._sel = min(self._sel + 1, len(self._rows) - 1)
            self._paint_sel()
        return "break"

    def _on_up(self, _e: Any = None) -> str:
        if self.is_open() and self._rows:
            self._sel = max(self._sel - 1, 0)
            self._paint_sel()
        return "break"

    def _on_return(self, _e: Any = None) -> str | None:
        if self.is_open() and self._rows:
            self._choose(self._sel)
            return "break"
        return None

    def _on_tab(self, _e: Any = None) -> str | None:
        if self.is_open() and self._rows:
            self._choose(self._sel)
            return "break"
        return None

    def _on_escape(self, _e: Any = None) -> str:
        self.hide()
        return "break"

    # ── apply / UI ───────────────────────────────────────────────────

    def _apply(self) -> None:
        if self._choosing:
            return

        q = self._text().strip()

        if self._committed is not None:
            if q == self._committed:
                if self.is_open():
                    self.hide()
                return
            self._committed = None

        if not q:
            if self.is_open() or self._shown_q:
                self.hide()
            return

        try:
            hits = self.dd.search_champions(q, limit=self.limit, contains=False)
        except Exception:
            hits = []

        if not hits:
            self.hide()
            self._shown_q = q
            return

        if (
            q == self._shown_q
            and self.is_open()
            and [r.get("id") for r in self._rows] == [h.get("id") for h in hits]
        ):
            return

        self._shown_q = q
        self._fill(hits)

    def _clear_list(self) -> None:
        self._rows = []
        self._sel = 0
        self._icons = []
        try:
            for child in self._list_box.winfo_children():
                child.destroy()
        except Exception:
            pass

    def _show_panel(self) -> None:
        if self._panel_visible:
            return
        try:
            self._panel.grid()
            self._panel_visible = True
        except Exception:
            try:
                self._panel.pack(fill="x", padx=8, pady=(0, 6))
                self._panel_visible = True
            except Exception:
                self._panel_visible = False

    def _preload_icons(self, hits: list[dict[str, Any]]) -> None:
        """캐시 미스 아이콘은 UI 스레드를 막지 않고 받은 뒤 목록을 다시 그린다."""
        keys = [str(c.get("id") or "") for c in hits]
        generation = self._icon_gen = self._icon_gen + 1
        shown_q = self._shown_q

        def _load() -> None:
            from lol_coach.static.icons import champion_pil

            for key in keys:
                if key:
                    champion_pil(key, self.icon_size)

            def _refresh() -> None:
                if (
                    generation != self._icon_gen
                    or shown_q != self._shown_q
                    or keys != [str(row.get("id") or "") for row in self._rows]
                ):
                    return
                self._fill(self._rows, preload=False)

            try:
                self.master.after(0, _refresh)
            except Exception:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _fill(self, hits: list[dict[str, Any]], *, preload: bool = True) -> None:
        self._clear_list()
        self._rows = list(hits)
        self._sel = 0

        from lol_coach.static.icons import champion_ctk

        for i, c in enumerate(hits):
            name = c.get("name") or c.get("id") or ""
            row = ctk.CTkFrame(
                self._list_box,
                fg_color="transparent",
                height=self.icon_size + 8,
            )
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            icon = None
            try:
                icon = champion_ctk(c["id"], self.icon_size)
                if icon is not None:
                    icon = self.keep_icon(icon)
                    self._icons.append(icon)
            except Exception:
                icon = None

            kw: dict[str, Any] = {
                "text": f"  {name}",
                "anchor": "w",
                "font": _FONT,
                "height": self.icon_size + 4,
                "fg_color": "transparent",
                "hover_color": ("#3B8ED0", "#1F6AA5"),
                "text_color": ("gray10", "gray90"),
                "command": lambda idx=i: self._choose(idx),
            }
            if icon is not None:
                kw["image"] = icon
                kw["compound"] = "left"
            btn = ctk.CTkButton(row, **kw)
            btn.pack(fill="both", expand=True, padx=2, pady=1)

        self._show_panel()
        self._paint_sel()
        if preload:
            self._preload_icons(hits)

    def _paint_sel(self) -> None:
        try:
            children = self._list_box.winfo_children()
        except Exception:
            return
        for i, row in enumerate(children):
            try:
                for child in row.winfo_children():
                    child.configure(
                        fg_color=("#3B8ED0", "#1F6AA5")
                        if i == self._sel
                        else "transparent"
                    )
            except Exception:
                pass

    def _choose(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._rows):
            return
        c = self._rows[idx]
        name = c.get("name") or c.get("id") or ""
        key = c.get("id") or ""

        self._choosing = True
        self._committed = name
        self._cancel_job()
        try:
            self.var.set(name)
        except Exception:
            pass
        self.hide()
        try:
            self.entry.icursor("end")
            self.entry.focus_set()
        except Exception:
            pass
        if self.on_select:
            try:
                self.on_select(key, name)
            except Exception:
                pass
        self._choosing = False
