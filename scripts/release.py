#!/usr/bin/env python3
"""릴리스 스크립트 — 버전 일괄 갱신 → 테스트 → exe/인스톨러 빌드.

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

※ README.md 의 "### vN.N 새 기능" 섹션은 이번 릴리스의 변경 요약이므로
  스크립트가 자동으로 쓰지 않습니다. 릴리스 전에 직접 추가해 주세요.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
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
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
    )
    if r.returncode != 0:
        sys.exit("테스트 실패 — 릴리스 중단")


def run_build(script: str) -> None:
    print(f"\n==> {script} 실행")
    r = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / script)],
        cwd=ROOT,
    )
    if r.returncode != 0:
        sys.exit(f"{script} 실패 — 릴리스 중단")


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
    print("\n✅ 릴리스 완료 — installer_output\\롤실전코치 Setup v"
          f"{new_version}.exe 를 배포하세요")


if __name__ == "__main__":
    main()
