"""챔피언/아이템 아이콘 — 런타임 다운로드 + 로컬 캐시 (exe 경량 유지).

증강 아이콘 캐시는 ``augment_icons`` 모듈로 이전되었습니다.
``icons.augment_pil``/``icons.augment_ctk``는 하위 호환용 래퍼로,
확인된 캐시 자산이 없으면 ``None``을 반환합니다.
"""


from __future__ import annotations

import re
import sys
import threading
from pathlib import Path
from typing import Any

from lol_coach import http_security
from lol_coach.static import ddragon_cache

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

DDRAGON = "https://ddragon.leagueoflegends.com"
_session = http_security.secure_session()
_session.headers.update({"User-Agent": "lol-coach-icons/1.0"})
_lock = threading.Lock()
_version: str | None = None
_mem: dict[str, object] = {}  # cache key -> PIL Image or CTkImage


def _may_download() -> bool:
    return threading.current_thread() is not threading.main_thread()


def cache_dir() -> Path:
    """아이콘 캐시 — 공통 ``cache_root()`` 아래."""
    try:
        from lol_coach.config import cache_root

        d = cache_root() / "icons"
    except Exception:
        if getattr(sys, "frozen", False):
            import os

            base = Path(
                os.environ.get("LOCALAPPDATA")
                or Path.home() / "AppData" / "Local"
            ) / "롤실전코치"
        else:
            base = Path(__file__).resolve().parents[3]
        d = base / "cache" / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d

def ddragon_version() -> str:
    """Data Dragon 최신 버전 — 성공 시 캐시 저장, 실패 시 마지막 성공 버전 사용."""
    global _version
    if _version:
        return _version
    try:
        versions = ddragon_cache.get_json(_session, f"{DDRAGON}/api/versions.json", "versions", timeout=12)
        _version = str(versions[0])
        try:
            (cache_dir() / ".ddragon_version").write_text(_version, encoding="utf-8")
        except Exception:
            pass
    except Exception:
        try:
            cached = (
                (cache_dir() / ".ddragon_version")
                .read_text(encoding="utf-8")
                .strip()
            )
            if cached:
                _version = cached
        except Exception:
            _version = "14.1.1"
    return _version or "14.1.1"


def _is_image_bytes(data: bytes) -> bool:
    """PNG/JPEG/GIF/WEBP 매직 바이트 확인 (HTML 오저장 방지)."""
    if not data or len(data) < 24:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return bool(data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def _download(url: str, dest: Path, timeout: float = 12.0, *, force: bool = False) -> bool:
    """이미지 URL 다운로드. 기존 파일이 깨져 있으면 다시 받음."""
    if not force and dest.exists() and dest.stat().st_size > 100:
        try:
            if _is_image_bytes(dest.read_bytes()[:64]) or (
                Image is not None and _open_local(dest, 16) is not None
            ):
                return True
        except Exception:
            pass
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
    try:
        data = http_security.download_same_origin(_session, url, http_security.DownloadPolicy(timeout, http_security.MAX_IMAGE_RESPONSE_BYTES))
        if len(data) < 100:
            return False
        if not _is_image_bytes(data):
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def _resize(img: Image.Image, size: int) -> Image.Image:
    # 저용량: LANCZOS 리사이즈, RGB 유지
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _open_local(path: Path, size: int) -> Image.Image | None:
    if Image is None or not path.exists():
        return None
    try:
        im: Any = Image.open(path)
        with im:
            if im.width * im.height > http_security.MAX_IMAGE_PIXELS:
                return None
            im.load()  # 깨진 파일 즉시 감지
            im = im.copy()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        return _resize(im, size)
    except Exception:
        return None


def _placeholder(label: str, size: int, color: tuple[int, int, int]) -> Image.Image:
    """항상 성공하는 대체 배지 (텍스트 1글자)."""
    if Image is None:
        raise RuntimeError("Pillow 필요")
    size = max(16, int(size or 32))
    img = Image.new("RGBA", (size, size), (*color, 255))
    d = ImageDraw.Draw(img)
    text = (label or "?")[:1]
    font = ImageFont.load_default()
    try:
        font = ImageFont.truetype("malgun.ttf", max(10, size // 2))
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", max(10, size // 2))
        except Exception:
            pass
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(
            ((size - tw) / 2, (size - th) / 2 - 1),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
    except Exception:
        pass
    img.info["lol_coach_placeholder"] = True
    return img


def champion_pil(champ_key: str, size: int = 48) -> Image.Image | None:
    """챔피언 키(Ahri) → PIL 이미지."""
    if Image is None:
        return None
    key = re.sub(r"[^A-Za-z0-9]", "", champ_key or "")
    if not key:
        return _placeholder("?", size, (80, 80, 90))
    # Data Dragon 키 특수 케이스
    specials = {
        "Wukong": "MonkeyKing",
        "monkeyking": "MonkeyKing",
        "FiddleSticks": "Fiddlesticks",
    }
    key = specials.get(key, specials.get(key[0].upper() + key[1:], key))
    if key == "Monkeyking":
        key = "MonkeyKing"
    # 첫 글자 대문자 관례
    if key and key[0].islower():
        key = key[0].upper() + key[1:]

    cache_key = f"champ_{key}_{size}"
    with _lock:
        if cache_key in _mem:
            return _mem[cache_key]  # type: ignore

    path = cache_dir() / f"c_{key}_{size}.png"
    if not path.exists():
        if _may_download():
            ver = ddragon_version()
            url = f"{DDRAGON}/cdn/{ver}/img/champion/{key}.png"
            raw = cache_dir() / f"c_{key}_raw.png"
            if _download(url, raw):
                im = _open_local(raw, size)
                if im:
                    rgb = im.convert("RGB")
                    rgb.save(path, format="JPEG", quality=55, optimize=True)
                    im = _resize(Image.open(path).convert("RGBA"), size)
                else:
                    im = _placeholder(key[:1], size, (40, 90, 140))
            else:
                im = _placeholder(key[:1], size, (40, 90, 140))
        else:
            im = _placeholder(key[:1], size, (40, 90, 140))
    else:
        im = _open_local(path, size) or _placeholder(key[:1], size, (40, 90, 140))

    if _may_download() or path.exists():
        with _lock:
            _mem[cache_key] = im
    return im


def item_pil(item_id: int, size: int = 32) -> Image.Image | None:
    if Image is None or not item_id:
        return None
    cache_key = f"item_{item_id}_{size}"
    with _lock:
        if cache_key in _mem:
            return _mem[cache_key]  # type: ignore

    path = cache_dir() / f"i_{item_id}_{size}.jpg"
    if not path.exists():
        raw = cache_dir() / f"i_{item_id}_raw.png"
        im = _open_local(raw, size)
        if im is not None:
            im.convert("RGB").save(path, format="JPEG", quality=50, optimize=True)
            im = _open_local(path, size)
        elif _may_download():
            ver = ddragon_version()
            url = f"{DDRAGON}/cdn/{ver}/img/item/{item_id}.png"
            if _download(url, raw):
                im = _open_local(raw, size)
                if im:
                    im.convert("RGB").save(
                        path, format="JPEG", quality=50, optimize=True
                    )
                    im = _open_local(path, size)
                else:
                    im = _placeholder(str(item_id)[-1], size, (90, 70, 40))
            else:
                im = _placeholder("?", size, (90, 70, 40))
        else:
            im = _placeholder("?", size, (90, 70, 40))
    else:
        im = _open_local(path, size) or _placeholder("?", size, (90, 70, 40))

    if _may_download() or path.exists():
        with _lock:
            _mem[cache_key] = im
    return im


def item_pil_by_name(name_ko_or_en: str, size: int = 32) -> Image.Image | None:
    """한글/영문 아이템명 → 아이콘 (Data Dragon id 역조회)."""
    if Image is None or not name_ko_or_en:
        return None
    try:
        from lol_coach.static.i18n import get_localizer

        loc = get_localizer()
        if not getattr(loc, "_loaded", False) and not _may_download():
            return _placeholder(name_ko_or_en[:1], size, (90, 70, 40))
        loc.ensure_loaded()
        # id → ko reverse
        target = name_ko_or_en.strip()
        for iid, ko in loc._item_ko.items():
            if ko == target:
                return item_pil(int(iid), size)
        # en map
        from lol_coach.static.i18n import _norm_key

        nk = _norm_key(target)
        for en, ko in loc._item_en2ko.items():
            if ko == target or en == nk:
                # find id
                for iid, ko2 in loc._item_ko.items():
                    if ko2 == ko:
                        return item_pil(int(iid), size)
    except Exception:
        pass
    return _placeholder(name_ko_or_en[:1], size, (90, 70, 40))


from lol_coach.static import augment_icons  # noqa: E402 — 하위 호환 래퍼용 지연 배치 import


def augment_pil(name_en: str, rarity: str = "gold", size: int = 40) -> Image.Image | None:
    """Deprecated: use ``augment_icons.augment_pil`` for true cache lookup.

    Delegates to the canonical cache-backed lookup and returns ``None`` when
    no verified asset is available.  Callers must render an explicit missing
    indicator instead of treating a placeholder as a real icon.
    """
    try:
        return augment_icons.augment_pil(name_en, size=size)
    except Exception:
        return None



def augment_ctk(name_en: str, rarity: str = "gold", size: int = 40):
    """Deprecated: use ``augment_icons.augment_ctk`` for true cache lookup.

    Delegates to the canonical cache-backed lookup and returns ``None`` when
    no verified asset is available.
    """
    try:
        return augment_icons.augment_ctk(name_en, size=size)
    except Exception:
        return None



def to_ctk(img: Image.Image | None, size: int | None = None):
    """PIL → CTkImage (customtkinter). 실패 시 None."""
    if img is None or Image is None:
        return None
    try:
        import customtkinter as ctk

        if size:
            img = _resize(img, size)
        # CTkImage는 RGB/RGBA 모두 가능하나 복사본으로 안전 전달
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        w, h = img.size
        return ctk.CTkImage(
            light_image=img.copy(),
            dark_image=img.copy(),
            size=(max(1, w), max(1, h)),
        )
    except Exception:
        return None


def champion_ctk(champ_key: str, size: int = 48):
    try:
        return to_ctk(champion_pil(champ_key, size), size)
    except Exception:
        return None


def item_ctk(item_id: int, size: int = 32):
    try:
        return to_ctk(item_pil(item_id, size), size)
    except Exception:
        return None


def map_pil(map_id: int, size: int = 512) -> Image.Image:
    """미니맵 배경 — DDragon img/map/map{map_id}.png (11=협곡, 12=칼바람).

    실패·오프라인이면 어두운 단색 배경을 반환 (마커는 그 위에 그린다).
    """
    cache_key = f"map_{map_id}_{size}"
    with _lock:
        if cache_key in _mem:
            return _mem[cache_key]  # type: ignore
    im: Image.Image | None = None
    try:
        maps_dir = cache_dir() / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)
        raw = maps_dir / f"m_{map_id}_raw.png"
        ver = ddragon_version()
        url = f"{DDRAGON}/cdn/{ver}/img/map/map{map_id}.png"
        if _may_download() and (not raw.exists() or raw.stat().st_size < 100):
            _download(url, raw)
        im = _open_local(raw, size)
    except Exception:
        im = None
    if im is None:
        im = _placeholder("map", size, (22, 26, 34))
    with _lock:
        _mem[cache_key] = im
    return im


def item_name_ctk(name: str, size: int = 32):
    try:
        image = item_pil_by_name(name, size)
        if image is None or image.info.get("lol_coach_placeholder"):
            return None
        return to_ctk(image, size)
    except Exception:
        return None


