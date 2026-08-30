"""모노크롬 UI 아이콘 — Segoe Fluent Icons / MDL2 글리프.

이모지 대신 단색 글리프를 써서 스킨 색과 자동으로 조화를 이룬다.
아이콘 폰트가 없는 환경(Win 구버전·비 Windows)에서는 한글 텍스트로
폴백해 기능이 사라지지 않게 한다.
"""

from __future__ import annotations

from typing import Any

from lol_coach.gui.constants import FONT_ICON, FONT_ICON_FALLBACK

# Segoe Fluent Icons / Segoe MDL2 Assets 공용 코드포인트
GLYPHS: dict[str, str] = {
    "settings": "\ue713",
    "refresh": "\ue72c",
    "copy": "\ue8c8",
    "pin": "\ue718",
    "pinned": "\ue840",
    "history": "\ue81c",
    "game": "\ue7fc",
    "lightning": "\ue945",
    "stats": "\ue9d9",
    "people": "\ue716",
    "check": "\ue73e",
    "chevron_right": "\ue76c",
    "chevron_down": "\ue70d",
    "info": "\ue946",
    "warning": "\ue7ba",
    "error": "\ue783",
    "close": "\ue711",
    "add": "\ue710",
    "remove": "\ue738",
    "trophy": "\ue734",
    "globe": "\ue774",
    "download": "\ue896",
    "eye": "\ue7b3",
}

# 아이콘 폰트 미탑재 환경용 텍스트 폴백
FALLBACK_TEXT: dict[str, str] = {
    "settings": "설정",
    "refresh": "업데이트",
    "copy": "복사",
    "pin": "위젯",
}

_font_family: str | None = None


def icon_font(root: Any = None) -> str | None:
    """가용 아이콘 폰트 패밀리 (없으면 None). 결과는 캐시."""
    global _font_family
    if _font_family is None:
        try:
            import tkinter as tk

            if root is not None:
                r = root
            else:
                default_root = getattr(tk, "_get_default_root", None)
                r = default_root() if callable(default_root) else None
            if r is None:
                _font_family = ""
                return _font_family
            fams = set(r.tk.call("font", "families"))
            _font_family = next(
                (f for f in (FONT_ICON, FONT_ICON_FALLBACK) if f in fams),
                "",
            )
        except Exception:
            _font_family = ""
    return _font_family or None


def glyph(name: str) -> str:
    """아이콘 이름 → 글리프 문자 (미지원 환경이면 '')."""
    if icon_font() is None:
        return FALLBACK_TEXT.get(name, "")
    return GLYPHS.get(name, "")


def icon_font_tuple(size: int = 14) -> tuple | None:
    fam = icon_font()
    if not fam:
        return None
    return (fam, size)
