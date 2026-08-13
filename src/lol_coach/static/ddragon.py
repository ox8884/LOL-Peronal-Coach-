"""Riot Data Dragon static data (champions, items, runes, spells).

Display names default to Korean (ko_KR). English pack is still loaded
indirectly via ``lol_coach.static.i18n`` for blitz.gg name translation.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from lol_coach import http_security
from lol_coach.static import ddragon_cache
from lol_coach.static.i18n import get_localizer

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"


def _compact(s: str) -> str:
    """공백·구두점 제거 (리 신 → 리신, Lee Sin → leesin)."""
    return re.sub(r"[\s\-'_\.·]+", "", (s or "").strip().lower())


def _ascii_slug(s: str) -> str:
    """영문/숫자만 남긴 슬러그 (한글은 제거)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class DataDragon:
    """Caches champion / item / rune lookups (default language: ko_KR)."""

    def __init__(self, language: str = "ko_KR", timeout: float = 15.0):
        self.language = language
        self.timeout = timeout
        self.session = http_security.secure_session()
        self.session.headers.update({"User-Agent": "lol-personal-coach/0.1"})
        self._version: str | None = None
        self._champions_by_id: dict[int, dict] = {}
        self._champions_by_key: dict[str, dict] = {}
        self._champions_by_name: dict[str, dict] = {}
        self._items: dict[str, dict] = {}
        self._runes: dict[int, dict] = {}
        self._spells: dict[int, dict] = {}
        self._details: dict[str, dict] = {}
        self._loaded = False
        self._loc = get_localizer()

    def _detail_url(self, key: str) -> str:
        return f"{DDRAGON_BASE}/cdn/{self.version}/data/{self.language}/champion/{key}.json"

    def champion_detail(self, key: str) -> dict[str, Any] | None:
        """Return cached full champion detail JSON for a Data Dragon key (e.g. 'Ahri')."""
        self.ensure_loaded()
        norm = key.strip()
        if not norm:
            return None
        if norm in self._details:
            return self._details[norm]
        c = self._champions_by_key.get(norm.lower())
        if not c:
            return None
        dd_key = c["id"]
        url = self._detail_url(dd_key)
        payload = http_security.fetch_json_object(self.session, url, timeout=self.timeout)
        detail = http_security.require_object_path(payload, "data", dd_key)
        detail["_source_url"] = url
        detail["_patch"] = self.version
        self._details[dd_key] = detail
        return detail

    def _ability_fact(self, key: str, slot: str) -> dict[str, Any] | None:
        detail = self.champion_detail(key)
        if not detail:
            return None
        if slot == "P":
            p = detail.get("passive")
            if not p:
                return None
            return {
                "slot": "P",
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "icon": p.get("image", {}).get("full", ""),
                "patch": detail.get("_patch", self.version),
                "source_url": detail.get("_source_url", ""),
            }
        spells = detail.get("spells", [])
        idx = {"Q": 0, "W": 1, "E": 2, "R": 3}.get(slot)
        if idx is None or idx >= len(spells):
            return None
        s = spells[idx]
        return {
            "slot": slot,
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "tooltip": s.get("tooltip", ""),
            "icon": s.get("image", {}).get("full", ""),
            "cooldown": s.get("cooldownBurn", ""),
            "cost": s.get("costBurn", ""),
            "range": s.get("rangeBurn", ""),
            "resource": s.get("resource", ""),
            "maxrank": s.get("maxrank"),
            "patch": detail.get("_patch", self.version),
            "source_url": detail.get("_source_url", ""),
        }

    def passive_fact(self, key: str) -> dict[str, Any] | None:
        return self._ability_fact(key, "P")

    def q_fact(self, key: str) -> dict[str, Any] | None:
        return self._ability_fact(key, "Q")

    def w_fact(self, key: str) -> dict[str, Any] | None:
        return self._ability_fact(key, "W")

    def e_fact(self, key: str) -> dict[str, Any] | None:
        return self._ability_fact(key, "E")

    def r_fact(self, key: str) -> dict[str, Any] | None:
        return self._ability_fact(key, "R")

    def ability_facts(self, key: str) -> dict[str, dict[str, Any] | None]:
        """Structured P/Q/W/E/R ability facts for a champion key."""
        return {
            "P": self.passive_fact(key),
            "Q": self.q_fact(key),
            "W": self.w_fact(key),
            "E": self.e_fact(key),
            "R": self.r_fact(key),
        }

    @property
    def version(self) -> str:
        if not self._version:
            data = ddragon_cache.get_json(
                self.session,
                f"{DDRAGON_BASE}/api/versions.json",
                "versions",
                timeout=self.timeout,
            )
            self._version = str(data[0])
        return self._version

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        ver = self.version
        lang = self.language

        champs = ddragon_cache.get_json(
            self.session,
            f"{DDRAGON_BASE}/cdn/{ver}/data/{lang}/champion.json",
            f"{ver}:{lang}:champion",
            timeout=self.timeout,
        )
        for c in champs["data"].values():
            cid = int(c["key"])
            self._champions_by_id[cid] = c
            if "_" in c["id"]:
                # 스킨/모드 변형 챔피언 (예: Jade_Ahri, key 60103).
                # 이름이 기본 챔피언과 같아("아리") 인덱스를 덮어쓰므로
                # 숫자 key 조회(Spectator용)만 등록하고 이름 인덱스는 건드리지 않는다.
                continue
            self._champions_by_key[c["id"].lower()] = c
            self._champions_by_name[c["name"].lower()] = c
            slug = _ascii_slug(c["id"])
            self._champions_by_key[slug] = c
            # also index English id variants for CLI args like "ahri"
            self._champions_by_name[slug] = c
            # Korean without spaces: "리 신" → "리신"
            compact = _compact(c["name"])
            if compact:
                self._champions_by_name[compact] = c

        # English champion names for resolve (user may type English)
        en_champs = ddragon_cache.get_json(
            self.session,
            f"{DDRAGON_BASE}/cdn/{ver}/data/en_US/champion.json",
            f"{ver}:en_US:champion",
            timeout=self.timeout,
        )
        for c in en_champs["data"].values():
            key = c["id"].lower()
            # map english → same key entry we already have in ko pack
            ko = self._champions_by_key.get(key)
            if not ko:
                continue
            self._champions_by_name[c["name"].lower()] = ko
            slug = _ascii_slug(c["name"])
            self._champions_by_name[slug] = ko
            self._champions_by_key[slug] = ko
            compact = _compact(c["name"])
            if compact:
                self._champions_by_name[compact] = ko

        items = ddragon_cache.get_json(
            self.session,
            f"{DDRAGON_BASE}/cdn/{ver}/data/{lang}/item.json",
            f"{ver}:{lang}:item",
            timeout=self.timeout,
        )
        self._items = items["data"]

        spells = ddragon_cache.get_json(
            self.session,
            f"{DDRAGON_BASE}/cdn/{ver}/data/{lang}/summoner.json",
            f"{ver}:{lang}:summoner",
            timeout=self.timeout,
        )
        for s in spells["data"].values():
            self._spells[int(s["key"])] = s

        runes = ddragon_cache.get_json(
            self.session,
            f"{DDRAGON_BASE}/cdn/{ver}/data/{lang}/runesReforged.json",
            f"{ver}:{lang}:runesReforged",
            timeout=self.timeout,
        )
        for tree in runes:
            self._runes[int(tree["id"])] = {
                "id": tree["id"],
                "name": tree["name"],
                "key": tree.get("key"),
                "kind": "style",
            }
            for slot in tree.get("slots", []):
                for rune in slot.get("runes", []):
                    self._runes[int(rune["id"])] = {
                        "id": rune["id"],
                        "name": rune["name"],
                        "key": rune.get("key"),
                        "kind": "rune",
                        "style": tree["name"],
                    }

        shard_names = {
            5008: "적응형 능력치",
            5005: "공격 속도",
            5007: "스킬 가속",
            5002: "방어력",
            5003: "마법 저항력",
            5001: "체력 성장",
            5011: "체력",
            5013: "강인함 및 둔화 저항",
            5010: "이동 속도",
        }
        for sid, name in shard_names.items():
            self._runes.setdefault(sid, {"id": sid, "name": name, "kind": "shard"})

        self._loc.ensure_loaded()
        self._loaded = True

    def champion_name(self, champion_id: int) -> str:
        self.ensure_loaded()
        c = self._champions_by_id.get(int(champion_id))
        return c["name"] if c else f"챔피언#{champion_id}"

    def champion_key(self, champion_id: int) -> str:
        """Data Dragon id / blitz slug base (e.g. 'Ahri', 'MissFortune')."""
        self.ensure_loaded()
        c = self._champions_by_id.get(int(champion_id))
        return c["id"] if c else str(champion_id)

    def resolve_champion(self, name_or_key: str) -> dict[str, Any] | None:
        """Fuzzy resolve 'ahri', 'Miss Fortune', '아리', '리신' → champion dict."""
        hits = self.search_champions(name_or_key, limit=1, contains=False)
        if not hits:
            hits = self.search_champions(name_or_key, limit=1, contains=True)
        return hits[0] if hits else None

    def search_champions(
        self,
        query: str,
        limit: int = 8,
        *,
        contains: bool = False,
    ) -> list[dict[str, Any]]:
        """챔피언 검색 (자동완성용).

        - 기본: 정확 일치 + **접두어** (공백 무시: 리신 → 리 신)
        - ``contains=True``: 이름 중간 포함 매칭까지 (resolve 폴백)
        """
        self.ensure_loaded()
        raw = (query or "").strip()
        if not raw:
            return []
        lower = raw.lower()
        compact = _compact(raw)
        slug = _ascii_slug(raw)

        # exact dictionary hits first
        exact: dict[str, Any] | None = None
        for key in (lower, compact, slug):
            if not key:
                continue
            if key in self._champions_by_key:
                exact = self._champions_by_key[key]
                break
            if key in self._champions_by_name:
                exact = self._champions_by_name[key]
                break

        scored: list[tuple[int, str, dict[str, Any]]] = []
        seen: set[str] = set()

        def add(c: dict[str, Any], score: int) -> None:
            cid = c["id"]
            if cid in seen:
                return
            seen.add(cid)
            scored.append((score, c["name"], c))

        if exact:
            add(exact, 0)

        for c in self._champions_by_id.values():
            if "_" in c["id"]:
                # 변형 챔피언(Jade_*)은 자동완성/검색에서 제외
                continue
            name_l = c["name"].lower()
            name_c = _compact(c["name"])
            id_l = c["id"].lower()
            id_slug = _ascii_slug(c["id"])

            if exact and c["id"] == exact["id"]:
                continue

            # exact (display name / id)
            if name_l == lower or name_c == compact or id_l == lower:
                add(c, 0)
                continue
            if slug and id_slug == slug:
                add(c, 0)
                continue

            # prefix (공백 제거 기준 포함)
            if compact and (name_l.startswith(lower) or name_c.startswith(compact)):
                add(c, 1)
                continue
            if slug and (id_l.startswith(slug) or id_slug.startswith(slug)):
                add(c, 1)
                continue

            if not contains:
                continue

            # contains (resolve 폴백)
            if compact and len(compact) >= 2 and compact in name_c:
                add(c, 2)
                continue
            if len(lower) >= 2 and lower in name_l:
                add(c, 2)
                continue
            if slug and len(slug) >= 2 and slug in id_slug:
                add(c, 3)
                continue

        scored.sort(key=lambda t: (t[0], t[1]))
        return [c for _, _, c in scored[: max(1, limit)]]

    def item_name(self, item_id: int) -> str:
        self.ensure_loaded()
        if not item_id:
            return ""
        item = self._items.get(str(item_id))
        if item:
            return item["name"]
        return self._loc.item(item_id)

    def item_names(self, item_ids: list[int]) -> list[str]:
        return [self.item_name(i) for i in item_ids if i]

    def item_id_for_name(self, name: str) -> int | None:
        """한글/영문 아이템명 → Data Dragon 아이템 id (없으면 None)."""
        self.ensure_loaded()
        target = (name or "").strip()
        if not target:
            return None
        for iid, data in self._items.items():
            if data.get("name") == target:
                try:
                    return int(iid)
                except (TypeError, ValueError):
                    continue
        # 로컬라이저의 en→ko 맵으로 역추적
        from lol_coach.static.i18n import _norm_key

        nk = _norm_key(target)
        for en, ko in self._loc._item_en2ko.items():
            if en == nk or ko == target:
                for iid, data in self._items.items():
                    if data.get("name") == ko:
                        try:
                            return int(iid)
                        except (TypeError, ValueError):
                            break
        return None

    def item_tooltip(self, item_id: int | None) -> str:
        """툴팁용 텍스트: 이름 · 가격 · 설명(태그 제거)."""
        self.ensure_loaded()
        if not item_id:
            return ""
        data = self._items.get(str(int(item_id)))
        if not data:
            return ""
        name = data.get("name") or ""
        gold = (data.get("gold") or {}).get("total")
        plain = (data.get("plaintext") or "").strip()
        if not plain:
            desc = re.sub(r"<[^>]+>", " ", data.get("description") or "")
            desc = re.sub(r"\s+", " ", desc).strip()
            plain = desc[:240] + ("…" if len(desc) > 240 else "")
        head = name
        if gold:
            head += f"  ·  {gold:,}G"
        return f"{head}\n{plain}" if plain else head

    def rune_name(self, rune_id: int) -> str:
        self.ensure_loaded()
        r = self._runes.get(int(rune_id))
        return r["name"] if r else self._loc.rune(rune_id)

    def spell_name(self, spell_id: int) -> str:
        self.ensure_loaded()
        s = self._spells.get(int(spell_id))
        if s:
            return s.get("name") or f"주문#{spell_id}"
        return self._loc.spell(spell_id)

    def localize_item_name(self, english_or_any: str) -> str:
        """Translate scraped English item label → Korean."""
        return self._loc.item(english_or_any)

    def localize_rune_name(self, english_or_any: str) -> str:
        return self._loc.rune(english_or_any)

    def localize_spell_name(self, english_or_any: str) -> str:
        return self._loc.spell(english_or_any)


@lru_cache(maxsize=1)
def default_ddragon() -> DataDragon:
    return DataDragon(language="ko_KR")
