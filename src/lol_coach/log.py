"""공통 로깅 — CLI ``-v`` / GUI 부팅 시 한 번 초기화.

라이브러리 모듈은 ``logging.getLogger("lol_coach...")`` 로 로그만 남기고,
화면 출력은 기존 rich/GUI 경로를 그대로 사용한다.

설치본 디버깅을 위해 ``<데이터폴더>/logs/lol_coach.log`` 에도 로그를 남긴다
(기본 INFO; ``-v``/``LOL_COACH_DEBUG=1`` 시 DEBUG).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER_NAME = "lol_coach"
_initialized = False


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


def setup_logging(verbose: bool = False) -> None:
    """루트 로거 설정 (여러 번 호출해도 안전 — 핸들러 중복 등록 없음).

    - ``verbose=True`` 또는 환경변수 ``LOL_COACH_DEBUG=1`` → DEBUG
    - 기본은 INFO (에러·핵심 이벤트 기록)
    - 콘솔 + ``<데이터폴더>/logs/lol_coach.log`` 파일 동시 출력 (로테이션)
    """
    global _initialized
    debug = verbose or os.environ.get("LOL_COACH_DEBUG", "").lower() in (
        "1",
        "true",
        "yes",
    )
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if _initialized:
        for handler in logger.handlers:
            handler.setLevel(level)
        return

    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    stream.setLevel(level)
    logger.addHandler(stream)

    try:
        from lol_coach.config import PROJECT_ROOT

        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "lol_coach.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception:
        pass  # 로그 파일 생성 실패는 치명적이지 않음

    _initialized = True
