"""사용자가 설정한 OpenAI 호환 API의 선택형 AI 코칭."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit, urlunsplit

DEFAULT_MODEL = ""
DEFAULT_PROVIDER = "custom"

# chat() 기본값 — GUI AI 카드 타임아웃과 맞출 때 참고
DEFAULT_TIMEOUT_S = 45.0
DEFAULT_MAX_ATTEMPTS = 3

# 게이트웨이 응답 크기 상한 (비정상 응답으로 인한 메모리 낭비 방지)
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

# chat() 호출마다 세션+TLS를 새로 만들지 않도록 모듈 세션을 재사용한다.
_LLM_SESSION: Any = None
_LLM_SESSION_LOCK = threading.Lock()


def _llm_session() -> Any:
    global _LLM_SESSION
    if _LLM_SESSION is None:
        with _LLM_SESSION_LOCK:
            if _LLM_SESSION is None:
                from lol_coach.http_security import secure_session

                _LLM_SESSION = secure_session()
    return _LLM_SESSION


def normalize_provider(value: str | None) -> str:
    """이전 호출부의 표시값 호환용. preset 라우팅은 지원하지 않는다."""
    return DEFAULT_PROVIDER


def normalize_base_url(value: str) -> str:
    """API 버전을 포함한 Base URL 검증. /v1 등의 경로를 추측하지 않는다."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Base URL에 제어 문자를 사용할 수 없습니다")
    raw = value.strip()
    if not raw:
        raise ValueError("Base URL을 입력하세요")
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        raise ValueError("Base URL 형식이 올바르지 않습니다") from None
    if (parsed.scheme not in ("https", "http") or not host
            or parsed.username is not None or parsed.password is not None
            or "?" in raw or "#" in raw or "\\" in raw
            or any(char.isspace() for char in raw) or "%" in host
            or port == 0):
        raise ValueError("Base URL은 사용자 정보·쿼리·fragment 없는 HTTP(S) 주소여야 합니다")
    local = host.lower() == "localhost"
    try:
        local = local or ip_address(host).is_loopback
    except ValueError:
        pass
    if parsed.scheme == "http" and not local:
        raise ValueError("원격 Base URL은 HTTPS가 필요합니다 (HTTP는 localhost만 허용)")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_credentials(api_key: str, model: str = "") -> tuple[str, str]:
    """헤더·환경 파일 삽입을 막고 비밀값을 오류에 포함하지 않는다."""
    if any(ord(char) < 32 or ord(char) == 127 for char in api_key + model):
        raise ValueError("API 키와 모델에 제어 문자를 사용할 수 없습니다")
    key, chosen_model = api_key.strip(), model.strip()
    if any(char.isspace() or ord(char) > 126 for char in key):
        raise ValueError("API 키 형식이 올바르지 않습니다")
    return key, chosen_model


def _configured_base_url() -> str:
    if os.getenv("LOL_COACH_LLM_PROVIDER", "").strip().lower() != DEFAULT_PROVIDER:
        return ""
    return os.getenv("LOL_COACH_LLM_BASE_URL", "").strip()


_SYSTEM = (
    "너는 리그 오브 레전드 실전 코치다. 사용자에게 한국어로, 30초 안에 읽을 수 "
    "있게 구체적인 인게임 조언을 준다. 일반론('시야를 챙기세요' 같은 문장)만 "
    "나열하지 말고 주어진 매치업/조합/전적 정보에 근거해 구체적으로 조언한다. "
    "메시지에 명시된 '분석 데이터 패치'를 기준으로 삼되 최신 패치라고 단정하지 않고, 훈련 시점 이후 "
    "패치에서 바뀐 스킬·아이템·룬 수치를 단정하지 않는다. 이전 시즌 메타를 "
    "현재 패치에 그대로 적용하지 않는다. 확실하지 않은 내용은 '~일 수 있다'로 "
    "표현하고, 주어지지 않은 정보는 지어내지 않는다. 오브젝트 생성 시간·모드 규칙은 "
    "입력에 근거가 없으면 단정하지 않는다. 일반 협곡·Swiftplay·ARAM의 규칙을 섞지 않는다. "
    "마크다운 헤더나 이모지 "
    "없이 각 줄을 '- ' 로 시작해 출력한다."
)


def _context_block(patch: str) -> str:
    """데이터 시점을 전달하되 캐시/스냅샷을 최신 라이브라고 단정하지 않는다."""
    from datetime import date

    lines = [f"오늘 날짜: {date.today().isoformat()}"]
    if patch:
        lines.append(f"분석 데이터 패치: {patch} — 최신 라이브 패치와 다를 수 있음")
    else:
        lines.append("분석 데이터 패치: 미확인 — 현재 메타·수치를 단정하지 않기")
    lines.append("확실하지 않은 수치(쿨다운·데미지·아이템 스탯)는 추측해 말하지 않기")
    return "\n".join(lines) + "\n"


def resolve_api_key(explicit: str = "", *, provider: str = "", base_url: str = "") -> str:
    """명시 키 또는 같은 Base URL에 명시적으로 저장한 custom 키만 반환."""
    if provider.strip() not in ("", DEFAULT_PROVIDER):
        return ""
    if explicit.strip():
        return validate_credentials(explicit)[0]
    configured = _configured_base_url()
    if not configured:
        return ""
    try:
        if base_url and normalize_base_url(base_url) != normalize_base_url(configured):
            return ""
        normalize_base_url(configured)
        return validate_credentials(os.getenv("LOL_COACH_LLM_KEY", ""))[0]
    except ValueError:
        return ""


def _models_response(api_key: str, base_url: str, timeout_s: float) -> Any:
    import requests

    url = normalize_base_url(base_url)
    key, _ = validate_credentials(api_key)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        return _llm_session().get(
            f"{url}/models", headers=headers, timeout=timeout_s, stream=True,
            allow_redirects=False, proxies={"http": "", "https": "", "all": ""},
            verify=requests.certs.where(),
        )
    except Exception:
        raise RuntimeError("AI 서버에 연결하지 못했습니다") from None


def _check_status(resp: Any) -> None:
    status = int(getattr(resp, "status_code", 0) or 0)
    if status in (401, 403):
        raise RuntimeError("API 키가 거부됐습니다")
    if 300 <= status < 400:
        raise RuntimeError("AI 서버 리디렉션은 허용되지 않습니다. Base URL을 확인하세요")
    if not 200 <= status < 300:
        raise RuntimeError(f"AI 서버 오류 ({status})")


def _close_response(resp: Any) -> None:
    close = getattr(resp, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def list_models(api_key: str = "", base_url: str = "", *, timeout_s: float = 12.0) -> list[str]:
    """명시적으로 GET /models를 요청한다. 조회 불가 시 안전한 오류를 반환한다.

    빈 목록 또는 조회 오류일 때 호출부는 모델 직접 입력을 허용해야 한다.
    네이티브 Anthropic 프로토콜은 지원하지 않는다.
    """
    resp = _models_response(api_key, base_url, timeout_s)
    try:
        _check_status(resp)
        try:
            data = _read_json_bounded(resp)
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ValueError("invalid model list")
            models = []
            for row in rows:
                model = row.get("id") if isinstance(row, dict) else None
                if isinstance(model, str) and model.strip():
                    _, model = validate_credentials("", model)
                    if model not in models:
                        models.append(model)
            return models
        except Exception:
            raise RuntimeError("모델 목록을 읽지 못했습니다. 모델을 직접 입력하세요") from None
    finally:
        _close_response(resp)


def probe_gateway(
    api_key: str = "", model: str = "", *, provider: str = "", base_url: str = "",
    timeout_s: float = 12.0,
) -> tuple[bool, str]:
    """GET /models 상태 확인만 수행하며 추론·모델 실행은 요청하지 않는다."""
    if provider.strip() not in ("", DEFAULT_PROVIDER):
        return False, "Base URL과 API 키를 다시 설정하세요"
    resp = None
    try:
        resp = _models_response(api_key, base_url, timeout_s)
        _check_status(resp)
        return True, "AI 서버 응답 확인됨 (모델 실행은 확인하지 않음)"
    except (ValueError, RuntimeError) as exc:
        return False, str(exc)
    except Exception:
        return False, "AI 서버 응답을 확인하지 못했습니다"
    finally:
        if resp is not None:
            _close_response(resp)


def _retry_delay_s(resp: Any, attempt: int) -> float:
    """429/5xx 재시도 대기 — Retry-After 헤더 존중 (상한 5초), 없으면 기존 백오프."""
    headers = getattr(resp, "headers", {}) or {}
    raw = str(headers.get("Retry-After") or "").strip()
    if raw:
        try:
            return min(max(float(raw), 0.5), 5.0)
        except ValueError:
            pass
    return 0.8 + attempt


def _read_json_bounded(resp: Any) -> dict[str, Any]:
    """본문을 바이트 상한 안에서 읽어 JSON으로 파싱."""
    resp_headers = getattr(resp, "headers", {}) or {}
    try:
        length = int(resp_headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        length = 0
    if length > _MAX_RESPONSE_BYTES:
        raise ValueError("응답 크기 초과")
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
                raise ValueError("응답 크기 초과")
            chunks.append(raw)
        return json.loads(b"".join(chunks))
    content = getattr(resp, "content", b"") or b""
    if len(content) > _MAX_RESPONSE_BYTES:
        raise ValueError("응답 크기 초과")
    return resp.json()


def _content_of(data: dict[str, Any]) -> str:
    """chat completion 응답 JSON → 메시지 본문."""
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    return str(msg.get("content") or "").strip()


def _consume_sse(
    resp: Any,
    on_delta: Callable[[str], None] | None,
    *,
    limit: int = _MAX_RESPONSE_BYTES,
) -> tuple[str, str]:
    """OpenAI 호환 SSE 스트림 소비 — (누적 텍스트, finish_reason).

    델타마다 ``on_delta(누적 텍스트)`` 를 호출한다(워커 스레드). 연결이
    중간에 끊겨도 지금까지 받은 텍스트는 반환한다.
    """
    total = 0
    acc: list[str] = []
    finish = ""
    try:
        for raw_line in resp.iter_lines(chunk_size=2048):
            if not raw_line:
                continue
            total += len(raw_line if isinstance(raw_line, bytes) else str(raw_line).encode("utf-8"))
            if total > limit:
                break
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else str(raw_line)
            )
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            if not body:
                continue
            try:
                obj = json.loads(body)
            except Exception:
                continue
            choices = obj.get("choices") or [{}]
            choice = choices[0] or {}
            piece = (choice.get("delta") or {}).get("content")
            if piece:
                acc.append(str(piece))
                if on_delta is not None:
                    try:
                        on_delta("".join(acc))
                    except Exception:
                        pass  # UI 콜백 실패는 스트림을 죽이지 않는다
            fr = choice.get("finish_reason")
            if fr:
                finish = str(fr)
    except Exception:
        pass  # 부분 텍스트라도 반환
    finally:
        _close_response(resp)
    return "".join(acc), finish


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
    on_delta: Callable[[str], None] | None = None,
) -> str | None:
    """OpenAI 호환 chat completion — 실패/타임아웃 시 None.

    ``on_delta`` 를 넘기면 ``stream: true`` 로 요청해 델타마다
    ``on_delta(누적 텍스트)`` 를 호출한다 — 첫 표시까지의 체감 대기가
    전체 생성 시간에서 첫 토큰 도착 시간으로 줄어든다.
    """
    if provider.strip() not in ("", DEFAULT_PROVIDER):
        return None
    try:
        configured = _configured_base_url()
        url = normalize_base_url(base_url or configured)
        if api_key is None and (not configured or url != normalize_base_url(configured)):
            return None
        key = api_key if api_key is not None else resolve_api_key(base_url=url)
        chosen_model = model
        if not chosen_model and configured and url == normalize_base_url(configured):
            chosen_model = os.getenv("LOL_COACH_LLM_MODEL", "")
        key, chosen_model = validate_credentials(key, chosen_model)
        if not chosen_model:
            return None
    except ValueError:
        return None
    payload: dict[str, Any] = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    token_option = "max_tokens"
    use_stream = on_delta is not None
    if use_stream:
        payload["stream"] = True
    req_headers = {
        **({"Authorization": f"Bearer {key}"} if key else {}),
        "Content-Type": "application/json",
    }
    attempts = max(1, int(max_attempts))
    try:
        import time

        import requests

        session = _llm_session()
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
                        allow_redirects=False,
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
                        time.sleep(_retry_delay_s(resp, attempt))
                        continue
                    return None
                try:
                    # 서버가 명시적으로 거부한 옵션만 조정하고 기존 재시도 한도를 지킨다.
                    if resp.status_code == 400 and attempt < attempts - 1:
                        error = _read_json_bounded(resp).get("error")
                        if isinstance(error, dict):
                            param, code = error.get("param"), error.get("code")
                            if param == "max_tokens" and code == "unsupported_parameter" and token_option == "max_tokens":
                                token_option = "max_completion_tokens"
                                payload[token_option] = payload.pop("max_tokens")
                                continue
                            if param == "temperature" and code in ("unsupported_parameter", "unsupported_value") and "temperature" in payload:
                                payload.pop("temperature")
                                continue
                    _check_status(resp)
                    resp.raise_for_status()
                    if use_stream:
                        ctype = str(
                            (getattr(resp, "headers", {}) or {}).get("Content-Type") or ""
                        ).lower()
                        if "text/event-stream" in ctype:
                            text, _finish = _consume_sse(resp, on_delta)
                            if text:
                                return text  # 잘리더라도 부분 텍스트가 무(無)보다 낫다
                            if attempt < attempts - 1:
                                time.sleep(0.8 + attempt)
                                continue
                            return None
                        # 게이트웨이가 stream=True를 무시하고 JSON으로 답한 경우
                        return _content_of(_read_json_bounded(resp))
                    data = _read_json_bounded(resp)
                    text = _content_of(data)
                    if text:
                        return text
                    # 추론 모델이 reasoning_content 에 토큰을 다 쓴 경우 한 번 더 시도
                    finish = (data.get("choices") or [{}])[0].get("finish_reason")
                    if finish == "length" and attempt < attempts - 1:
                        max_tokens = min(max_tokens * 2, 4000)
                        payload[token_option] = max_tokens
                        continue
                    return None
                except Exception:
                    return None
            finally:
                if resp is not None:
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
    provider: str = "",
    on_delta: Callable[[str], None] | None = None,
    base_url: str = "",
) -> str | None:
    """빠른 추천용 — 상대 라이너 카운터 기반 30초 라인전 팁."""
    counter_txt = "\n".join(_counter_lines(counters)) or "- 데이터 없음"
    prompt = (
        f"{_context_block(patch)}"
        f"매치업: 내 포지션 {role_ko} vs 상대 {enemy_ko} (패치 {patch})\n"
        f"blitz.gg 카운터 데이터 (15분 골드 차 기준):\n{counter_txt}\n\n"
        f"{enemy_ko} 상대 라인전에서 픽타임 30초 동안 읽을 팁을 알려줘."
    )
    return chat(
        prompt,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        max_tokens=2000,
        on_delta=on_delta,
    )


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
    on_delta: Callable[[str], None] | None = None,
    base_url: str = "",
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
    out = chat(
        prompt,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        max_tokens=3000,
        on_delta=on_delta,
    )
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
    on_delta: Callable[[str], None] | None = None,
    base_url: str = "",
) -> str | None:
    """ARAM 아수라장용 — 양 팀 조합 기반 인게임 플레이/증강 코칭.

    아이템 빌드는 화면에 따로 표시되므로 여기서는 다루지 않는다.
    오직 인게임 조합 분석과 실전 행동 팁에 집중.
    """
    has_comp = bool(ally_comp) and bool(enemy_comp)
    augs = augments_txt or "정보 없음"
    if has_comp:
        comp_block = f"우리 조합: {', '.join(ally_comp)}\n상대 조합: {', '.join(enemy_comp)}\n"
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
    return chat(
        prompt,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        max_tokens=2000,
        temperature=0.0,
        on_delta=on_delta,
    )


def coach_review(
    match,
    rev,
    api_key: str = "",
    model: str = DEFAULT_MODEL,
    provider: str = "",
    on_delta: Callable[[str], None] | None = None,
    base_url: str = "",
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
    return chat(
        prompt,
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        max_tokens=2000,
        on_delta=on_delta,
    )
