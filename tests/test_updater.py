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
