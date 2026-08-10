from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_coach import http_security
from lol_coach.riot.client import RiotClient
from lol_coach.static import augment_icons, ddragon_cache, icons
from lol_coach.static.ddragon import DataDragon


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        json_body: dict | list | None = None,
        url: str = "https://cdn.example/image.png",
    ) -> None:
        self._body = body
        self._json_body = json_body
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.encoding = "utf-8"

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args) -> None:
        return None

    @property
    def content(self) -> bytes:
        return self._body

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [
            self._body[offset : offset + chunk_size]
            for offset in range(0, len(self._body), chunk_size)
        ]

    def json(self) -> dict | list:
        assert self._json_body is not None
        return self._json_body

    def raise_for_status(self) -> None:
        return None


def _valid_png_bytes() -> bytes:
    assert augment_icons.Image is not None
    output = io.BytesIO()
    augment_icons.Image.new("RGBA", (128, 128), (10, 20, 30, 255)).save(
        output, format="PNG"
    )
    return output.getvalue()


def test_riot_json_rejects_declared_response_over_limit() -> None:
    # Given
    response = FakeResponse(
        b'{}',
        headers={"Content-Length": str(33 * 1024 * 1024)},
        json_body={"ok": True},
    )
    client = RiotClient("RGAPI-test-only", max_retries=1)
    client.session = SimpleNamespace(get=lambda *_args, **_kwargs: response)

    # When
    with pytest.raises(ValueError) as caught:
        client._get("https://na1.api.riotgames.com/test")

    # Then
    assert str(caught.value)


def test_ddragon_json_rejects_declared_response_over_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setattr(ddragon_cache, "_root", lambda: tmp_path)
    response = FakeResponse(
        b'{}',
        headers={"Content-Length": str(17 * 1024 * 1024)},
        json_body={"data": {}},
    )
    session = SimpleNamespace(get=lambda *_args, **_kwargs: response)

    # When
    with pytest.raises(ValueError) as caught:
        ddragon_cache.get_json(
            session, "https://ddragon.leagueoflegends.com/data.json", "oversize", timeout=3
        )

    # Then
    assert str(caught.value)


def test_champion_detail_rejects_declared_response_over_limit() -> None:
    # Given
    response = FakeResponse(
        b'{}',
        headers={"Content-Length": str(17 * 1024 * 1024)},
        json_body={"data": {"Ahri": {}}},
    )
    data_dragon = DataDragon()
    data_dragon._version = "15.1.1"
    data_dragon._loaded = True
    data_dragon._champions_by_key = {"ahri": {"id": "Ahri"}}
    data_dragon.session = SimpleNamespace(get=lambda *_args, **_kwargs: response)

    # When
    with pytest.raises(ValueError) as caught:
        data_dragon.champion_detail("ahri")

    # Then
    assert str(caught.value)


def test_champion_detail_rejects_non_object_json() -> None:
    # Given
    response = FakeResponse(b"[]", json_body=[])
    data_dragon = DataDragon()
    data_dragon._version = "15.1.1"
    data_dragon._loaded = True
    data_dragon._champions_by_key = {"ahri": {"id": "Ahri"}}
    data_dragon.session = SimpleNamespace(get=lambda *_args, **_kwargs: response)

    # When
    with pytest.raises(ValueError) as caught:
        data_dragon.champion_detail("ahri")

    # Then
    assert str(caught.value)


def test_icon_download_rejects_cross_origin_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    body = _valid_png_bytes()
    private_url = "https://127.0.0.1:8443/private.png"

    class RedirectingSession:
        def get(self, url: str, **kwargs) -> FakeResponse:
            if kwargs.get("allow_redirects", True):
                return FakeResponse(body, url=private_url)
            return FakeResponse(
                b"",
                status_code=302,
                headers={"Location": private_url},
                url=url,
            )

    monkeypatch.setattr(icons, "_session", RedirectingSession())
    destination = tmp_path / "icon.png"

    # When
    downloaded = icons._download("https://cdn.example/icon.png", destination)

    # Then
    assert downloaded is False
    assert not destination.exists()


def test_icon_download_rejects_declared_response_over_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    body = _valid_png_bytes()
    response = FakeResponse(
        body,
        headers={"Content-Length": str(9 * 1024 * 1024)},
    )
    monkeypatch.setattr(
        icons,
        "_session",
        SimpleNamespace(get=lambda *_args, **_kwargs: response),
    )

    # When
    downloaded = icons._download("https://cdn.example/icon.png", tmp_path / "icon.png")

    # Then
    assert downloaded is False


def test_cached_icon_rejects_excessive_pixel_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    assert icons.Image is not None
    path = tmp_path / "large.png"
    icons.Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(path)
    monkeypatch.setattr(http_security, "MAX_IMAGE_PIXELS", 100)

    # When
    image = icons._open_local(path, 8)

    # Then
    assert image is None


def test_augment_download_rejects_cross_origin_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    body = _valid_png_bytes()
    private_url = "https://127.0.0.1:8443/private.png"

    class RedirectingSession:
        def get(self, url: str, **kwargs) -> FakeResponse:
            if kwargs.get("allow_redirects", True):
                return FakeResponse(body, url=private_url)
            return FakeResponse(
                b"",
                status_code=302,
                headers={"Location": private_url},
                url=url,
            )

    monkeypatch.setattr(augment_icons, "_session", RedirectingSession())

    # When
    downloaded = augment_icons._download_one(
        "https://cdn.example/augment.png", tmp_path / "augment.png"
    )

    # Then
    assert downloaded is False


def test_icon_download_accepts_same_origin_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    body = _valid_png_bytes()

    class SameOriginSession:
        def get(self, url: str, **_kwargs) -> FakeResponse:
            if url.endswith("original.png"):
                return FakeResponse(
                    b"",
                    status_code=302,
                    headers={"Location": "/final.png"},
                    url=url,
                )
            return FakeResponse(body, url=url)

    monkeypatch.setattr(icons, "_session", SameOriginSession())
    destination = tmp_path / "icon.png"

    # When
    downloaded = icons._download("https://cdn.example/original.png", destination)

    # Then
    assert downloaded is True
    assert destination.read_bytes() == body
