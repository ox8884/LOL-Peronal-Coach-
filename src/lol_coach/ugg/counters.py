"""u.gg 카운터픽 페이지 파싱."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from lol_coach.ugg.client import UGGClient, UGGError, champion_slug, normalize_role

ROLE_QUERY = {
    "top": "top",
    "jungle": "jungle",
    "mid": "middle",
    "middle": "middle",
    "adc": "adc",
    "bottom": "adc",
    "bot": "adc",
    "support": "support",
    "supp": "support",
    "utility": "support",
}

ROLE_KO = {
    "top": "탑",
    "jungle": "정글",
    "mid": "미드",
    "middle": "미드",
    "adc": "원딜",
    "bottom": "원딜",
    "support": "서폿",
}


@dataclass
class CounterPick:
    champion: str  # English name from u.gg
    gd15: int  # gold diff @ 15
    matches: int
    win_rate: float | None = None

    @property
    def gd15_str(self) -> str:
        sign = "+" if self.gd15 >= 0 else ""
        return f"{sign}{self.gd15}"


@dataclass
class CounterReport:
    enemy: str
    role: str
    patch: str
    source_url: str
    lane_counters: list[CounterPick] = field(default_factory=list)
    # weak against enemy (low GD15 / hard matchups) — optional
    hard_matchups: list[CounterPick] = field(default_factory=list)


def _report_to_dict(report: CounterReport) -> dict:
    """CounterReport → JSON 직렬화 가능 dict (공용 캐시용)."""
    return {
        "enemy": report.enemy,
        "role": report.role,
        "patch": report.patch,
        "source_url": report.source_url,
        "lane_counters": [asdict(c) for c in report.lane_counters],
        "hard_matchups": [asdict(c) for c in report.hard_matchups],
    }


def _pick_from_dict(data: Any) -> CounterPick:
    if not isinstance(data, dict):
        raise UGGError("카운터 캐시 형식 오류")
    return CounterPick(
        champion=str(data.get("champion") or ""),
        gd15=int(data.get("gd15") or 0),
        matches=int(data.get("matches") or 0),
        win_rate=data.get("win_rate"),
    )


def _report_from_dict(data: Any) -> CounterReport:
    if not isinstance(data, dict):
        raise UGGError("카운터 캐시 형식 오류")
    return CounterReport(
        enemy=str(data.get("enemy") or ""),
        role=str(data.get("role") or ""),
        patch=str(data.get("patch") or ""),
        source_url=str(data.get("source_url") or ""),
        lane_counters=[
            _pick_from_dict(c) for c in (data.get("lane_counters") or [])
        ],
        hard_matchups=[
            _pick_from_dict(c) for c in (data.get("hard_matchups") or [])
        ],
    )


class CounterClient:
    """Fetch Best Lane Counters from u.gg counter pages."""

    def __init__(self, ugg: UGGClient | None = None):
        self.ugg = ugg or UGGClient(timeout=45.0)

    def counter_url(self, champion: str, role: str) -> str:
        slug = champion_slug(champion)
        role_key = ROLE_QUERY.get(role.strip().lower())
        if not role_key:
            # try normalize_role then map
            try:
                rs = normalize_role(role)
                role_key = ROLE_QUERY.get(rs, rs)
            except UGGError as exc:
                raise UGGError(str(exc)) from exc
        return f"{self.ugg.BASE}/lol/champions/{slug}/counter?role={role_key}"

    def get_counters(
        self,
        enemy: str,
        role: str = "mid",
        limit: int = 10,
        min_matches: int = 800,
    ) -> CounterReport:
        url = self.counter_url(enemy, role)
        key = f"counters:{champion_slug(enemy)}:{role.strip().lower()}"
        cached = self.ugg.cached_get(key)
        if cached is not None:
            try:
                return _report_from_dict(cached)
            except UGGError:
                pass  # 손상 캐시 → 재조회
        try:
            html = self.ugg.fetch_html(url)
            report = self._parse(
                html,
                enemy=enemy,
                role=role,
                url=url,
                limit=limit,
                min_matches=min_matches,
            )
        except UGGError:
            # 네트워크/파싱 실패 → TTL 지난 캐시라도 사용
            stale = self.ugg.cached_get(key, allow_stale=True)
            if stale is not None:
                try:
                    return _report_from_dict(stale)
                except UGGError:
                    pass
            raise
        self.ugg.cached_set(key, _report_to_dict(report))
        return report

    def _parse(
        self,
        html: str,
        *,
        enemy: str,
        role: str,
        url: str,
        limit: int,
        min_matches: int,
    ) -> CounterReport:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n", strip=True)

        patch = "unknown"
        m_patch = re.search(r"Patch\s*(\d+\.\d+)", text)
        if m_patch:
            patch = m_patch.group(1)

        # Best Lane Counters block
        m = re.search(
            r"Best Lane Counters vs (.+?)\n"
            r"(?:These picks[^\n]*\n)?"
            r"((?:[A-Za-z][A-Za-z .'\-]*\n[+\-]\d+ GD15\n[\d,]+\ngames\n?)+)",
            text,
        )
        lane: list[CounterPick] = []
        if m:
            block = m.group(2)
            rows = re.findall(
                r"([A-Za-z][A-Za-z .'\-]*)\n([+\-]\d+) GD15\n([\d,]+)\ngames",
                block,
            )
            for name, gd, matches in rows:
                name = name.strip()
                if not name or name.lower() in ("games", "matches"):
                    continue
                n = int(matches.replace(",", ""))
                if n < min_matches:
                    continue
                lane.append(
                    CounterPick(
                        champion=name,
                        gd15=int(gd),
                        matches=n,
                    )
                )

        # hard matchups = negative GD15 from same list (or bottom of list)
        hard = [c for c in lane if c.gd15 < 0]
        # Prefer positive GD counters first
        good = [c for c in lane if c.gd15 > 0]
        good.sort(key=lambda c: (-c.gd15, -c.matches))
        hard.sort(key=lambda c: (c.gd15, -c.matches))

        if not good and not lane:
            raise UGGError(
                f"u.gg에서 {enemy} 카운터 데이터를 찾지 못했습니다. "
                "챔피언 이름/포지션을 확인하세요."
            )

        return CounterReport(
            enemy=enemy,
            role=role,
            patch=patch,
            source_url=url,
            lane_counters=good[:limit],
            hard_matchups=hard[:5],
        )
