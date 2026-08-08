"""Korean localization for items, runes, spells, champions, and UI labels.

Uses dual Data Dragon packs (en_US + ko_KR) so English names scraped from
blitz.gg (e.g. \"Blackfire Torch\") resolve to official Korean names
(e.g. \"어둠불꽃 횃불\").
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

import requests

from lol_coach.static import ddragon_cache

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"

# Stat shards / blitz.gg shard alts → 한국어 (runesReforged에 없음)
SHARD_KO: dict[str, str] = {
    "adaptive force": "적응형 능력치",
    "attack speed": "공격 속도",
    "ability haste": "스킬 가속",
    "armor": "방어력",
    "magic resist": "마법 저항력",
    "health": "체력",
    "health scaling": "체력 성장",
    "move speed": "이동 속도",
    "tenacity and slow resist": "강인함 및 둔화 저항",
    "tenacity": "강인함",
}

# 소환사 주문 별칭 (blitz.gg / 영문 축약)
SPELL_KO: dict[str, str] = {
    "flash": "점멸",
    "ignite": "점화",
    "teleport": "순간이동",
    "heal": "회복",
    "barrier": "방어막",
    "exhaust": "탈진",
    "cleanse": "정화",
    "ghost": "유체화",
    "smite": "강타",
    "mark": "표식",
    "snowball": "눈덩이",
    "clarity": "총명",
    "poro toss": "포로 던지기",
    "to the king": "왕에게로!",
}

# 룬 트리 영문 → 한글 (유실 시 폴백)
STYLE_KO: dict[str, str] = {
    "precision": "정밀",
    "domination": "지배",
    "sorcery": "마법",
    "resolve": "결의",
    "inspiration": "영감",
}

# 포지션 / 모드 UI
ROLE_KO: dict[str, str] = {
    "TOP": "탑",
    "JUNGLE": "정글",
    "MIDDLE": "미드",
    "MID": "미드",
    "BOTTOM": "원딜",
    "ADC": "원딜",
    "UTILITY": "서폿",
    "SUPPORT": "서폿",
    "ARAM": "칼바람",
    "UNKNOWN": "미상",
    "NONE": "없음",
}

MODE_KO: dict[str, str] = {
    "Ranked Solo": "솔로 랭크",
    "Ranked Flex": "자유 랭크",
    "Normal Draft": "일반 드래프트",
    "Normal Blind": "일반 블라인드",
    "Summoner's Rift": "소환사의 협곡",
    "ARAM": "칼바람",
    "ARAM Mayhem": "아수라장",
    "ARAM Clash": "칼바람 격전",
    "ARAM (Bridge)": "칼바람 (다리)",
    "Clash": "격전",
    "ARAM / ARAM Mayhem": "칼바람 · 아수라장",
    "other": "기타",
}

# 자주 쓰이는 아이템 별칭 (blitz.gg 축약/구명칭 대응)
ITEM_ALIAS_KO: dict[str, str] = {
    # 신발
    "ionian boots of lucidity": "명석함의 아이오니아 장화",
    "crimson lucidity": "명석함의 아이오니아 장화",
    "crimson lucidity quest reward": "명석함의 아이오니아 장화",
    "ionian boots": "명석함의 아이오니아 장화",
    "sorcerer's shoes": "마법사의 신발",
    "sorcerers shoes": "마법사의 신발",
    "mercury's treads": "헤르메스의 발걸음",
    "mercurys treads": "헤르메스의 발걸음",
    "plated steelcaps": "판금 장화",
    "berserker's greaves": "광전사의 군화",
    "berserkers greaves": "광전사의 군화",
    "boots of swiftness": "신속의 장화",
    "slightly magical footwear": "약간 신비한 신발",
    "spellslinger's shoes": "주문사의 신발",
    "spellslingers shoes": "주문사의 신발",
    "boots": "장화",
    # 핵심 전설/신화급
    "ludens echo": "루덴의 메아리",
    "luden's echo": "루덴의 메아리",
    "luden's companion": "루덴의 동반자",
    "ludens companion": "루덴의 동반자",
    "blackfire torch": "어둠불꽃 횃불",
    "death's dance": "죽음의 무도",
    "deaths dance": "죽음의 무도",
    "liandry's torment": "리안드리의 고통",
    "liandry's anguish": "리안드리의 고뇌",
    "liandrys torment": "리안드리의 고통",
    "liandrys anguish": "리안드리의 고뇌",
    "riftmaker": "균열 생성기",
    "shadowflame": "그림자불꽃",
    "zhonya's hourglass": "존야의 모래시계",
    "zhonyas hourglass": "존야의 모래시계",
    "banshee's veil": "밴시의 장막",
    "banshees veil": "밴시의 장막",
    "rabadon's deathcap": "라바돈의 죽음모자",
    "rabadons deathcap": "라바돈의 죽음모자",
    "void staff": "공허의 지팡이",
    "morellonomicon": "모렐로노미콘",
    "horizon focus": "지평선의 초점",
    "cosmic drive": "우주적 추진력",
    "cryptbloom": "크립트블룸",
    "stormsurge": "폭풍쇄도",
    "malignance": "악의",
    "bloodletter's curse": "피의 저주",
    "bloodletters curse": "피의 저주",
    "mejai's soulstealer": "메자이의 영혼약탈자",
    "mejais soulstealer": "메자이의 영혼약탈자",
    "nashor's tooth": "내셔의 이빨",
    "nashors tooth": "내셔의 이빨",
    "lich bane": "리치베인",
    "hextech rocketbelt": "마법공학 로켓 벨트",
    "night harvester": "밤의 수확자",
    "everfrost": "영겁의 지팡이",
    "crown of the shattered queen": "부서진 여왕의 왕관",
    "rod of ages": "영겁의 지팡이",
    "seraph's embrace": "대천사의 포옹",
    "seraphs embrace": "대천사의 포옹",
    "archangel's staff": "대천사의 지팡이",
    "archangels staff": "대천사의 지팡이",
    "tear of the goddess": "여신의 눈물",
    "doran's ring": "도란의 반지",
    "dorans ring": "도란의 반지",
    "doran's blade": "도란의 검",
    "dorans blade": "도란의 검",
    "doran's shield": "도란의 방패",
    "dorans shield": "도란의 방패",
    "health potion": "체력 물약",
    "refillable potion": "충전형 물약",
    "dark seal": "암흑의 인장",
    "seeker's armguard": "추적자의 팔목 보호대",
    "seekers armguard": "추적자의 팔목 보호대",
    "infinity edge": "무한의 대검",
    "kraken slayer": "크라켄 학살자",
    "collector": "수집가",
    "the collector": "수집가",
    "lord dominik's regards": "도미닉 경의 인사",
    "lord dominiks regards": "도미닉 경의 인사",
    "mortal reminder": "필멸자의 운명",
    "bloodthirster": "피바라기",
    "guinsoo's rageblade": "구인수의 격노검",
    "guinsoos rageblade": "구인수의 격노검",
    "blade of the ruined king": "몰락한 왕의 검",
    "trinity force": "삼위일체",
    "divine sunderer": "신성한 파괴자",
    "eclipse": "월식",
    "youmuu's ghostblade": "요우무의 유령검",
    "youmuus ghostblade": "요우무의 유령검",
    "opportunity": "기회",
    "hubris": "오만",
    "profane hydra": "불경한 히드라",
    "ravenous hydra": "굶주린 히드라",
    "titanic hydra": "거대한 히드라",
    "sterak's gage": "스테락의 도전",
    "steraks gage": "스테락의 도전",
    "black cleaver": "검은 도끼",
    "sundered sky": "갈라진 하늘",
    "stridebreaker": "발걸음 분쇄기",
    "goredrinker": "선혈포식자",
    "heartsteel": "강철심장",
    "jak'sho the protean": "자크쇼",
    "jaksho": "자크쇼",
    "sunfire aegis": "태양불꽃 방패",
    "hollow radiance": "공허한 광휘",
    "thornmail": "가시 갑옷",
    "randuin's omen": "란두인의 예언",
    "randuins omen": "란두인의 예언",
    "force of nature": "대자연의 힘",
    "spirit visage": "영혼의 형상",
    "warmog's armor": "워모그의 갑옷",
    "warmogs armor": "워모그의 갑옷",
    "kaenic rookern": "카에닉 루커른",
    "abyssal mask": "심연의 가면",
    "locket of the iron solari": "강철의 솔라리 펜던트",
    "knight's vow": "기사의 맹세",
    "knights vow": "기사의 맹세",
    "redemption": "구원",
    "moonstone renewer": "월석 재생기",
    "imperial mandate": "제국의 명령",
    "shurelya's battlesong": "슈렐리아의 군가",
    "shurelyas battlesong": "슈렐리아의 군가",
    "echoes of helia": "헬리아의 메아리",
    "dream maker": "꿈 제작자",
    "staff of flowing water": "흐르는 물의 지팡이",
    "ardent censer": "열정의 향로",
    "chemtech putrifier": "화학공학 부패기",
    "mikael's blessing": "미카엘의 축복",
    "mikaels blessing": "미카엘의 축복",
    "warden's mail": "파수꾼의 갑옷",
    "wardens mail": "파수꾼의 갑옷",
    "null magic mantle": "음전기 망토",
    "cloth armor": "천 갑옷",
    "ruby crystal": "루비 수정",
    "sapphire crystal": "사파이어 수정",
    "amplifying tome": "증폭의 고서",
    "blasting wand": "방출의 마법봉",
    "needlessly large rod": "쓸데없이 큰 지팡이",
    "fiendish codex": "악마의 고서",
    "aether wisp": "에테르 위습",
    "lost chapter": "사라진 두루마리",
    "catalyst of aeons": "영겁의 촉매",
    "hextech alternator": "마법공학 교류 발전기",
    "recurve bow": "곡궁",
    "bf sword": "B.F. 대검",
    "pickaxe": "곡괭이",
    "long sword": "롱소드",
    "vampiric scepter": "흡혈의 낫",
    "caulfield's warhammer": "콜필드의 전투 망치",
    "caulfields warhammer": "콜필드의 전투 망치",
    "serrated dirk": "톱날 단검",
    "last whisper": "최후의 속삭임",
    "executioner's calling": "처형인의 호출",
    "executioners calling": "처형인의 호출",
    "control ward": "제어 와드",
    "stealth ward": "투명 와드",
    "farsight alteration": "예언자의 렌즈",
    "oracle lens": "예언자의 렌즈",
}


def _norm_key(name: str) -> str:
    """Normalize for fuzzy English→Korean lookup."""
    s = name.strip().lower()
    s = s.replace("’", "'").replace("`", "'")
    # strip common blitz prefixes already cleaned, plus leftovers
    for prefix in (
        "the keystone ",
        "the rune tree ",
        "the rune ",
        "the ",
        "summoner spell ",
        "summoner ",
    ):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    if s.endswith(" shard"):
        s = s[: -len(" shard")]
    # drop quest reward fluff from boots text
    s = re.sub(r"\s*quest reward\s*", " ", s, flags=re.I)
    s = re.sub(r"[^a-z0-9'+]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class KoreanLocalizer:
    """Translate game entity names to Korean via Data Dragon ko_KR."""

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "lol-personal-coach/0.1"})
        self._version: str | None = None
        self._loaded = False

        # id → ko name
        self._item_ko: dict[int, str] = {}
        self._rune_ko: dict[int, str] = {}
        self._spell_ko: dict[int, str] = {}
        self._champ_ko: dict[int, str] = {}
        self._champ_key_ko: dict[str, str] = {}  # Ahri → 아리

        # normalized en name → ko name
        self._item_en2ko: dict[str, str] = {}
        self._rune_en2ko: dict[str, str] = {}
        self._spell_en2ko: dict[str, str] = {}
        self._champ_en2ko: dict[str, str] = {}

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
        en = self._fetch_json(f"/cdn/{ver}/data/en_US")
        ko = self._fetch_json(f"/cdn/{ver}/data/ko_KR")

        # ── items ──
        for iid, en_item in en["item"]["data"].items():
            ko_item = ko["item"]["data"].get(iid)
            if not ko_item:
                continue
            kid = int(iid)
            en_name = en_item["name"]
            ko_name = ko_item["name"]
            self._item_ko[kid] = ko_name
            self._item_en2ko[_norm_key(en_name)] = ko_name
            # also map without apostrophes variants
            self._item_en2ko[_norm_key(en_name.replace("'", ""))] = ko_name

        # ── champions ──
        for key, en_c in en["champion"]["data"].items():
            ko_c = ko["champion"]["data"].get(key)
            if not ko_c:
                continue
            cid = int(en_c["key"])
            self._champ_ko[cid] = ko_c["name"]
            self._champ_key_ko[key.lower()] = ko_c["name"]
            self._champ_en2ko[_norm_key(en_c["name"])] = ko_c["name"]
            self._champ_en2ko[_norm_key(key)] = ko_c["name"]
            slug = re.sub(r"[^a-z0-9]", "", en_c["name"].lower())
            self._champ_en2ko[slug] = ko_c["name"]

        # ── summoner spells ──
        for key, en_s in en["summoner"]["data"].items():
            ko_s = ko["summoner"]["data"].get(key)
            if not ko_s:
                continue
            sid = int(en_s["key"])
            en_name = en_s["name"]
            ko_name = ko_s["name"]
            self._spell_ko[sid] = ko_name
            self._spell_en2ko[_norm_key(en_name)] = ko_name
            # "SummonerFlash" → flash
            short = re.sub(r"^summoner", "", key, flags=re.I)
            self._spell_en2ko[_norm_key(short)] = ko_name
            # strip common english display without "Summoner"
            bare = re.sub(r"^summoner\s*", "", en_name, flags=re.I)
            self._spell_en2ko[_norm_key(bare)] = ko_name

        # ── runes ──
        for en_tree, ko_tree in zip(
            en["runesReforged"], ko["runesReforged"], strict=False
        ):
            style_id = int(en_tree["id"])
            self._rune_ko[style_id] = ko_tree["name"]
            self._rune_en2ko[_norm_key(en_tree["name"])] = ko_tree["name"]
            self._rune_en2ko[_norm_key(en_tree.get("key", ""))] = ko_tree["name"]

            for en_slot, ko_slot in zip(
                en_tree.get("slots", []), ko_tree.get("slots", []), strict=False
            ):
                for en_r, ko_r in zip(
                    en_slot.get("runes", []),
                    ko_slot.get("runes", []),
                    strict=False,
                ):
                    rid = int(en_r["id"])
                    self._rune_ko[rid] = ko_r["name"]
                    self._rune_en2ko[_norm_key(en_r["name"])] = ko_r["name"]
                    if en_r.get("key"):
                        self._rune_en2ko[_norm_key(en_r["key"])] = ko_r["name"]

        # seed shard + style + item alias fallbacks
        for alias, ko_name in SHARD_KO.items():
            self._rune_en2ko.setdefault(alias, ko_name)
        for alias, ko_name in STYLE_KO.items():
            self._rune_en2ko.setdefault(alias, ko_name)
        for alias, ko_name in SPELL_KO.items():
            self._spell_en2ko.setdefault(alias, ko_name)
        # 별칭은 공식 데이터보다 우선 (blitz.gg 축약/퀘스트 표기 대응)
        for alias, ko_name in ITEM_ALIAS_KO.items():
            self._item_en2ko[alias] = ko_name

        self._loaded = True

    def _fetch_json(self, prefix: str) -> dict:
        """prefix like /cdn/14.1.1/data/en_US — loads item, champion, summoner, runes."""
        parts = prefix.split("/")
        ver = parts[2]
        lang = parts[4]
        base = f"{DDRAGON_BASE}{prefix}"
        out: dict = {}
        for name, path in (
            ("item", f"{base}/item.json"),
            ("champion", f"{base}/champion.json"),
            ("summoner", f"{base}/summoner.json"),
            ("runesReforged", f"{base}/runesReforged.json"),
        ):
            out[name] = ddragon_cache.get_json(
                self.session, path, f"{ver}:{lang}:{name}", timeout=self.timeout
            )
        return out

    # ── public translators ────────────────────────────────────────────

    def item(self, name_or_id: str | int | None) -> str:
        if name_or_id is None or name_or_id == "":
            return ""
        self.ensure_loaded()
        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and name_or_id.isdigit()
        ):
            return self._item_ko.get(int(name_or_id), "")
        raw = str(name_or_id).strip()
        low = raw.lower()
        if low in (
            "build this every game",
            "best for most matchups",
            "quest reward",
            "options after core build",
        ):
            return ""
        if "build this" in low or "best for most" in low:
            return ""
        # strip quest reward then translate
        cleaned = re.sub(r"(?i)\s*quest reward\s*", " ", raw).strip()
        if not cleaned:
            return ""
        key = _norm_key(cleaned)
        if key in ITEM_ALIAS_KO:
            return ITEM_ALIAS_KO[key]
        if key in self._item_en2ko:
            return self._item_en2ko[key]
        hit = self._fuzzy(key, self._item_en2ko)
        if hit and re.search(r"[가-힣]", hit):
            return hit
        # 이미 한글이면 그대로
        if re.search(r"[가-힣]", raw):
            return raw
        # 영문 잔여 → 빈 문자열 (출력에서 숨김)
        return ""

    def items_strict(self, names: Iterable[str | int]) -> list[str]:
        """한글 번역된 아이템만 (영문 잔여 제외)."""
        out: list[str] = []
        for n in names:
            ko = self.item(n)
            if ko and re.search(r"[가-힣]", ko):
                out.append(ko)
        return out

    def rune(self, name_or_id: str | int | None) -> str:
        if name_or_id is None or name_or_id == "":
            return ""
        self.ensure_loaded()
        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and str(name_or_id).isdigit()
        ):
            return self._rune_ko.get(int(name_or_id), f"룬#{name_or_id}")
        raw = str(name_or_id).strip()
        key = _norm_key(raw)
        if key in self._rune_en2ko:
            return self._rune_en2ko[key]
        if key in SHARD_KO:
            return SHARD_KO[key]
        hit = self._fuzzy(key, self._rune_en2ko)
        return hit or raw

    def spell(self, name_or_id: str | int | None) -> str:
        if name_or_id is None or name_or_id == "":
            return ""
        self.ensure_loaded()
        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and str(name_or_id).isdigit()
        ):
            return self._spell_ko.get(int(name_or_id), f"주문#{name_or_id}")
        raw = str(name_or_id).strip()
        key = _norm_key(raw)
        if key in self._spell_en2ko:
            return self._spell_en2ko[key]
        if key in SPELL_KO:
            return SPELL_KO[key]
        hit = self._fuzzy(key, self._spell_en2ko)
        return hit or raw

    def champion(self, name_or_id: str | int | None) -> str:
        if name_or_id is None or name_or_id == "":
            return ""
        self.ensure_loaded()
        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and str(name_or_id).isdigit()
        ):
            return self._champ_ko.get(int(name_or_id), f"챔피언#{name_or_id}")
        raw = str(name_or_id).strip()
        key = _norm_key(raw)
        slug = re.sub(r"[^a-z0-9]", "", key)
        if key in self._champ_en2ko:
            return self._champ_en2ko[key]
        if slug in self._champ_en2ko:
            return self._champ_en2ko[slug]
        if slug in self._champ_key_ko:
            return self._champ_key_ko[slug]
        hit = self._fuzzy(key, self._champ_en2ko)
        return hit or raw

    def items(self, names: Iterable[str | int]) -> list[str]:
        return self.items_strict(names)

    def runes(self, names: Iterable[str | int]) -> list[str]:
        return [self.rune(n) for n in names if n]

    def spells(self, names: Iterable[str | int]) -> list[str]:
        return [self.spell(n) for n in names if n]

    def role(self, role: str) -> str:
        if not role:
            return ""
        return ROLE_KO.get(role.upper(), ROLE_KO.get(role, role))

    def mode(self, label: str) -> str:
        if not label:
            return ""
        if label in MODE_KO:
            return MODE_KO[label]
        # Queue 123 fallback
        if label.startswith("Queue "):
            return f"큐 {label.split(' ', 1)[1]}"
        low = label.lower()
        if "mayhem" in low:
            return "아수라장"
        if "aram" in low:
            return "칼바람"
        if "summoner" in low or "rift" in low:
            return "소환사의 협곡"
        if "ranked solo" in low:
            return "솔로 랭크"
        if "ranked flex" in low:
            return "자유 랭크"
        if re.search(r"[가-힣]", label):
            return label
        return label

    def looks_english(self, text: str) -> bool:
        if not text:
            return False
        # mostly latin letters → still English
        letters = re.findall(r"[A-Za-z]", text)
        hangul = re.findall(r"[가-힣]", text)
        return len(letters) >= 3 and len(hangul) == 0

    @staticmethod
    def _fuzzy(key: str, table: dict[str, str]) -> str | None:
        if not key or len(key) < 3:
            return None
        # exact-ish containment
        candidates: list[tuple[int, str]] = []
        for en, ko in table.items():
            if not en:
                continue
            if key == en:
                return ko
            if key in en or en in key:
                candidates.append((len(en), ko))
        if candidates:
            # prefer closest length match
            candidates.sort(key=lambda x: abs(x[0] - len(key)))
            return candidates[0][1]
        return None


@lru_cache(maxsize=1)
def get_localizer() -> KoreanLocalizer:
    return KoreanLocalizer()
