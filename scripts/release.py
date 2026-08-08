#!/usr/bin/env python3
"""릴리스 스크립트 — 버전 일괄 갱신 → 테스트 → 빌드 → GitHub Release.

사용법:
  python scripts/release.py --version 1.5.0          # 전체 릴리스
  python scripts/release.py --version 1.5.0 --dry-run  # 변경 대상만 출력
  python scripts/release.py --version 1.5.0 --skip-build  # 버전만 갱신

동작:
  1. 버전 문자열을 소스/인스톨러/문서 전반에 반영
     - pyproject.toml, src/lol_coach/__init__.py
     - installer/롤실전코치.iss (MyAppVersion → 출력 파일명도 자동)
     - docs/features.html (상단 배지 + 푸터), BUILD.md
  2. pytest 로 전체 회귀 확인
  3. build_exe.ps1 → build_installer.ps1 순으로 빌드
  4. git 태그 생성·푸시 → GitHub Release 생성 → 인스톨러 asset 업로드
     (인증은 git credential 저장 토큰 사용, 토큰은 화면에 출력하지 않음)

※ README.md 의 "### vN.N 새 기능" 섹션은 이번 릴리스의 변경 요약이므로
  스크립트가 자동으로 쓰지 않습니다. 릴리스 전에 직접 추가해 주세요.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _replace_in_file(path: Path, old: str, new: str) -> bool:
    """파일에서 old → new 치환. 바뀐 게 있으면 True."""
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new), encoding="utf-8")
    return True


def bump_version(new_version: str, *, dry_run: bool = False) -> None:
    """버전 문자열을 모든 릴리스 지점에 반영한다."""
    # 현재 버전은 __init__.py 에서 읽는다
    init = ROOT / "src" / "lol_coach" / "__init__.py"
    m = re.search(r'__version__ = "([^"]+)"', init.read_text(encoding="utf-8"))
    if not m:
        sys.exit("ERROR: src/lol_coach/__init__.py 에서 버전을 찾을 수 없습니다")
    old_version = m.group(1)

    if old_version == new_version:
        print(f"이미 {new_version} 입니다 — 변경할 내용 없음")
        return

    targets = [
        (ROOT / "pyproject.toml", f'version = "{old_version}"', f'version = "{new_version}"'),
        (ROOT / "src" / "lol_coach" / "__init__.py", f'__version__ = "{old_version}"', f'__version__ = "{new_version}"'),
        (ROOT / "installer" / "롤실전코치.iss", f'#define MyAppVersion   "{old_version}"', f'#define MyAppVersion   "{new_version}"'),
        (ROOT / "docs" / "features.html", f">v{old_version}<", f">v{new_version}<"),
        (ROOT / "docs" / "features.html", f"롤 실전 코치 v{old_version}", f"롤 실전 코치 v{new_version}"),
        (ROOT / "BUILD.md", f"v{old_version}", f"v{new_version}"),
    ]

    changed = 0
    for path, old, new in targets:
        if not path.exists():
            print(f"  SKIP (없음): {path.relative_to(ROOT)}")
            continue
        if dry_run:
            if old in path.read_text(encoding="utf-8"):
                print(f"  변경 예정: {path.relative_to(ROOT)}  ({old} → {new})")
                changed += 1
            continue
        if _replace_in_file(path, old, new):
            print(f"  변경: {path.relative_to(ROOT)}")
            changed += 1
        else:
            print(f"  그대로: {path.relative_to(ROOT)}  (패턴 없음: {old!r})")

    if changed == 0 and not dry_run:
        print("변경된 파일이 없습니다 — 버전 패턴을 확인해 주세요")
        return

    print(f"\n버전 {old_version} → {new_version} ({changed}개 파일)")
    if dry_run:
        print("(--dry-run 이므로 실제 변경 없음)")
    else:
        print("README.md 의 '### 새 기능' 섹션을 이번 변경 내용으로 갱신하세요.")


def run_tests() -> None:
    print("\n==> pytest 실행")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    for attempt in (1, 2):
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode == 0:
            return
        if attempt == 1:
            # Windows Tk 초기화가 간헐적으로 실패하는 일시 오류 — 1회 재시도
            print("  테스트 실패 — 일시 오류일 수 있어 1회 재시도합니다...")
            import time

            time.sleep(2)
    sys.exit("테스트 실패 — 릴리스 중단")


def run_build(script: str) -> None:
    print(f"\n==> {script} 실행")
    r = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / script)],
        cwd=ROOT,
    )
    if r.returncode != 0:
        sys.exit(f"{script} 실패 — 릴리스 중단")

def github_release(new_version: str) -> None:
    """GitHub Release 생성 + 인스톨러 asset 업로드 (git credential 토큰 사용)."""
    import json

    print("\n==> GitHub Release 생성")
    # git credential 에서 토큰 읽기 (출력에 노출하지 않음)
    cred = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    token = ""
    for line in (cred.stdout or "").splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1]
            break
    if not token:
        sys.exit("GitHub 토큰을 가져올 수 없습니다 — git credential 설정을 확인하세요")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    repo = "ox8884/LOL-Peronal-Coach-"
    tag = f"v{new_version}"

    # 태그 푸시
    subprocess.run(["git", "tag", tag], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "push", "origin", tag], cwd=ROOT, capture_output=True)

    # 릴리스 생성 (이미 있으면 재사용)

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases",
        data=json.dumps(
            {
                "tag_name": tag,
                "name": f"롤 실전 코치 {tag}",
                "body": (
                    f"{tag} 릴리스\n\n"
                    "## 📥 다운로드\n"
                    "아래 **Assets** 에서 `LOL-Coach-Setup-"
                    f"{new_version}.exe` 를 받아 실행하세요.\n\n"
                    "## 🔒 보안 안내\n"
                    "- 설치 파일에는 API 키가 **포함되지 않습니다**\n"
                    "- 첫 실행 시 Riot API 키 입력 → `.env` 가 자동 생성 (PC에만 저장)\n"
                    "- 설치본 설정/캐시: `%LOCALAPPDATA%\\롤실전코치`"
                ),
            },
        ).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # 422 = 이미 존재 (같은 태그로 재실행) → 태그로 조회해 재사용
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {}
        if exc.code != 422:
            sys.exit(f"릴리스 생성 실패: {json.dumps(body, ensure_ascii=False)[:300]}")
        req2 = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req2) as resp2:
                release = json.loads(resp2.read())
        except urllib.error.HTTPError as exc2:
            sys.exit(f"릴리스 조회 실패: {exc2.code} {exc2.reason}")
    release_id = release["id"]
    print(f"  release: {release['html_url']}")

    # 인스톨러 업로드 (영문 파일명 — GitHub asset 한글명 불안정)
    installer = ROOT / "installer_output" / f"롤실전코치 Setup v{new_version}.exe"
    if not installer.exists():
        sys.exit(f"인스톨러 없음: {installer} — build_installer.ps1 결과를 확인하세요")
    asset_name = f"LOL-Coach-Setup-v{new_version}.exe"
    print(f"  asset 업로드: {asset_name} ({installer.stat().st_size / 1e6:.1f} MB)")

    def _upload_asset(name: str, data: bytes, content_type: str) -> None:
        upload = urllib.request.Request(
            f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets"
            f"?name={urllib.parse.quote(name)}",
            data=data,
            headers={**headers, "Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(upload) as resp:
                asset = json.loads(resp.read())
            print(f"  다운로드: {asset['browser_download_url']}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if "already_exists" in body:
                print(f"  asset 이미 존재 — 건너뜀: {name}")
            else:
                sys.exit(f"asset 업로드 실패 ({name}): {body[:300]}")

    with open(installer, "rb") as fh:
        raw = fh.read()
    _upload_asset(asset_name, raw, "application/octet-stream")

    # SHA256 사이드카 (앱 자동 업데이트 무결성 검증용)
    import hashlib

    digest = hashlib.sha256(raw).hexdigest()
    sha_name = f"{asset_name}.sha256"
    sha_body = f"{digest}  {asset_name}\n".encode()
    print(f"  sha256: {digest}")
    _upload_asset(sha_name, sha_body, "text/plain")


def main() -> None:
    ap = argparse.ArgumentParser(description="롤 실전 코치 릴리스 — 버전 갱신 + 테스트 + 빌드")
    ap.add_argument("--version", required=True, help="새 버전 (예: 1.5.0)")
    ap.add_argument("--dry-run", action="store_true", help="변경 대상만 출력하고 종료")
    ap.add_argument("--skip-build", action="store_true", help="빌드 건너뛰기 (버전 갱신만)")
    args = ap.parse_args()

    new_version = args.version.strip()
    if not VERSION_RE.match(new_version):
        sys.exit(f"버전 형식 오류: {new_version!r} — X.Y.Z 형식이어야 합니다")

    bump_version(new_version, dry_run=args.dry_run)
    if args.dry_run:
        return

    run_tests()
    if args.skip_build:
        print("\n완료 (빌드 건너뜀)")
        return

    run_build("build_exe.ps1")
    run_build("build_installer.ps1")
    print("\n✅ 빌드 완료 — GitHub Release 업로드 진행")
    github_release(new_version)
    print("\n✅ 릴리스 완료 — https://github.com/ox8884/LOL-Peronal-Coach-/releases/latest 에서 배포")


if __name__ == "__main__":
    main()
