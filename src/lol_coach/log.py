"""공통 로깅 — CLI ``-v`` / GUI 부팅 시 한 번 초기화.

라이브러리 모듈은 ``logging.getLogger("lol_coach...")`` 로 로그만 남기고,
화면 출력은 기존 rich/GUI 경로를 그대로 사용한다.
"""

from __future__ import annotations

import logging
import os

_LOGGER_NAME = "lol_coach"
_initialized = False


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def setup_logging(verbose: bool = False) -> None:
    """루트 로거 설정 (여러 번 호출필도 안전).

    - ``verbose=True`` 또는 환경변수 ``LOL_COACH_DEBUG=1`` → DEBUG
    - 기본은 WARNING (조용)
    """
    global _initialized
    debug = verbose or os.environ.get("LOL_COACH_DEBUG", "").lower() in (
        "1",
        "true",
        "yes",
    )
    level = logging.DEBUG if debug else logging.WARNING
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    for handler in logger.handlers:
        handler.setLevel(level)
    _initialized = True
