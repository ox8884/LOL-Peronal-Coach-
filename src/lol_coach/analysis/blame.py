"""이 판 누구 탓 % — 팀운 정산 (결정적 계산, LLM 없음).

모델은 투명한 상대 점수 기반 분해다:
    점수 = KDA 비율(어시 0.7 가중, 상한 10) + 팀 내 데미지 비중 × 3

패배 시:
    기준 나 25 / 팀 40 / 상대 35 에서
    - 내 점수/팀원 평균이 1.2배 이상 → 내 탓 감소
    - 0.7배 이하 → 내 탓 증가
    - 팀원 평균/상대 평균이 1.1배 이상 → 팀 탓 감소 (상대 탓 증가)
    - 0.7배 이하 → 팀 탓 증가
승리 시에는 같은 수치를 승리 기여 분해로 해석한다.

표본(팀원 3명 미만)이 부족하면 None — 지어내지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from lol_coach.riot.models import MatchPlayer, MatchSummary

_ME_BASE = 25
_TEAM_BASE = 40
_ENEMY_BASE = 35
_MIN_PCT = 5
_MAX_PCT = 80
_MIN_ALLIES = 3
_MIN_ENEMIES = 3

_KDA_CAP = 10.0
_ASSIST_WEIGHT = 0.7
_DMG_WEIGHT = 3.0


@dataclass(frozen=True, slots=True)
class BlameReport:
    win: bool
    me_pct: int
    team_pct: int
    enemy_pct: int
    verdict: str
    my_score: float
    ally_avg: float
    enemy_avg: float
    lines: tuple[str, ...]

    @property
    def is_loss(self) -> bool:
        return not self.win


def player_score(p: MatchPlayer, team_damage_total: int) -> float:
    """KDA(어시 0.7) + 팀 데미지 비중 — 이해 가능한 상대 점수."""
    kda = (p.kills + _ASSIST_WEIGHT * p.assists) / max(1, p.deaths)
    kda = min(kda, _KDA_CAP)
    dmg_share = p.damage_to_champs / max(1, team_damage_total)
    return round(kda + _DMG_WEIGHT * dmg_share, 2)


def _norm(me: int, team: int, enemy: int) -> tuple[int, int, int]:
    """5~80 클램프 후 합계 100으로 보정 (반올림 오차는 팀이 흡수)."""
    values = [
        max(_MIN_PCT, min(_MAX_PCT, me)),
        max(_MIN_PCT, min(_MAX_PCT, team)),
        max(_MIN_PCT, min(_MAX_PCT, enemy)),
    ]
    total = sum(values)
    if total != 100:
        diff = 100 - total
        values[1] += diff  # 팀 버킷이 보정 흡수
    return values[0], values[1], values[2]


def _verdict(
    win: bool, me: int, team: int, enemy: int, my_ratio: float
) -> str:
    if not win:
        if team >= 55:
            if my_ratio < 1.2:
                return "팀 전체가 같이 무너졌습니다 — 개인 탓으로 돌리기 애매한 판"
            return "이 판은 팀 탓이 큽니다 — 네 탓 아님"
        if me >= 45:
            return "이 판은 내 탓이 큽니다 — 다음 판 행동 목표를 확인하세요"
        if enemy >= 50:
            return "상대가 잘했습니다 — 팀운 나쁨, 자책 금지"
        return "팽팽한 판이었습니다 — 한 끗 차이"
    if me >= 45:
        return "이 판은 네가 캐리했습니다"
    if team >= 55:
        return "팀원들이 잘해줬습니다 — 뒤에서 받쳐준 한 판"
    return "팀 전체가 잘 풀린 판이었습니다"


def analyze_blame(match: MatchSummary) -> BlameReport | None:
    """MatchSummary → 누구 탓 % 분해. 표본 부족 시 None."""
    allies = [p for p in match.ally_team if not getattr(p, "is_me", False)]
    enemies = list(match.enemy_team)
    if len(allies) < _MIN_ALLIES or len(enemies) < _MIN_ENEMIES:
        return None

    ally_dmg_total = sum(p.damage_to_champs for p in match.ally_team)
    enemy_dmg_total = sum(p.damage_to_champs for p in match.enemy_team)

    # 내 점수 — MatchSummary 자체 스탯 사용 (팀 리스트에 없어도 동작)
    my_kda = (match.kills + _ASSIST_WEIGHT * match.assists) / max(1, match.deaths)
    my_kda = min(my_kda, _KDA_CAP)
    my_dmg_share = match.damage_to_champs / max(1, ally_dmg_total)
    my_score = round(my_kda + _DMG_WEIGHT * my_dmg_share, 2)

    ally_scores = [player_score(p, ally_dmg_total) for p in allies]
    enemy_scores = [player_score(p, enemy_dmg_total) for p in enemies]
    ally_avg = round(sum(ally_scores) / len(ally_scores), 2)
    enemy_avg = round(sum(enemy_scores) / len(enemy_scores), 2)

    me = _ME_BASE
    team = _TEAM_BASE
    enemy = _ENEMY_BASE

    my_ratio = my_score / max(0.01, ally_avg)
    if my_ratio >= 1.2:
        if match.win:
            me += 20
            team -= 20
        else:
            me -= 12
            team += 12
    elif my_ratio <= 0.7:
        me += 20
        team -= 20

    team_ratio = ally_avg / max(0.01, enemy_avg)
    if team_ratio >= 1.1:
        team -= 10
        enemy += 10
    elif team_ratio <= 0.5:
        team += 16
        enemy -= 16
    elif team_ratio <= 0.7:
        team += 12
        enemy -= 12

    me_pct, team_pct, enemy_pct = _norm(me, team, enemy)

    kda_txt = f"{match.kills}/{match.deaths}/{match.assists}"
    lines = (
        f"내 KDA {kda_txt} · 팀원 평균 점수 {ally_avg}",
        f"아군 평균 {ally_avg} vs 적 평균 {enemy_avg}",
        f"내 점수 {my_score} (KDA + 팀 데미지 비중 기준)",
    )
    return BlameReport(
        win=bool(match.win),
        me_pct=me_pct,
        team_pct=team_pct,
        enemy_pct=enemy_pct,
        verdict=_verdict(match.win, me_pct, team_pct, enemy_pct, my_ratio),
        my_score=my_score,
        ally_avg=ally_avg,
        enemy_avg=enemy_avg,
        lines=lines,
    )
