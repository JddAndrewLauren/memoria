"""Memoria CLI entry point."""

import argparse
import sys

from memoria import changes
from memoria.index import INDEX_RELATIVE_PATH, IndexSchemaError, rebuild
from memoria.normalize import normalize as run_normalize
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import NoEvidenceRoot, from_env, require_evidence_root
from memoria.validate import validate
from memoria.write import Checkpointed, checkpoint

# Where the repository is, and where evidence is, are `memoria.repository`'s
# to answer (ADR-0004). The CLI held both until the core grew a read side; it
# is one adapter of three, and the MCP server would otherwise have had to
# import from it.


def _report_derived(counts) -> None:
    """Print what the derive step produced.

    #17 asks that the raw and filtered candidate counts be reported, and the
    reason is not tidiness: the recurrence filter is a known miss generator
    (part 06 §8.4), so the gap between the two numbers is the size of what is
    being set aside. A filter whose cost is never printed is a filter nobody
    argues with.
    """
    if counts.memo_misses:
        print(
            f"rebuild: {counts.memo_hits} of {counts.paragraphs} paragraphs "
            f"read by the extraction; {counts.memo_misses} not current - run "
            "the extraction to read them"
        )
    print(
        f"rebuild: {counts.placements} placement(s), "
        f"{counts.unplaced_forms} unplaced surface form(s), "
        f"{counts.relations} relation(s), "
        f"{counts.proposed_match_terms} proposed match term(s)"
    )
    for subject_id, (raw, kept) in sorted(counts.per_subject.items()):
        print(
            f"rebuild:   {subject_id}: {raw} candidate(s) raw -> {kept} above "
            f"the recurrence filter (threshold {counts.recurrence_threshold})"
        )
    if counts.clusters:
        print(
            f"rebuild: {counts.clusters} cluster(s) "
            f"[{counts.clustering_backend}]"
        )
    elif counts.placements or counts.candidates_raw:
        print(
            "rebuild: no clusters - install the `graph` extra "
            "(`pip install -e '.[graph]'`) to cluster the co-occurrence graph"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="memoria")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "validate", help="Verify the raw evidence corpus against its manifest"
    )
    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Delete and regenerate all derived state from the normalized records",
    )
    rebuild_parser.add_argument(
        "--recurrence-threshold",
        type=int,
        default=None,
        metavar="N",
        help=(
            "How many distinct paragraphs a candidate must appear in to clear "
            "the recurrence filter (default 5). Rejected candidates are kept "
            "and stay listable either way."
        ),
    )
    rebuild_parser.add_argument(
        "--reset-cache",
        action="store_true",
        help=(
            "Also discard the extraction's memo cache. This throws away model "
            "output that only another extraction pass can replace; a plain "
            "rebuild keeps it."
        ),
    )
    subparsers.add_parser(
        "checkpoint",
        help="Commit any outside edits to durable files under one CHG- id",
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
        report = run_normalize(repository, evidence_root, force_all=args.all)
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
        try:
            report = rebuild(
                repository,
                recurrence_threshold=args.recurrence_threshold,
                reset_cache=args.reset_cache,
            )
        except IndexSchemaError as exc:
            print(f"rebuild: {exc}", file=sys.stderr)
            return 1
        records = report.records
        print(
            f"rebuild: indexed {len(records)} records to "
            f"{repository.root / INDEX_RELATIVE_PATH}"
        )
        if not records:
            print(
                "rebuild: no normalized records found - run `memoria "
                "normalize` to produce them, or choose an evidence corpus "
                "(see docs/open-problems.md 2.4)"
            )
        _report_derived(report.counts)
        change_ids = changes.rebuild(repository)
        print(
            f"rebuild: wrote {len(change_ids)} change projection(s) to "
            f"{repository.root / changes.CHANGES_RELATIVE_PATH}"
        )
        return 0

    if args.command == "checkpoint":
        result = checkpoint(repository)
        if isinstance(result, Checkpointed):
            print(f"checkpoint: committed {len(result.files)} file(s) as {result.change_id}")
        else:
            print("checkpoint: nothing to checkpoint, tree is clean")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
