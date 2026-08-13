from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_coach import config as config_mod
from lol_coach import llm
from lol_coach.gui import update_mixin, updater
from lol_coach.gui.update_mixin import UpdateMixin
from lol_coach.lcu import LCUClient
from lol_coach.riot.client import RiotClient


class FakeDownloadResponse:
    def __init__(self, body: bytes, content_length: int) -> None:
        self._body = body
        self._offset = 0
        self.headers = {"Content-Length": str(content_length)}

    def __enter__(self) -> FakeDownloadResponse:
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_cwd_dotenv_is_ignored_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    trusted_env = tmp_path / "trusted" / ".env"
    trusted_env.parent.mkdir()
    trusted_env.write_text("RIOT_PLATFORM=kr\n", encoding="utf-8")
    hostile_cwd = tmp_path / "hostile"
    hostile_cwd.mkdir()
    (hostile_cwd / ".env").write_text(
        "HTTPS_PROXY=http://127.0.0.1:9090\n", encoding="utf-8"
    )
    monkeypatch.setattr(config_mod, "ENV_PATH", trusted_env)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.chdir(hostile_cwd)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)

    # When
    config_mod._ensure_env_loaded()

    # Then
    assert "HTTPS_PROXY" not in os.environ


def test_frozen_app_root_uses_local_app_data_even_when_exe_dir_is_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    portable_dir = tmp_path / "shared-portable"
    portable_dir.mkdir()
    executable = portable_dir / "롤실전코치.exe"
    executable.write_bytes(b"exe")
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    # When
    root = config_mod._app_root()

    # Then
    assert root == local_app_data / "롤실전코치"


def test_credential_sessions_ignore_environment_proxies(tmp_path: Path) -> None:
    # Given
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:123:54321:secret:https", encoding="utf-8")

    # When
    riot = RiotClient("RGAPI-test-only")
    lcu = LCUClient(lockfile, verify=False)

    # Then
    assert riot.session.trust_env is False
    assert lcu.session.trust_env is False


def test_llm_request_ignores_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    captured: dict[str, dict[str, str] | str] = {}

    class LlmResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int) -> list[bytes]:
            del chunk_size
            return [b'{"choices":[{"message":{"content":"safe"}}]}']

        def close(self) -> None:
            return None

    def fake_post(_url: str, **kwargs) -> LlmResponse:
        captured["proxies"] = kwargs["proxies"]
        captured["verify"] = kwargs["verify"]
        return LlmResponse()

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9090")
    import lol_coach.http_security as hs

    fake_session = SimpleNamespace(trust_env=False, post=fake_post)
    monkeypatch.setattr(hs, "secure_session", lambda: fake_session)

    # When
    result = llm.chat("prompt", api_key="secret", max_attempts=1)

    # Then
    assert result == "safe"
    # 세션 차원의 프록시 격리 (trust_env=False) + 요청 차원의 이중 방어
    assert fake_session.trust_env is False
    assert captured["proxies"] == {"http": "", "https": "", "all": ""}
    assert isinstance(captured["verify"], str)


def test_update_stops_before_download_when_checksum_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    downloaded: list[Path] = []
    launched: list[str] = []
    failures: list[str] = []

    def fake_download(_version: str, dest: Path, **_kwargs) -> Path:
        downloaded.append(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"installer")
        return dest

    app = SimpleNamespace(
        _latest_version="1.6.41",
        _latest_sha256="",
        after=lambda _delay, callback: callback(),
        status=SimpleNamespace(configure=lambda **_kwargs: None),
        update_btn=SimpleNamespace(configure=lambda **_kwargs: None),
        _launch_installer=lambda path, _version: launched.append(path),
        _update_failed=failures.append,
    )
    monkeypatch.setattr(config_mod, "cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(updater, "fetch_expected_sha256", lambda _version: "")
    monkeypatch.setattr(updater, "download_installer", fake_download)
    monkeypatch.setattr(update_mixin.messagebox, "askyesno", lambda *_args: True)

    # When
    UpdateMixin._download_update(app)

    # Then
    assert downloaded == []
    assert launched == []
    assert len(failures) == 1


def test_update_check_clears_stale_action_when_checksum_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    button_calls: list[dict[str, str]] = []
    status_calls: list[str] = []
    app = SimpleNamespace(
        _latest_version="9.8.0",
        _latest_sha256="stale-hash",
        after=lambda _delay, callback: callback(),
        status=SimpleNamespace(
            configure=lambda **kwargs: status_calls.append(kwargs["text"]),
            cget=lambda _key: "업데이트 확인 중…",
        ),
        update_btn=SimpleNamespace(
            configure=lambda **kwargs: button_calls.append(kwargs)
        ),
    )
    app._version_tuple = UpdateMixin._version_tuple.__get__(app)
    monkeypatch.setattr(update_mixin, "__version__", "1.6.41")
    monkeypatch.setattr(updater, "fetch_latest_tag", lambda: "9.9.0")
    monkeypatch.setattr(updater, "fetch_expected_sha256", lambda _version: "")

    # When
    UpdateMixin._check_update(app)

    # Then
    assert app._latest_version == ""
    assert app._latest_sha256 == ""
    assert button_calls[-1]["state"] == "disabled"
    assert button_calls[-1]["text"] == "업데이트 사용 불가"
    assert status_calls and "자동 업데이트를 중단했습니다" in status_calls[-1]


def test_installer_download_rejects_declared_size_over_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    destination = tmp_path / "installer.exe"
    body = b"x" * 128
    monkeypatch.setattr(updater, "_MAX_INSTALLER_BYTES", 64, raising=False)
    monkeypatch.setattr(
        updater,
        "urlopen",
        lambda *_args, **_kwargs: FakeDownloadResponse(body, len(body)),
    )

    def legacy_download(_url: str, dest: Path, **_kwargs) -> None:
        dest.write_bytes(body)

    monkeypatch.setattr(urllib.request, "urlretrieve", legacy_download)

    # When
    with pytest.raises(OSError) as caught:
        updater.download_installer("1.6.41", destination, min_bytes=1)

    # Then
    assert caught.value.filename is None
