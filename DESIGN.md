---
name: 롤 실전 코치
description: 보조 모니터에서 2~3초 곁눈으로 읽는 게임 공략본 한 쪽. 이번 판의 답 하나가 가장 크고 가장 진하다.
colors:
  yellow: "#FFD400"
  yellow-hover: "#FFE04D"
  me-row: "#FFF0A3"
  ink: "#111111"
  ink-hover: "#34332D"
  ink-rule: "#4A4943"
  on-ink: "#FFFFFF"
  on-ink-dim: "#C9C7BC"
  bg: "#F1E3A8"
  panel: "#FBF8EE"
  row: "#F2EEDD"
  row-hover: "#E8E2CA"
  border: "#CFCAB6"
  input-bg: "#FFFFFF"
  text: "#23221E"
  text-dim: "#4A483F"
  text-mute: "#5E5C53"
  green: "#0B6B3A"
  green-hover: "#085A30"
  red: "#BB241A"
  red-hover: "#A51F15"
  red-soft: "#B03A2E"
  blue: "#1C57C8"
  blue-soft: "#2C5AA8"
  purple: "#6A35E0"
  purple-hover: "#5527BD"
  warn: "#8A5A00"
  silver: "#C3CAD3"
  rarity-gold: "#F0A800"
  prism: "#B99BFF"
typography:
  display:
    fontFamily: "Black Han Sans, 맑은 고딕"
    fontSize: "84px"
    fontWeight: 400
  headline:
    fontFamily: "Black Han Sans, 맑은 고딕"
    fontSize: "40px"
    fontWeight: 400
  title:
    fontFamily: "Black Han Sans, 맑은 고딕"
    fontSize: "19px"
    fontWeight: 400
  body:
    fontFamily: "맑은 고딕"
    fontSize: "13px"
    fontWeight: 400
  label:
    fontFamily: "맑은 고딕"
    fontSize: "12px"
    fontWeight: 700
  number:
    fontFamily: "Bahnschrift SemiBold Condensed"
    fontSize: "26px"
    fontWeight: 700
rounded:
  none: "0px"
spacing:
  board-margin: "20px"
  section-gap: "18px"
  heading-gap: "6px"
  rule-leaf: "7px"
  rule-heavy: "3px"
  rule-ink: "2px"
  rule-hair: "1px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.ink-hover}"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
  button-secondary-hover:
    backgroundColor: "{colors.row-hover}"
  button-tertiary:
    backgroundColor: "{colors.row}"
    textColor: "{colors.text-dim}"
    rounded: "{rounded.none}"
  button-tertiary-hover:
    backgroundColor: "{colors.row-hover}"
  button-selected:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
  button-selected-hover:
    backgroundColor: "{colors.yellow-hover}"
  button-band:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink-dim}"
    rounded: "{rounded.none}"
  button-band-hover:
    backgroundColor: "{colors.ink-hover}"
  button-success:
    backgroundColor: "{colors.green}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
  button-success-hover:
    backgroundColor: "{colors.green-hover}"
  button-purple:
    backgroundColor: "{colors.purple}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
  button-purple-hover:
    backgroundColor: "{colors.purple-hover}"
  button-danger:
    backgroundColor: "{colors.red}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
  button-danger-hover:
    backgroundColor: "{colors.red-hover}"
  nav-tab:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink-dim}"
    height: "44px"
    padding: "0 20px"
  nav-tab-selected:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.ink}"
  phase-step:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink-dim}"
    height: "28px"
    padding: "0 11px"
  phase-step-current:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.ink}"
  input:
    backgroundColor: "{colors.input-bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "34px"
  chip-rarity-silver:
    backgroundColor: "{colors.silver}"
    textColor: "{colors.ink}"
    height: "24px"
    padding: "0 10px"
  chip-rarity-gold:
    backgroundColor: "{colors.rarity-gold}"
    textColor: "{colors.ink}"
    height: "24px"
    padding: "0 10px"
  chip-rarity-prism:
    backgroundColor: "{colors.prism}"
    textColor: "{colors.ink}"
    height: "24px"
    padding: "0 10px"
  highlight-name:
    backgroundColor: "{colors.yellow}"
    textColor: "{colors.ink}"
    padding: "0 5px"
  answer-block:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.yellow}"
    typography: "{typography.display}"
---

# Design System: 롤 실전 코치

Windows 데스크톱 앱(Python + CustomTkinter)이다. CSS는 없다. 토큰의 원천은 `src/lol_coach/gui/components.py`(색·버튼·모양)와 `src/lol_coach/gui/constants.py`(글꼴)이고, 위 frontmatter는 그 값을 옮겨 적은 것이다. 글자 크기는 100% 배율 기준 픽셀이며 Tk 배율(100·125·150%)에 따라 함께 커진다.

## Overview

**Creative North Star: "공략본"**

게임 공략집의 한 쪽이다. 연한 버터색 판 위에 종이색 낱장이 놓이고, 먹색 띠와 굵은 괘선이 구획을 나눈다. 이번 판의 답 하나가 화면에서 가장 크고 가장 진하다. 진한 노랑은 형광펜이라서, 지금 고를 것에만 칠해진다.

읽는 상황이 형태를 정했다. 사용자는 한 명이고, 게임은 주 모니터에, 이 앱은 1920×1080·100% 배율의 보조 모니터에 떠 있다. 밴픽 30~60초와 판 사이에 2~3초씩 곁눈으로 읽는다. 그래서 답은 왼쪽 먹색 칸에 최대 84px 노란 글씨로 놓이고, 순위는 색이 아니라 크기로 구분되며, 게임 단계(대기·밴픽·게임 중·복기)가 화면을 스스로 넘긴다.

Tk가 못 하는 것이 곧 이 세계의 재료다. 그림자·흐림·그라디언트·위젯 단위 투명이 없으므로 깊이는 판과 낱장 두 겹, 그리고 괘선 굵기로만 만든다. 화면 전환과 상태 변화는 인쇄물처럼 단계 없이 즉시 일어난다. 버려진 것: 어두운 남색 바탕에 네온 강조, 왼쪽 메뉴, 같은 크기의 둥근 카드가 쌓인 전적 사이트 형태, 전환 가능한 스킨 3종.

**Key Characteristics:**
- 판(`ui.BG`)과 낱장(`ui.PANEL`) 두 겹, 그 위에 먹색(`ui.INK`) 띠와 괘선
- 진한 노랑(`ui.YELLOW`)은 답·선택·1순위에만
- 순위는 고정된 크기 단계로 말한다
- 모서리는 직각, 그림자 없음, 움직임 없음
- 상태는 색과 글자를 항상 함께 쓴다
- 팔레트는 하나. 스킨 전환 없음

## Colors

버터색 종이와 먹, 그리고 형광펜 한 자루. 의미색과 희귀도색은 글자와 함께 쓰일 때만 등장한다.

### Primary
- **형광펜 노랑** (`ui.YELLOW`, #FFD400): 답(먹색 칸의 큰 글씨), 선택된 탭·단계·필터 칩(`BTN_SELECTED`), 1순위 이름 뒤 칠, 복기의 "다음 판에 바꿀 한 가지" 줄. hover는 `ui.YELLOW_HOVER`(#FFE04D).
- **연한 형광펜** (`ui.ME_ROW`, #FFF0A3): 여러 줄 가운데 "나"이거나 지금 열어 둔 경기 행. 진한 노랑보다 한 단계 약한 표시다.

### Secondary
- **먹** (`ui.INK`, #111111): 위 56px 띠와 아래 30px 띠, 답이 놓이는 칸, 낱장 머리의 굵은 괘선, 주 버튼, 입력 칸 테두리, 섹션 제목 앞 네모. 낱장 위 강조는 노랑이 아니라 먹이다(`ui.GOLD`는 호환용 이름일 뿐 값은 `INK`).
- **먹 위의 단계** (`ui.INK_HOVER` #34332D, `ui.INK_RULE` #4A4943): 먹색 면 위의 hover와 괘선.
- **먹 위의 글자** (`ui.ON_INK` #FFFFFF, `ui.ON_INK_DIM` #C9C7BC): 띠의 로고·강한 줄은 흰색, 선택되지 않은 탭·도구·보조 줄은 흐린 색.

### Tertiary
- **의미색**: `ui.GREEN`(#0B6B3A) 승·개선, `ui.RED`(#BB241A)·`ui.RED_SOFT`(#B03A2E) 패·악화·오래된 데이터 경고, `ui.BLUE`(#1C57C8)·`ui.BLUE_SOFT`(#2C5AA8) 중립 정보, `ui.PURPLE`(#6A35E0) AI 동작, `ui.WARN`(#8A5A00) 표본 주의. 모두 낱장 위 글자로 쓸 수 있는 진하기다.
- **증강 희귀도 칩**: `ui.SILVER`(#C3CAD3) 실버, `ui.RARITY_GOLD`(#F0A800) 골드, `ui.PRISM`(#B99BFF) 프리즘. 칩 바탕으로만 쓰고 글자는 먹, 칩 안에 이름을 적는다.

### Neutral
- **버터색 판** (`ui.BG`, #F1E3A8): 창 바탕. 사용자가 "노랑을 덜 세게"라고 요청해 진한 노랑 대신 정해진 색이다.
- **종이 낱장** (`ui.PANEL`, #FBF8EE): 내용이 놓이는 면. `ui.CARD`는 같은 값이다.
- **행** (`ui.ROW` #F2EEDD, `ui.ROW_HOVER` #E8E2CA): 낱장 위의 목록 행·타일과 그 hover.
- **가는 괘선** (`ui.BORDER`, #CFCAB6): 행 사이, 낱장 안 구획의 1px 선.
- **입력 바탕** (`ui.INPUT_BG`, #FFFFFF): 입력 칸만 순백이다. 테두리는 먹 1px.
- **글자** (`ui.TEXT` #23221E 본문, `ui.TEXT_DIM` #4A483F 설명, `ui.TEXT_MUTE` #5E5C53 출처·메타): 제목과 이름은 `ui.INK`.

### Named Rules
**형광펜 규칙.** `ui.YELLOW`는 답, 선택된 탭·칩, 1순위 표시에만 쓴다. 사용자가 확인한 규칙이다. 낱장 위에서 무언가를 강조하고 싶으면 먹과 굵기를 쓴다.

**글자 동반 규칙.** 상태를 색만으로 전하지 않는다. 승패 배지에는 승·패 글자가, 희귀도 칩에는 실버·골드·프리즘 이름이, 티어에는 숫자가 들어간다.

**4.5:1 규칙.** 글자와 바탕의 모든 조합은 `tests/test_gui_behavior.py::test_palette_matches_the_packaged_theme_and_readable_text`가 4.5:1 이상으로 검사한다. 색을 더하거나 바꾸면 이 검사에 조합을 넣는다.

**한 팔레트 규칙.** 색은 `components.py` 상수만 쓴다. `theme.json`은 `build_ctk_theme()`가 팔레트에서 만들어 내는 결과물이라 손으로 고치지 않는다.

## Typography

**Display Font:** Black Han Sans (`FONT_HEAD`, `gui/fonts/`에 동봉·OFL, 이 프로세스에만 등록. 등록 실패 시 맑은 고딕 굵게)
**Body Font:** 맑은 고딕 (`FONT_UI`, Windows 기본)
**Label/Mono Font:** Bahnschrift SemiBold Condensed (`FONT_DISPLAY`, 숫자 전용)

**Character:** 잡지 공략 쪽의 굵은 제목과 또렷한 본문. 제목은 한 가지 굵기뿐인 Black Han Sans로 눌러 찍고, 숫자는 좁은 DIN 계열로 자리를 아낀다.

### Hierarchy
- **Display** (`FH(84/68/56/44/32)`): 먹색 칸의 답. 글자 수에 따라 다섯 단계 중 하나로 정해진다(3자 이하 84, 5자 이하 68, 7자 이하 56, 10자 이하 44, 그 이상 32).
- **Headline** (`FH(40)`, `FT` = `FH(24)`): 챔피언 이름판 40, 화면 제목 24.
- **Title** (`FS` = `FH(19)`, 로고 `FH(21)`): 섹션 제목과 띠의 로고.
- **Body** (`FU` 14, `FB` 13, `FM` 12): 입력·버튼 14, 본문 13, 출처·메타 12. 본문 안의 강조 줄은 `FL`(15 굵게)로, 제목 글꼴을 쓰지 않는다.
- **Label** (맑은 고딕 굵게 11~14): `FCH` 11 작은 칩, 12 희귀도 칩·단계 표시, 14 탭.
- **Number** (`FNUM(20~30)`): 순위 숫자 1순위 30·2~3순위 20, 아이템 순서 26, 비교 줄 티어 28, 벤치 티어 24.

### Named Rules
**크기 순위 규칙.** 순위는 크기로 말한다. 증강 1순위는 숫자 30·아이콘 52px·이름 17 굵게에 형광펜 칠, 2~3순위는 숫자 20·아이콘 34px·이름 14 굵게에 칠 없음. 새 순위 목록도 이 두 단계를 쓴다.

**제목 기호 규칙.** Black Han Sans에는 `·` `—` `→` `「」` 글리프가 없다. 제목 글꼴로 찍는 문자열은 `ui.head_text()`를 거쳐 `/` `-` `>` `'`로 바뀐다. 다른 글꼴이 섞여 보이지 않게 하기 위해서다.

**숫자 글꼴 규칙.** 순위·티어·순서 같은 큰 숫자는 `FNUM()`만 쓴다. 문장 속 숫자는 본문 글꼴 그대로 둔다.

## Layout

세로 3단 셸이다. 위 먹색 띠 56px(노란 표지 네모 11×24, 로고, 탭 5개, 오른쪽에 게임 단계 4칸과 미니 위젯·요약 복사·설정), 가운데 판, 아래 먹색 상태 띠 30px(연결 상태, 데이터 패치, 버전). 판의 여백은 좌우 20px, 위 18px, 아래 16px. 창 최소 크기는 960×780.

아수라장 화면은 판 위에 2단으로 직접 놓인다. 왼쪽 단은 고정 너비 372px(`SIDE_W`)로 챔피언 일러스트(높이 196px)와 이름판, 답이 놓이는 먹색 칸, 벤치 티어 줄이 위에서 아래로 쌓인다. 오른쪽 낱장에는 추천 증강 3열(실버·골드·프리즘), 아이템 구매 순서 6칸, 실전 팁 3열이 놓인다. 한 화면의 주인공 구획은 하나다.

나머지 화면(티어표·내 전적·세션·협곡)은 낱장 한 장이고, 낱장 머리에 7px 먹색 괘선이 붙는다. 섹션은 위 18px·아래 6px 간격의 `ui.section_heading()`(13px 먹색 네모 + 제목)으로 시작한다. 설정 창(540×720)은 판 위에 낱장 묶음을 세로로 쌓는다. 미니 위젯(340×460, 항상 위)은 먹색 한 장이다.

괘선 굵기는 네 단계뿐이다. 7px 낱장 머리, 3px 구획 머리(희귀도 줄, 팁 칸), 2px 먹 위의 구분선과 단계 표시 테두리, 1px 가는 괘선.

네이티브 창(HWND) 수가 성능 예산이다. 글자는 `ui.TextLabel`(창 1개)로 찍고 `CTkLabel`(창 3개)은 아이콘 타일처럼 CTk 기능이 필요한 곳에만 쓴다. CTk 기능이 필요 없는 그릇은 `tk.Frame`이다. 보이지 않는 탭은 첫 방문 때 만든다.

### Named Rules
**창 예산 규칙.** 새 화면은 위젯 수를 늘리지 않는다. 글자는 `ui.TextLabel`, 그릇은 `tk.Frame`, 여러 조각은 합성 이미지 한 장으로.

**주인공 하나 규칙.** 한 화면에서 가장 큰 구획은 하나다. 아수라장에서는 왼쪽 먹색 칸이다.

## Elevation & Depth

그림자가 없다. Tk에는 그림자·흐림·그라디언트가 없고, 이 세계도 그것을 원하지 않는다. 깊이는 판과 낱장 두 겹의 명도 차, 먹색 면, 괘선 굵기로만 만든다. 움직임도 없다. 화면 전환과 상태 변화는 즉시 일어나고, 탭·행·버튼의 hover만 색으로 반응한다.

투명은 미니 위젯 한 곳에만 있다. 창 전체 불투명도를 0.5~1.0으로 조절하는 슬라이더이며, 게임 위에 겹쳐 놓기 위한 기능이지 장식이 아니다.

### Named Rules
**두 겹 규칙.** 위계는 판과 낱장 두 겹으로만 만든다. 낱장 위에 또 낱장을 띄우지 않고, 구획은 행 색(`ui.ROW`)과 괘선으로 나눈다.

**즉시 규칙.** 페이드·슬라이드·깜빡임을 넣지 않는다. 바뀐 것은 바뀐 채로 바로 보인다.

## Shapes

모서리는 직각이다(`CARD_RADIUS = 0`, `ROW_RADIUS = 0`, `ui.btn()`의 `corner_radius=0`, 테마의 프레임·버튼·입력·체크박스·스위치·세그먼트 모두 0). 선은 1px이 기본이고(`CARD_BORDER`, `ROW_BORDER`), 강조가 필요하면 굵기를 올린다. 둥근 것은 테마의 라디오 버튼과 스크롤바 손잡이 두 가지뿐이다.

되풀이되는 형태는 네모다. 띠의 노란 표지 네모, 섹션 제목 앞 13px 먹색 네모, 상태 띠의 9px 네모, 정사각 아이콘 타일. 증강 아이콘은 밝은 선화라 먹색 타일 위에 놓는다.

## Components

### Buttons
`ui.btn(*ui.BTN_*)`로 만든다. 직각이고 그림자가 없으며, hover는 바탕색만 바뀐다.
- **Primary** (`BTN_PRIMARY`): 먹 바탕에 흰 글자. 화면의 주 동작(전적 로드, 설정 저장, 닫기). 높이 34px.
- **Secondary** (`BTN_SECONDARY`): 종이 바탕에 먹 글자, 먹 1px 테두리. `ui.btn()`이 종이색 버튼에 테두리를 자동으로 붙인다.
- **Tertiary** (`BTN_TERTIARY`): 행 색 바탕에 흐린 글자, `ui.BORDER` 1px 테두리. 접기·삭제 같은 조용한 동작.
- **Selected** (`BTN_SELECTED`): 노란 바탕에 먹 글자. 지금 선택된 필터 칩. 선택되지 않은 칩은 Secondary.
- **Band** (`BTN_BAND`): 먹색 띠 위의 조용한 버튼.
- **Success / Purple / Danger** (`BTN_SUCCESS`, `BTN_PURPLE`, `BTN_DANGER`): 초록·보라·빨강 바탕에 흰 글자. 의미가 있는 동작에만.

### Chips
- **희귀도 칩**: 24px 높이, 좌우 10px, 맑은 고딕 12 굵게, 칩 색 바탕에 먹 글자. 칩 옆으로 같은 색 3px 줄이 열 너비만큼 이어진다.
- **티어 칩** (`ui.tier()`): 등급은 무게로 말한다. S 먹 바탕에 노란 글자, A 노란 바탕에 먹 글자, B `ROW_HOVER` 바탕, C `ROW` 바탕에 흐린 글자.
- **승패 배지** (`_result_icon`): 챔피언 아이콘 귀퉁이의 초록·빨강 네모에 흰 승·패 글자.
- **경고 칩**: `ui.RED` 2px 테두리에 빨간 굵은 글자(오래된 패치 데이터 알림). 바탕은 칠하지 않는다.

### Cards / Containers
- **낱장**: `ui.PANEL`, 직각, 그림자 없음. 머리에 7px 먹 괘선. 안쪽 구획은 `ui.BORDER` 1px.
- **행**: `ui.ROW` 바탕, 1px `ui.BORDER`. hover는 `ui.ROW_HOVER`에 먹 테두리. 선택된 행·나의 행은 `ui.ME_ROW`.
- **경기 목록 행**: 높이 60px, 44px 챔피언 아이콘에 승패 배지, 두 줄 글자.
- **먹색 칸**: `ui.INK` 바탕. 안의 구분선은 `ui.INK_RULE` 2px.

### Inputs / Fields
- **Style:** 흰 바탕, 먹 1px 테두리, 직각, 높이 34px. 드롭다운은 `ui.ROW` 바탕에 `ui.BORDER` 색 화살표 칸.
- **체크박스:** 먹 2px 테두리, 체크되면 먹 바탕에 노란 체크 표시.
- **스위치·슬라이더:** 직각. 꺼짐 `#B8B29B`, 켜짐 먹.
- **드롭다운 목록:** 종이 바탕, hover한 항목이 노랑.

### Navigation
- **탭** (`_select_nav`): 먹색 띠 위 44px 높이, 좌우 20px, 맑은 고딕 14 굵게. 기본 `ON_INK_DIM` 글자, hover하면 흰 글자, 선택되면 노란 칸에 먹 글자.
- **게임 단계 표시** (`_set_phase`): 대기·밴픽·게임 중·복기 네 칸을 2px 선으로 잇는다. 28px 높이, 12 굵게, `INK_RULE` 2px 테두리. 현재 단계만 노란 칸에 먹 글자. 단계가 바뀌면 화면이 스스로 넘어간다.
- **띠 도구**: 미니 위젯·요약 복사·설정은 글자뿐인 버튼이고 hover하면 글자가 노랑으로 바뀐다.

### 답 칸 (signature)
`AramSide`의 먹색 칸. 맨 위에 노란 답(`FH(32~84)`), 그 아래 흰 보조 줄(맑은 고딕 18 굵게), 이어서 비교 줄(챔피언 아이콘, 이름 15 굵게, 티어 `FNUM(28)`, 오른쪽 끝 메모). 비교 줄에서 강한 쪽만 흰 이름에 노란 티어이고 나머지는 흐리다. 이름판의 티어 칩은 내 챔피언이 답일 때만 노랗게 칠해지고, 아니면 먹 바탕에 흐린 테두리다.

### 증강 칸
`_AugmentSlot`. 순위 숫자, 먹색 타일 위 아이콘, 이름, 설명 2줄, 아래 1px 괘선. 1순위만 이름 뒤에 형광펜이 칠해진다. 설명 전체는 칸에 마우스를 올리면 툴팁으로 나온다.

### 아이템 칸
`_ItemSlot`. 순서 숫자 `FNUM(26)`, 52px 아이콘, 이름 13 굵게 두 줄 가운데 정렬. 여섯 칸이 한 줄에 선다.

### 미니 위젯
`widget.py`. 340×460 먹색 창, 맨 위 4px 노란 줄, `INK_RULE` 2px 구분선. 첫 줄이 답이라 노랗고 나머지는 흰 글자다. 항상 위·클릭 통과·불투명도 조절을 갖는다.

## Do's and Don'ts

### Do:
- **Do** 답 하나를 먹색 칸에 노란 Black Han Sans로 가장 크게 놓는다(`FH(32~84)`).
- **Do** 색은 `ui.*` 상수만, 버튼은 `ui.btn(*ui.BTN_*)`만 쓴다.
- **Do** 글자는 `ui.TextLabel`로, CTk 기능이 필요 없는 그릇은 `tk.Frame`으로 만든다.
- **Do** 제목 글꼴로 찍는 문자열은 `ui.head_text()`를 거치게 한다.
- **Do** 섹션은 `ui.section_heading()`으로 시작한다.
- **Do** 승패·희귀도·티어에는 색과 함께 글자나 숫자를 적는다.
- **Do** 새 글자·바탕 조합은 4.5:1 검사에 넣는다.
- **Do** 추천 옆에 출처·패치·표본을 `FM` 흐린 글자로 남긴다.

### Don't:
- **Don't** `ui.YELLOW`를 답·선택·1순위 밖의 장식이나 일반 강조에 쓰지 않는다.
- **Don't** 판을 진한 노랑으로 칠하지 않는다. 판은 `ui.BG`다.
- **Don't** 둥근 모서리, 그림자, 그라디언트, 전환 애니메이션을 넣지 않는다.
- **Don't** 어두운 남색 바탕에 네온 강조, 왼쪽 메뉴, 같은 크기의 둥근 카드 묶음으로 돌아가지 않는다.
- **Don't** 스킨 전환을 다시 만들지 않는다. 팔레트는 하나다.
- **Don't** 낱장 위에 낱장을 겹치지 않는다.
- **Don't** 순위를 색으로만 구분하지 않는다. 크기로 구분한다.
- **Don't** `theme.json`을 손으로 고치지 않는다.
- **Don't** 글자 한 줄을 위해 `CTkLabel`을 쓰지 않는다.
