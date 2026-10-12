"""내 전적 탭 — 매치 상세 뷰 (타임라인·킬 지도·복기 렌더).

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.review import analyze_match
from lol_coach.gui import components as ui
from lol_coach.gui.constants import FM, FS, FU
from lol_coach.gui.types import MixinBase
from lol_coach.log import get_logger
from lol_coach.modes import (
    ARAM_QUEUES,
    QUEUE_ARAM_MAYHEM,
    QUEUE_NORMAL_BLIND,
    QUEUE_NORMAL_DRAFT,
    QUEUE_RANKED_FLEX,
    QUEUE_RANKED_SOLO,
    is_aram_queue,
)
from lol_coach.riot.models import MatchSummary
from lol_coach.static.icons import (
    champion_ctk,
    item_ctk,
    item_pil,
    rune_pil,
    spell_pil,
    to_ctk,
)
from lol_coach.static.mayhem_augments import resolve_display

_log = get_logger("me")

_HIDDEN_ROLES = frozenset({"", "미상", "없음", "unknown", "none"})

# 증강 아이콘 PIL 메모리 캐시 (id → PIL Image | None)
_aug_img_mem: dict[int, Any] = {}
# 팀 조합 아이템 줄 합성 이미지 캐시 ((아이템 IDs, 크기) → PIL) — FIFO 상한
_item_strip_mem: dict[tuple[tuple[int, ...], int], Any] = {}
_ITEM_STRIP_CAP = 512


def _augment_image(meta: Any, lcu: Any = None) -> Any:
    """증강 아이콘 PIL 이미지 (메모리/디스크 캐시 → LCU 에셋). 실패 시 None."""
    if meta.id and meta.id in _aug_img_mem:
        return _aug_img_mem[meta.id]
    img = None
    try:
        import io

        from PIL import Image as PILImage

        from lol_coach.static import mayhem_augments as ma

        raw = ma.icon_bytes_for(meta, lcu)
        if raw:
            img = PILImage.open(io.BytesIO(raw))
    except Exception as exc:
        _log.debug("증강 아이콘 로드 실패(무시): %s", exc)
    # 성공한 이미지만 캐시 — None 은 LCU 상태가 바뀌면 재시도할 수 있어야 한다
    if meta.id and img is not None:
        _aug_img_mem[meta.id] = img
    return img


def _aug_chip_text(meta: Any, tiers: dict[int, int] | None) -> str:
    """증강 칩 문구 — 이 챔프 기준 blitz 티어가 있으면 아래 줄에 (1티어 = 최상)."""
    tier = (tiers or {}).get(int(getattr(meta, "id", 0) or 0))
    name = str(meta.name)[:10]
    return f"{name}\n이 챔프 {tier}티어" if tier else name


def _item_strip(item_ids: list[int], size: int = 22) -> Any:
    """아이템 아이콘 한 줄을 PIL 한 장으로 합성 (칸마다 CTkLabel = 네이티브 창 3개 대신 1개).

    placeholder가 섞이지 않은 결과만 캐시 — 같은 PIL이라 to_ctk도 같은 CTkImage를 재사용한다.
    """
    key = (tuple(int(i) for i in item_ids), size)
    hit = _item_strip_mem.get(key)
    if hit is not None:
        return hit
    pils = [p for p in (item_pil(i, size) for i in key[0]) if p is not None]
    if not pils:
        return None
    from PIL import Image as PILImage

    gap = 2  # 예전 칸 padx=1 양쪽과 같은 간격
    strip = PILImage.new("RGBA", (len(pils) * (size + gap) - gap, size), (0, 0, 0, 0))
    for i, p in enumerate(pils):
        strip.paste(p.convert("RGBA"), (i * (size + gap), 0))
    if not any(p.info.get("lol_coach_placeholder") for p in pils):
        if len(_item_strip_mem) >= _ITEM_STRIP_CAP:
            _item_strip_mem.pop(next(iter(_item_strip_mem)), None)
        _item_strip_mem[key] = strip
    return strip


def team_line_title(
    champ: str,
    *,
    role: str = "",
    riot_id: str = "",
    is_me: bool = False,
) -> str:
    """복기 팀 줄 제목 — 미상 대신 Riot ID. 라인은 알 때만 앞에 붙인다."""
    me = "  ★나" if is_me else ""
    name = (champ or "").strip() or "?"
    rid = (riot_id or "").strip()
    role_txt = (role or "").strip()
    if role_txt.lower() in _HIDDEN_ROLES:
        role_txt = ""
    if rid and role_txt:
        head = f"{role_txt}  {rid}  {name}"
    elif rid:
        head = f"{rid}  {name}"
    elif role_txt:
        head = f"{role_txt}  {name}"
    else:
        head = name
    return f"{head}{me}"


# 내 전적 큐 필터 (None = 전체)
_ME_QUEUE_FILTERS: list[tuple[str, set[int] | None]] = [
    ("전체", None),
    ("솔랭", {QUEUE_RANKED_SOLO}),
    ("자유랭크", {QUEUE_RANKED_FLEX}),
    ("일반", {QUEUE_NORMAL_DRAFT, QUEUE_NORMAL_BLIND}),
    ("칼바람", set(ARAM_QUEUES) - {QUEUE_ARAM_MAYHEM}),
    ("아수라장", {QUEUE_ARAM_MAYHEM}),
]


class MeDetailMixin(MixinBase):
    def _scroll_me_detail_top(self) -> None:
        """복기 패널 스크롤을 맨 위로 (이전/다음 전환 시)."""
        try:
            canvas = getattr(self.me_detail, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0)
        except Exception:
            pass

    def _highlight_match_btn(self, match_id: str | None) -> None:
        """왼쪽 목록에서 현재 복기 중인 경기 강조."""
        for mid, btn in getattr(self, "_me_match_btns", []) or []:
            try:
                if match_id and mid == match_id:
                    btn.configure(
                        fg_color=ui.PANEL,
                        border_width=1,
                        border_color=ui.GOLD,
                    )
                else:
                    btn.configure(
                        fg_color=ui.ROW,
                        border_width=0,
                        border_color=ui.BORDER,
                    )
            except Exception:
                pass

    def _clear_match_detail(self) -> None:
        """복기 패널을 비우고 안내 문구로 돌아감 (목록으로)."""
        try:
            self._me_detail_gen = int(getattr(self, "_me_detail_gen", 0)) + 1
        except Exception:
            pass
        self._me_match_index: int | None = None
        self._highlight_match_btn(None)
        self._clear(self.me_detail)
        self._lbl(
            self.me_detail,
            "왼쪽 경기를 클릭하면 팀 조합·오브젝트·학습 포인트가 여기에 표시됩니다.\n"
            "복기 중에는 상단 「← 목록」 또는 「이전/다음」으로 이동할 수 있습니다.",
            0,
            color=ui.TEXT_DIM,
            pady=16,
            wrap=420,
        )
        self.status.configure(text="복기 닫음 · 왼쪽에서 다른 경기를 선택하세요")
        self._notify("복기 닫음 — 왼쪽 목록에서 다른 경기를 선택하세요", level="info", ms=2200)

    def _nav_match(self, delta: int) -> None:
        """이전/다음 경기 복기로 이동."""
        form = getattr(self, "form", None)
        matches = list(getattr(form, "matches", None) or [])
        if not matches:
            self._notify("불러온 경기가 없습니다.", level="warn")
            return
        cur = getattr(self, "_me_match_index", None)
        if cur is None:
            cur = 0
        nxt = max(0, min(len(matches) - 1, int(cur) + int(delta)))
        if nxt == cur and delta != 0:
            edge = "첫 경기" if delta < 0 else "마지막 경기"
            self._notify(f"{edge}입니다.", level="info", ms=1600)
            return
        self._show_match_detail(matches[nxt])

    def _show_match_detail(self, m: MatchSummary) -> None:
        """한 판 복기 패널."""
        # 새 복기 시 이전 AI 카드 응답 무시
        try:
            self._ai_gen = int(getattr(self, "_ai_gen", 0)) + 1
        except Exception:
            pass

        self._clear(self.me_detail)
        self._scroll_me_detail_top()
        idx = self._match_index_of(m)
        self._me_match_index = idx
        self._highlight_match_btn(getattr(m, "match_id", None))
        # 타임라인 등 지연 응답용 — 복기 전환 시 이전 응답 무시
        self._me_detail_gen = int(getattr(self, "_me_detail_gen", 0)) + 1

        loc = self.loc
        loc.ensure_loaded()
        champ = loc.champion(m.champion_name) or m.champion_name
        role = loc.role(m.role)
        mode = loc.mode(m.mode_label)
        mark = "승리" if m.win else "패배"
        col = ui.GREEN if m.win else ui.RED_SOFT
        me_riot = next(
            (
                (p.riot_id or "").strip()
                for p in (m.ally_team or [])
                if getattr(p, "is_me", False) and (p.riot_id or "").strip()
            ),
            "",
        )
        if not me_riot:
            me_riot = str(getattr(getattr(self, "profile", None), "riot_id", "") or "").strip()
        head_mid = me_riot if (role or "").strip() in _HIDDEN_ROLES else role

        r = 0
        # ── 뒤로가기 · 이전/다음 네비 ──
        form = getattr(self, "form", None)
        total = len(getattr(form, "matches", None) or [])
        nav = ctk.CTkFrame(self.me_detail, fg_color="transparent")
        nav.grid(row=r, column=0, sticky="ew", padx=8, pady=(6, 2))
        ctk.CTkButton(
            nav,
            text="← 목록",
            width=72,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_SECONDARY),
            command=self._clear_match_detail,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            nav,
            text="◀ 이전",
            width=68,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=lambda: self._nav_match(-1),
            state=("normal" if idx is not None and idx > 0 else "disabled"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            nav,
            text="다음 ▶",
            width=68,
            height=30,
            font=FM,
            **ui.btn(*ui.BTN_TERTIARY),
            command=lambda: self._nav_match(1),
            state=("normal" if idx is not None and total and idx < total - 1 else "disabled"),
        ).pack(side="left", padx=(0, 8))
        if idx is not None and total:
            ui.TextLabel(
                nav,
                text=f"{idx + 1} / {total}",
                font=FM,
                text_color=ui.TEXT_DIM,
            ).pack(side="left")
        r += 1

        # 복기 패널은 클릭마다 새로 그린다 — 네이티브 창 수가 비용이라
        # 텍스트·아이콘은 CTkLabel(창 3개) 대신 TextLabel(창 1개)로 그린다.
        head = self._row_frame(self.me_detail, r, pady=6)
        cicon = self._keep_icon(champion_ctk(m.champion_name, 52))
        if cicon:
            ui.TextLabel(head, image=cicon).pack(side="left", padx=(10, 10), pady=8)
        title = (
            f"[{mark}]  {champ} · {head_mid}  ·  {mode}"
            if head_mid
            else f"[{mark}]  {champ}  ·  {mode}"
        )
        ui.TextLabel(
            head,
            text=(
                f"{title}\n"
                f"{m.duration_min}분  ·  {m.kda_str} (KDA {m.kda_ratio})  ·  "
                f"CS {m.cs} ({m.cs_per_min}/분)  ·  Lv{m.champ_level}"
            ),
            font=FS,
            text_color=col,
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(0, 12), pady=8)
        r += 1
        r = self._lbl(
            self.me_detail,
            ui.provenance_label(getattr(form, "provenance", None)),
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=(0, 4),
            wrap=480,
        )

        # 핵심 지표
        r = self._sec(self.me_detail, "내 지표", r)
        kp = ""
        if m.kill_participation is not None:
            kp_v = m.kill_participation * 100 if m.kill_participation <= 1 else m.kill_participation
            kp = f"킬관여 {kp_v:.0f}%"
        ds = ""
        if m.damage_share is not None:
            ds_v = m.damage_share * 100 if m.damage_share <= 1 else m.damage_share
            ds = f"딜지분 {ds_v:.0f}%"
        # 칼바람·아수라장은 와드·드래곤·바론·전령이 없다 — 협곡 전용 줄은 숨긴다
        aram = is_aram_queue(int(getattr(m, "queue_id", 0) or 0))
        bits = [
            f"딜 {m.damage_to_champs:,}",
            f"받은 피해 {m.damage_taken:,}",
            f"골드 {m.gold:,}" + (f" ({m.gold_per_min}/분)" if m.gold_per_min else ""),
            f"비전 {m.vision_score}",
            f"포탑 파괴 {m.turret_kills}",
        ]
        if not aram:
            bits.insert(4, f"와드 {m.wards_placed}/{m.wards_killed} (제어 {m.control_wards})")
        if m.dpm:
            bits.append(f"DPM {m.dpm:.0f}")
        if kp:
            bits.insert(0, kp)
        if ds:
            bits.insert(1, ds)
        if m.first_blood:
            bits.append("선취혈")
        if m.solo_kills:
            bits.append(f"솔킬 {m.solo_kills}")
        if m.largest_multi_kill >= 2:
            bits.append(f"멀티킬 {m.largest_multi_kill}")
        r = self._lbl(self.me_detail, "  ·  ".join(bits), r, font=FM, wrap=480, pady=4)

        spells = getattr(m, "summoner_spells", None) or []
        primary_rune = getattr(m, "primary_rune", None)
        if spells or primary_rune:
            r = self._sec(self.me_detail, "소환사 주문 · 룬", r)
            sr_row = r
            r = self._lbl(
                self.me_detail,
                "주문 불러오는 중…",
                r,
                font=FM,
                color=ui.TEXT_DIM,
                wrap=480,
            )

        # 아이템 아이콘 행
        if m.items:
            r = self._sec(self.me_detail, "아이템", r)
            items_frame = self._row_frame(self.me_detail, r, pady=3)
            names = self.dd.item_names(m.items) if m.items else []
            for idx, iid in enumerate(m.items[:7]):
                if not iid:
                    continue
                ic = self._keep_icon(item_ctk(int(iid), 28))
                label = names[idx] if idx < len(names) else str(iid)
                self._icon_chip(items_frame, ic, label[:8])
            r += 1

        gen = getattr(self, "_me_detail_gen", 0)

        # ── 획득 증강 (아수라장 등 Arena 계열) ──
        # 카탈로그(CDragon)·아이콘(LCU 에셋)은 네트워크라 워커에서 — 이름 먼저, 아이콘은 나중에
        if getattr(m, "augment_ids", None) or getattr(m, "augment_names", None):
            aug_row = r
            r = self._sec(self.me_detail, "획득 증강", r)
            r = self._lbl(
                self.me_detail,
                "증강 불러오는 중…",
                r,
                font=FM,
                color=ui.TEXT_DIM,
                wrap=480,
            )
            threading.Thread(
                target=self._load_augments, args=(m, aug_row, gen), daemon=True
            ).start()

        # 오브젝트
        r = self._sec(self.me_detail, "오브젝트 (아군 : 적군)", r)
        if m.obj:
            a, e = m.obj.ally, m.obj.enemy
            if not aram:
                r = self._lbl(
                    self.me_detail,
                    f"드래곤  {a.dragons} : {e.dragons}    "
                    f"바론  {a.barons} : {e.barons}    "
                    f"전령  {a.heralds} : {e.heralds}",
                    r,
                    font=FU,
                    wrap=480,
                )
            r = self._lbl(
                self.me_detail,
                f"포탑  {a.towers} : {e.towers}    "
                f"억제기  {a.inhibitors} : {e.inhibitors}"
                + (f"    공허 유충  {a.grubs} : {e.grubs}" if (a.grubs or e.grubs) else ""),
                r,
                font=FU,
                wrap=480,
            )
        else:
            r = self._lbl(self.me_detail, "오브젝트 정보 없음", r, color=ui.TEXT_DIM)

        # 팀 조합
        r = self._sec(self.me_detail, "아군 조합", r)
        r = self._render_team_block(self.me_detail, m.ally_team, r, ally=True)
        r = self._sec(self.me_detail, "적군 조합", r)
        r = self._render_team_block(self.me_detail, m.enemy_team, r, ally=False)

        # ── 타임라인 요약 (백그라운드 fetch, 실패 시 조용히 생략) ──
        tl_row = r
        r = self._sec(self.me_detail, "타임라인", r)
        r = self._lbl(
            self.me_detail,
            "타임라인 불러오는 중…",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            wrap=480,
        )

        skill_row = r
        r = self._sec(self.me_detail, "스킬 순서", r)
        r = self._lbl(
            self.me_detail,
            "스킬 불러오는 중…",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            wrap=480,
        )

        # ── 킬·데스 지도 (타임라인과 같은 스레드에서 합성) ──
        map_row = r
        r = self._sec(self.me_detail, "🗺 킬·데스 지도", r)
        r = self._lbl(
            self.me_detail,
            "지도 불러오는 중…",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            wrap=480,
        )

        match_id = m.match_id
        pid = (m.raw_participant or {}).get("participantId")
        try:
            pid = int(pid) if pid else None
        except (TypeError, ValueError):
            pid = None

        def _tl_work() -> None:
            km = None
            lines, flow = [], {}
            skill_order: list[str] = []
            minimap_pil = snapshot_pil = None
            caption = ""
            tl = raw = None
            spell_pils: list[tuple[int, Any]] = []
            rune_pil_img: Any = None
            from lol_coach.analysis.killmap import (
                build_kill_map,
                map_id_for_queue,
                participant_index,
                skill_order_from_timeline,
            )
            from lol_coach.analysis.review import timeline_brief, timeline_flow
            from lol_coach.gui.map_render import (
                render_collapse_snapshot,
                render_kill_minimap,
            )
            from lol_coach.static.icons import map_pil

            try:
                local_mode = bool(getattr(self, "_me_local_mode", False))
                riot_local = getattr(self, "riot", None)
                if not local_mode and riot_local is not None:
                    try:
                        tl = riot_local.get_match_timeline(match_id)
                        raw = riot_local.get_match(match_id)
                    except Exception:
                        tl = raw = None
                if tl is None or raw is None:
                    from lol_coach.analysis.lcu_match import try_local_timeline
                    from lol_coach.lcu import LCUClient

                    pair = None
                    try:
                        pair = try_local_timeline(
                            LCUClient(), match_id, id_to_key=self.dd.champion_key
                        )
                    except Exception:
                        pair = None
                    if pair is not None:
                        tl, raw = pair
                if tl is not None:
                    lines = timeline_brief(tl, my_participant_id=pid)
                    skill_order = skill_order_from_timeline(tl, pid)
                    if raw is not None:
                        pid_team = {p: pi.team_id for p, pi in participant_index(raw).items()}
                        flow = timeline_flow(tl, my_participant_id=pid, pid_team=pid_team)
            except Exception:
                lines, flow = [], {}
                skill_order = []
            if tl is not None and raw is not None:
                try:
                    km = build_kill_map(tl, raw, pid)
                    if km.my_kills or km.my_deaths:
                        base = map_pil(map_id_for_queue(m.queue_id), 512)
                        minimap_pil = render_kill_minimap(km, base, size=320)
                        if km.collapse is not None:
                            snapshot_pil = render_collapse_snapshot(km, base, size=340)
                            caption = km.collapse.caption
                except Exception:
                    km = None
            if spells or primary_rune:
                try:
                    for sid in spells[:2]:
                        if sid:
                            spell_pils.append((int(sid), spell_pil(int(sid), 28)))
                    if primary_rune:
                        rune_pil_img = rune_pil(int(primary_rune), 28)
                except Exception:
                    spell_pils = []
                    rune_pil_img = None
            self.after(
                0,
                lambda ls=lines, fl=flow, g=gen: self._apply_timeline(tl_row, ls, fl, gen=g),
            )
            self.after(
                0,
                lambda so=skill_order, g=gen: self._apply_skill_order(skill_row, so, gen=g),
            )
            self.after(
                0,
                lambda mp=minimap_pil, sp=snapshot_pil, cap=caption, g=gen: self._apply_killmap(
                    map_row,
                    mp,
                    sp,
                    cap,
                    kills_n=len(km.my_kills) if km else 0,
                    deaths_n=len(km.my_deaths) if km else 0,
                    gen=g,
                ),
            )
            # sr_row 는 주문·룬이 있을 때만 정의된다 (없으면 NameError)
            if spells or primary_rune:
                self.after(
                    0,
                    lambda sp=spell_pils, rp=rune_pil_img, g=gen: self._apply_spells_rune(
                        sr_row, sp, rp, spells, primary_rune, gen=g
                    ),
                )

        threading.Thread(target=_tl_work, daemon=True).start()

        # 심화 복기
        rev = analyze_match(m)
        title_reason = "이 게임을 이긴 주요 이유" if m.win else "이 게임을 진 주요 이유"
        r = self._sec(self.me_detail, title_reason, r)
        for i, t in enumerate(rev.win_loss_reasons, 1):
            r = self._lbl(
                self.me_detail,
                f"{i}.  {t}",
                r,
                color=(ui.BLUE_SOFT if m.win else ui.RED_SOFT),
                wrap=480,
                pady=3,
            )

        r = self._sec(self.me_detail, "내 플레이 — 잘한 점", r)
        for t in rev.good:
            r = self._lbl(self.me_detail, f"✓  {t}", r, color=ui.GREEN, wrap=480, pady=2)

        r = self._sec(self.me_detail, "내 플레이 — 개선할 점 (다음 판 행동)", r)
        for t in rev.improve:
            r = self._lbl(self.me_detail, f"→  {t}", r, color=ui.WARN, wrap=480, pady=2)

        # 한 줄 교훈 강조
        frame = ctk.CTkFrame(
            self.me_detail,
            fg_color=ui.PANEL,
            corner_radius=ui.CARD_RADIUS,
            border_width=ui.CARD_BORDER,
            border_color=ui.BORDER,
        )
        frame.grid(row=r, column=0, sticky="ew", padx=10, pady=(14, 6))
        ctk.CTkLabel(
            frame,
            text=f"다음 경기 교훈\n{rev.lesson}",
            font=FU,
            text_color=ui.GOLD_SOFT,
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(anchor="w", padx=14, pady=12)
        r += 1

        r = self._lbl(
            self.me_detail,
            f"매치 ID  {m.match_id}",
            r,
            font=FM,
            color=ui.TEXT_DIM,
            pady=(8, 8),
            wrap=480,
        )

        # 미니 위젯용 요약 — 방금 판 결과를 위젯에서 바로 확인
        summary = [
            f"[{mark}] {champ} · {role}  ·  {m.duration_min}분",
            f"KDA {m.kda_str}  ·  CS {m.cs}  ·  딜 {m.damage_to_champs:,}",
        ]
        if kp:
            summary.append(f"킬관여 {kp}")
        try:
            if rev.win_loss_reasons:
                summary.append("")
                summary.append("주요 원인: " + rev.win_loss_reasons[0])
            if rev.improve:
                summary.append("")
                summary.append("개선: " + rev.improve[0])
            if rev.lesson:
                summary.append("")
                summary.append("교훈: " + rev.lesson)
        except Exception:
            pass
        self._push_summary(f"🔔 방금 게임 {champ} {mark}", summary)
        key = self._ai_key()
        if key:
            self._maybe_ai(
                self.me_detail,
                lambda on_delta=None: self._ai_coach_review(m, rev, key, on_delta=on_delta),
            )

    @staticmethod
    def _shift_grid_rows(parent: Any, start_row: int, by: int) -> None:
        """start_row 이상 행에 그리드된 위젯을 by만큼 아래로 이동."""
        if by <= 0:
            return
        for w in parent.winfo_children():
            try:
                info = w.grid_info()
            except Exception:
                continue
            if not info:
                continue
            try:
                r = int(info.get("row", 0) or 0)
            except (TypeError, ValueError):
                continue
            if r >= start_row:
                w.grid(row=r + by)

    def _apply_timeline(
        self,
        tl_row: int,
        lines: list[str],
        flow: dict | None = None,
        *,
        gen: int | None = None,
    ) -> None:
        """타임라인 fetch 결과를 복기 패널에 반영 (빈 결과면 자리만 제거)."""
        # 새 복기로 이동했으면 늦게 도착한 이전 응답은 무시 (데이터 섞임 방지)
        if gen is not None and gen != getattr(self, "_me_detail_gen", gen):
            return
        try:
            row = tl_row + 1  # 자기 플레이스홀더 행 (다른 섹션 것은 건드리지 않는다)
            for w in self.me_detail.winfo_children():
                try:
                    txt = str(w.cget("text"))
                except Exception:
                    txt = ""
                if txt == "타임라인 불러오는 중…":
                    w.destroy()
            if lines:
                self._lbl(
                    self.me_detail,
                    " · ".join(lines),
                    row,
                    font=FM,
                    color=ui.TEXT_DIM,
                    wrap=480,
                )
                row += 1
            if flow:
                from lol_coach.gui.trend_viz import pack_flow_chart

                chart = pack_flow_chart(self.me_detail, flow)
                if chart is not None:
                    self._shift_grid_rows(self.me_detail, row, 1)
                    chart.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 6))
        except Exception:
            pass

    def _apply_killmap(
        self,
        map_row: int,
        minimap_pil: Any,
        snapshot_pil: Any,
        caption: str = "",
        *,
        kills_n: int = 0,
        deaths_n: int = 0,
        gen: int | None = None,
    ) -> None:
        """킬·데스 지도 합성 결과 반영 (없으면 플레이스홀더만 제거)."""
        if gen is not None and gen != getattr(self, "_me_detail_gen", gen):
            return
        try:
            row = map_row
            for w in self.me_detail.winfo_children():
                try:
                    txt = str(w.cget("text"))
                except Exception:
                    txt = ""
                if txt == "지도 불러오는 중…":
                    info = w.grid_info()
                    try:
                        row = int(info.get("row", map_row))
                    except (TypeError, ValueError):
                        row = map_row
                    w.destroy()
            if minimap_pil is None:
                return
            from lol_coach.gui.map_render import show_map_popup
            from lol_coach.static.icons import to_ctk

            img_ctk = to_ctk(minimap_pil, 320)
            if img_ctk is None:
                return
            self._keep_icon(img_ctk)

            def _open() -> None:
                show_map_popup(
                    self,
                    minimap_img=minimap_pil,
                    snapshot_img=snapshot_pil,
                    caption=caption,
                )

            self._shift_grid_rows(self.me_detail, row + 1, 2)
            btn = ctk.CTkButton(
                self.me_detail,
                image=img_ctk,
                text="",
                width=320,
                height=320,
                fg_color="transparent",
                hover_color=ui.ROW,
                corner_radius=10,
                command=_open,
            )
            btn.grid(row=row, column=0, sticky="w", padx=10, pady=(2, 2))
            self._lbl(
                self.me_detail,
                f"파랑: 내 킬 {kills_n} · 빨강 X: 내 데스 {deaths_n} · 클릭하면 확대",
                row + 1,
                font=FM,
                color=ui.TEXT_DIM,
                wrap=480,
            )
        except Exception:
            pass

    def _pop_placeholder(self, text: str, min_row: int) -> int | None:
        """min_row 이후의 플레이스홀더 라벨을 지우고 그 그리드 행을 돌려준다 (없으면 None)."""
        for w in self.me_detail.winfo_children():
            try:
                if str(w.cget("text")) != text:
                    continue
                gr = int(w.grid_info().get("row", min_row))
            except Exception:
                continue
            if gr >= min_row:
                w.destroy()
                return gr
        return None

    @staticmethod
    def _icon_chip(
        parent: Any, image: Any, text: str, *, color: str = ui.TEXT_DIM, padx: Any = 4
    ) -> Any:
        """아이콘 위 + 이름 아래 칸 — CTkFrame+CTkLabel 2개(창 8개) 대신 TextLabel 1개."""
        chip = ui.TextLabel(
            parent, text=text, image=image, compound="top", font=FM, text_color=color
        )
        # ipady: 예전 칸(28px 라벨 2개)과 같은 높이
        chip.pack(side="left", padx=padx, pady=6, ipady=7)
        return chip

    def _load_augments(self, m: MatchSummary, aug_row: int, gen: int) -> None:
        """워커: 증강 카탈로그 조회 → 이름 칩 먼저, 아이콘(디스크 → LCU 에셋)은 나중에."""
        metas = resolve_display(
            getattr(m, "augment_ids", None), getattr(m, "augment_names", None)
        )[:6]
        tiers = self._champ_augment_tiers(m) if any(meta.id for meta in metas) else {}
        self.after(0, lambda: self._apply_augments(aug_row, metas, gen=gen, tiers=tiers))
        pils = [_augment_image(meta) for meta in metas]
        if any(img is None and meta.icon_path for img, meta in zip(pils, metas, strict=True)):
            # 디스크 캐시에 없는 아이콘만 LCU 에셋으로 — 클라이언트 연결 확인도 여기서
            lcu = getattr(self, "_aug_lcu", None)
            if lcu is None:
                try:
                    from lol_coach.lcu import LCUClient

                    if LCUClient.is_client_running():
                        lcu = LCUClient()
                        self._aug_lcu: Any = lcu
                except Exception:
                    lcu = None
            if lcu is not None:
                pils = [
                    img if img is not None else _augment_image(meta, lcu)
                    for img, meta in zip(pils, metas, strict=True)
                ]
        if any(img is not None for img in pils):
            self.after(0, lambda: self._apply_augment_icons(pils, gen=gen))

    def _champ_augment_tiers(self, m: MatchSummary) -> dict[int, int]:
        """워커: 아수라장 판이면 이 챔프 기준 blitz 증강 티어 {증강 ID: 1~5} (현재 패치)."""
        if int(getattr(m, "queue_id", 0) or 0) != QUEUE_ARAM_MAYHEM:
            return {}
        try:
            from lol_coach.blitz.mayhem_live import fetch_live_mayhem_top

            top = fetch_live_mayhem_top(str(m.champion_id), client=getattr(self, "blitz", None))
        except Exception:
            return {}
        if top is None:
            return {}
        return {a.augment_id: a.tier for augs in top.by_rarity.values() for a in augs}

    def _apply_augments(
        self, aug_row: int, metas: list, *, gen: int, tiers: dict[int, int] | None = None
    ) -> None:
        if gen != getattr(self, "_me_detail_gen", gen):
            return
        try:
            row = self._pop_placeholder("증강 불러오는 중…", aug_row)
            if row is None:
                return
            if not metas:
                # 카탈로그에 없는 증강뿐 — 섹션 제목도 숨긴다
                for w in self.me_detail.grid_slaves(row=aug_row):
                    w.destroy()
                return
            aug_frame = self._row_frame(self.me_detail, row, pady=3)
            chips = []
            for meta in metas:
                aug_color = {
                    "prismatic": ui.PURPLE,
                    "gold": ui.GOLD,
                    "silver": ui.TEXT_DIM,
                }.get(meta.rarity, ui.TEXT)
                chips.append(
                    self._icon_chip(
                        aug_frame, None, _aug_chip_text(meta, tiers), color=aug_color, padx=6
                    )
                )
            self._me_aug_chips = chips
        except Exception:
            pass

    def _apply_augment_icons(self, pils: list, *, gen: int) -> None:
        if gen != getattr(self, "_me_detail_gen", gen):
            return
        for chip, img in zip(getattr(self, "_me_aug_chips", []), pils, strict=False):
            ic = self._keep_icon(to_ctk(img, 30))
            try:
                if ic is not None and chip.winfo_exists():
                    chip.set_image(ic)
            except Exception:
                pass

    def _apply_skill_order(
        self,
        skill_row: int,
        order: list[str],
        *,
        gen: int | None = None,
    ) -> None:
        if gen is not None and gen != getattr(self, "_me_detail_gen", gen):
            return
        try:
            row = self._pop_placeholder("스킬 불러오는 중…", skill_row)
            if not order:
                return
            if row is None:
                row = skill_row
                self._shift_grid_rows(self.me_detail, row, 1)
            seq = " ".join(order)
            self._lbl(
                self.me_detail,
                seq,
                row,
                font=FM,
                color=ui.TEXT_DIM,
                wrap=480,
            )
        except Exception:
            pass

    def _apply_spells_rune(
        self,
        sr_row: int,
        spell_pils: list[tuple[int, Any]],
        rune_pil_img: Any,
        spells: list,
        primary_rune: int | None,
        *,
        gen: int | None = None,
    ) -> None:
        if gen is not None and gen != getattr(self, "_me_detail_gen", gen):
            return
        try:
            row = self._pop_placeholder("주문 불러오는 중…", sr_row)
            if row is None:
                row = sr_row
            if not any(sid for sid, _ in spell_pils) and not (primary_rune and rune_pil_img):
                return
            sr_frame = self._row_frame(self.me_detail, row, pady=3)
            for sid, pil_img in spell_pils:
                if not sid:
                    continue
                sic = self._keep_icon(to_ctk(pil_img, 28)) if pil_img is not None else None
                self._icon_chip(sr_frame, sic, self.dd.spell_name(int(sid))[:6])
            if primary_rune and rune_pil_img is not None:
                ric = self._keep_icon(to_ctk(rune_pil_img, 28))
                self._icon_chip(
                    sr_frame, ric, self.dd.rune_name(int(primary_rune))[:8], padx=(12, 4)
                )
        except Exception:
            pass

    def _render_team_block(self, parent: Any, players: list, row: int, *, ally: bool) -> int:
        loc = self.loc
        if not players:
            return self._lbl(parent, "참가자 정보 없음", row, color=ui.TEXT_DIM)
        for p in players:
            champ = loc.champion(p.champion_name) or p.champion_name
            role = loc.role(p.role)
            title = team_line_title(
                champ,
                role=role,
                riot_id=getattr(p, "riot_id", "") or "",
                is_me=bool(p.is_me),
            )
            bg = "#132238" if p.is_me else ui.ROW
            frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8)
            frame.grid(row=row, column=0, sticky="ew", padx=10, pady=2)
            frame.grid_columnconfigure(1, weight=1)

            # 한 줄 = CTkFrame + TextLabel 3개 (아이템 6칸은 합성 이미지 한 장)
            ic = self._keep_icon(champion_ctk(p.champion_name, 40))
            if ic:
                ui.TextLabel(frame, image=ic).grid(
                    row=0, column=0, rowspan=2, padx=(8, 6), pady=6
                )
            iic = None
            if p.items:
                iic = self._keep_icon(to_ctk(_item_strip([i for i in p.items[:6] if i])))
            ui.TextLabel(
                frame,
                text=f"{title}\n"
                f"{p.kda_str}  CS {p.cs}  딜 {p.damage_to_champs:,}  "
                f"골드 {p.gold:,}  시야 {p.vision_score}  Lv{p.champ_level}",
                font=FM,
                anchor="w",
                justify="left",
            ).grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(4, 0 if iic else 4))
            if iic:
                ui.TextLabel(frame, image=iic, min_height=0).grid(
                    row=1, column=1, sticky="w", padx=(0, 8), pady=(3, 4)
                )
            row += 1
        return row
