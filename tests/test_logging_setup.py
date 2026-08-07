"""setup_logging 핸들러 중복 등록 방지."""

from __future__ import annotations

import logging

from lol_coach import log


def test_setup_logging_idempotent(monkeypatch, tmp_path) -> None:
    # 이전 테스트/세션 핸들러 초기화
    logger = logging.getLogger("lol_coach")
    logger.handlers.clear()
    log._initialized = False  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "lol_coach.config.PROJECT_ROOT",
        tmp_path,
        raising=False,
    )
    # config import 경유 — setup_logging 내부 import 후 경로
    import lol_coach.config as cfg

    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)

    log.setup_logging(verbose=False)
    n1 = len(logger.handlers)
    log.setup_logging(verbose=True)
    n2 = len(logger.handlers)
    assert n1 == n2
    assert n1 >= 1
    # DEBUG 레벨 반영
    assert logger.level == logging.DEBUG
