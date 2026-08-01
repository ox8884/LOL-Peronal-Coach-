#!/usr/bin/env python3
"""u.gg 파서 헬스체크 — HTML 구조 변경으로 파싱이 깨졌는지 조기 감지.

사용법:
    python scripts/check_ugg_health.py
    python scripts/check_ugg_health.py --champion Ahri --role mid

종료 코드: 0 = 정상, 1 = 파싱 이상 감지
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lol_coach.modes import MODE_ARAM, MODE_SUMMONERS_RIFT
from lol_coach.ugg.client import UGGClient, UGGError
from lol_coach.ugg.counters import CounterClient


def _check(label: str, ok: bool, detail: str, failures: list[str]) -> None:
    mark = "OK " if ok else "FAIL"
    print(f"  [{mark}] {label:<28} {detail}")
    if not ok:
        failures.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description="u.gg 파서 헬스체크")
    parser.add_argument("--champion", default="Ahri")
    parser.add_argument("--role", default="mid")
    args = parser.parse_args()

    ugg = UGGClient(timeout=45.0)
    failures: list[str] = []

    print(f"■ 협곡 빌드: {args.champion} ({args.role})")
    try:
        build = ugg.get_champion_build(
            args.champion, role=args.role, mode=MODE_SUMMONERS_RIFT
        )
    except UGGError as exc:
        print(f"  [FAIL] 빌드 조회 실패: {exc}")
        return 1
    _check("패치 감지", bool(build.patch and build.patch != "unknown"), build.patch, failures)
    _check(
        "승률 파싱",
        build.win_rate is not None,
        f"{build.win_rate}% / {build.matches:,}게임" if build.win_rate else "없음",
        failures,
    )
    _check("룬(키스톤)", bool(build.runes.keystone), build.runes.keystone or "없음", failures)
    _check("스킬 우선순위", bool(build.skills.priority), " > ".join(build.skills.priority) or "없음", failures)
    _check("코어 아이템", bool(build.core_items.items), " → ".join(build.core_items.items[:3]) or "없음", failures)

    print(f"■ 칼바람 빌드: {args.champion}")
    try:
        aram = ugg.get_champion_build(args.champion, mode=MODE_ARAM)
        _check("ARAM 승률", aram.win_rate is not None, f"{aram.win_rate}%" if aram.win_rate else "없음", failures)
    except UGGError as exc:
        _check("ARAM 빌드", False, str(exc), failures)

    print(f"■ 카운터 페이지: {args.champion} ({args.role})")
    try:
        counters = CounterClient(ugg).get_counters(args.champion, role=args.role, limit=5)
        top = ", ".join(f"{c.champion} {c.gd15_str}" for c in counters.lane_counters[:3])
        _check("카운터 목록", bool(counters.lane_counters), top or "없음", failures)
    except UGGError as exc:
        _check("카운터 페이지", False, str(exc), failures)

    if failures:
        print(f"\n✗ {len(failures)}개 항목 이상 — u.gg HTML 구조 변경 가능성 확인 필요")
        return 1
    print("\n✓ 모든 파싱 경로 정상")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
