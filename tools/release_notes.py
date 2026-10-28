"""Print one version's CHANGELOG section, for use as GitHub release notes.

Usage: ``python -m tools.release_notes 1.0.0 [--changelog PATH]``

The section is everything between ``## [<version>]`` and the next ``## `` heading,
with surrounding blank lines removed. The command exits 1 if the version has no
section or the section is empty, so a release job cannot publish empty notes.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


class MissingSectionError(LookupError):
    pass


def section(changelog: str, version: str) -> str:
    """The body of the ``## [version]`` section of ``changelog``."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](?: - \d{{4}}-\d{{2}}-\d{{2}})?\s*$")
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise MissingSectionError(f"CHANGELOG has no section for {version}")

    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    text = "\n".join(body).strip()
    if not text:
        raise MissingSectionError(f"CHANGELOG section for {version} is empty")
    return text + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.release_notes")
    parser.add_argument("version", help="MAJOR.MINOR.PATCH, with or without a leading v")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    args = parser.parse_args(argv)
    try:
        notes = section(args.changelog.read_text(), args.version.removeprefix("v"))
    except MissingSectionError as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
