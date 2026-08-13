"""Configuration: load / save Riot API key and default player settings."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv, set_key, unset_key


def _app_root() -> Path:
    """개발 시 프로젝트 루트 / 설치본은 사용자 쓰기 가능 폴더.

    설치 경로와 관계없이 %LOCALAPPDATA%\\롤실전코치 를 사용해
    공유 또는 쓰기 가능한 실행 파일 폴더에 비밀값을 남기지 않는다.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        data = base / "롤실전코치"
        data.mkdir(parents=True, exist_ok=True)
        return data
    return Path(__file__).resolve().parents[2]


# Project root = lol-coach/ 또는 사용자 데이터 폴더
PROJECT_ROOT = _app_root()
ENV_PATH = PROJECT_ROOT / ".env"
PROFILES_PATH = PROJECT_ROOT / "profiles.json"
UI_PATH = PROJECT_ROOT / "ui.json"


def cache_root() -> Path:
    """캐시 루트 — 설치/개발 모두 PROJECT_ROOT 아래 ``cache/``.

    riot/icons/blitz 등에서 각자 경로를 만들지 말고 이 함수를 쓴다.
    """
    root = PROJECT_ROOT / "cache"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


# Valid Riot personal/dev key shape (loose check)
_API_KEY_RE = re.compile(r"^RGAPI-[0-9a-fA-F-]{8,}$")

PLATFORM_TO_REGION = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}
SUPPORTED_REGIONS = frozenset(PLATFORM_TO_REGION.values())

DEFAULT_PLATFORM = "kr"
DEFAULT_GAME_NAME = ""
DEFAULT_TAG_LINE = ""

# Development API 키 권장 재발급 주기 (초) — 24h, UI 안내용
DEV_KEY_MAX_AGE_S = 24 * 3600


class InvalidPlatformError(ValueError):
    def __init__(self, platform: str) -> None:
        self.platform = platform
        super().__init__(f"지원하지 않는 Riot 서버 코드입니다: {platform}")


def normalize_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized not in PLATFORM_TO_REGION:
        raise InvalidPlatformError(platform)
    return normalized


def normalize_region(region: str) -> str:
    normalized = region.strip().lower()
    if normalized not in SUPPORTED_REGIONS:
        raise InvalidPlatformError(region)
    return normalized


@dataclass
class Settings:
    riot_api_key: str
    game_name: str = DEFAULT_GAME_NAME
    tag_line: str = DEFAULT_TAG_LINE
    platform: str = DEFAULT_PLATFORM
    llm_api_key: str = ""
    llm_model: str = ""

    @property
    def region(self) -> str:
        return PLATFORM_TO_REGION.get(self.platform.lower(), "americas")

    @property
    def riot_id(self) -> str:
        if not self.game_name or not self.tag_line:
            return ""
        return f"{self.game_name}#{self.tag_line}"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.riot_api_key:
            errors.append("RIOT_API_KEY is missing.")
        elif not _API_KEY_RE.match(self.riot_api_key.strip()):
            errors.append("RIOT_API_KEY does not look valid (expected RGAPI-...).")
        if not self.game_name:
            errors.append("game_name is empty.")
        if not self.tag_line:
            errors.append("tag_line is empty.")
        if self.platform.lower() not in PLATFORM_TO_REGION:
            errors.append(f"Unknown platform: {self.platform}")
        return errors


def _ensure_env_loaded() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)


def load_settings() -> Settings:
    """Load settings from environment / .env file."""
    _ensure_env_loaded()
    return Settings(
        riot_api_key=os.getenv("RIOT_API_KEY", "").strip(),
        game_name=os.getenv("RIOT_GAME_NAME", DEFAULT_GAME_NAME).strip(),
        tag_line=os.getenv("RIOT_TAG_LINE", DEFAULT_TAG_LINE).strip(),
        platform=os.getenv("RIOT_PLATFORM", DEFAULT_PLATFORM).strip().lower(),
        llm_api_key=os.getenv("LOL_COACH_LLM_KEY", "").strip(),
        llm_model=os.getenv("LOL_COACH_LLM_MODEL", "").strip(),
    )


def save_api_key(api_key: str, env_path: Path | None = None) -> Path:
    """Persist RIOT_API_KEY to .env (create file if needed)."""
    from datetime import datetime, timezone

    path = env_path or ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    key = api_key.strip()
    if not path.exists():
        path.write_text(
            "# LoL Personal Coach environment\n"
            f"RIOT_API_KEY={key}\n"
            f"RIOT_GAME_NAME={DEFAULT_GAME_NAME}\n"
            f"RIOT_TAG_LINE={DEFAULT_TAG_LINE}\n"
            f"RIOT_PLATFORM={DEFAULT_PLATFORM}\n",
            encoding="utf-8",
        )
    else:
        set_key(str(path), "RIOT_API_KEY", key)
    # Refresh process env
    os.environ["RIOT_API_KEY"] = key
    # Development 키 만료 안내용 타임스탬프 (키가 비어 있으면 제거)
    if key:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        set_key(str(path), "RIOT_API_KEY_SAVED_AT", stamp)
        os.environ["RIOT_API_KEY_SAVED_AT"] = stamp
    else:
        unset_key(str(path), "RIOT_API_KEY_SAVED_AT")
        os.environ.pop("RIOT_API_KEY_SAVED_AT", None)
    return path


def api_key_saved_at() -> float | None:
    """``.env`` 의 RIOT_API_KEY_SAVED_AT → unix timestamp (없으면 None)."""
    from datetime import datetime, timezone

    _ensure_env_loaded()
    raw = os.getenv("RIOT_API_KEY_SAVED_AT", "").strip()
    if not raw:
        return None
    try:
        # ISO-8601 with optional Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def api_key_age_seconds() -> float | None:
    """키 저장 후 경과 초. 타임스탬프 없으면 None."""
    import time

    saved = api_key_saved_at()
    if saved is None:
        return None
    return max(0.0, time.time() - saved)


def api_key_expiry_hint() -> str:
    """UI 상태바용 짧은 안내. 문제 없으면 빈 문자열."""
    age = api_key_age_seconds()
    if age is None:
        return ""
    hours = age / 3600.0
    if hours >= 24:
        return "⚠ Riot API 키가 24시간 경과 — 개발 키는 만료됐을 수 있음 · Personal 키 권장"
    if hours >= 22:
        left = max(0, 24 - hours)
        return f"⏳ 개발 키라면 약 {left:.1f}시간 후 만료 · Personal 키 권장"
    return ""


def save_llm_key(llm_key: str, env_path: Path | None = None) -> Path:
    """AI 코칭 키 저장/해제 — 빈 문자열이면 .env 에서 제거."""
    path = env_path or ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_api_key("", path)
    key = llm_key.strip()
    if key:
        set_key(str(path), "LOL_COACH_LLM_KEY", key)
    else:
        unset_key(str(path), "LOL_COACH_LLM_KEY")
    if key:
        os.environ["LOL_COACH_LLM_KEY"] = key
    else:
        os.environ.pop("LOL_COACH_LLM_KEY", None)
    return path


def save_llm_model(llm_model: str, env_path: Path | None = None) -> Path:
    """AI 코칭 모델 저장/해제 — 빈 문자열이면 .env 에서 제거."""
    path = env_path or ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_api_key("", path)
    model = llm_model.strip()
    if model:
        set_key(str(path), "LOL_COACH_LLM_MODEL", model)
    else:
        unset_key(str(path), "LOL_COACH_LLM_MODEL")
    if model:
        os.environ["LOL_COACH_LLM_MODEL"] = model
    else:
        os.environ.pop("LOL_COACH_LLM_MODEL", None)
    return path


def save_player(
    game_name: str,
    tag_line: str,
    platform: str = DEFAULT_PLATFORM,
    env_path: Path | None = None,
) -> Path:
    """Persist default Riot ID / platform to .env."""
    platform_key = normalize_platform(platform)
    path = env_path or ENV_PATH
    if not path.exists():
        save_api_key("", path)
    set_key(str(path), "RIOT_GAME_NAME", game_name.strip())
    set_key(str(path), "RIOT_TAG_LINE", tag_line.strip())
    set_key(str(path), "RIOT_PLATFORM", platform_key)
    # RIOT_REGION은 platform에서 파생되므로 저장하지 않는다 (불일치 방지).
    # 예전 버전이 남긴 값이 있으면 제거.
    unset_key(str(path), "RIOT_REGION")
    os.environ.pop("RIOT_REGION", None)
    os.environ["RIOT_GAME_NAME"] = game_name.strip()
    os.environ["RIOT_TAG_LINE"] = tag_line.strip()
    os.environ["RIOT_PLATFORM"] = platform_key
    return path


def prompt_for_api_key(force: bool = False) -> str:
    """
    Interactive prompt for Riot API key.
    Skips prompt if a key already exists unless force=True.
    """
    settings = load_settings()
    if settings.riot_api_key and not force:
        return settings.riot_api_key

    print()
    print("=" * 60)
    print("  롤 개인 코치 — Riot API 키 설정")
    print("=" * 60)
    print("1. https://developer.riotgames.com/ 접속")
    print("2. 로그인 후 Development API Key (RGAPI-...) 복사")
    print("3. 아래에 붙여넣기 (개인 키는 24시간마다 만료)")
    print("-" * 60)

    while True:
        import getpass

        try:
            key = getpass.getpass("Riot API 키: ").strip()
        except (EOFError, OSError):
            # 터미널이 아닌 환경(리다이렉트 등)에서는 일반 입력으로 폴백
            key = input("Riot API 키: ").strip()
        # Allow pasting with accidental quotes/spaces
        key = key.strip("\"'")
        if not key:
            print("키가 비어 있습니다. 다시 입력하세요.")
            continue
        if not _API_KEY_RE.match(key):
            print("경고: RGAPI-... 형식이 아닌 것 같습니다.")
            confirm = input("그래도 저장할까요? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                continue
        path = save_api_key(key)
        print(f"저장 완료: {path}")
        return key


def ensure_configured(interactive: bool = True) -> Settings:
    """
    Return valid Settings, prompting for API key if needed.
    Raises SystemExit if non-interactive and key is missing.
    """
    settings = load_settings()
    if not settings.riot_api_key:
        if not interactive:
            raise SystemExit(
                "RIOT_API_KEY not set. Run: python -m lol_coach setup\n"
                f"Or create {ENV_PATH} from .env.example"
            )
        key = prompt_for_api_key(force=True)
        settings = load_settings()
        settings.riot_api_key = key
    return settings


# ── 멀티 프로필 (profiles.json) ──────────────────────────────────────


def _read_profiles(path: Path | None = None) -> list[dict]:
    p = path or PROFILES_PATH
    try:
        if not p.exists():
            return []
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("riot_id")]
    except Exception:
        pass
    return []


def _write_profiles(profiles: list[dict], path: Path | None = None) -> Path:
    p = path or PROFILES_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def list_profiles(path: Path | None = None) -> list[dict]:
    """저장된 프로필 목록. 각 항목: {riot_id, platform}."""
    return _read_profiles(path)


def add_profile(
    riot_id: str,
    platform: str = DEFAULT_PLATFORM,
    path: Path | None = None,
) -> Path:
    """프로필 추가/갱신 (같은 riot_id면 platform만 갱신, 최근 사용이 앞으로)."""
    rid = riot_id.strip()
    if "#" not in rid:
        raise ValueError("Riot ID는 Name#TAG 형식이어야 합니다")
    platform_key = normalize_platform(platform)
    profiles = [p for p in _read_profiles(path) if p.get("riot_id") != rid]
    profiles.insert(0, {"riot_id": rid, "platform": platform_key})
    return _write_profiles(profiles[:20], path)


def remove_profile(riot_id: str, path: Path | None = None) -> Path:
    rid = riot_id.strip()
    profiles = [p for p in _read_profiles(path) if p.get("riot_id") != rid]
    return _write_profiles(profiles, path)


# ── UI 설정 (ui.json) — 창 크기/위치 · 테마 ─────────────────────────


def clamp_window_geometry(
    geometry: object,
    *,
    screen_width: int,
    screen_height: int,
) -> str:
    """Keep a saved Tk geometry visible on the current screen."""
    match = re.fullmatch(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", str(geometry or ""))
    if match is None:
        return "1120x920+0+0"

    width, height, x, y = (int(value) for value in match.groups())
    width = min(width, max(screen_width, 1))
    height = min(height, max(screen_height, 1))
    max_x = max(0, screen_width - width)
    max_y = max(0, screen_height - height)
    x = min(max(x, 0), max_x)
    y = min(max(y, 0), max_y)
    return f"{width}x{height}{x:+d}{y:+d}"


def load_ui_settings() -> dict:
    """저장된 UI 설정 (없으면 빈 dict). 값 형식은 호출부에서 검증한다."""
    try:
        if not UI_PATH.exists():
            return {}
        data = json.loads(UI_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_ui_settings(**updates: object) -> Path:
    """UI 설정 병합 저장 (기존 값 보존)."""
    data = load_ui_settings()
    data.update(updates)
    UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = UI_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(UI_PATH)
    return UI_PATH


def _as_bool(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("0", "false", "no", "off", "n"):
            return False
        if s in ("1", "true", "yes", "on", "y"):
            return True
        return default
    return bool(value)


def game_end_notify_enabled() -> bool:
    """매 판 종료 시 소리·작업표시줄 알림 사용 여부 (기본 ON)."""
    return _as_bool(load_ui_settings().get("game_end_notify"), default=True)


def set_game_end_notify(enabled: bool) -> Path:
    """게임 종료 알림 on/off 저장."""
    return save_ui_settings(game_end_notify=bool(enabled))


def game_start_notify_enabled() -> bool:
    """게임 시작 감지 알림 (소리·상태바·위젯) 사용 여부 (기본 ON)."""
    return _as_bool(load_ui_settings().get("game_start_notify"), default=True)


def set_game_start_notify(enabled: bool) -> Path:
    """게임 시작 알림 on/off 저장."""
    return save_ui_settings(game_start_notify=bool(enabled))


def auto_open_latest_match_enabled() -> bool:
    """전적 로드 직후 최근 1판 복기를 자동으로 열지 여부 (기본 OFF)."""
    return _as_bool(load_ui_settings().get("auto_open_latest_match"), default=False)


def set_auto_open_latest_match(enabled: bool) -> Path:
    """전적 로드 시 최근 경기 자동 복기 on/off 저장."""
    return save_ui_settings(auto_open_latest_match=bool(enabled))


def game_end_auto_review_enabled() -> bool:
    """게임 종료 감지 시 복기 패널을 자동으로 열지 여부 (기본 ON)."""
    return _as_bool(load_ui_settings().get("game_end_auto_review"), default=True)


def set_game_end_auto_review(enabled: bool) -> Path:
    """게임 종료 시 자동 복기 on/off 저장."""
    return save_ui_settings(game_end_auto_review=bool(enabled))


def discord_webhook_url() -> str:
    """디스코드 복기 카드 웹훅 URL — 환경변수 우선, ui.json 폴백."""
    env = os.getenv("LOL_COACH_DISCORD_WEBHOOK", "").strip()
    if env:
        return env
    raw = load_ui_settings().get("discord_webhook")
    return raw.strip() if isinstance(raw, str) else ""


def set_discord_webhook(url: str) -> Path:
    """디스코드 웹훅 URL 저장 (빈 문자열이면 해제)."""
    return save_ui_settings(discord_webhook=(url or "").strip())


def discord_review_enabled() -> bool:
    """게임 종료 시 디스코드 복기 카드 자동 전송 여부 (기본 ON)."""
    return _as_bool(load_ui_settings().get("discord_review"), default=True)


def set_discord_review(enabled: bool) -> Path:
    """디스코드 자동 전송 on/off 저장."""
    return save_ui_settings(discord_review=bool(enabled))
