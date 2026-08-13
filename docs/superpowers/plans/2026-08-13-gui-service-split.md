# GUI 믹스인 → 탭/서비스 분리 계획

**Goal:** `CoachApp`이 더 이상 8개 믹스인 + `CTk`의 공유 `self`에 모든 상태를 두지 않게 한다. 동작은 그대로 두고, 라이브 루프·전적·협곡·아수라장을 각자의 객체로 옮긴다.

**Why now:** v1.6.56에서 고친 리메이크 워처·정산 누락은 전부 `self._watcher` / `_watcher_gen` / `_on_game_ended`가 탭과 한 객체에 묶여 있어서 난 버그다. 다음 기능이 `live_mixin`에 또 붙으면 같은 종류의 경합이 재발한다.

**Non-goal:** UI 프레임워크 교체, 탭 정보구조 개편, 기능 추가, 한 번에 전 파일 rewrite.

## 현재 상태

```
CoachApp(Notify, Update, Ai, SrTab, AramTab, MeTab, MeDetail, Live, CTk)
```

| 파일 | 대략 줄 | 하는 일 |
|---|---:|---|
| `me_tab.py` | 1190 | 전적 로드, 프로필, 필터, 성장 리포트 |
| `aram_tab.py` | 1030 | 아수라장 입력·브리핑·증강 |
| `sr_tab.py` | 910 | 협곡 카운터·조합 |
| `app.py` | 770 | 셸, 테마, 스레드, 공통 위젯 헬퍼 |
| `live_mixin.py` | 850 | 시작/종료 워처, 예측, 정찰, 팀운, 디스코드 |
| `me_detail_mixin.py` | 600 | 복기 패널 |
| `types.py` | 160+ | 믹스인이 `self`로 가정하는 공용 API 목록 |

문제는 줄 수가 아니라 **소유권**이다. 워처·Riot 클라이언트·전적 폼·디스코드 웹훅이 전부 `CoachApp` 속성이다. 탭은 서로를 `self._show_match_detail`처럼 직접 호출한다.

## 목표 구조

```
CoachApp (CTk 셸)
  ├─ services
  │    LiveSession      시작/종료 워처, 예측 저장, 정찰, 팀운 정산
  │    DiscordCards     웹훅 검증 + 카드 전송 (토큰 미노출)
  │    MatchLoader      Riot 우선, LCU 폴백 (이미 analysis/lcu_match)
  └─ tabs
       SrTab / AramTab / MeTab   위젯만 소유, 서비스에 요청
```

규칙은 세 가지다.

1. **서비스는 tk를 import하지 않는다.** 콜백으로 UI에 결과를 넘긴다 (`after(0, ...)`는 셸이 한다).
2. **탭은 다른 탭의 private 메서드를 호출하지 않는다.** 필요하면 셸의 작은 facade (`show_match(match)`, `notify(...)`).
3. **새 기능은 맞는 서비스에 붙인다.** 라이브 루프면 `LiveSession`, 카드면 `DiscordCards`. `live_mixin`에 메서드를 더하지 않는다.

`CoachAppAPI` 프로토콜은 단계마다 줄어든다. 최종적으로 셸이 노출하는 건 `after`, `notify`, `status`, `spawn_thread`, `show_match` 정도다.

## 단계 (한 단계 = 한 PR/커밋, 동작 동일)

### 1. `LiveSession` 추출 (가장 이득 큼)

`live_mixin.py`의 워처·예측·정찰·팀운·리메이크 게이트를 `gui/live_session.py`로 옮긴다.

- 입력: `RiotClient`, `profile`, `DataDragon`, 예측 파일 경로, 콜백들
- 상태: `watcher`, `watcher_gen`, `watcher_game_id`, `watcher_puuid` — **여기만** 둔다
- 콜백: `on_started(game)`, `on_ended(match | None)`, `on_remake(match)`, `on_scout(report)`, `on_prediction(pred)`
- v1.6.56에서 넣은 `is_remake_or_abort` / generation / 최신 예측 소비는 이 객체 테스트로 고정한다

`LiveMixin`은 한동안 facade로 남긴다. `CoachApp` 시그니처를 한 번에 깨지 않기 위함이다.

테스트: `test_live_mixin.py`, `test_watcher.py`를 서비스 단위로 옮기거나 래핑. GUI `SimpleNamespace` 가짜 앱은 줄인다.

### 2. `DiscordCards` 추출

`_post_discord_card`와 카드 PNG 빌더 호출을 `gui/discord_cards.py`로 모은다. 웹훅 URL은 인자로만 받고, 예외 문자열은 절대 UI에 넣지 않는다 (v1.6.56 회귀 테스트 유지).

### 3. `MeTab` 합성

`MeTabMixin` + `MeDetailMixin`을 `gui/tabs/me.py` 클래스(`MeTab`)로 바꾼다. 생성 시 `parent`, `LiveSession`, `MatchLoader`, `notify`를 받는다.

전적 로드 세대(`generation`)와 아이콘 프리페치는 탭 내부 상태가 된다. 종료 복기가 상세를 열려면 `CoachApp.show_match(match)` → `me_tab.show(match)` 한 경로만 쓴다.

### 4. `SrTab` / `AramTab`

같은 패턴. LCU 밴픽 워처는 `LiveSession`이 아니라 탭이 `ChampSelectWatcher`를 소유한다 (이미 탭별로 적용 함수가 다름).

### 5. 셸 축소

`CoachApp`에서 믹스인 상속을 제거하고, 탭 인스턴스를 필드로 둔다.

```
class CoachApp(ctk.CTk):
    def __init__(...):
        self.live = LiveSession(...)
        self.me = MeTab(...)
        self.sr = SrTab(...)
        self.aram = AramTab(...)
```

`types.py`의 거대 프로토콜은 삭제하거나 셸 facade만 남긴다. v1.6.34에서 런타임 상속이 크래시를 냈던 전례가 있으므로, 프로토콜은 **타입 전용**을 유지하고 `CoachApp`이 프로토콜을 상속하지 않는다.

## 하지 말 것

- 탭마다 새 `RiotClient`를 만들지 않는다. 키·플랫폼은 셸이 하나 들고 서비스에 넘긴다.
- `analysis/*` 순수 계산(예측·팀운·정찰)은 이미 분리돼 있다. 다시 GUI로 끌어오지 않는다.
- 스킨 11종·위젯 헬퍼(`_sec`, `_lbl`)는 당분간 `app.py`/`components.py`에 둔다. 이번 작업의 병목이 아니다.
- 한 커밋에 3단계 이상을 넣지 않는다. 1단계만 해도 리메이크 회귀를 서비스 테스트로 잠글 수 있다.

## 완료 기준

- `CoachApp` MRO에 탭 믹스인이 없다
- `live_mixin.py`는 삭제됐거나 30줄 이하 facade
- `test_live_mixin` / `test_watcher` / `test_gui_behavior`의 종료·리메이크 케이스가 서비스 또는 facade에서 통과
- 사용자-facing 동작 변화 없음 (변화 있으면 별도 릴리스 노트)

## 추천 착수

1단계 `LiveSession`만 먼저. v1.6.56 버그의 진원지이고, 탭 UI를 안 건드리고도 끝나며, 테스트가 이미 있다.
