"""blitz 클라이언트 인코딩·페이지 파서 회귀 테스트.

v1.6.109 — requests 가 charset 없는 Content-Type 을 ISO-8859-1 로 디코딩해
'완성 아이템' 라벨 매칭이 깨지고 페이지 파싱이 실패하던 버그의 회귀 방지.
"""

from __future__ import annotations

import customtkinter  # noqa: F401  (테스트 환경 Tk 초기화 보장)

from lol_coach.blitz.client import BlitzClient
from lol_coach.static.blitz_aram import parse_blitz_aram_page

_MINI_HTML = """
<html><body>
<div class="items-group">
  <div class="items-group-title">시작 아이템</div>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/1039.webp" alt="신성한 격석"/>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/2003.webp" alt="생명의 물약"/>
</div>
<div class="items-group">
  <div class="items-group-title">완성 아이템</div>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/6655.webp" alt="루덴의 메아리"/>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/3020.webp" alt="마법사의 신발"/>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/4646.webp" alt="폭풍 쇄도"/>
  <img class="item-img" src="https://blitz-cdn.blitz.gg/blitz/lol/item/3089.webp" alt="라바돈의 죽음모자"/>
</div>
</body></html>
"""


class _FakeResp:
    """charset 없는 Content-Type — requests 가 ISO-8859-1 로 되돌리는 상황 재현."""

    encoding = "ISO-8859-1"

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = {"Content-Length": str(len(body))}

    def iter_content(self, chunk_size: int = 64 * 1024):
        yield self._body


def test_response_html_forces_utf8_when_charset_missing() -> None:
    body = "완성 아이템 루덴의 메아리".encode()
    html = BlitzClient._response_html(_FakeResp(body))
    assert "완성 아이템" in html
    assert "루덴의 메아리" in html


def test_parse_page_keeps_completed_order_with_boots() -> None:
    build = parse_blitz_aram_page(_MINI_HTML, champion="Ahri", patch="16.17", source_url="t")
    names = [item.name_ko for item in build.core_items]
    # 완성 아이템 그룹 순서 그대로 (신발이 끼어 있는 것도 사이트 순서대로)
    assert names == ["루덴의 메아리", "마법사의 신발", "폭풍 쇄도", "라바돈의 죽음모자"]
    assert build.core_items[0].item_id == "6655"
