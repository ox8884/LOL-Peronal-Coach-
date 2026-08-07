"""One-shot: split CoachApp methods from gui/app.py into mixin modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src" / "lol_coach" / "gui" / "app.py"
OUT_DIR = ROOT / "src" / "lol_coach" / "gui"

GROUPS: dict[str, set[str]] = {
    "update_mixin": {
        "_version_tuple",
        "_check_update",
        "_start_update",
        "_download_update",
        "_update_failed",
        "_launch_installer",
    },
    "ai_mixin": {
        "_ai_key",
        "_save_llm_key",
        "_ai_model",
        "_refresh_ai_status",
        "_ai_header",
        "_append_ai_card",
        "_push_ai_to_widget",
        "_apply_ai_card",
        "_maybe_ai",
        "_ai_coach_lane",
        "_ai_coach_comp",
        "_ai_coach_aram",
        "_ai_coach_review",
    },
    "sr_tab": {
        "_build_sr",
        "_opt_champ",
        "_lcu_fill_sr",
        "_apply_lcu_sr",
        "_start_sr_champ_watch",
        "_live_fill_sr",
        "_apply_live_sr",
        "_run_sr_quick",
        "_run_sr_detail",
        "_sr_err",
        "_reset_sr",
        "_render_sr_quick",
        "_render_sr_detail",
        "_sr_quick_enter",
        "_push_sr_history",
        "_back_sr_history",
    },
    "aram_tab": {
        "_build_aram",
        "_lcu_fill_aram",
        "_apply_lcu_aram",
        "_start_aram_champ_watch",
        "_aram_enter",
        "_on_aram_aug_changed",
        "_open_augment_picker",
        "_pick_augment",
        "_suggest_augments",
        "_parse_offered_augments",
        "_run_aram",
        "_aram_err",
        "_reset_aram",
        "_render_aram",
        "_augment_missing_card",
        "_live_fill_aram",
        "_apply_live_aram",
        "_push_aram_history",
        "_back_aram_history",
    },
    "me_tab": {
        "_build_me",
        "_show_api_help",
        "_profile_labels",
        "_refresh_profile_menu",
        "_on_profile_pick",
        "_save_current_profile",
        "_delete_current_profile",
        "_export_me",
        "_load_me",
        "_me_err",
        "_prefetch_match_icons",
        "_reset_me",
        "_render_me",
        "_show_match_detail",
        "_apply_timeline",
        "_render_team_block",
    },
    "live_mixin": {
        "_prepare_riot_for_live",
        "_start_game_end_watcher",
        "_on_game_ended",
        "_notify_game_end",
    },
}

CLASS_NAMES = {
    "update_mixin": "UpdateMixin",
    "ai_mixin": "AiMixin",
    "sr_tab": "SrTabMixin",
    "aram_tab": "AramTabMixin",
    "me_tab": "MeTabMixin",
    "live_mixin": "LiveMixin",
}

DOCS = {
    "update_mixin": "자동 업데이트 UI 핸들러",
    "ai_mixin": "선택형 AI 코칭 카드·키·모델",
    "sr_tab": "소환사의 협곡 탭",
    "aram_tab": "ARAM 아수라장 탭",
    "me_tab": "내 전적 탭",
    "live_mixin": "인게임/종료 감지 공통",
}


def main() -> None:
    src = SRC_PATH.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CoachApp")

    methods: dict[str, tuple[int, int]] = {}
    for m in cls.body:
        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert m.end_lineno is not None
            methods[m.name] = (m.lineno, m.end_lineno)

    name_to_group: dict[str, str] = {}
    for g, names in GROUPS.items():
        for n in names:
            if n not in methods:
                raise SystemExit(f"missing method: {n}")
            name_to_group[n] = g

    def method_src(name: str) -> str:
        s, e = methods[name]
        return "".join(lines[s - 1 : e])

    for g, names in GROUPS.items():
        ordered = sorted(names, key=lambda n: methods[n][0])
        body = "\n\n".join(method_src(n) for n in ordered)
        content = (
            f'"""{DOCS[g]}\n\n'
            "CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.\n"
            '"""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n\n"
            f"class {CLASS_NAMES[g]}:\n"
            f"{body}\n"
        )
        path = OUT_DIR / f"{g}.py"
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(ordered)} methods)")

    core_methods = [n for n in methods if n not in name_to_group]
    core_ordered = sorted(core_methods, key=lambda n: methods[n][0])
    core_body = "\n\n".join(method_src(n) for n in core_ordered)
    print("core methods:", ", ".join(core_ordered))

    preamble = "".join(lines[: cls.lineno - 1])
    post = "".join(lines[cls.end_lineno :])

    mixin_import = (
        "from lol_coach.gui.ai_mixin import AiMixin\n"
        "from lol_coach.gui.aram_tab import AramTabMixin\n"
        "from lol_coach.gui.live_mixin import LiveMixin\n"
        "from lol_coach.gui.me_tab import MeTabMixin\n"
        "from lol_coach.gui.sr_tab import SrTabMixin\n"
        "from lol_coach.gui.update_mixin import UpdateMixin\n"
    )
    if "from lol_coach.gui.ai_mixin" not in preamble:
        preamble = preamble.rstrip() + "\n" + mixin_import + "\n"

    new_app = (
        preamble
        + "class CoachApp(\n"
        + "    UpdateMixin,\n"
        + "    AiMixin,\n"
        + "    SrTabMixin,\n"
        + "    AramTabMixin,\n"
        + "    MeTabMixin,\n"
        + "    LiveMixin,\n"
        + "    ctk.CTk,\n"
        + "):\n"
        + core_body
        + "\n"
        + post
    )
    SRC_PATH.write_text(new_app, encoding="utf-8")
    print(f"rewrote {SRC_PATH.relative_to(ROOT)} ({new_app.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
