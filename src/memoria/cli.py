"""Memoria CLI entry point."""

import argparse
import sys

from memoria.index import INDEX_RELATIVE_PATH, rebuild
from memoria.normalize import normalize as run_normalize
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import NoEvidenceRoot, from_env, require_evidence_root
from memoria.validate import validate

# Where the repository is, and where evidence is, are `memoria.repository`'s
# to answer (ADR-0004). The CLI held both until the core grew a read side; it
# is one adapter of three, and the MCP server would otherwise have had to
# import from it.


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
    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Append new raw units to the manifest ledger and convert what changed",
    )
    normalize_parser.add_argument(
        "--all",
        action="store_true",
        help="Reconvert every unit, not only those whose hash or converter changed",
    )

    args = parser.parse_args(argv)

    repository = from_env()

    if args.command == "validate":
        try:
            evidence_root = require_evidence_root(repository)
        except NoEvidenceRoot as exc:
            print(f"validate: {exc}", file=sys.stderr)
            return 1
        errors = validate(evidence_root, repository.root)
        for error in errors:
            print(error)
        if errors:
            return 1
        print("validate: OK")
        return 0

    if args.command == "normalize":
        try:
            evidence_root = require_evidence_root(repository)
        except NoEvidenceRoot as exc:
            print(f"normalize: {exc}", file=sys.stderr)
            return 1
        report = run_normalize(repository, evidence_root, all=args.all)
        if report.added_units:
            print(f"normalize: added {len(report.added_units)} new unit(s) to the ledger")
        print(
            f"normalize: converted {len(report.converted)}, skipped "
            f"{len(report.skipped)} (unchanged) to "
            f"{repository.root / NORMALIZED_RELATIVE_PATH}"
        )
        if report.unconvertible:
            print(
                f"normalize: {len(report.unconvertible)} unit(s) have no "
                "converter registered for their format yet"
            )
        return 0

    if args.command == "rebuild":
        records = rebuild(repository)
        print(
            f"rebuild: indexed {len(records)} records to "
            f"{repository.root / INDEX_RELATIVE_PATH}"
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
