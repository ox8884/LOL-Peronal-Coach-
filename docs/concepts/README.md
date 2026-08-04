# 롤 실전 코치 — GUI 리디자인 (v1.6, "다크 리그 에디션")

> 기능 100% 유지 + 스킨 레벨 리디자인. CustomTkinter 커스텀 테마 JSON + 공통 컴포넌트로 구현.

## 디자인 방향: "다크 리그 에디션"

LoL 클라이언트의 정제된 다크 팔레트 + 전술 코칭 도구의 정보 밀도.
기존 CTk 기본 블루 테마 → 딥 네이비 + 리그 골드 액센트.

## 디자인 토큰

### 색상

| 토큰 | 값 | 용도 |
|---|---|---|
| `bg` | `#0A0E14` | 창 배경 |
| `panel` | `#121A24` | 서브 패널 |
| `card` | `#16202C` | 카드 표면 |
| `row` | `#18232F` | 결과 행 카드 |
| `border` | `#1E2A3A` | 카드/입력 테두리 |
| `gold` | `#C8AA6E` | 메인 액센트 (버튼/탭/섹션 바) |
| `gold_hover` | `#DCC08A` | 골드 호버 |
| `blue` | `#4DA3FF` | 정보 (A등급) |
| `green` | `#31C48D` | 성공/승리 (B등급) |
| `red` | `#F05252` | 위험/패배 (C등급) |
| `purple` | `#A78BFA` | ARAM 마법 포인트 |
| `tier_s` | `#FFD700` | S 등급 칩 |
| `text` | `#C9D4E0` | 본문 |
| `text_dim` | `#7B8BA0` | 라벨/보조 |

### 타이포그래피

| 용도 | 크기/굵기 |
|---|---|
| 앱 타이틀 | 20px Bold (골드 도트 로고 +) |
| 섹션 타이틀 | 15px Bold + 3px 골드 액센트 바 |
| 본문 | 13px |
| 라벨 | 12px / 11px |
| 등급 칩 | 10px Bold |

### 컴포넌트

- **카드**: radius 10~12, 1px 보더, 패딩 16
- **버튼 변형**: primary=골드 채움+다크 텍스트 / secondary=다크 패널 / tertiary=입력 배경 / success=초록 / purple=보라
- **탭**: 선택=골드 채움+다크 텍스트(굵게), 비선택=다크+연골드 (CTk 6.x 내부 버튼 개별 지정)
- **등급 칩**: S/A/B/C 라운드 칩 (골드/블루/그린/레드) — 카운터 GD@15, 증강 티어
- **입력칸**: `#0D1520` + 1px 보더

## 구현 위치

| 파일 | 내용 |
|---|---|
| `src/lol_coach/gui/theme.json` | CTk 커스텀 컬러 테마 (팔레트 전체) |
| `src/lol_coach/gui/components.py` | 토큰 상수 + `btn()`/`tier()`/`tier_chip()`/`ctk_label()` |
| `src/lol_coach/gui/app.py` | 모든 하드코딩 색상 → 토큰, `_sec` 골드 바, 행 카드, 등급 칩, 탭 스타일 |
| `src/lol_coach/gui/widget.py` | 미니 위젯 — 골드 상단 라인 + 패널 바디 |
| `src/lol_coach/gui/setup_dialog.py` / `tooltip.py` / `api_help.py` / `champ_autocomplete.py` | 색상 토큰 적용 |
| `lol_coach.spec` / `pyproject.toml` | theme.json 패키징 (PyInstaller datas + package-data) |

## 검증

- pytest 전체 106개 통과 (기능 무변경 확인)
- ruff 통과, `compileall` 통과
- 실제 GUI 실행 → 스크린샷 `05_after_impl.png` (딥 네이비 배경·골드 탭/버튼·보더 카드 확인)
- 결과 렌더링 (카운터 행 + S/A/B/C 칩 + 골드 섹션 바) 실화면 확인

## 화면별 컨셉 이미지

| 파일 | 화면 |
|---|---|
| `01_sr_tab.jpg` | 소환사의 협곡 탭 (메인) — 컨셉 |
| `02_stats_tab.jpg` | 내 전적 탭 — 컨셉 |
| `03_aram_tab.jpg` | ARAM 아수라장 탭 — 컨셉 |
| `04_widget.jpg` | 미니 위젯 — 컨셉 |
| `05_after_impl.png` | **구현 후 실제 앱 스크린샷** |
