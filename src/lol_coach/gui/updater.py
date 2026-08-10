"""앱 내 자동 업데이트 — 다운로드 · SHA256 검증 · 인스톨러 실행.

GitHub Release 자산:
  - LOL-Coach-Setup-v{ver}.exe
  - LOL-Coach-Setup-v{ver}.exe.sha256  (필수)
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

REPO = "ox8884/LOL-Peronal-Coach-"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/download"


def version_tuple(v: str) -> tuple[int, ...]:
    """'1.5.3' / 'v1.5.3' → (1,5,3)."""
    return tuple(
        int(x) for x in re.split(r"[.-]", v.strip().lstrip("vV")) if x.isdigit()
    )


_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def is_valid_version(v: str) -> bool:
    """릴리스 태그로 안전한 형식인지 (숫자·점만 — 경로 조작 방지)."""
    return bool(_VERSION_RE.match(v.strip()))


# GitHub API/자산 응답 크기 상한 (blitz 클라이언트와 동일한 방어)
_MAX_API_BYTES = 2 * 1024 * 1024
_MAX_INSTALLER_BYTES = 250 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_DOWNLOAD_TIMEOUT_S = 60.0


def fetch_latest_tag(timeout: float = 8.0) -> str:
    """최신 릴리스 태그 (앞에 v 없음). 실패 시 빈 문자열."""
    import json

    with urlopen(RELEASES_API, timeout=timeout) as resp:
        raw = resp.read(_MAX_API_BYTES + 1)
    if len(raw) > _MAX_API_BYTES:
        return ""
    data = json.loads(raw)
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
    try:
        with urlopen(sha256_url(version), timeout=timeout) as resp:
            raw = resp.read(_MAX_API_BYTES + 1)
        if len(raw) > _MAX_API_BYTES:
            return ""
        return parse_sha256_text(raw.decode("utf-8", errors="replace"))
    except Exception:
        return ""


def download_installer(
    version: str,
    dest: Path,
    *,
    progress: Callable[[int], None] | None = None,
    min_bytes: int = 5_000_000,
) -> Path:
    """인스톨러 다운로드. ``progress(pct 0-100)`` 선택."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = installer_url(version)
    try:
        with urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as response, dest.open("wb") as output:
            raw_total = response.headers.get("Content-Length", "")
            try:
                total_size = int(raw_total)
            except ValueError:
                total_size = 0
            if total_size > _MAX_INSTALLER_BYTES:
                raise OSError("다운로드 파일이 허용 크기를 초과했습니다")
            downloaded = 0
            while block := response.read(_DOWNLOAD_CHUNK_BYTES):
                downloaded += len(block)
                if downloaded > _MAX_INSTALLER_BYTES:
                    raise OSError("다운로드 파일이 허용 크기를 초과했습니다")
                output.write(block)
                if progress is not None and total_size > 0:
                    progress(min(100, int(downloaded * 100 / total_size)))
    except (OSError, ValueError):
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
        raise ValueError(
            f"SHA256 불일치\n기대: {expected_hex.lower()}\n실제: {actual.lower()}"
        )


def launch_silent_installer(installer_path: str | Path) -> None:
    import subprocess
    from pathlib import Path as P

    path = P(installer_path)
    subprocess.Popen(
        [str(path), "/SILENT", "/SUPPRESSMSGBOXES"],
        cwd=str(path.parent),
    )
