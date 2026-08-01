# Deep Interview Spec: ARAM 아수라장 실전 팁 및 증강 이미지 품질

## Metadata
- Interview ID: 019f4cd9-c439-7000-81a8-1e111f4de713
- Rounds: 7
- Final Ambiguity Score: 5%
- Type: brownfield
- Generated: 2026-07-10
- Threshold: 0.05
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED
- Auto-Researched Rounds: none
- Auto-Answered Rounds: none
- Architect Failures: 0
- Lateral Reviews: 1
- Lateral Panel Failures: 0
- Refined Rounds: none
- Closure Overrides: none
- Restated Goal: 사용자가 입력한 챔피언과 현재 제시된 증강을 근거로, 출처·패치 시점이 표시된 개별화 아수라장 실전 팁을 제공하고, 모든 알려진 증강을 선명한 실제 이미지와 검증된 오프라인 캐시로 표시한다.

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.95 | 0.35 | 0.3325 |
| Constraint Clarity | 0.95 | 0.25 | 0.2375 |
| Success Criteria | 0.95 | 0.25 | 0.2375 |
| Context Clarity | 0.90 | 0.15 | 0.1350 |
| **Total Clarity** | | | **0.9425** |
| **Ambiguity** | | | **0.05** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 아수라장 실전 팁 품질 | active | 챔피언·증강·상황별 실행 조언 | 챔피언 운영 2개 이상, 입력 증강 시너지/주의점 1개 이상, 출처·패치 시점 표시 |
| 증강 이미지 품질 | active | 실제 아이콘의 안정적 표시 | 실제 128px 이상 이미지, Riot 우선·검증 Wiki 보조, 캐시·오프라인 정책 |

## Goal
사용자가 챔피언과 현재 제시된 증강을 직접 입력하면, 챔피언 고유 스킬·운영과 입력 증강의 구체 시너지·주의점을 담은 아수라장 실전 팁을 출처·패치 시점과 함께 제공하고, 모든 알려진 증강을 선명한 실제 이미지로 표시한다.

## Constraints
- Riot 공식 데이터와 패치 노트를 최우선으로 사용한다.
- U.GG와 League Wiki는 검증된 보조 출처로만 사용한다.
- 사용자가 현재 제시된 증강 이름을 직접 입력·선택한다.
- 증강 이미지는 Riot 우선, 검증된 Wiki 보조 출처로 수집한다.
- 앱 시작 또는 패치 변경 시 이미지 캐시를 백그라운드에서 갱신한다.
- 네트워크 실패·오프라인에서는 마지막 검증 캐시를 사용한다.
- 캐시가 없을 때만 이름·희귀도가 보이는 명확한 대체 카드를 표시한다.

## Non-Goals
- 라이엇 클라이언트에서 증강 선택지를 자동으로 읽지 않는다.
- 룬 추천이나 일반 소환사의 협곡 코칭을 확장하지 않는다.

## Acceptance Criteria
- [ ] 챔피언과 입력 증강으로 생성한 3~5개 팁 중 최소 2개가 챔피언 고유 스킬 또는 운영을 직접 언급한다.
- [ ] 최소 1개 팁이 입력 증강의 이름과 구체적 시너지 또는 주의점을 직접 언급한다.
- [ ] 팁 화면에 사용한 출처와 패치 또는 갱신 시점이 보인다.
- [ ] 알려진 모든 증강은 최소 128px 원본 또는 그 이상 실제 아이콘을 내려받아 선명하게 축소 표시한다.
- [ ] 이미지 수집은 Riot 출처를 먼저 시도하고, 검증된 Wiki 출처를 보조로 사용한다.
- [ ] 오프라인 또는 다운로드 실패 시 마지막 검증 캐시를 표시하며, 캐시가 없을 때만 대체 카드를 표시한다.
- [ ] 패치 변경 또는 앱 시작 후 이미지 갱신은 UI를 멈추지 않는다.

## Technical Context
- `src/lol_coach/analysis/aram_mayhem.py::_play_tips`는 역할군 태그 기반의 일반 문구를 생성하므로 챔피언·입력 증강 기반 추천 모델로 교체가 필요하다.
- `src/lol_coach/gui/app.py::_run_aram`은 챔피언만 입력받으므로 증강 선택지 입력 UI와 분석 경로가 필요하다.
- `src/lol_coach/static/icons.py::augment_pil`은 추정한 League Wiki URL을 사용하므로 출처 매니페스트·원본 해상도 검증·캐시 갱신 정책이 필요하다.
- `src/lol_coach/gui/app.py::_render_aram`은 증강 아이콘을 40px/36px로 표시한다.

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| 아수라장 실전 팁 | core domain | 챔피언 고유 스킬, 운영, 증강 시너지, 증강 주의점, 출처, 패치 시점 | 챔피언과 입력 증강을 근거로 생성 |
| 증강 이미지 | supporting | 출처 URL, 원본 해상도, 캐시 상태, 희귀도 | 증강 추천 결과에 표시 |

## Lateral Review Panel
- Round 3, initial→progress: 실제 증강 입력 경로, 검증된 이미지 매니페스트, 정보 최신성 표기 필요성을 확인했다.

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 챔피언 이름만으로 증강 시너지 팁을 만들 수 있다 | 실제 제시 증강을 알 수 있는가 | 사용자가 현재 제시된 증강을 직접 입력·선택한다 |
| 추정 Wiki URL이면 이미지가 충분하다 | 누락·저해상도·오프라인을 보장하는가 | Riot 우선, 검증 Wiki 보조, 128px 검증 및 캐시 정책 사용 |

## Deferrals
- 라이엇 클라이언트 증강 선택지 자동 수집은 이번 범위에서 제외한다.
