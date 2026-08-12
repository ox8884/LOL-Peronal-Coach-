from pathlib import Path
from threading import Thread

from lol_coach.static import augment_icons, icons
from lol_coach.static.augment_catalog import AugmentCatalog


def test_cache_miss_never_downloads_icons_on_main_thread(
    monkeypatch,
    tmp_path: Path,
) -> None:
    download_attempts: list[str] = []

    def record_download(url: str, _dest: Path, *args, **kwargs) -> bool:
        download_attempts.append(url)
        return False

    monkeypatch.setattr(icons, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(icons, "_download", record_download)
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()
    icons._mem.clear()

    assert icons.champion_pil("Ahri", 32) is not None
    assert icons.item_pil(3089, 32) is not None
    assert icons.augment_pil("Jeweled Gauntlet", "gold", 32) is None

    assert download_attempts == []

    worker = Thread(target=lambda: icons.champion_pil("Ahri", 32))
    worker.start()
    worker.join()

    assert len(download_attempts) == 1


def test_worker_download_populates_champion_icon_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def download_png(_url: str, dest: Path, *args, **kwargs) -> bool:
        assert icons.Image is not None
        icons.Image.new("RGB", (8, 8), (12, 34, 56)).save(dest, format="PNG")
        return True

    monkeypatch.setattr(icons, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(icons, "_download", download_png)
    monkeypatch.setattr(icons, "ddragon_version", lambda: "15.1.1")
    icons._mem.clear()

    worker = Thread(target=lambda: icons.champion_pil("Ahri", 32))
    worker.start()
    worker.join()

    cached = tmp_path / "c_Ahri_32.png"
    assert cached.exists()
    image = icons.champion_pil("Ahri", 32)
    assert image is not None
    assert image.size == (32, 32)


def test_augment_missing_candidates_returns_none_on_main_thread(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Records with no image candidates yield explicit missing state (no fake icon)."""
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    # Use a name that is not present in the catalog at all.
    result = augment_icons.augment_pil("No Such Augment", size=40)
    assert result is None


def test_augment_refresh_honors_exact_catalog_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Only URLs returned by AugmentCatalog.candidate_urls_for are attempted."""
    attempted: list[str] = []

    def fake_download(url: str, dest: Path, timeout: float = 12.0) -> bool:
        attempted.append(url)
        return False

    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(augment_icons, "_download_one", fake_download)
    augment_icons.reset_augment_cache()

    # Jeweled Gauntlet now has a verified Blitz CDN candidate.
    augment_icons.refresh_augment_sync("Jeweled Gauntlet")
    assert attempted == [
        "https://blitz-cdn.blitz.gg/blitz/lol/arena/augments/jeweledgauntlet_large.webp"
    ]


def test_augment_cache_serves_valid_cached_image(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A valid raw asset already on disk is resized and served at display size."""
    assert augment_icons.Image is not None
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    raw = tmp_path / "a_jeweledgauntlet_raw.png"
    augment_icons.Image.new("RGBA", (128, 128), (10, 20, 30, 255)).save(raw)

    img = augment_icons.augment_pil("Jeweled Gauntlet", size=40)
    assert img is not None
    assert img.size == (40, 40)


def test_augment_last_known_good_fallback_on_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """If the best candidate fails, a previously-good raw asset is kept."""
    assert augment_icons.Image is not None
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    raw = tmp_path / "a_jeweledgauntlet_raw.png"
    good = augment_icons.Image.new("RGBA", (128, 128), (255, 0, 0, 255))
    good.save(raw)
    augment_icons._set_last_known_good("jeweledgauntlet", "https://example.com/good.png")

    # Force a refresh attempt that will fail.
    def fake_download(url: str, dest: Path, timeout: float = 12.0) -> bool:
        return False

    monkeypatch.setattr(augment_icons, "_download_one", fake_download)
    ok = augment_icons.refresh_augment_sync("Jeweled Gauntlet")
    assert ok is True
    # Existing valid raw asset is preserved; refresh reports success.
    assert raw.exists()

    img = augment_icons.augment_pil("Jeweled Gauntlet", size=40)
    assert img is not None
    assert img.size == (40, 40)


def test_augment_invalid_small_image_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Images smaller than 128px are rejected and do not populate the cache."""
    assert augment_icons.Image is not None
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    def fake_download(url: str, dest: Path, timeout: float = 12.0) -> bool:
        augment_icons.Image.new("RGBA", (64, 64), (0, 0, 0, 255)).save(dest)
        return True

    monkeypatch.setattr(augment_icons, "_download_one", fake_download)

    # The packaged catalog already has a candidate for Jeweled Gauntlet.
    ok = augment_icons.refresh_augment_sync("Jeweled Gauntlet")
    assert ok is False
    assert not (tmp_path / "a_jeweledgauntlet_raw.png").exists()


def test_deprecated_icons_augment_pil_is_none_without_verified_asset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The deprecated icons.augment_pil wrapper must not fabricate placeholders."""
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    assert icons.augment_pil("No Such Augment", "gold", 40) is None


def test_deprecated_icons_augment_ctk_is_none_without_verified_asset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The deprecated icons.augment_ctk wrapper must not fabricate placeholders."""
    monkeypatch.setattr(augment_icons, "_cache_dir", lambda: tmp_path)
    augment_icons.reset_augment_cache()

    assert icons.augment_ctk("No Such Augment", "gold", 40) is None


def test_augment_catalog_has_validated_candidate_for_every_record() -> None:
    """Every catalog record must have a validated image candidate.

    Unique art requires >=128px; augments whose in-game icon is the generic
    per-rarity placeholder allow its native 64px resolution.
    """
    catalog = AugmentCatalog()
    missing = [rec.id for rec in catalog.records if not rec.image_candidates]
    small = [
        rec.id
        for rec in catalog.records
        for c in rec.image_candidates
        if c.size < (64 if "genericabilityaugmenticon" in c.url else 128)
    ]
    assert not missing, f"records missing image candidates: {missing}"
    assert not small, f"records with candidates below the size bar: {small}"


def test_map_pil_returns_placeholder_when_offline() -> None:
    """메인 스레드(다운로드 불가)에서도 단색 폴백 이미지를 돌려준다."""
    from lol_coach.static import icons

    img = icons.map_pil(11, size=256)
    assert img is not None
    assert img.size == (256, 256)
