"""승패 예측 + 예측 저장소 — 결정적 계산 (LLM 없음, 환각 0).

모델:
    예상 승률 = 50% 기준 + 조합 균형 델타(±16) + 내 폼 델타(±12, 표본 5+)

표본이 부족한 항목은 조용히 빼고 근거가 없는 수치는 만들지 않는다.
예측은 게임 시작 시 저장되고, 게임 종료 시 로스터 시그니처로 소비된다.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from lol_coach.static.ddragon import DataDragon

_BASE = 50.0
_FORM_SAMPLE_MIN = 5
_FORM_WEIGHT = 40.0  # (winrate - 50%) * 40 → 60% 폼 = +4%
_FORM_CAP = 12.0
_COMP_CAP = 16.0
_PROB_MIN = 20
_PROB_MAX = 80
_PRUNE_AFTER_MS = 6 * 60 * 60 * 1000  # 6시간 지난 미소비 예측 정리


def _as_int(value: object) -> int | None:
    try:
        return int(value) if isinstance(value, (int, float, str)) else None
    except (TypeError, ValueError):
        return None


def _as_str_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    for item in value:
        if not isinstance(item, (int, float, str)):
            return None
        out.append(str(item))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Prediction:
    """게임 시작 시점의 승패 예측 1건."""

    created_at_ms: int
    my_champ_id: int
    ally_roster: tuple[int, ...]  # 내 챔피언 포함, 정렬된 champion id
    enemy_roster: tuple[int, ...]  # 정렬된 champion id
    win_prob: int  # 0~100
    reasons: tuple[str, ...]
    sample_games: int = 0
    form_winrate: float | None = None

    @property
    def signature(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return (self.ally_roster, self.enemy_roster)

    def to_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> Prediction | None:
        created = _as_int(raw.get("created_at_ms"))
        champ = _as_int(raw.get("my_champ_id"))
        prob = _as_int(raw.get("win_prob"))
        ally = _as_str_tuple(raw.get("ally_roster"))
        enemy = _as_str_tuple(raw.get("enemy_roster"))
        reasons_raw = raw.get("reasons")
        if not isinstance(reasons_raw, list):
            reasons: tuple[str, ...] | None = None
        else:
            reasons = tuple(str(r) for r in reasons_raw if isinstance(r, (str, int, float)))
        sample = _as_int(raw.get("sample_games")) or 0
        form_raw = raw.get("form_winrate")
        form = None
        if form_raw is not None and isinstance(form_raw, (int, float, str)):
            try:
                form = float(form_raw)
            except (TypeError, ValueError):
                form = None
        if (
            created is None
            or champ is None
            or prob is None
            or ally is None
            or enemy is None
            or reasons is None
        ):
            return None
        return cls(
            created_at_ms=created,
            my_champ_id=champ,
            ally_roster=tuple(int(a) for a in ally),
            enemy_roster=tuple(int(e) for e in enemy),
            win_prob=prob,
            reasons=reasons,
            sample_games=sample,
            form_winrate=form,
        )


def _tag_counts(dd: DataDragon, roster: list[int]) -> dict[str, int]:
    """챔피언 id 목록 → DataDragon 태그 카운트."""
    dd.ensure_loaded()
    by_id = getattr(dd, "_champions_by_id", {}) or {}
    counts: dict[str, int] = {}
    for cid in roster:
        ch = by_id.get(int(cid))
        if not ch:
            continue
        for tag in ch.get("tags") or []:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def comp_delta(
    dd: DataDragon,
    ally_roster: list[int],
    enemy_roster: list[int],
) -> tuple[float, list[str]]:
    """조합 균형 델타(%)와 근거 문장. 양수 = 아군 우위."""
    mine = _tag_counts(dd, ally_roster)
    theirs = _tag_counts(dd, enemy_roster)
    delta = 0.0
    reasons: list[str] = []

    def cnt(tags: dict[str, int], key: str) -> int:
        return tags.get(key, 0)

    # 1) 앞라인(Tank+Fighter) — ARAM에서 가장 결정적인 신호
    my_front = cnt(mine, "Tank") + cnt(mine, "Fighter")
    enemy_front = cnt(theirs, "Tank") + cnt(theirs, "Fighter")
    front_diff = my_front - enemy_front
    if front_diff >= 1:
        delta += min(front_diff, 2) * 8.0
        reasons.append(f"앞라인 {front_diff}명 우위")
    elif front_diff <= -1:
        delta -= min(-front_diff, 2) * 8.0
        reasons.append(f"앞라인 {abs(front_diff)}명 열세")

    # 2) 힐·유틸 지속력 (ARAM)
    sup_diff = cnt(mine, "Support") - cnt(theirs, "Support")
    if sup_diff >= 2:
        delta += 6.0
        reasons.append(f"힐·유틸 {sup_diff}명 우위")
    elif sup_diff <= -2:
        delta -= 6.0
        reasons.append(f"적 힐·유틸 {abs(sup_diff)}명 우위")

    # 3) 포킹에 맞설 앞라인 부재
    if cnt(theirs, "Mage") >= 3 and my_front == 0:
        delta -= 8.0
        reasons.append("적 포킹 3+에 맞설 앞라인 없음")

    # 4) 풀 AD/풀 AP 페널티 (Marksman=AD 확정, Mage=AP 확정)
    my_ad, my_ap = cnt(mine, "Marksman"), cnt(mine, "Mage")
    their_ad, their_ap = cnt(theirs, "Marksman"), cnt(theirs, "Mage")
    if len(ally_roster) >= 5 and my_ad >= 2 and my_ap == 0:
        delta -= 6.0
        reasons.append("우리 팀 물리 화력 일색 (풀 AD 경계)")
    if len(ally_roster) >= 5 and my_ap >= 3 and my_ad == 0:
        delta -= 6.0
        reasons.append("우리 팀 마법 화력 일색 (풀 AP 경계)")
    if len(enemy_roster) >= 5 and their_ad >= 2 and their_ap == 0:
        delta += 6.0
        reasons.append("적 팀 풀 AD — 방어템으로 카운터 가능")
    if len(enemy_roster) >= 5 and their_ap >= 3 and their_ad == 0:
        delta += 6.0
        reasons.append("적 팀 풀 AP — 마저템으로 카운터 가능")

    return max(-_COMP_CAP, min(_COMP_CAP, delta)), reasons


def predict_game(
    dd: DataDragon,
    *,
    my_champ_id: int,
    my_team_id: int,
    participants: list[dict],
    form_winrate: float | None,
    form_sample: int = 0,
    created_at_ms: int | None = None,
) -> Prediction:
    """LiveGame 참가자 + 내 폼 → 승률 예측 (없으면 예외 대신 보수적 기본값)."""
    ally: list[int] = []
    enemy: list[int] = []
    for p in participants:
        cid = int(p.get("championId") or 0)
        if not cid:
            continue
        team = int(p.get("teamId") or 0)
        if team == my_team_id:
            ally.append(cid)
        else:
            enemy.append(cid)
    ally = sorted(set(ally))
    enemy = sorted(set(enemy))

    delta, reasons = comp_delta(dd, ally, enemy)

    form_delta = 0.0
    used_sample = 0
    used_form: float | None = None
    if form_winrate is not None and form_sample >= _FORM_SAMPLE_MIN:
        form_delta = (form_winrate - 50.0) * (_FORM_WEIGHT / 100.0)
        form_delta = max(-_FORM_CAP, min(_FORM_CAP, form_delta))
        used_sample = form_sample
        used_form = form_winrate
        direction = "핫" if form_delta > 0 else "콜드"
        reasons.append(f"내 최근 폼 {direction} (최근 {form_sample}판 승률 {form_winrate:.0f}%)")

    prob = int(round(_BASE + delta + form_delta))
    prob = max(_PROB_MIN, min(_PROB_MAX, prob))
    if not reasons:
        reasons = ["양팀 조합이 팽팽합니다 — 개인 기량이 승부처"]

    return Prediction(
        created_at_ms=created_at_ms or int(time.time() * 1000),
        my_champ_id=my_champ_id,
        ally_roster=tuple(ally),
        enemy_roster=tuple(enemy),
        win_prob=prob,
        reasons=tuple(reasons),
        sample_games=used_sample,
        form_winrate=used_form,
    )


# ── 저장소 ───────────────────────────────────────────────


def load_predictions(path: Path) -> list[Prediction]:
    """저장된 미소비 예측 목록 (손상 파일은 빈 목록)."""
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out: list[Prediction] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            pred = Prediction.from_json(item)
            if pred is not None:
                out.append(pred)
        return out
    except Exception:
        return []


def save_predictions(path: Path, preds: list[Prediction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps([p.to_json() for p in preds], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def add_prediction(path: Path, pred: Prediction) -> None:
    """추가 + 6시간 지난 미소비 예측 정리."""
    now = int(time.time() * 1000)
    kept = [p for p in load_predictions(path) if now - p.created_at_ms <= _PRUNE_AFTER_MS]
    kept.append(pred)
    save_predictions(path, kept)


def consume_prediction(
    path: Path,
    *,
    ally_roster: tuple[int, ...],
    enemy_roster: tuple[int, ...],
) -> Prediction | None:
    """로스터 시그니처가 일치하는 최신 예측 1건을 꺼내고 제거한다.

    로스터가 맞지 않으면 None (닷지·리메이크로 인한 오소비 방지).
    """
    signature = (ally_roster, enemy_roster)
    preds = load_predictions(path)
    matches = [p for p in preds if p.signature == signature]
    if not matches:
        return None
    chosen = max(matches, key=lambda p: p.created_at_ms)
    # 같은 로스터의 오래된 잔여(리메이크)는 같이 버린다
    rest = [p for p in preds if p.signature != signature]
    save_predictions(path, rest)
    return chosen
