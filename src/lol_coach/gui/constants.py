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
]

FT = ("Malgun Gothic", 20, "bold")
FS = ("Malgun Gothic", 15, "bold")
FU = ("Malgun Gothic", 13)
FB = ("Malgun Gothic", 12)
FM = ("Malgun Gothic", 11)
FCH = ("Malgun Gothic", 10, "bold")
AI_TITLE = ("Malgun Gothic", 18, "bold")
AI_SECTION = ("Malgun Gothic", 14, "bold")
AI_SUMMARY = ("Malgun Gothic", 15, "bold")
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
