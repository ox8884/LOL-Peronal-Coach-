from types import SimpleNamespace

import lol_coach.http_security as hs
from lol_coach import llm


def test_chat_stops_oversized_stream_and_closes_response(monkeypatch) -> None:
    # Given
    stream_requested: list[bool] = []

    class OversizedResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            yield b"a" * (3 * 1024 * 1024)
            yield b"b" * (2 * 1024 * 1024)

        def json(self) -> None:
            raise AssertionError("oversized response must not be parsed")

        def close(self) -> None:
            self.closed = True

    response = OversizedResponse()

    def fake_post(*_args, **kwargs):
        stream_requested.append(kwargs.get("stream") is True)
        return response

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))

    # When
    result = llm.chat("프롬프트", api_key="sk-x", max_attempts=1)

    # Then
    assert result is None
    assert stream_requested == [True]
    assert response.closed is True
