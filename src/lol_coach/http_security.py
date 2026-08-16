"""Bounded HTTP response readers and redirect-safe binary downloads."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias, TypeGuard
from urllib.parse import urljoin, urlparse

import requests

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

MAX_JSON_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_RIOT_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# GitHub 릴리스 다운로드 허용 호스트 (github.com → githubusercontent.com 리디렉션)
ALLOWED_DOWNLOAD_HOSTS: frozenset[str] = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
})


@dataclass(frozen=True, slots=True)
class ResponseTooLargeError(ValueError):
    max_bytes: int
    actual_bytes: int

    def __str__(self) -> str:
        return f"HTTP 응답이 허용 크기를 초과했습니다: {self.actual_bytes} > {self.max_bytes}"


@dataclass(frozen=True, slots=True)
class UnsafeRedirectError(ValueError):
    source_url: str
    target_url: str

    def __str__(self) -> str:
        return f"허용되지 않은 리디렉션입니다: {self.source_url} -> {self.target_url}"


@dataclass(frozen=True, slots=True)
class InvalidJsonObjectError(ValueError):
    field: str

    def __str__(self) -> str:
        return f"JSON 객체 필드 형식이 올바르지 않습니다: {self.field}"


@dataclass(frozen=True, slots=True)
class DownloadPolicy:
    timeout: float
    max_bytes: int
    max_redirects: int = 3


def secure_session() -> requests.Session:
    """Create a session that ignores ambient proxy and CA environment variables."""
    session = requests.Session()
    session.trust_env = False
    return session


def read_limited_bytes(response: requests.Response, max_bytes: int) -> bytes:
    """Read a streamed response while enforcing declared and actual byte limits."""
    raw_length = response.headers.get("Content-Length")
    if raw_length:
        try:
            declared = int(raw_length)
        except ValueError:
            declared = 0
        if declared > max_bytes:
            raise ResponseTooLargeError(max_bytes=max_bytes, actual_bytes=declared)

    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLargeError(max_bytes=max_bytes, actual_bytes=len(body))
    return bytes(body)


def read_limited_json(response: requests.Response, max_bytes: int) -> JsonValue:
    """Decode JSON only after a streamed byte limit has been enforced."""
    return json.loads(read_limited_bytes(response, max_bytes))


def read_limited_text(response: requests.Response, max_bytes: int) -> str:
    """Decode a bounded response body for safe error reporting."""
    return read_limited_bytes(response, max_bytes).decode("utf-8", errors="replace")


def require_json_object(value: JsonValue, field: str) -> dict[str, JsonValue]:
    """Narrow an untrusted JSON value to the required object shape."""
    if not _is_json_object(value):
        raise InvalidJsonObjectError(field=field)
    return value


def require_object_path(value: JsonValue, *fields: str) -> dict[str, JsonValue]:
    """Traverse a required object-only path in untrusted JSON."""
    current = require_json_object(value, "response")
    for field in fields:
        current = require_json_object(current.get(field), field)
    return current


def fetch_json_object(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_bytes: int = MAX_JSON_RESPONSE_BYTES,
) -> dict[str, JsonValue]:
    """Fetch one non-redirecting HTTPS JSON object with a strict body limit."""
    with session.get(
        url,
        timeout=timeout,
        stream=True,
        allow_redirects=False,
    ) as response:
        response.raise_for_status()
        return require_json_object(read_limited_json(response, max_bytes), "response")


def _is_json_object(value: JsonValue) -> TypeGuard[dict[str, JsonValue]]:
    return isinstance(value, dict)


def download_same_origin(
    session: requests.Session,
    url: str,
    policy: DownloadPolicy,
) -> bytes:
    """Download bytes while allowing only bounded same-origin HTTPS redirects."""
    origin = _https_origin(url)
    current_url = url
    for redirect_count in range(policy.max_redirects + 1):
        with session.get(
            current_url,
            timeout=policy.timeout,
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("Location", "")
                target_url = urljoin(current_url, location)
                if redirect_count >= policy.max_redirects or _https_origin(target_url) != origin:
                    raise UnsafeRedirectError(
                        source_url=current_url,
                        target_url=target_url,
                    )
                current_url = target_url
                continue
            response.raise_for_status()
            return read_limited_bytes(response, policy.max_bytes)
    raise UnsafeRedirectError(source_url=url, target_url=current_url)


def _https_origin(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeRedirectError(source_url=url, target_url=url)
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeRedirectError(source_url=url, target_url=url) from exc
    return parsed.hostname.lower(), port


def is_allowed_host(url: str, allowed: frozenset[str]) -> bool:
    """URL 호스트가 허용 목록에 있는지 (HTTPS만)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    return parsed.hostname.lower() in allowed
