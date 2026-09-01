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

from memoria.normalize import (
    NormalizedRecord,
    normalize_journals,
    write_normalized_records,
)
from memoria.validate import NORMALIZED_RELATIVE_PATH
from memoria.year_resolution import resolve_years

INDEX_RELATIVE_PATH = ".memoria/index.db"

# Source types that carry editorial voice rather than evidence - Torrey's
# apparatus, footnotes, introductions. Segregating these into their own
# records is issue #5's job; this is the forward-looking hook that lets a
# query exclude them by source_type once it does. Empty for now: this
# slice's normalizer only ever produces source_type "journal".
EDITORIAL_SOURCE_TYPES = frozenset({"editorial"})


@dataclass
class SearchResult:
    src_id: str
    anchor: str
    source_type: str


def build_index(db_path: Path, records: list[NormalizedRecord]) -> None:
    """(Re)build the FTS5 index at ``db_path`` from ``records``.

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
    """Delete and regenerate all derived state - the normalized records and
    the FTS5 index - from evidence, losing nothing (§42).

    Normalized records are themselves rebuildable derived state (see
    ``docs/normalized-record-schema.md``): this re-derives them from
    evidence before indexing, rather than trusting whatever is already on
    disk under ``sources/normalized/``, so rebuild is correct whether that
    directory is absent, stale, or up to date.
    """
    evidence_root = Path(evidence_root)
    repo_root = Path(repo_root)

    records = normalize_journals(evidence_root)
    resolve_years(records, evidence_root)
    write_normalized_records(records, repo_root / NORMALIZED_RELATIVE_PATH)
    build_index(repo_root / INDEX_RELATIVE_PATH, records)
    return records
