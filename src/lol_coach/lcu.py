"""LCU(League Client Update) 로컬 API — 챔피언 셀렉트 실시간 감지.

게임 클라이언트가 띄운 로컬 HTTPS 서버(lockfile의 포트/비밀번호)에 접속해
밴픽 세션을 읽는다. Riot API 키 없이 동작하며, Spectator와 달리
**밴픽 단계에서** 픽 정보를 얻을 수 있다.

참고: lockfile은 클라이언트 실행 중에만 존재한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_LOCKFILES = [
    Path(r"C:\Riot Games\League of Legends\lockfile"),
    Path(r"D:\Riot Games\League of Legends\lockfile"),
    Path(r"E:\Riot Games\League of Legends\lockfile"),
    Path(r"F:\Riot Games\League of Legends\lockfile"),
    Path(r"G:\Riot Games\League of Legends\lockfile"),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Riot Games"
    / "League of Legends"
    / "lockfile",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Riot Games"
    / "League of Legends"
    / "lockfile",
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Riot Games"
    / "League of Legends"
    / "lockfile",
]


def _registry_lol_lockfile() -> Path | None:
    """Windows 레지스트리에서 클라이언트 설치 경로 추정 (best-effort)."""
    try:
        import winreg  # type: ignore
    except ImportError:
        return None
    keys = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Riot Games\Riot Client"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Riot Games\Riot Client"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Riot Games\Riot Client"),
    ]
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                for value_name in ("InstallFolder", "Location", "Install Path"):
                    try:
                        val, _ = winreg.QueryValueEx(k, value_name)
                    except OSError:
                        continue
                    if not val:
                        continue
                    base = Path(str(val))
                    for candidate in (
                        base / "League of Legends" / "lockfile",
                        base / "lockfile",
                        base.parent / "League of Legends" / "lockfile",
                    ):
                        if candidate.is_file():
                            return candidate
        except OSError:
            continue
    return None


class LCUError(Exception):
    pass


@dataclass(frozen=True)
class Lockfile:
    port: int
    password: str
    protocol: str = "https"
    pid: int = 0


def parse_lockfile(text: str) -> Lockfile:
    """lockfile 내용 파싱: ``name:pid:port:password:protocol``."""
    parts = (text or "").strip().split(":")
    if len(parts) < 5:
        raise LCUError("lockfile 형식이 올바르지 않습니다")
    try:
        return Lockfile(
            pid=int(parts[1]),
            port=int(parts[2]),
            password=parts[3],
            protocol=parts[4] or "https",
        )
    except ValueError as exc:
        raise LCUError(f"lockfile 숫자 필드 파싱 실패: {exc}") from exc


def find_lockfile() -> Path | None:
    """lockfile 경로 탐색 (환경변수 LOL_LOCKFILE 우선 → 기본 드라이브 → 레지스트리)."""
    env = os.environ.get("LOL_LOCKFILE")
    candidates: list[Path] = [Path(env)] if env else []
    candidates += list(_DEFAULT_LOCKFILES)
    reg = _registry_lol_lockfile()
    if reg is not None:
        candidates.append(reg)
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path)
            if key in seen or not key.strip():
                continue
            seen.add(key)
            if path.is_file():
                return path
        except OSError:
            continue
    return None


@dataclass
class ChampSelectInfo:
    """파싱된 챔피언 셀렉트 상태."""

    phase: str = ""
    my_cell_id: int = -1
    my_champion_id: int = 0
    my_position: str = ""  # top/jungle/middle/bottom/utility
    ally_champion_ids: list[int] = field(default_factory=list)
    enemy_champion_ids: list[int] = field(default_factory=list)
    ban_champion_ids: list[int] = field(default_factory=list)
    is_aram: bool = False

    @property
    def in_champ_select(self) -> bool:
        return bool(self.phase) and self.phase not in ("", "None")


def parse_champ_select(session: dict[str, Any]) -> ChampSelectInfo:
    """/lol-champ-select/v1/session 응답 → 구조화 (순수 함수, 테스트 용이)."""
    info = ChampSelectInfo()
    timer = session.get("timer") or {}
    info.phase = str(timer.get("phase") or "")
    local_id = int(session.get("localPlayerCellId") or -1)
    info.my_cell_id = local_id

    my_team = session.get("myTeam") or []
    their_team = session.get("theirTeam") or []

    for cell in my_team:
        cid = int(cell.get("championId") or 0)
        cell_id = int(cell.get("cellId") or -1)
        if cell_id == local_id:
            info.my_champion_id = cid
            info.my_position = str(cell.get("assignedPosition") or "").lower()
        elif cid:
            info.ally_champion_ids.append(cid)

    for cell in their_team:
        cid = int(cell.get("championId") or 0)
        if cid:
            info.enemy_champion_ids.append(cid)

    bans: list[int] = []
    for action_group in session.get("actions") or []:
        for action in action_group or []:
            if str(action.get("type") or "").lower() != "ban":
                continue
            cid = int(action.get("championId") or 0)
            if cid and cid not in bans:
                bans.append(cid)
    info.ban_champion_ids = bans

    # 밴픽 중 적 픽이 하나도 안 보이고 아군만 보이면 ARAM류로 간주
    info.is_aram = bool(my_team) and not their_team
    return info


class LCUClient:
    """lockfile 기반 로컬 클라이언트 API."""

    def __init__(self, lockfile_path: Path | None = None, timeout: float = 3.0):
        self.timeout = timeout
        path = lockfile_path or find_lockfile()
        if path is None:
            raise LCUError(
                "League of Legends 클라이언트를 찾지 못했습니다. "
                "게임 클라이언트가 실행 중인지 확인하세요."
            )
        try:
            self.lockfile = parse_lockfile(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LCUError(f"lockfile을 읽을 수 없습니다: {exc}") from exc
        self.session = requests.Session()
        self.session.auth = ("riot", self.lockfile.password)
        self.session.verify = False
        self.session.headers.update({"Accept": "application/json"})

    @property
    def base_url(self) -> str:
        return f"{self.lockfile.protocol}://127.0.0.1:{self.lockfile.port}"

    @staticmethod
    def is_client_running() -> bool:
        return find_lockfile() is not None

    def _get(self, path: str) -> Any:
        try:
            resp = self.session.get(
                f"{self.base_url}{path}", timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise LCUError(f"게임 클라이언트 연결 실패: {exc}") from exc
        if resp.status_code == 404:
            raise LCUError(f"엔드포인트 없음(404): {path}")
        if resp.status_code != 200:
            raise LCUError(f"LCU HTTP {resp.status_code}: {path}")
        return resp.json()

    def gameflow_phase(self) -> str:
        """Lobby / ChampSelect / InProgress / EndOfGame ..."""
        try:
            data = self._get("/lol-gameflow/v1/session")
        except LCUError:
            return ""
        return str((data or {}).get("phase") or "")

    def champ_select(self) -> ChampSelectInfo:
        """현재 챔피언 셀렉트 세션 (없으면 LCUError)."""
        data = self._get("/lol-champ-select/v1/session")
        if not isinstance(data, dict):
            raise LCUError("챔피언 셀렉트 세션이 아닙니다")
        info = parse_champ_select(data)
        if not info.phase and info.my_cell_id == -1:
            raise LCUError("지금은 챔피언 셀렉트 중이 아닙니다")
        return info
