"""Memoria CLI entry point."""

import argparse
import os
import sys
from pathlib import Path

from memoria.normalize import (
    normalize_journals,
    normalize_letters,
    recipients_table,
    write_normalized_records,
    write_recipients_table,
)
from memoria.validate import NORMALIZED_RELATIVE_PATH, validate

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"
DEFAULT_EVIDENCE_ROOT = "../thoreau-evidence"


def evidence_root() -> Path:
    return Path(os.environ.get(EVIDENCE_ROOT_ENV_VAR, DEFAULT_EVIDENCE_ROOT))


def repo_root() -> Path:
    """Locate the Memoria repo root by walking up from the current
    directory looking for pyproject.toml, so `memoria validate` and
    `memoria normalize` find sources/normalized/ regardless of which
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
        "normalize",
        help=(
            "Normalize the journal and letters volumes into per-entry "
            "sources/normalized/ records"
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        errors = validate(evidence_root(), repo_root())
        for error in errors:
            print(error)
        if errors:
            return 1
        print("validate: OK")
        return 0

    if args.command == "normalize":
        journal_records = normalize_journals(evidence_root())
        letter_records = normalize_letters(
            evidence_root(), start_id=len(journal_records) + 1
        )
        records = journal_records + letter_records
        output_root = repo_root() / NORMALIZED_RELATIVE_PATH
        written = write_normalized_records(records, output_root)
        print(f"normalize: wrote {len(written)} records to {output_root}")
        table = recipients_table(letter_records)
        recipients_path = write_recipients_table(
            table, output_root / "recipients.yaml"
        )
        print(
            f"normalize: wrote {len(table)} recipients to {recipients_path}"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
