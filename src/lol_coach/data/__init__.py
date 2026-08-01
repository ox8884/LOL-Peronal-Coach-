"""Packaged data resources for lol_coach."""

from __future__ import annotations

import importlib.resources as _resources
from pathlib import Path
from typing import BinaryIO


def resource_path(name: str) -> Path:
    """Return an importlib.resources path for a packaged data file."""
    return _resources.files(__package__) / name


def open_resource(name: str) -> BinaryIO:
    """Open a packaged data resource for binary reading."""
    return _resources.files(__package__).joinpath(name).open("rb")
