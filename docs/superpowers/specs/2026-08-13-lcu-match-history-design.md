# LCU 키리스 전적 폴백 & API 키 안내 개선 설계 (2026-08-13)

## 배경·목표

Riot 개발용 API 키는 24시간마다 만료되어 사용자 경험이 나쁘다. Blitz.gg는
Riot 정식 파트너(프로덕션 키 + 서버 측 호출)일 뿐 아니라 게임 클라이언트의
로컬 API(LCU)를 직접 읽는다. 이 프로젝트도 이미 LCU 통신(`lcu.py`, 밴픽 감지)을
하고 있으므로, **LCU의 전적 관련 엔드포인트로 키리스 폴백**을 구현한다.

목표:
1. API 키가 없거나 만료·오류여도 **내 전적·복기·(가능하면)킬 지도**가 동작
2. 키 만료 시 개발 키/개인 키 차이를 설명하는 안내 (개인 키는 24시간 만료 없음)

## 검증된 사실

- LCU 접근 방식은 기존 `lcu.py`에 검증됨 (lockfile 파싱, 루프백 HTTPS, basic auth)
- LCU 전적 엔드포인트 (커뮤니티 문서상 확실):
  - `GET /lol-match-history/v1/products/lol/current-summoner/matches`
    — 현재 로그인 계정의 최근 경기 목록 (`games.games[]`, begIndex/endIndex 페이징)
  - `GET /lol-match-history/v1/games/{gameId}` — 경기 상세 (match-v3 스타일 DTO,
    participant stats 전체 포함)
- **프로빙 필요**: `GET /lol-match-history/v1/game-timelines/{gameId}`
  (타임라인, v3 형태 `frames[]` + `frameInterval` + 프레임별 `events`·
  `participantFrames.position`) — 클라이언트 버전에 따라 404 가능.
  구현 중 클라이언트 켠 상태로 실측해 어댑터 보정 (설계 검증 단계에 포함)
- LCU gameId(숫자) + 플랫폼 접두사(`KR_<gameId>`) = **실제 Riot 매치 ID와 동일 형식**
  → 나중에 키가 생기면 같은 경기의 타임라인·킬 지도로 자연 업그레이드 가능

## 스코프

### In

1. `lcu.py` 확장: `match_history(beg_index, end_index)`, `match_detail(game_id)`,
   `match_timeline(game_id) -> dict | None` (프로빙, 404/없음이면 None)
2. `analysis/lcu_match.py` (신규, 순수 변환):
   - `lcu_to_match_summary(dto) -> MatchSummary` — v3 DTO → 기존 모델 매핑
   - `lcu_to_timeline_v5(dto) -> dict` — v3 타임라인 → killmap v5 형태
     (`{"info": {"frames": [...]}}` 래핑)
   - `match_id_for(game_id) -> str` — `f"KR_{game_id}"` (플랫폼은 사용자 설정
     `settings.platform` 기준, 기본 DEFAULT_PLATFORM="kr")
3. `me_tab._load_me` 폴백: Riot API 우선 → 키 없음/만료(403)/네트워크 오류 시
   LCU 경로로 `RecentForm` 구성 (기존 `aggregate_form` 재사용, 렌더링 동일)
   - 상태바: "로컬 전적 모드 (롤 클라이언트 전적 · API 키 불필요)"
   - 로그인 계정 본인 전적만 가능 (다른 소환사 검색은 키 필요 — 안내 유지)
4. 킬 지도 연동: `me_tab` 킬 지도·타임라인 로드도 LCU 타임라인 폴백
   (엔드포인트가 살아 있을 때만, 없으면 기존처럼 조용히 생략)
5. 키 안내 개선:
   - Riot API 403(만료) 감지 시 다이얼로그: 개발 키는 24시간 만료 →
     Developer Portal에서 **Personal** 앱 등록 안내 (장기 사용)
   - `_show_api_help` 내용에 개발 키 vs 개인 키 구분 추가
   - `config.api_key_expiry_hint` 문구 개인 키 기준으로 개선

### Out

- 임의 소환사 검색의 키리스 지원 (LCU는 본인 계정만)
- 리플레이(ROFL) 파싱, LCU가 켜지지 않은 상태의 키리스 전적
- 프록시 서버 (Riot 정책 위반 리스크)

## 아키텍처·데이터 흐름

```
내 전적 로드(_load_me)
  ├─ Riot API 경로 (기존): get_recent_form 성공 → 기존 렌더링
  └─ 실패(키 없음/403/네트워크):
       LCUClient.match_history(0, N) → 각 gameId별 match_detail
       → lcu_to_match_summary → aggregate_form → 기존 렌더링
       상태바 "로컬 전적 모드" + (403이었으면) 개인 키 안내 다이얼로그 1회

복기 상세 타임라인 (_tl_work)
  ├─ Riot API: get_match_timeline (기존)
  └─ 실패 or 키리스 모드: LCUClient.match_timeline(gameId)
       → lcu_to_timeline_v5 → timeline_brief/flow/build_kill_map 그대로
       404/없음 → 킬 지도·타임라인 섹션 조용히 생략 (기존 폴백 패턴)
```

## 데이터 매핑 (LCU v3 DTO → MatchSummary)

- 기본: `kills/deaths/assists`, CS=`totalMinionsKilled+neutralMinionsKilled`,
  `goldEarned`, `totalDamageDealtToChampions`, `visionScore`, `win`,
  `gameDuration`, `queueId`, `gameVersion`, `gameCreation`→`game_end_timestamp`
- 아이템 `item0~6`, 스펠 `spell1Id/spell2Id`, 룬 `perkPrimaryStyle/perkSubStyle`
- 심화: `totalDamageTaken`, `wardsPlaced/wardsKilled/detectorWardsPlaced`,
  `turretKills/inhibitorKills`, `firstBloodKill`, `largestMultiKill`,
  `totalTimeSpentDead`, `dragonKills/baronKills`
- 팀 10인: participants 전체로 `ally_team/enemy_team` (role/lane은
  participant `timeline.lane/role`), `is_me`는 소환사명 매칭
- 파생: 킬관여·딜지분은 아군 합계로 계산 (기존 로직 재활용)
- 없는 것: `obj`(None), challenges 기반(cs10·gold_lead 등 None), puuid(빈 값)

## 에러 처리·폴백 체인

1. Riot API 키 없음 → 즉시 LCU 폴백 시도 (다이얼로그 없이 상태바만)
2. Riot API 403 만료 → LCU 폴백 + 개인 키 안내 다이얼로그 (세션당 1회)
3. Riot API 기타 오류 → LCU 폴백 시도, LCU도 실패하면 기존 오류 안내
4. LCU lockfile 없음 → "롤 클라이언트를 켜면 키 없이 전적을 볼 수 있어요"
5. LCU 매치 필드 누락(gameId 없음 등) → 해당 매치 스킵
6. LCU 타임라인 404 → None (킬 지도만 생략, 나머지는 정상)

## 테스트

`tests/test_lcu_match.py` (fixture: v3 DTO 인라인 dict):
- `lcu_to_match_summary`: 필드 매핑·팀 구성·`is_me`·gameId 매치 ID 합성·
  없는 필드 None 처리
- `lcu_to_timeline_v5` → `build_kill_map` 연동 (킬·붕괴가 실제로 나옴)
- `match_id_for`: `KR_<gameId>` 형식
- 폴백 분기: mock 기반 — 키 없음/403/LCU 성공/LCU 실패 경로
- `tests/test_lcu.py` 확장: `match_history` 응답 구조 파싱 (games 중첩·빈 목록·오류)

## 실측 검증 (구현 중 필수)

1. 클라이언트 실행 상태에서 `/lol-match-history/.../matches` 실제 응답 구조 기록
2. `game-timelines` 프로빙 — 존재 시 어댑터 보정, 404 시 폴백 확인
3. 키 제거 후 앱 실행 → 전적·복기·(가능하면)킬 지도가 LCU로 표시되는지 확인

## 릴리스 (AGENTS.md)

- 버전 1.6.46 (`scripts/release.py --version 1.6.46 --skip-build`)
- README `### v1.6.46` 릴리스 노트, features.html에 "키 없는 로컬 전적 모드" 카드
- exe·인스톨러 재빌드 후 커밋·푸시
