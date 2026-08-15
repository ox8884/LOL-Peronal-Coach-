"""Riot Games API client (Account V1, Summoner V4, Match V5, League V4, Spectator V5)."""

from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from lol_coach.config import (
    PLATFORM_TO_REGION,
    SUPPORTED_REGIONS,
    InvalidPlatformError,
    normalize_platform,
    normalize_region,
)
from lol_coach.http_security import (
    MAX_RIOT_RESPONSE_BYTES,
    read_limited_json,
    read_limited_text,
    secure_session,
)
from lol_coach.log import get_logger
from lol_coach.modes import queues_for_mode
from lol_coach.riot.models import (
    ChampionStats,
    FormProvenance,
    LiveGame,
    MatchObjectives,
    MatchPlayer,
    MatchSummary,
    ModeBucketStats,
    PlayerProfile,
    RankInfo,
    RecentForm,
    SideObjectives,
)

_log = get_logger("riot")

# PUUID/summoner-id 등 식별자 마스킹 — 로그에 PII 유출 방지
_PUUID_RE = re.compile(r"/(by-puuid|by-summoner|active-games/by-summoner)/[A-Za-z0-9_-]{20,}")


def _redact_url(url: str) -> str:
    """URL 경로에서 PUUID/summoner-id 세그먼트를 마스킹."""
    return _PUUID_RE.sub(r"/\1/***", url)


ROLE_NORMALIZE = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MIDDLE",
    "MID": "MIDDLE",
    "BOTTOM": "BOTTOM",
    "ADC": "BOTTOM",
    "UTILITY": "UTILITY",
    "SUPPORT": "UTILITY",
    "NONE": "UNKNOWN",
    "": "UNKNOWN",
}


class RiotAPIError(Exception):
    def __init__(self, status_code: int, message: str, url: str = ""):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"[{status_code}] {message}")


class RiotClient:
    """Thin wrapper around Riot REST endpoints with retries & rate-limit sleep."""

    def __init__(
        self,
        api_key: str,
        platform: str = "na1",
        region: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        max_workers: int = 4,
        use_cache: bool = True,
    ):
        self.api_key = api_key.strip()
        self.platform = normalize_platform(platform)
        self.region = normalize_region(region or self.default_region(self.platform))
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max(1, int(max_workers))
        self.use_cache = use_cache
        try:
            from lol_coach import __version__ as _ver
        except Exception:  # pragma: no cover
            _ver = "dev"
        self.session = secure_session()
        self.session.headers.update(
            {
                "X-Riot-Token": self.api_key,
                "Accept": "application/json",
                "User-Agent": f"lol-personal-coach/{_ver}",
            }
        )
        self._last_prune_at = 0.0

    @staticmethod
    def default_region(platform: str) -> str:
        """platform 코드 → regional routing (asia/americas/europe/sea)."""
        return PLATFORM_TO_REGION[normalize_platform(platform)]

    # 하위 호환 별칭
    _default_region = default_region

    def set_platform(self, platform: str) -> None:
        """플랫폼 변경 + 라우팅 리전 동기화 (검증 포함)."""
        self.platform = normalize_platform(platform)
        self.region = self.default_region(self.platform)

    def _host(self, routing: str) -> str:
        normalized = routing.strip().lower()
        if normalized not in PLATFORM_TO_REGION and normalized not in SUPPORTED_REGIONS:
            raise InvalidPlatformError(routing)
        return f"https://{normalized}.api.riotgames.com"

    def _get(self, url: str, params: dict | None = None) -> Any:
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.timeout, stream=True, allow_redirects=False
                )
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(0.5 * (attempt + 1))
                continue

            if resp.status_code == 200:
                return read_limited_json(resp, MAX_RIOT_RESPONSE_BYTES)
            if resp.status_code == 429:
                try:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                except (TypeError, ValueError):
                    retry_after = 2.0
                if not math.isfinite(retry_after):
                    retry_after = 2.0
                # 비정상적으로 큰 값이 와도 무한 대기하지 않도록 상한
                retry_after = min(max(retry_after, 0.0), 60.0)
                _log.debug("429 rate limit — %.2fs 대기: %s", retry_after, _redact_url(url))
                time.sleep(retry_after + 0.25)
                continue

            if resp.status_code in (500, 502, 503, 504):
                _log.debug("%s 서버 오류 — 재시도 %d: %s", resp.status_code, attempt + 1, _redact_url(url))
                time.sleep(0.75 * (attempt + 1))
                continue

            # Client errors
            msg = read_limited_text(resp, MAX_RIOT_RESPONSE_BYTES)
            if resp.status_code in (401, 403):
                msg = (
                    f"{msg}\n\n"
                    "API 키가 만료되었거나 올바르지 않을 수 있습니다.\n"
                    "Riot 개발자 포털(https://developer.riotgames.com/)에서\n"
                    "Development API 키를 다시 발급받아 설정해 주세요.\n"
                    "(Development 키는 24시간마다 만료됩니다)"
                )
            raise RiotAPIError(resp.status_code, msg, url)

        if last_err:
            raise RiotAPIError(0, f"Network error: {last_err}", url)
        raise RiotAPIError(0, "Max retries exceeded", url)

    # ── Account / Summoner ────────────────────────────────────────────

    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> dict:
        g = quote(game_name, safe="")
        t = quote(tag_line, safe="")
        url = f"{self._host(self.region)}/riot/account/v1/accounts/by-riot-id/{g}/{t}"
        return self._get(url)

    def get_summoner_by_puuid(self, puuid: str) -> dict:
        url = f"{self._host(self.platform)}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return self._get(url)

    def resolve_player(self, game_name: str, tag_line: str) -> PlayerProfile:
        """Riot ID → PUUID (+ optional summoner profile)."""
        account = self.get_account_by_riot_id(game_name, tag_line)
        puuid = account["puuid"]
        profile = PlayerProfile(
            game_name=account.get("gameName", game_name),
            tag_line=account.get("tagLine", tag_line),
            puuid=puuid,
            platform=self.platform,
        )
        try:
            summoner = self.get_summoner_by_puuid(puuid)
            profile.summoner_id = summoner.get("id")
            profile.account_id = summoner.get("accountId")
            profile.profile_icon_id = summoner.get("profileIconId")
            profile.summoner_level = summoner.get("summonerLevel")
        except RiotAPIError:
            # Account works even if summoner endpoint fails
            pass
        return profile

    # ── Match V5 ──────────────────────────────────────────────────────

    def get_match_ids(
        self,
        puuid: str,
        count: int = 10,
        start: int = 0,
        queue: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[str]:
        params: dict[str, Any] = {"start": start, "count": min(count, 100)}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        url = f"{self._host(self.region)}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self._get(url, params=params)

    # ── 매치 디스크 캐시 (match payload는 불변) ──────────────────────

    def _match_cache_path(self, match_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in match_id)
        from lol_coach.config import cache_root

        return cache_root() / "matches" / f"{safe}.json"

    def _read_match_cache(self, match_id: str) -> dict | None:
        try:
            path = self._match_cache_path(match_id)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("metadata", {}).get("matchId"):
                _log.debug("매치 캐시 히트: %s", match_id)
                return data
        except Exception:
            pass
        return None

    def _write_match_cache(self, match_id: str, data: dict) -> None:
        try:
            path = self._match_cache_path(match_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass
        # 매 저장마다 전체 스캔하지 않음 — 세션당/10분당 1회 수준
        self._prune_match_cache(force=False)

    def _prune_match_cache(self, *, force: bool = False) -> None:
        """디스크 캐시 용량 제한 — 30일 경과분 + 최대 파일 수 초과분 삭제 (best-effort)."""
        min_interval = 600.0  # 10분
        now = time.time()
        if not force and (now - getattr(self, "_last_prune_at", 0.0)) < min_interval:
            return
        self._last_prune_at = now
        max_files = 1000
        keep_files = 800
        max_age_s = 30 * 86400
        try:
            from lol_coach.config import cache_root

            for sub in ("matches", "timelines"):
                self._prune_cache_dir(cache_root() / sub, max_files, keep_files, max_age_s)
        except Exception:
            pass

    @staticmethod
    def _prune_cache_dir(
        cache_dir: Path, max_files: int, keep_files: int, max_age_s: float
    ) -> None:
        """단일 캐시 폴더 정리 (matches/timelines 공용)."""
        try:
            if not cache_dir.is_dir():
                return
            now = time.time()
            entries: list[tuple[float, Path]] = []
            for p in cache_dir.glob("*.json"):
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if now - mtime > max_age_s:
                    p.unlink(missing_ok=True)
                    continue
                entries.append((mtime, p))
            if len(entries) > max_files:
                entries.sort()  # 오래된 것부터
                for _mtime, p in entries[: len(entries) - keep_files]:
                    p.unlink(missing_ok=True)
        except Exception:
            pass

    def get_match(self, match_id: str) -> dict:
        if self.use_cache:
            cached = self._read_match_cache(match_id)
            if cached is not None:
                return cached
        url = f"{self._host(self.region)}/lol/match/v5/matches/{match_id}"
        data = self._get(url)
        if self.use_cache and isinstance(data, dict):
            self._write_match_cache(match_id, data)
        return data

    def _timeline_cache_path(self, match_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in match_id)
        from lol_coach.config import cache_root

        return cache_root() / "timelines" / f"{safe}.json"

    def _read_timeline_cache(self, match_id: str) -> dict | None:
        try:
            path = self._timeline_cache_path(match_id)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("metadata", {}).get("matchId"):
                _log.debug("타임라인 캐시 히트: %s", match_id)
                return data
        except Exception:
            pass
        return None

    def _write_timeline_cache(self, match_id: str, data: dict) -> None:
        try:
            path = self._timeline_cache_path(match_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def get_match_timeline(self, match_id: str) -> dict:
        if self.use_cache:
            cached = self._read_timeline_cache(match_id)
            if cached is not None:
                return cached
        url = f"{self._host(self.region)}/lol/match/v5/matches/{match_id}/timeline"
        data = self._get(url)
        if self.use_cache and isinstance(data, dict):
            self._write_timeline_cache(match_id, data)
        return data

    @staticmethod
    def _participant_for_puuid(
        match: dict, puuid: str, *, game_name: str = "", tag_line: str = ""
    ) -> dict | None:
        for p in match.get("info", {}).get("participants", []):
            if p.get("puuid") == puuid:
                return p
        # Fallback: Account API puuid가 Match-V5 puuid와 불일치할 때
        # (계정 이전 · 리전 마이그레이션 등) Riot ID로 참가자 검색
        if game_name:
            gn = game_name.lower()
            tl = (tag_line or "").lower()
            for p in match.get("info", {}).get("participants", []):
                pn = (p.get("riotIdGameName") or "").lower()
                pt = (p.get("riotIdTagline") or "").lower()
                if pn == gn and (not tl or pt == tl):
                    return p
        return None

    @staticmethod
    def _normalize_role(participant: dict) -> str:
        team_pos = (participant.get("teamPosition") or "").upper()
        if team_pos:
            return ROLE_NORMALIZE.get(team_pos, team_pos)
        individual = (participant.get("individualPosition") or "").upper()
        if individual and individual != "Invalid":
            return ROLE_NORMALIZE.get(individual, individual)
        lane = (participant.get("lane") or "").upper()
        role = (participant.get("role") or "").upper()
        if lane == "TOP":
            return "TOP"
        if lane == "JUNGLE":
            return "JUNGLE"
        if lane == "MIDDLE" or lane == "MID":
            return "MIDDLE"
        if lane == "BOTTOM":
            if role in ("DUO_SUPPORT", "SUPPORT"):
                return "UTILITY"
            return "BOTTOM"
        return "UNKNOWN"

    def _participant_to_player(self, p: dict, *, me_puuid: str) -> MatchPlayer:
        items = [p.get(f"item{i}", 0) for i in range(7) if p.get(f"item{i}", 0)]
        name = p.get("riotIdGameName") or p.get("summonerName") or ""
        tag = p.get("riotIdTagline") or ""
        riot_id = f"{name}#{tag}" if name and tag else name
        return MatchPlayer(
            champion_name=p.get("championName", "Unknown"),
            champion_id=int(p.get("championId") or 0),
            role=self._normalize_role(p),
            team_id=int(p.get("teamId") or 0),
            kills=int(p.get("kills") or 0),
            deaths=int(p.get("deaths") or 0),
            assists=int(p.get("assists") or 0),
            cs=int(p.get("totalMinionsKilled") or 0) + int(p.get("neutralMinionsKilled") or 0),
            gold=int(p.get("goldEarned") or 0),
            damage_to_champs=int(p.get("totalDamageDealtToChampions") or 0),
            vision_score=int(p.get("visionScore") or 0),
            champ_level=int(p.get("champLevel") or 0),
            items=items,
            riot_id=riot_id,
            is_me=p.get("puuid") == me_puuid,
            win=bool(p.get("win")),
        )

    @staticmethod
    def _parse_side_objectives(team: dict) -> SideObjectives:
        obj = team.get("objectives") or {}

        def n(key: str) -> int:
            block = obj.get(key) or {}
            return int(block.get("kills") or 0)

        return SideObjectives(
            dragons=n("dragon"),
            barons=n("baron"),
            towers=n("tower"),
            inhibitors=n("inhibitor"),
            heralds=n("riftHerald"),
            grubs=n("horde"),
        )

    def summarize_match(
        self,
        match: dict,
        puuid: str,
        *,
        game_name: str = "",
        tag_line: str = "",
    ) -> MatchSummary | None:
        info = match.get("info", {})
        meta = match.get("metadata", {})
        p = self._participant_for_puuid(
            match, puuid, game_name=game_name, tag_line=tag_line
        )
        if not p:
            return None

        items = [p.get(f"item{i}", 0) for i in range(7) if p.get(f"item{i}", 0)]
        primary_rune = None
        perks = p.get("perks") or {}
        styles = perks.get("styles") or []
        if styles:
            selections = styles[0].get("selections") or []
            if selections:
                primary_rune = selections[0].get("perk")

        my_team = int(p.get("teamId") or 100)
        participants = info.get("participants") or []
        ally: list[MatchPlayer] = []
        enemy: list[MatchPlayer] = []
        for part in participants:
            mp = self._participant_to_player(part, me_puuid=puuid)
            if int(part.get("teamId") or 0) == my_team:
                ally.append(mp)
            else:
                enemy.append(mp)

        # role order for display
        order = {"TOP": 0, "JUNGLE": 1, "MIDDLE": 2, "BOTTOM": 3, "UTILITY": 4}
        ally.sort(key=lambda x: order.get(x.role, 9))
        enemy.sort(key=lambda x: order.get(x.role, 9))

        team_kills = sum(a.kills for a in ally)
        challenges = p.get("challenges") or {}
        kp = challenges.get("killParticipation")
        if kp is None and team_kills > 0:
            kp = (int(p.get("kills") or 0) + int(p.get("assists") or 0)) / team_kills

        dmg = int(p.get("totalDamageDealtToChampions") or 0)
        team_dmg = sum(a.damage_to_champs for a in ally) or 1
        dmg_share = dmg / team_dmg

        duration = int(info.get("gameDuration") or 0)
        gold = int(p.get("goldEarned") or 0)
        gpm = (gold / (duration / 60.0)) if duration > 0 else None
        mins = duration / 60.0 if duration > 0 else 1.0

        # objectives
        obj = MatchObjectives()
        for team in info.get("teams") or []:
            side = self._parse_side_objectives(team)
            if int(team.get("teamId") or 0) == my_team:
                obj.ally = side
            else:
                obj.enemy = side

        enemy_kills = sum(e.kills for e in enemy)
        ally_gold = sum(a.gold for a in ally)
        enemy_gold = sum(e.gold for e in enemy)

        def _ch_num(key: str) -> float | None:
            v = challenges.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _ch_int(key: str) -> int:
            v = _ch_num(key)
            return int(v) if v is not None else 0

        gold_lead = _ch_num("laningPhaseGoldExpAdvantage")
        if gold_lead is None:
            gold_lead = _ch_num("earlyLaningPhaseGoldExpAdvantage")

        cs10 = _ch_num("laneMinionsFirst10Minutes")
        jg10 = _ch_num("jungleCsBefore10Minutes")
        vis_adv = _ch_num("visionScoreAdvantageLaneOpponent")
        dpm = _ch_num("damagePerMinute")
        if dpm is None and duration > 0:
            dpm = dmg / mins

        return MatchSummary(
            match_id=meta.get("matchId", ""),
            champion_name=p.get("championName", "Unknown"),
            champion_id=int(p.get("championId") or 0),
            role=self._normalize_role(p),
            lane=(p.get("lane") or "UNKNOWN").upper(),
            win=bool(p.get("win")),
            kills=int(p.get("kills") or 0),
            deaths=int(p.get("deaths") or 0),
            assists=int(p.get("assists") or 0),
            cs=int(p.get("totalMinionsKilled") or 0) + int(p.get("neutralMinionsKilled") or 0),
            gold=gold,
            damage_to_champs=dmg,
            vision_score=int(p.get("visionScore") or 0),
            game_duration_s=duration,
            queue_id=int(info.get("queueId") or 0),
            items=items,
            summoner_spells=[
                int(p.get("summoner1Id") or 0),
                int(p.get("summoner2Id") or 0),
            ],
            primary_rune=primary_rune,
            raw_participant=p,
            team_id=my_team,
            champ_level=int(p.get("champLevel") or 0),
            damage_taken=int(p.get("totalDamageTaken") or 0),
            kill_participation=float(kp) if kp is not None else None,
            damage_share=dmg_share,
            gold_per_min=round(gpm, 1) if gpm is not None else None,
            wards_placed=int(p.get("wardsPlaced") or 0),
            wards_killed=int(p.get("wardsKilled") or 0),
            control_wards=int(p.get("detectorWardsPlaced") or 0),
            turret_kills=int(p.get("turretKills") or 0),
            first_blood=bool(p.get("firstBloodKill")),
            largest_multi_kill=int(p.get("largestMultiKill") or 0),
            solo_kills=int(challenges.get("soloKills") or 0),
            total_team_kills=team_kills,
            ally_team=ally,
            enemy_team=enemy,
            obj=obj,
            game_mode=str(info.get("gameMode") or ""),
            game_version=str(info.get("gameVersion") or ""),
            game_end_timestamp=int(info.get("gameEndTimestamp") or 0),
            time_dead_s=int(p.get("totalTimeSpentDead") or 0),
            damage_to_objectives=int(p.get("damageDealtToObjectives") or 0),
            damage_to_buildings=int(p.get("damageDealtToBuildings") or 0),
            cs10=int(cs10) if cs10 is not None else None,
            gold_lead_lane=int(gold_lead) if gold_lead is not None else None,
            vision_adv_lane=vis_adv,
            plates=_ch_int("turretPlatesTaken"),
            dragon_takedowns=_ch_int("dragonTakedowns"),
            baron_takedowns=_ch_int("baronTakedowns"),
            herald_takedowns=_ch_int("riftHeraldTakedowns"),
            epic_steals=_ch_int("epicMonsterSteals"),
            jungle_cs_10=jg10,
            scuttle_kills=_ch_int("scuttleCrabKills"),
            dpm=round(dpm, 0) if dpm is not None else None,
            team_early_surrender=bool(p.get("teamEarlySurrendered")),
            enemy_team_kills=enemy_kills,
            ally_gold_total=ally_gold,
            enemy_gold_total=enemy_gold,
        )

    def get_recent_form(
        self,
        profile: PlayerProfile,
        count: int = 10,
        queue: int | None = None,
        queues: set[int] | None = None,
    ) -> RecentForm:
        """
        Fetch last N matches and aggregate stats.

        If ``queues`` is set, scan a wider match-id window and keep only those
        queue ids (needed when ARAM/Mayhem is mixed into history).
        """
        fetch_count = count
        if queues is not None:
            # Pull extra ids so filtered modes still fill the sample
            fetch_count = min(count * 4, 100)

        match_ids = self.get_match_ids(profile.puuid, count=fetch_count, queue=queue)
        matches = self._collect_summaries(
            match_ids,
            profile.puuid,
            count=count,
            queues=queues,
            game_name=profile.game_name,
            tag_line=profile.tag_line,
        )
        return self._aggregate_form(profile, matches)

    def _summary_or_none(
        self,
        match_id: str,
        puuid: str,
        *,
        game_name: str = "",
        tag_line: str = "",
    ) -> MatchSummary | None:
        try:
            raw = self.get_match(match_id)
            return self.summarize_match(
                raw, puuid, game_name=game_name, tag_line=tag_line
            )
        except RiotAPIError as exc:
            # 403/404 — restricted/broken payloads are skipped
            if exc.status_code in (403, 404):
                return None
            raise

    def _collect_summaries(
        self,
        match_ids: list[str],
        puuid: str,
        *,
        count: int,
        queues: set[int] | None,
        game_name: str = "",
        tag_line: str = "",
    ) -> list[MatchSummary]:
        """매치 상세를 병렬로 가져오되, 순서·큐 필터·조기 종료 규칙 유지.

        청크 단위 ThreadPoolExecutor — 필요한 개수(count)를 채우면
        남은 ID는 요청하지 않는다 (큐 필터 스캔 시 불필요한 호출 절약).
        """
        matches: list[MatchSummary] = []
        if not match_ids:
            return matches
        workers = max(1, self.max_workers)
        idx = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while idx < len(match_ids) and len(matches) < count:
                chunk_size = max(workers * 2, count - len(matches), 4)
                chunk = match_ids[idx : idx + chunk_size]
                def _fetch(mid: str) -> MatchSummary | None:
                    return self._summary_or_none(
                        mid, puuid, game_name=game_name, tag_line=tag_line
                    )

                for summary in pool.map(_fetch, chunk):
                    if summary is None:
                        continue
                    if queues is not None and summary.queue_id not in queues:
                        continue
                    matches.append(summary)
                    if len(matches) >= count:
                        break
        return matches

    # ── League V4 (랭크) ────────────────────────────────────────────

    def get_league_entries(self, puuid: str) -> list[RankInfo]:
        """솔로/자유 랭크 엔트리 (언랭이면 빈 리스트)."""
        url = f"{self._host(self.platform)}/lol/league/v4/entries/by-puuid/{puuid}"
        data = self._get(url)
        if not isinstance(data, list):
            return []
        return [RankInfo.from_api(e) for e in data]

    @staticmethod
    def _aggregate_form(profile: PlayerProfile, matches: list[MatchSummary]) -> RecentForm:
        wins = sum(1 for m in matches if m.win)
        losses = len(matches) - wins
        if matches:
            avg_kda = round(sum(m.kda_ratio for m in matches) / len(matches), 2)
            avg_cspm = round(sum(m.cs_per_min for m in matches) / len(matches), 1)
        else:
            avg_kda = 0.0
            avg_cspm = 0.0

        role_counts: dict[str, int] = defaultdict(int)
        champ_map: dict[str, ChampionStats] = {}
        mode_acc: dict[str, list[MatchSummary]] = defaultdict(list)

        for m in matches:
            role_counts[m.role] += 1
            mode_acc[m.mode_label].append(m)
            cs = champ_map.get(m.champion_name)
            if not cs:
                cs = ChampionStats(champion_name=m.champion_name)
                champ_map[m.champion_name] = cs
            cs.games += 1
            cs.wins += 1 if m.win else 0
            cs.kills += m.kills
            cs.deaths += m.deaths
            cs.assists += m.assists
            cs.cs += m.cs
            cs.roles[m.role] = cs.roles.get(m.role, 0) + 1

        mode_stats: dict[str, ModeBucketStats] = {}
        for label, group in mode_acc.items():
            n = len(group)
            mode_stats[label] = ModeBucketStats(
                label=label,
                games=n,
                wins=sum(1 for g in group if g.win),
                avg_kda=round(sum(g.kda_ratio for g in group) / n, 2),
                avg_cs_per_min=round(sum(g.cs_per_min for g in group) / n, 1),
                avg_damage=round(sum(g.damage_to_champs for g in group) / n, 0),
            )

        freshness = "unknown"
        age = "unknown"
        timestamps = [m.game_end_timestamp for m in matches if m.game_end_timestamp]
        if timestamps:
            age_min = max(0, (int(time.time() * 1000) - max(timestamps)) / 60000.0)
            if age_min < 60:
                age = f"{max(1, int(age_min))}분 전"
            elif age_min < 1440:
                age = f"{int(age_min / 60)}시간 전"
            else:
                age = f"{int(age_min / 1440)}일 전"
            if age_min < 360:
                freshness = "신선"
            elif age_min < 2880:
                freshness = "보통"
            else:
                freshness = "오래됨"

        provenance = FormProvenance(
            source="Riot Match-V5",
            patches=tuple(dict.fromkeys(m.game_version for m in matches if m.game_version)),
            sample_count=len(matches),
            freshness=freshness,
            age=age,
        )
        return RecentForm(
            profile=profile,
            matches=matches,
            wins=wins,
            losses=losses,
            avg_kda=avg_kda,
            avg_cs_per_min=avg_cspm,
            role_counts=dict(role_counts),
            champion_stats=champ_map,
            mode_stats=mode_stats,
            provenance=provenance,
        )

    def get_champion_matches(
        self,
        profile: PlayerProfile,
        champion_name: str,
        lookback: int = 20,
        queue: int | None = None,
        queues: set[int] | None = None,
        mode: str | None = None,
    ) -> list[MatchSummary]:
        """Recent games on a specific champion (name is Riot key, e.g. 'Ahri')."""
        if mode and queues is None:
            queues = queues_for_mode(mode)
        # For mode-filtered searches scan more history
        scan = lookback
        if queues is not None:
            scan = min(max(lookback * 5, 30), 100)

        form = self.get_recent_form(profile, count=scan, queue=queue, queues=queues)
        target = champion_name.strip().lower().replace(" ", "").replace("'", "")
        out = []
        for m in form.matches:
            key = m.champion_name.lower().replace(" ", "").replace("'", "")
            if key == target:
                out.append(m)
            if len(out) >= lookback:
                break
        return out

    # ── Spectator V5 ──────────────────────────────────────────────────

    def get_active_game(self, puuid: str) -> LiveGame | None:
        """
        Check if player is currently in game via Spectator V5.
        Returns None if not in game (404).
        """
        url = f"{self._host(self.platform)}/lol/spectator/v5/active-games/by-summoner/{puuid}"
        try:
            data = self._get(url)
        except RiotAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

        participants = data.get("participants") or []
        my = next((p for p in participants if p.get("puuid") == puuid), None)
        return LiveGame(
            game_id=int(data.get("gameId") or 0),
            game_mode=data.get("gameMode") or "",
            game_type=data.get("gameType") or "",
            map_id=int(data.get("mapId") or 0),
            game_queue_config_id=int(data.get("gameQueueConfigId") or 0),
            game_start_time=int(data.get("gameStartTime") or 0),
            game_length=int(data.get("gameLength") or 0),
            participants=participants,
            my_champion_id=int(my["championId"]) if my else None,
            my_team_id=int(my["teamId"]) if my else None,
            observers_key=(data.get("observers") or {}).get("encryptionKey"),
        )

    def is_in_game(self, puuid: str) -> bool:
        return self.get_active_game(puuid) is not None


def aggregate_form(profile: PlayerProfile, matches: list[MatchSummary]) -> RecentForm:
    """매치 목록 → RecentForm 집계 (큐/패치 필터 재집계 등 공용)."""
    return RiotClient._aggregate_form(profile, matches)
