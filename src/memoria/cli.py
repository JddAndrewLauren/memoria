"""Memoria CLI entry point."""

import argparse
import os
import sys
from pathlib import Path

from memoria.index import INDEX_RELATIVE_PATH, rebuild
from memoria.validate import validate

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


class NoEvidenceRoot(Exception):
    """Raised when a command that reads evidence has no corpus configured."""


def evidence_root() -> Path:
    """The configured evidence corpus root.

    There is no default. It used to be ``../thoreau-evidence``, which was
    correct only when run from beside that sibling checkout; the corpus was
    retired 2026-09-01 (docs/open-problems.md §2.4) and a default pointing at
    a path that is not there fails later and less clearly than refusing here.

    Called only by the commands that actually read evidence, so anything
    working from this repo's own normalized records never needs the variable
    set.
    """
    configured = os.environ.get(EVIDENCE_ROOT_ENV_VAR)
    if not configured:
        raise NoEvidenceRoot(
            f"{EVIDENCE_ROOT_ENV_VAR} is not set, and there is no default: "
            "no evidence corpus is currently chosen "
            "(see docs/open-problems.md 2.4). Set it to the absolute path of "
            "an evidence repository to run this command."
        )
    return Path(configured)


def repo_root() -> Path:
    """Locate the Memoria repo root by walking up from the current
    directory looking for pyproject.toml, so `memoria validate` and
    `memoria rebuild` find sources/normalized/ regardless of which
    subdirectory they are run from. Falls back to the current directory
    (rather than raising) if no pyproject.toml is found above it.
    """
    candidate = Path.cwd()
    for directory in (candidate, *candidate.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="memoria")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "validate", help="Verify the raw evidence corpus against its manifest"
    )
    subparsers.add_parser(
        "rebuild",
        help="Delete and regenerate the search index from the normalized records",
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            root = evidence_root()
        except NoEvidenceRoot as exc:
            print(f"validate: {exc}", file=sys.stderr)
            return 1
        errors = validate(root, repo_root())
        for error in errors:
            print(error)
        if errors:
            return 1
        print("validate: OK")
        return 0

    if args.command == "rebuild":
        root = repo_root()
        records = rebuild(root)
        print(
            f"rebuild: indexed {len(records)} records to "
            f"{root / INDEX_RELATIVE_PATH}"
        )
        if not records:
            print(
                "rebuild: no normalized records found, and no normalizer is "
                "wired in - no evidence corpus is currently chosen "
                "(see docs/open-problems.md 2.4)"
            )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
