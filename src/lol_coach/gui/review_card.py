"""디스코드 복기 카드 PNG 렌더러 — 게임 종료 후 웹훅으로 보내는 카드.

입력은 MatchSummary(복기 요약)와 선택적 킬 지도/붕괴 스냅샷 PIL 이미지다.
GUI 위젯에 의존하지 않는 순수 PIL 합성이므로 워커 스레드에서 안전하다.
디자인 토큰은 DESIGN.md 팔레트(배경 #0A0E14 · 패널 #121A24 · 골드 #C8AA6E)를
따르며, 그림자·애니메이션 없이 borders-only 계층만 사용한다.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from lol_coach.analysis.cardfont import card_font, wrap_text
from lol_coach.analysis.review import MatchReview
from lol_coach.riot.models import MatchSummary

WIDTH = 1080

BG = "#0A0E14"
PANEL = "#121A24"
BORDER = "#2A3B50"
GOLD = "#C8AA6E"
TEXT = "#E8ECF2"
BODY = "#C9D4E0"
DIM = "#7B8BA0"
GREEN = "#4CAF7D"
RED = "#E05B5B"

_LEFT_X = 48
_LEFT_W = 380
_RIGHT_X = 464
_RIGHT_W = WIDTH - 64 - _RIGHT_X


def _ellipsize(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _measure_sections(
    draw: ImageDraw.ImageDraw,
    match: MatchSummary,
    review: MatchReview,
) -> int:
    """오른쪽 열 총 높이 계산 (섹션 제목 + 줄바꿈 본문)."""
    body_font = card_font(22)
    line_h = 30
    gap = 14
    height = 0

    def add_section(title: str, items: list[str], limit: int) -> None:
        nonlocal height
        height += 34 + gap  # 섹션 제목
        for text in items[:limit]:
            wrapped = wrap_text(draw, text, body_font, _RIGHT_W)
            height += len(wrapped) * line_h + 4
        height += 8

    add_section("이 판 핵심", review.win_loss_reasons, 3)
    add_section("잘한 점", review.good, 3)
    add_section("다음 판 행동", review.improve, 2)
    # 교훈 박스 (패딩 포함)
    lesson_wrapped = wrap_text(draw, review.lesson or "", card_font(22, bold=True), _RIGHT_W - 48)
    height += 34 + gap + len(lesson_wrapped) * 30 + 40
    return height


def render_review_card(
    match: MatchSummary,
    review: MatchReview,
    *,
    minimap: Image.Image | None = None,
    collapse: Image.Image | None = None,
    collapse_caption: str = "",
) -> Image.Image:
    """복기 카드 합성 — 킬 지도(선택) + 붕괴 스냅샷(선택) + 텍스트 복기."""
    mode = _ellipsize(match.mode_label or "게임", 24)
    champ = _ellipsize(match.champion_name or "?", 20)
    result = "승리" if match.win else "패배"
    kda = f"{match.kills}/{match.deaths}/{match.assists} ({match.kda_ratio:.2f})"
    duration = f"{match.duration_min:.0f}분"

    # 1차 측정용 임시 드로어 (높이 계산)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    right_h = _measure_sections(probe, match, review)
    left_h = 360 + 44 if minimap is not None else 120
    body_h = max(right_h, left_h) + 30

    collapse_h = 0
    if collapse is not None:
        collapse_h = 380
    footer_h = 78
    height = 168 + body_h + collapse_h + footer_h

    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (24, 24, WIDTH - 24, height - 24),
        radius=28,
        fill=PANEL,
        outline=BORDER,
        width=2,
    )
    draw.rectangle((24, 24, 38, height - 24), fill=GOLD)

    # ── 헤더 ─────────────────────────────────────────────
    title_font = card_font(38, bold=True)
    draw.text((_LEFT_X, 56), f"{mode} 복기 카드", font=title_font, fill=TEXT)
    draw.text(
        (_LEFT_X, 108),
        f"{champ} · {result}",
        font=card_font(26, bold=True),
        fill=GREEN if match.win else RED,
    )
    meta = f"KDA {kda} · {duration}"
    meta_w = draw.textlength(meta, font=card_font(24))
    draw.text(
        (WIDTH - 48 - meta_w, 96),
        meta,
        font=card_font(24),
        fill=BODY,
    )

    # ── 본문 ─────────────────────────────────────────────
    y = 168
    # 왼쪽: 킬 지도
    if minimap is not None:
        thumb = minimap.convert("RGB").resize((360, 360), Image.Resampling.LANCZOS)
        image.paste(thumb, (_LEFT_X, y))
        draw.text(
            (_LEFT_X, y + 368),
            "킬 지도 · 파랑 킬 / 빨강 X 데스",
            font=card_font(18),
            fill=DIM,
        )
    else:
        draw.rounded_rectangle(
            (_LEFT_X, y, _LEFT_X + 360, y + 92),
            radius=14,
            fill="#0F1620",
            outline=BORDER,
            width=2,
        )
        msg = "킬 지도 없음 (타임라인 조회 실패)"
        msg_w = draw.textlength(msg, font=card_font(20))
        draw.text(
            (_LEFT_X + (360 - msg_w) / 2, y + 32),
            msg,
            font=card_font(20),
            fill=DIM,
        )

    # 오른쪽: 텍스트 복기
    body_font = card_font(22)
    sec_font = card_font(24, bold=True)
    ry = y

    def draw_section(title: str, items: list[str], limit: int, color: str) -> int:
        nonlocal ry
        ry += 8
        draw.rectangle((_RIGHT_X, ry + 6, _RIGHT_X + 4, ry + 30), fill=GOLD)
        draw.text((_RIGHT_X + 14, ry), title, font=sec_font, fill=color)
        ry += 38
        for text in items[:limit]:
            for line in wrap_text(draw, text, body_font, _RIGHT_W):
                draw.text((_RIGHT_X + 14, ry), line, font=body_font, fill=BODY)
                ry += 30
            ry += 4
        return ry

    draw_section(
        "이 판 핵심",
        review.win_loss_reasons or ["표본 부족 — 복기 데이터가 없습니다."],
        3,
        GREEN if match.win else RED,
    )
    draw_section(
        "잘한 점",
        review.good or ["기록된 잘한 점이 없습니다."],
        3,
        GREEN,
    )
    draw_section(
        "다음 판 행동",
        review.improve or ["다음 판도 같은 실수를 반복하지 않기"],
        2,
        "#E0A94F",
    )

    # 교훈 박스
    ry += 10
    lesson = review.lesson or "오늘의 한 판에서 얻은 것 하나를 기록하세요."
    lesson_lines = wrap_text(draw, lesson, card_font(22, bold=True), _RIGHT_W - 48)
    box_h = 24 + len(lesson_lines) * 30
    draw.rounded_rectangle(
        (_RIGHT_X, ry, _RIGHT_X + _RIGHT_W, ry + box_h),
        radius=14,
        fill="#0F1620",
        outline=GOLD,
        width=2,
    )
    draw.text((_RIGHT_X + 20, ry + 12), "다음 경기 교훈", font=card_font(20), fill=GOLD)
    ly = ry + 40
    for line in lesson_lines:
        draw.text((_RIGHT_X + 20, ly), line, font=card_font(22, bold=True), fill=TEXT)
        ly += 30

    body_end = y + body_h

    # ── 붕괴 스냅샷 (전체 폭 하단) ────────────────────────
    if collapse is not None:
        cy = body_end + 10
        thumb = collapse.convert("RGB").resize((300, 300), Image.Resampling.LANCZOS)
        image.paste(thumb, (_LEFT_X, cy))
        draw.text(
            (_LEFT_X + 330, cy + 6),
            "붕괴 스냅샷",
            font=card_font(24, bold=True),
            fill=GOLD,
        )
        caption = collapse_caption or "30초 내 한 팀 3킬+ — 판이 무너진 시점"
        cy2 = cy + 44
        for line in wrap_text(draw, caption, card_font(20), _RIGHT_W - 60):
            draw.text((_LEFT_X + 330, cy2), line, font=card_font(20), fill=BODY)
            cy2 += 28

    # ── 푸터 ─────────────────────────────────────────────
    footer = "롤 실전 코치 · Riot Match-V5 기반"
    footer_w = draw.textlength(footer, font=card_font(18))
    draw.text(
        ((WIDTH - footer_w) / 2, height - 56),
        footer,
        font=card_font(18),
        fill=DIM,
    )
    return image


def review_card_bytes(
    match: MatchSummary,
    review: MatchReview,
    *,
    minimap: Image.Image | None = None,
    collapse: Image.Image | None = None,
    collapse_caption: str = "",
) -> bytes:
    """복기 카드 → PNG 바이트 (디스코드 multipart 업로드용)."""
    image = render_review_card(
        match,
        review,
        minimap=minimap,
        collapse=collapse,
        collapse_caption=collapse_caption,
    )
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def sample_card_bytes() -> bytes:
    """웹훅 연결 테스트용 샘플 복기 카드 PNG."""
    match = MatchSummary(
        match_id="SAMPLE-0001",
        champion_name="Ahri",
        champion_id=103,
        role="MIDDLE",
        lane="MID",
        win=True,
        kills=9,
        deaths=3,
        assists=12,
        cs=140,
        gold=11500,
        damage_to_champs=26000,
        vision_score=8,
        game_duration_s=1290,
        queue_id=450,
        game_mode="aram",
    )
    review = MatchReview(
        win_loss_reasons=[
            "한타마다 궁극기로 상대 딜러를 먼저 묶었다",
            "상대 앞라인이 무너진 타이밍에 바로 밀어붙였다",
        ],
        good=["포킹 각을 잘 잡아 21분 전까지 무력화", "데스 3회로 생존 관리 안정적"],
        improve=["아이템 3코어 이후 존야 타이밍이 늦었다"],
        lesson="우세할 때는 탑 포탑보다 한타 합류가 먼저다.",
    )
    return review_card_bytes(match, review)
