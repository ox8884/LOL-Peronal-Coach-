"""lol.ps 전체 챔피언 점검 — 추천·비추천 증강의 아이콘·설명, 아이템 이름·아이콘.

화면과 같은 경로(MayhemCoach.advise → 아이콘 로더)를 워커 스레드에서 돌려 실제로 뜨는지 본다.
lol.ps 자료나 증강 표시를 고친 뒤, 또는 새 패치마다 돌린다. 문제 0건이 목표.
usage: python scripts/dev_audit_aram.py <out.json>
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lol_coach import lolps  # noqa: E402
from lol_coach.analysis.aram_mayhem import MayhemCoach  # noqa: E402
from lol_coach.static import augment_icons  # noqa: E402
from lol_coach.static import mayhem_augments as ma  # noqa: E402
from lol_coach.static.ddragon import DataDragon  # noqa: E402
from lol_coach.static.icons import item_pil  # noqa: E402

out_path = sys.argv[1]
BAD_TEXT = re.compile(r"\?|@|%i:|\s의\s|\s{2,}|^\s|\s$|설명은 게임 안에서|효과 확인 후 선택|blitz\.gg 챔피언별")


def icon_ok(pick) -> str:
    """화면 로더와 같은 순서: 내장 카탈로그 → 증강 ID 의 게임 아이콘."""
    if augment_icons.augment_pil(pick.name_en, 40) is not None:
        return "catalog"
    aid = str(pick.record.id).removeprefix("live:")
    meta = ma.augment_meta(int(aid)) if aid.isdigit() else ma.meta_by_name(pick.name_ko)
    if meta is None:
        return ""
    return "game" if ma.icon_bytes_for(meta, None) else ""


def main() -> None:
    t0 = time.time()
    got = lolps.prefetch_all(pause_s=0.3)
    print(f"prefetch new={got} {time.time() - t0:.0f}s", flush=True)
    dd = DataDragon()
    dd.ensure_loaded()
    print("dd version", dd._version, flush=True)
    coach = MayhemCoach(dd, lolps=lolps)
    listing = lolps.index()
    problems: dict[str, list] = defaultdict(list)
    kinds: Counter = Counter()
    seen_aug: dict[int, dict] = {}
    champs = sorted(listing["champs"], key=int)
    for n, cid in enumerate(champs, 1):
        name = listing["champs"][cid]["name"]
        try:
            key = dd.champion_key(int(cid))
            adv = coach.advise(key)
        except Exception as exc:
            problems["advise_error"].append((name, repr(exc)))
            continue
        if not adv.source or adv.source.primary != "lol.ps 아수라장":
            problems["not_lolps"].append(name)
            continue
        detail = lolps.champion(int(cid), network=False) or {}
        picks = [*adv.fixed_top.silver, *adv.fixed_top.gold, *adv.fixed_top.prismatic, *adv.avoid_augments]
        for rarity in ("silver", "gold", "prismatic"):
            if len(getattr(adv.fixed_top, rarity)) < 3:
                problems["short_board"].append((name, rarity, len(getattr(adv.fixed_top, rarity))))
        for p in picks:
            entry = seen_aug.setdefault(p.name_ko, {"desc": p.desc, "icon": None, "champs": 0})
            entry["champs"] += 1
            if entry["icon"] is None:
                entry["icon"] = icon_ok(p)
            if not entry["icon"]:
                problems["no_icon"].append((name, p.name_ko, p.record.id))
            kinds[entry["icon"]] += 1
            if BAD_TEXT.search(p.desc):
                problems["bad_desc"].append((name, p.name_ko, p.desc))
        for item_id in adv.core_item_ids:
            if not dd.item_name(item_id):
                problems["item_name"].append((name, item_id))
            im = item_pil(item_id, 32)
            if im is None or im.info.get("lol_coach_placeholder"):
                problems["item_icon"].append((name, item_id))
        for aug in detail.get("good") or []:
            for item_id in aug.get("items") or []:
                if not dd.item_name(item_id):
                    problems["aug_item_name"].append((name, aug["name"], item_id))
        if n % 20 == 0:
            print(f"{n}/{len(champs)} {time.time() - t0:.0f}s", flush=True)
    report = {
        "champs": len(champs),
        "augments_seen": len(seen_aug),
        "icon_sources": dict(kinds),
        "problems": {k: v for k, v in problems.items()},
        "counts": {k: len(v) for k, v in problems.items()},
        "builds": dict(Counter(str((lolps.champion(int(c), network=False) or {}).get("build")) for c in champs)),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("counts", report["counts"], "icons", report["icon_sources"], f"{time.time() - t0:.0f}s", flush=True)


th = threading.Thread(target=main)  # 아이콘 받기는 워커 스레드에서만 일어난다 (화면과 같은 조건)
th.start()
th.join()
