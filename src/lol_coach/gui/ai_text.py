"""AI 코칭 텍스트 정규화 헬퍼 (GUI 렌더용).

app.py 에서 분리해 단위 테스트·재사용이 쉽게 한다.
"""

from __future__ import annotations

import re


def ai_lines(text: str) -> list[str]:
    """모델 출력을 읽기 쉬운 비어 있지 않은 줄 목록으로 정규화."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]\s*|\d+[.)]\s*)", "", raw)
        line = re.sub(r"[#*_`]", "", line).strip()
        if len(line) >= 4 and line not in lines:
            lines.append(line)
    return lines


def ai_key_points(text: str, *, limit: int = 4) -> list[str]:
    """핵심 요약용 — 우선순위 키워드 기반 상위 줄 선택 (모델 순서 유지)."""
    lines = ai_lines(text)
    high_priority = ("핵심", "주의", "우선", "결론", "금지", "먼저")
    medium_priority = ("추천", "아이템", "증강", "한타", "오브젝트", "진입")

    def priority(line: str) -> tuple[int, int]:
        index = lines.index(line)
        if any(token in line for token in high_priority):
            return 0, index
        if any(token in line for token in medium_priority):
            return 1, index
        return 2, index

    selected = sorted(lines, key=priority)[: max(1, limit)]
    return [line for line in lines if line in selected]


_REPEAT_TOKEN_RE = re.compile(r"(\S+)( \1){3,}")


def sanitize_summary_lines(
    lines: list[str],
    *,
    max_line: int = 240,
    max_lines: int = 80,
) -> list[str]:
    """위젯 요약 방어 — LLM 반복 루프(prowess prowess…) 접기 + 길이 제한."""
    out: list[str] = []
    for line in lines or []:
        line = _REPEAT_TOKEN_RE.sub(lambda m: m.group(1) + " …", line)
        if len(line) > max_line:
            line = line[: max_line - 1] + "…"
        out.append(line)
        if len(out) >= max_lines:
            out.append("(이하 생략)")
            break
    return out
