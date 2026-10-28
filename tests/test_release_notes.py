from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.release_notes import DEFAULT_CHANGELOG, MissingSectionError, main, section

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

## [1.0.0] - 2026-10-28

### Added

- The first stable API.

## [0.2.0] - 2026-10-08

- Earlier work.

## [0.1.0] - 2026-10-01
"""


def test_extracts_the_section_without_its_heading() -> None:
    assert section(CHANGELOG, "1.0.0") == "### Added\n\n- The first stable API.\n"


def test_last_section_runs_to_the_end_of_the_file() -> None:
    with pytest.raises(MissingSectionError, match=re.escape("0.1.0 is empty")):
        section(CHANGELOG, "0.1.0")
    assert section(CHANGELOG + "\n- Initial import.\n", "0.1.0") == "- Initial import.\n"


def test_version_must_match_exactly() -> None:
    # A prefix is not a match, and the dots are literal rather than regex wildcards.
    with pytest.raises(MissingSectionError, match=re.escape("no section for 0.2")):
        section(CHANGELOG, "0.2")
    with pytest.raises(MissingSectionError):
        section(CHANGELOG.replace("[0.2.0]", "[0x2.0]"), "0.2.0")


def test_cli_accepts_a_tag_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG)

    assert main(["v1.0.0", "--changelog", str(changelog)]) == 0
    assert capsys.readouterr().out == "### Added\n\n- The first stable API.\n"

    assert main(["9.9.9", "--changelog", str(changelog)]) == 1
    assert "no section for 9.9.9" in capsys.readouterr().err


def test_repository_changelog_has_notes_for_every_release() -> None:
    text = DEFAULT_CHANGELOG.read_text()
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.MULTILINE)
    assert versions
    for version in versions:
        assert section(text, version).strip()
