"""Small dependency-free project maintenance commands."""

from __future__ import annotations

import argparse
from pathlib import Path

GENERATED_DIRECTORIES = (
    "data/raw",
    "data/interim",
    "data/processed",
    "data/archive",
    "reports/figures",
)


def init_dirs(root: Path | None = None) -> list[Path]:
    """Create generated-data directories and return their resolved paths."""
    project_root = (root or Path.cwd()).resolve()
    created: list[Path] = []
    for relative in GENERATED_DIRECTORIES:
        path = project_root / relative
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init-dirs"])
    args = parser.parse_args(argv)
    if args.command == "init-dirs":
        for path in init_dirs():
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
