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


def test_chat_streams_sse_deltas(monkeypatch) -> None:
    """stream=True + on_delta — SSE 델타를 누적 콜백으로 전달하고 전문 반환."""
    seen_kwargs: dict = {}

    class SSEResponse:
        status_code = 200
        headers = {"Content-Type": "text/event-stream"}
        closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self, chunk_size: int = 1):
            yield 'data: {"choices":[{"delta":{"content":"안녕"}}]}'.encode()
            yield b""
            yield 'data: {"choices":[{"delta":{"content":"하세요"}}]}'.encode()
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'
            yield b"data: [DONE]"

        def close(self) -> None:
            self.closed = True

    resp = SSEResponse()

    def fake_post(_url, **kwargs):
        seen_kwargs["stream"] = kwargs.get("stream")
        seen_kwargs["payload_stream"] = kwargs.get("json", {}).get("stream")
        return resp

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))

    deltas: list[str] = []
    result = llm.chat("프롬프트", api_key="sk-x", max_attempts=1, on_delta=deltas.append)

    assert result == "안녕하세요"
    assert deltas[-1] == "안녕하세요"
    assert len(deltas) >= 2
    assert seen_kwargs["stream"] is True
    assert seen_kwargs["payload_stream"] is True
    assert resp.closed is True


def test_chat_stream_gateway_returns_plain_json(monkeypatch) -> None:
    """게이트웨이가 stream=True를 무시하고 JSON으로 답해도 정상 파싱."""

    class JsonResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            yield b'{"choices":[{"message":{"content":"bulk response"}}]}'

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        hs, "secure_session", lambda: SimpleNamespace(post=lambda *_a, **_k: JsonResponse())
    )

    deltas: list[str] = []
    result = llm.chat("프롬프트", api_key="sk-x", max_attempts=1, on_delta=deltas.append)
    assert result == "bulk response"
    assert deltas == []  # 스트림이 아니었으므로 델타 없음
