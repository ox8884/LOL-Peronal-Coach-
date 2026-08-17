"""선택형 AI 코칭 — OpenAI 호환 게이트웨이 (opencode-go / Gemini / Groq / OpenRouter)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_PROVIDER = "opencode-go"
PROVIDER_NAME = "opencode-go"

# chat() 기본값 — GUI AI 카드 타임아웃과 맞출 때 참고
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_MAX_ATTEMPTS = 3

# 게이트웨이 응답 크기 상한 (비정상 응답으로 인한 메모리 낭비 방지)
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

# 테스트에서 monkeypatch 하는 기본 경로 (후보 목록의 첫 항목으로도 사용)
_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

_OPENROUTER_AUTH = "https://openrouter.ai/auth"
_OPENROUTER_EXCHANGE = "https://openrouter.ai/api/v1/auth/keys"
_APP_TITLE = "롤 실전 코치"
_APP_REFERER = "https://github.com/ox8884/LOL-Peronal-Coach-"


@dataclass(frozen=True)
class Provider:
    """설정에 노출하는 LLM 프로바이더."""

    id: str
    name: str
    base_url: str
    default_model: str
    models: tuple[str, ...]
    hint: str
    key_url: str = ""
    extra_body: dict[str, object] = field(default_factory=dict)
    extra_headers: dict[str, str] = field(default_factory=dict)
    supports_oauth: bool = False
    detect_opencode: bool = False


PROVIDERS: dict[str, Provider] = {
    "opencode-go": Provider(
        id="opencode-go",
        name="opencode-go",
        base_url=BASE_URL,
        default_model=DEFAULT_MODEL,
        models=(
            "deepseek-v4-flash",
            "deepseek-v4-pro",
            "kimi-k3",
            "glm-5",
            "qwen3.7-plus",
            "mimo-v2.5",
        ),
        hint="유료 게이트웨이. 키를 비우면 이 PC의 OpenCode CLI 로그인을 자동 감지합니다.",
        key_url="https://opencode.ai",
        extra_body={"reasoning_effort": "low"},
        detect_opencode=True,
    ),
    "gemini": Provider(
        id="gemini",
        name="Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.5-flash",
        models=("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"),
        hint="구글 계정으로 키만 받으면 됩니다. 결제 연결(Set up billing)을 하지 마세요. 한도까지 무료, 넘으면 거절입니다.",
        key_url="https://aistudio.google.com/apikey",
    ),
    "groq": Provider(
        id="groq",
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.1-8b-instant",
        models=(
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-20b",
        ),
        hint="카드 없이 무료입니다. 한도를 넘으면 청구 대신 거절됩니다.",
        key_url="https://console.groq.com/keys",
    ),
    "openrouter": Provider(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/free",
        models=(
            "openrouter/free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
        ),
        hint="브라우저로 연결하거나 키를 붙이세요. :free 모델은 크레딧 없이 하루 약 50회입니다.",
        key_url="https://openrouter.ai/keys",
        extra_headers={
            "HTTP-Referer": _APP_REFERER,
            "X-Title": _APP_TITLE,
        },
        supports_oauth=True,
    ),
}

PROVIDER_IDS: tuple[str, ...] = tuple(PROVIDERS.keys())
PROVIDER_LABELS: dict[str, str] = {pid: p.name for pid, p in PROVIDERS.items()}


def normalize_provider(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "google": "gemini",
        "google-gemini": "gemini",
        "opencode": "opencode-go",
        "or": "openrouter",
    }
    pid = aliases.get(raw, raw)
    return pid if pid in PROVIDERS else DEFAULT_PROVIDER


def get_provider(value: str | None = None) -> Provider:
    return PROVIDERS[normalize_provider(value)]


def resolve_provider(explicit: str = "") -> Provider:
    """명시 값 > env > 기본(opencode-go)."""
    if explicit.strip():
        return get_provider(explicit)
    return get_provider(os.getenv("LOL_COACH_LLM_PROVIDER", ""))


def provider_key_env(provider: str) -> str:
    return "LOL_COACH_LLM_KEY_" + normalize_provider(provider).upper().replace("-", "_")


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


def resolve_api_key(explicit: str = "", *, provider: str = "") -> str:
    """사용 가능한 LLM 키 결정 — 명시 입력 > 프로바이더 env > 공용 env > opencode 자동 감지."""
    key = explicit.strip()
    if key:
        return key
    prov = resolve_provider(provider)
    key = os.getenv(provider_key_env(prov.id), "").strip()
    if key:
        return key
    key = os.getenv("LOL_COACH_LLM_KEY", "").strip()
    if key:
        return key
    if prov.detect_opencode:
        return detect_opencode_key()
    return ""


def probe_gateway(
    api_key: str = "",
    model: str = "",
    *,
    provider: str = "",
    base_url: str = "",
    timeout_s: float = 12.0,
) -> tuple[bool, str]:
    """선택한 게이트웨이에 API 키가 먹히는지 확인한다. 키는 메시지에 넣지 않는다."""
    prov = resolve_provider(provider)
    key = resolve_api_key(api_key, provider=prov.id)
    if not key:
        return False, f"{prov.name} API 키가 없습니다"
    url = (base_url or prov.base_url).rstrip("/")
    headers = {"Authorization": f"Bearer {key}", **prov.extra_headers}
    try:
        from lol_coach.http_security import secure_session

        session = secure_session()
        resp = session.get(
            f"{url}/models",
            headers=headers,
            timeout=timeout_s,
            stream=True,
        )
        # stream=True로 본문 버퍼링 방지 — 상태코드만 확인하므로 본문 미읽기
    except Exception:
        return False, f"{prov.name} 에 연결하지 못했습니다"
    if resp.status_code in (401, 403):
        return False, "API 키가 거부됐습니다"
    if resp.status_code >= 400:
        return False, f"게이트웨이 오류 {resp.status_code}"
    label = (model or prov.default_model).strip() or prov.default_model
    return True, f"{prov.name} 연결됨 · {label}"


def chat(
    prompt: str,
    *,
    system: str = _SYSTEM,
    model: str = "",
    max_tokens: int = 500,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    api_key: str | None = None,
    provider: str = "",
    base_url: str = "",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    temperature: float = 0.7,
) -> str | None:
    """OpenAI 호환 chat completion — 실패/타임아웃 시 None."""
    prov = resolve_provider(provider)
    key = api_key if api_key is not None else resolve_api_key(provider=prov.id)
    if not key:
        return None
    chosen_model = (model or prov.default_model).strip() or prov.default_model
    url = (base_url or prov.base_url).rstrip("/")
    payload: dict[str, Any] = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    payload.update(prov.extra_body)
    req_headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        **prov.extra_headers,
    }
    attempts = max(1, int(max_attempts))
    try:
        import time

        import requests

        from lol_coach.http_security import secure_session

        session = secure_session()
        for attempt in range(attempts):
            resp = None
            try:
                try:
                    resp = session.post(
                        f"{url}/chat/completions",
                        headers=req_headers,
                        json=payload,
                        timeout=timeout_s,
                        stream=True,
                        proxies={"http": "", "https": "", "all": ""},
                        verify=requests.certs.where(),
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
                    resp_headers = getattr(resp, "headers", {}) or {}
                    try:
                        length = int(resp_headers.get("Content-Length") or 0)
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
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                text = str(msg.get("content") or "").strip()
                if text:
                    return text
                # 추론 모델이 reasoning_content 에 토큰을 다 쓴 경우 한 번 더 시도
                finish = (data.get("choices") or [{}])[0].get("finish_reason")
                if finish == "length" and attempt < attempts - 1:
                    max_tokens = min(max_tokens * 2, 4000)
                    payload["max_tokens"] = max_tokens
                    continue
                return None
            finally:
                close = getattr(resp, "close", None)
                if callable(close):
                    close()
        return None
    except Exception:
        return None


def openrouter_pkce() -> tuple[str, str]:
    """OpenRouter PKCE (S256) — (verifier, challenge)."""
    import base64
    import hashlib
    import secrets

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def exchange_openrouter_code(
    code: str,
    code_verifier: str,
    *,
    timeout_s: float = 20.0,
) -> tuple[bool, str]:
    """인가 코드를 유저 키로 교환. 성공 시 (True, key), 실패 시 (False, 안내)."""
    token = (code or "").strip()
    if not token or not code_verifier:
        return False, "인가 코드가 없습니다"
    try:
        from lol_coach.http_security import secure_session

        session = secure_session()
        resp = session.post(
            _OPENROUTER_EXCHANGE,
            json={
                "code": token,
                "code_verifier": code_verifier,
                "code_challenge_method": "S256",
            },
            timeout=timeout_s,
        )
    except Exception:
        return False, "OpenRouter 키 교환에 실패했습니다"
    if resp.status_code in (401, 403):
        return False, "OpenRouter 인가가 거부됐습니다"
    if resp.status_code >= 400:
        return False, f"OpenRouter 오류 {resp.status_code}"
    try:
        data = resp.json()
    except Exception:
        return False, "OpenRouter 응답을 읽지 못했습니다"
    key = str((data or {}).get("key") or "").strip()
    if not key:
        return False, "OpenRouter 키를 받지 못했습니다"
    return True, key


def run_openrouter_oauth(*, timeout_s: float = 180.0) -> tuple[bool, str]:
    """브라우저에서 OpenRouter 로그인 후 키를 받는다. 성공 시 (True, key)."""
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlencode, urlparse

    verifier, challenge = openrouter_pkce()
    box: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server 규약
            parsed = urlparse(self.path)
            if parsed.path in ("/favicon.ico", "/"):
                code = (parse_qs(parsed.query).get("code") or [""])[0]
            else:
                code = (parse_qs(parsed.query).get("code") or [""])[0]
            if code:
                box["code"] = code
                body = (
                    "<!doctype html><meta charset=utf-8><title>연결됨</title>"
                    "<p>OpenRouter 연결이 끝났습니다. 이 창을 닫고 앱으로 돌아가세요.</p>"
                )
                self.send_response(200)
            else:
                body = (
                    "<!doctype html><meta charset=utf-8><title>대기</title>"
                    "<p>인가 코드가 없습니다. 앱에서 다시 연결해 주세요.</p>"
                )
                self.send_response(400)
            raw = body.encode("utf-8")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            if code:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *_args: object) -> None:
            return

    try:
        server = HTTPServer(("127.0.0.1", 0), Handler)
    except Exception:
        return False, "로컬 로그인 창을 열지 못했습니다"
    port = int(server.server_address[1])
    callback = f"http://127.0.0.1:{port}/"
    query = urlencode(
        {
            "callback_url": callback,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    try:
        webbrowser.open(f"{_OPENROUTER_AUTH}?{query}")
    except Exception:
        server.server_close()
        return False, "브라우저를 열지 못했습니다"
    timer = threading.Timer(max(10.0, timeout_s), server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    except Exception:
        return False, "OpenRouter 로그인이 중단됐습니다"
    finally:
        timer.cancel()
        try:
            server.server_close()
        except Exception:
            pass
    code = box.get("code", "")
    if not code:
        return False, "브라우저 로그인이 시간 초과됐거나 취소됐습니다"
    return exchange_openrouter_code(code, verifier)


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
    provider: str = "",
) -> str | None:
    """빠른 추천용 — 상대 라이너 카운터 기반 30초 라인전 팁."""
    counter_txt = "\n".join(_counter_lines(counters)) or "- 데이터 없음"
    prompt = (
        f"{_context_block(patch)}"
        f"매치업: 내 포지션 {role_ko} vs 상대 {enemy_ko} (패치 {patch})\n"
        f"blitz.gg 카운터 데이터 (15분 골드 차 기준):\n{counter_txt}\n\n"
        f"{enemy_ko} 상대 라인전에서 픽타임 30초 동안 읽을 팁을 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, provider=provider, max_tokens=2000)


def _format_core_path(
    core_items: list[str] | None,
    *,
    max_cores: int = 5,
) -> str:
    items = [str(x).strip() for x in (core_items or []) if str(x).strip()]
    if not items:
        return "데이터 없음"
    return " → ".join(f"{i}코어 {name}" for i, name in enumerate(items[:max_cores], 1))


def _format_core_lines(
    core_items: list[str] | None,
    *,
    max_cores: int = 5,
) -> str:
    items = [str(x).strip() for x in (core_items or []) if str(x).strip()]
    if not items:
        return f"- (메타 데이터 없음 — 챔프 표준 1~{max_cores}코어를 채워 줘)"
    lines = [f"- {i}코어: {name}" for i, name in enumerate(items[:max_cores], 1)]
    # 슬롯이 부족하면 명시적으로 채우라고 표시
    for i in range(len(items) + 1, max_cores + 1):
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
        if 1 <= idx <= 6 and _is_real_core_name(name):
            slots[idx] = name
    if slots:
        return [slots[i] for i in range(1, 7) if i in slots]
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
        if len(out) >= 6:
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
                if 1 <= idx <= 6 and _is_real_core_name(name) and idx not in slots:
                    slots[idx] = name
            continue
        idx = int(m.group(1))
        name = _clean_item_name(m.group(2))
        if 1 <= idx <= 6 and _is_real_core_name(name):
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
    duplicate_slots: set[int] = set()
    used_names: set[str] = set()
    for slot, name in sorted(slots.items()):
        if name in used_names:
            duplicate_slots.add(slot)
        else:
            used_names.add(name)
    for slot in duplicate_slots:
        slots.pop(slot)
    real_n = len(slots)

    if (real_n >= min_cores and not duplicate_slots) or not meta:
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

    if duplicate_slots:
        kept = [
            raw
            for raw in body.splitlines()
            if not (
                (match := _SINGLE_CORE_LINE_RE.match(raw.strip()))
                and int(match.group(1)) in duplicate_slots
            )
        ]
        body = "\n".join(kept)
    note = "- (메타 빌드로 아이템 트리 보충 — 모델 응답 검증 후)"
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
    provider: str = "",
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
    out = chat(prompt, api_key=api_key, model=model, provider=provider, max_tokens=3000)
    return enrich_item_tree_response(out, list(core_items or []))


def coach_aram(
    my_champ_ko: str,
    ally_comp: list,
    enemy_comp: list,
    augments_txt: str,
    patch: str,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
    provider: str = "",
) -> str | None:
    """ARAM 아수라장용 — 양 팀 조합 기반 인게임 플레이/증강 코칭.

    아이템 빌드는 화면에 따로 표시되므로 여기서는 다루지 않는다.
    오직 인게임 조합 분석과 실전 행동 팁에 집중.
    """
    has_comp = bool(ally_comp) and bool(enemy_comp)
    augs = augments_txt or "정보 없음"
    if has_comp:
        comp_block = (
            f"우리 조합: {', '.join(ally_comp)}\n"
            f"상대 조합: {', '.join(enemy_comp)}\n"
        )
    else:
        comp_block = "조합 데이터 없음 — 챔피언 기준 팁만\n"
    items: list[str] = []
    if has_comp:
        items.append("1) 조합 분석 2줄 — 우리 팀 강점과 상대 팀 위협 요소")
    items.append("2) 승리 조건 1줄 — 이 조합으로 이기는 핵심")
    items.append("3) 증강 선택 1줄 — 제시 증강 중 가장 추천하는 것과 이유")
    items.append("4) 초반(1~6레벨) 행동 2줄 — 포지셔닝, 스킬 교환, 딜/탱킹 포커스")
    items.append("5) 한타 행동 3줄 — 진입 타이밍, 궁극기 사용, 물어야 할 타겟")
    if has_comp:
        items.append("6) 주의할 상대 2줄 — 가장 위험한 적 챔피언과 대응법")
    items_txt = "\n".join(items) + "\n"
    prompt = (
        f"{_context_block(patch)}"
        f"모드: ARAM 아수라장 · 내 챔피언: {my_champ_ko}\n"
        f"{comp_block}"
        f"제시 증강: {augs}\n\n"
        "이 판은 ARAM 아수라장이다. 정글 캠프·오브젝트·라인 관리 같은 "
        "소환사의 협곡 전용 개념은 절대 언급하지 마.\n"
        "아이템 빌드는 화면에 따로 표시되므로 아이템 추천은 하지 마.\n\n"
        "아래 형식으로 각 항목을 '- ' 한 줄로 간결하게 적어.\n"
        f"{items_txt}"
    )
    if not has_comp:
        prompt += (
            "1번(조합 분석)과 6번(주의할 상대)은 조합 데이터가 없으므로 생략하고 "
            "챔피언 기반 실전 팁만 적어.\n"
        )
    prompt += "쓸데없는 일반론 말고 이 조합에 맞는 구체적이고 실전적인 팁만 적어."
    return chat(prompt, api_key=api_key, model=model, provider=provider, max_tokens=2000, temperature=0.0)


def coach_review(
    match,
    rev,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
    provider: str = "",
) -> str | None:
    """경기 복기용 — 한 판 요약 + 규칙 판정 기반 승패 코칭."""
    mark = "승리" if match.win else "패배"
    reasons = " · ".join(rev.win_loss_reasons[:3]) or "없음"
    good = " · ".join(rev.good[:2]) or "없음"
    improve = " · ".join(rev.improve[:2]) or "없음"
    # 게임 모드 인지 — ARAM(칼바람·아수라장)은 SR 전용 조언 금지
    mode_label = getattr(match, "mode_label", "") or ""
    is_aram = "ARAM" in mode_label or mode_label == "칼바람"
    mode_line = f"모드: {mode_label}  ·  " if mode_label else ""
    mode_guard = ""
    if is_aram:
        mode_guard = (
            "이 판은 ARAM(칼바람/아수라장)입니다. 정글 캠프·늑대·두꺼비·"
            "오브젝트(용/바론/전령)·라인 관리·스플릿 푸시·CS 150 같은 "
            "소환사의 협곡 전용 개념은 이 판에 존재하지 않으므로 절대 언급하지 마. "
            "오직 한타·포지셔닝·스킬 적중·딜/탱킹·킬 교환 같은 ARAM 요소만 다뤄.\n"
        )
    prompt = (
        f"{_context_block('')}"
        f"{mode_line}"
        f"한 판 결과: {mark}  ·  챔피언 {match.champion_name}\n"
        f"KDA {match.kda_str} (비율 {match.kda_ratio})  ·  CS {match.cs}  ·  "
        f"딜 {match.damage_to_champs:,}\n"
        f"킬관여 {match.kill_participation}  ·  데스 {match.deaths}  ·  "
        f"경기 시간 {match.duration_min}분\n"
        f"규칙 기반 판정 — 주요 원인: {reasons}\n"
        f"잘한 점: {good}  ·  개선점: {improve}\n\n"
        f"{mode_guard}"
        "이 판의 진짜 승패 요인과 다음 판에 바로 쓸 행동 1~2가지를 알려줘."
    )
    return chat(prompt, api_key=api_key, model=model, provider=provider, max_tokens=2000)
