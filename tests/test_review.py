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
