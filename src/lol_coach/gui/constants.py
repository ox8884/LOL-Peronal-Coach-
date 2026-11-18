"""GUI 공통 상수·토큰 (탭 믹스인·app 공유)."""

from __future__ import annotations

ROLES = [
    ("탑", "top"),
    ("정글", "jungle"),
    ("미드", "mid"),
    ("원딜", "adc"),
    ("서폿", "support"),
]

# 자주 쓰는 서버 우선 배치 (드롭다운)
PLATFORMS = ["kr", "na1", "euw1", "eun1", "jp1", "br1", "oc1", "tr1", "ru", "la1", "la2"]

# AI 코칭 모델 선택지 (opencode-go 게이트웨이 동작 확인 목록)
AI_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "kimi-k3",
    "glm-5",
    "qwen3.7-plus",
    "mimo-v2.5",
]

# UI 배율 (tk scaling 배수)
FONT_SCALE_CHOICES = ["0.9", "1.0", "1.1", "1.2", "1.3"]
DEFAULT_FONT_SCALE = 1.0

# ── 글꼴 ───────────────────────────────────────────────────────────
# FONT_UI     : 한글 본문 (Windows 기본 제공, 작은 크기에서 가장 또렷함)
# FONT_HEAD   : 제목 — Black Han Sans (gui/fonts 에 동봉, OFL). 등록 실패 시 FONT_UI 굵게
# FONT_DISPLAY: 숫자 — 좁은 DIN 계열 (Win10+ 기본)
# FONT_ICON   : 세그오 아이콘 폰트 — 실제 가용 폰트는 gui.icons.icon_font() 로 확인
FONT_UI = "맑은 고딕"
FONT_HEAD = "Black Han Sans"
FONT_DISPLAY = "Bahnschrift SemiBold Condensed"
FONT_ICON = "Segoe Fluent Icons"
FONT_ICON_FALLBACK = "Segoe MDL2 Assets"


def _register_fonts() -> bool:
    """동봉 글꼴을 이 프로세스에만 등록한다 (PC에 설치하지 않음)."""
    try:
        import ctypes
        from pathlib import Path

        path = Path(__file__).resolve().parent / "fonts" / "BlackHanSans-Regular.ttf"
        return path.is_file() and ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0) > 0
    except Exception:
        return False


_HEAD_OK = _register_fonts()


def FH(size: int) -> tuple:
    """제목 글꼴 — 가운뎃점(·)은 글리프가 없으니 제목 문구에 쓰지 않는다."""
    return (FONT_HEAD, size) if _HEAD_OK else (FONT_UI, size, "bold")


FT = FH(24)
FS = FH(19)
FU = (FONT_UI, 14)
FB = (FONT_UI, 13)
FM = (FONT_UI, 12)
FCH = (FONT_UI, 11, "bold")
FL = (FONT_UI, 15, "bold")  # 본문 안의 강조 줄 (제목 글꼴 아님)
# AI 상세 코칭 = 최대 가독성
AI_TITLE = (FONT_UI, 15, "bold")
AI_SECTION = (FONT_UI, 13, "bold")
AI_SUMMARY = (FONT_UI, 12)
AI_BODY = (FONT_UI, 14)


def FNUM(size: int, bold: bool = True) -> tuple:
    """숫자·영문 지표(KPI·승률·킬차·타이머)용 디스플레이 폰트."""
    return (FONT_DISPLAY, size, "bold" if bold else "normal")


def counter_tier(gd15: int) -> str:
    """GD@15 값 → 카운터 등급 배지(S/A/B/C)."""
    if gd15 >= 300:
        return "S"
    if gd15 >= 200:
        return "A"
    if gd15 >= 100:
        return "B"
    return "C"


def apply_tk_ui_scale(root, scale: float, *, base: float | None = None) -> float:
    """Tk 전체 UI 스케일 적용. 반환: 사용한 base scaling.

    ``scale`` 은 사용자 배율(0.9~1.2). ``base`` 는 최초 tk 기본값.
    """
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        scale = DEFAULT_FONT_SCALE
    scale = max(0.85, min(1.35, scale))
    try:
        if base is None:
            base = float(root.tk.call("tk", "scaling"))
            # 이미 배율이 곱해진 상태면 base 추정 불가 — 속성 사용
            stored = getattr(root, "_ui_scale_base", None)
            if stored is not None:
                base = float(stored)
            else:
                # 현재 = base * prev_scale 가정 어려움 → 현재를 base로 저장 1회
                pass
        root._ui_scale_base = float(base)
        root.tk.call("tk", "scaling", float(base) * scale)
    except Exception:
        pass
    return float(base) if base is not None else 1.0
