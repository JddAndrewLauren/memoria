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

from memoria.records import NormalizedRecord, read_all
from memoria.repository import Repository

INDEX_RELATIVE_PATH = ".memoria/index.db"

# Editorial records - footnotes, bracketed asides, interpolations, editors'
# introductions - carry this source_type, distinct from the evidence rows
# they annotate, so exclude_editorial actually excludes them.
#
# Nothing produces editorial records today: the extractor was written for the
# retired Thoreau corpus (docs/open-problems.md §2.4). The source_type and the
# filter survive it deliberately - the contemporaneous/retrospective split is
# how §6's temporal discipline reaches retrieval (#12), and it is part of the
# record schema rather than of any one corpus.
EDITORIAL_SOURCE_TYPES = frozenset({"editorial"})


@dataclass
class SearchResult:
    src_id: str
    anchor: str
    source_type: str


def build_index(db_path: Path, records: list[NormalizedRecord]) -> None:
    """(Re)build the FTS5 index at ``db_path`` from ``records``.

    Each record is indexed under its own ``source_type``, which is what
    ``exclude_editorial`` filters on - an editorial record is a record whose
    source_type says so, not a separate kind of argument. (It used to be a
    second parameter, taking the extractor's own record type; that type was
    Thoreau-specific and went with the corpus, and the schema's discriminator
    was always the better seam.)

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


def rebuild(repository: Repository) -> list[NormalizedRecord]:
    """Delete and regenerate all derived state from evidence, losing nothing.

    §42's contract: derived state carries no authority and can always be
    thrown away. That contract is the point of this function and it is
    unchanged.

    **There is no normalizer to call.** The one that existed was written for
    the Thoreau proof-of-concept corpus, which was retired 2026-09-01
    (``docs/open-problems.md`` §2.4); it was removed with the corpus, and no
    replacement is chosen. So this rebuilds the index from the records
    already on disk and reports that no producer is wired in.

    That is deliberately not a seam. Inventing a normalizer signature for a
    corpus nobody has chosen would be exactly the speculative abstraction the
    retirement removed - the shape of that interface is a decision for
    whoever chooses the corpus, made against a real one.

    Returns the records it indexed, which is an empty list when none exist.
    """
    records = read_all(repository)
    build_index(repository.root / INDEX_RELATIVE_PATH, records)
    return records
