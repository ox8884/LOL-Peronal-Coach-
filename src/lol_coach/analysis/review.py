"""한 판 심화 복기 — 승패 원인 · 잘한 점 · 개선점 · 다음 판 교훈."""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.modes import is_aram_queue
from lol_coach.riot.models import MatchSummary
from lol_coach.static.i18n import get_localizer


@dataclass
class MatchReview:
    """학습용 경기 분석 결과."""

    win_loss_reasons: list[str] = field(default_factory=list)  # 승/패 주요 원인 3~4
    good: list[str] = field(default_factory=list)
    improve: list[str] = field(default_factory=list)
    lesson: str = ""

    # 하위 호환
    @property
    def bad(self) -> list[str]:
        return self.improve


def _pct(v: float | None) -> float | None:
    if v is None:
        return None
    return v * 100 if v <= 1.5 else v


def _role_ko(role: str) -> str:
    return {
        "TOP": "탑",
        "JUNGLE": "정글",
        "MIDDLE": "미드",
        "BOTTOM": "원딜",
        "UTILITY": "서폿",
    }.get(role, role)


def _ro(word: str) -> str:
    """조사 '로/으로'."""
    if not word:
        return "로"
    ch = word[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0:
        return "으로"
    return "로"


def _analyze_aram_match(
    match: MatchSummary,
    champion: str,
    kill_participation: float | None,
    damage_share: float | None,
) -> MatchReview:
    reasons: list[str] = []
    good: list[str] = []
    improve: list[str] = []

    if match.win:
        if match.kda_ratio >= 3:
            reasons.append(
                f"KDA {match.kda_str} - 생존하면서 한타에 꾸준히 기여했습니다."
            )
        if kill_participation is not None and kill_participation >= 60:
            reasons.append(
                f"킬관여 {kill_participation:.0f}% - 팀과 함께 싸운 시간이 승리로 이어졌습니다."
            )
        if damage_share is not None and damage_share >= 25:
            reasons.append(
                f"딜 지분 {damage_share:.0f}% - {champion}의 화력이 한타의 중심이었습니다."
            )
        if not reasons:
            reasons.append("한타 진입과 궁극기 타이밍을 팀과 맞춘 승리로 보입니다.")
    else:
        if match.deaths >= 7:
            reasons.append(
                f"데스 {match.deaths}회 - 사망 공백이 반복돼 수적 열세 한타가 많았습니다."
            )
        if kill_participation is not None and kill_participation < 45:
            reasons.append(
                f"킬관여 {kill_participation:.0f}% - 팀 교전과 떨어진 시간이 길었습니다."
            )
        if damage_share is not None and damage_share < 15:
            reasons.append(
                f"딜 지분 {damage_share:.0f}% - 사거리와 스킬 재사용 기회를 충분히 살리지 못했습니다."
            )
        if not reasons:
            reasons.append("한 번의 한타 패배 뒤 재정비 없이 연속 교전한 흐름이 아쉬웠습니다.")

    if kill_participation is not None and kill_participation >= 65:
        good.append(f"킬관여 {kill_participation:.0f}% - 팀과 같은 타이밍에 움직였습니다.")
    if match.kda_ratio >= 3 and match.deaths <= 4:
        good.append(
            f"KDA {match.kda_str} - 무리한 진입을 줄이고 안전한 딜 각을 잡았습니다."
        )
    if damage_share is not None and damage_share >= 25:
        good.append(f"딜 지분 {damage_share:.0f}% - 한타 화력 기여가 충분했습니다.")
    if match.largest_multi_kill >= 3:
        good.append(f"멀티킬 {match.largest_multi_kill} - 마무리 집중력이 좋았습니다.")
    if not good:
        good.append("팀과 함께 움직인 교전 구간은 다음 경기에도 유지할 만합니다.")

    if match.deaths >= 7:
        improve.append(
            f"데스 {match.deaths}회 - 눈덩이 뒤로 혼자 나가지 말고 아군 앞라인 뒤에서 싸우세요."
        )
    if kill_participation is not None and kill_participation < 50:
        improve.append(
            f"킬관여 {kill_participation:.0f}% - 부활 후 혼자 진입하지 말고 아군 합류를 기다리세요."
        )
    if damage_share is not None and damage_share < 15:
        improve.append(
            f"딜 지분 {damage_share:.0f}% - 첫 스킬을 급하게 쓰지 말고 핵심 대상에게 사거리를 유지하세요."
        )
    if not improve:
        improve.append("다음 한타 전 궁극기와 증강 재사용 시간을 확인하고 팀 핑에 맞추세요.")

    if match.deaths >= 7:
        lesson = "다음 판 목표: 고립 데스 0회 - 아군과 같은 화면에서 한타를 시작하세요."
    elif kill_participation is not None and kill_participation < 50:
        lesson = "다음 판 목표: 킬관여 60% 이상 - 부활 후 가장 가까운 아군과 합류하세요."
    else:
        lesson = "다음 판 목표: 궁극기와 증강 타이밍을 맞춘 한타를 한 번 더 만드세요."

    return MatchReview(
        win_loss_reasons=reasons[:4],
        good=good[:5],
        improve=improve[:5],
        lesson=lesson,
    )


def analyze_match(m: MatchSummary) -> MatchReview:
    """실전 복기 생성."""
    loc = get_localizer()
    try:
        loc.ensure_loaded()
        champ = loc.champion(m.champion_name) or m.champion_name
    except Exception:
        champ = m.champion_name

    mins = max(m.duration_min, 1.0)
    role = m.role
    role_k = _role_ko(role)
    kp = _pct(m.kill_participation)
    ds = _pct(m.damage_share)
    dead_min = m.time_dead_s / 60.0 if m.time_dead_s else 0.0

    if is_aram_queue(m.queue_id):
        return _analyze_aram_match(m, champ, kp, ds)

    reasons: list[str] = []
    good: list[str] = []
    improve: list[str] = []

    # ── 팀 골드/오브젝트 격차 ──
    gold_diff = 0
    if m.ally_gold_total and m.enemy_gold_total:
        gold_diff = m.ally_gold_total - m.enemy_gold_total

    drag_diff = tow_diff = bar_diff = 0
    if m.obj:
        drag_diff = m.obj.ally.dragons - m.obj.enemy.dragons
        tow_diff = m.obj.ally.towers - m.obj.enemy.towers
        bar_diff = m.obj.ally.barons - m.obj.enemy.barons

    # ══════════════════════════════════════════════════════════════════
    # 승패 주요 원인 (팀 + 개인 기여)
    # ══════════════════════════════════════════════════════════════════
    if m.team_early_surrender:
        if m.win:
            reasons.append("상대 팀 조기 항복 — 초반 스노우볼이 게임을 끝냈습니다.")
        else:
            reasons.append("조기 항복 — 초반 격차가 커 팀이 게임을 일찍 접었습니다.")

    if m.win:
        if gold_diff >= 5000:
            reasons.append(
                f"팀 골드 +{gold_diff:,} — 라인·오브젝트에서 경제를 압도했습니다."
            )
        elif gold_diff >= 2000:
            reasons.append(
                f"팀 골드 +{gold_diff:,} — 소폭 경제 우위를 운영으로 지켰습니다."
            )
        if drag_diff >= 2:
            reasons.append(
                f"드래곤 {m.obj.ally.dragons if m.obj else 0}:{m.obj.enemy.dragons if m.obj else 0} — "
                "용 스택·시야 싸움에서 이겼습니다."
            )
        if bar_diff >= 1:
            reasons.append(
                f"바론 {m.obj.ally.barons if m.obj else 0}:{m.obj.enemy.barons if m.obj else 0} — "
                "한타 이득을 바론으로 연결해 포탑을 밀었습니다."
            )
        if tow_diff >= 3:
            reasons.append(
                f"포탑 {m.obj.ally.towers if m.obj else 0}:{m.obj.enemy.towers if m.obj else 0} — "
                "맵 압박·사이드 운영이 앞서 있었습니다."
            )
        if kp is not None and kp >= 55 and m.kda_ratio >= 2.5:
            reasons.append(
                f"당신 킬관여 {kp:.0f}%·KDA {m.kda_ratio} — "
                "팀 싸움에 꾸준히 기여해 승리를 도왔습니다."
            )
        if ds is not None and ds >= 28 and m.win:
            reasons.append(
                f"딜 지분 {ds:.0f}% — {champ} 캐리 압력이 게임의 축이었습니다."
            )
        if not reasons:
            reasons.append(
                "한타·스커미시에서 조금씩 앞서며 포탑을 가져간 운영 승리로 보입니다."
            )
    else:
        if gold_diff <= -5000:
            reasons.append(
                f"팀 골드 {gold_diff:,} — 초중반부터 경제가 무너져 복구가 어려웠습니다."
            )
        elif gold_diff <= -2000:
            reasons.append(
                f"팀 골드 {gold_diff:,} — 라인 손실이 중반 격차로 이어졌습니다."
            )
        if drag_diff <= -2:
            reasons.append(
                f"드래곤 {m.obj.ally.dragons if m.obj else 0}:"
                f"{m.obj.enemy.dragons if m.obj else 0} — "
                "용 합류·시야가 밀려 상대 스택이 쌓였습니다."
            )
        if bar_diff < 0:
            reasons.append(
                "바론을 내줬습니다 — 한타 패배 후 오브젝트 전환이 치명적이었습니다."
            )
        if tow_diff <= -3:
            reasons.append(
                f"포탑 {m.obj.ally.towers if m.obj else 0}:"
                f"{m.obj.enemy.towers if m.obj else 0} — "
                "사이드·한타 패배로 베이스가 열렸습니다."
            )
        if m.deaths >= 8 or dead_min >= 3.5:
            reasons.append(
                f"당신 데스 {m.deaths}회(사망 시간 약 {dead_min:.1f}분) — "
                "리스폰 공백이 팀 한타·오브젝트 싸움을 약화시켰습니다."
            )
        if kp is not None and kp < 40 and mins >= 20:
            reasons.append(
                f"킬관여 {kp:.0f}% — 팀 교전에 자주 빠지며 영향력이 줄었습니다."
            )
        if not reasons:
            reasons.append(
                "한타 패배와 오브젝트 전환 실패가 겹친 패배로 보입니다. "
                "한 번의 대형 교전을 복기해 보세요."
            )

    reasons = reasons[:4]

    # ══════════════════════════════════════════════════════════════════
    # 잘한 점 (실전적)
    # ══════════════════════════════════════════════════════════════════
    if m.solo_kills >= 2:
        good.append(
            f"솔킬 {m.solo_kills}회 — {role_k} 라인에서 1대1 압박이 먹혀 "
            "상대를 타워에 가뒀습니다. 이 템포를 유지하세요."
        )
    elif m.solo_kills == 1 and m.kda_ratio >= 3:
        good.append(
            f"솔킬 1회 + KDA {m.kda_str} — 라인 우위 구간을 잘 만들었습니다."
        )

    if m.cs10 is not None and role in ("TOP", "MIDDLE", "BOTTOM"):
        if m.cs10 >= 70:
            good.append(
                f"10분 CS {m.cs10} — 초반 웨이브 관리가 좋아 코어 타이밍이 빨랐을 가능성이 큽니다."
            )
        elif m.cs10 >= 55:
            good.append(f"10분 CS {m.cs10} — 초반 파밍은 평균 이상이었습니다.")

    if m.plates >= 3:
        good.append(
            f"포탑 방패(플레이트) {m.plates}개 — 라인 주도권으로 "
            "타워 골드까지 챙긴 좋은 압박입니다."
        )
    elif m.plates >= 1 and role in ("TOP", "MIDDLE", "BOTTOM"):
        good.append(f"플레이트 {m.plates}개 — 타워 골드 타이밍을 놓치지 않았습니다.")

    if m.gold_lead_lane is not None and m.gold_lead_lane >= 500:
        good.append(
            f"라인전 골드 우위 약 +{m.gold_lead_lane} — "
            "초반 교환·CS에서 앞섰습니다. 이 격차로 로밍/전령을 노리세요."
        )

    if m.dragon_takedowns >= 2:
        good.append(
            f"드래곤 관여 {m.dragon_takedowns}회 — 용 스폰에 맞춰 합류한 센스가 좋습니다."
        )
    if m.baron_takedowns >= 1:
        good.append(
            f"바론 관여 {m.baron_takedowns}회 — 오브젝트 한타 포지션이 맞아 떨어졌습니다."
        )
    if m.herald_takedowns >= 1 and role in ("JUNGLE", "TOP", "MIDDLE"):
        good.append(
            f"전령 관여 {m.herald_takedowns}회 — 전령으로 타워 압박을 시도한 운영이 좋습니다."
        )
    if m.epic_steals >= 1:
        good.append(
            f"에픽 몬스터 스틸 {m.epic_steals}회 — 스틸 각을 본 플레이가 게임 흐름을 바꿨을 수 있습니다."
        )

    if role == "JUNGLE":
        if m.scuttle_kills >= 2:
            good.append(
                f"바위게 {m.scuttle_kills}회 — 강가 시야·동선 싸움에서 이득을 봤습니다."
            )
        if m.jungle_cs_10 is not None and m.jungle_cs_10 >= 40:
            good.append(
                f"10분 정글 CS {m.jungle_cs_10:.0f} — 풀캠프 동선이 안정적이었습니다."
            )

    if role == "UTILITY":
        if m.vision_score >= 45 or (m.vision_score / mins) >= 1.8:
            good.append(
                f"비전 {m.vision_score}·제어와드 {m.control_wards} — "
                "시야가 팀 한타·로밍 안전망이 되었습니다."
            )
        if m.control_wards >= 6:
            good.append(
                f"제어와드 {m.control_wards}개 — 강가·용 둥지 시야 투자가 충분했습니다."
            )

    if kp is not None and kp >= 65:
        good.append(
            f"킬관여 {kp:.0f}% — 맵을 읽고 교전에 자주 합류했습니다. "
            "로밍·합류 타이밍이 좋았을 가능성이 큽니다."
        )
    if m.kda_ratio >= 4 and m.deaths <= 3:
        good.append(
            f"데스 {m.deaths}·KDA {m.kda_ratio} — 무리한 진입을 자제하며 딜 각을 골랐습니다."
        )
    if m.largest_multi_kill >= 3:
        good.append(
            f"멀티킬 {m.largest_multi_kill} — 한타에서 스킬 연계·포지션이 좋았습니다."
        )
    if m.first_blood:
        good.append("선취혈 — 레벨 2~3 교환 타이밍을 잘 잡았습니다.")
    if m.damage_to_objectives >= 8000:
        good.append(
            f"오브젝트 딜 {m.damage_to_objectives:,} — "
            "용/바론/타워에 딜을 박아 운영 기여가 있었습니다."
        )
    if m.damage_to_buildings >= 5000:
        good.append(
            f"건물 딜 {m.damage_to_buildings:,} — 사이드·공성 압박에 힘을 실었습니다."
        )

    if not good:
        good.append(
            f"{champ}{_ro(champ)} 큰 하이라이트 지표는 적지만, "
            "팀과 맞춰 게임을 굴린 무난한 플레이였습니다."
        )

    # ══════════════════════════════════════════════════════════════════
    # 개선할 점 (실전적 · 다음 판 행동)
    # ══════════════════════════════════════════════════════════════════
    if m.deaths >= 9:
        improve.append(
            f"데스 {m.deaths}회(사망 ~{dead_min:.1f}분) — "
            "시야 없는 강가·적 정글 진입을 끊고, "
            "한타 전 위치를 한 발 뒤로 잡으세요."
        )
    elif m.deaths >= 6:
        improve.append(
            f"데스 {m.deaths}회 — 솔킬/과한 올인 각을 줄이면 "
            "경험치·골드 격차가 바로 줄어듭니다."
        )

    if m.cs10 is not None and role in ("TOP", "MIDDLE", "BOTTOM") and m.cs10 < 50:
        improve.append(
            f"10분 CS {m.cs10} — 초반 웨이브(특히 3·캐논 웨이브) 관리가 아쉽습니다. "
            "교환 후 미니언을 먼저 정리하는 습관을 들이세요."
        )
    elif role in ("TOP", "MIDDLE", "BOTTOM") and mins >= 20 and m.cs_per_min < 5.5:
        improve.append(
            f"CS/분 {m.cs_per_min} — 중반 이후 사이드 파밍이 끊겼을 수 있습니다. "
            "한타 사이 웨이브를 챙기세요."
        )

    if kp is not None and kp < 40 and mins >= 18 and role != "UNKNOWN":
        if role == "MIDDLE":
            improve.append(
                f"킬관여 {kp:.0f}% — 미드에서 로밍·합류가 늦었을 수 있습니다. "
                "우선 푸시 후 강가 시야를 보고 봇/탑 개입을 노리세요."
            )
        elif role == "JUNGLE":
            improve.append(
                f"킬관여 {kp:.0f}% — 교전 합류가 늦었습니다. "
                "라인 핑 기준 동선을 미리 잡아 두세요."
            )
        elif role == "UTILITY":
            improve.append(
                f"킬관여 {kp:.0f}% — 로밍·시야 싸움 타이밍을 원딜과 맞추세요."
            )
        else:
            improve.append(
                f"킬관여 {kp:.0f}% — 팀 교전에 더 자주 붙어 "
                "스킬 쿨을 팀에 기여하세요."
            )

    if ds is not None and ds < 14 and role in ("MIDDLE", "BOTTOM", "TOP") and mins >= 22:
        improve.append(
            f"딜 지분 {ds:.0f}% — 한타에서 딜 각이 짧았을 수 있습니다. "
            "앞라인 뒤에서 스킬 사거리를 유지하세요."
        )

    if role == "UTILITY" and mins >= 20 and m.vision_score < 28:
        improve.append(
            f"비전 {m.vision_score} — 와드 주기가 깁니다. "
            "귀환할 때마다 제어와드+와드를 사고, 용 스폰 40초 전 시야를 박으세요."
        )
    elif role == "JUNGLE" and m.vision_score < 15 and mins >= 20:
        improve.append(
            "정글 시야가 얇습니다 — 바위게·적 캠프 동선에 와드를 남겨 "
            "갱·카정 각을 읽으세요."
        )

    if m.obj and m.obj.enemy.dragons >= m.obj.ally.dragons + 2:
        if m.dragon_takedowns == 0 and role in ("JUNGLE", "MIDDLE", "UTILITY"):
            improve.append(
                f"드래곤 {m.obj.ally.dragons}:{m.obj.enemy.dragons}·본인 관여 0 — "
                "용 스폰 전 미리 동선/핑을 맞추세요."
            )
        else:
            improve.append(
                f"드래곤 {m.obj.ally.dragons}:{m.obj.enemy.dragons} — "
                "용 한타 전 시야 싸움에서 밀렸을 가능성이 큽니다."
            )

    if m.obj and m.obj.enemy.barons > m.obj.ally.barons and m.baron_takedowns == 0:
        improve.append(
            "바론을 내줬고 관여가 없습니다 — "
            "한타 패배 후 바로 바론 시야를 포기하지 말고, "
            "남은 인원으로 견제 핑을 하세요."
        )

    if gold_diff <= -4000 and not m.win and m.deaths >= 5:
        improve.append(
            "크게 진 경제 + 개인 데스 — "
            "불리할 때는 사이드 깊게 밀지 말고 그룹·수비 위주로 전환하세요."
        )

    if m.plates == 0 and role in ("TOP", "MIDDLE") and mins >= 14 and m.cs10 and m.cs10 >= 60:
        improve.append(
            "CS는 괜찮은데 플레이트가 0 — "
            "라인 우위 시 타워 방패를 치는 타이밍을 기억하세요."
        )

    if not improve:
        if m.win:
            improve.append(
                "큰 구멍은 없습니다. 다음엔 리드 시 오브젝트 전환 속도만 "
                "더 빠르게 가져가 보세요."
            )
        else:
            improve.append(
                "지표상 한 가지를 고르면: 데스 줄이기. "
                "다음 판 목표를 '데스 4 이하'로 잡아 보세요."
            )

    # ══════════════════════════════════════════════════════════════════
    # 한 줄 교훈
    # ══════════════════════════════════════════════════════════════════
    if not m.win and m.deaths >= 7:
        lesson = (
            f"다음 판 목표: {champ} 데스 4 이하 — "
            "시야 밖 강가·솔킬 각만 끊어도 승률이 움직입니다."
        )
    elif not m.win and kp is not None and kp < 40:
        lesson = (
            f"다음 판 목표: 킬관여 50%+ — "
            f"{role_k}에서 우선 푸시 후 합류 타이밍을 의식하세요."
        )
    elif not m.win and m.obj and drag_diff <= -2:
        lesson = (
            "다음 판 목표: 용 스폰 40초 전 시야·합류 — "
            "오브젝트 한 번을 더 가져가면 게임이 달라집니다."
        )
    elif m.win and ds is not None and ds >= 25:
        lesson = (
            f"다음 판: {champ} 캐리 템포를 유지하되, "
            "리드 시 바론·억제기로 더 빨리 끝내세요."
        )
    elif m.win and m.solo_kills >= 1:
        lesson = (
            "다음 판: 라인 솔킬 후 바로 전령/로밍으로 눈덩이를 굴리세요."
        )
    elif role == "UTILITY":
        lesson = (
            "다음 판 목표: 제어와드 8개+ · 용 둥지 시야 — "
            "서폿 시야가 팀 실수를 줄입니다."
        )
    elif role == "JUNGLE":
        lesson = (
            "다음 판 목표: 바위게·용 타이밍 동선 고정 — "
            "교전 합류 1초가 오브젝트를 바꿉니다."
        )
    else:
        lesson = (
            f"다음 판 목표: {champ} CS/분 0.5 올리기 + 데스 1 줄이기 — "
            "작은 두 가지가 코어·한타를 바꿉니다."
        )

    return MatchReview(
        win_loss_reasons=reasons[:4],
        good=good[:5],
        improve=improve[:5],
        lesson=lesson,
    )


def timeline_flow(
    timeline: dict,
    *,
    my_participant_id: int | None = None,
) -> dict:
    """타임라인 프레임 → 분당 골드 격차·내 CS·데스 시각화 데이터.

    반환: {"minutes": [1..N], "gold_diff": [...], "my_cs": [...], "deaths": [분, ...]}
    gold_diff 는 아군 팀 총골드 - 적군 팀 총골드 (내 팀 기준 +).
    내 participantId 가 없으면 my_cs/deaths 는 빈 리스트.
    """
    out: dict = {"minutes": [], "gold_diff": [], "my_cs": [], "deaths": []}
    try:
        info = timeline.get("info") or {}
        frames = info.get("frames") or []
        if not frames:
            return out
        pid_team: dict[int, int] = {}
        for p in info.get("participants") or []:
            pid = int(p.get("participantId") or 0)
            if pid:
                pid_team[pid] = int(p.get("teamId") or 0)
        my_team = pid_team.get(int(my_participant_id or 0))
        for f in frames:
            ts = int(f.get("timestamp") or 0)
            minute = ts // 60000
            if minute < 1:
                continue
            pfs = f.get("participantFrames") or {}
            team_gold: dict[int, int] = {100: 0, 200: 0}
            my_cs = 0
            for pid_s, pf in pfs.items():
                pid = int(pid_s)
                gold = int(pf.get("totalGold") or 0)
                cs = int(pf.get("minionsKilled") or 0) + int(
                    pf.get("jungleMinionsKilled") or 0
                )
                tid = pid_team.get(pid)
                if tid in team_gold:
                    team_gold[tid] += gold
                if pid == my_participant_id:
                    my_cs = cs
            diff = team_gold[100] - team_gold[200]
            if my_team == 200:
                diff = -diff
            out["minutes"].append(minute)
            out["gold_diff"].append(diff)
            out["my_cs"].append(my_cs)
        if my_participant_id is not None:
            deaths: list[int] = []
            for ev in info.get("events") or []:
                if str(ev.get("type") or "") != "CHAMPION_KILL":
                    continue
                if int(ev.get("victimId") or 0) == my_participant_id:
                    deaths.append(int(ev.get("timestamp") or 0) // 60000)
            out["deaths"] = deaths
    except Exception:
        pass
    return out


def review_match(m: MatchSummary) -> tuple[list[str], list[str]]:
    """하위 호환: (잘한 점, 개선점)."""
    rev = analyze_match(m)
    return rev.good, rev.improve

def timeline_brief(
    timeline: dict,
    *,
    my_participant_id: int | None = None,
) -> list[str]:
    """Match V5 타임라인 → 한 판 흐름 요약 (15분 내 골드 · 첫 킬 · 오브젝트 타이밍).

    - timeline: get_match_timeline() 원본 JSON
    - my_participant_id: 내 participantId (MatchSummary.raw_participant["participantId"])
      주어지면 15분 시점 내 골드를 첫 줄에 추가
    """
    lines: list[str] = []
    try:
        info = timeline.get("info") or {}
        frames = info.get("frames") or []
        events = info.get("events") or []

        # ── 15분 시점 내 골드 ──
        if frames and my_participant_id is not None:
            target = 15 * 60 * 1000
            best = None
            for f in frames:
                ts = int(f.get("timestamp") or 0)
                if ts <= target:
                    best = f
                else:
                    break
            if best is not None:
                pf = (best.get("participantFrames") or {}).get(
                    str(my_participant_id)
                ) or {}
                gold15 = pf.get("totalGold")
                if gold15 is not None:
                    lines.append(f"15분 내 골드 {int(gold15):,}")

        # ── 첫 킬 타이밍 ──
        first_kill = None
        for ev in events:
            if str(ev.get("type") or "") == "CHAMPION_KILL":
                first_kill = ev
                break
        if first_kill:
            t = int(first_kill.get("timestamp") or 0) / 60000
            lines.append(f"첫 킬 {t:.0f}분")

        # ── 오브젝트 첫 처치 ──
        obj_first: dict[str, float] = {}
        obj_names = {
            "DRAGON": "용",
            "BARON_NASHOR": "바론",
            "RIFTHERALD": "전령",
            "VOIDGRUB": "공허유충",
        }
        for ev in events:
            if str(ev.get("type") or "") != "ELITE_MONSTER_KILL":
                continue
            mtype = str(ev.get("monsterType") or "")
            key = obj_names.get(mtype)
            if key and key not in obj_first:
                obj_first[key] = int(ev.get("timestamp") or 0) / 60000
        if obj_first:
            parts = " · ".join(
                f"{k} {int(t)}분" for k, t in sorted(obj_first.items(), key=lambda x: x[1])
            )
            lines.append(f"오브젝트: {parts}")

        # ── 첫 포탑 ──
        first_tower = None
        for ev in events:
            if (
                str(ev.get("type") or "") == "BUILDING_KILL"
                and str(ev.get("buildingType") or "") == "TOWER_BUILDING"
            ):
                first_tower = ev
                break
        if first_tower:
            t = int(first_tower.get("timestamp") or 0) / 60000
            lines.append(f"첫 포탑 {t:.0f}분")

        # ── 총 킬 수 ──
        kills = sum(
            1 for ev in events if str(ev.get("type") or "") == "CHAMPION_KILL"
        )
        if kills:
            lines.append(f"총 킬 {kills}회")
    except Exception:
        pass
    return lines
