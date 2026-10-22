from typing import TYPE_CHECKING, Any

from .models import MatchSummary, PlayerProfile, RecentForm

if TYPE_CHECKING:
    from .client import RiotAPIError, RiotClient

__all__ = [
    "RiotAPIError",
    "RiotClient",
    "MatchSummary",
    "PlayerProfile",
    "RecentForm",
]


def __getattr__(name: str) -> Any:
    # client 는 requests 를 끌어온다 — 실제 사용 시점까지 import 지연 (GUI 시작 속도)
    if name in ("RiotAPIError", "RiotClient"):
        from . import client

        return getattr(client, name)
    raise AttributeError(name)
