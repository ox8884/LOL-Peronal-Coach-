"""llm 모듈 — 키 감지/우선순위/코칭 프롬프트. 네트워크 없이 단위 검증."""

from __future__ import annotations

import json

from lol_coach import llm


def _fake_auth(tmp_path, key: str = "sk-opencode-test") -> object:
    p = tmp_path / "auth.json"
    p.write_text(
        json.dumps({"opencode-go": {"type": "api", "key": key}}), encoding="utf-8"
    )
    return p


def test_detect_opencode_key_found(tmp_path) -> None:
    p = _fake_auth(tmp_path)
    assert llm.detect_opencode_key(p) == "sk-opencode-test"


def test_detect_opencode_key_missing(tmp_path) -> None:
    assert llm.detect_opencode_key(tmp_path / "nope.json") == ""
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert llm.detect_opencode_key(bad) == ""


def test_resolve_api_key_priority(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LOL_COACH_LLM_KEY", raising=False)
    fake = _fake_auth(tmp_path, key="sk-detected")
    monkeypatch.setattr(llm, "_OPENCODE_AUTH", fake)
    assert llm.resolve_api_key("sk-manual") == "sk-manual"
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "sk-env")
    assert llm.resolve_api_key() == "sk-env"
    monkeypatch.delenv("LOL_COACH_LLM_KEY")
    assert llm.resolve_api_key() == "sk-detected"


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

    monkeypatch.setattr("requests.post", fake_post)
    out = llm.chat("프롬프트", api_key="sk-x")
    assert out == "- 팁 한 줄\n- 팁 두 줄"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-x"
    assert captured["json"]["model"] == llm.DEFAULT_MODEL


def test_chat_no_key(monkeypatch) -> None:
    monkeypatch.delenv("LOL_COACH_LLM_KEY", raising=False)
    assert llm.chat("프롬프트", api_key="") is None


def test_chat_failure_returns_none(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise TimeoutError("network down")

    monkeypatch.setattr("requests.post", boom)
    assert llm.chat("프롬프트", api_key="sk-x") is None


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

    monkeypatch.setattr("requests.post", fake_post)
    counters = [
        ("아리", type("C", (), {"champion": "Ahri", "gd15": 340, "gd15_str": "+340", "matches": 15234, "win_rate": None})())
    ]
    out = llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="sk-x")
    assert out == "- 초반 강한 교환"
    user = calls[0]["messages"][1]["content"]
    assert "아칼리" in user and "Ahri" in user and "+340" in user

    monkeypatch.delenv("LOL_COACH_LLM_KEY", raising=False)
    assert llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="") is None


def test_save_llm_key_roundtrip(tmp_path, monkeypatch) -> None:
    from lol_coach import config

    env = tmp_path / ".env"
    config.save_llm_key("  sk-manual  ", env_path=env)
    assert "sk-manual" in env.read_text(encoding="utf-8")
    monkeypatch.setenv("LOL_COACH_LLM_KEY", "sk-manual")
    settings = config.load_settings()
    assert settings.llm_api_key == "sk-manual"
    config.save_llm_key("", env_path=env)
    assert "LOL_COACH_LLM_KEY" not in env.read_text(encoding="utf-8")


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

    monkeypatch.setattr("requests.post", fake_post)
    counters = [
        ("아리", type("C", (), {"champion": "Ahri", "gd15": 340, "gd15_str": "+340", "matches": 15234})())
    ]
    llm.coach_lane("아칼리", "미드", counters, "15.4", api_key="sk-x", model="kimi-k3")
    assert calls[0]["model"] == "kimi-k3"
    assert calls[0]["reasoning_effort"] == "low"


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
    # 5개 넘치면 5개까지만
    path = llm._format_core_path([f"i{n}" for n in range(1, 8)])
    assert path.count("코어") == 5


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

    monkeypatch.setattr("requests.post", fake_post)
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

    monkeypatch.setattr("requests.post", fake_post)
    out = llm.coach_aram(
        "베이가",
        ["세라핀", "문도"],
        ["리 신", "케이틀린"],
        "유령의 칼날(S)",
        "1코어 로스트 챕터 → 2코어 라바돈 → 3코어 존야",
        "15.4",
        api_key="sk-x",
        model="qwen3.7-plus",
    )
    assert out == "- 한타 대응"
    user = calls[0]["messages"][1]["content"]
    assert "우리 조합: 세라핀, 문도" in user
    assert "상대 조합: 리 신, 케이틀린" in user
    assert "유령의 칼날(S)" in user and "로스트 챕터" in user
    assert "현재 롤 패치: 15.4" in user
    assert "5코어" in user
    assert "1~2코어만" in user
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

    monkeypatch.setattr("requests.post", fake_post)
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
