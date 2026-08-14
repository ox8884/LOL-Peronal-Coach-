"""디스코드 웹훅 카드 전송 서비스 — tk 없이 콜백으로 UI 갱신.

v1.6.56 회귀 고정:
- 웹훅 URL은 인자로만 받는다 (config 를 import 하지 않는다).
- 예외 문자열(웹훅 토큰 포함 가능)은 절대 UI 에 넣지 않는다.
  notify.discord.post_card 가 DiscordWebhookError 로 래핑한 안전한 메시지만 토스트.

소유권 경합 해소 (gui-service-split 단계2):
- _post_discord_card 공통 경로(웹훅 가드 + 백그라운드 전송 + 토스트)를
  CoachApp self 에서 이 객체로 옮긴다.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from lol_coach.notify.discord import DiscordWebhookError

_log = __import__("logging").getLogger(__name__)

NotifyCb = Callable[..., None]
AfterCb = Callable[[int, Callable[[], None]], Any]


class DiscordCards:
    """디스코드 카드 전송 서비스.

    after_cb(ms, fn)  — UI 스레드로 콜백 마셜링 (tk after(0, ...) 등).
    notify_cb(msg, *, level, ms, ...) — 토스트/상태바 알림.
    """

    def __init__(self, *, after_cb: AfterCb, notify_cb: NotifyCb) -> None:
        self._after = after_cb
        self._notify = notify_cb

    def post_card(
        self,
        *,
        webhook_url: str | None,
        title_fn: Callable[[], str],
        description_fn: Callable[[], str],
        png_bytes_fn: Callable[[], bytes],
        footer_fn: Callable[[], str],
        ok_msg: str,
        fail_msg: str,
    ) -> None:
        """웹훅 가드 + 백그라운드 전송 + 토스트 공통 경로.

        webhook_url 이 비어 있으면 부수 효과 없이 스킵한다 (렌더도 타지 않음).
        전송은 데몬 스레드에서 비동기로 일어난다.
        실패 시 DiscordWebhookError 의 안전한 메시지만 토스트 —
        원본 예외(토큰 포함 가능)는 UI 에 노출하지 않는다.
        """
        if not webhook_url:
            return

        def work() -> None:
            try:
                from lol_coach.notify.discord import post_card as _post_card

                _post_card(
                    webhook_url,
                    title=title_fn(),
                    description=description_fn(),
                    png_bytes=png_bytes_fn(),
                    footer=footer_fn(),
                )

                def _ok() -> None:
                    self._notify(ok_msg, level="ok", ms=2600)

                self._after(0, _ok)
            except DiscordWebhookError as exc:
                # post_card 가 래핑한 안전한 메시지 — 토큰 누출 없음

                def _fail(_exc: DiscordWebhookError = exc) -> None:
                    self._notify(f"{fail_msg}: {_exc}", level="error", ms=5200)

                self._after(0, _fail)
            except Exception as exc:
                _log.exception("디스코드 카드 전송 실패: %s", exc)

                def _fail_unknown() -> None:
                    self._notify(fail_msg, level="error", ms=5200)

                self._after(0, _fail_unknown)

        threading.Thread(target=work, daemon=True).start()
