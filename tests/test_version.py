"""The version is declared in pyproject.toml and in the package; a release bumps both."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from nyc_taxi_lake import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_package_and_project_versions_match() -> None:
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

    assert __version__ == declared


def test_released_version_has_a_changelog_entry() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text()
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)

    assert __version__ in headings
