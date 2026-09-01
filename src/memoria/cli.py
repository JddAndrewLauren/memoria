"""Memoria CLI entry point."""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from memoria.answer_key import (
    ANSWER_KEY_RELATIVE_PATH,
    build_answer_key,
    write_answer_key,
)
from memoria.cross_references import (
    CROSS_REFERENCES_RELATIVE_PATH,
    extract_cross_references,
    write_cross_references_table,
)
from memoria.editorial import (
    EDITORIAL_RELATIVE_PATH,
    extract_editorial_apparatus,
    write_editorial_records,
)
from memoria.index import INDEX_RELATIVE_PATH, rebuild
from memoria.normalize import (
    normalize_journals,
    normalize_letters,
    normalize_targets,
    recipients_table,
    write_normalized_records,
    write_recipients_table,
)
from memoria.validate import NORMALIZED_RELATIVE_PATH, validate
from memoria.year_resolution import resolve_years

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
    subparsers.add_parser(
        "rebuild",
        help="Delete and regenerate all derived state (normalized records, search index) from evidence",
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
        # Order matters (issue #6 review round 3, in response to #5 review
        # round 1's note that this sequence was undocumented):
        # resolve_years() reads only record.recorded_date and re-parses
        # the raw file directly for headings/chapters - it never reads
        # record.paragraphs - so it is unaffected by whether
        # extract_editorial_apparatus() has already stripped that record's
        # paragraphs. Running it first anyway is deliberate pipeline
        # discipline, not accidental: it is the "read-mostly" mutation
        # (recorded_date/event_date/date_confidence only), while editorial
        # extraction is the more invasive one (rewrites/drops paragraphs
        # outright) - doing the narrower mutation first keeps the sequence
        # easy to reason about and guards against a future resolve_years
        # change that starts reading paragraph text landing after its
        # apparatus has already been stripped out from under it.
        #
        # resolve_years() operates on journal_records only, before
        # letter_records exist - it filters internally by JOURNAL_VOLUMES /
        # original_file and would leave letter records untouched even
        # called on the combined list, but keeping letters out of it
        # entirely is one fewer thing to reason about.
        #
        # extract_editorial_apparatus() (issue #56) now covers both source
        # types, so letter_records must exist first - it filters
        # internally by original_file too, and processing only
        # journal_records here would silently leave the letters'
        # apparatus inline, undoing #56.
        warnings = resolve_years(journal_records, evidence_root())
        for warning in warnings:
            print(f"normalize: {warning}")
        letter_records = normalize_letters(
            evidence_root(), start_id=len(journal_records) + 1
        )
        editorial_records = extract_editorial_apparatus(
            evidence_root(), journal_records + letter_records
        )
        # The audit targets (issue #9) come last in the SRC- sequence, so
        # adding them moves no existing ID.
        target_records = normalize_targets(
            evidence_root(),
            start_id=len(journal_records) + len(letter_records) + 1,
        )
        records = journal_records + letter_records + target_records
        output_root = repo_root() / NORMALIZED_RELATIVE_PATH
        written = write_normalized_records(records, output_root)
        editorial_output_root = repo_root() / EDITORIAL_RELATIVE_PATH
        editorial_written = write_editorial_records(
            editorial_records, editorial_output_root
        )
        counts = Counter(record.date_confidence for record in records)
        counts_text = ", ".join(
            f"{level}={counts[level]}"
            for level in (
                "exact",
                "inferred",
                "chapter-only",
                "unresolved",
                "published",
            )
            if counts[level]
        )
        print(
            f"normalize: wrote {len(written)} records to {output_root} ({counts_text})"
        )
        print(
            f"normalize: wrote {len(editorial_written)} editorial records to "
            f"{editorial_output_root}"
        )
        table = recipients_table(letter_records)
        recipients_path = write_recipients_table(
            table, output_root / "recipients.yaml"
        )
        print(f"normalize: wrote {len(table)} recipients to {recipients_path}")
        cross_references = extract_cross_references(editorial_records)
        cross_references_path = write_cross_references_table(
            cross_references, repo_root() / CROSS_REFERENCES_RELATIVE_PATH
        )
        print(
            f"normalize: wrote {len(cross_references)} cross-references to "
            f"{cross_references_path}"
        )
        key_rows, key_summaries, key_editions = build_answer_key(
            evidence_root(), cross_references, records
        )
        key_path = write_answer_key(
            key_rows,
            key_summaries,
            key_editions,
            repo_root() / ANSWER_KEY_RELATIVE_PATH,
        )
        resolved = sum(s.resolved for s in key_summaries)
        print(
            f"normalize: wrote {len(key_rows)} answer-key links to {key_path} "
            f"({resolved} resolved)"
        )
        return 0

    if args.command == "rebuild":
        root = repo_root()
        records = rebuild(evidence_root(), root)
        print(
            f"rebuild: indexed {len(records)} records to "
            f"{root / INDEX_RELATIVE_PATH}"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
