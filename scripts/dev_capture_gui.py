"""GUI 검증 캡처 (개발 전용).

앱을 보조 모니터(x=2000)에 띄워 화면을 PNG로 저장하고 닫는다. 메인 모니터를 쓰지 않는다.
- 창 내용은 PrintWindow 로 받는다 (가려져 있어도 찍힌다. ImageGrab 은 검게 나올 수 있다).
- 롤 클라이언트 감시와 알림 토스트를 끄고, 개발용 ui.json 을 건드리지 않는다.
- 클라이언트가 꺼져 있어도 me_fake / session_fake 로 전적·세션 화면을 볼 수 있다.

usage: python scripts/dev_capture_gui.py <outdir> [screens...]
screens: aram aram_result phase tier sr me me_data me_fake me_review session session_fake settings widget
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_winshot import shot

import lol_coach.config as cfg

_real_load = cfg.load_ui_settings


def _load():
    d = dict(_real_load())
    d.update(
        geometry=GEOMETRY,
        widget_visible=False,
        last_nav="ARAM 아수라장",
        widget_geometry=WIDGET_GEOMETRY,
        discord_review=False,
        game_start_notify=False,
    )
    d.pop("widget_font_size", None)  # 기본 크기로 본다
    return d


cfg.load_ui_settings = _load
cfg.save_ui_settings = lambda **kw: cfg.UI_PATH

# 창 크기를 바꿔 보려면 LOL_CAP_GEOMETRY=960x998+2000+20 (x 는 보조 모니터 안쪽으로)
GEOMETRY = os.environ.get("LOL_CAP_GEOMETRY", "1280x860+2000+60")
WIDGET_GEOMETRY = os.environ.get("LOL_CAP_WIDGET", "340x460+3360+80")

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
screens = sys.argv[2:] or ["aram", "aram_result", "tier", "sr", "me", "session"]

from lol_coach.gui.app import CoachApp  # noqa: E402 — 설정 대역을 먼저 걸어야 한다

# 실제 게임에 반응하지 않도록 감시를 끈다
for name in ("_start_mayhem_select_watcher", "_start_live_client_watcher"):
    setattr(CoachApp, name, lambda self: None)
# 알림 토스트는 메인 모니터 위에 뜬다 — 캡처 중에는 띄우지 않는다
CoachApp._notify = lambda self, *a, **k: None

app = CoachApp()
app.geometry(GEOMETRY)
app.update()
NAV = {
    "aram": "ARAM 아수라장",
    "tier": "티어표",
    "sr": "소환사의 협곡",
    "me": "내 전적",
    "session": "세션 리포트",
}


def fake_select(app):
    """밴픽 상태 재현: 유나라 + 벤치(릴리아·소나·티모·가렌)."""
    from types import SimpleNamespace

    from lol_coach.analysis.aram_mayhem import champ_select_advice

    dd = app.dd
    ids = {
        n: int(dd.resolve_champion(n)["key"])
        for n in ("Yunara", "Lillia", "Sona", "Teemo", "Garen")
    }
    tiers = app.mayhem.champion_tiers()
    info = SimpleNamespace(
        game_id=777,
        my_champion_id=ids["Yunara"],
        in_champ_select=True,
        is_aram=True,
        bench_champion_ids=[ids["Lillia"], ids["Sona"], ids["Teemo"], ids["Garen"]],
        rerolls_remaining=1,
        my_team=[],
        their_team=[],
    )
    adv = champ_select_advice(
        info.my_champion_id,
        tiers,
        dd.champion_name,
        bench_ids=info.bench_champion_ids,
        rerolls=1,
        win_rates=app.mayhem.champion_win_rates(),
    )
    return info, adv, tiers


steps = list(screens)


def run():
    if not steps:
        app.after(300, app._on_close)
        return
    s = steps.pop(0)
    delay = 1800
    try:
        if s in NAV:
            app._select_nav(NAV[s])
            delay = 4200 if s in ("tier", "session") else 1800
        elif s == "aram_result":
            app._select_nav("ARAM 아수라장")
            info, adv, tiers = fake_select(app)
            app._on_mayhem_select(info, adv)
            hook = getattr(app, "_capture_select", None)
            if hook:
                hook(info, adv, tiers)
            else:
                app._aram_select_advice = (info.my_champion_id, adv)
                app.aram_tab._aram_quick_pick("유나라")
            import time as _t

            app._select_seen_at = _t.monotonic() + 60
            app._set_phase("밴픽")
            delay = 9000
        elif s == "me_data":
            app._select_nav("내 전적")
            app.me_tab._load_me_local(count=20, platform="kr")
            delay = 12000
        elif s == "me_fake":
            # 롤 클라이언트가 꺼져 있을 때 — 만든 경기 기록으로 화면만 확인
            import time as _t

            from lol_coach.riot.client import aggregate_form
            from lol_coach.riot.models import MatchSummary, PlayerProfile

            rows = [
                ("Cassiopeia", False, 5, 11, 29, 37837, 1044),
                ("Yunara", True, 21, 9, 12, 44661, 798),
                ("Ekko", True, 18, 11, 32, 56909, 978),
                ("LeeSin", False, 13, 13, 22, 35405, 990),
                ("Yasuo", True, 8, 7, 19, 21492, 942),
                ("Ezreal", False, 7, 5, 12, 13672, 498),
                ("Irelia", False, 9, 12, 20, 30111, 1100),
                ("Ahri", True, 12, 6, 25, 41200, 1010),
            ]
            now = int(_t.time() * 1000)
            ms = [
                MatchSummary(
                    match_id=f"NA1_{9000 + i}",
                    champion_name=c,
                    champion_id=0,
                    role="",
                    lane="",
                    win=w,
                    kills=k,
                    deaths=d,
                    assists=a,
                    cs=40 + i * 5,
                    gold=12000 + i * 300,
                    damage_to_champs=dmg,
                    vision_score=0,
                    game_duration_s=dur,
                    queue_id=2400,
                    game_end_timestamp=now - i * 1500000,
                )
                for i, (c, w, k, d, a, dmg, dur) in enumerate(rows)
            ]
            app._select_nav("내 전적")
            form = aggregate_form(
                PlayerProfile(game_name="", tag_line="", puuid="x", platform="na1"), ms
            )
            app.me_tab._me_form_full = form
            app.form = form
            app.me_tab._render_me(form)
            delay = 3500
        elif s == "session_fake":
            import time as _t

            from lol_coach.analysis.session import analyze_session
            from lol_coach.riot.models import MatchSummary

            rows = [
                ("Cassiopeia", False, 5, 11, 29, 37837, 1044),
                ("Yunara", True, 21, 9, 12, 44661, 798),
                ("Ekko", False, 6, 12, 18, 26909, 978),
                ("LeeSin", False, 13, 13, 22, 35405, 990),
            ]
            now = int(_t.time() * 1000)
            ms = [
                MatchSummary(
                    match_id=f"NA1_{9100 + i}",
                    champion_name=c,
                    champion_id=0,
                    role="",
                    lane="",
                    win=w,
                    kills=k,
                    deaths=d,
                    assists=a,
                    cs=40,
                    gold=12000,
                    damage_to_champs=dmg,
                    vision_score=0,
                    game_duration_s=dur,
                    queue_id=2400,
                    game_end_timestamp=now - i * 1500000,
                )
                for i, (c, w, k, d, a, dmg, dur) in enumerate(rows)
            ]
            app._select_nav("세션 리포트")
            app._session_loaded = True
            app._render_session(analyze_session(ms), source="롤 클라이언트 오늘 조회")
            delay = 2500
        elif s == "me_review":
            form = getattr(app, "form", None)
            ms = list(getattr(form, "matches", []) or [])
            print("matches:", len(ms), flush=True)
            if ms:
                app.me_tab.show_match(ms[0])
            delay = 8000
        elif s == "phase":
            app._select_nav("ARAM 아수라장")
            app._set_phase("밴픽")
            delay = 600
        elif s == "settings":
            app._open_settings()
            delay = 2500
        elif s == "widget":
            app._set_widget_visible(True, persist=False)
            app._push_summary(
                "🎮 유나라 증강 TOP3 · 16.22",
                [
                    "프리즘: 미친 과학자 · 결투의 대가 · 탭 댄서",
                    "골드: 상급 조준경 부착 · 영혼 흡수 · 치명적 리듬",
                    "실버: 육중한 힘 · 불을 밝혀 · 광신자",
                    "아이템: 크라켄 학살자 → 루난의 허리케인 → 광전사의 군화 → 무한의 대검 → 도미닉 경의 인사 → 몰락한 왕의 검",
                ],
            )
            delay = 2500
    except Exception:
        import traceback

        traceback.print_exc()

    def snap():
        try:
            target = app
            if s == "settings":
                target = getattr(app, "_settings_win", None) or app
                target.geometry("+2200+90")
                target.update()
            elif s == "widget":
                target = app._widget
                target.geometry("+" + WIDGET_GEOMETRY.split("+", 1)[1])
                target.update()
            shot(target, str(out / f"{s}.png"))
            if s == "settings" and target is not app:
                target.destroy()
        except Exception:
            import traceback

            traceback.print_exc()
        run()

    app.after(delay, snap)


app.after(3500, run)
app.mainloop()
