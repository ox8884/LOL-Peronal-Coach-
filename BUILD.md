# 빌드 · 설치 프로그램 가이드

## 한 줄 — 설치 프로그램까지

```powershell
cd C:\Users\hyj53\lol-coach
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

결과:

| 파일 | 경로 |
|------|------|
| 앱 (포터블) | `dist\롤실전코치.exe` |
| **설치 프로그램** | `installer_output\롤실전코치 Setup v1.6.90.exe` |


---

## 릴리스 절차 (기능 추가 후) — 스크립트 한 방

기능/수정을 반영할 때마다 버전을 올리고 빌드 + 문서를 갱신합니다:

```powershell
# 1) README.md 의 "### vN.N 새 기능" 섹션에 이번 변경 요약을 먼저 적어 주세요
#    (스크립트는 이 섹션을 자동으로 쓰지 않습니다)

# 2) 릴리스 실행 — 버전 갱신 → 테스트 → 빌드 → GitHub Release(태그+인스톨러 업로드)까지 전부
python scripts\release.py --version 1.5.0
```

| 단계 | 스크립트가 하는 일 |
|------|-------------------|
| 1 | `pyproject.toml` / `src\lol_coach\__init__.py` 버전 갱신 |
| 2 | `installer\롤실전코치.iss` 버전 갱신 (출력 파일명도 자동) |
| 3 | `docs\features.html` 배지·푸터, `BUILD.md` 버전 갱신 |
| 4 | pytest 전체 회귀 (실패 시 중단) |
| 5 | `build_exe.ps1` → `build_installer.ps1` 순차 빌드 |
| 6 | git 태그 `vX.Y.Z` 생성·푸시 → GitHub Release 생성 → `LOL-Coach-Setup-vX.Y.Z.exe` asset 업로드 (인증: git credential) |

보조 옵션:
- `--dry-run` — 변경 대상만 출력 (실제 변경 없음)
- `--skip-build` — 버전 갱신 + 테스트까지만 (빌드·릴리스는 나중에)

---

## exe 만 빌드

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

결과: `dist\롤실전코치.exe` (~26MB)

### 수동 명령어

```powershell
cd C:\Users\hyj53\lol-coach
pip install -r requirements.txt
pip install pyinstaller pillow
python scripts\make_icon.py
$env:PYTHONPATH = "src"
python -m PyInstaller --noconfirm --clean lol_coach.spec
```

---

## 설치 프로그램 (Inno Setup)

### 사전 준비

1. **Inno Setup 6** 설치
   - https://jrsoftware.org/isinfo.php
   - 또는: `winget install JRSoftware.InnoSetup`
2. **exe 빌드 완료** (`dist\롤실전코치.exe` 존재)

### 한 줄 빌드 (exe + Setup)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

### exe 이미 있을 때 Setup 만

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipExe
```

### 수동 — ISCC 로 컴파일

```powershell
cd C:\Users\hyj53\lol-coach

# Inno Setup 설치 경로 예
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" ".\installer\롤실전코치.iss"
```

출력: `installer_output\롤실전코치 Setup v1.6.90.exe`

### .iss 스크립트 위치

- `installer\롤실전코치.iss` — 설치 정의
- `installer\info_before.txt` — 마법사 “정보” 페이지 설명

### 설치 프로그램 기능

| 항목 | 내용 |
|------|------|
| 기본 경로 | `C:\Program Files\롤실전코치` (사용자 변경 가능) |
| 바로가기 | 시작 메뉴 + 바탕화면(선택) |
| 완료 후 실행 | 체크박스 (기본 ON) |
| 제거 | 제어판 / 시작 메뉴 “제거” |
| 마법사 설명 | 개인 LoL 코칭 툴 소개 |

---

## 실행 · 데이터 위치

1. API 키 없으면 초기 설정 창
2. **설정 저장**
   - 포터블(쓰기 가능 폴���): exe 옆 `.env`
   - Program Files 설치: `%LOCALAPPDATA%\롤실전코치\.env`
3. **아이콘 캐시**: 같은 데이터 폴���의 `cache\icons\`
   - 챔피언·아이템 아이콘은 Data Dragon에서, 증강 아이콘은 카탈로그 후보 URL에서 다운로드합니다.
   - 이미지는 다운로드 직후 PNG/JPEG/GIF/WEBP 매직 바이트와 해상도(≥128px)를 검증합니다.
   - 검증에 실패하거나 HTML 오류 페이지가 날아오면 저장하지 않고, 이미 캐시된 `last_known_good` 이미지가 있으면 그것을 재사용합니다.
   - 파일이 깨지면 다음 요청 때 자동으로 다시 받습니다.

## ARAM Mayhem 데이터 점검

릴리스 전 카탈로그 상태를 확인하려면:

```powershell
python scripts\refresh_aram_mayhem_data.py
```

- 기본적으로 `src/lol_coach/data/aram_mayhem_augments.json`을 검사합니다.
- 스키마 버전, ID·이름·등급 유효성, 중복을 확인합니다.
- 모든 증강에 **≥128 px 후보 이미지**가 있는지 검사합니다.
- `--patch 16.15`로 현재 Blitz 기대 패치를 지정할 수 있습니다.
- `--require-full-coverage` (기본 `true`): 이미지 후보가 없으면 비제로 종료합니다.
- `--allow-community-only` (기본 `true`): Riot/Wiki 자동 검증이 어려울 때 arammayhem.com 커뮤니티 자산을 정확한 후보로 허용합니다.

이 스크립트는 이미지 URL을 생성하지 않습니다. 기존 카탈로그의 출처와 해상도 제약만 검증합니다.

## Blitz ARAM-Mayhem 챔피언 빌드 갱신

Blitz의 챔피언별 `/aram-mayhem` 페이지에서 완성 아이템 코어 순서를 전부 다시 수집합니다:

```powershell
python scripts\refresh_blitz_aram_builds.py --patch 16.15
```

- Data Dragon의 실제 챔피언 키 173개를 대상으로 실행합니다.
- 각 페이지의 `완성 아이템` 순서와 Blitz CDN 아이콘 URL을 `blitz_aram_builds.json`에 저장합니다.
- 하나라도 실패하면 기존 패키지를 덮어쓰지 않고 비제로 종료합니다.

---

## 배포 시 참고

- 배포 파일: **`롤실전코치 Setup v1.6.90.exe`** 하나만 있으면 됨
- 또는 포터블로 `dist\롤실전코치.exe` 만 복사
- `.env` 에 API 키가 있으므로 **공유하지 마세요**
- Windows Defender가 서명 없는 exe를 처음 한 번 경고할 수 있음
- 인터넷 필요 (Riot API · Blitz.gg · Data Dragon)
- 비공식 개인 도구 (Riot Games 와 무관)
