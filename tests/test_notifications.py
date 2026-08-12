from types import SimpleNamespace

from lol_coach.gui.notify_mixin import NotifyMixin


def test_focus_active_game_notifications_are_queued_and_deduplicated() -> None:
    status_updates: list[str] = []
    app = SimpleNamespace(
        _live_notification_blocked=True,
        status=SimpleNamespace(
            configure=lambda **kwargs: status_updates.append(kwargs["text"])
        ),
        _flash_status=lambda text: status_updates.append(text),
        _queue_notification=lambda message, level, ms, also_status: NotifyMixin._queue_notification(
            app, message, level, ms, also_status
        ),
        _toast_win=None,
        after_cancel=lambda job: None,
        after=lambda ms, callback: None,
    )

    NotifyMixin._notify(app, "새 게임 이벤트", level="info")
    NotifyMixin._notify(app, "새 게임 이벤트", level="info")

    assert status_updates == []
    assert app._notification_queue == [("새 게임 이벤트", "info", 3800, True)]


def test_focus_notification_queue_flushes_once_after_game() -> None:
    delivered: list[tuple[str, str, int, bool]] = []
    app = SimpleNamespace(
        _live_notification_blocked=True,
        _deliver_notification=lambda *args, **kwargs: delivered.append(
            (args[0], kwargs["level"], kwargs["ms"], kwargs["also_status"])
        ),
    )

    app._notification_queue = [("게임 중 이벤트", "info", 3800, True)]

    NotifyMixin._flush_notification_queue(app)

    assert delivered == [("게임 중 이벤트", "info", 3800, True)]
    assert app._notification_queue == []


def test_notification_queue_flush_prioritizes_severity() -> None:
    """게임 중 쌓인 error/warn가 info에 묻히지 않아야 한다."""
    delivered: list[tuple[str, str, int, bool]] = []
    app = SimpleNamespace(
        _live_notification_blocked=True,
        _deliver_notification=lambda *args, **kwargs: delivered.append(
            (args[0], kwargs["level"], kwargs["ms"], kwargs["also_status"])
        ),
    )

    app._notification_queue = [
        ("게임 중 안내", "info", 3800, True),
        ("API 오류 발생", "error", 5200, True),
    ]

    NotifyMixin._flush_notification_queue(app)

    assert delivered == [("API 오류 발생", "error", 5200, True)]
    assert app._notification_queue == []
