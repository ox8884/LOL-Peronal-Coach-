"""LCU(League Client Update) 로컬 API — 챔피언 셀렉트 실시간 감지.

게임 클라이언트가 띄운 로컬 HTTPS 서버(lockfile의 포트/비밀번호)에 접속해
밴픽 세션을 읽는다. Riot API 키 없이 동작하며, Spectator와 달리
**밴픽 단계에서** 픽 정보를 얻을 수 있다.

참고: lockfile은 클라이언트 실행 중에만 존재한다.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import urllib3

# LCU 는 로컬 루프백의 자체 서명 인증서를 사용하므로 verify=False 가 필요하다.
# 경고 억제를 모듈 전역으로 하지 않고 _get() 안에서만 스코프 한정한다
# (다른 코드가 우연히 verify=False 를 써도 경고가 보이도록).

_DEFAULT_LOCKFILES = [
    Path(r"C:\Riot Games\League of Legends\lockfile"),
    Path(r"D:\Riot Games\League of Legends\lockfile"),
    Path(r"E:\Riot Games\League of Legends\lockfile"),
    Path(r"F:\Riot Games\League of Legends\lockfile"),
    Path(r"G:\Riot Games\League of Legends\lockfile"),
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Riot Games"
    / "League of Legends"
    / "lockfile",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
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
        import winreg
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
        pid = int(parts[1])
        port = int(parts[2])
    except ValueError as exc:
        raise LCUError(f"lockfile 숫자 필드 파싱 실패: {exc}") from exc
    if not (1 <= port <= 65535):
        raise LCUError(f"lockfile 포트가 올바르지 않습니다: {port}")
    return Lockfile(
        pid=pid,
        port=port,
        password=parts[3],
        protocol=parts[4] or "https",
    )


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
    my_augments: list[str] = field(default_factory=list)
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
            # ARAM 아수라장(2400) — 제시 증강 자동 읽기 (필드 없으면 빈 목록)
            for aug in cell.get("augments") or []:
                if isinstance(aug, dict):
                    name = str(aug.get("name") or aug.get("id") or "").strip()
                else:
                    name = str(aug).strip()
                if name and not name.isdigit() and name not in info.my_augments:
                    info.my_augments.append(name)
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
            with warnings.catch_warnings():
                # LCU 루프백 자체 서명 인증서 — 경고 억제를 이 요청으로만 한정
                warnings.simplefilter(
                    "ignore", urllib3.exceptions.InsecureRequestWarning
                )
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
