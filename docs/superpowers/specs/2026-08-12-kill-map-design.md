# 킬·데스 지도 & 붕괴 스냅샷 설계 (2026-08-12)

## 배경·목표

매치 상세 복기 패널에 "킬·데스 지도"를 추가해 롤도사(loldosa.com) 수준의
공간적 복기를 제공한다. 내 킬/데스 위치를 미니맵에 마커로 표시하고,
클릭하면 큰 지도와 "붕괴 스냅샷"(판이 무너진 시점의 10인 위치)을 보여준다.

지원 모드: **소환사의 협곡(SR) + 칼바람/아수라장(ARAM)** — 두 맵 모두 처음부터 지원.

## 검증된 사실 (실측, 2026-08-12)

설계 전 실제 데이터로 확인한 사항:

1. **타임라인 JSON 구조**: Match-V5 `/timeline`은 이벤트가 `info.events`가 아니라
   **프레임마다 내장**됨 (`info.frames[i].events`). `info.events`는 null.
   - 실측: 캐시된 실제 SR 랭크 타임라인(1.1MB) — frames 31개, events 총 1070개
   - `CHAMPION_KILL` 101개 전부 `position{x,y}`, `killerId`, `victimId`,
     `assistingParticipantIds`, `timestamp`, `bounty` 보유
2. **좌표 범위** (실측): 킬 x[594, 14044] y[572, 13336], 프레임 10인 좌표
   x[130, 14589] y[135, 14673] — 아래 경계 상수와 일치
3. **프레임 간격**: `frameInterval` 60000ms (1분 단위)
4. **맵 이미지**: DDragon `img/map/map11.png`(SR, 67KB), `map12.png`(칼바람, 139KB)
   둘 다 512×512 RGB 다운로드 확인됨
5. **렌더링 인프라**: `static/icons.py`의 `_download` 캐시 패턴 + `to_ctk`
   (PIL→CTkImage)가 이미 존재 — 재사용

## 스코프

### In

- 복기 패널(`_show_match_detail`)에 "킬·데스 지도" 섹션 (미니맵 약 320×320)
- 내 킬(파랑)·내 데스(빨강) 마커 + 순서 번호 + 범례 라벨
- 미니맵 클릭 → 확대 Toplevel: 큰 지도(520~560px) + 붕괴 스냅샷 + 캡션
- 붕괴 판정: 30초 내 같은 팀 3킬+ 전투, 후보 중 최다 킬, 동률이면 늦은 시점
- 스냅샷: 붕괴 시점 10인 위치 — 생존자는 가장 가까운 프레임 `position`,
  사망자는 그 킬 이벤트의 `position`, 챔피언 아이콘 마커
- **보너스 버그픽스**: 기존 `timeline_brief`/`timeline_flow`가 `info.events`를
  읽어 첫 킬·오브젝트·데스 정보가 실제로는 비어 있음 → 이번에 만드는
  공용 이벤트 병합 헬퍼(`flatten_events`)를 쓰도록 수정

### Out (이번엔 안 함)

- LLM 코멘트, 팀탓/내탓 % 모델, 마커 호버·애니메이션, op.gg 연동,
  16유형 진단, 주간 리포트 (이후 별도 스펙)

## 아키텍처·모듈

```
analysis/killmap.py      # 신규 — 순수 데이터 레이어 (GUI 의존 0)
static/icons.py          # map_pil(map_id, size) 추가
gui/map_render.py        # 신규 — PIL 합성 + 확대 Toplevel
gui/me_tab.py            # _show_match_detail에 지도 섹션 + 백그라운드 적용
gui/trend_viz.py         # 참고 — 기존 viz 헬퍼 모듈 (패턴 참고용)
```

### analysis/killmap.py

- `flatten_events(info: dict) -> list[dict]` — `frames[i].events` 병합 후
  timestamp 정렬. `review.py`의 `timeline_brief`/`timeline_flow`도 이걸 쓰게 수정
- `KillMapData` (dataclass):
  - `my_kills: list[KillEvent]`, `my_deaths: list[KillEvent]` — 순서 번호, 분:초,
    x/y, 상대 챔피언 id, 팀(100/200)
  - `collapse: CollapseSnapshot | None` — 시점(ms), 승리 팀, 10인 위치
    (participantId → (championId, x, y, alive)), 킬 요약
- `build_kill_map(timeline: dict, my_participant_id: int | None) -> KillMapData`
- 좌표 변환: `game_to_pixel(x, y, map_id, size)` — 맵별 경계 상수로 정규화
  (clamp + 3% 여백), 맵 이미지 방향에 따라 y축 플립
  - SR: x[-120, 14820], y[-120, 14881]  (실측 검증됨)
  - 칼바람(HA): x[-28, 12849], y[-19, 12858] — 구현 시 실제 ARAM 타임라인
    샘플로 검증·보정 (데이터 없으면 SR과 동일한 자동 정규화 폴백:
    이벤트 min-max 기준)

### 붕괴 판정 알고리즘

1. `flatten_events`에서 CHAMPION_KILL만 시간순 순회
2. 슬라이딩 윈도우: 같은 팀(킬러 기준)이 30초 이내 3킬+ → 후보
3. 후보 중 킬 수 최다 선택, 동률이면 늦은 시점
4. `CollapseSnapshot` 구성: 생존자 위치 = 타임스탬프에 가장 가까운 프레임의
   `participantFrames[].position`, 사망자 = 킬 이벤트 `position`
5. 후보 없으면 `collapse = None` (스냅샷 생략, 지도만 표시)

### static/icons.py

- `map_pil(map_id: int, size: int = 512) -> PIL Image | None`
  - DDragon `{ver}/img/map/map{map_id}.png` 다운로드·로컬 캐시 (기존
    `_download`/`_may_download` 패턴, `cache_dir()/maps/`)
  - 실패·오프라인이면 어두운 단색 배경 이미지 반환 (마커는 그대로 그림)
  - map_id 결정: `queue_id` → SR이면 11, ARAM이면 12 (ARAM 100/65 레거시 포함)

### gui/map_render.py

- `render_kill_minimap(data, map_pil, size=320) -> PIL Image`
  - 배경 맵 + 내 킬(파랑 원+번호) + 내 데스(빨강 X+번호) + 범례 텍스트
- `render_collapse_snapshot(data, map_pil, size=340) -> PIL Image | None`
  - 10인 위치에 챔피언 아이콘 원형 마커 (아군 파랑/적 빨강 테두리,
    사망자는 어둡게) + "N분 M초" 캡션
- `show_map_popup(app, minimap_img, snapshot_img, caption) -> None`
  - Toplevel: 큰 지도 + 스냅샷 나란히/아래, 닫기 버튼
  - 이미 열려 있으면 내용만 갱신 (중복 창 방지)
- `keep_image`는 기존 `app._keep_icon` 위임

### gui/me_tab.py

- `_show_match_detail`: "타임라인" 섹션 다음에 "🗺 킬·데스 지도" 섹션 추가,
  "불러오는 중…" 플레이스홀더 + `map_row` 확보
- 기존 `_tl_work` 스레드 확장: `tl = riot.get_match_timeline(...)` 후
  `build_kill_map(tl, pid)` → `map_pil` + `render_*` (PIL 합성도 스레드 안에서)
  → `after(0, _apply_killmap(map_row, minimap_ctk, snapshot_ctk, gen))`
- `_apply_killmap`: gen 가드(`_me_detail_gen`), 이벤트 없으면 섹션 숨김,
  미니맵 클릭 바인딩 → `show_map_popup`
- 타임라인 fetch 실패 시 기존과 동일하게 조용히 생략

## 데이터 흐름

```
복기 열기 → 지도 섹션 placeholder
  → _tl_work 스레드:
      get_match_timeline (디스크 캐시 1차)
      → build_kill_map → KillMapData
      → map_pil + render_kill_minimap / render_collapse_snapshot (PIL)
  → after(0) → _apply_killmap (gen 검증) → CTkImage 표시
클릭 → show_map_popup (확대 + 스냅샷)
```

## 에러 처리·폴백

- 타임라인 fetch 실패 → 섹션 숨김 (기존 패턴)
- 킬 이벤트 0개 → 섹션 숨김
- 좌표 누락 이벤트 → 해당 마커만 스킵
- 맵 이미지 없음 → 단색 폴백 위에 마커
- 붕괴 후보 없음 → 스냅샷 없이 지도만
- participantId 없음(my_participant_id None) → 지도 대신 "본인 식별 불가" 안내 한 줄

## 테스트

`tests/test_killmap.py` (fixture: 실제 캐시 타임라인에서 발췌한 축소 JSON):

- `flatten_events`: 프레임 병합·시간순 정렬·빈 프레임 무시
- 킬·데스 분류: killerId/victimId 기준, 팀(100/200) 판정
- 붕괴 판정: 29초(판정)/31초(미판정) 경계, 동률 시 늦은 시점, 3킬 미만 None,
  서로 다른 팀 킬 혼재
- 좌표 변환: 경계값·클램프·여백, SR/ARAM 경계 상수 적용
- 스냅샷: 사망자=이벤트 좌표, 생존자=최근접 프레임 좌표
- `timeline_brief`/`timeline_flow`가 flatten_events 경유 후 첫 킬·데스 정상 산출
  (기존 테스트 유지+보강)
- 렌더 smoke: 이미지 크기·마커 수 (PIL 합성은 결정적이라 쉽게 검증)

## 릴리스 (AGENTS.md)

- 버전 1.6.45 (`scripts/release.py --version 1.6.45 --skip-build`)
- README `### v1.6.45` 릴리스 노트, `docs/features.html`에 킬·데스 지도 카드
- `scripts/build_exe.ps1` → `scripts/build_installer.ps1` 재빌드 후 커밋·푸시
