"""상대 5명 정찰 — 리드 칩 (결정적 계산, 표본 부족 침묵).

게임 시작 시 Spectator 참가자(puuid)들의 최근 전적을 순차 조회해
'오늘 N판째', '빡큐', '원챔', '폼 핫/콜드' 칩을 만든다.

레이트리밋 안전 설계:
- 플레이어당 리스트 호출 1회 (30분 TTL 캐시로 반복 게임 시 0회)
- 상세 매치는 RiotClient 자체 디스크 캐시에 의존
- 순차 조회 + 호출 사이 pacing (기본 0.15초)
- 한 플레이어 실패는 스킵하고 나머지 계속
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_SCOUT_TTL_MS = 30 * 60 * 1000
_DETAILS_PER_PLAYER = 5
_DEFAULT_PACING_S = 0.15
_BANGKYU_WINDOW_MS = 20 * 60 * 1000
_MIN_SAMPLE = 3


@dataclass(frozen=True, slots=True)
class ScoutChip:
    kind: str  # danger | warn | hot | cold | info
    text: str


@dataclass(frozen=True, slots=True)
class PlayerScout:
    summoner_name: str
    champion_id: int
    team_id: int
    chips: tuple[ScoutChip, ...]
    sample_games: int = 0


@dataclass(frozen=True, slots=True)
class ScoutingReport:
    enemy: tuple[PlayerScout, ...]
    ally: tuple[PlayerScout, ...]
    scanned: int
    skipped: int


def _my_participant(match: dict, puuid: str) -> dict | None:
    for p in (match.get("info") or {}).get("participants") or []:
        if p.get("puuid") == puuid:
            return p
    return None


def _same_local_day(ended_ms: int, now_ms: int) -> bool:
    try:
        return (
            datetime.fromtimestamp(ended_ms / 1000).date()
            == datetime.fromtimestamp(now_ms / 1000).date()
        )
    except (OSError, OverflowError, ValueError):
        return False


def scout_player(
    summoner_name: str,
    puuid: str,
    matches: list[dict],
    *,
    now_ms: int,
) -> PlayerScout:
    """최근 전적(최신순) → 리드 칩. 표본 3판 미만이면 침묵."""
    wins: list[bool] = []
    champs: list[str] = []
    ended: list[int] = []
    for m in matches:
        p = _my_participant(m, puuid)
        if p is None:
            continue
        info = m.get("info") or {}
        ended.append(int(info.get("gameEndTimestamp") or info.get("gameCreation") or 0))
        wins.append(bool(p.get("win")))
        champs.append(str(p.get("championName") or "").strip() or "?")

    sample = len(wins)
    if sample < _MIN_SAMPLE:
        return PlayerScout(
            summoner_name=summoner_name,
            champion_id=0,
            team_id=0,
            chips=(),
            sample_games=sample,
        )

    chips: list[ScoutChip] = []

    # 오늘 N판째
    today_idx = [i for i, ms in enumerate(ended) if ms and _same_local_day(ms, now_ms)]
    if len(today_idx) >= 2:
        t_wins = sum(1 for i in today_idx if wins[i])
        t_losses = len(today_idx) - t_wins
        chips.append(
            ScoutChip(kind="info", text=f"오늘 {len(today_idx)}판째 ({t_wins}승 {t_losses}패)")
        )

    # 빡큐 — 마지막 판이 패배이고 20분 내 재큐
    if ended and not wins[0] and 0 <= now_ms - ended[0] <= _BANGKYU_WINDOW_MS:
        chips.append(ScoutChip(kind="danger", text="방금 패배 후 재큐 — 빡큐 위험"))

    # 원챔 — 최근 5판 중 같은 챔프 4판+
    if sample >= 5:
        champ, count = Counter(champs).most_common(1)[0]
        if champ != "?" and count >= 4:
            chips.append(ScoutChip(kind="warn", text=f"원챔 {champ} — 최근 5판 중 {count}판"))

    # 폼 핫/콜드
    w = sum(1 for x in wins if x)
    if w >= sample - 1:
        chips.append(ScoutChip(kind="hot", text=f"최근 {sample}판 {w}승 — 폼 핫"))
    elif w <= sample - (_MIN_SAMPLE + 1) or (sample >= 5 and w <= 1):
        chips.append(ScoutChip(kind="cold", text=f"최근 {sample}판 {w}승 — 폼 콜드"))

    order = {"danger": 0, "warn": 1, "cold": 2, "hot": 3, "info": 4}
    chips.sort(key=lambda c: order.get(c.kind, 9))
    return PlayerScout(
        summoner_name=summoner_name,
        champion_id=0,
        team_id=0,
        chips=tuple(chips),
        sample_games=sample,
    )


def scouting_headline(report: ScoutingReport) -> str:
    """토스트용 한 줄 요약 — 적 팀 칩 우선."""
    chips = [c for p in report.enemy for c in p.chips]
    danger = sum(1 for c in chips if c.kind == "danger")
    cold = sum(1 for c in chips if c.kind == "cold")
    hot = sum(1 for c in chips if c.kind == "hot")
    one_trick = sum(1 for c in chips if c.kind == "warn")
    if danger:
        return f"적 {danger}명 빡큐·위험 신호"
    if cold:
        return f"적 {cold}명 폼 콜드"
    if hot:
        return f"적 {hot}명 폼 핫 — 경계"
    if one_trick:
        return f"적 {one_trick}명 원챔"
    return "적 팀 특이 신호 없음"


# ── 캐시·오케스트레이션 ──────────────────────────────────


def load_scout_cache(path: Path) -> dict[str, dict]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: dict[str, dict] = {}
        for k, v in data.items():
            if (
                isinstance(k, str)
                and isinstance(v, dict)
                and isinstance(v.get("fetched_at_ms"), (int, float))
                and isinstance(v.get("ids"), list)
            ):
                out[k] = v
        return out
    except Exception:
        return {}


def save_scout_cache(path: Path, data: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_scouting_report(
    client,
    participants: list[dict],
    my_puuid: str,
    *,
    cache_path: Path,
    now_ms: int | None = None,
    pacing_s: float = _DEFAULT_PACING_S,
    details_per_player: int = _DETAILS_PER_PLAYER,
) -> ScoutingReport:
    """참가자 목록 → 정찰 리포트. 적 우선, 순차, 실패 스킵, TTL 캐시."""
    now = now_ms or int(time.time() * 1000)
    my_team_id = next(
        (int(p.get("teamId") or 0) for p in participants if p.get("puuid") == my_puuid),
        0,
    )

    others = [p for p in participants if p.get("puuid") != my_puuid]
    others.sort(key=lambda p: (int(p.get("teamId") or 0) == my_team_id, p.get("puuid") or ""))

    cache = load_scout_cache(cache_path)
    cache_changed = False
    enemy: list[PlayerScout] = []
    ally: list[PlayerScout] = []
    scanned = skipped = 0

    for p in others:
        puuid = str(p.get("puuid") or "")
        if not puuid:
            skipped += 1
            continue
        entry = cache.get(puuid)
        if entry is not None and now - int(entry["fetched_at_ms"]) <= _SCOUT_TTL_MS:
            ids = [str(x) for x in entry["ids"]]
        else:
            try:
                ids = [str(x) for x in client.get_match_ids(puuid, count=details_per_player)]
            except Exception:
                skipped += 1
                continue
            cache[puuid] = {"fetched_at_ms": now, "ids": ids}
            cache_changed = True
            if pacing_s > 0:
                time.sleep(pacing_s)

        matches: list[dict] = []
        for match_id in ids[:details_per_player]:
            try:
                matches.append(client.get_match(match_id))
            except Exception:
                continue
        name = str(p.get("summonerName") or "") or "?"
        if matches:
            scout = scout_player(name, puuid, matches, now_ms=now)
        else:
            scout = PlayerScout(
                summoner_name=name,
                champion_id=int(p.get("championId") or 0),
                team_id=int(p.get("teamId") or 0),
                chips=(),
                sample_games=0,
            )
        scout = PlayerScout(
            summoner_name=scout.summoner_name,
            champion_id=int(p.get("championId") or 0),
            team_id=int(p.get("teamId") or 0),
            chips=scout.chips,
            sample_games=scout.sample_games,
        )
        scanned += 1
        if int(p.get("teamId") or 0) == my_team_id:
            ally.append(scout)
        else:
            enemy.append(scout)

    if cache_changed:
        save_scout_cache(cache_path, cache)
    return ScoutingReport(
        enemy=tuple(enemy),
        ally=tuple(ally),
        scanned=scanned,
        skipped=skipped,
    )
