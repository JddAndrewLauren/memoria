"""Memoria CLI entry point."""

import argparse
import sys

from memoria import changes
from memoria.embeddings import default_embed_fn
from memoria.extraction import RECURRENCE_THRESHOLD_DEFAULT
from memoria.index import INDEX_RELATIVE_PATH, IndexSchemaError, rebuild
from memoria.normalize import normalize as run_normalize
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import NoEvidenceRoot, from_env, require_evidence_root
from memoria.subjects import write_builtin_subjects
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


def _report_appearances(report) -> None:
    """Print what the appearances pass produced (#19, part 06 §8.11).

    The seventh acceptance criterion is that Themes and Arcs producing no
    appearances is a reported gap, not a silent zero - so this always names
    what was skipped and why, not only what was found.
    """
    print(
        f"rebuild: {report.appearances} appearance(s) over "
        f"{report.entries_computed} lexically-matchable entr"
        f"{'y' if report.entries_computed == 1 else 'ies'}"
    )
    if report.skipped_subjects:
        print(
            f"rebuild: appearances not computed for {report.entries_skipped} "
            f"entr{'y' if report.entries_skipped == 1 else 'ies'} under "
            f"{', '.join(report.skipped_subjects)} - the model engine those "
            "subjects need still waits for the audit at M5 (part 06 §8.11)"
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
            f"the recurrence filter (default {RECURRENCE_THRESHOLD_DEFAULT}). "
            "Rejected candidates are kept and stay listable either way."
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
    subparsers.add_parser(
        "seed-subjects",
        help=(
            "Write the five built-in subjects into the repository, skipping "
            "any that already exist"
        ),
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
        try:
            errors = validate(evidence_root, repository.root)
        except IndexSchemaError as exc:
            print(f"validate: {exc}", file=sys.stderr)
            return 1
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
        # The drift report (#79, part 05 §5.4): printed before the caller
        # decides whether to launch the extraction, so a converter bump's
        # cost is a number, not a surprise. Always printed, zero included -
        # "reports zero changed paragraph hashes" is itself the gate output
        # on an unchanged pin.
        print(
            f"normalize: {len(report.paragraph_drift)} record(s), "
            f"{sum(report.paragraph_drift.values())} paragraph hash(es) "
            "changed since their last conversion"
        )
        if report.unconvertible:
            print(
                f"normalize: {len(report.unconvertible)} unit(s) have no "
                "converter registered for their format yet"
            )
        if report.failed:
            print(
                f"normalize: {len(report.failed)} unit(s) failed to convert "
                "and have no record - each is retried on the next run:",
                file=sys.stderr,
            )
            for unit_id, reason in report.failed.items():
                print(f"  {unit_id}: {reason}", file=sys.stderr)
        return 0

    if args.command == "rebuild":
        try:
            report = rebuild(
                repository,
                recurrence_threshold=args.recurrence_threshold,
                reset_cache=args.reset_cache,
                # The one caller that opts into the semantic index (#81):
                # `rebuild`'s own default is `None` (skip) so that every
                # other caller - the test suite included - never triggers a
                # real model load. `memoria rebuild` is the actual "at
                # rebuild" moment ADR-0007 names.
                embed_fn=default_embed_fn,
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
        _report_appearances(report.appearances)
        change_ids = changes.rebuild(repository)
        print(
            f"rebuild: wrote {len(change_ids)} change projection(s) to "
            f"{repository.root / changes.CHANGES_RELATIVE_PATH}"
        )
        print(f"rebuild: completed in {report.elapsed_seconds:.2f}s")
        return 0

    if args.command == "checkpoint":
        result = checkpoint(repository)
        if isinstance(result, Checkpointed):
            print(f"checkpoint: committed {len(result.files)} file(s) as {result.change_id}")
        else:
            print("checkpoint: nothing to checkpoint, tree is clean")
        return 0

    if args.command == "seed-subjects":
        written = write_builtin_subjects(repository)
        if written:
            for path in written:
                print(f"seed-subjects: wrote {path}")
        else:
            print(
                "seed-subjects: nothing to write, all five built-in subjects "
                "already exist"
            )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
