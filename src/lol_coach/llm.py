"""선택형 AI 코칭 — opencode-go 게이트웨이(OpenAI 호환)로 한국어 코칭 생성.

키 우선순위: 명시 입력 > 환경변수/`.env`의 `LOL_COACH_LLM_KEY` > opencode
CLI 인증 파일(`~/.local/share/opencode/auth.json`) 자동 감지.
키가 없거나 호출이 실패하면 규칙 기반 결과만 쓰도록 None 을 돌려준다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4-flash"

_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

_SYSTEM = (
    "너는 리그 오브 레전드 실전 코치다. 사용자에게 한국어로, 30초 안에 읽을 수 "
    "있게 구체적인 인게임 조언을 준다. 일반론('시야를 챙기세요' 같은 문장)만 "
    "나열하지 말고 주어진 매치업/조합/전적 정보에 근거해 구체적으로 조언한다. "
    "확실하지 않은 내용은 '~일 수 있다'로 표현하고, 주어지지 않은 정보는 지어내지 "
    "않는다. 마크다운 헤더나 이모지 없이 각 줄을 '- ' 로 시작해 출력한다."
)


def detect_opencode_key(auth_path: Path | None = None) -> str:
    """opencode CLI 인증 파일에서 opencode-go 키를 찾아 반환 (없으면 빈 문자열)."""
    path = auth_path or _OPENCODE_AUTH
    try:
        if not path.is_file():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = data.get("opencode-go") or {}
        key = str(entry.get("key") or "")
        return key.strip()
    except Exception:
        return ""


def resolve_api_key(explicit: str = "") -> str:
    """사용 가능한 LLM 키 결정 — 명시 입력 > env/.env > opencode 자동 감지."""
    key = explicit.strip()
    if key:
        return key
    key = os.getenv("LOL_COACH_LLM_KEY", "").strip()
    if key:
        return key
    return detect_opencode_key()


def chat(
    prompt: str,
    *,
    system: str = _SYSTEM,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 500,
    timeout_s: float = 45.0,
    api_key: str | None = None,
    base_url: str = BASE_URL,
) -> str | None:
    """OpenAI 호환 chat completion — 실패/타임아웃 시 None."""
    key = api_key if api_key is not None else resolve_api_key()
    if not key:
        return None
    try:
        import requests

        for attempt in range(2):
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "reasoning_effort": "low",
                    "temperature": 0.7,
                },
                timeout=timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
            msg = ((data.get("choices") or [{}])[0].get("message") or {})
            text = str(msg.get("content") or "").strip()
            if text:
                return text
            # 추론 모델이 reasoning_content 에 토큰을 다 쓴 경우 한 번 더 시도
            finish = (data.get("choices") or [{}])[0].get("finish_reason")
            if finish == "length" and attempt == 0:
                max_tokens = max(max_tokens * 2, 400)
                continue
            return None
        return None
    except Exception:
        return None


def _counter_lines(counters: list) -> list[str]:
    lines: list[str] = []
    for _ko, c in counters[:5]:
        wr = getattr(c, "win_rate", None)
        wr_txt = f", 승률 {wr:.1f}%" if wr else ""
        lines.append(f"- {c.champion}: GD@15 {c.gd15_str} ({c.matches:,}게임{wr_txt})")
    return lines


def coach_lane(
    enemy_ko: str,
    role_ko: str,
    counters: list,
    patch: str,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> str | None:
    """빠른 추천용 — 상대 라이너 카운터 기반 30초 라인전 팁."""
    counter_txt = "\n".join(_counter_lines(counters)) or "- 데이터 없음"
    prompt = (
        f"매치업: 내 포지션 {role_ko} vs 상대 {enemy_ko} (패치 {patch})\n"
        f"u.gg 카운터 데이터 (15분 골드 차 기준):\n{counter_txt}\n\n"
        f"{enemy_ko} 상대 라인전에서 픽타임 30초 동안 읽을 팁을 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, max_tokens=2000)


def coach_comp(
    my_ko: str,
    role_ko: str,
    enemy_team: list,
    counters: list,
    threats: list,
    midgame: list,
    situ: list,
    patch: str,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> str | None:
    """상세 분석용 — 조합/오브젝트/상황템 기반 운영 코칭."""
    team_txt = ", ".join(f"{r} {n}" for r, n in enemy_team) or "적 조합 미입력"
    counter_txt = "\n".join(_counter_lines(counters)) or "- 데이터 없음"
    rules_txt = "\n".join(f"- {t}" for t in [*threats[:3], *midgame[:2]]) or "-"
    situ_txt = ", ".join(f"{i} ({w})" for i, w in situ[:4]) or "없음"
    prompt = (
        f"내 픽: {my_ko} ({role_ko})  ·  패치 {patch}\n"
        f"적 조합: {team_txt}\n"
        f"카운터 데이터:\n{counter_txt}\n"
        f"조합 분석 요약:\n{rules_txt}\n"
        f"상황템 후보: {situ_txt}\n\n"
        "이 조합에서 라인전 이후 운영(오브젝트·한타·사이드) 코칭을 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, max_tokens=2000)


def coach_review(
    match,
    rev,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> str | None:
    """경기 복기용 — 한 판 요약 + 규칙 판정 기반 승패 코칭."""
    mark = "승리" if match.win else "패배"
    reasons = " · ".join(rev.win_loss_reasons[:3]) or "없음"
    good = " · ".join(rev.good[:2]) or "없음"
    improve = " · ".join(rev.improve[:2]) or "없음"
    prompt = (
        f"한 판 결과: {mark}  ·  챔피언 {match.champion_name}\n"
        f"KDA {match.kda_str} (비율 {match.kda_ratio})  ·  CS {match.cs}  ·  "
        f"딜 {match.damage_to_champs:,}\n"
        f"킬관여 {match.kill_participation}  ·  데스 {match.deaths}  ·  "
        f"경기 시간 {match.duration_min}분\n"
        f"규칙 기반 판정 — 주요 원인: {reasons}\n"
        f"잘한 점: {good}  ·  개선점: {improve}\n\n"
        "이 판의 진짜 승패 요인과 다음 판에 바로 쓸 행동 1~2가지를 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, max_tokens=2000)
