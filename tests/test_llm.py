"""llm 모듈 — 키 감지/우선순위/코칭 프롬프트. 네트워크 없이 단위 검증."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import lol_coach.http_security as hs
from lol_coach import llm


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "custom")
    monkeypatch.setenv("LOL_COACH_LLM_BASE_URL", "https://api.example/custom")
    monkeypatch.setenv("LOL_COACH_LLM_MODEL", "manual-model")


def test_chat_uses_isolated_session(monkeypatch) -> None:
    """chat() 요청은 프록시 환경을 무시하는 secure_session으로 나간다."""
    import json as _json
    import time as real_time

    import requests as real_requests

    calls: dict = {}

    class FakeResp:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=1):
            yield _json.dumps(
                {"choices": [{"message": {"content": "답변"}, "finish_reason": "stop"}]}
            ).encode()

        def close(self):
            pass

    class FakeSession:
        def __init__(self):
            self.trust_env = False

        def post(self, url, **kwargs):
            calls["url"] = url
            calls["trust_env"] = self.trust_env
            return FakeResp()

    monkeypatch.setattr(hs, "secure_session", lambda: FakeSession())

    def boom(*a, **k):
        raise AssertionError("plain requests.post 사용 금지 — secure_session이어야 함")

    monkeypatch.setattr(real_requests, "post", boom)
    monkeypatch.setattr(real_time, "sleep", lambda s: None)

    out = llm.chat("안녕", api_key="sk-test")
    assert out == "답변"
    assert calls.get("url", "").endswith("/chat/completions")
    assert calls.get("trust_env") is False


def _clear_llm_env(monkeypatch) -> None:
    for name in (
        "LOL_COACH_LLM_BASE_URL",
        "LOL_COACH_LLM_MODEL",
        "LOL_COACH_LLM_KEY",
        "LOL_COACH_LLM_PROVIDER",
        "LOL_COACH_LLM_KEY_OPENCODE_GO",
        "LOL_COACH_LLM_KEY_GEMINI",
        "LOL_COACH_LLM_KEY_GROQ",
        "LOL_COACH_LLM_KEY_OPENROUTER",
    ):
        monkeypatch.delenv(name, raising=False)


def test_chat_success(monkeypatch) -> None:
    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {"message": {"content": "- 팁 한 줄\n- 팁 두 줄"}}
                ]
            }

    captured: dict = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["headers"] = kw["headers"]
        captured["json"] = kw["json"]
        return FakeResp()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    out = llm.chat("프롬프트", api_key="sk-x")
    assert out == "- 팁 한 줄\n- 팁 두 줄"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-x"
    assert captured["json"]["model"] == "manual-model"


def test_chat_no_key(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    assert llm.chat("프롬프트", api_key="") is None


@pytest.mark.parametrize("params", [("max_tokens",), ("temperature",), ("max_tokens", "temperature")])
def test_custom_chat_adapts_explicit_unsupported_options(monkeypatch, params) -> None:
    payloads = []
    closed = []

    def post(url, **kwargs):
        payload = dict(kwargs["json"])
        payloads.append(payload)
        rejected = next((p for p in params if p in payload), None)
        data = ({"error": {"param": rejected, "code": "unsupported_parameter"}}
                if rejected else {"choices": [{"message": {"content": "코칭 성공"}}]})
        return SimpleNamespace(
            status_code=400 if rejected else 200, headers={}, json=lambda: data,
            raise_for_status=lambda: None, close=lambda: closed.append(True),
        )

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=post))
    assert llm.chat("프롬프트", api_key="test", model="server-model", max_tokens=850) == "코칭 성공"
    assert len(payloads) == len(params) + 1 == len(closed)
    for payload in payloads:
        assert payload["model"] == "server-model"
        assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 850
    assert all(param not in payloads[-1] for param in params)


@pytest.mark.parametrize("status,param,code,attempts", [
    (401, "temperature", "unsupported_parameter", 3),
    (400, "messages", "unsupported_parameter", 3),
    (400, "max_tokens", "invalid_value", 3),
    (400, "temperature", "unsupported_value", 1),
])
def test_custom_chat_does_not_retry_other_errors_or_exceed_budget(monkeypatch, status, param, code, attempts) -> None:
    calls = []

    def post(*args, **kwargs):
        calls.append(dict(kwargs["json"]))
        return SimpleNamespace(
            status_code=status, headers={},
            json=lambda: {"error": {"param": param, "code": code}},
            close=lambda: None,
        )

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=post))
    assert llm.chat("프롬프트", api_key="test", max_attempts=attempts) is None
    assert len(calls) == 1


def test_chat_custom_has_no_provider_specific_payload(monkeypatch) -> None:
    captured: dict = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "- 팁"}}]}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["json"] = kw["json"]
        captured["headers"] = kw["headers"]
        return FakeResp()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    out = llm.chat("프롬프트", api_key="manual-key", provider="custom")
    assert out == "- 팁"
    assert captured["url"] == "https://api.example/custom/chat/completions"
    assert "reasoning_effort" not in captured["json"]
    assert captured["json"]["model"] == "manual-model"


def test_chat_failure_returns_none(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise TimeoutError("network down")

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=boom))
    assert llm.chat("프롬프트", api_key="sk-x") is None


def test_chat_retries_on_429(monkeypatch) -> None:
    """회귀: 게이트웨이 429(요청 한도)도 5xx처럼 재시도한다."""
    calls: list[int] = []

    def fake_post(*_a, **_k):
        calls.append(1)
        if len(calls) == 1:
            class R429:
                status_code = 429

                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict:
                    return {}

            return R429()

        class R200:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": "- 재시도 성공"}}]}

        return R200()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    out = llm.chat("프롬프트", api_key="sk-x", max_attempts=3)
    assert out == "- 재시도 성공"
    assert len(calls) == 2


def test_chat_429_exhausts_attempts(monkeypatch) -> None:
    """429가 계속되면 재시도 횟수만큼 돌고 None을 반환한다."""
    calls: list[int] = []

    def fake_post(*_a, **_k):
        calls.append(1)
        class R429:
            status_code = 429

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {}

        return R429()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    assert llm.chat("프롬프트", api_key="sk-x", max_attempts=2) is None
    assert len(calls) == 2


def test_coach_lane_prompt_and_fallback(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url, **kw):
        calls.append(kw["json"])
        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "- 초반 강한 교환"}}]}

        return R()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    counters = [
        ("아리", type("C", (), {"champion": "Ahri", "gd15": 340, "gd15_str": "+340", "matches": 15234, "win_rate": None})())
    ]
    out = llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="sk-x")
    assert out == "- 초반 강한 교환"
    user = calls[0]["messages"][1]["content"]
    assert "아칼리" in user and "Ahri" in user and "+340" in user

    _clear_llm_env(monkeypatch)
    assert llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="") is None


def test_coach_lane_model_passthrough(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url, **kw):
        calls.append(kw["json"])

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "- 팁"}}]}

        return R()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    counters = [
        ("아리", type("C", (), {"champion": "Ahri", "gd15": 340, "gd15_str": "+340", "matches": 15234})())
    ]
    llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="sk-x", model="kimi-k3")
    assert calls[0]["model"] == "kimi-k3"
    assert "reasoning_effort" not in calls[0]


def test_enrich_splits_packed_core_line() -> None:
    raw = "- 아이템: 1코어 리안드리 2코어 존야 3코어 라바돈"
    out = llm.enrich_item_tree_response(raw, ["무시"])
    assert "1코어: 리안드리" in out
    assert "2코어: 존야" in out
    assert "3코어: 라바돈" in out


def test_enrich_fills_below_three_cores() -> None:
    raw = "- 라인전 후 사이드 운영\n- 1코어: 리안드리의 고뇌"
    meta = ["리안드리의 고뇌", "마법사의 신발", "라일라이의 수정홀", "존야", "라바돈"]
    out = llm.enrich_item_tree_response(raw, meta)
    assert "1코어: 리안드리" in out
    assert "2코어:" in out and "신발" in out
    assert "3코어:" in out and "라일라이" in out
    assert "메타 빌드로 아이템 트리 보충" in out
    # 이미 있는 1코어는 덮지 않음
    assert out.count("1코어: 리안드리의 고뇌") == 1


def test_enrich_skips_when_enough_cores() -> None:
    raw = "- 1코어: A\n- 2코어: B\n- 3코어: C"
    out = llm.enrich_item_tree_response(raw, ["X", "Y", "Z"])
    assert "메타 빌드로" not in out
    assert "X" not in out


def test_parse_core_items_from_build() -> None:
    assert llm.parse_core_items_from_build(
        "1코어 로스트 챕터 → 2코어 라바돈 → 3코어 존야"
    ) == ["로스트 챕터", "라바돈", "존야"]
    assert llm.parse_core_items_from_build("리안드리 → 존야 → 라바돈")[:2] == [
        "리안드리",
        "존야",
    ]


def test_format_core_path_and_lines() -> None:
    assert llm._format_core_path([]) == "데이터 없음"
    assert llm._format_core_path(["리안드리", "존야", "라바돈"]) == (
        "1코어 리안드리 → 2코어 존야 → 3코어 라바돈"
    )
    lines = llm._format_core_lines(["리안드리", "존야"])
    assert "1코어: 리안드리" in lines
    assert "2코어: 존야" in lines
    assert "3코어: (상황" in lines
    assert "5코어: (상황" in lines
    path = llm._format_core_path([f"i{n}" for n in range(1, 8)])
    assert path.count("코어") == 5

    aram_path = llm._format_core_path(
        [f"i{n}" for n in range(1, 8)], max_cores=6
    )
    assert aram_path.count("코어") == 6


def test_enrich_fills_all_six_aram_slots() -> None:
    meta = ["AA", "BB", "CC", "DD", "EE", "FF"]

    out = llm.enrich_item_tree_response(
        "- 승리 조건: 앞라인 뒤에서 딜\n- 1코어: AA",
        meta,
        min_cores=6,
        max_cores=6,
    )

    assert out is not None
    slots = llm._extract_core_slots(out)
    assert slots == {1: "AA", 2: "BB", 3: "CC", 4: "DD", 5: "EE", 6: "FF"}


def test_enrich_replaces_duplicate_aram_slots_from_meta() -> None:
    meta = ["AA", "BB", "CC", "DD", "EE", "FF"]
    raw = "\n".join(
        (
            "- 1코어: AA",
            "- 2코어: AA",
            "- 3코어: CC",
            "- 4코어: DD",
            "- 5코어: EE",
            "- 6코어: FF",
        )
    )

    out = llm.enrich_item_tree_response(
        raw,
        meta,
        min_cores=6,
        max_cores=6,
    )

    assert out is not None
    slots = llm._extract_core_slots(out)
    assert slots == {1: "AA", 2: "BB", 3: "CC", 4: "DD", 5: "EE", 6: "FF"}


def test_coach_comp_requires_full_item_tree(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url, **kw):
        calls.append(kw["json"])

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "- 1코어: 리안드리"}}]}

        return R()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    out = llm.coach_comp(
        "아지르",
        "미드",
        [("탑", "가렌"), ("정글", "리 신")],
        [],
        ["포킹 위협"],
        ["용 타이밍"],
        [("존야의 모래시계", "암살자 대응")],
        "16.1",
        api_key="sk-x",
        core_items=["리안드리의 고뇌", "마법사의 신발", "라일라이"],
        boots=["마법사의 신발"],
    )
    assert out
    # 모델이 1코어만 줘도 후처리로 3코어까지 보충
    assert "1코어: 리안드리" in out
    assert "2코어:" in out and "3코어:" in out
    assert "메타 빌드로 아이템 트리 보충" in out
    user = calls[0]["messages"][1]["content"]
    assert "1코어: 리안드리" in user or "1코어 리안드리" in user
    assert "3코어" in user and "5코어" in user
    assert "1~2코어만" in user  # 금지 문구
    assert "존야" in user
    assert calls[0]["max_tokens"] >= 2500


def test_coach_aram_prompt_and_patch_anchor(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url, **kw):
        calls.append(kw["json"])

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "- 한타 대응"}}]}

        return R()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    out = llm.coach_aram(
        "베이가",
        ["세라핀", "문도"],
        ["리 신", "케이틀린"],
        "유령의 칼날(S)",
        "15.4",
        api_key="sk-x",
        model="qwen3.7-plus",
    )
    assert out is not None
    assert "한타 대응" in out
    assert calls[0]["model"] == "qwen3.7-plus"
    # 아이템 섹션 제거 — 프롬프트에서 빌드 언급 없음
    prompt = calls[0]["messages"][1]["content"]
    assert "아이템 빌드는 화면에 따로 표시" in prompt
    assert "정글 캠프" in prompt  # SR 전용 금지 가드
    assert "조합 분석" in prompt  # 조합 기반 팁 요구
    assert calls[0]["max_tokens"] >= 1500


def test_coach_lane_patch_anchor(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kw):
        captured["json"] = kw["json"]

        class R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "- 팁"}}]}

        return R()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    counters = [("아리", type("C", (), {"champion": "Ahri", "gd15": 340, "gd15_str": "+340", "matches": 15234})())]
    llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="sk-x")
    user = captured["json"]["messages"][1]["content"]
    assert "분석 데이터 패치: 15.4" in user
    assert "최신 라이브 패치와 다를 수 있음" in user
    assert "현재 롤 패치: 15.4" not in user
    assert "추측해 말하지 않기" in user


def test_push_ai_to_widget() -> None:
    from lol_coach.gui import app as app_mod

    a = app_mod.CoachApp.__new__(app_mod.CoachApp)
    a._last_summary_title = "⚡ vs 아칼리"
    a._last_summary_lines = ["1. 아리 — 초반 강함"]
    a._widget = None
    a._push_ai_to_widget("- 아리 픽 권장\n- 3렙 견제")
    assert a._last_summary_lines[-4:] == [
        "",
        "🤖 AI 코칭 · 핵심",
        "• 아리 픽 권장",
        "• 3렙 견제",
    ]


def test_import_app_module_ok() -> None:
    from lol_coach.gui import app as app_mod

    assert hasattr(app_mod, "CoachApp")


@pytest.mark.parametrize("url", [
    "http://api.example/v1", "https://user:secret@api.example/v1",
    "https://api.example/v1?key=secret", "https://api.example/v1#secret",
    "https://api.example:bad/v1", "file:///tmp/api", "https://api.example/\nsecret",
    "https://api.example/v1?", "https://api.example/v1#",
])
def test_custom_rejects_unsafe_url_without_network(url, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(hs, "secure_session", lambda: calls.append(True))
    with pytest.raises(ValueError) as exc:
        llm.list_models("test-secret", url)
    assert "secret" not in str(exc.value)
    assert calls == []


@pytest.mark.parametrize("base", ["https://api.example/custom", "http://localhost:8123/v1", "http://127.0.0.1:8123", "http://[::1]:8123/v2"])
def test_custom_model_list_preserves_base_path_and_closes(base, monkeypatch) -> None:
    calls = []
    closed = []
    response = SimpleNamespace(
        status_code=200, headers={},
        json=lambda: {"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "z-model"}, {}, {"id": 3}]},
        close=lambda: closed.append(True),
    )
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=get))
    assert llm.list_models("manual-secret", base + "/") == ["z-model", "a-model"]
    assert calls[0][0] == base + "/models"
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["headers"]["Authorization"] == "Bearer manual-secret"
    assert closed == [True]


def test_custom_chat_does_not_forward_saved_key_to_other_base(monkeypatch) -> None:
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "custom")
    monkeypatch.setenv("LOL_COACH_LLM_BASE_URL", "https://saved.example/v1")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "saved-secret")
    monkeypatch.setenv("LOL_COACH_LLM_MODEL", "saved-model")
    calls = []
    monkeypatch.setattr(hs, "secure_session", lambda: calls.append(True))
    assert llm.chat("prompt", base_url="https://different.example/v1", model="manual") is None
    assert calls == []


@pytest.mark.parametrize("status", [302, 307, 401, 403, 404, 500])
def test_custom_listing_errors_are_safe_and_close_response(status, monkeypatch) -> None:
    closed = []
    response = SimpleNamespace(status_code=status, headers={"Location": "https://secret.example/?key=secret"}, close=lambda: closed.append(True))
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    with pytest.raises(RuntimeError) as exc:
        llm.list_models("secret", "https://api.example/v1")
    assert "secret" not in str(exc.value)
    assert closed == [True]


def test_custom_manual_model_works_when_listing_unavailable(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, headers={}, raise_for_status=lambda: None, json=lambda: {"choices": [{"message": {"content": "manual response"}}]})
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(
        get=lambda *a, **k: SimpleNamespace(status_code=404), post=post,
    ))
    with pytest.raises(RuntimeError):
        llm.list_models("key", "https://manual.example/api/v3")
    assert llm.chat("prompt", api_key="key", model="not-listed", base_url="https://manual.example/api/v3") == "manual response"
    assert calls[0][0] == "https://manual.example/api/v3/chat/completions"
    assert calls[0][1]["json"]["model"] == "not-listed"
    assert calls[0][1]["allow_redirects"] is False


def test_custom_timeout_error_does_not_echo_key_or_url(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("Bearer private-secret https://api.example/private-path")
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=fail))
    with pytest.raises(RuntimeError) as exc:
        llm.list_models("private-secret", "https://api.example/private-path")
    assert "private" not in str(exc.value)
    ok, message = llm.probe_gateway("private-secret", base_url="https://api.example/private-path")
    assert not ok
    assert "private" not in message


@pytest.mark.parametrize("data", [[], {}, {"data": None}, {"data": "bad"}])
def test_custom_malformed_model_list_has_safe_error(data, monkeypatch):
    closed = []
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: SimpleNamespace(
        status_code=200, headers={}, json=lambda: data, close=lambda: closed.append(True),
    )))
    with pytest.raises(RuntimeError):
        llm.list_models("key", "https://api.example/v1")
    assert closed == [True]


def test_custom_empty_model_list_and_oversized_response(monkeypatch):
    response = SimpleNamespace(status_code=200, headers={}, json=lambda: {"data": []})
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: response))
    assert llm.list_models("key", "https://api.example/v1") == []
    response.headers["Content-Length"] = str(5 * 1024 * 1024)
    with pytest.raises(RuntimeError):
        llm.list_models("key", "https://api.example/v1")


@pytest.mark.parametrize("provider", ["opencode-go", "groq", "gemini", "openrouter", ""])
def test_custom_legacy_credentials_never_resolve(provider, monkeypatch):
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", provider)
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "legacy-common-key")
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GROQ", "legacy-provider-key")
    assert llm.resolve_api_key() == ""


def test_custom_saved_key_resolution_requires_same_base(monkeypatch):
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "saved-key")
    assert llm.resolve_api_key(base_url="https://api.example/custom/") == "saved-key"
    assert llm.resolve_api_key(base_url="https://api.example/other") == ""
    assert llm.resolve_api_key("explicit-key", base_url="https://new.example/v2") == "explicit-key"


@pytest.mark.parametrize("base", ["", "   "])
def test_custom_blank_model_lookup_url_never_uses_saved_endpoint(monkeypatch, base):
    calls = []
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(
        get=lambda *args, **kwargs: calls.append(args) or SimpleNamespace(
            status_code=200, headers={}, json=lambda: {"data": []}, close=lambda: None,
        ),
    ))
    with pytest.raises(ValueError):
        llm.list_models("new-draft-key", base)
    ok, _ = llm.probe_gateway("new-draft-key", base_url=base)
    assert not ok
    assert calls == []


@pytest.mark.parametrize("coach", ["lane", "comp", "aram", "review"])
def test_custom_all_coaching_wrappers_forward_base(coach, monkeypatch):
    captured = []
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: captured.append(kw) or "response")
    args = dict(api_key="key", model="manual", base_url="https://selected.example/api/v2")
    if coach == "lane":
        llm.coach_lane("아리", "미드", [], "16.1", **args)
    elif coach == "comp":
        llm.coach_comp("아리", "미드", [], [], [], [], [], "16.1", **args)
    elif coach == "aram":
        llm.coach_aram("아리", [], [], "", "16.1", **args)
    else:
        match = SimpleNamespace(win=True, champion_name="아리", kda_str="1/0/1", kda_ratio=2, cs=10, damage_to_champs=500, kill_participation=0.5, deaths=0, duration_min=10)
        review = SimpleNamespace(win_loss_reasons=[], good=[], improve=[])
        llm.coach_review(match, review, **args)
    assert captured[0]["api_key"] == "key"
    assert captured[0]["model"] == "manual"
    assert captured[0]["base_url"] == "https://selected.example/api/v2"
