"""디스코드 웹훅 전송 — 복기 카드 PNG 업로드.

- URL 호스트·스킴 검증 (https + 디스코드 도메인만)
- multipart 업로드, 리디렉션 금지, 응답 크기 제한
- 429(rate limit)·5xx는 제한적 재시도, 나머지 4xx는 즉시 실패
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from lol_coach.http_security import secure_session

MAX_PNG_BYTES = 8 * 1024 * 1024  # 디스코드 웹훅 첨부 한도(8MB)
_MAX_RESPONSE_BYTES = 64 * 1024
_DEFAULT_ATTEMPTS = 3
_DEFAULT_TIMEOUT_S = 15.0
_MAX_RETRY_AFTER_S = 15.0

_ALLOWED_HOSTS = frozenset(
    {
        "discord.com",
        "discordapp.com",
        "canary.discord.com",
        "ptb.discord.com",
    }
)


class DiscordWebhookError(ValueError):
    """디스코드 웹훅 전송 실패."""


def validate_webhook_url(url: str) -> None:
    """웹훅 URL 검증 — 실패 시 DiscordWebhookError."""
    try:
        parsed = urlparse(url or "")
    except ValueError as exc:
        raise DiscordWebhookError("웹훅 URL을 해석할 수 없습니다") from exc
    if parsed.scheme != "https":
        raise DiscordWebhookError("웹훅 URL은 https:// 로 시작해야 합니다")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise DiscordWebhookError(f"허용되지 않는 웹훅 호스트입니다: {host or '(없음)'}")
    if not parsed.path.startswith("/api/webhooks/"):
        raise DiscordWebhookError("웹훅 URL 경로가 올바르지 않습니다 (/api/webhooks/...)")


def post_card(
    webhook_url: str,
    *,
    title: str,
    description: str,
    png_bytes: bytes,
    footer: str = "",
    attempts: int = _DEFAULT_ATTEMPTS,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> None:
    """복기 카드 PNG를 디스코드 웹훅으로 전송. 성공 시 None, 실패 시 예외."""
    validate_webhook_url(webhook_url)
    if not png_bytes:
        raise DiscordWebhookError("전송할 카드 이미지가 비어 있습니다")
    if len(png_bytes) > MAX_PNG_BYTES:
        raise DiscordWebhookError(
            f"카드 이미지가 디스코드 한도(8MB)를 초과했습니다: {len(png_bytes)} bytes"
        )

    embed = {
        "title": title[:256],
        "description": description[:4096],
        "color": 0xC8AA6E,
        "image": {"url": "attachment://review.png"},
    }
    if footer:
        embed["footer"] = {"text": footer[:2048]}
    payload_json = json.dumps({"embeds": [embed]}, ensure_ascii=False).encode("utf-8")

    session = secure_session()
    last_status = -1
    last_body = ""
    for attempt in range(max(1, attempts)):
        try:
            response = session.post(
                webhook_url,
                data={"payload_json": payload_json},
                files={"file": ("review.png", png_bytes, "image/png")},
                timeout=timeout,
                allow_redirects=False,
            )
        except Exception as exc:
            raise DiscordWebhookError(f"웹훅 요청 실패: {exc}") from exc
        last_status = response.status_code
        if response.status_code in (200, 204):
            return
        if response.status_code == 429:
            retry_after = _parse_retry_after(response)
            if attempt + 1 < attempts:
                time.sleep(retry_after)
                continue
            raise DiscordWebhookError(f"디스코드 rate limit(429) — {attempts}회 시도 후 실패")
        if response.status_code >= 500:
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            raise DiscordWebhookError(f"디스코드 서버 오류 (HTTP {last_status})")
        last_body = _read_error_body(response)
        break
    raise DiscordWebhookError(f"웹훅 전송 실패 (HTTP {last_status}): {last_body[:300]}")


def _parse_retry_after(response: object) -> float:
    raw = getattr(response, "headers", {}).get("Retry-After", "1")
    try:
        return min(max(float(raw), 0.0), _MAX_RETRY_AFTER_S)
    except (TypeError, ValueError):
        return 1.0


def _read_error_body(response: object) -> str:
    try:
        raw = getattr(response, "content", b"")
        body = raw[:_MAX_RESPONSE_BYTES] if isinstance(raw, (bytes, bytearray)) else b""
        return bytes(body).decode("utf-8", errors="replace")
    except Exception:
        return ""
