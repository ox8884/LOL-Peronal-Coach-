# Hextech 리디자인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 롤 실전 코치 CustomTkinter GUI를 LoL 공식 Hextech 톤(네이비 베이스 + 골드 액센트 + 헥사딕 블루)으로 전면 재스타일링한다.

**Architecture:** 새 `gui/theme.py` 디자인 토큰 단일 출처 + `assets/hextech.json` CTk 커스텀 컬러 테마. 4개 GUI 파일(`app.py`, `setup_dialog.py`, `api_help.py`, `champ_autocomplete.py`)의 하드코딩 색/폰트를 토큰 참조로 교체. 기존 모듈 상수(`FT`, `FU`, `FB`, `FM`, `FS`)는 backward-compat alias로 남겨 기존 테스트(`app_module.FB` 등 참조) 통과 유지하되, 내부 값은 토큰에서 가져온다.

**Tech Stack:** Python 3.11+, customtkinter (CTk), tkinter, Malgun Gothic (시스템 폰트), pytest, ruff.

## Global Constraints

- **폰트**: 모든 폰트는 `("Malgun Gothic", <size>[, "bold"])` 형식 유지. 시스템 폰트 번들 안 함.
- **색 토큰**: 모든 색은 `gui/theme.py`의 `COLORS` dict에서 (light, dark) 튜플로 참조. 직접 hex 코드 금지.
- **기존 테스트 호환성**: `tests/test_gui_threading.py`는 `app_module.FT`, `app_module.FS`, `app_module.FB`, `app_module.FM` 등의 모듈 상수에 의존하므로, 이 상수는 제거하지 않고 토큰 기반 값으로 재정의.
- **기능/레이아웃 불변**: 위젯 id, 메서드 이름, grid 배치, RiotClient/UGGClient/DataDragon 호출부는 절대 수정하지 않는다. 스타일 파라미터(`fg_color`, `text_color`, `font`, `corner_radius`, `border_width` 등)만 교체.
- **OUT OF SCOPE**: 헥사곤 패턴 배경/글로우/캔버스 드로잉/폰트 번들/기능 추가/레이아웃 변경/아이콘 에셋/윈도우 크기 변경.
- **커밋**: 각 Task 끝에 atomic commit. 메시지는 `feat:`/`refactor:`/`test:`/`style:` prefix.

---

## File Structure

| 파일 | 변경 | 책임 |
|---|---|---|
| `src/lol_coach/gui/theme.py` | **Create** | 디자인 토큰 (COLORS, FONTS, SPACE, CORNER) + `apply_hextech_theme()` 함수 |
| `assets/hextech.json` | **Create** | CTk 커스텀 컬러 테마 JSON (프리미티브별 light/dark 색) |
| `src/lol_coach/gui/app.py` | **Modify** | 모듈 상수를 토큰 참조로 재정의, `theme.py` import, `apply_hextech_theme()` 호출, `_sec`/`_row_frame`/카드/버튼/라벨 스타일 토큰 교체, 이모지 제거 |
| `src/lol_coach/gui/setup_dialog.py` | **Modify** | 폰트 상수 → 토큰 import |
| `src/lol_coach/gui/api_help.py` | **Modify** | 폰트 상수 → 토큰 import (해당시) |
| `src/lol_coach/gui/champ_autocomplete.py` | **Modify** | `_FONT` → 토큰, 색 하드코딩 → 토큰 |
| `tests/test_theme.py` | **Create** | theme.py 단위 테스트 |

---

### Task 1: theme.py 디자인 토큰 + hextech.json 커스텀 테마

**Files:**
- Create: `src/lol_coach/gui/theme.py`
- Create: `assets/hextech.json`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: `customtkinter` (for `set_default_color_theme`)
- Produces:
  - `COLORS: dict[str, tuple[str, str]]` — 18개 색 토큰 (light, dark) 튜플
  - `FONTS: dict[str, tuple[str, int] | tuple[str, int, str]]` — 6개 폰트 토큰
  - `SPACE: dict[str, int]` — 6개 여백 토큰
  - `CORNER: dict[str, int]` — 3개 코너 토큰
  - `apply_hextech_theme() -> None` — `ctk.set_default_color_theme(<hextech.json 경로>)` 호출
  - `THEME_JSON_PATH -> str` — hextech.json 절대 경로 상수

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme.py`:

```python
"""gui.theme 단위 테스트 — 토큰 구조 및 hex 포맷 검증."""

import re

from lol_coach.gui import theme

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_colors_all_tokens_exist():
    """스펙에 정의된 18개 색 토큰이 모두 존재한다."""
    expected = {
        "BG_SHELL",
        "BG_PANEL",
        "BG_PANEL_RAISED",
        "BG_TAB",
        "ACCENT_GOLD",
        "ACCENT_GOLD_BRIGHT",
        "ACCENT_HEX",
        "ACCENT_HEX_DEEP",
        "TEXT_PRIMARY",
        "TEXT_MUTED",
        "BORDER_GOLD",
        "ROLE_ACTIVE",
        "ROLE_IDLE",
        "BTN_LIVE_BG",
        "BTN_LIVE_HOVER",
        "ACCENT_GOOD",
        "ACCENT_WARN",
        "ACCENT_DANGER",
    }
    assert set(theme.COLORS.keys()) == expected


def test_colors_are_light_dark_tuples():
    """모든 색 토큰은 (light, dark) 2-튜플이며 #RRGGBB 포맷이다."""
    for name, pair in theme.COLORS.items():
        assert isinstance(pair, tuple), f"{name} is not a tuple"
        assert len(pair) == 2, f"{name} must have exactly light+dark"
        for i, color in enumerate(pair):
            assert isinstance(color, str), f"{name}[{i}] must be str"
            assert _HEX_RE.match(color), f"{name}[{i}]={color} is not #RRGGBB"


def test_fonts_all_tokens_exist():
    """6개 폰트 토큰이 존재한다."""
    expected = {"TITLE", "HEADING", "BODY", "SMALL", "CAPTION", "TAB"}
    assert set(theme.FONTS.keys()) == expected


def test_fonts_all_malgun_gothic():
    """모든 폰트는 Malgun Gothic이다."""
    for name, font in theme.FONTS.items():
        assert font[0] == "Malgun Gothic", f"{name} uses {font[0]}"


def test_space_and_corner_tokens():
    """여백/코너 토큰이 정의되어 있다."""
    assert theme.SPACE["PAD_X"] == 16
    assert theme.SPACE["GAP_LG"] == 20
    assert theme.CORNER["CARD"] == 10
    assert theme.CORNER["INPUT"] == 6
    assert theme.CORNER["PILL"] == 16


def test_theme_json_path_exists():
    """hextech.json 파일이 존재한다."""
    import os

    assert os.path.isfile(theme.THEME_JSON_PATH), (
        f"hextech.json not found at {theme.THEME_JSON_PATH}"
    )


def test_theme_json_is_valid_ctk_schema():
    """hextech.json은 CTk 테마 스키마(필수 프리미티브 키 포함)를 따른다."""
    import json

    with open(theme.THEME_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert "CTk" in data
    assert "CTkButton" in data
    assert "CTkEntry" in data
    assert "CTkFrame" in data
    assert "CTkTabview" in data
    assert "CTkScrollableFrame" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lol_coach.gui.theme'`

- [ ] **Step 3: Write theme.py**

Create `src/lol_coach/gui/theme.py`:

```python
"""Hextech 디자인 토큰 — LoL 공식 클라이언트 톤의 단일 스타일 출처.

모든 GUI 파일은 색/폰트/여백/코너 값을 이 모듈에서 import 한다.
색은 항상 (light, dark) 튜플이므로 CTk appearance_mode 전환에 대응한다.
"""

from __future__ import annotations

import os

import customtkinter as ctk

# (light, dark) 튜플 — CTk appearance_mode 전환 대비
COLORS: dict[str, tuple[str, str]] = {
    "BG_SHELL":          ("#F5F5F0", "#010A13"),
    "BG_PANEL":          ("#FFFFFF", "#0A1428"),
    "BG_PANEL_RAISED":   ("#E8E8E0", "#1E2328"),
    "BG_TAB":            ("#ECECE4", "#091428"),
    "ACCENT_GOLD":        ("#785A28", "#C8AA6E"),
    "ACCENT_GOLD_BRIGHT": ("#C8AA6E", "#F0E6D2"),
    "ACCENT_HEX":         ("#0397AB", "#0AC8B9"),
    "ACCENT_HEX_DEEP":    ("#005A82", "#005A82"),
    "TEXT_PRIMARY":   ("#1E2328", "#F0E6D2"),
    "TEXT_MUTED":     ("#555555", "#A09B8C"),
    "BORDER_GOLD":    ("#C8AA6E", "#463714"),
    "ROLE_ACTIVE":    ("#0397AB", "#0AC8B9"),
    "ROLE_IDLE":      ("#A29788", "#3C3C41"),
    "BTN_LIVE_BG":    ("#2E7D32", "#0A3D0A"),
    "BTN_LIVE_HOVER": ("#388E3C", "#0E5A0E"),
    "ACCENT_GOOD":    ("#3A8A8A", "#46A0A0"),
    "ACCENT_WARN":    ("#785A28", "#C8AA6E"),
    "ACCENT_DANGER":  ("#A33A3A", "#BA3B3B"),
}

FONTS: dict[str, tuple[str, int] | tuple[str, int, str]] = {
    "TITLE":   ("Malgun Gothic", 18, "bold"),
    "HEADING": ("Malgun Gothic", 14, "bold"),
    "BODY":    ("Malgun Gothic", 13),
    "SMALL":   ("Malgun Gothic", 12),
    "CAPTION": ("Malgun Gothic", 11),
    "TAB":     ("Malgun Gothic", 14, "bold"),
}

SPACE: dict[str, int] = {
    "PAD_X": 16,
    "PAD_Y": 12,
    "GAP_XS": 4,
    "GAP_SM": 8,
    "GAP_MD": 12,
    "GAP_LG": 20,
}

CORNER: dict[str, int] = {"CARD": 10, "INPUT": 6, "PILL": 16}

THEME_JSON_PATH: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "assets",
    "hextech.json",
)


def apply_hextech_theme() -> None:
    """앱 진입점에서 1회 호출 — CTk 커스텀 컬러 테마 적용."""
    ctk.set_default_color_theme(THEME_JSON_PATH)
```

- [ ] **Step 4: Write hextech.json**

Create `assets/hextech.json` — CTk v5 커스텀 테마 스키마. 각 프리미티브별 `fg_color`, `border_color`, `text_color`, `hover_color`를 (light, dark) 문자열 쌍으로 정의:

```json
{
    "CTk": {
        "fg_color": ["#F5F5F0", "#010A13"],
        "bg_color": ["#F5F5F0", "#010A13"]
    },
    "CTkFrame": {
        "fg_color": ["#FFFFFF", "#0A1428"],
        "border_color": ["#C8AA6E", "#463714"],
        "border_width": 0,
        "corner_radius": 10
    },
    "CTkLabel": {
        "fg_color": "transparent",
        "text_color": ["#1E2328", "#F0E6D2"]
    },
    "CTkButton": {
        "fg_color": ["#0397AB", "#0AC8B9"],
        "hover_color": ["#005A82", "#005A82"],
        "border_color": ["#C8AA6E", "#463714"],
        "border_width": 0,
        "corner_radius": 6,
        "text_color": ["#F5F5F0", "#010A13"]
    },
    "CTkEntry": {
        "fg_color": ["#E8E8E0", "#1E2328"],
        "border_color": ["#C8AA6E", "#463714"],
        "border_width": 1,
        "corner_radius": 6,
        "text_color": ["#1E2328", "#F0E6D2"],
        "placeholder_text_color": ["#555555", "#A09B8C"]
    },
    "CTkTabview": {
        "fg_color": ["#ECECE4", "#091428"],
        "border_color": ["#C8AA6E", "#463714"],
        "border_width": 1,
        "corner_radius": 10,
        "segmented_button_fg_color": ["transparent", "transparent"],
        "segmented_button_selected_color": ["#0397AB", "#0AC8B9"],
        "segmented_button_selected_hover_color": ["#005A82", "#005A82"],
        "segmented_button_unselected_color": ["transparent", "transparent"],
        "segmented_button_unselected_hover_color": ["#E8E8E0", "#1E2328"],
        "segmented_button_text_color": ["#1E2328", "#F0E6D2"],
        "segmented_button_text_color_selected": ["#010A13", "#010A13"]
    },
    "CTkScrollableFrame": {
        "fg_color": ["#ECECE4", "#091428"],
        "border_color": ["#C8AA6E", "#463714"],
        "border_width": 1,
        "corner_radius": 10,
        "label_fg_color": ["#785A28", "#C8AA6E"],
        "label_text_color": ["#F0E6D2", "#1E2328"]
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`
Expected: 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lol_coach/gui/theme.py assets/hextech.json tests/test_theme.py
git commit -m "feat(theme): add Hextech design tokens module + CTk custom theme JSON"
```

---

### Task 2: app.py 모듈 상수를 토큰 기반으로 재정의 + apply_hextech_theme 적용

**Goal**: `app.py`의 모듈 상단 `FT`/`FS`/`FU`/`FB`/`FM`과 `set_default_color_theme("blue")`를 교체. 기존 테스트가 `app_module.FT`/`app_module.FB`/`app_module.FS`/`app_module.FM`을 참조하므로, 상수는 제거하지 않고 `theme.py` 토큰을 참조하는 값으로 재정의.

**Files:**
- Modify: `src/lol_coach/gui/app.py:11-44` (import 추가, set_default_color_theme 교체, FT/FS/FU/FB/FM 재정의)
- Test: `tests/test_theme.py`, `tests/test_gui_threading.py`

**Interfaces:**
- Consumes: `from lol_coach.gui.theme import COLORS, FONTS, SPACE, CORNER, apply_hextech_theme`
- Produces: `app_module.FT`, `app_module.FS`, `app_module.FU`, `app_module.FB`, `app_module.FM` (backward-compat alias, 값은 토큰 기반)

- [ ] **Step 1: Write a verification test (existing tests must pass)**

`tests/test_gui_threading.py`는 이미 `app_module.FB`, `app_module.FS`, `app_module.FE`를 참조한다. 별도 새 테스트 없이 기존 테스트 통과가 검증 조건.

- [ ] **Step 2: Modify app.py import block and constants**

Edit `src/lol_coach/gui/app.py` — replace lines 29-44:

```python
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ROLES = [
    ("탑", "top"),
    ("정글", "jungle"),
    ("미드", "mid"),
    ("원딜", "adc"),
    ("서폿", "support"),
]

FT = ("Malgun Gothic", 18, "bold")
FS = ("Malgun Gothic", 14, "bold")
FU = ("Malgun Gothic", 13)
FB = ("Malgun Gothic", 12)
FM = ("Malgun Gothic", 11)
```

with:

```python
from lol_coach.gui.theme import COLORS, FONTS, SPACE, CORNER, apply_hextech_theme

ctk.set_appearance_mode("dark")
apply_hextech_theme()

ROLES = [
    ("탑", "top"),
    ("정글", "jungle"),
    ("미드", "mid"),
    ("원딜", "adc"),
    ("서폿", "support"),
]

# backward-compat alias — 기존 테스트(app_module.FB 등) 호환을 위해 유지.
# 새 코드는 theme.FONTS["TITLE"] 등을 직접 사용할 것.
FT = FONTS["TITLE"]
FS = FONTS["HEADING"]
FU = FONTS["BODY"]
FB = FONTS["SMALL"]
FM = FONTS["CAPTION"]
```

- [ ] **Step 3: Run tests to verify nothing breaks**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All tests PASS. (`test_gui_threading.py`는 `app_module.FB`, `app_module.FS`를 참조하므로 alias가 정상 동작해야 함)

- [ ] **Step 4: LSP diagnostics on app.py**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "refactor(gui): wire app.py to theme tokens + apply hextech theme"
```

---

### Task 3: app.py — `_sec` 섹션 헤더 리디자인 (화살표 제거 + 골드 헤어라인)

**Goal**: `▸ 제목` → 골드 볼드 제목 (`▸` 제거) + 하단 1px 골드 헤어라인 추가.

**Files:**
- Modify: `src/lol_coach/gui/app.py:159-163` (the `_sec` method)
- Test: `tests/test_gui_threading.py` (existing test references `▸ {title}` format)

**Important**: `test_gui_threading.py:173`에서 `text=f"▸ {title}"` 형식을 테스트 헬퍼가 직접 재정의하고 있다 (`app_module.FS`를 사용). 실제 `CoachApp._sec` 메서드를 테스트하지는 않음 — 단순히 `_sec` 메서드가 정상적으로 라벨을 생성하는지만 확인하면 됨.

- [ ] **Step 1: Modify `_sec` method**

Edit `src/lol_coach/gui/app.py:159-163`:

```python
    def _sec(self, parent: Any, title: str, row: int) -> int:
        ctk.CTkLabel(parent, text=f"▸ {title}", font=FS, anchor="w").grid(
            row=row, column=0, sticky="w", padx=10, pady=(14, 4)
        )
        return row + 1
```

with:

```python
    def _sec(self, parent: Any, title: str, row: int) -> int:
        """골드 볼드 섹션 타이틀 + 1px 헤어라인."""
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=0, sticky="ew", padx=10, pady=(14, 4))
        wrap.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            wrap,
            text=title,
            font=FONTS["HEADING"],
            anchor="w",
            text_color=COLORS["ACCENT_GOLD_BRIGHT"],
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkFrame(
            wrap, height=1, fg_color=COLORS["BORDER_GOLD"]
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        return row + 1
```

- [ ] **Step 2: Run existing tests**

Run: `pytest tests/test_gui_threading.py -v`
Expected: All tests PASS. `_sec`은 `test_render_aram_shows_only_offered_and_metadata`에서 `_collect_texts`로 라벨 텍스트를 수집하는데, 화살표 제거 후에는 섹션 제목 자체(예: "1. 제시된 증강 비교")가 그대로 text에 들어가므로 assertion 영향 없음.

- [ ] **Step 3: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): redesign _sec section header — gold bold title + hairline"
```

---

### Task 4: app.py — `_row_frame` 행 카드 + `_lbl` 기본 폰트 토큰 교체

**Goal**: 행 카드 색을 `BG_PANEL_RAISED` + 골드 액센트 바 추가. `_lbl`의 기본 폰트 인자를 `FB` → `FONTS["SMALL"]`로 교체.

**Files:**
- Modify: `src/lol_coach/gui/app.py:133-157` (`_lbl` method)
- Modify: `src/lol_coach/gui/app.py:170-173` (`_row_frame` method)

**Important**: `test_gui_threading.py:160-163`와 `:165`에서 `fg_color=("gray90", "gray22")`를 하드코딩 참조한다. 이 테스트는 `_row_frame`을 자체 override하므로 실제 `CoachApp._row_frame`을 직접 테스트하지는 않음 — 우리가 프로덕션 코드만 교체하면 됨.

- [ ] **Step 1: Modify `_lbl` default font**

Edit `src/lol_coach/gui/app.py:133-157` — `_lbl` 메서드에서 `font=FB` 기본값을 `font=FONTS["SMALL"]`로 교체:

```python
    def _lbl(
        self,
        parent: Any,
        text: str,
        row: int,
        *,
        font=FONTS["SMALL"],
        color=None,
        wrap: int = 960,
        pady: int = 2,
        padx: int = 10,
    ) -> int:
```

(나머지 메서드 본문은 동일)

- [ ] **Step 2: Modify `_row_frame` to use BG_PANEL_RAISED + gold accent bar**

Edit `src/lol_coach/gui/app.py:170-173`:

```python
    def _row_frame(self, parent: Any, row: int, padx: int = 10, pady: int = 2) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=("gray90", "gray22"), corner_radius=8)
        frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        return frame
```

with:

```python
    def _row_frame(self, parent: Any, row: int, padx: int = 10, pady: int = 2) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent,
            fg_color=COLORS["BG_PANEL_RAISED"],
            corner_radius=CORNER["CARD"],
        )
        frame.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        # 좌측 3px 골드 액센트 바
        accent = ctk.CTkFrame(
            frame,
            width=3,
            fg_color=COLORS["ACCENT_GOLD"],
            corner_radius=0,
        )
        accent.pack(side="left", fill="y", padx=(0, 0))
        return frame
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 4: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): redesign row cards — BG_PANEL_RAISED + gold accent bar"
```

---

### Task 5: app.py — `_entry_row` + `_select_role` 토큰 교체

**Goal**: `_entry_row`의 라벨/엔트리 폰트 → `FONTS["BODY"]`. `_select_role`의 역할 버튼 활성/비활성 색 → `ROLE_ACTIVE`/`ROLE_IDLE` 토큰.

**Files:**
- Modify: `src/lol_coach/gui/app.py:175-185` (`_entry_row`)
- Modify: `src/lol_coach/gui/app.py:203-210` (`_select_role`)
- Modify: `src/lol_coach/gui/app.py:234-244` (역할 버튼 생성 시 `fg_color=("gray70","gray30")` → `ROLE_IDLE`)

- [ ] **Step 1: Modify `_entry_row`**

Edit `src/lol_coach/gui/app.py:175-185`:

```python
    def _entry_row(
        self, parent: Any, row: int, label: str, var: tk.StringVar, ph: str = ""
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=FU, width=90, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=5
        )
        entry = ctk.CTkEntry(
            parent, textvariable=var, placeholder_text=ph, font=FU, height=34
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        return entry
```

with:

```python
    def _entry_row(
        self, parent: Any, row: int, label: str, var: tk.StringVar, ph: str = ""
    ) -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent, text=label, font=FONTS["BODY"], width=90, anchor="w"
        ).grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=5
        )
        entry = ctk.CTkEntry(
            parent,
            textvariable=var,
            placeholder_text=ph,
            font=FONTS["BODY"],
            height=34,
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        return entry
```

- [ ] **Step 2: Modify `_select_role`**

Edit `src/lol_coach/gui/app.py:203-210`:

```python
    def _select_role(self, label: str) -> None:
        self.role_var.set(label)
        for b in self._role_btns:
            b.configure(
                fg_color=("#3B8ED0", "#1F6AA5")
                if b.cget("text") == label
                else ("gray70", "gray30")
            )
```

with:

```python
    def _select_role(self, label: str) -> None:
        self.role_var.set(label)
        for b in self._role_btns:
            if b.cget("text") == label:
                b.configure(
                    fg_color=COLORS["ROLE_ACTIVE"],
                    text_color=COLORS["BG_SHELL"],
                    corner_radius=CORNER["PILL"],
                )
            else:
                b.configure(
                    fg_color=COLORS["ROLE_IDLE"],
                    text_color=COLORS["TEXT_PRIMARY"],
                    corner_radius=CORNER["PILL"],
                )
```

- [ ] **Step 3: Modify role button creation in `_build_sr`**

Edit `src/lol_coach/gui/app.py:234-244`:

```python
            b = ctk.CTkButton(
                roles,
                text=lab,
                width=58,
                height=30,
                font=FM,
                fg_color=("gray70", "gray30"),
                command=lambda L=lab: self._select_role(L),
            )
```

with:

```python
            b = ctk.CTkButton(
                roles,
                text=lab,
                width=58,
                height=30,
                font=FONTS["CAPTION"],
                fg_color=COLORS["ROLE_IDLE"],
                text_color=COLORS["TEXT_PRIMARY"],
                corner_radius=CORNER["PILL"],
                command=lambda L=lab: self._select_role(L),
            )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 5: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): role pill buttons + entry_row font tokens"
```

---

### Task 6: app.py — `_build` 헤더 + 탭 토큰 교체, 이모지 제거

**Goal**: 헤더 타이틀 골드 + 헤어라인, 상태 텍스트 muted, 탭 corner_radius → CORNER["CARD"], `🎮`/`📋`/`⚡` 이모지 제거.

**Files:**
- Modify: `src/lol_coach/gui/app.py:76-99` (`_build` shell)
- Modify: `src/lol_coach/gui/app.py:222-224` (빠른 카운터 헤더 — `⚡` 제거)
- Modify: `src/lol_coach/gui/app.py:268-277` (live btn — `🎮` 제거 + BTN_LIVE 토큰)
- Modify: `src/lol_coach/gui/app.py:299-301` (상세 헤더 — `📋` 제거)
- Modify: `src/lol_coach/gui/app.py:423`, `:450`, `:502`, `:525` 등 — `_busy_set` 호출의 idle 텍스트에서 `🎮 ` 접두사 제거

- [ ] **Step 1: Modify `_build` shell (header + tabs)**

Edit `src/lol_coach/gui/app.py:76-99`:

```python
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        ctk.CTkLabel(head, text="롤 실전 코치", font=FT).pack(side="left")
        self.status = ctk.CTkLabel(
            head, text="준비 중…", font=FM, text_color=("gray50", "gray60")
        )
        self.status.pack(side="right")

        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
```

with:

```python
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=SPACE["PAD_X"], pady=(12, 4))
        ctk.CTkLabel(
            head,
            text="롤 실전 코치",
            font=FONTS["TITLE"],
            text_color=COLORS["ACCENT_GOLD_BRIGHT"],
        ).pack(side="left")
        self.status = ctk.CTkLabel(
            head, text="준비 중…", font=FONTS["CAPTION"], text_color=COLORS["TEXT_MUTED"]
        )
        self.status.pack(side="right")
        # 헤더 하단 골드 헤어라인
        ctk.CTkFrame(
            self, height=1, fg_color=COLORS["BORDER_GOLD"]
        ).grid(row=0, column=0, sticky="ew")

        self.tabs = ctk.CTkTabview(self, corner_radius=CORNER["CARD"])
        self.tabs.grid(
            row=1, column=0, sticky="nsew", padx=SPACE["GAP_MD"], pady=(0, SPACE["GAP_MD"])
        )
```

- [ ] **Step 2: Modify 빠른 카운터 헤더 (⚡ 제거)**

Edit `src/lol_coach/gui/app.py:222-224`:

```python
        ctk.CTkLabel(
            quick, text="⚡ 빠른 카운터픽 (픽타임용)", font=FS, anchor="w"
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))
```

with:

```python
        ctk.CTkLabel(
            quick,
            text="빠른 카운터픽 (픽타임용)",
            font=FONTS["HEADING"],
            text_color=COLORS["ACCENT_GOLD_BRIGHT"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))
```

- [ ] **Step 3: Modify live button (🎮 제거 + BTN_LIVE 토큰)**

Edit `src/lol_coach/gui/app.py:268-277`:

```python
        self.sr_live_btn = ctk.CTkButton(
            live_row,
            text="🎮 실행 중인 게임 자동 검색",
            height=32,
            font=FU,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#388E3C", "#2E7D32"),
            command=self._live_fill_sr,
        )
```

with:

```python
        self.sr_live_btn = ctk.CTkButton(
            live_row,
            text="실행 중인 게임 자동 검색",
            height=32,
            font=FONTS["BODY"],
            fg_color=COLORS["BTN_LIVE_BG"],
            hover_color=COLORS["BTN_LIVE_HOVER"],
            command=self._live_fill_sr,
        )
```

- [ ] **Step 4: Modify 상세 분석 헤더 (📋 제거)**

Edit `src/lol_coach/gui/app.py:299-301`:

```python
        ctk.CTkLabel(
            detail, text="📋 상세 분석 (조합·용/바론·상황템)", font=FS, anchor="w"
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 4))
```

with:

```python
        ctk.CTkLabel(
            detail,
            text="상세 분석 (조합·용/바론·상황템)",
            font=FONTS["HEADING"],
            text_color=COLORS["ACCENT_GOLD_BRIGHT"],
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 4))
```

- [ ] **Step 5: Remove `🎮 ` prefix from all _busy_set idle strings**

`grep`으로 `🎮 실행 중인 게임 자동 검색` 모든 인스턴스를 찾아 `실행 중인 게임 자동 검색`으로 교체 (`replaceAll` 사용).

Edit `src/lol_coach/gui/app.py` — `replaceAll` 모드로 `"🎮 실행 중인 게임 자동 검색"` → `"실행 중인 게임 자동 검색"` 실행.

총 6개 인스턴스: `_live_fill_sr`(line ~423, ~450), `_live_fill_aram`(line ~525, ~551, ~568, ~582, ~588), `_run_aram`(line ~?).

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 7: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): remove emojis from headers + apply hextech tokens to shell"
```

---

### Task 7: app.py — `_build_sr` 나머지 색/그레이 토큰 일괄 교체

**Goal**: `("gray45","gray60")`, `("gray50","gray60")`, `("gray60","gray35")` 등 muted/caption 그레이를 `TEXT_MUTED`로, "상세 분석" 버튼 `("gray60","gray35")` → `ACCENT_HEX`.

**Files:**
- Modify: `src/lol_coach/gui/app.py:278-291` (live_row caption, sr_status)
- Modify: `src/lol_coach/gui/app.py:335-349` (detail_btn + caption)
- Modify: `src/lol_coach/gui/app.py:351-364` (sr_out label_text 제거 + 초기 플레이스홀더 색)

- [ ] **Step 1: Replace all gray tuples for muted/caption text**

Edit `src/lol_coach/gui/app.py` — `replaceAll` for each:

- `("gray45", "gray60")` → `COLORS["TEXT_MUTED"]`
- `("gray50", "gray60")` → `COLORS["TEXT_MUTED"]`
- `("gray50", "gray55")` → `COLORS["TEXT_MUTED"]` (ARAM 메타 라인)

주의: gray 튜플이 `fg_color=`로 쓰이는 경우도 있는지 확인. `text_color=`로 쓰이는 곳만 교체.

- [ ] **Step 2: Modify detail_btn fg_color**

Edit `src/lol_coach/gui/app.py:335-342`:

```python
        self.sr_detail_btn = ctk.CTkButton(
            btn_row,
            text="상세 분석",
            height=36,
            font=FU,
            fg_color=("gray60", "gray35"),
            command=self._run_sr_detail,
        )
```

with:

```python
        self.sr_detail_btn = ctk.CTkButton(
            btn_row,
            text="상세 분석",
            height=36,
            font=FONTS["BODY"],
            fg_color=COLORS["ACCENT_HEX_DEEP"],
            hover_color=COLORS["ACCENT_HEX"],
            command=self._run_sr_detail,
        )
```

- [ ] **Step 3: Remove sr_out label_text**

Edit `src/lol_coach/gui/app.py:351-353`:

```python
        self.sr_out = ctk.CTkScrollableFrame(
            self.t_sr, corner_radius=10, label_text="결과"
        )
```

with:

```python
        self.sr_out = ctk.CTkScrollableFrame(
            self.t_sr, corner_radius=CORNER["CARD"]
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 5: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): replace hardcoded gray tuples with TEXT_MUTED + detail_btn ACCENT_HEX"
```

---

### Task 8: app.py — `_render_sr_quick`/`_render_sr_detail`/`_sr_err` 결과 색 토큰 교체

**Goal**: `#81C784` → `ACCENT_GOOD`, `#FFB74D` → `ACCENT_WARN`, `#E57373` → `ACCENT_DANGER`, `#A064DC` 등 증강 카드 색은 유지 (증강 등급 플래그 색이라 Hextech 밖 — 아웃오브스콥 확인 후 별도 논의). 우선 우세/무난/오류 색만 교체.

**Files:**
- Modify: `src/lol_coach/gui/app.py:698-701` (`_sr_err`)
- Modify: `src/lol_coach/gui/app.py:724-725` (`_render_sr_quick` 색)
- Modify: `src/lol_coach/gui/app.py:775-776` (`_render_sr_detail` 색)
- Modify: `src/lol_coach/gui/app.py:1119-1121` (`_render_aram` validation 색)
- Modify: `src/lol_coach/gui/app.py:1152` (`_render_aram` top augment 색)
- Modify: `src/lol_coach/gui/app.py:1182` (`_render_aram` avoid 색)
- Modify: `src/lol_coach/gui/app.py:1074` (`_aram_err` 색)

- [ ] **Step 1: _sr_err color**

Edit `src/lol_coach/gui/app.py:698-701`:

```python
    def _sr_err(self, msg: str) -> None:
        self._clear(self.sr_out)
        self._lbl(self.sr_out, f"오류: {msg}", 0, color="#E57373")
        self.sr_status.configure(text="실패")
```

with:

```python
    def _sr_err(self, msg: str) -> None:
        self._clear(self.sr_out)
        self._lbl(self.sr_out, f"오류: {msg}", 0, color=COLORS["ACCENT_DANGER"])
        self.sr_status.configure(text="실패")
```

- [ ] **Step 2: _aram_err color**

Edit `src/lol_coach/gui/app.py:1074`:

```python
        self._lbl(self.aram_out, f"오류: {msg}", 0, color="#E57373")
```

with:

```python
        self._lbl(self.aram_out, f"오류: {msg}", 0, color=COLORS["ACCENT_DANGER"])
```

- [ ] **Step 3: _render_sr_quick counter colors**

Edit `src/lol_coach/gui/app.py:724-725`:

```python
                col = "#81C784" if c.gd15 >= 200 else "#FFB74D"
                tip = "초반 강함" if c.gd15 >= 300 else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
```

with:

```python
                col = COLORS["ACCENT_GOOD"] if c.gd15 >= 200 else COLORS["ACCENT_WARN"]
                tip = "초반 강함" if c.gd15 >= 300 else ("무난 우위" if c.gd15 >= 100 else "소폭 우위")
```

- [ ] **Step 4: _render_sr_detail counter colors**

Edit `src/lol_coach/gui/app.py:775`:

```python
            col = "#81C784" if c.gd15 >= 200 else "#FFB74D"
```

with:

```python
            col = COLORS["ACCENT_GOOD"] if c.gd15 >= 200 else COLORS["ACCENT_WARN"]
```

- [ ] **Step 5: _render_aram validation note color**

Edit `src/lol_coach/gui/app.py:1119-1121`:

```python
                    r = self._lbl(
                        self.aram_out,
                        " · ".join(notes),
                        r,
                        color="#FFB74D",
                        font=FM,
                    )
```

with:

```python
                    r = self._lbl(
                        self.aram_out,
                        " · ".join(notes),
                        r,
                        color=COLORS["ACCENT_WARN"],
                        font=FONTS["CAPTION"],
                    )
```

- [ ] **Step 6: _render_aram top augment text_color**

Edit `src/lol_coach/gui/app.py:1152`:

```python
                    text_color="#81C784",
```

with:

```python
                    text_color=COLORS["ACCENT_GOOD"],
```

- [ ] **Step 7: _render_aram avoid text_color**

Edit `src/lol_coach/gui/app.py:1182`:

```python
                    text_color="#E57373",
```

with:

```python
                    text_color=COLORS["ACCENT_DANGER"],
```

- [ ] **Step 8: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS. `test_render_aram_shows_only_offered_and_metadata`는 `_collect_texts`로 라벨 text를 수집하고 "보석 건틀릿" 등 증강 이름이 들어있는지만 확인하므로 색 변경 영향 없음.

- [ ] **Step 9: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/app.py`
Expected: No errors.

- [ ] **Step 10: Commit**

```bash
git add src/lol_coach/gui/app.py
git commit -m "style(gui): replace hardcoded status colors with ACCENT_GOOD/WARN/DANGER tokens"
```

---

### Task 9: app.py — `champ_autocomplete.py` 색 토큰 교체

**Goal**: `_FONT` → `FONTS["SMALL"]`, `("gray90","gray20")` → `COLORS["BG_PANEL"]`, `("gray70","gray35")`/`("#3B8ED0","#1F6AA5")` → `COLORS["ACCENT_HEX"]`.

**Files:**
- Modify: `src/lol_coach/gui/champ_autocomplete.py:19`, `:55-57`, `:533`, `:536`, `:537`, `:560`

- [ ] **Step 1: Add theme import + _FONT replacement**

Edit `src/lol_coach/gui/champ_autocomplete.py:15-19`:

```python
import customtkinter as ctk

from lol_coach.static.ddragon import DataDragon

_FONT = ("Malgun Gothic", 12)
```

with:

```python
import customtkinter as ctk

from lol_coach.gui.theme import COLORS, FONTS, CORNER
from lol_coach.static.ddragon import DataDragon

_FONT = FONTS["SMALL"]
```

- [ ] **Step 2: Panel colors**

Edit `src/lol_coach/gui/champ_autocomplete.py:52-58`:

```python
        self._panel = ctk.CTkFrame(
            parent,
            corner_radius=8,
            fg_color=("gray90", "gray20"),
            border_width=1,
            border_color=("gray70", "gray35"),
        )
```

with:

```python
        self._panel = ctk.CTkFrame(
            parent,
            corner_radius=CORNER["CARD"],
            fg_color=COLORS["BG_PANEL"],
            border_width=1,
            border_color=COLORS["BORDER_GOLD"],
        )
```

- [ ] **Step 3: List item colors (match_existing similar pattern)**

Edit `src/lol_coach/gui/champ_autocomplete.py:533-537` & `:560`:

```python
        "hover_color": ("#3B8ED0", "#1F6AA5"),
        "text_color": ("gray10", "gray90"),
```

with:

```python
        "hover_color": COLORS["ACCENT_HEX"],
        "text_color": COLORS["TEXT_PRIMARY"],
```

그리고 `:560`:

```python
            fg_color=("#3B8ED0", "#1F6AA5")
```

with:

```python
            fg_color=COLORS["ACCENT_HEX"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 5: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/champ_autocomplete.py`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add src/lol_coach/gui/champ_autocomplete.py
git commit -m "style(autocomplete): replace hardcoded colors with theme tokens"
```

---

### Task 10: `setup_dialog.py` + `api_help.py` 폰트 토큰 교체

**Goal**: `FT`/`FU`/`FM`/`FS` 상수 → `theme.FONTS` import.

**Files:**
- Modify: `src/lol_coach/gui/setup_dialog.py:22-25` (font constants block)
- Modify: `src/lol_coach/gui/api_help.py` (font usages if any)

- [ ] **Step 1: setup_dialog.py font constants**

Edit `src/lol_coach/gui/setup_dialog.py:9-25`:

```python
import customtkinter as ctk
import tkinter as tk

from lol_coach.config import (
    DEFAULT_PLATFORM,
    load_settings,
    save_api_key,
    save_player,
)
from lol_coach.gui.api_help import RIOT_DEV_URL, open_api_key_help

_API_KEY_RE = re.compile(r"^RGAPI-[0-9a-fA-F-]{8,}$")

FT = ("Malgun Gothic", 16, "bold")
FU = ("Malgun Gothic", 13)
FM = ("Malgun Gothic", 11)
FS = ("Malgun Gothic", 12)
```

with:

```python
import customtkinter as ctk
import tkinter as tk

from lol_coach.config import (
    DEFAULT_PLATFORM,
    load_settings,
    save_api_key,
    save_player,
)
from lol_coach.gui.api_help import RIOT_DEV_URL, open_api_key_help
from lol_coach.gui.theme import FONTS

_API_KEY_RE = re.compile(r"^RGAPI-[0-9a-fA-F-]{8,}$")

# 기존 alias — 새 코드는 FONTS["TITLE"] / FONTS["BODY"] 등을 직접 사용할 것.
FT = FONTS["TITLE"]
FU = FONTS["BODY"]
FM = FONTS["CAPTION"]
FS = FONTS["SMALL"]
```

- [ ] **Step 2: api_help.py — 폰트가 있는지 확인만 하고 있다면 동일 교체**

Run grep: `grep -n "Malgun Gothic\|font=" src/lol_coach/gui/api_help.py`

만약 `api_help.py`에 폰트 정의가 있다면 동일한 패턴으로 교체. 없다면 스킵.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_theme.py tests/test_gui_threading.py -v`
Expected: All PASS.

- [ ] **Step 4: LSP diagnostics**

Run: `lsp_diagnostics` on `src/lol_coach/gui/setup_dialog.py`
Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
git add src/lol_coach/gui/setup_dialog.py
git commit -m "refactor(setup_dialog): use theme.FONTS instead of local font constants"
```

---

### Task 11: 종합 검증 + 시각적 확인

**Goal**: 전체 테스트 통과, LSP 클린, 앱 실행 시각적 확인.

**Files:**
- Test: `tests/test_theme.py`, `tests/test_gui_threading.py`
- Visual: `gui_main.py` 실행

- [ ] **Step 1: Full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS. report any unexpected failures that are NOT related to our change and document them.

- [ ] **Step 2: LSP diagnostics on all changed files**

Run `lsp_diagnostics` on each:
- `src/lol_coach/gui/theme.py`
- `src/lol_coach/gui/app.py`
- `src/lol_coach/gui/setup_dialog.py`
- `src/lol_coach/gui/champ_autocomplete.py`

Expected: No errors. (Pre-existing warnings OK to ignore — only confirm we didn't introduce new errors)

- [ ] **Step 3: Verify theme tokens are actually used**

Run grep against app.py — confirm no remaining hardcoded colors:

```bash
grep -n '"gray[0-9]*"\|"#3B8ED0"\|"#81C784"\|"#FFB74D"\|"#E57373"' src/lol_coach/gui/app.py
```

Expected: Empty output, or only `_augment_missing_card` rarity color dict (lines ~1249-1253) — that dict is 별도 rarity 배지 색이라 spec out-of-scope이므로 유지.

- [ ] **Step 4: Visual verification**

Run: `$env:PYTHONPATH="src"; python gui_main.py`

눈으로 검수:
- 헤더: "롤 실전 코치" 골드 볼드 + 하단 헤어라인
- 탭 바: 어두운 배경, 헥사딕 블루 인디케이터
- 소환사의 협곡 탭:
  - "빠른 카운터픽 (픽타임용)" 골드 볼드 (`⚡` 없음)
  - 역할 버튼 pill 형태 + 활성 헥사딕 블루
  - "실행 중인 게임 자동 검색" (`🎮` 없음) 그린 버튼
  - "상세 분석" (`📋` 없음) 골드 볼드 + 헥사딕 딥 버튼
  - 섹션: 골드 볼드 + 헤어라인 (`▸` 없음)
- ARAM 탭: 동일한 골드/헥사딕 톤
- 내 전적 탭: 동일한 톤

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "verify: all tests green + hextech theme visually confirmed"
```

(이 커밋은 빈 경우 skip — 변경 사항 이미 이전 커밋으로 들어감. 필요시 빈 커밋은 만들지 않음.)

---

## Self-Review

**1. Spec coverage** (스펙 각 섹션 → 태스크 매핑):
- 팔레트 18개 색 토큰 → Task 1 ✅
- 6개 폰트 토큰 → Task 1 ✅
- 8개 SPACE 토큰 → Task 1 ✅
- 3개 CORNER 토큰 → Task 1 ✅
- `assets/hextech.json` (6개 프리미티브) → Task 1 ✅
- 4개 GUI 파일 토큰 치환 → Task 2 (app.py 상수), Task 9 (champ_autocomplete), Task 10 (setup_dialog, api_help) ✅
- `apply_hextech_theme()` 진입점 연결 → Task 2 ✅
- `_sec` 화살표 제거 + 헤어라인 → Task 3 ✅
- 행 카드 BG_PANEL_RAISED + 골드 엑센트 바 → Task 4 ✅
- 역할 버튼 PILL + ROLE_ACTIVE/IDLE → Task 5 ✅
- 헤더 골드 + 헤어라인, 탭 corner → Task 6 ✅
- 이모지 제거 (`⚡📋🎮`) → Task 6 ✅
- gray 튜플 → TEXT_MUTED, detail_btn ACCENT_HEX → Task 7 ✅
- 결과 색 토큰 (GOOD/WARN/DANGER) → Task 8 ✅
- 테스트 (`test_theme.py` + 기존 통과 유지) → Task 1, 각 Task마다 ✅
- 정지 조건 (완료 기준) → Task 11 ✅

**2. Placeholder scan**: TODO/TBD 없음. 모든 코드 블록은 실제 값 포함. ✅

**3. Type consistency**:
- `COLORS` → `dict[str, tuple[str, str]]` (Task 1 정의, 모든 후속 Task 동일 참조) ✅
- `FONTS` → `dict[str, tuple[str, int] | tuple[str, int, str]]` ✅
- `apply_hextech_theme()` → `() -> None` (Task 1 정의, Task 2 호출) ✅
- 기존 `FT`/`FU`/`FB`/`FM`/`FS` alias (`("Malgun Gothic", int, ...)`) → Task 2/10에서 `FONTS["KEY"]` 값으로 재정의, 타입 일치 ✅