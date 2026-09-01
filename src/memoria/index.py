"""Build and query the FTS5 search index over normalized records.

Scope of this module (issue #7): a SQLite FTS5 index over
``sources/normalized/`` records' paragraphs, and ``memoria rebuild``, which
deletes and regenerates the index from evidence + normalization -
establishing the §42 contract that derived state carries no authority and
can always be thrown away. Search-time chunking lives in the index only;
the normalized record stays the unit of evidence (docs/adr, part 16 M0).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memoria.cross_references import (
    CROSS_REFERENCES_RELATIVE_PATH,
    extract_cross_references,
    write_cross_references_table,
)
from memoria.editorial import (
    EDITORIAL_RELATIVE_PATH,
    EditorialRecord,
    extract_editorial_apparatus,
    write_editorial_records,
)
from memoria.normalize import (
    NormalizedRecord,
    normalize_journals,
    normalize_letters,
    normalize_targets,
    recipients_table,
    write_normalized_records,
    write_recipients_table,
)
from memoria.validate import NORMALIZED_RELATIVE_PATH
from memoria.year_resolution import resolve_years

INDEX_RELATIVE_PATH = ".memoria/index.db"

# Editorial records (issue #5's EditorialRecord - footnotes, bracketed
# asides, interpolations, introductions) are indexed under this
# source_type, distinct from any NormalizedRecord's own source_type
# ("journal" or "letter"), so exclude_editorial actually excludes them.
EDITORIAL_SOURCE_TYPES = frozenset({"editorial"})


@dataclass
class SearchResult:
    src_id: str
    anchor: str
    source_type: str


def build_index(
    db_path: Path,
    records: list[NormalizedRecord],
    editorial_records: list[EditorialRecord] | None = None,
) -> None:
    """(Re)build the FTS5 index at ``db_path`` from ``records`` and,
    optionally, ``editorial_records`` (issue #5) - indexed under
    ``source_type: "editorial"`` so ``exclude_editorial`` actually
    excludes them, rather than the evidence rows they annotate.

    Deletes any existing database file first, so the index is always a
    clean regeneration rather than an incremental update - derived state
    has no authority of its own (§42).
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE VIRTUAL TABLE records USING fts5("
            "src_id UNINDEXED, anchor UNINDEXED, source_type UNINDEXED, text"
            ")"
        )
        for record in records:
            for paragraph_number, paragraph in enumerate(record.paragraphs, start=1):
                con.execute(
                    "INSERT INTO records (src_id, anchor, source_type, text) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        record.id,
                        record.anchor_id(paragraph_number),
                        record.source_type,
                        paragraph,
                    ),
                )
        for editorial in editorial_records or []:
            con.execute(
                "INSERT INTO records (src_id, anchor, source_type, text) "
                "VALUES (?, ?, ?, ?)",
                (
                    editorial.id,
                    editorial.linked_anchor or "",
                    "editorial",
                    editorial.text,
                ),
            )
        con.commit()
    finally:
        con.close()


def search(
    db_path: Path, query: str, exclude_editorial: bool = False
) -> list[SearchResult]:
    """Full-text search the index, returning matching records with their
    ``SRC-`` ID and the paragraph anchor that matched, ranked by relevance.

    Evidence and editorial-voice records are distinguished by
    ``source_type``: pass ``exclude_editorial=True`` to search evidence
    only.
    """
    con = sqlite3.connect(db_path)
    try:
        sql = (
            "SELECT src_id, anchor, source_type FROM records "
            "WHERE records MATCH ?"
        )
        params: list[str] = [query]
        if exclude_editorial:
            placeholders = ", ".join("?" for _ in EDITORIAL_SOURCE_TYPES)
            sql += f" AND source_type NOT IN ({placeholders})"
            params.extend(EDITORIAL_SOURCE_TYPES)
        sql += " ORDER BY rank"
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [SearchResult(src_id=r[0], anchor=r[1], source_type=r[2]) for r in rows]


def rebuild(evidence_root: Path, repo_root: Path) -> list[NormalizedRecord]:
    """Delete and regenerate all derived state - the normalized records,
    the recipients table, the cross-reference table, the editorial
    records, and the FTS5 index - from evidence, losing nothing (§42).

    Normalized records are themselves rebuildable derived state (see
    ``docs/normalized-record-schema.md``): this re-derives them from
    evidence before indexing, rather than trusting whatever is already on
    disk under ``sources/normalized/``, so rebuild is correct whether that
    directory is absent, stale, or up to date. Editorial apparatus
    (issue #5) is extracted out of the journal records - and the
    editorial records it produces written and indexed - in the same pass,
    so a plain ``rebuild()`` never regresses back to unstripped,
    unsearchable-exclusion evidence the way calling ``normalize_journals``
    + ``build_index`` directly would. Must also produce exactly what
    ``memoria normalize`` produces for the letters (issue #6 review round
    1: rebuild used to call ``normalize_journals`` alone, silently
    deleting every letter record on a rebuild and leaving a stale
    ``recipients.yaml`` behind) - ``tests/test_cli.py``'s
    ``test_rebuild_produces_byte_identical_output_to_normalize`` is the
    regression test for the whole class of defect, not just this instance.

    Letters do not get year resolution or editorial extraction here:
    ``resolve_years`` and ``extract_editorial_apparatus`` both filter by
    ``original_file`` against ``JOURNAL_VOLUMES`` and leave letter records
    untouched, so every letter keeps ``date_confidence: unresolved`` after
    both ``memoria normalize`` and ``memoria rebuild`` - deliberately, not
    a gap this function is meant to close. A letter's dateline already
    carries an explicit year as text (unlike a journal heading), but
    turning that into a resolved ``event_date``/``date_confidence`` is
    letters-specific year-resolution work issue #6 scoped out (part 16:
    "year resolution" and "letters parsing" are separate M0 build steps),
    not something to grow inside ``rebuild()`` unasked.
    """
    evidence_root = Path(evidence_root)
    repo_root = Path(repo_root)

    journal_records = normalize_journals(evidence_root)
    # Order matters (see cli.py's matching comment on `memoria normalize`,
    # which this function must stay in lockstep with): resolve_years()
    # reads only recorded_date and the raw file, never record.paragraphs,
    # so it is unaffected by extract_editorial_apparatus()'s paragraph
    # rewrite either way - run first anyway as the narrower, read-mostly
    # mutation before the more invasive one.
    resolve_years(journal_records, evidence_root)
    editorial_records = extract_editorial_apparatus(evidence_root, journal_records)
    letter_records = normalize_letters(
        evidence_root, start_id=len(journal_records) + 1
    )
    target_records = normalize_targets(
        evidence_root, start_id=len(journal_records) + len(letter_records) + 1
    )
    records = journal_records + letter_records + target_records

    output_root = repo_root / NORMALIZED_RELATIVE_PATH
    write_normalized_records(records, output_root)
    write_recipients_table(
        recipients_table(letter_records), output_root / "recipients.yaml"
    )
    write_cross_references_table(
        extract_cross_references(editorial_records),
        repo_root / CROSS_REFERENCES_RELATIVE_PATH,
    )
    write_editorial_records(editorial_records, repo_root / EDITORIAL_RELATIVE_PATH)
    # The audit targets are deliberately **not** indexed. The index is the
    # evidence retrieval surface; the books are the query side of the
    # benchmark (a probe is a book paragraph, part 06 §8.3). Indexing them
    # would let a search for a book paragraph return that same paragraph as
    # its own top hit, which is the self-agreement failure the answer key
    # exists to prevent. Appearances over the audit targets (part 06 §8.11)
    # are M2's, and get their own structure.
    build_index(
        repo_root / INDEX_RELATIVE_PATH,
        journal_records + letter_records,
        editorial_records,
    )
    return records
