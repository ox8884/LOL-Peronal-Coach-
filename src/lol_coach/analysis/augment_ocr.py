"""아수라장 제시 증강 — 화면 캡처 + Windows OCR + 카탈로그 매칭.

Riot은 맵에서 뜨는 3장을 LCU로 주지 않는다. 붙여넣기 대신
증강 창이 보일 때 화면 글자를 읽어 카탈로그 이름과 맞춘다.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import tempfile
from ctypes import wintypes
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
$lineObjs = @()
foreach ($line in $result.Lines) {
    if (-not $line.Words -or $line.Words.Count -eq 0) { continue }
    $minX = [double]::MaxValue; $minY = [double]::MaxValue
    $maxX = 0.0; $maxY = 0.0
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        if ($r.X -lt $minX) { $minX = [double]$r.X }
        if ($r.Y -lt $minY) { $minY = [double]$r.Y }
        $right = [double]$r.X + [double]$r.Width
        $bottom = [double]$r.Y + [double]$r.Height
        if ($right -gt $maxX) { $maxX = $right }
        if ($bottom -gt $maxY) { $maxY = $bottom }
    }
    $lineObjs += @{
        t = [string]$line.Text
        x = $minX
        y = $minY
        w = [math]::Max(0.0, $maxX - $minX)
        h = [math]::Max(0.0, $maxY - $minY)
    }
}
$payload = @{ text = $text; lines = @($lineObjs) }
$json = $payload | ConvertTo-Json -Compress -Depth 6
if ($Out) {
    [System.IO.File]::WriteAllText($Out, $json, [System.Text.UTF8Encoding]::new($false))
} else {
    Write-Output $json
}
"""


@dataclass(frozen=True)
class OfferedRead:
    """화면에서 읽은 제시 증강."""

    names: list[str]
    reason: str  # ok | blank | empty_ocr | no_match | weak_match | error
    raw: str = ""


@dataclass(frozen=True)
class OcrLine:
    text: str
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0


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


def pick_offered_from_lines(
    lines: list[OcrLine],
    records: list[Any],
    *,
    width: float,
) -> list[str]:
    """카드 3열(좌·중·우)에서 각 열의 가장 그럴듯한 이름 하나씩.

    앱 위젯의 실버 TOP 3처럼 한쪽에 쌓인 이름은 한 열로만 잡혀
    한 개만 나오고, 맵의 3장은 열마다 하나씩 나온다.
    """
    if width <= 0:
        width = 1.0
    bands: list[list[tuple[float, int, str]]] = [[], [], []]
    for line in lines:
        names = match_catalog_names(line.text, records, limit=1)
        if not names:
            continue
        idx = min(2, max(0, int(line.cx / width * 3)))
        bands[idx].append((line.h, len(names[0]), names[0]))
    out: list[str] = []
    seen: set[str] = set()
    for band in bands:
        if not band:
            continue
        band.sort(key=lambda item: (-item[0], -item[1]))
        name = band[0][2]
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
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


def _lol_window_rect() -> tuple[int, int, int, int] | None:
    hwnd = _find_lol_hwnd()
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if int(rect.right - rect.left) < 200 or int(rect.bottom - rect.top) < 200:
        return None
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def _grab_window_image(hwnd: int) -> Any | None:
    """PrintWindow(PW_RENDERFULLCONTENT) — 일부 전체화면/테두리없음 창."""
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
    """롤 창만 잘라 증강 선택 영역을 얻는다. 다른 모니터의 앱은 읽지 않는다."""
    from PIL import ImageGrab

    hwnd = _find_lol_hwnd()
    image = None
    source = "none"
    box = _lol_window_rect()
    if box is not None:
        try:
            image = ImageGrab.grab(bbox=box, all_screens=True)
            source = "lol-bbox"
        except Exception as exc:
            _log.debug("롤 창 bbox 캡처 실패: %s", exc)
            image = None
        if (image is None or image_is_blank(image)) and hwnd:
            win_img = _grab_window_image(hwnd)
            if win_img is not None and not image_is_blank(win_img):
                image = win_img
                source = "window"
    if image is None or image_is_blank(image):
        try:
            image = ImageGrab.grab(all_screens=False)
            source = "primary"
        except Exception as exc:
            _log.debug("주 모니터 캡처 실패: %s", exc)
            image = None
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


def _run_ocr_script(path: Path, *, lang: str, timeout: float) -> str:
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


def parse_ocr_payload(raw: str) -> tuple[str, list[OcrLine]]:
    """PowerShell JSON 또는 예전 평문 OCR 출력을 파싱한다."""
    text = (raw or "").strip()
    if not text:
        return "", []
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text, [OcrLine(text=text)]
        blob = str(data.get("text") or "")
        lines_raw = data.get("lines") or []
        if isinstance(lines_raw, dict):
            lines_raw = [lines_raw]
        lines: list[OcrLine] = []
        if isinstance(lines_raw, list):
            for item in lines_raw:
                if not isinstance(item, dict):
                    continue
                line_text = str(item.get("t") or item.get("text") or "").strip()
                if not line_text:
                    continue
                lines.append(
                    OcrLine(
                        text=line_text,
                        x=float(item.get("x") or 0),
                        y=float(item.get("y") or 0),
                        w=float(item.get("w") or 0),
                        h=float(item.get("h") or 0),
                    )
                )
        return blob or " ".join(ln.text for ln in lines), lines
    return text, [OcrLine(text=text)]


def ocr_image_windows(path: Path, *, lang: str = "ko", timeout: float = 12.0) -> str:
    """Windows 기본 OCR. 콘솔 창을 띄우지 않는다."""
    text, _lines = parse_ocr_payload(_run_ocr_script(path, lang=lang, timeout=timeout))
    return text


def ocr_layout_windows(
    path: Path, *, lang: str = "ko", timeout: float = 12.0
) -> tuple[str, list[OcrLine]]:
    return parse_ocr_payload(_run_ocr_script(path, lang=lang, timeout=timeout))


def inspect_offered_from_screen(records: list[Any]) -> OfferedRead:
    """롤 창 중앙 3열에서 제시 증강을 읽는다. 한 장만 잡히면 버린다."""
    with tempfile.TemporaryDirectory(prefix="lol-coach-ocr-") as tmp:
        png = Path(tmp) / "picker.png"
        try:
            image, _source = grab_picker_image()
            if image is None or image_is_blank(image):
                return OfferedRead([], "blank")
            image.save(png, format="PNG")
            raw, lines = ocr_layout_windows(png)
        except Exception as exc:
            _log.debug("증강 화면 읽기 실패: %s", exc)
            return OfferedRead([], "error")
        if not raw.strip() and not lines:
            return OfferedRead([], "empty_ocr")
        names = pick_offered_from_lines(lines, records, width=float(image.width))
        snippet = raw[:200]
        if len(names) >= 2:
            return OfferedRead(names, "ok", raw=snippet)
        if names:
            return OfferedRead(names, "weak_match", raw=snippet)
        return OfferedRead([], "no_match", raw=snippet)


def read_offered_from_screen(records: list[Any]) -> list[str]:
    """화면 중앙을 읽어 카탈로그와 맞는 증강 이름 최대 3개."""
    result = inspect_offered_from_screen(records)
    return list(result.names) if result.reason == "ok" else []
