"""아수라장 제시 증강 — 화면 캡처 + Windows OCR + 카탈로그 매칭.

Riot은 맵에서 뜨는 3장을 LCU로 주지 않는다. 붙여넣기 대신
증강 창이 보일 때 화면 글자를 읽어 카탈로그 이름과 맞춘다.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from lol_coach.log import get_logger

_log = get_logger("augocr")

_MIN_LABEL = 3
_AUG_LEVELS = frozenset({3, 7, 11, 15})

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


def grab_picker_png(path: Path) -> Path:
    from PIL import ImageGrab

    image = ImageGrab.grab()
    width, height = image.size
    box = (
        int(width * 0.08),
        int(height * 0.22),
        int(width * 0.92),
        int(height * 0.78),
    )
    image.crop(box).save(path, format="PNG")
    return path


def ocr_image_windows(path: Path, *, lang: str = "ko", timeout: float = 12.0) -> str:
    """Windows 기본 OCR. 엔진/언어가 없으면 빈 문자열."""
    script = path.with_suffix(".ocr.ps1")
    out = path.with_suffix(".ocr.txt")
    script.write_text(_OCR_PS, encoding="utf-8")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
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
    )
    if completed.returncode != 0:
        _log.debug("Windows OCR 실패: %s", (completed.stderr or "")[:300])
        return ""
    try:
        return out.read_text(encoding="utf-8").strip()
    except OSError:
        return (completed.stdout or "").strip()


def read_offered_from_screen(records: list[Any]) -> list[str]:
    """화면 중앙을 읽어 카탈로그와 맞는 증강 이름 최대 3개."""
    with tempfile.TemporaryDirectory(prefix="lol-coach-ocr-") as tmp:
        png = Path(tmp) / "picker.png"
        try:
            grab_picker_png(png)
            raw = ocr_image_windows(png)
        except Exception as exc:
            _log.debug("증강 화면 읽기 실패: %s", exc)
            return []
        if not raw:
            return []
        return match_catalog_names(raw, records)
