"""llm 모듈 — 키 감지/우선순위/코칭 프롬프트. 네트워크 없이 단위 검증."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import lol_coach.http_security as hs
from lol_coach import llm


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)


def _fake_auth(tmp_path, key: str = "sk-opencode-test") -> object:
    p = tmp_path / "auth.json"
    p.write_text(
        json.dumps({"opencode-go": {"type": "api", "key": key}}), encoding="utf-8"
    )
    return p


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


def test_detect_opencode_key_found(tmp_path) -> None:
    p = _fake_auth(tmp_path)
    assert llm.detect_opencode_key(p) == "sk-opencode-test"


def test_detect_opencode_key_missing(tmp_path) -> None:
    assert llm.detect_opencode_key(tmp_path / "nope.json") == ""
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert llm.detect_opencode_key(bad) == ""


def _clear_llm_env(monkeypatch) -> None:
    for name in (
        "LOL_COACH_LLM_KEY",
        "LOL_COACH_LLM_PROVIDER",
        "LOL_COACH_LLM_KEY_OPENCODE_GO",
        "LOL_COACH_LLM_KEY_GEMINI",
        "LOL_COACH_LLM_KEY_GROQ",
        "LOL_COACH_LLM_KEY_OPENROUTER",
    ):
        monkeypatch.delenv(name, raising=False)


def test_resolve_api_key_priority(tmp_path, monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    fake = _fake_auth(tmp_path, key="sk-detected")
    monkeypatch.setattr(llm, "_OPENCODE_AUTH", fake)
    assert llm.resolve_api_key("sk-manual") == "sk-manual"
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "sk-env")
    assert llm.resolve_api_key() == "sk-env"
    monkeypatch.delenv("LOL_COACH_LLM_KEY")
    assert llm.resolve_api_key() == "sk-detected"


def test_normalize_and_provider_catalog() -> None:
    assert llm.normalize_provider("google") == "gemini"
    assert llm.normalize_provider("nope") == "opencode-go"
    groq = llm.get_provider("groq")
    assert groq.base_url.startswith("https://api.groq.com")
    assert "llama-3.1-8b-instant" in groq.models
    assert llm.get_provider("openrouter").supports_oauth is True
    assert llm.get_provider("opencode-go").detect_opencode is True


def test_resolve_api_key_per_provider(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GROQ", "gsk-groq")
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GEMINI", "gem-1")
    assert llm.resolve_api_key(provider="groq") == "gsk-groq"
    assert llm.resolve_api_key(provider="gemini") == "gem-1"
    monkeypatch.setattr(llm, "detect_opencode_key", lambda: "")
    assert llm.resolve_api_key(provider="opencode-go") == ""


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
    assert captured["json"]["model"] == llm.DEFAULT_MODEL


def test_chat_no_key(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(llm, "detect_opencode_key", lambda: "")
    assert llm.chat("프롬프트", api_key="") is None


def test_chat_groq_skips_reasoning_effort(monkeypatch) -> None:
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
    out = llm.chat("프롬프트", api_key="gsk-x", provider="groq")
    assert out == "- 팁"
    assert captured["url"].startswith("https://api.groq.com/")
    assert "reasoning_effort" not in captured["json"]
    assert captured["json"]["model"] == "llama-3.1-8b-instant"


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
    monkeypatch.setattr(llm, "detect_opencode_key", lambda: "")
    assert llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="") is None


def test_probe_gateway_reports_missing_and_rejected_keys(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(llm, "detect_opencode_key", lambda: "")
    ok, msg = llm.probe_gateway("")
    assert ok is False
    assert "API 키" in msg

    class Resp:
        status_code = 401

    monkeypatch.setattr(llm, "resolve_api_key", lambda explicit="", provider="": "sk-test")
    from lol_coach import http_security as hs

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: Resp()))
    ok, msg = llm.probe_gateway("sk-test")
    assert ok is False
    assert "거부" in msg


def test_probe_gateway_ok(monkeypatch) -> None:
    class Resp:
        status_code = 200

    monkeypatch.setattr(llm, "resolve_api_key", lambda explicit="", provider="": "sk-ok")
    from lol_coach import http_security as hs

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: Resp()))
    ok, msg = llm.probe_gateway("sk-ok", "deepseek-v4-flash")
    assert ok is True
    assert "opencode-go" in msg
    assert "deepseek-v4-flash" in msg


def test_probe_gateway_uses_provider_name(monkeypatch) -> None:
    class Resp:
        status_code = 200

    monkeypatch.setattr(llm, "resolve_api_key", lambda explicit="", provider="": "sk-ok")
    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(get=lambda *a, **k: Resp()))
    ok, msg = llm.probe_gateway("sk-ok", provider="gemini")
    assert ok is True
    assert "Gemini" in msg


def test_exchange_openrouter_code(monkeypatch) -> None:
    class Resp:
        status_code = 200

        def json(self) -> dict:
            return {"key": "sk-or-test"}

    captured: dict = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["json"] = kw["json"]
        return Resp()

    monkeypatch.setattr(hs, "secure_session", lambda: SimpleNamespace(post=fake_post))
    ok, key = llm.exchange_openrouter_code("abc", "verifier")
    assert ok is True
    assert key == "sk-or-test"
    assert captured["url"].endswith("/auth/keys")
    assert captured["json"]["code"] == "abc"
    verifier, challenge = llm.openrouter_pkce()
    assert verifier and challenge and verifier != challenge


def test_save_llm_key_roundtrip(tmp_path, monkeypatch) -> None:
    from lol_coach import config

    _clear_llm_env(monkeypatch)
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env)
    config.save_llm_key("  sk-manual  ", env_path=env)
    assert "sk-manual" in env.read_text(encoding="utf-8")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "sk-manual")
    settings = config.load_settings()
    assert settings.llm_api_key == "sk-manual"
    config.save_llm_key("", env_path=env)
    assert "LOL_COACH_LLM_KEY=" not in env.read_text(encoding="utf-8")


def test_save_llm_provider_keeps_separate_keys(tmp_path, monkeypatch) -> None:
    from lol_coach import config

    _clear_llm_env(monkeypatch)
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env)
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "opencode-go")
    config.save_llm_provider("groq", env_path=env)
    config.save_llm_key("gsk-1", env_path=env, provider="groq")
    config.save_llm_key("gem-1", env_path=env, provider="gemini")
    text = env.read_text(encoding="utf-8")
    assert "gsk-1" in text and "gem-1" in text
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "groq")
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GROQ", "gsk-1")
    monkeypatch.setenv("LOL_COACH_LLM_KEY_GEMINI", "gem-1")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "gsk-1")
    assert config.load_settings().llm_provider == "groq"
    assert config.load_settings().llm_api_key == "gsk-1"
    config.save_llm_provider("gemini", env_path=env)
    monkeypatch.setenv("LOL_COACH_LLM_PROVIDER", "gemini")
    assert config.load_settings().llm_api_key == "gem-1"


def test_save_llm_model_roundtrip(tmp_path, monkeypatch) -> None:
    from lol_coach import config

    env = tmp_path / ".env"
    config.save_llm_model("kimi-k3", env_path=env)
    assert "kimi-k3" in env.read_text(encoding="utf-8")
    monkeypatch.setenv("LOL_COACH_LLM_MODEL", "kimi-k3")
    assert config.load_settings().llm_model == "kimi-k3"
    config.save_llm_model("", env_path=env)
    assert "LOL_COACH_LLM_MODEL" not in env.read_text(encoding="utf-8")


def test_coach_lane_model_passthrough(monkeypatch) -> None:
    _clear_llm_env(monkeypatch)
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
    assert calls[0]["reasoning_effort"] == "low"


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
        (
            "1코어 로스트 챕터 → 2코어 마법사의 신발 → 3코어 라바돈 → "
            "4코어 존야 → 5코어 공허의 지팡이 → 6코어 밴시의 장막"
        ),
        "15.4",
        api_key="sk-x",
        model="qwen3.7-plus",
    )
    assert out is not None
    assert "한타 대응" in out
    slots = llm._extract_core_slots(out)
    assert len(slots) == 6
    assert slots[1] == "로스트 챕터"
    assert slots[6] == "밴시의 장막"
    assert calls[0]["model"] == "qwen3.7-plus"
    assert calls[0]["max_tokens"] >= 2500


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
    assert "현재 롤 패치: 15.4" in user
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
