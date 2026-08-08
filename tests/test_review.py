from lol_coach.analysis.review import analyze_match, review_match
from lol_coach.riot.models import MatchObjectives, MatchSummary, SideObjectives


def _base(**kwargs) -> MatchSummary:
    data = dict(
        match_id="NA1_1",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MIDDLE",
        win=True,
        kills=10,
        deaths=2,
        assists=8,
        cs=200,
        gold=12000,
        damage_to_champs=25000,
        vision_score=20,
        game_duration_s=1800,
        queue_id=420,
        kill_participation=0.7,
        damage_share=0.3,
        solo_kills=2,
        cs10=75,
        plates=3,
        dragon_takedowns=2,
        ally_gold_total=60000,
        enemy_gold_total=48000,
        obj=MatchObjectives(
            ally=SideObjectives(dragons=3, barons=1, towers=9),
            enemy=SideObjectives(dragons=1, barons=0, towers=3),
        ),
    )
    data.update(kwargs)
    return MatchSummary(**data)


def test_timeline_flow_gold_diff_and_cs() -> None:
    """경기 흐름 차트 데이터 — 분당 골드 격차·내 CS·데스 분."""
    from lol_coach.analysis.review import timeline_flow

    tl = {
        "info": {
            "participants": [
                {"participantId": 1, "teamId": 100},
                {"participantId": 2, "teamId": 100},
                {"participantId": 3, "teamId": 200},
                {"participantId": 4, "teamId": 200},
            ],
            "frames": [
                {
                    "timestamp": 60000,
                    "participantFrames": {
                        "1": {"totalGold": 500, "minionsKilled": 10, "jungleMinionsKilled": 0},
                        "2": {"totalGold": 400, "minionsKilled": 8, "jungleMinionsKilled": 0},
                        "3": {"totalGold": 450, "minionsKilled": 9, "jungleMinionsKilled": 0},
                        "4": {"totalGold": 350, "minionsKilled": 7, "jungleMinionsKilled": 0},
                    },
                },
                {
                    "timestamp": 120000,
                    "participantFrames": {
                        "1": {"totalGold": 800, "minionsKilled": 20, "jungleMinionsKilled": 0},
                        "2": {"totalGold": 600, "minionsKilled": 15, "jungleMinionsKilled": 0},
                        "3": {"totalGold": 700, "minionsKilled": 18, "jungleMinionsKilled": 0},
                        "4": {"totalGold": 500, "minionsKilled": 12, "jungleMinionsKilled": 0},
                    },
                },
            ],
            "events": [{"type": "CHAMPION_KILL", "timestamp": 90000, "victimId": 1}],
        }
    }
    flow = timeline_flow(tl, my_participant_id=1)
    assert flow["minutes"] == [1, 2]
    assert flow["gold_diff"] == [100, 200]
    assert flow["my_cs"] == [10, 20]
    assert flow["deaths"] == [1]


def test_aggregate_form_filters_by_queue() -> None:
    """내 전적 큐 필터 — 매치 부분집합으로 RecentForm 재집계."""
    from lol_coach.riot.client import aggregate_form
    from lol_coach.riot.models import PlayerProfile

    profile = PlayerProfile(
        game_name="Tester", tag_line="KR1", puuid="p1", platform="kr"
    )
    sr = _base(match_id="SR_1", queue_id=420)
    aram = _base(match_id="ARAM_1", queue_id=450)
    form = aggregate_form(profile, [sr, aram])
    assert form.games == 2
    filtered = aggregate_form(profile, [m for m in [sr, aram] if m.queue_id == 420])
    assert filtered.games == 1
    assert filtered.matches[0].match_id == "SR_1"
    assert filtered.wins == 1


def test_analyze_win_has_reasons_and_lesson():
    rev = analyze_match(_base())
    assert len(rev.win_loss_reasons) >= 2
    assert rev.good
    assert rev.improve
    assert rev.lesson
    assert "다음" in rev.lesson or "목표" in rev.lesson


def test_analyze_loss_deaths():
    rev = analyze_match(
        _base(
            win=False,
            kills=2,
            deaths=12,
            assists=3,
            cs=100,
            gold=8000,
            damage_to_champs=8000,
            kill_participation=0.25,
            damage_share=0.12,
            solo_kills=0,
            cs10=40,
            plates=0,
            dragon_takedowns=0,
            ally_gold_total=40000,
            enemy_gold_total=62000,
            time_dead_s=240,
            obj=MatchObjectives(
                ally=SideObjectives(dragons=0, barons=0, towers=2),
                enemy=SideObjectives(dragons=3, barons=1, towers=9),
            ),
        )
    )
    assert any("데스" in r or "골드" in r or "드래곤" in r for r in rev.win_loss_reasons)
    assert any("데스" in b for b in rev.improve)
    assert rev.lesson


def test_review_match_compat():
    good, bad = review_match(_base())
    assert good and bad


def test_aram_review_does_not_emit_summoners_rift_advice():
    rev = analyze_match(
        _base(
            queue_id=450,
            role="MIDDLE",
            win=False,
            deaths=9,
            kill_participation=0.35,
            cs10=35,
            plates=0,
            dragon_takedowns=0,
            baron_takedowns=0,
            obj=MatchObjectives(),
        )
    )

    text = " ".join([*rev.win_loss_reasons, *rev.good, *rev.improve, rev.lesson])
    for summoners_rift_term in (
        "강가",
        "적 정글",
        "드래곤",
        "바론",
        "CS",
        "라인전",
        "와드",
    ):
        assert summoners_rift_term not in text
    assert "한타" in text or "포지션" in text
