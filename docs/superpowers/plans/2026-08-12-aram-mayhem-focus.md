# ARAM Mayhem Focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 아수라장 결과 화면의 최상단에 실버·골드·프리즘 고정 TOP 3를 배치하고, 규칙 기반 브리핑과 AI 코칭 모두 6슬롯 아이템 경로를 보장한다.

**Architecture:** `MayhemAdvice`가 희귀도별 고정 순위와 완성된 6슬롯 경로를 단일 데이터 계약으로 제공한다. GUI는 이 계약을 3열 증강 보드와 3×2 아이템 카드로 렌더링하고, LLM 계층은 같은 경로를 구조화된 코칭 입력과 누락 보충에 사용한다.

**Tech Stack:** Python 3.10+, CustomTkinter, pytest, 기존 Blitz ARAM 패키지 카탈로그, 기존 LLM HTTP 어댑터

## Global Constraints

- 제시 증강 입력과 무관하게 Blitz 챔피언별 실버·골드·프리즘 순서의 앞 3개를 유지한다.
- 신발을 포함한 최종 아이템 슬롯을 최대 6개까지 표시한다.
- 모델이 누락한 슬롯은 검증된 메타·폴백 아이템만으로 보충하며 중복 아이템을 만들지 않는다.
- 새 원시 색상·글꼴·간격을 만들지 않고 `DESIGN.md`와 `components.py` 토큰을 사용한다.
- 기존 제시 증강 추천·회피, LCU 자동 입력, 조합 분석, 출처 표시는 유지한다.

---

### Task 1: 희귀도별 TOP 3와 6슬롯 도메인 계약

**Files:**
- Modify: `src/lol_coach/analysis/aram_mayhem.py`
- Modify: `tests/test_aram_mayhem.py`
- Modify: `tests/test_aram_blitz_parity.py`

**Interfaces:**
- Produces: `AugmentTierTop` and `MayhemAdvice.fixed_top`
- Produces: `MayhemAdvice.core_slots` containing up to six unique completed items

- [ ] 제시 증강이 달라도 희귀도별 TOP 3가 같은지 검증하는 실패 테스트를 작성한다.
- [ ] Blitz 순서가 희귀도별로 보존되는지 실패 테스트를 실행한다.
- [ ] `AugmentTierTop`을 추가하고 Blitz 추천을 희귀도별 3개로 투영한다.
- [ ] 6개 미만의 빌드는 역할 기반 폴백에서 중복 없이 보충한다.
- [ ] 관련 테스트가 통과하는지 확인한다.

### Task 2: LLM 6슬롯 출력 계약

**Files:**
- Modify: `src/lol_coach/llm.py`
- Modify: `src/lol_coach/gui/ai_mixin.py`
- Modify: `tests/test_llm.py`
- Modify: `tests/test_ai_mixin.py`

**Interfaces:**
- Consumes: `MayhemAdvice.fixed_top`, `MayhemAdvice.core_slots`
- Produces: `enrich_item_tree_response(..., min_cores=6, max_cores=6)` for ARAM coaching

- [ ] AI가 한 슬롯만 답해도 1~6슬롯이 모두 나오는 실패 테스트를 작성한다.
- [ ] 파서와 포매터가 6번째 슬롯을 보존하는 실패 테스트를 실행한다.
- [ ] 코어 슬롯 추출·포매팅 상한을 6으로 올리고 ARAM 후처리를 6슬롯 필수로 변경한다.
- [ ] 희귀도별 TOP 3, 양 팀 조합, 현재 제시 증강, 6슬롯 경로를 AI 입력에 전달한다.
- [ ] 관련 테스트가 통과하는지 확인한다.

### Task 3: 아수라장 집중 결과 화면

**Files:**
- Modify: `DESIGN.md`
- Modify: `src/lol_coach/gui/aram_tab.py`
- Modify: `tests/test_gui_behavior.py`

**Interfaces:**
- Consumes: `MayhemAdvice.fixed_top`, `MayhemAdvice.core_slots`
- Produces: 최상단 3열 증강 보드, 제시 증강 판정, 3×2 아이템 카드

- [ ] 테스트 더블로 희귀도 세 열과 여섯 아이템 슬롯 렌더를 검증하는 실패 테스트를 작성한다.
- [ ] `DESIGN.md`에 `Rarity Board`와 `Build Slot Card` 프리미티브를 추가한다.
- [ ] 기존 `_sec`, `_row_frame`, 팔레트, 글꼴 토큰으로 재사용 가능한 렌더 메서드를 구현한다.
- [ ] 제시 증강 판정과 보조 정보의 정보 순서를 설계대로 재배치한다.
- [ ] GUI 관련 테스트가 통과하는지 확인한다.

### Task 4: 회귀·실기동 검증과 사용자 릴리스 세트

**Files:**
- Modify: `README.md`
- Modify: `docs/features.html`
- Modify: release version files through `scripts/release.py`

- [ ] ARAM 타깃 테스트, 전체 pytest, ruff, mypy를 실행한다.
- [ ] 실제 앱에서 일반 폭과 좁은 폭의 아수라장 결과 화면을 캡처한다.
- [ ] 독립 시각 QA에서 정보 위계·CJK 줄바꿈·6슬롯 표시 PASS를 받는다.
- [ ] 다음 패치 버전으로 README와 기능 가이드를 갱신한다.
- [ ] exe와 installer를 재빌드하고 산출물을 실행해 확인한다.
- [ ] 구현·테스트·문서·버전 변경을 커밋한다. 푸시와 GitHub Release는 별도 요청이 있을 때만 수행한다.
