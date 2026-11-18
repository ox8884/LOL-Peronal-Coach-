"""공략본 디자인에 딸린 로직 — 증강 설명 정리, 벤치·리롤 답, 제목 글꼴, 말줄임."""

from __future__ import annotations

from pathlib import Path

from lol_coach.analysis.aram_mayhem import champ_select_advice, clean_augment_text, tier_letter


def test_augment_text_drops_icon_tokens_and_empty_number_slots() -> None:
    # 실제 화면에 깨져 나왔던 문장들
    assert clean_augment_text("%i:scaleAD% 공격력이 20% 증가합니다.") == "공격력이 20% 증가합니다."
    assert clean_augment_text("공격력이 20% (?) 증가합니다.") == "공격력이 20% 증가합니다."
    assert (
        clean_augment_text("치명타 확률을 25% (+0.05% %i:scaleCrit%) 얻습니다.")
        == "치명타 확률을 25% (+0.05% 치명타 확률) 얻습니다."
    )
    assert clean_augment_text("반복해서 ?의 피해를 8회 입힙니다.") == "반복해서 피해를 8회 입힙니다."
    assert clean_augment_text("") == ""


def test_augment_text_keeps_words_apart_and_reads_split_numbers() -> None:
    # 줄바꿈이 사라지며 "공격력이공격 속도로" 처럼 붙던 것
    assert clean_augment_text("<scaleAD>공격력</scaleAD>이<br>공격 속도로 전환됩니다.") == "공격력이 공격 속도로 전환됩니다."
    assert clean_augment_text("골드를 획득합니다.\n죽음의 무도") == "골드를 획득합니다. 죽음의 무도"
    assert (
        clean_augment_text("공격 사거리가 %i:meleeActive% 150 / %i:rangedActive% 100 증가합니다.")
        == "공격 사거리가 근접 150 / 원거리 100 증가합니다."
    )
    # 경기 중에 정해지는 퀘스트 횟수
    assert clean_augment_text("적 챔피언을 ?회 맞혀야 합니다.") == "적 챔피언을 여러 번 맞혀야 합니다."
    assert clean_augment_text("적 챔피언 ?명을 저격해야") == "적 챔피언 여러 명을 저격해야"
    assert (
        clean_augment_text("투사체 1+300% %i:scaleCrit%개를 발사해")
        == "투사체 1개(+치명타 확률의 300%)를 발사해"
    )


def test_select_advice_carries_the_answer_for_the_screen() -> None:
    names = {1: "유나라", 2: "릴리아", 3: "소나", 4: "가렌"}
    tiers = {1: 2, 2: 1, 3: 1, 4: 5}

    bench = champ_select_advice(1, tiers, names.get, bench_ids=[4, 2, 3], rerolls=1)
    assert bench is not None and bench.kind == "bench"
    assert bench.headline == "벤치 릴리아, 소나 잡기"
    assert bench.picks == (2, 3) and bench.my_tier == 2
    assert bench.bench == ((4, 5), (2, 1), (3, 1))
    assert bench.actions[0].startswith("벤치 릴리아·소나(S티어) 잡기 추천 — 지금 유나라 A티어")
    # 화면과 알림은 lol.ps 와 같은 글자로 말한다
    assert [tier_letter(n) for n in (1, 2, 3, 4, 5, None, 0)] == ["S", "A", "B", "C", "D", "?", "?"]

    # 같은 티어면 승률이 높은 챔피언이 답이 된다
    by_win = champ_select_advice(
        1, tiers, names.get, bench_ids=[4, 2, 3], rerolls=1, win_rates={1: 51.5, 2: 50.1, 3: 53.4}
    )
    assert by_win is not None and by_win.picks == (3, 2) and by_win.headline == "벤치 소나, 릴리아 잡기"
    assert by_win.win_rates == {1: 51.5, 2: 50.1, 3: 53.4}

    keep = champ_select_advice(2, tiers, names.get, bench_ids=[4], rerolls=1)
    assert keep is not None and (keep.kind, keep.headline) == ("keep", "릴리아 유지")

    reroll = champ_select_advice(4, tiers, names.get, bench_ids=[], rerolls=2)
    assert reroll is not None and (reroll.kind, reroll.headline, reroll.rerolls) == ("reroll", "리롤하세요", 2)

    info = champ_select_advice(1, tiers, names.get)
    assert info is not None and info.kind == "info" and info.rerolls is None
    assert champ_select_advice(1, {}, names.get) is None


def test_head_font_is_bundled_and_headings_avoid_missing_glyphs() -> None:
    from lol_coach.gui import components as ui

    font = Path(ui.__file__).parent / "fonts" / "BlackHanSans-Regular.ttf"
    assert font.is_file() and font.stat().st_size > 500_000
    assert ui.head_text("소환사 주문 · 룬 — 「복기」 → 끝") == "소환사 주문 / 룬 - '복기' > 끝"


def test_long_descriptions_are_cut_to_fit_and_short_ones_kept() -> None:
    from lol_coach.gui.aram_view import _fit

    short = "공격력이 20% 증가합니다."
    assert _fit(short, 13, 240, 2) == short
    long = "부활할 때마다 크기가 커져 적응형 능력치와 체력을 얻습니다. " * 6
    cut = _fit(long, 13, 240, 2)
    assert cut.endswith("…") and len(cut) < len(long)
    # 두 줄(240px × 2)에 들어갈 글자 수를 넘지 않는다 — 한글은 글자 크기만큼 차지
    assert len(cut) <= 2 * 240 / (13 * 0.95)
