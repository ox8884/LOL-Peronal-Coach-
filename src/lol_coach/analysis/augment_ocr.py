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
$wordObjs = @()
foreach ($line in $result.Lines) {
    if (-not $line.Words) { continue }
    foreach ($word in $line.Words) {
        $r = $word.BoundingRect
        $wordObjs += @{
            t = [string]$word.Text
            x = [double]$r.X
            y = [double]$r.Y
            w = [double]$r.Width
            h = [double]$r.Height
        }
    }
}
$payload = @{ text = $text; lines = @($lineObjs); words = @($wordObjs) }
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


def match_catalog_names_in_order(text: str, records: list[Any], *, limit: int = 3) -> list[str]:
    """한 줄에 카드 여러 장이 붙어도 왼쪽부터 이름을 모두 살린다."""
    hay = _compact(text)
    if not hay:
        return []
    candidates: list[tuple[int, int, str, str]] = []
    for rec in records:
        labels = [getattr(rec, "name_ko", ""), getattr(rec, "name_en", "")]
        labels.extend(getattr(rec, "aliases", ()) or ())
        rec_id = str(getattr(rec, "id", "") or getattr(rec, "name_en", ""))
        best_pos = -1
        best_len = 0
        display = str(getattr(rec, "name_ko", "") or getattr(rec, "name_en", "") or "")
        for label in labels:
            needle = _compact(str(label))
            if len(needle) < _MIN_LABEL:
                continue
            pos = hay.find(needle)
            if pos >= 0 and len(needle) > best_len:
                best_pos = pos
                best_len = len(needle)
        if best_pos >= 0 and display:
            candidates.append((best_pos, best_len, rec_id, display))
    candidates.sort(key=lambda item: (item[0], -item[1]))
    out: list[str] = []
    seen: set[str] = set()
    occupied: list[tuple[int, int]] = []
    for pos, length, rec_id, display in candidates:
        if rec_id in seen:
            continue
        end = pos + length
        if any(pos < oend and end > ostart for ostart, oend in occupied):
            continue
        seen.add(rec_id)
        occupied.append((pos, end))
        out.append(display)
        if len(out) >= limit:
            break
    return out


def _column_of(cx: float, width: float) -> int:
    if width <= 0:
        return 0
    return min(2, max(0, int(cx / width * 3)))


def _one_name_per_column(placed: list[tuple[float, float, str]], width: float) -> list[str]:
    """(cx, height, name) → 좌·중·우 각 1개."""
    bands: list[list[tuple[float, str]]] = [[], [], []]
    for cx, height, name in placed:
        bands[_column_of(cx, width)].append((height, name))
    out: list[str] = []
    seen: set[str] = set()
    for band in bands:
        if not band:
            continue
        band.sort(key=lambda item: -item[0])
        name = band[0][1]
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def cluster_words_by_gaps(words: list[OcrLine], width: float, *, k: int = 3) -> list[list[OcrLine]]:
    """카드 사이 큰 가로 틈으로 단어를 최대 3묶음으로 나눈다."""
    if not words:
        return []
    min_h = max(4.0, width * 0.01)
    useful = [w for w in words if w.h >= min_h or len((w.text or "").strip()) >= 2]
    if not useful:
        useful = list(words)
    ordered = sorted(useful, key=lambda w: w.cx)
    if len(ordered) == 1:
        return [ordered]
    gaps = [
        (ordered[i].x - (ordered[i - 1].x + ordered[i - 1].w), i)
        for i in range(1, len(ordered))
    ]
    min_gap = max(20.0, width * 0.05)
    big = sorted((g, i) for g, i in gaps if g >= min_gap)
    big.sort(reverse=True)
    splits = sorted(i for _g, i in big[: k - 1])
    if not splits:
        return [ordered]
    clusters: list[list[OcrLine]] = []
    start = 0
    for split in splits + [len(ordered)]:
        chunk = ordered[start:split]
        if chunk:
            clusters.append(chunk)
        start = split
    return clusters


def pick_offered_from_lines(
    lines: list[OcrLine],
    records: list[Any],
    *,
    width: float,
    words: list[OcrLine] | None = None,
) -> list[str]:
    """카드 3열에서 이름을 고른다. 한 줄에 두 장이 붙어도 둘 다 살린다."""
    if width <= 0:
        width = 1.0
    placed: list[tuple[float, float, str]] = []
    for line in lines:
        names = match_catalog_names_in_order(line.text, records, limit=3)
        if not names:
            continue
        if len(names) == 1:
            placed.append((line.cx, line.h, names[0]))
            continue
        slot = line.w / len(names) if line.w > 1 else width / max(len(names), 1)
        for i, name in enumerate(names):
            placed.append((line.x + (i + 0.5) * slot, line.h, name))
    names = _one_name_per_column(placed, width)
    if len(names) >= 3 or not words:
        return names
    for cluster in cluster_words_by_gaps(words, width):
        blob = "".join(w.text for w in sorted(cluster, key=lambda w: (w.y, w.x)))
        found = match_catalog_names_in_order(blob, records, limit=1)
        if not found:
            continue
        cx = sum(w.cx for w in cluster) / len(cluster)
        height = max(w.h for w in cluster)
        placed.append((cx, height, found[0]))
    return _one_name_per_column(placed, width)


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
        int(width * 0.03),
        int(height * 0.16),
        int(width * 0.97),
        int(height * 0.82),
    )
    return image.crop(box)


def _prepare_for_ocr(image: Any) -> Any:
    """어두운 카드 위 금색 글자를 OCR이 읽기 쉽게 키우고 대비를 올린다."""
    from PIL import Image, ImageOps, ImageStat

    gray = ImageOps.autocontrast(image.convert("L"), cutoff=2)
    try:
        mean = float(ImageStat.Stat(gray).mean[0])
    except Exception:
        mean = 128.0
    if mean < 100:
        gray = ImageOps.invert(gray)
    return gray.resize(
        (max(2, gray.width * 2), max(2, gray.height * 2)),
        resample=Image.Resampling.LANCZOS,
    ).convert("RGB")


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


def _ocr_items(raw_items: object) -> list[OcrLine]:
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    out: list[OcrLine] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        line_text = str(item.get("t") or item.get("text") or "").strip()
        if not line_text:
            continue
        out.append(
            OcrLine(
                text=line_text,
                x=float(item.get("x") or 0),
                y=float(item.get("y") or 0),
                w=float(item.get("w") or 0),
                h=float(item.get("h") or 0),
            )
        )
    return out


def parse_ocr_payload(raw: str) -> tuple[str, list[OcrLine], list[OcrLine]]:
    """PowerShell JSON 또는 예전 평문 OCR 출력을 파싱한다. (text, lines, words)."""
    text = (raw or "").strip()
    if not text:
        return "", [], []
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text, [OcrLine(text=text)], []
        blob = str(data.get("text") or "")
        lines = _ocr_items(data.get("lines"))
        words = _ocr_items(data.get("words"))
        return blob or " ".join(ln.text for ln in lines), lines, words
    return text, [OcrLine(text=text)], []


def ocr_image_windows(path: Path, *, lang: str = "ko", timeout: float = 12.0) -> str:
    """Windows 기본 OCR. 콘솔 창을 띄우지 않는다."""
    text, _lines, _words = parse_ocr_payload(_run_ocr_script(path, lang=lang, timeout=timeout))
    return text


def ocr_layout_windows(
    path: Path, *, lang: str = "ko", timeout: float = 12.0
) -> tuple[str, list[OcrLine], list[OcrLine]]:
    return parse_ocr_payload(_run_ocr_script(path, lang=lang, timeout=timeout))


def _ocr_card_slices(image: Any, records: list[Any], tmp: Path) -> list[str]:
    """좌·중·우를 따로 읽어 한 장만 빠진 칸을 채운다."""
    width, height = image.size
    bounds = ((0.0, 0.38), (0.31, 0.69), (0.62, 1.0))
    out: list[str] = []
    seen: set[str] = set()
    for i, (left, right) in enumerate(bounds):
        crop = image.crop((int(width * left), 0, max(int(width * right), int(width * left) + 8), height))
        if crop.width < 8 or crop.height < 8:
            continue
        png = tmp / f"slice-{i}.png"
        try:
            _prepare_for_ocr(crop).save(png, format="PNG")
            raw, _lines, _words = ocr_layout_windows(png)
        except Exception as exc:
            _log.debug("칸 OCR 실패(%s): %s", i, exc)
            continue
        for name in match_catalog_names_in_order(raw, records, limit=2):
            if name in seen:
                continue
            seen.add(name)
            out.append(name)
            break
    return out


def inspect_offered_from_screen(records: list[Any]) -> OfferedRead:
    """롤 창 중앙 3열에서 제시 증강을 읽는다. 한 장만 잡히면 버린다."""
    with tempfile.TemporaryDirectory(prefix="lol-coach-ocr-") as tmp:
        folder = Path(tmp)
        png = folder / "picker.png"
        try:
            image, _source = grab_picker_image()
            if image is None or image_is_blank(image):
                return OfferedRead([], "blank")
            prepared = _prepare_for_ocr(image)
            prepared.save(png, format="PNG")
            raw, lines, words = ocr_layout_windows(png)
        except Exception as exc:
            _log.debug("증강 화면 읽기 실패: %s", exc)
            return OfferedRead([], "error")
        if not raw.strip() and not lines:
            return OfferedRead([], "empty_ocr")
        names = pick_offered_from_lines(
            lines, records, width=float(prepared.width), words=words
        )
        if len(names) < 3:
            for extra in _ocr_card_slices(image, records, folder):
                if extra not in names:
                    names.append(extra)
                if len(names) >= 3:
                    break
        snippet = raw[:200]
        if len(names) >= 2:
            return OfferedRead(names[:3], "ok", raw=snippet)
        if names:
            return OfferedRead(names, "weak_match", raw=snippet)
        return OfferedRead([], "no_match", raw=snippet)


def read_offered_from_screen(records: list[Any]) -> list[str]:
    """화면 중앙을 읽어 카탈로그와 맞는 증강 이름 최대 3개."""
    result = inspect_offered_from_screen(records)
    return list(result.names) if result.reason == "ok" else []
