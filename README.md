# LoL Personal Coach CLI

Riot Match API로 최근 전적을 분석하고, [u.gg](https://u.gg) 현재 패치 메타 빌드(룬/스킬/아이템/승률)를 가져와 **맞춤 코칭**을 출력하는 Python CLI/GUI입니다.


[![Release](https://img.shields.io/badge/릴리스-v1.4.1-3B8ED0?logo=github)](https://github.com/ox8884/LOL-Peronal-Coach-/releases/latest)
[![Download](https://img.shields.io/badge/⬇%20인스톨러%20다운로드-27.6MB-81C784)](https://github.com/ox8884/LOL-Peronal-Coach-/releases/latest)

> **설치 파일은 [Releases](https://github.com/ox8884/LOL-Peronal-Coach-/releases/latest) 페이지에서 받을 수 있습니다.**
> `.env`(API 키)는 설치 파일에 포함되지 않으며, 첫 실행 시 입력하면 자동 생성됩니다.
> 📄 **기능 소개 페이지**: [**롤 실전 코치 — 기능 가이드**](https://ox8884.github.io/LOL-Peronal-Coach-/features.html) — 브라우저에서 바로 열어 보는 전체 기능 가이드 (GitHub Pages 렌더링)

## Features

1. **Riot ID → PUUID + 최근 N게임 분석** (KDA, CS, 승률, 포지션, 챔프별 성적, **모드별 구분**)
2. **현재 게임 중인지 확인** (Spectator V5)
3. **챔피언 메타 빌드** — Summoner's Rift 포지션 **또는 ARAM / ARAM Mayhem** (u.gg 실시간 파싱)
4. **내 최근 해당 챔프 플레이 vs 메타 비교** + 자연어 조언 (`--mode aram` 지원)


### v1.5 새 기능

- **⬆ 자동 업데이트 알림** — 앱 시작 시 GitHub 최신 릴리스 확인, 새 버전이 있으면 상태바에 안내
- **📈 타임라인 복기** — 경기 복기에 15분 내 골드 · 첫 킬/포탑 · 용/바론/전령/공허유충 처치 타이밍 추가 (Match V5 Timeline)
- **📌 미니 위젯 개선** — 위젯 클릭 시 메인 창 복귀 + 📋 복사 버튼 (인게임에서 바로 활용)
- **🖼 아이콘 버전 영속화** — Data Dragon 버전을 캐시에 저장, 오프라인에도 마지막 성공 버전 사용 (신규 챔피언 아이콘 보존)
- **🧪 GUI 테스트 안정화** — Tk 이미지 네임스페이스 충돌 제거로 flaky 테스트 수정
- **📦 빌드 안정화** — PyInstaller hiddenimports 보강 (함수 내 import 모듈 누락 방지)

### v1.5.1 개선

- **📈 타임라인 디스크 캐시** — 복기 타임라인도 `cache/timelines/`에 저장, 재조회 시 API 재호출 없음 (정리 규칙 포함)
- **🛡 단일 인스턴스** — exe 중복 실행 시 "이미 실행 중" 경고 후 종료 (LCU/워처 중복 폴링 방지)
- **🔢 경기 수 선택** — 전적 탭에서 최근 5~50경기 드롭다운으로 선택 (기존 15경기 고정)
- **🧹 빌드 정리** — 빈 루트 `data/` 참조 제거 (패키징은 `src/lol_coach/data`만)

### v1.5.2 개선

- **🗑 프로필 삭제 버튼** — 전적 탭에서 저장된 프로필을 목록에서 바로 제거 (Riot 계정·전적엔 영향 없음)
- **📄 로그 파일 저장** — `logs/lol_coach.log`에 기록 (설치본 문제 진단 시 이 파일 공유)
- **🪟 창 크기/위치 기억** — 닫을 때 `ui.json`에 저장, 다음 실행 시 복원
- **🔁 릴리스 안정화** — 테스트가 Windows Tk 일시 오류로 실패해도 1회 재시도 (릴리스 중단 방지)
### v1.4 새 기능

- **🎯 LCU 밴픽 연동** — 게임 클라이언트 로컬 API로 **챔피언 셀렉트 중** 적/내 픽을 읽어 바로 카운터 추천 (API 키 불필요, Spectator로 안 되던 밴픽 단계 커버)
- **🔔 게임 종료 자동 복기** — 인게임 자동입력 후 종료를 폴당해 방금 판 복기를 자동 표시
- **🏅 랭크 표시** — League V4 솔로/자유 랭크 티어·LP·승률 (GUI 내 전적 탭 + CLI `profile`)
- **📊 챔피언 풀 진단** — 베이지안 보정 승률 기반 집중/유지/정리 추천 (GUI + CLI `pool`)
- **📌 미니 위젯** — 마지막 분석 요약을 항상 위 창으로 (인게임 중 Alt+Tab 불필요)
- **📁 전적 내보내기** — CSV/JSON 파일로 저장 (GUI 버튼 + CLI `export`)
- **👤 멀티 프로필** — 여러 Riot ID 저장·전환 (`profiles.json`)
- **💡 아이템 툴팁** — 상세 분석 아이템에 마우스를 올리면 가격·설명 표시
- **📷 증강 화면 인식 (베타)** — 아수라장 제시 증강을 화면 캡처로 자동 입력 (`pip install "lol-coach[screen]"`)
- **⚡ 성능** — 매치 상세 병렬 조회 + 디스크 캐시(`cache/matches/`)로 재조회 즉시 완료
- **🔧 로깅** — CLI `-v/--verbose` 또는 `LOL_COACH_DEBUG=1`로 네트워크 진단 로그
- **⌨️ 챔피언 자동완성** — 협곡 탭 7개 입력(적 라이너·내 챔프·정글·서폿·탑·미드·원딜) 한글/영문 자동완성 (Windows IME 조합 문자 지원)
- **🔄 LCU 밴픽 자동 추적** — 밴픽 중 픽이 바뀔 때마다 4초 간격 자동 갱신, ARAM 밴픽은 협곡 탭에서 눌러도 탭 자동 전환
- **🗂 탭별 동시 작업** — 협곡 분석 중에도 전적 로드·ARAM 브리핑 실행 가능 (글로벌 잠금 → 작업별 잠금)
- **📜 결과 히스토리 + 📋 복사** — 최근 20개 결과 복원 버튼, 요약 클립보드 복사 버튼
- **🗂 증강 목록 피커** — 카탈로그 200+종 검색 팝업에서 클릭으로 제시 증강 입력
- **⚡ 시작 시 자동 로드** — 마지막 프로필 전적 자동 로드 + 서버 선택 드롭다운
- **💾 u.gg 디스크 캐시** — 빌드 데이터 영속 저장, 재시작·Cloudflare 차단에도 마지막 빌드 복원
- **🔔 종료 알림** — 게임 종료 시 비프음 + 작업표시줄 플래시, 폴링 간격 45초→15초 단축
- **🧹 캐시 자동 정리** — 매치 캐시 30일 경과분 + 1000개 초과분 자동 삭제
- **⏰ API 키 만료 안내** — 401/403 응답 시 "키 재발급" 안내 (개발 키 24시간 만료)

### Modes

| Mode | Riot queues | u.gg source |
|------|-------------|-------------|
| `summoners_rift` | 400/420/430/440… | `/lol/champions/{champ}/build/{role}` |
| `aram` | 450 ARAM + **2400 ARAM Mayhem** | `/lol/champions/aram/{champ}-aram` |

## Project layout

```
lol-coach/
├── main.py                 # CLI entry
├── gui_main.py             # GUI entry
├── requirements.txt
├── .env.example
├── src/lol_coach/
│   ├── cli.py              # click commands (setup/profile/live/meta/coach/pool/export)
│   ├── config.py           # API key / .env / 멀티 프로필(profiles.json)
│   ├── lcu.py              # LCU lockfile + 챔피언 셀렉트 파싱
│   ├── log.py              # 공통 로깅 (-v/--verbose)
│   ├── riot/               # Account, Match V5(+병렬/캐시), League V4, Spectator
│   ├── ugg/                # u.gg fetch + HTML parse
│   ├── static/             # Data Dragon / 로컬라이저 / 아이콘·증강 카탈로그
│   ├── analysis/           # coach · 복기 · 조합 · 아수라장 · 풀 진단 · 내보내기 · 화면 인식
│   └── gui/                # app · 자동완성 · 미니 위젯 · 툴팁 · 종료 감지 워처
└── tests/
```

## GUI (롤 실전 코치)

```powershell
cd C:\Users\hyj53\lol-coach
$env:PYTHONPATH = "src"
pip install customtkinter
python gui_main.py
```

| 탭 | 기능 |
|----|------|
| **소환사의 협곡** | 적 라이너(+정글/서폿/전체) → 카운터 · 조합 위협 · 용/바론 · 코어+상황템 · 체크리스트 · **LCU 밴픽 불러오기** · 아이템 툴팁 |
| **ARAM 아수라장** | 챔피언 + **게임에서 제시된 증강** → Top5 추천 · 피할 증강 · 칼바람 빌드 · 실전 팁 · **LCU 내 픽 입력** · **화면 증강 인식(베타)** |
| **내 전적** | 내 Riot ID 연동 · 최근 경기 · 챔프별 성적 · **랭크** · **챔프 풀 진단** · **CSV/JSON 내보내기** · **멀티 프로필** · **게임 종료 자동 복기** |

공통: 헤더의 **📌 미니 위젯**으로 마지막 분석 요약을 항상 위 창에 띄울 수 있습니다.

## LCU 밴픽 연동 (신규)

GUI 각 탭의 **🎯 밴픽 (LCU)** 버튼은 게임 클라이언트의 로컬 API(lockfile)를 읽어
**챔피언 셀렉트 중인 픽/밴**을 가져옵니다.

- Riot API 키 없이 동작 (로컬호스트 통신만 사용)
- 협곡 탭: 적 5명 픽 → 포지션 추정(태그 기반, 부정확할 수 있음) + 내 픽/포지션 자동 입력 → 즉시 카운터 추천
- ARAM 탭: 내가 고른 챔피언 자동 입력
- 클라이언트가 꺼져 있거나 밴픽 중이 아니면 안내 메시지만 표시
- lockfile 경로가 기본값(`C:\Riot Games\League of Legends\lockfile`)과 다른 경우
  환경변수 `LOL_LOCKFILE`로 지정

## 화면 증강 인식 (베타)

```powershell
pip install -e ".[screen]"   # mss + numpy
```

ARAM 탭 **📷 화면 인식 (베타)** — 게임 화면을 캡처해 캐시된 증강 아이콘과
적분 이미지 기반 템플릿 매칭(NCC)으로 제시 증강을 찾아 입력칸에 채웁니다.
브리핑을 한 번 실행해 아이콘 캐시를 만든 뒤 사용하세요.
(설치본 exe는 용량 절감을 위해 이 기능이 빠져 있습니다.)



## Setup

```powershell
cd lol-coach
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

`pyproject.toml` 없이 바로 쓰려면:

```powershell
$env:PYTHONPATH = "src"
python main.py setup
```

### Riot API Key

1. https://developer.riotgames.com/ 에서 Development API Key 발급
2. 아래 중 하나:

```powershell
python main.py setup
# 또는
python main.py setup --api-key "RGAPI-...." --riot-id "소환사명#KR1" --platform kr
```

키는 프로젝트 루트 `.env`에 저장됩니다. **개인 키는 24시간마다 만료**됩니다.

## Commands

| Command | Description |
|---------|-------------|
| `setup` | API 키 / 기본 소환사 설정 |
| `test-key` | 키 유효성 검사 |
| `profile` | 최근 전적 분석 (+ 랭크 표시) |
| `live` | 현재 인게임 여부 |
| `meta <champ> -r mid` | u.gg 메타 빌드만 |
| `coach <champ> -r mid` | 메타 + 내 기록 맞춤 코칭 |
| `pool` | 챔피언 풀 진단 (집중/유지/정리) |
| `export` | 최근 전적 CSV/JSON 내보내기 |
| `gui` | 데스크탑 GUI 실행 |

모든 명령은 `-v/--verbose`로 디버그 로그를 켤 수 있습니다 (`lol-coach -v profile`).

### Examples

```powershell
$env:PYTHONPATH = "src"

python main.py setup --api-key "RGAPI-xxx" --riot-id "소환사명#KR1" --platform kr
python main.py test-key
python main.py profile --count 15
python main.py live
python main.py meta Ahri -r mid
python main.py meta Ahri -m aram
python main.py coach Ahri -r mid --lookback 20
python main.py coach Ahri -m aram --lookback 20

# ARAM Mayhem: GUI의 "제시 증강" 칸에 게임에서 보이는 증강을 쉼표 또는 줄바꿈으로 직접 입력
# CLI의 `-m aram`은 일반 ARAM 빌드 조회용이며, 제시 증강 기반 아수라장 브리핑은 GUI에서 제공합니다.
```


## How u.gg data is fetched

1. `cloudscraper`로 Cloudflare를 통과해 챔피언 빌드 페이지 HTML을 가져옵니다.
2. BeautifulSoup으로 **현재 패치, 티어, 승/픽/밴률, 룬(perk-active), 스킬 우선순위/패스, 소환사 주문, 코어/시추에이셔널 섹션**을 파싱합니다.
3. 결과는 기본 5분 캐시됩니다.

> 일부 아이템 아이콘은 클라이언트 사이드 렌더라 HTML에 이름이 비어 있을 수 있습니다. 이 경우 헤더 요약 아이템·부츠 텍스트·u.gg URL을 함께 표시합니다.

## ARAM Mayhem 코칭

### 입력

- 사용자가 **게임 안에서 실제로 제시된 증강 이름**을 쉼표/줄바꿈으로 입력합니다.
- 제시되지 않은 증강은 추천·회피에 포함되지 않습니다.
- 한글/영문/별칭을 모두 인식하며, 중복과 카탈로그에 없는 이름은 별도로 안내합니다.

### 개인화 로직

- 챔피언 성향(`Mage`, `Marksman`, `Assassin`, `Fighter`, `Tank`, `Support`)을 Data Dragon 태그로 판단합니다.
- 제시된 증강 중 **S/A 등급 + 챔프 성향 시너지**를 우선 추천하고, 성향 충돌이나 B등급은 회피로 분류합니다.
- 아이템 빌드는 u.gg ARAM 메타를 우선 사용하고 실패 시 클래식 ARAM 폴팅을 제공합니다.

### 출처

- 증강 데이터: 패키징된 `src/lol_coach/data/aram_mayhem_augments.json` 기준.
- 아이템/스킬 빌드: u.gg ARAM 페이지.
- 팁: Data Dragon 스킬 정보 + 제시된 증강 위주의 조합 해석.

### 이미지

- 증강 아이콘은 **카탈로그에 등록된 정확한 후보 URL**만 사용합니다.
- 우선순위: Riot Data Dragon / Riot 패치 노트 / u.gg / League Wiki / ARAM Mayhem 커뮤니티(arammayhem.com).
- 네트워크 실패·검증 실패 시 이미지 대신 **이름+등급 카드**를 표시합니다.

## Cache

- 챔피언·아이템·증강 아이콘은 Data Dragon/u.gg/커뮤니티에서 받아 **로컬에 캐시**합니다.
- **매치 데이터도 디스크 캐시**(`cache\matches\{match_id}.json`) — 매치 payload는 불변이라
  한 번 받은 경기는 API 재호출 없이 즉시 로드됩니다. (`RiotClient(use_cache=False)`로 해제 가능)
- 캐시 위치: 설치본은 `%LOCALAPPDATA%\롤실전코치\cache\`, 포터블/개발 환경은 exe/프로젝트 옆 `cache\`.
- GUI는 브리핑 생성 시 백그라운드 스레드에서 필요한 아이콘을 프리패치합니다.
- 이전에 성공한 이미지 URL은 `last_known_good` 인덱스로 유지되어, 오프라인/일시 장애 시에도 마지막으로 확인된 아이콘을 보여줍니다.
- 이미지 파일이 깨지면 다음 요청 때 자동으로 다시 받습니다.

## Maintainer check

릴리스 전 카탈로그 상태를 점검하려면:

```powershell
python scripts/refresh_aram_mayhem_data.py
```

u.gg HTML 구조 변경으로 파싱이 깨졌는지 확인하려면:

```powershell
python scripts/check_ugg_health.py
# 정상이면 종료 코드 0, 파싱 이상이면 1 (빌드/ARAM/카운터 3경로 점검)
```

- `data/aram_mayhem_augments.json`의 스키마·중복·ID·등급 유효성을 검사합니다.
- 모든 증강에 **≥128 px 후보 이미지**가 있는지 확인합니다.
- `--patch 15.x`로 기대 패치를 지정할 수 있습니다.
- `--require-full-coverage` 기본값은 `true`: 이미지 후보가 없는 증강이 있으면 비제로 종료합니다.
- `--allow-community-only` 기본값은 `true`: Riot/Wiki 자동 검증이 어려울 때 arammayhem.com 커뮤니티 자산을 정확한 후보로 허용합니다.

이 스크립트는 **이미지 URL을 새로 만들지 않습니다**. 기존 카탈로그의 내보내기 출처와 해상도 제약만 검증합니다.

## Notes

- 기본 플랫폼: `na1` / routing `americas`
- Rate limit(429) 시 `Retry-After`를 존중합니다.
- u.gg 이용약관·Cloudflare 정책에 유의하세요. 개인/학습 용도로만 사용하세요.

## License

MIT (personal project)
