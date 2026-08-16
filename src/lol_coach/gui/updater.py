"""앱 내 자동 업데이트 — 다운로드 · SHA256 검증 · 인스톨러 실행.

GitHub Release 자산:
  - LOL-Coach-Setup-v{ver}.exe
  - LOL-Coach-Setup-v{ver}.exe.sha256  (필수)

네트워크는 전부 ``secure_session()`` (``trust_env=False``) 기반으로 환경
프록시/CA 환경변수를 무시한다 — llm.py·riot client 등 나머지 앱과 동일한
위협 모델. GitHub 다운로드는 ``github.com`` → ``objects.githubusercontent.com``
리디렉션을 쓰므로 호스트 허용목록 기반 수동 리디렉션 추적으로 받는다.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from lol_coach.http_security import (
    _REDIRECT_STATUSES,
    ALLOWED_DOWNLOAD_HOSTS,
    MAX_JSON_RESPONSE_BYTES,
    UnsafeRedirectError,
    fetch_json_object,
    is_allowed_host,
    read_limited_text,
    secure_session,
)

REPO = "ox8884/LOL-Peronal-Coach-"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/download"


def version_tuple(v: str) -> tuple[int, ...]:
    """'1.5.3' / 'v1.5.3' → (1,5,3)."""
    return tuple(int(x) for x in re.split(r"[.-]", v.strip().lstrip("vV")) if x.isdigit())


_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def is_valid_version(v: str) -> bool:
    """릴리스 태그로 안전한 형식인지 (숫자·점만 — 경로 조작 방지)."""
    return bool(_VERSION_RE.match(v.strip()))


# GitHub API/자산 응답 크기 상한 (blitz 클라이언트와 동일한 방어)
_MAX_API_BYTES = 2 * 1024 * 1024
_MAX_INSTALLER_BYTES = 250 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_DOWNLOAD_TIMEOUT_S = 60.0
_MAX_DOWNLOAD_REDIRECTS = 3

# read_limited_json 이 dict 가 아닌 값을 거부하므로 releases API 바디(객체)에
# 상한을 명시적으로 맞춘다 — _MAX_API_BYTES 보다 작거나 같아야 한다.
assert _MAX_API_BYTES <= MAX_JSON_RESPONSE_BYTES, "API 상한이 JSON 전역 상한을 초과함"


def fetch_latest_tag(timeout: float = 8.0) -> str:
    """최신 릴리스 태그 (앞에 v 없음). 실패 시 빈 문자열."""
    try:
        data = fetch_json_object(
            secure_session(), RELEASES_API, timeout=timeout, max_bytes=_MAX_API_BYTES
        )
    except Exception:
        return ""
    tag = str(data.get("tag_name") or "").lstrip("v")
    return tag if is_valid_version(tag) else ""


def installer_url(version: str) -> str:
    if not is_valid_version(version):
        raise ValueError(f"잘못된 릴리스 버전: {version!r}")
    return f"{DOWNLOAD_BASE}/v{version}/LOL-Coach-Setup-v{version}.exe"


def sha256_url(version: str) -> str:
    return installer_url(version) + ".sha256"


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def parse_sha256_text(text: str) -> str:
    """``hex  filename`` 또는 순수 hex 줄에서 해시 추출."""
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # "abc...  file.exe" or "abc..."
        part = line.split()[0].strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", part):
            return part
    return ""


def fetch_expected_sha256(version: str, timeout: float = 15.0) -> str:
    """릴리스의 .sha256 자산. 없으면 빈 문자열."""
    session = secure_session()
    url = sha256_url(version)
    try:
        for _ in range(_MAX_DOWNLOAD_REDIRECTS + 1):
            with session.get(
                url, timeout=timeout, stream=True, allow_redirects=False
            ) as resp:
                if resp.status_code in _REDIRECT_STATUSES:
                    location = resp.headers.get("Location", "")
                    url = urljoin(url, location)
                    if not is_allowed_host(url, ALLOWED_DOWNLOAD_HOSTS):
                        raise UnsafeRedirectError(
                            source_url=sha256_url(version), target_url=url
                        )
                    continue
                resp.raise_for_status()
                raw = read_limited_text(resp, _MAX_API_BYTES)
                return parse_sha256_text(raw)
    except Exception:
        return ""
    return ""


def download_installer(
    version: str,
    dest: Path,
    *,
    progress: Callable[[int], None] | None = None,
    min_bytes: int = 5_000_000,
) -> Path:
    """인스톨러 다운로드. ``progress(pct 0-100)`` 선택."""
    session = secure_session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = installer_url(version)
    try:
        # 허용 호스트 리디렉션만 수동 추적 (allow_redirects=False)
        response = None
        for _ in range(_MAX_DOWNLOAD_REDIRECTS + 1):
            response = session.get(
                url, timeout=_DOWNLOAD_TIMEOUT_S, stream=True, allow_redirects=False
            )
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("Location", "")
                response.close()
                url = urljoin(url, location)
                if not is_allowed_host(url, ALLOWED_DOWNLOAD_HOSTS):
                    raise UnsafeRedirectError(
                        source_url=installer_url(version), target_url=url
                    )
                continue
            break
        if response is None:
            raise OSError("다운로드 리디렉션 한계 초과")
        with response, dest.open("wb") as output:
            response.raise_for_status()
            raw_total = response.headers.get("Content-Length", "")
            try:
                total_size = int(raw_total)
            except ValueError:
                total_size = 0
            if total_size > _MAX_INSTALLER_BYTES:
                raise OSError("다운로드 파일이 허용 크기를 초과했습니다")
            downloaded = 0
            for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > _MAX_INSTALLER_BYTES:
                    raise OSError("다운로드 파일이 허용 크기를 초과했습니다")
                output.write(chunk)
                if progress is not None and total_size > 0:
                    progress(min(100, int(downloaded * 100 / total_size)))
    except (OSError, ValueError, UnsafeRedirectError):
        dest.unlink(missing_ok=True)
        raise
    if not dest.exists() or dest.stat().st_size < min_bytes:
        dest.unlink(missing_ok=True)
        raise OSError("다운로드 파일이 비정상적으로 작습니다")
    return dest


def verify_installer(path: Path, expected_hex: str) -> None:
    """SHA256 불일치 시 ValueError."""
    if not expected_hex:
        raise ValueError("검증용 SHA256 이 비어 있습니다")
    actual = file_sha256(path)
    if actual.lower() != expected_hex.lower():
        raise ValueError(f"SHA256 불일치\n기대: {expected_hex.lower()}\n실제: {actual.lower()}")


def launch_silent_installer(installer_path: str | Path) -> None:
    import subprocess
    from pathlib import Path as P

    path = P(installer_path)
    subprocess.Popen(
        [str(path), "/SILENT", "/SUPPRESSMSGBOXES"],
        cwd=str(path.parent),
    )
