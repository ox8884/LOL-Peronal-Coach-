# Hextech 리디자인 — 디자인 스펙

- 날짜: 2026-07-14
- 대상: 롤 실전 코치 CustomTkinter GUI 전면 재스타일링
- 방식: A — Design Tokens 모듈 + 커스텀 CTk 컬러 테마 (JSON)
- 범위: 전체 재스타일링 (헤더 + 탭 3 + 셋업 다이얼로그 + 오토컴플릿 드롭다운 + API 도움말)
- 폰트: Malgun Gothic 시스템 폰트 유지

## 1. 목표

현재 앱 디자인은 제네릭 CTk 기본 테마(blue) + 어드혹 그레이 카드 + 이모지 헤더로 "구리다"는 평가를 받는다.
리그 오브 레전드 공식 클라이언트의 **Hextech 무드**(어두운 네이비 베이스 + 골드 액센트 + 헥사딕 블루 보조)를
단일 design tokens 모듈과 CTk 커스텀 컬러 테마로 일관 적용한다.

**목적 (WHY)**: 게이머에게 자연스러운 "LoL 클라이언트 다움" 인상을 주면서 기능/레이아웃 구조는 건드리지 않는다.
**기대 결과 (RESULT)**: 4개 GUI 파일의 색/폰트 하드코딩이 단일 `gui/theme.py` + `assets/hextech.json`으로 수렴하고, 모든 프리미티브가 일관된 Hextech 팔레트를 따른다.

## 2. 아키텍처

### 2.1 새 파일 `src/lol_coach/gui/theme.py` — 단일 디자인 토큰 출처

```python
# (light, dark) 튜플 — CTk appearance_mode 전환 대비
COLORS = {
    "BG_SHELL":         ("#F5F5F0", "#010A13"),  # 윈도우 배경 (가장 어두운 LoL 베이스)
    "BG_PANEL":         ("#FFFFFF", "#0A1428"),  # 카드/섹션 패널 (네이비 틴트)
    "BG_PANEL_RAISED":  ("#E8E8E0", "#1E2328"),  # 행 카드/입력셀
    "BG_TAB":           ("#ECECE4", "#091428"),  # 탭 바 & 스크롤 프레임 배경
    "ACCENT_GOLD":          ("#785A28", "#C8AA6E"),  # 1차 액센트 — 섹션 타이틀/헤어라인
    "ACCENT_GOLD_BRIGHT":   ("#C8AA6E", "#F0E6D2"),  # 강조 텍스트 / 활성 상태
    "ACCENT_HEX":           ("#0397AB", "#0AC8B9"),  # 2차 액센트 — CTA/포커스 링
    "ACCENT_HEX_DEEP":      ("#005A82", "#005A82"),  # 헥사딕 호버 딥
    "TEXT_PRIMARY":     ("#1E2328", "#F0E6D2"),  # 본문 텍스트 (양피지 톤)
    "TEXT_MUTED":       ("#555555", "#A09B8C"),  # 헬퍼/caption
    "BORDER_GOLD":       ("#C8AA6E", "#463714"),  # 1px 헤어라인 보더
    "ROLE_ACTIVE":      ("#0397AB", "#0AC8B9"),  # 포지션 버튼 활성 (헥사딕)
    "ROLE_IDLE":        ("#A29788", "#3C3C41"),  # 포지션 버튼 비활성
    "BTN_LIVE_BG":      ("#2E7D32", "#0A3D0A"),  # "실행 중인 게임 자동 검색" 버튼 (그린 유지)
    "BTN_LIVE_HOVER":   ("#388E3C", "#0E5A0E"),
    "ACCENT_GOOD":      ("#3A8A8A", "#46A0A0"),  # 우위 표시 (헥사딕 틸)
    "ACCENT_WARN":      ("#785A28", "#C8AA6E"),  # 무난/딜레이 — 골드
    "ACCENT_DANGER":    ("#A33A3A", "#BA3B3B"),  # 오류 — 딥 레드 (채도 낮춤)
}

FONTS = {
    "TITLE":    ("Malgun Gothic", 18, "bold"),  # 앱/헤더
    "HEADING":  ("Malgun Gothic", 14, "bold"),  # 섹션 타이틀 (▸ 제거)
    "BODY":     ("Malgun Gothic", 13),          # 입력 라벨/버튼 (기존 FU)
    "SMALL":    ("Malgun Gothic", 12),          # 결과 행 (기존 FB)
    "CAPTION":  ("Malgun Gothic", 11),          # 헬퍼/캡션 (기존 FM)
    "TAB":      ("Malgun Gothic", 14, "bold"),  # 탭 라벨
}

SPACE = {
    "PAD_X": 16, "PAD_Y": 12,
    "GAP_XS": 4, "GAP_SM": 8, "GAP_MD": 12, "GAP_LG": 20,
}

CORNER = {"CARD": 10, "INPUT": 6, "PILL": 16}

def apply_hextech_theme() -> None:
    """앱 진입점에서 ctk.set_default_color_theme(custom_json_path) 호출 — 1회."""
```

### 2.2 `assets/hextech.json` — CTk 커스텀 컬러 테마

CTk 공식 스키마(`{"CTk":{...}, "CTkButton":{...}, "CTkEntry":{...}, "CTkFrame":{...}, "CTkTabview":{...}, "CTkScrollableFrame":{...}}`)를 따르는 JSON 파일.
각 프리미티브의 `fg_color`, `border_color`, `text_color`, `hover_color`를 (light, dark) 튜플 문자열로 정의.
`theme.py`의 `apply_hextech_theme()`이 이 파일을 `ctk.set_default_color_theme()` 인자로 전달.
적용 후 개별 `configure(fg_color=...)` 하드코딩 호출 대부분 제거 가능.

### 2.3 4개 GUI 파일 토큰 치환 패턴

| 파일 | 기존 | 치환 |
|---|---|---|
| `app.py`, `setup_dialog.py`, `api_help.py`, `champ_autocomplete.py` | `FT = ("Malgun Gothic", 18, "bold") ...` 각 파일마다 별도 정의 | `from .theme import FONTS as F, COLORS, SPACE, CORNER` → `F["TITLE"]` 등 사용 |
| `app.py` `_select_role()` | `("#3B8ED0","#1F6AA5")` / `("gray70","gray30")` | `COLORS["ROLE_ACTIVE"]` / `COLORS["ROLE_IDLE"]` |
| `app.py` `_row_frame()` | `("gray90","gray22")` | `COLORS["BG_PANEL_RAISED"]` |
| `app.py` `_render_sr_quick/detail`, 텍스트 색 | `#81C784` / `#FFB74D` / `#E57373` | `COLORS["ACCENT_GOOD"]` / `COLORS["ACCENT_WARN"]` / `COLORS["ACCENT_DANGER"]` |
| `app.py` caption `("gray45","gray60")`, `("gray50","gray60")` | (제각각) | `COLORS["TEXT_MUTED"]` |
| `app.py` `live_btn` `("#2E7D32","#1B5E20")` / `("#388E3C","#2E7D32")` | (하드코딩) | `COLORS["BTN_LIVE_BG"]` / `COLORS["BTN_LIVE_HOVER"]` |
| `app.py` `sr_out` 등 `label_text="결과"` | (제거) | CTkScrollableFrame label_text 제거, `BG_TAB` 배경 |
| `app.py` `_sec` 메서드 — `▸ 제목` 형식 | (이모지/화살표 있음) | 화살표 제거, `F["HEADING"]` 골드 볼드 + 하단 1px `BORDER_GOLD` 헤어라인(CTkFrame height=1) |
| `app.py` `⚡빠른 카운터`, `📋상세 분석`, `🎮실행 중인 게임` 이모지 헤더 | (이모지 + 텍스트) | 이모지 제거, 골드 볼드 텍스트만 — Hextech 절제 톤 |

### 2.4 진입점 연결

- `app.py` 모듈 상단(현재 29~30줄)에서 `ctk.set_appearance_mode("dark")`는 유지하되, 기존 `ctk.set_default_color_theme("blue")`를 `apply_hextech_theme()` 호출로 교체
- `apply_hextech_theme()` 내부에서 `ctk.set_default_color_theme(<assets/hextech.json 경로>)` 실행

## 3. 컴포넌트 디테일

| 컴포넌트 | 현재 | Hextech 적용 |
|---|---|---|
| 헤더 | `롤 실전 코치` 볼드 + 회색 상태 | 타이틀 `ACCENT_GOLD_BRIGHT`(dark), 상태 텍스트 `TEXT_MUTED`, 헤더 하단 1px 골드 헤어라인 `CTkFrame(height=1, fg_color=BORDER_GOLD)` |
| 탭 바 | 기본 CTkTabview blue | 활성 탭 텍스트 `ACCENT_GOLD_BRIGHT`, 비활성 `TEXT_MUTED`, 탭 하단 2px 헥사딕 블루 인디케이터 (CTkTabview 자체 인디케이터 색 = `ACCENT_HEX`) |
| 섹션 타이틀 (`_sec`) | `▸ 제목` | 화살표 제거, 골드 볼드 제목(`F["HEADING"]`/`ACCENT_GOLD_BRIGHT`) + 하단 1px `BORDER_GOLD` 헤어라인 |
| 빠른 카운터 카드 / 상세 카드 | `corner_radius=10` + transparent | `BG_PANEL` + `CORNER_CARD` + `BORDER_GOLD` 헤어라인 보더 (`border_width=1`, `border_color=BORDER_GOLD`) |
| 행 카드 (`_row_frame`) | `("gray90","gray22")` | `BG_PANEL_RAISED` + `CORNER_CARD` + 좌측 3px 골드 액센트 바 (`CTkFrame(width=3, fg_color=ACCENT_GOLD)` pack side="left") |
| 역할 버튼 | 회색 사각형 | `CORNER_PILL` 필 버튼, 활성 `ROLE_ACTIVE`(헥사딕), 비활성 `ROLE_IDLE`, 활성 시 텍스트 검정/펄 |
| CTA / 빠른 추천 버튼 | 기본 파란 CTk | `ACCENT_HEX`(헥사딕 블루), 호버 `ACCENT_HEX_DEEP`, 텍스트 `BG_SHELL`(dark) |
| 실행 중인 게임 자동 검색 버튼 | `#2E7D32` 그린 | `BTN_LIVE_BG` 토큰 (색 유지, "LIVE" 컨벤션) |
| 입력창 | 기본 CTkEntry 블루 포커스 | 포커스 링 `ACCENT_HEX`, `CORNER_INPUT`(6, 살짝 날카로움), `BG_PANEL_RAISED` 배경, `BORDER_GOLD` 보더 `border_width=1` |
| 결과 라벨 색 | `#81C784`/`#FFB74D`/`#E57373` | `ACCENT_GOOD`(=`#46A0A0` dark, 헥사딕 틸) / `ACCENT_WARN`(=`#C8AA6E` dark, 골드) / `ACCENT_DANGER`(=`#BA3B3B` dark, 딥 레드) — 채도 낮춰 팔레트 통합 |
| 헬퍼/캡션 | 제각각 gray 튜플 | `TEXT_MUTED` |
| 스크롤 프레임 (`sr_out` 등) | `label_text="결과"` | label_text 제거, `BG_TAB` 배경, `CORNER_CARD` |
| 이모지 헤더 텍스트 (`⚡`, `📋`, `🎮`) | 이모지 + 텍스트 | 이모지 제거, 골드 볼드 텍스트만 (Hextech 절제 톤) |

## 4. 데이터 흐름 · 에러 · 테스트

### 4.1 데이터 흐름 (변경 없음)

`RiotClient` / `UGGClient` / `DataDragon` / `MayhemCoach` / `CounterClient` 호출 부분은 전혀 손대지 않는다. 토큰 참조만 교체.

### 4.2 에러 처리

- HTTP/입력 에러 메시지 색: `ACCENT_DANGER`(`#BA3B3B` dark)
- `_busy_set`의 `"분석 중…"` 텍스트 유지 — 폰트/색만 토큰 적용
- `messagebox`는 시스템이라 톤 불가 → 그대로

### 4.3 테스트 전략

1. **기존 테스트** (`tests/test_gui_threading.py`) 통과 유지 — 위젯 id, 레이아웃 구조, 메서드 이름 안 건드림
2. **새 단위 테스트** `tests/test_theme.py`:
   - `theme.py` import 시 `COLORS`/`FONTS`/`SPACE`/`CORNER` 모든 키 존재
   - 각 색 토큰 (light, dark) 튜플 길이 2, hex `#RRGGBB` 포맷
   - `apply_hextech_theme()` CTk 가상 루트에서 호출 시 예외 없음
3. **시각적 확인**: `gui_main.py` 실행 후 3개 탭 + 셋업 다이얼로그 + 오토컴플릿 드롭다운 눈으로 스크린샷 검수 (수동 PoC)

## 5. 명시적 범위 밖 (OUT OF SCOPE)

- 헥사곤 패턴 배경 / 글로우 효과 / 캔버스 드로잉 / 완전 커스텀 위젯 ( → 향후 C 옵션)
- 폰트 파일 번들 (Malgun Gothic 시스템 폰트 유지)
- 기능 추가/레이아웃 변경 / 위젯 재배치 / 탭 순서 변경
- 아이콘 에셋(`assets/icon.ico`, `assets/icon.png`) 변경
- 앱 윈도우 기본 크기(`1040x860`) / minsize 변경

## 6. 정지 조건 (완료 기준)

- [ ] `src/lol_coach/gui/theme.py` 존재 + `COLORS`/`FONTS`/`SPACE`/`CORNER` 모든 키 정의
- [ ] `assets/hextech.json` CTk 스키마 준수 + 6개 프리미티브(CTk/Button/Entry/Frame/Tabview/ScrollableFrame) 정의
- [ ] `app.py`, `setup_dialog.py`, `api_help.py`, `champ_autocomplete.py`에서 `FT`/`FU`/`FB`/`FM`/`FS` 상수 정의 제거
- [ ] `app.py`에서 `set_default_color_theme("blue")` 제거, `apply_hextech_theme()` 호출 추가
- [ ] `app.py` `_sec` 메서드: `▸` 제거 + 골드 헤어라인 추가
- [ ] `app.py` 헤더/탭/card/버튼/입력창/라벨 모두 토큰 참조 + `⚡📋🎮` 이모지 제거
- [ ] `tests/test_theme.py` 작성 + 통과
- [ ] 기존 `tests/test_gui_threading.py` 통과 유지
- [ ] `gui_main.py` 실행 — 3개 탭 + 다이얼로그 시각적 확인 (눈 검수)
- [ ] `lsp_diagnostics` 변경 파일 모두 error 없음