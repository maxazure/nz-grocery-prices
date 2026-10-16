"""Package metadata checks (offline)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from nzgrocery import __version__, cli

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_metadata_matches_package():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["version"] == __version__
    assert meta["license"] == "MIT"
    scripts = meta["scripts"]
    # uvx/pipx run use the distribution name as the command name.
    assert scripts[meta["name"]] == scripts["nzgrocery"] == "nzgrocery.cli:main"
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    shipped = package_data["tool"]["setuptools"]["package-data"]["nzgrocery"]
    assert "stores/*.json" in shipped
    assert (ROOT / "src" / "nzgrocery" / "stores" / "nz.json").is_file()
    assert not (ROOT / "src" / "nzgrocery" / "stores" / "auckland.json").exists()
