"""소환사의 협곡 — 적 조합 분석 · 오브젝트 · 시추에이셔널 아이템."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lol_coach.blitz.models import ChampionBuild, CounterPick, CounterReport
from lol_coach.static.ddragon import DataDragon
from lol_coach.static.i18n import get_localizer

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
class CompReport:
    my_role: str
    my_champ_ko: str
    enemy_lane_ko: str
    enemy_team: list[tuple[str, str]]  # (역할한글, 챔프한글)
    patch: str
    counters: list[tuple[str, CounterPick]]
    threats: list[str] = field(default_factory=list)
    midgame: list[str] = field(default_factory=list)
    core_items: list[str] = field(default_factory=list)
    situational: list[tuple[str, str]] = field(default_factory=list)  # (아이템, 이유)
    runes_line: str = ""
    spells_line: str = ""
    skill_line: str = ""
    action_plan: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)


class CompAnalyzer:
    def __init__(self, ddragon: DataDragon | None = None):
        self.dd = ddragon or DataDragon(language="ko_KR")
        self.loc = get_localizer()

    def _tags(self, name: str) -> set[str]:
        c = self.dd.resolve_champion(name)
        if not c:
            return set()
        return set(c.get("tags") or [])

    def _name_ko(self, name: str) -> str:
        return self.loc.champion(name) or name

    def analyze(
        self,
        *,
        my_role: str,
        enemy_lane: str,
        my_champ: str | None = None,
        enemy_jg: str | None = None,
        enemy_sup: str | None = None,
        enemy_top: str | None = None,
        enemy_mid: str | None = None,
        enemy_adc: str | None = None,
        counter_report: CounterReport | None = None,
        my_build: ChampionBuild | None = None,
    ) -> CompReport:
        self.dd.ensure_loaded()
        self.loc.ensure_loaded()
        role = my_role.lower()
        role_ko = ROLE_KO.get(role, role)

        # Build enemy roster with labels
        roster: list[tuple[str, str, str]] = []  # role_key, en_or_key, ko
        def add(rk: str, champ: str | None) -> None:
            if not champ or not champ.strip():
                return
            c = self.dd.resolve_champion(champ.strip())
            key = c["id"] if c else champ.strip()
            ko = c["name"] if c else champ.strip()
            roster.append((rk, key, ko))

        # Lane opponent always present
        lane_c = self.dd.resolve_champion(enemy_lane)
        lane_key = lane_c["id"] if lane_c else enemy_lane
        lane_ko = lane_c["name"] if lane_c else enemy_lane
        # map role of enemy laner roughly opposite of my role
        enemy_lane_role = {
            "top": "top",
            "jungle": "jungle",
            "mid": "mid",
            "middle": "mid",
            "adc": "adc",
            "bottom": "adc",
            "support": "support",
        }.get(role, "mid")
        roster.append((enemy_lane_role, lane_key, lane_ko))

        add("jungle", enemy_jg)
        add("support", enemy_sup)
        add("top", enemy_top)
        add("mid", enemy_mid)
        add("adc", enemy_adc)

        # dedupe by champ key keep first
        seen = set()
        unique: list[tuple[str, str, str]] = []
        for rk, key, ko in roster:
            k = key.lower()
            if k in seen:
                continue
            seen.add(k)
            unique.append((rk, key, ko))

        my_ko = ""
        my_key = ""
        if my_champ:
            mc = self.dd.resolve_champion(my_champ)
            if mc:
                my_key, my_ko = mc["id"], mc["name"]
            else:
                my_key, my_ko = my_champ, my_champ

        counters: list[tuple[str, CounterPick]] = []
        patch = "—"
        urls: list[str] = []
        if counter_report:
            patch = counter_report.patch
            urls.append(counter_report.source_url)
            for c in counter_report.lane_counters[:8]:
                counters.append((self._name_ko(c.champion), c))

        core: list[str] = []
        runes = spells = skills = ""
        if my_build:
            patch = my_build.patch or patch
            if my_build.source_url:
                urls.append(my_build.source_url)
            core = self.loc.items(my_build.core_items.items)
            boots = self.loc.items(my_build.boots.items)
            # 신발은 보통 1~2코어 사이 — 중복 없이 삽입
            if boots:
                boot = boots[0]
                if boot not in core:
                    if len(core) >= 1:
                        core = core[:1] + [boot] + core[1:]
                    else:
                        core = [boot]
            # u.gg 코어가 2개뿐인 경우가 많아 situational로 3~5코어 보강
            for sec in my_build.situational or []:
                for name in self.loc.items(sec.items):
                    if name and name not in core:
                        core.append(name)
                    if len(core) >= 5:
                        break
                if len(core) >= 5:
                    break
            core = core[:5]
            if my_build.runes.keystone:
                runes = (
                    f"{self.loc.rune(my_build.runes.keystone)} "
                    f"({self.loc.rune(my_build.runes.primary_tree)}+"
                    f"{self.loc.rune(my_build.runes.secondary_tree)})"
                )
                main = " · ".join(self.loc.runes(my_build.runes.primary_runes))
                if main:
                    runes += f"  |  {main}"
            if my_build.summoner_spells:
                spells = " + ".join(self.loc.spells(my_build.summoner_spells))
            if my_build.skills.priority:
                skills = " › ".join(my_build.skills.priority)

        threats = self._threats(unique, role)
        midgame = self._midgame(unique, role, lane_ko)
        situ = self._situational_items(unique, my_key or my_champ or "")
        plan = self._action_plan(
            role_ko, my_ko, lane_ko, unique, counters, core, situ
        )

        return CompReport(
            my_role=role_ko,
            my_champ_ko=my_ko or "(미선택)",
            enemy_lane_ko=lane_ko,
            enemy_team=[(ROLE_KO.get(rk, rk), ko) for rk, _k, ko in unique],
            patch=patch,
            counters=counters,
            threats=threats,
            midgame=midgame,
            core_items=core,
            situational=situ,
            runes_line=runes,
            spells_line=spells,
            skill_line=skills,
            action_plan=plan,
            source_urls=urls,
        )

    def _threats(
        self, roster: list[tuple[str, str, str]], my_role: str
    ) -> list[str]:
        tips: list[str] = []
        tags_all: Counter[str] = Counter()
        by_role: dict[str, set[str]] = {}
        for rk, key, _ko in roster:
            t = self._tags(key)
            by_role[rk] = t
            for x in t:
                tags_all[x] += 1

        # jungle gank pressure
        jg = next((x for x in roster if x[0] == "jungle"), None)
        if jg:
            jg_tags = by_role.get("jungle", set())
            jg_ko = jg[2]
            if "Assassin" in jg_tags or "Fighter" in jg_tags:
                tips.append(
                    f"정글 {jg_ko}: 초반 갱·다이브 압박이 큽니다. "
                    "강가 부시 와드 + 2레벨 동선을 먼저 읽으세요."
                )
            elif "Mage" in jg_tags:
                tips.append(
                    f"정글 {jg_ko}: 오브젝트·카정 성향. "
                    "용/전령 타이밍 시야를 아끼지 마세요."
                )
            else:
                tips.append(
                    f"정글 {jg_ko} 개입 가정: 라인 우선권 없을 때 "
                    "깊게 밀지 말고 강가를 비우세요."
                )
        else:
            tips.append(
                "적 정글 미입력 — 기본적으로 강가 와드 후 푸시하세요. "
                "실종 핑이 오면 뒤로 빼는 습관을 고정하세요."
            )

        sup = next((x for x in roster if x[0] == "support"), None)
        if sup:
            st = by_role.get("support", set())
            sk = sup[2]
            if "Tank" in st or "Fighter" in st:
                tips.append(
                    f"서폿 {sk}: 이니시/로밍형. 봇 우선권 밀리면 "
                    "미드·탑 강가 갱을 항상 가정하세요."
                )
            elif "Mage" in st or "Marksman" in st:
                tips.append(
                    f"서폿 {sk}: 포킹/견제형. 한타 전 포킹 구간에서 "
                    "체력을 깎이지 않게 진형을 잡으세요."
                )
            else:
                tips.append(f"서폿 {sk} 로밍 각을 미니맵으로 체크하세요.")

        # damage profile
        ap = tags_all.get("Mage", 0)
        ad = tags_all.get("Marksman", 0) + tags_all.get("Fighter", 0)
        ass = tags_all.get("Assassin", 0)
        tank = tags_all.get("Tank", 0)
        if ap >= 3:
            tips.append("적 조합 AP 비중이 높습니다. 마저 신발·존야·포스 오브 네이처 타이밍을 앞당기세요.")
        if ad >= 3:
            tips.append("적 조합 AD/크리 비중이 높습니다. 판금·란두인·가시갑옷을 후보에 두세요.")
        if ass >= 2:
            tips.append("암살자가 2명 이상입니다. 시야 없는 전진 금지, 존야/수호천사·스쿼시 보호가 핵심입니다.")
        if tank >= 2:
            tips.append("탱커가 두껍습니다. 방관/%체력(리안드리·보크·도미닉) 없이는 한타가 늘어집니다.")

        return tips[:6]

    def _midgame(
        self,
        roster: list[tuple[str, str, str]],
        my_role: str,
        lane_ko: str,
    ) -> list[str]:
        tips: list[str] = []
        tags_all: Counter[str] = Counter()
        names = []
        for _rk, key, ko in roster:
            names.append(ko)
            for t in self._tags(key):
                tags_all[t] += 1

        tips.append(
            f"라인전 이후: {lane_ko} 실종 시 즉시 핑. "
            "혼자 사이드 밀기보다 시야 잡고 그룹하세요."
        )

        # dragon / baron
        engage = tags_all.get("Tank", 0) + tags_all.get("Fighter", 0)
        poke = tags_all.get("Mage", 0)
        if engage >= 2:
            tips.append(
                "적 이니시가 강합니다. 용·바론 둥지에서 먼저 들어가지 말고, "
                "시야 깔고 받아치기 구도를 만드세요."
            )
        else:
            tips.append(
                "적 이니시가 약하면 오브젝트 선점·시야 장악이 유리합니다. "
                "전령/용 스폰 40초 전 강가 와드를 박으세요."
            )

        if poke >= 2:
            tips.append(
                "포킹 조합 상대: 한타 전 체력 관리가 승부. "
                "강제 이니시 각이 없으면 억지 한타를 피하세요."
            )

        tips.append(
            "용 스택 2 이상이면 억지 싸움 가치↑, "
            "바론은 시야 없이 치지 말고 시야 전투부터 이기세요."
        )

        if my_role in ("mid", "middle", "adc", "bottom"):
            tips.append(
                "중반 사이드: 텔레포트/합류 가능한 아군과 타이밍을 맞추고, "
                "2명 이상 실종이면 타워를 포기하세요."
            )
        if my_role == "jungle":
            tips.append(
                "정글 중반: 상대 정글 동선 역이용 + 오브젝트 스폰 동선 고정. "
                "이득 라인에 캠프를 두세요."
            )
        if my_role == "support":
            tips.append(
                "서폿 중반: 와드  liberating(시야 전쟁)이 본업. "
                "원딜 백핑 후 강가·바론 시야를 순환하세요."
            )

        # clean accidental english
        tips = [t.replace("와드  liberating(시야 전쟁)", "와드·시야 전쟁") for t in tips]
        return tips[:5]

    def _situational_items(
        self, roster: list[tuple[str, str, str]], my_champ: str
    ) -> list[tuple[str, str]]:
        tags_all: Counter[str] = Counter()
        for _rk, key, _ko in roster:
            for t in self._tags(key):
                tags_all[t] += 1

        my_tags = self._tags(my_champ) if my_champ else set()
        situ: list[tuple[str, str]] = []

        ap = tags_all.get("Mage", 0)
        ad = tags_all.get("Marksman", 0) + tags_all.get("Fighter", 0)
        ass = tags_all.get("Assassin", 0)
        tank = tags_all.get("Tank", 0)
        heal_like = tags_all.get("Fighter", 0)  # rough

        if ap >= 2:
            if "Mage" in my_tags or "Assassin" in my_tags:
                situ.append(("헤르메스의 발걸음", "AP·CC 상대 기본 신발"))
                situ.append(("존야의 모래시계", "암살·누킹 한 방 넘기기"))
            else:
                situ.append(("헤르메스의 발걸음", "마법 피해·CC 감소"))
                situ.append(("대자연의 힘", "지속 AP 한타"))
                situ.append(("카에닉 루커른", "폭발 마법 피해 흡수"))
        if ad >= 2 or tags_all.get("Marksman", 0) >= 1:
            situ.append(("판금 장화", "AD·평타 압박"))
            if tags_all.get("Marksman", 0) >= 1:
                situ.append(("란두인의 예언", "크리 원딜 한타"))
            situ.append(("가시 갑옷", "평타·흡혈 라인 견제"))
        if ass >= 1:
            situ.append(("수호 천사", "암살 각 한 번 넘기기"))
            if "Mage" in my_tags:
                situ.append(("존야의 모래시계", "암살 콤보 무력화"))
        if tank >= 1:
            if "Mage" in my_tags:
                situ.append(("리안드리의 고통", "탱 녹이는 지속 마법 피해"))
                situ.append(("공허의 지팡이", "마저 스택 관통"))
            if "Marksman" in my_tags or "Fighter" in my_tags:
                situ.append(("몰락한 왕의 검", "%체력 물리"))
                situ.append(("도미닉 경의 인사", "탱 방관"))
            if "Fighter" in my_tags:
                situ.append(("검은 도끼", "방깎 + 이속"))
        if heal_like >= 2:
            situ.append(("모렐로노미콘", "치유 감소(마법)"))
            situ.append(("처형인의 호출 → 가시/필멸", "치유 감소(물리)"))

        # always useful
        if not situ:
            situ.append(("상황 방어 옵션", "상대 주 딜 타입 보고 마저/방 선택"))

        # dedupe by item name keep order
        out: list[tuple[str, str]] = []
        seen = set()
        for item, why in situ:
            if item in seen:
                continue
            seen.add(item)
            out.append((item, why))
        return out[:7]

    def _action_plan(
        self,
        role_ko: str,
        my_ko: str,
        lane_ko: str,
        roster: list[tuple[str, str, str]],
        counters: list[tuple[str, CounterPick]],
        core: list[str],
        situ: list[tuple[str, str]],
    ) -> list[str]:
        plan: list[str] = []
        if my_ko and my_ko != "(미선택)":
            plan.append(f"픽: {my_ko} ({role_ko}) — {lane_ko} 라인 구도 기준")
        else:
            if counters:
                names = ", ".join(n for n, _ in counters[:3])
                plan.append(f"라인 카운터 후보: {names}")
            plan.append(f"포지션 {role_ko} · 상대 라이너 {lane_ko}")

        plan.append("초반: 강가 와드 → 3·6 타이밍 교환 → 정글/서폿 실종 시 후퇴")
        plan.append("중반: 용 스폰 40초 전 시야 → 억지 바론 금지 → 그룹 핑")
        if core:
            plan.append(f"코어 루트(1~5): {' → '.join(core[:5])}")
        if situ:
            plan.append(f"상황템 1순위: {situ[0][0]} ({situ[0][1]})")
        return plan
