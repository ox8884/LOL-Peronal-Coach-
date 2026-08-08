"""ARAM Mayhem augment icon cache.

Lookup is local-only: callers ask for a display icon and either get a cached
PIL/CTk image or ``None`` (missing).  Network refresh happens through
:func:`refresh_augment_async` / :func:`refresh_augment_sync`, which download
only exact image candidates from :class:`AugmentCatalog`.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from lol_coach.static.augment_catalog import AugmentCatalog, CatalogError

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

_DDRAGON = "https://ddragon.leagueoflegends.com"
_KINDS_ORDER = ("blitz", "riot_data", "riot_patch_notes", "ugg", "league_wiki")

_lock = threading.Lock()
_catalog: AugmentCatalog | None = None

def _get_catalog() -> AugmentCatalog | None:
    """Lazy, thread-safe catalog singleton."""
    global _catalog
    if _catalog is not None:
        return _catalog
    with _lock:
        if _catalog is not None:
            return _catalog
        try:
            _catalog = AugmentCatalog()
        except (CatalogError, FileNotFoundError, ValueError, OSError):
            _catalog = AugmentCatalog({"schema_version": 1, "augments": []})
        return _catalog


def _may_download() -> bool:
    return threading.current_thread() is not threading.main_thread()


def _is_image_bytes(data: bytes) -> bool:
    """PNG/JPEG/GIF/WEBP magic-byte check (guards against HTML saves)."""
    if not data or len(data) < 24:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    return bool(data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def _cache_dir() -> Path:
    """Icon cache root; mirrors ``icons.cache_dir`` without circular imports."""
    try:
        from lol_coach.config import cache_root

        d = cache_root() / "icons"
    except Exception:
        import sys

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


def _augment_key(name_en: str) -> str:
    name = _norm_augment_name(name_en)
    return re.sub(r"[^a-z0-9]", "", name.lower()) or "unknown"


def _norm_augment_name(name_en: str) -> str:
    """Unicode normalization used by the legacy scraper and catalog index."""
    s = (name_en or "").strip()
    for src, dst in (
        ("\u2019", "'"),
        ("\u2018", "'"),
        ("\u2032", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u00a0", " "),
    ):
        s = s.replace(src, dst)
    s = re.sub(r"\s+", " ", s)
    return s


def _raw_path(key: str) -> Path:
    return _cache_dir() / f"a_{key}_raw.png"


def _index_path(key: str) -> Path:
    return _cache_dir() / f"a_{key}_idx.json"


def _display_path(key: str, size: int) -> Path:
    return _cache_dir() / f"a_{key}_{size}.png"


def _read_index(key: str) -> dict[str, str]:
    import json

    path = _index_path(key)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write_index(key: str, url: str, good: bool) -> None:
    import json

    path = _index_path(key)
    try:
        path.write_text(
            json.dumps({"last_url": url, "last_good": good}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _validate_image(data: bytes) -> bool:
    """Ensure ``data`` is a decoded image with both dimensions >= 128 px."""
    if Image is None:
        return False
    if not _is_image_bytes(data):
        return False
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            with Image.open(tmp_path) as im:
                im.load()
                if im.width < 128 or im.height < 128:
                    return False
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return True
    except Exception:
        return False


def _download_one(url: str, dest: Path, timeout: float = 12.0) -> bool:
    """Download a single exact URL; validate it before writing ``dest``."""
    import requests

    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or len(r.content) < 100:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        if "html" in ct or "text/" in ct:
            return False
        if not _validate_image(r.content):
            return False
        dest.write_bytes(r.content)
        return True
    except Exception:
        return False


def _open_local(path: Path, size: int) -> Image.Image | None:
    if Image is None or not path.exists():
        return None
    try:
        im: Any = Image.open(path)
        with im:
            im.load()
            im = im.copy()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        return im.resize((size, size), Image.Resampling.LANCZOS)
    except Exception:
        return None


def _atomic_replace(src: Path, dst: Path) -> None:
    try:
        shutil.move(str(src), str(dst))
    except Exception:
        # Fallback for cross-device moves.
        try:
            dst.write_bytes(src.read_bytes())
            try:
                src.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass


def _resize_and_save(src: Path, dest: Path, size: int) -> bool:
    if Image is None:
        return False
    try:
        im: Any = Image.open(src)
        with im:
            im.load()
            im = im.copy()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        out = im.resize((size, size), Image.Resampling.LANCZOS)
        out.save(dest, format="PNG", optimize=True)
        return True
    except Exception:
        return False


def _candidate_urls(name_en: str) -> list[str]:
    catalog = _get_catalog()
    if catalog is None:
        return []
    return catalog.candidate_urls_for(name_en, kinds_order=_KINDS_ORDER)


def _last_known_good_url(key: str) -> str | None:
    idx = _read_index(key)
    return idx.get("last_url") if idx.get("last_good") else None


def _set_last_known_good(key: str, url: str) -> None:
    _write_index(key, url, good=True)


def _set_failed(key: str, url: str) -> None:
    _write_index(key, url, good=False)


def refresh_augment_sync(name_en: str, timeout: float = 12.0) -> bool:
    """Download and validate the best catalog candidate for ``name_en``.

    Returns ``True`` if a new raw asset was stored.  Existing valid raw assets
    are left untouched.  Safe to call from worker threads.
    """
    key = _augment_key(name_en)
    raw = _raw_path(key)
    if raw.exists():
        try:
            if _validate_image(raw.read_bytes()):
                return True
        except Exception:
            pass
        try:
            raw.unlink(missing_ok=True)
        except Exception:
            pass

    urls = _candidate_urls(name_en)
    if not urls:
        return False

    temp_dir = Path(tempfile.gettempdir())
    for url in urls:
        tmp = temp_dir / f"a_{key}_{threading.current_thread().ident or 0}_dl.png"
        try:
            if _download_one(url, tmp, timeout=timeout) and _validate_image(tmp.read_bytes()):
                _atomic_replace(tmp, raw)
                _set_last_known_good(key, url)
                return True
            _set_failed(key, url)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
    return False


def refresh_augment_async(name_en: str) -> None:
    """Start a background thread that refreshes the augment icon cache."""
    thread = threading.Thread(target=refresh_augment_sync, args=(name_en,), daemon=True)
    thread.start()


def augment_pil(name_en: str, size: int = 40) -> Image.Image | None:
    """Return a cached augment icon at ``size`` or ``None`` if missing.

    On a worker thread this will attempt a synchronous refresh if the asset is
    not yet cached.  On the main thread the lookup is strictly non-network.
    """
    if Image is None:
        return None
    key = _augment_key(name_en)
    display = _display_path(key, size)

    if display.exists():
        im = _open_local(display, size)
        if im is not None:
            return im
        try:
            display.unlink(missing_ok=True)
        except Exception:
            pass

    raw = _raw_path(key)
    if raw.exists():
        im = _open_local(raw, size)
        if im is not None:
            _resize_and_save(raw, display, size)
            return _open_local(display, size) or im
        try:
            raw.unlink(missing_ok=True)
        except Exception:
            pass

    if _may_download():
        refresh_augment_sync(name_en)
        if raw.exists():
            im = _open_local(raw, size)
            if im is not None:
                _resize_and_save(raw, display, size)
                return _open_local(display, size) or im

    return None


def augment_ctk(name_en: str, size: int = 40):
    """Return a cached augment CTkImage or ``None`` if missing."""
    pil = augment_pil(name_en, size)
    if pil is None or Image is None:
        return None
    try:
        import customtkinter as ctk

        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGBA")
        copy = pil.copy()
        return ctk.CTkImage(
            light_image=copy,
            dark_image=copy,
            size=(max(1, copy.width), max(1, copy.height)),
        )
    except Exception:
        return None


def reset_augment_cache(name_en: str | None = None) -> None:
    """Remove cached augment raw/display/index files.  ``None`` clears all."""
    root = _cache_dir()
    if name_en is None:
        for p in root.glob("a_*"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        return
    key = _augment_key(name_en)
    for p in (root / f"a_{key}_raw.png", root / f"a_{key}_idx.json"):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    for p in root.glob(f"a_{key}_*.png"):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
