"""아수라장 제시 증강 — 화면 캡처 + Windows OCR + 카탈로그 매칭.

Riot은 맵에서 뜨는 3장을 LCU로 주지 않는다. 붙여넣기 대신
증강 창이 보일 때 화면 글자를 읽어 카탈로그 이름과 맞춘다.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lol_coach.log import get_logger

_log = get_logger("augocr")

_MIN_LABEL = 3
_AUG_LEVELS = frozenset({3, 7, 11, 15})
_CREATE_NO_WINDOW = 0x08000000
_PW_RENDERFULLCONTENT = 2

_OCR_PS = r"""
param([string]$Path, [string]$Lang = "ko", [string]$Out = "")
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
function Await-WinRT($op, [type]$t) {
    $asTask = $asTaskGeneric.MakeGenericMethod($t)
    $netTask = $asTask.Invoke($null, @($op))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
$file = Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$lang = New-Object Windows.Globalization.Language $Lang
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { throw "Windows OCR engine unavailable" }
$result = Await-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$text = [string]$result.Text
if ($Out) {
    [System.IO.File]::WriteAllText($Out, $text, [System.Text.UTF8Encoding]::new($false))
} else {
    Write-Output $text
}
"""


@dataclass(frozen=True)
class OfferedRead:
    """화면에서 읽은 제시 증강."""

    names: list[str]
    reason: str  # ok | blank | empty_ocr | no_match | error
    raw: str = ""


def active_player_level(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    player = payload.get("activePlayer")
    if not isinstance(player, dict):
        return 0
    try:
        return int(player.get("level") or 0)
    except (TypeError, ValueError):
        return 0


def is_augment_level(level: int) -> bool:
    return int(level) in _AUG_LEVELS


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def match_catalog_names(text: str, records: list[Any], *, limit: int = 3) -> list[str]:
    """OCR 문자열에서 카탈로그 증강 이름을 긴 것부터 찾는다."""
    hay = _compact(text)
    if not hay:
        return []
    hits: list[tuple[int, str, str]] = []
    for rec in records:
        labels = [getattr(rec, "name_ko", ""), getattr(rec, "name_en", "")]
        labels.extend(getattr(rec, "aliases", ()) or ())
        rec_id = str(getattr(rec, "id", "") or getattr(rec, "name_en", ""))
        best = ""
        for label in labels:
            needle = _compact(str(label))
            if len(needle) < _MIN_LABEL:
                continue
            if needle in hay and len(needle) > len(best):
                best = needle
        if best:
            display = str(getattr(rec, "name_ko", "") or getattr(rec, "name_en", "") or "")
            hits.append((len(best), rec_id, display))
    hits.sort(key=lambda h: (-h[0], h[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _n, rec_id, display in hits:
        if not display or rec_id in seen:
            continue
        seen.add(rec_id)
        out.append(display)
        if len(out) >= limit:
            break
    return out


def image_is_blank(image: Any) -> bool:
    """전체화면 전용 모드에서 흔히 나오는 검정/단색 캡처."""
    try:
        small = image.convert("L").resize((64, 36))
        flat = getattr(small, "get_flattened_data", None)
        pixels = list(flat() if callable(flat) else small.getdata())
    except Exception:
        return True
    if not pixels:
        return True
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return mean < 10 or var < 6


def _crop_picker(image: Any) -> Any:
    width, height = image.size
    box = (
        int(width * 0.08),
        int(height * 0.22),
        int(width * 0.92),
        int(height * 0.78),
    )
    return image.crop(box)


def _find_lol_hwnd() -> int:
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if "League of Legends" in title:
            found.append(int(hwnd))
        return True

    user32.EnumWindows(_cb, 0)
    for hwnd in found:
        length = int(user32.GetWindowTextLengthW(hwnd))
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "Client" in (buf.value or ""):
            return hwnd
    return found[0] if found else 0


def _grab_window_image(hwnd: int) -> Any | None:
    """PrintWindow(PW_RENDERFULLCONTENT) — 일부 전체화면/테두리없음 창."""
    from ctypes import wintypes

    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width < 200 or height < 200:
        return None

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    old = gdi32.SelectObject(memdc, hbmp)
    try:
        ok = user32.PrintWindow(hwnd, memdc, _PW_RENDERFULLCONTENT)
        if not ok:
            return None
        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3),
            ]

        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buf = ctypes.create_string_buffer(width * height * 4)
        got = gdi32.GetDIBits(memdc, hbmp, 0, height, buf, ctypes.byref(info), 0)
        if not got:
            return None
        return Image.frombuffer("RGB", (width, height), buf, "raw", "BGRX", 0, 1).copy()
    except Exception as exc:
        _log.debug("창 캡처 실패: %s", exc)
        return None
    finally:
        gdi32.SelectObject(memdc, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)


def grab_picker_image() -> tuple[Any | None, str]:
    """화면(또는 롤 창)에서 증강 선택 영역을 자른다. (image, source)."""
    from PIL import ImageGrab

    image = None
    source = "desktop"
    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        _log.debug("ImageGrab 실패: %s", exc)
    if image is None or image_is_blank(image):
        hwnd = _find_lol_hwnd()
        if hwnd:
            win_img = _grab_window_image(hwnd)
            if win_img is not None and not image_is_blank(win_img):
                image = win_img
                source = "window"
    if image is None:
        return None, source
    return _crop_picker(image), source


def grab_picker_png(path: Path) -> Path:
    image, _source = grab_picker_image()
    if image is None:
        raise RuntimeError("화면을 캡처하지 못했습니다")
    image.save(path, format="PNG")
    return path


def _powershell_exe() -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(candidate) if candidate.is_file() else "powershell.exe"


def ocr_image_windows(path: Path, *, lang: str = "ko", timeout: float = 12.0) -> str:
    """Windows 기본 OCR. 콘솔 창을 띄우지 않는다."""
    script = path.with_suffix(".ocr.ps1")
    out = path.with_suffix(".ocr.txt")
    script.write_text(_OCR_PS, encoding="utf-8")
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    completed = subprocess.run(
        [
            _powershell_exe(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Path",
            str(path),
            "-Lang",
            lang,
            "-Out",
            str(out),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        creationflags=_CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        _log.debug("Windows OCR 실패: %s", (completed.stderr or "")[:300])
        return ""
    try:
        return out.read_text(encoding="utf-8").strip()
    except OSError:
        return (completed.stdout or "").strip()


def inspect_offered_from_screen(records: list[Any]) -> OfferedRead:
    """화면 중앙을 읽어 이름과 실패 이유를 같이 돌려준다."""
    with tempfile.TemporaryDirectory(prefix="lol-coach-ocr-") as tmp:
        png = Path(tmp) / "picker.png"
        try:
            image, _source = grab_picker_image()
            if image is None or image_is_blank(image):
                return OfferedRead([], "blank")
            image.save(png, format="PNG")
            raw = ocr_image_windows(png)
        except Exception as exc:
            _log.debug("증강 화면 읽기 실패: %s", exc)
            return OfferedRead([], "error")
        if not raw.strip():
            return OfferedRead([], "empty_ocr")
        names = match_catalog_names(raw, records)
        if not names:
            return OfferedRead([], "no_match", raw=raw[:200])
        return OfferedRead(names, "ok", raw=raw[:200])


def read_offered_from_screen(records: list[Any]) -> list[str]:
    """화면 중앙을 읽어 카탈로그와 맞는 증강 이름 최대 3개."""
    return list(inspect_offered_from_screen(records).names)
