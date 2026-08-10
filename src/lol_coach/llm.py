"""선택형 AI 코칭 — opencode-go 게이트웨이(OpenAI 호환)로 한국어 코칭 생성.

키 우선순위: 명시 입력 > 환경변수/`.env`의 `LOL_COACH_LLM_KEY` > opencode
CLI 인증 파일 자동 감지 (Windows/Linux/macOS 후보 경로).
키가 없거나 호출이 실패하면 규칙 기반 결과만 쓰도록 None 을 돌려준다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4-flash"

# chat() 기본값 — GUI AI 카드 타임아웃과 맞출 때 참고
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_MAX_ATTEMPTS = 3

# 게이트웨이 응답 크기 상한 (비정상 응답으로 인한 메모리 낭비 방지)
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

# 테스트에서 monkeypatch 하는 기본 경로 (후보 목록의 첫 항목으로도 사용)
_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"


def _opencode_auth_candidates() -> list[Path]:
    """플랫폼별 opencode auth.json 후보."""
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA") or ""
    roaming = os.environ.get("APPDATA") or ""
    xdg = os.environ.get("XDG_DATA_HOME") or ""
    raw = [
        _OPENCODE_AUTH,
        home / ".local" / "share" / "opencode" / "auth.json",
        home / ".config" / "opencode" / "auth.json",
    ]
    if xdg:
        raw.append(Path(xdg) / "opencode" / "auth.json")
    if local:
        raw.append(Path(local) / "opencode" / "auth.json")
        raw.append(Path(local) / "opencode" / "data" / "auth.json")
    if roaming:
        raw.append(Path(roaming) / "opencode" / "auth.json")
    seen: set[str] = set()
    out: list[Path] = []
    for p in raw:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


_SYSTEM = (
    "너는 리그 오브 레전드 실전 코치다. 사용자에게 한국어로, 30초 안에 읽을 수 "
    "있게 구체적인 인게임 조언을 준다. 일반론('시야를 챙기세요' 같은 문장)만 "
    "나열하지 말고 주어진 매치업/조합/전적 정보에 근거해 구체적으로 조언한다. "
    "메시지에 명시된 '현재 롤 패치'를 반드시 기준으로 삼고, 훈련 시점 이후 "
    "패치에서 바뀐 스킬·아이템·룬 수치를 단정하지 않는다. 이전 시즌 메타를 "
    "현재 패치에 그대로 적용하지 않는다. 확실하지 않은 내용은 '~일 수 있다'로 "
    "표현하고, 주어지지 않은 정보는 지어내지 않는다. 마크다운 헤더나 이모지 "
    "없이 각 줄을 '- ' 로 시작해 출력한다."
)


def _context_block(patch: str) -> str:
    """패치/날짜 앵커 — LLM 훈련 데이터보다 최신 패치 기준을 강제."""
    from datetime import date

    lines = [f"오늘 날짜: {date.today().isoformat()}"]
    if patch:
        lines.append(f"현재 롤 패치: {patch} — 반드시 이 패치 기준으로만 코칭")
    lines.append("확실하지 않은 수치(쿨다운·데미지·아이템 스탯)는 추측해 말하지 않기")
    return "\n".join(lines) + "\n"


def detect_opencode_key(auth_path: Path | None = None) -> str:
    """opencode CLI 인증 파일에서 opencode-go 키를 찾아 반환 (없으면 빈 문자열)."""
    paths = [auth_path] if auth_path is not None else _opencode_auth_candidates()
    for path in paths:
        if path is None:
            continue
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = data.get("opencode-go") or {}
            key = str(entry.get("key") or "").strip()
            if key:
                return key
        except Exception:
            continue
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
    timeout_s: float = DEFAULT_TIMEOUT_S,
    api_key: str | None = None,
    base_url: str = BASE_URL,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> str | None:
    """OpenAI 호환 chat completion — 실패/타임아웃 시 None."""
    key = api_key if api_key is not None else resolve_api_key()
    if not key:
        return None
    attempts = max(1, int(max_attempts))
    try:
        import time

        import requests

        for attempt in range(attempts):
            resp = None
            try:
                try:
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
                        stream=True,
                    )
                except Exception:
                    if attempt < attempts - 1:
                        time.sleep(0.8 + attempt)
                        continue
                    return None
                # 게이트웨이 5xx(일시 라우터 오류)·429(요청 한도)는 잠시 후 재시도
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < attempts - 1:
                        time.sleep(0.8 + attempt)
                        continue
                    return None
                try:
                    resp.raise_for_status()
                    headers = getattr(resp, "headers", {}) or {}
                    try:
                        length = int(headers.get("Content-Length") or 0)
                    except (TypeError, ValueError):
                        length = 0
                    if length > _MAX_RESPONSE_BYTES:
                        return None

                    iterator = getattr(resp, "iter_content", None)
                    if callable(iterator):
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in iterator(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            raw = chunk.encode() if isinstance(chunk, str) else bytes(chunk)
                            total += len(raw)
                            if total > _MAX_RESPONSE_BYTES:
                                return None
                            chunks.append(raw)
                        data = json.loads(b"".join(chunks))
                    else:
                        content = getattr(resp, "content", b"") or b""
                        if len(content) > _MAX_RESPONSE_BYTES:
                            return None
                        data = resp.json()
                except Exception:
                    return None
                msg = ((data.get("choices") or [{}])[0].get("message") or {})
                text = str(msg.get("content") or "").strip()
                if text:
                    return text
                # 추론 모델이 reasoning_content 에 토큰을 다 쓴 경우 한 번 더 시도
                finish = (data.get("choices") or [{}])[0].get("finish_reason")
                if finish == "length" and attempt < attempts - 1:
                    max_tokens = min(max_tokens * 2, 4000)
                    continue
                return None
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    close()
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
        f"{_context_block(patch)}"
        f"매치업: 내 포지션 {role_ko} vs 상대 {enemy_ko} (패치 {patch})\n"
        f"blitz.gg 카운터 데이터 (15분 골드 차 기준):\n{counter_txt}\n\n"
        f"{enemy_ko} 상대 라인전에서 픽타임 30초 동안 읽을 팁을 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, max_tokens=2000)


def _format_core_path(core_items: list[str] | None) -> str:
    """1~5코어 슬롯을 번호 붙여 한 줄로 표시."""
    items = [str(x).strip() for x in (core_items or []) if str(x).strip()]
    if not items:
        return "데이터 없음"
    return " → ".join(f"{i}코어 {name}" for i, name in enumerate(items[:5], 1))


def _format_core_lines(core_items: list[str] | None) -> str:
    """1~5코어를 줄바꿈 목록으로 (AI가 그대로 확장하기 쉽게)."""
    items = [str(x).strip() for x in (core_items or []) if str(x).strip()]
    if not items:
        return "- (메타 데이터 없음 — 챔프 표준 1~5코어를 채워 줘)"
    lines = [f"- {i}코어: {name}" for i, name in enumerate(items[:5], 1)]
    # 슬롯이 부족하면 명시적으로 채우라고 표시
    for i in range(len(items) + 1, 6):
        lines.append(f"- {i}코어: (상황·후반 옵션에서 채워 줘)")
    return "\n".join(lines)


# 한 줄에 여러 코어가 몰린 경우 분리용
_PACKED_CORE_RE = re.compile(
    r"(\d)\s*코어\s*[:：]?\s*",
    re.UNICODE,
)
_SINGLE_CORE_LINE_RE = re.compile(
    r"^\s*(?:[-*•]\s*|\d+[.)]\s*)?(\d)\s*코어\s*[:：]?\s*(.+?)\s*$",
    re.UNICODE,
)
_PLACEHOLDER_RE = re.compile(
    r"^(?:\.{1,3}|…|\(.*?\)|없음|미정|상황|후반|옵션|데이터)",
    re.UNICODE,
)


def _clean_item_name(name: str) -> str:
    s = re.sub(r"[#*_`]", "", str(name or "")).strip()
    s = re.sub(r"\s+", " ", s)
    # 줄 끝 잡음
    s = s.strip(" ·|,/;")  # noqa: B005 — 문자 집합 trim 의도
    return s


def _is_real_core_name(name: str) -> bool:
    n = _clean_item_name(name)
    return len(n) >= 2 and not _PLACEHOLDER_RE.match(n)


def parse_core_items_from_build(build_txt: str | None) -> list[str]:
    """'1코어 A → 2코어 B' / 'A → B → C' 형태의 빌드 문자열에서 아이템 목록 추출."""
    text = str(build_txt or "").strip()
    if not text:
        return []
    # N코어 표기가 있으면 슬롯 순으로
    slots: dict[int, str] = {}
    for m in re.finditer(
        r"(\d)\s*코어\s*[:：]?\s*([^→\n|·]+)",
        text,
        re.UNICODE,
    ):
        idx = int(m.group(1))
        name = _clean_item_name(m.group(2))
        if 1 <= idx <= 5 and _is_real_core_name(name):
            slots[idx] = name
    if slots:
        return [slots[i] for i in range(1, 6) if i in slots]
    # 화살표/중점 나열
    parts = re.split(r"\s*(?:→|->|›|»|·|/)\s*", text)
    out: list[str] = []
    for p in parts:
        p = _clean_item_name(re.sub(r"^\d+\s*코어\s*[:：]?\s*", "", p))
        # 스펠 등 잡음 스킵
        if not _is_real_core_name(p):
            continue
        if "스펠" in p or p.startswith("패치"):
            continue
        out.append(p)
        if len(out) >= 5:
            break
    return out


def _split_packed_core_lines(text: str) -> str:
    """한 줄에 1코어…2코어…가 몰린 경우 여러 줄로 분리."""
    out_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        matches = list(_PACKED_CORE_RE.finditer(line))
        if len(matches) < 2:
            out_lines.append(line)
            continue
        # 각 매치 구간 잘라 개별 줄
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            name = _clean_item_name(line[start:end])
            n = m.group(1)
            if name:
                out_lines.append(f"- {n}코어: {name}")
            else:
                out_lines.append(f"- {n}코어:")
    return "\n".join(out_lines)


def _extract_core_slots(text: str) -> dict[int, str]:
    """응답 텍스트에서 {슬롯: 아이템명} 추출 (1~5)."""
    slots: dict[int, str] = {}
    for raw in text.splitlines():
        m = _SINGLE_CORE_LINE_RE.match(raw.strip())
        if not m:
            # 인라인: 1코어 리안드리 (줄에 다른 내용 없을 때 대략)
            for im in re.finditer(
                r"(\d)\s*코어\s*[:：]?\s*([^\d\n→]{2,40})",
                raw,
                re.UNICODE,
            ):
                idx = int(im.group(1))
                name = _clean_item_name(im.group(2))
                if 1 <= idx <= 5 and _is_real_core_name(name) and idx not in slots:
                    slots[idx] = name
            continue
        idx = int(m.group(1))
        name = _clean_item_name(m.group(2))
        if 1 <= idx <= 5 and _is_real_core_name(name):
            slots[idx] = name
    return slots


def enrich_item_tree_response(
    text: str | None,
    meta_items: list[str] | None,
    *,
    min_cores: int = 3,
    max_cores: int = 5,
) -> str | None:
    """AI 응답 아이템 트리 후처리.

    - 한 줄에 몰린 1~N코어를 줄 분리
    - 실명 코어가 min_cores 미만이면 메타 슬롯으로 빈 칸 보충 (AI 문구는 유지)
    """
    if text is None:
        return None
    if not str(text).strip():
        return text

    body = _split_packed_core_lines(str(text))
    meta = [_clean_item_name(x) for x in (meta_items or []) if _is_real_core_name(str(x))]
    meta = meta[:max_cores]
    slots = _extract_core_slots(body)
    real_n = len(slots)

    if real_n >= min_cores or not meta:
        return body

    # 부족한 슬롯만 메타로 채움 (이미 AI가 쓴 슬롯은 덮지 않음)
    filled: list[str] = []
    target = min(max_cores, max(min_cores, len(meta)))
    for i in range(1, target + 1):
        if i in slots:
            continue
        if i - 1 < len(meta):
            # 메타 아이템이 이미 다른 슬롯에 있으면 스킵
            name = meta[i - 1]
            if name in slots.values():
                # 다음 미사용 메타 탐색
                used = set(slots.values()) | set(filled)
                alt = next((m for m in meta if m not in used), None)
                if not alt:
                    continue
                name = alt
            filled.append(f"- {i}코어: {name}")
            slots[i] = name

    if not filled:
        return body

    note = "- (메타 빌드로 아이템 트리 보충 — 모델이 짧게 답했을 때)"
    return body.rstrip() + "\n" + note + "\n" + "\n".join(filled)


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
    core_items: list | None = None,
    boots: list | None = None,
) -> str | None:
    """상세 분석용 — 조합/오브젝트/풀 아이템 트리 기반 운영 코칭."""
    team_txt = ", ".join(f"{r} {n}" for r, n in enemy_team) or "적 조합 미입력"
    counter_txt = "\n".join(_counter_lines(counters)) or "- 데이터 없음"
    rules_txt = "\n".join(f"- {t}" for t in [*threats[:4], *midgame[:3]]) or "-"
    core_path = _format_core_path(list(core_items or []))
    core_lines = _format_core_lines(list(core_items or []))
    boots_txt = ", ".join(str(b) for b in (boots or [])[:2]) or "메타 신발"
    situ_txt = ", ".join(f"{i} ({w})" for i, w in (situ or [])[:6]) or "없음"
    full = len(enemy_team) >= 5
    scope = "전체 조합(5명)" if full else "입력된 조합(부분 정보)"
    prompt = (
        f"{_context_block(patch)}"
        f"내 픽: {my_ko} ({role_ko})  ·  패치 {patch}\n"
        f"적 조합({scope}): {team_txt}\n"
        f"카운터 데이터:\n{counter_txt}\n"
        f"조합 분석 요약:\n{rules_txt}\n"
        f"메타 코어 요약: {core_path}\n"
        f"메타 코어 슬롯(1~5):\n{core_lines}\n"
        f"신발: {boots_txt}\n"
        f"상황·후반 옵션(상대 조합 대응): {situ_txt}\n\n"
        "아래를 각각 '- ' 줄로 알려줘. 아이템 이름은 한글로.\n"
        "1) 라인전 이후 운영(오브젝트·한타·사이드) 2~3줄\n"
        "2) 아이템 트리 — 반드시 아래 5줄을 각각 따로 써 (한 줄에 몰아쓰지 마):\n"
        "   - 1코어: (아이템)\n"
        "   - 2코어: (아이템)\n"
        "   - 3코어: (아이템)  ← 보통 여기까지는 거의 완성됨\n"
        "   - 4코어: (아이템 또는 상황 방어/관통 옵션)\n"
        "   - 5코어: (아이템 또는 후반 완성 옵션)\n"
        "   메타 슬롯과 상황 옵션을 합쳐 채워. 1~2코어만 쓰고 끝내지 마.\n"
        "   게임이 20분 넘으면 3코어, 길어지면 4~5코어까지 간다고 가정해.\n"
        "3) 언제 상황템으로 분기할지 (상대 조합 기준 1~2줄)"
    )
    if full:
        prompt += (
            "\n전체 조합이 입력됐으니 상대 5명 구성에 맞는 상대법"
            "(한타 구도·진입/보호 대상·오브젝트 운영)을 우선 알려줘."
        )
    out = chat(prompt, api_key=api_key, model=model, max_tokens=3000)
    return enrich_item_tree_response(out, list(core_items or []))


def coach_aram(
    my_champ_ko: str,
    ally_comp: list,
    enemy_comp: list,
    augments_txt: str,
    build_txt: str,
    patch: str,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> str | None:
    """ARAM 아수라장용 — 양 팀 조합 기반 플레이/증강/템트리 코칭."""
    ally = ", ".join(ally_comp) or "정보 없음 (챔피언 기준)"
    enemy = ", ".join(enemy_comp) or "정보 없음 (챔피언 기준)"
    augs = augments_txt or "정보 없음"
    build = build_txt or "정보 없음"
    prompt = (
        f"{_context_block(patch)}"
        f"모드: ARAM 아수라장 · 내 챔피언: {my_champ_ko}\n"
        f"우리 조합: {ally}\n"
        f"상대 조합: {enemy}\n"
        f"추천 증강: {augs}\n"
        f"아이템 빌드 루트(1~5코어): {build}\n\n"
        "이 조합 구도에서 각각 '- ' 줄로 알려줘. 아이템 이름은 한글로.\n"
        "① 플레이 방식(한타/포킹/진입 판단) 2줄\n"
        "② 증강 선택 우선순위 2줄\n"
        "③ 템트리 — 반드시 1코어·2코어·3코어·4코어·5코어를 각각 한 줄씩:\n"
        "   - 1코어: …\n"
        "   - 2코어: …\n"
        "   - 3코어: …\n"
        "   - 4코어: … (상황 옵션 가능)\n"
        "   - 5코어: … (후반 완성)\n"
        "   1~2코어만 쓰고 끝내지 마. 신발·상황 옵션도 언급해."
    )
    out = chat(prompt, api_key=api_key, model=model, max_tokens=3000)
    meta = parse_core_items_from_build(build)
    return enrich_item_tree_response(out, meta)


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
        f"{_context_block('')}"
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
