from importlib import resources
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from lol_coach import __version__
from lol_coach.gui.api_help import HELP_BODY

ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_matches_runtime_version() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == __version__


def test_package_metadata_includes_icon_runtime_dependency() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]

    assert any(dependency.lower().startswith("pillow") for dependency in dependencies)


def test_catalog_is_importable_as_a_resource_package() -> None:
    spec = (ROOT / "lol_coach.spec").read_text(encoding="utf-8")
    assert '"lol_coach.data"' in spec

    catalog = resources.files("lol_coach.data").joinpath("aram_mayhem_augments.json")

    assert catalog.is_file()


def test_api_key_help_describes_the_actual_network_boundary() -> None:
    assert "외부로 전송하지 않습니다" not in HELP_BODY
    assert "Riot" in HELP_BODY
