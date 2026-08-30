"""자동 업데이트 유틸 — 해시·파싱 (네트워크 없이)."""

from __future__ import annotations

from pathlib import Path

from lol_coach.gui.updater import (
    file_sha256,
    parse_sha256_text,
    verify_installer,
    version_tuple,
)


def test_version_tuple() -> None:
    assert version_tuple("1.6.6") == (1, 6, 6)
    assert version_tuple("v1.6.6") == (1, 6, 6)
    assert version_tuple("1.6.6") > version_tuple("1.6.5")


def test_parse_sha256_text() -> None:
    h = "a" * 64
    assert parse_sha256_text(f"{h}  LOL-Coach-Setup-v1.0.0.exe\n") == h
    assert parse_sha256_text(h) == h
    assert parse_sha256_text("# comment\n") == ""


def test_file_sha256_and_verify(tmp_path: Path) -> None:
    p = tmp_path / "x.exe"
    p.write_bytes(b"hello-installer")
    digest = file_sha256(p)
    assert len(digest) == 64
    verify_installer(p, digest)
    try:
        verify_installer(p, "0" * 64)
        assert False, "should raise"
    except ValueError as exc:
        assert "불일치" in str(exc)


def test_version_tuple_numeric_compare_regression() -> None:
    """1.6.100 vs 1.6.99 — 문자열 비교면 '1.6.100' < '1.6.99' 로 깨진다 (회귀 방지)."""
    assert version_tuple("1.6.100") > version_tuple("1.6.99")
    assert version_tuple("1.6.100") > version_tuple("1.6.9")


class _FakeResp:
    def __init__(self, status: int, location: str = "") -> None:
        self.status_code = status
        self.headers = {"Location": location}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResp]) -> None:
        self.responses = list(responses)

    def get(self, url, timeout=None, stream=False, allow_redirects=False):
        return self.responses.pop(0)


def test_fetch_latest_tag_via_redirect_parses_location() -> None:
    from lol_coach.gui.updater import fetch_latest_tag_via_redirect

    session = _FakeSession(
        [
            _FakeResp(
                302,
                "https://github.com/ox8884/LOL-Peronal-Coach-/releases/tag/v1.6.102",
            )
        ]
    )
    assert fetch_latest_tag_via_redirect(session=session) == "1.6.102"


def test_fetch_latest_tag_via_redirect_non_redirect_is_empty() -> None:
    from lol_coach.gui.updater import fetch_latest_tag_via_redirect

    session = _FakeSession([_FakeResp(200)])
    assert fetch_latest_tag_via_redirect(session=session) == ""


def test_fetch_latest_tag_falls_back_to_redirect(monkeypatch) -> None:
    """API 실패(레이트리밋 등) 시 리디렉션 우회로 최신 태그를 얻는다."""
    import time as _time

    from lol_coach.gui import updater as upd

    monkeypatch.setattr(upd, "_fetch_latest_tag_api", lambda timeout=8.0: "")
    monkeypatch.setattr(upd, "fetch_latest_tag_via_redirect", lambda timeout=8.0, session=None: "1.6.102")
    monkeypatch.setattr(_time, "sleep", lambda s: None)
    monkeypatch.setattr(upd.time, "sleep", lambda s: None)
    assert upd.fetch_latest_tag() == "1.6.102"


def test_fetch_latest_tag_api_first(monkeypatch) -> None:
    from lol_coach.gui import updater as upd

    monkeypatch.setattr(upd, "_fetch_latest_tag_api", lambda timeout=8.0: "1.6.103")
    called = []
    monkeypatch.setattr(
        upd, "fetch_latest_tag_via_redirect", lambda timeout=8.0, session=None: called.append(1)
    )
    assert upd.fetch_latest_tag() == "1.6.103"
    assert not called  # API 성공 시 우회 호출 안 함
