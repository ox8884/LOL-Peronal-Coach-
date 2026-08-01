"""화면 캡처 → 아수라장 제시 증강 자동 인식 (베타).

방식: 적분 이미지(integral image) 기반 박스 평균색 시그니처 매칭.
증강 아이콘은 색상이 뚜렷해 4x4 그리드 평균색만으로 구분력이 높다.

- 캡처: ``mss`` (선택 의존성)
- 매칭: ``numpy`` (선택 의존성)
- 설치: ``pip install lol-coach[screen]`` 또는 ``pip install mss numpy``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 검색 박스 크기(화면상 증강 아이콘 한 변 픽셀 후보)
_BOX_SIZES = (56, 64, 72, 80, 88, 96)
_GRID = 4  # 4x4 셀 평균색
_DEFAULT_THRESHOLD = 0.93
_MIN_SCORE_GAP = 0.005  # NMS 시 미세 점수 차는 위치 우선


@dataclass
class ScreenMatch:
    name: str
    score: float
    box: tuple[int, int, int, int]  # x, y, w, h


def _np():
    try:
        import numpy as np

        return np
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "화면 인식에는 numpy가 필요합니다: pip install numpy"
        ) from exc


def capture_screen() -> Any:
    """주 모니터 전체 캡처 → PIL.Image (mss 필요)."""
    try:
        import mss
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "화면 캡처에는 mss가 필요합니다: pip install mss"
        ) from exc
    from PIL import Image

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def _signature_from_image(img: Any, grid: int = _GRID):
    """PIL 이미지 → (grid*grid*3,) 평균색 벡터 (0~1)."""
    np = _np()
    small = img.convert("RGB").resize((grid, grid))
    arr = np.asarray(small, dtype=np.float64) / 255.0
    return arr.reshape(-1)


def _integral(arr):
    np = _np()
    ii = np.zeros((arr.shape[0] + 1, arr.shape[1] + 1, 3))
    ii[1:, 1:] = np.cumsum(np.cumsum(arr, axis=0), axis=1)
    return ii


def _box_signatures(ii, size: int, stride: int, grid: int = _GRID):
    """적분 이미지에서 모든 후보 박스의 gridxgrid 평균색 시그니처 + 좌표."""
    np = _np()
    h, w = ii.shape[0] - 1, ii.shape[1] - 1
    cell = size / grid
    boxes: list[tuple[int, int]] = []
    sigs: list = []
    ys = range(0, h - size + 1, stride)
    xs = range(0, w - size + 1, stride)
    coords = [(x, y) for y in ys for x in xs]
    if not coords:
        return np.zeros((0, grid * grid * 3)), []
    cell_coords = [
        (int(round(c * cell)), int(round((c + 1) * cell))) for c in range(grid)
    ]
    for x, y in coords:
        feats = []
        for gy0, gy1 in cell_coords:
            for gx0, gx1 in cell_coords:
                y0, y1 = y + gy0, y + gy1
                x0, x1 = x + gx0, x + gx1
                s = (
                    ii[y1, x1]
                    - ii[y0, x1]
                    - ii[y1, x0]
                    + ii[y0, x0]
                )
                feats.append(s / ((y1 - y0) * (x1 - x0)))
        sigs.append(np.concatenate(feats))
        boxes.append((x, y))
    return np.asarray(sigs), boxes


def match_augments(
    screen: Any,
    templates: dict[str, Any],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    box_sizes: tuple[int, ...] = _BOX_SIZES,
    max_results: int = 6,
) -> list[ScreenMatch]:
    """스크린에서 증강 아이콘 위치를 찾는다.

    - ``screen``: PIL.Image (RGB)
    - ``templates``: {증강 식별자: PIL.Image 아이콘}
    - 반환: 점수순 + 위치 중복 제거(NMS)된 ScreenMatch 목록
    """
    np = _np()
    if not templates:
        return []

    names = list(templates.keys())
    tmat = np.asarray(
        [_signature_from_image(templates[n]) for n in names]
    )
    # 밝기 무관 패턴 비교를 위해 벡터 평균을 뺀다 (NCC) —
    # 회색 배경처럼 균일한 박스는 0 벡터가 되어 자동 탈락.
    tmat = tmat - tmat.mean(axis=1, keepdims=True)
    tmat = tmat / np.clip(
        np.linalg.norm(tmat, axis=1, keepdims=True), 1e-9, None
    )

    arr = np.asarray(screen.convert("RGB"), dtype=np.float64) / 255.0
    ii = _integral(arr)

    candidates: list[ScreenMatch] = []
    for size in box_sizes:
        stride = max(4, size // 6)
        sigs, boxes = _box_signatures(ii, size, stride)
        if sigs.size == 0:
            continue
        sigs = sigs - sigs.mean(axis=1, keepdims=True)
        sigs = sigs / np.clip(
            np.linalg.norm(sigs, axis=1, keepdims=True), 1e-9, None
        )
        sims = sigs @ tmat.T  # (N, M)
        best_t = sims.argmax(axis=1)
        best_s = sims[np.arange(sims.shape[0]), best_t]
        hits = np.nonzero(best_s >= threshold)[0]
        for i in hits:
            x, y = boxes[i]
            candidates.append(
                ScreenMatch(
                    name=names[best_t[i]],
                    score=float(best_s[i]),
                    box=(x, y, size, size),
                )
            )

    # NMS: 점수 높은 것부터, 겹치는 박스/같은 증강 중복 제거
    candidates.sort(key=lambda c: -c.score)
    accepted: list[ScreenMatch] = []
    seen_names: set[str] = set()
    for cand in candidates:
        if cand.name in seen_names:
            continue
        cx, cy, cw, ch = cand.box
        overlap = False
        for prev in accepted:
            px, py, pw, ph = prev.box
            ix = max(0, min(cx + cw, px + pw) - max(cx, px))
            iy = max(0, min(cy + ch, py + ph) - max(cy, py))
            inter = ix * iy
            if inter > 0.3 * min(cw * ch, pw * ph):
                overlap = True
                break
        if overlap:
            continue
        accepted.append(cand)
        seen_names.add(cand.name)
        if len(accepted) >= max_results:
            break

    # 화면 표시 순서(위→아래, 왼쪽→오른쪽)로 정렬
    accepted.sort(key=lambda c: (c.box[1] // 50, c.box[0]))
    return accepted


def build_templates_from_catalog(
    names: list[str],
    *,
    size: int = 48,
) -> dict[str, Any]:
    """캐시된 증강 아이콘 → 매칭용 템플릿 dict (없는 아이콘은 건당 생략)."""
    from lol_coach.static.augment_icons import augment_pil

    out: dict[str, Any] = {}
    for name in names:
        try:
            img = augment_pil(name, size=size)
        except Exception:
            img = None
        if img is not None:
            out[name] = img
    return out
