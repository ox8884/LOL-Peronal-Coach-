"""Add imports to split mixins and point app.py at constants."""

from __future__ import annotations

from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "src" / "lol_coach" / "gui"

CONST_IMPORT = """from lol_coach.gui.constants import (
    AI_BODY,
    AI_MODELS,
    AI_SECTION,
    AI_SUMMARY,
    AI_TITLE,
    FB,
    FCH,
    FM,
    FS,
    FT,
    FU,
    PLATFORMS,
    ROLES,
    counter_tier as _counter_tier,
)
from lol_coach.gui.ai_text import ai_key_points as _ai_key_points
from lol_coach.gui.ai_text import ai_lines as _ai_lines
"""

MIXIN_HEADERS: dict[str, str] = {
    "update_mixin.py": '''"""자동 업데이트 UI 핸들러

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Any

from lol_coach import __version__
from lol_coach.gui import components as ui


class UpdateMixin:
''',
    "ai_mixin.py": '''"""선택형 AI 코칭 카드·키·모델

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
''',
    "live_mixin.py": '''"""인게임/종료 감지 공통

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Any

from lol_coach.config import DEFAULT_PLATFORM, load_settings, save_api_key, save_player
from lol_coach.riot.client import RiotClient


class LiveMixin:
''',
    "sr_tab.py": '''"""소환사의 협곡 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FS, FU, ROLES, counter_tier as _counter_tier
from lol_coach.modes import MODE_SUMMONERS_RIFT
from lol_coach.static.icons import champion_ctk, champion_pil, item_name_ctk, item_pil_by_name


class SrTabMixin:
''',
    "aram_tab.py": '''"""ARAM 아수라장 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.gui import components as ui
from lol_coach.gui.constants import FB, FCH, FM, FS, FU
from lol_coach.static.augment_icons import augment_ctk, augment_pil
from lol_coach.static.icons import champion_ctk, champion_pil, item_name_ctk, item_pil_by_name


class AramTabMixin:
''',
    "me_tab.py": '''"""내 전적 탭

CoachApp 믹스인 — 메서드는 self 를 CoachApp 인스턴스로 가정한다.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from lol_coach.analysis.export import export_matches_csv, export_matches_json
from lol_coach.analysis.pool import diagnose_pool
from lol_coach.analysis.review import analyze_match
from lol_coach.config import (
    DEFAULT_PLATFORM,
    add_profile,
    list_profiles,
    load_settings,
    remove_profile,
    save_api_key,
    save_player,
)
from lol_coach.gui import components as ui
from lol_coach.gui.constants import AI_MODELS, FM, FS, FU, PLATFORMS
from lol_coach.riot.client import RiotAPIError, RiotClient
from lol_coach.static.icons import champion_ctk, item_ctk


class MeTabMixin:
''',
}


def replace_class_header(path: Path, new_header: str) -> None:
    text = path.read_text(encoding="utf-8")
    # Keep from first method (def ) after class line
    idx = text.find("\n    def ")
    if idx < 0:
        raise SystemExit(f"no methods in {path}")
    body = text[idx + 1 :]  # starts with '    def '
    path.write_text(new_header + body, encoding="utf-8")
    print(f"fixed imports: {path.name}")


def fix_app() -> None:
    path = GUI / "app.py"
    text = path.read_text(encoding="utf-8")
    start = text.find("ROLES = [")
    if start < 0:
        if "from lol_coach.gui.constants import" in text:
            print("app.py already uses constants")
            return
        raise SystemExit("ROLES block not found in app.py")
    end = text.find("from lol_coach.gui.ai_mixin import")
    if end < 0:
        end = text.find("class CoachApp")
    # also remove _counter_tier if between
    # Find end of _counter_tier function
    ct = text.find("def _counter_tier")
    if ct > start:
        # end of function: next blank line then non-indent or next import/class
        rest = text[ct:]
        # find double newline after return "C"
        marker = '    return "C"\n'
        m = rest.find(marker)
        if m >= 0:
            end = ct + m + len(marker)
            # skip following blank lines
            while end < len(text) and text[end] == "\n":
                end += 1
    # If ai_text imports are in the block, drop them (CONST_IMPORT re-adds)
    new_text = text[:start] + CONST_IMPORT + "\n" + text[end:]
    # dedupe ai_text imports if CONST_IMPORT already has them and old remains
    while new_text.count("from lol_coach.gui.ai_text import") > 1:
        # keep first only
        first = new_text.find("from lol_coach.gui.ai_text import")
        second = new_text.find("from lol_coach.gui.ai_text import", first + 1)
        # remove line at second
        line_end = new_text.find("\n", second)
        new_text = new_text[:second] + new_text[line_end + 1 :]
    path.write_text(new_text, encoding="utf-8")
    print("fixed app.py constants")


def main() -> None:
    for name, header in MIXIN_HEADERS.items():
        replace_class_header(GUI / name, header)
    fix_app()


if __name__ == "__main__":
    main()
