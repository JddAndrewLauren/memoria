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
# they annotate. Nothing produces editorial records today: the extractor was
# written for the retired Thoreau corpus (docs/open-problems.md §2.4). The
# source_type survives it deliberately - the contemporaneous/retrospective
# split is how §6's temporal discipline reaches retrieval (#12), and it is
# part of the record schema rather than of any one corpus.


@dataclass
class SearchResult:
    src_id: str
    anchor: str
    source_type: str


@dataclass
class SearchFilters:
    """The §25 filters #12 ships, over the plain ``paragraphs`` table.

    All four compose (ANDed together) and are all optional. ``event_date``
    and ``recorded_date`` match the verbatim frontmatter string exactly - the
    schema gives dates no sortable value (``date_confidence`` runs from
    ``exact`` to ``unresolved``), so a range filter has nothing ordered to
    compare against; exact match is what the field actually supports
    (docs/tool-surface.md records the choice).
    """

    event_date: str | None = None
    recorded_date: str | None = None
    source_type: str | None = None
    contemporaneous: bool | None = None


def build_index(db_path: Path, records: list[NormalizedRecord]) -> None:
    """(Re)build the FTS5 index at ``db_path`` from ``records``.

    Each record is indexed under its own ``source_type``, which is what
    ``SearchFilters.source_type`` filters on - an editorial record is a
    record whose source_type says so, not a separate kind of argument. (It
    used to be a second parameter to this function, taking the extractor's
    own record type; that type was Thoreau-specific and went with the corpus,
    and the schema's discriminator was always the better seam.)

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
        # A plain (non-FTS) table keyed by anchor, carrying the filterable
        # metadata. #81 (a sqlite-vec table) and #74 (the extraction's
        # placements) put more paragraph-keyed rows in this same database
        # file and must honour these same filters; if the metadata lived
        # only inside the FTS5 virtual table, every one of those queries
        # would either join into a virtual table or keep a second copy of
        # it - the §40.1 duplication this table exists to avoid.
        con.execute(
            "CREATE TABLE paragraphs("
            "anchor TEXT PRIMARY KEY, src_id TEXT, source_type TEXT, "
            "event_date TEXT, recorded_date TEXT, contemporaneous INTEGER"
            ")"
        )
        for record in records:
            for paragraph_number, paragraph in enumerate(record.paragraphs, start=1):
                anchor = record.anchor_id(paragraph_number)
                con.execute(
                    "INSERT INTO records (src_id, anchor, source_type, text) "
                    "VALUES (?, ?, ?, ?)",
                    (record.id, anchor, record.source_type, paragraph),
                )
                con.execute(
                    "INSERT INTO paragraphs "
                    "(anchor, src_id, source_type, event_date, recorded_date, "
                    "contemporaneous) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        anchor,
                        record.id,
                        record.source_type,
                        record.event_date,
                        record.recorded_date,
                        1 if record.contemporaneous else 0,
                    ),
                )
        con.commit()
    finally:
        con.close()


def filter_predicate(filters: SearchFilters | None) -> tuple[str, list]:
    """One predicate builder, turning a ``SearchFilters`` into a SQL ``WHERE``
    fragment and its params against the plain ``paragraphs`` table.

    Reusable by any query joined to that table, FTS5 or not: ``search()``
    joins FTS5 hits to it, and #81/#74 are expected to join a vector search
    and cluster membership to it the same way.

    Returns ``("", [])`` when no filter is set, so a caller can always append
    ``f"AND {sql}"`` when ``sql`` is truthy rather than branching itself.
    """
    if filters is None:
        return "", []
    clauses = []
    params: list = []
    if filters.event_date is not None:
        clauses.append("paragraphs.event_date = ?")
        params.append(filters.event_date)
    if filters.recorded_date is not None:
        clauses.append("paragraphs.recorded_date = ?")
        params.append(filters.recorded_date)
    if filters.source_type is not None:
        clauses.append("paragraphs.source_type = ?")
        params.append(filters.source_type)
    if filters.contemporaneous is not None:
        clauses.append("paragraphs.contemporaneous = ?")
        params.append(1 if filters.contemporaneous else 0)
    return " AND ".join(clauses), params


def search(
    repository: Repository, query: str, filters: SearchFilters | None = None
) -> list[SearchResult]:
    """Full-text search the index, returning matching records with their
    ``SRC-`` ID and the paragraph anchor that matched, ranked by relevance.

    Takes the frozen ``Repository`` value, like every other core read
    (ADR-0004), rather than a bare ``db_path`` - #74 and #81 inherit this
    shape.

    ``filters`` narrows by event date, recorded date, source type and
    contemporaneous/retrospective (``SearchFilters``); all compose. Applied
    in the core so the same filters reach every caller - the MCP tool (#12),
    the web API (#64) and cross-layer search (#24) - without a second,
    divergent copy in any of them (§40.1).

    A missing index - every fresh clone, since ``.memoria/`` is gitignored -
    returns no results rather than raising or creating the database file:
    "the corpus is not built" is an answer, not a driver exception.
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        predicate, predicate_params = filter_predicate(filters)
        sql = (
            "SELECT records.src_id, records.anchor, records.source_type "
            "FROM records JOIN paragraphs ON paragraphs.anchor = records.anchor "
            "WHERE records MATCH ?"
        )
        params: list = [query]
        if predicate:
            sql += f" AND {predicate}"
            params.extend(predicate_params)
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
