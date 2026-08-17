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

FT = ("Malgun Gothic", 20, "bold")
FS = ("Malgun Gothic", 15, "bold")
FU = ("Malgun Gothic", 13)
FB = ("Malgun Gothic", 12)
FM = ("Malgun Gothic", 11)
FCH = ("Malgun Gothic", 10, "bold")
# AI 상세 코칭 = 최대 가독성
AI_TITLE = ("Malgun Gothic", 14, "bold")
AI_SECTION = ("Malgun Gothic", 12, "bold")
AI_SUMMARY = ("Malgun Gothic", 11)
AI_BODY = ("Malgun Gothic", 13)


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
