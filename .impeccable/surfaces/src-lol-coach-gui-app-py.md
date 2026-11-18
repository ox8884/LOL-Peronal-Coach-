---
version: 1
slug: "src-lol-coach-gui-app-py"
primary_target: "src/lol_coach/gui/app.py"
related_targets: ["src/lol_coach/gui/components.py","src/lol_coach/gui/aram_view.py","src/lol_coach/gui/aram_tab.py","src/lol_coach/gui/widget.py"]
---

# 롤 실전 코치 데스크톱 앱 — 전체 화면

- 범위: `src/lol_coach/gui/` 전체(셸, 아수라장, 티어표, 내 전적, 세션, 협곡, 설정, 미니 위젯). 모드: Operate.
- 사용자·일: Jay 한 사람. 메인 모니터에 롤, 보조 모니터에 이 앱. 밴픽 30~60초와 판 사이에 2~3초씩 곁눈으로 읽는다. 플레이의 90% 이상이 아수라장.
- 과제: 밴픽 → 게임 중 → 복기 각 단계에서 "지금 할 것"이 앱을 만지지 않아도 보인다.
- 제약: 위젯(HWND) 수를 늘리지 않는다. 모든 기존 기능 유지. 화면 스타일 3종 전환은 없앤다.
- 사용자 결정(2026-11-17): 후보 3개 중 A 공략본 선택, "노랑을 덜 세게" → 판은 연한 버터색, 진한 노랑은 강조에만. "압도적으로 실용적이어야 한다."
- 미해결: 없음.

## Direction contract

THESIS: 게임 공략본의 한 쪽. 이번 판의 답 하나가 화면에서 가장 크고 가장 진하다. 거부하는 것: 어두운 남색 바탕에 네온 강조, 왼쪽 메뉴, 같은 크기의 둥근 카드가 쌓인 전적 사이트 형태.

OWN-WORLD: 연한 버터색 판(#F1E3A8) 위에 종이색 낱장(#FBF8EE), 먹색(#111) 굵은 띠와 굵은 괘선, 진한 노랑(#FFD400)은 답·선택·1순위 형광펜에만. 모서리는 전부 직각. 제목은 Black Han Sans, 본문은 맑은 고딕, 숫자는 좁은 DIN 계열. 순위는 크기로 말한다(1순위가 2·3순위보다 크다). 희귀도는 실버 회색·골드 호박색·프리즘 보라 칩에 글자를 함께 쓴다.

STORY: 밴픽이 시작되면 앱이 스스로 아수라장 화면으로 넘어가고, 사용자는 왼쪽 검은 칸의 노란 큰 글씨(벤치 잡기·리롤·유지)를 먼저 읽는다. 다음으로 희귀도별 1순위 증강, 아이템 1~6 순서를 읽는다. 게임이 끝나면 복기가 열려 있다.

FIRST VIEWPORT: 위 56px 먹색 띠 — 로고, 탭 5개(선택 탭은 노란 칸), 오른쪽에 대기·밴픽·게임 중·복기 단계 표시와 미니 위젯·요약 복사·설정. 아래 판은 2단: 왼쪽 400px 고정 — 챔피언 일러스트와 이름판, 그 아래 먹색 칸에 답(70px급 노란 글씨)과 비교 두 줄, 맨 아래 벤치 티어 줄. 오른쪽 낱장 — 추천 증강 3열(희귀도 칩, 1순위는 큰 아이콘과 형광펜 이름, 설명 2줄), 아이템 구매 순서 6칸(순서 숫자), 실전 팁 3열. 맨 아래 30px 먹색 띠에 연결 상태와 데이터·버전.

FORM: 게임 공략본(공략집·게임 잡지 공략 쪽). 내 후보 목록의 4번째. seed:813d6edc4391a9d3. 서명 동작은 형광펜 — 지금 고를 것 하나에만 진한 노랑이 칠해진다. 화면 전환과 상태 변화는 단계 없이 즉시(인쇄물처럼), 탭·행 hover만 색으로 반응한다.
Raised from 동물원 안내도: 한 화면에 주인공 구획 하나.
Raised from 별자리표: 순위는 고정된 크기 단계로.
Raised from 세로 영상 피드: 게임 단계가 화면을 넘긴다(대기·밴픽·게임 중·복기 표시와 자동 전환).
Raised from 인화 노출 기록: 명도는 정해진 단계만 쓴다.
Raised from 아세테이트 탭 설명서: 판·낱장 두 겹으로만 위계를 만든다.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
