"""Build and query the FTS5 search index over normalized records.

Scope of this module (issue #7): a SQLite FTS5 index over
``sources/normalized/`` records' paragraphs, and ``memoria rebuild``, which
deletes and regenerates the index from evidence + normalization -
establishing the §42 contract that derived state carries no authority and
can always be thrown away. Search-time chunking lives in the index only;
the normalized record stays the unit of evidence (docs/adr, part 16 M0).

**This module owns the database file's shape** (#17). Every ``CREATE TABLE``
in ``.memoria/index.db`` is here, including the extraction's - placements,
unplaced surface forms, relations, candidates, clusters and the memo cache -
even though ``memoria.extraction`` is what reads and writes those rows. The
DDL cannot live there: ``extraction`` imports ``INDEX_RELATIVE_PATH`` from
this module, so the reverse direction would be a cycle. Keeping it here also
puts the rebuild rule (``PRESERVED_TABLES`` / ``DERIVED_TABLES``) beside the
function that enforces it, where one test can check that every table in the
file is named by exactly one of the two.

**It also owns the gathered set and its pin/exclude overlay** (#18, #21, part
06 §8.3): ``gather`` recombines what ``placements``/``relations`` already
hold with a direct lexical match against an entry's own word-shaped match
terms, plus the overlay. ``pin``/``exclude`` record the author's attributed
overlay **on the entry file itself** (``memoria.subjects.OverlayAct``),
through the durable write path (``memoria.write``) - not in this database at
all. Part 04 §42 is explicit that "deleting ``.memoria/index.db`` must never
destroy intellectual work"; an index-only overlay row would fail that the
moment someone deletes ``.memoria/`` rather than merely running
``memoria rebuild`` against it, so this file holds no table for it and there
is nothing here for a rebuild to preserve or lose.

**And appearances, lexical engine only** (#19, part 06 §8.11): the manuscript
passages an entry turns out to touch, with a short note on how - kept in the
derived ``appearances`` table, separate from the gathered set on purpose
(§8.8's reason: a gathered set is evidence to write from, an appearance is
prose already written, and merging them would let the book cite itself).
``compute_appearances`` runs at every ``memoria rebuild`` and is the only
writer; there is no overlay and no author act against a row, because an
author act against one passage would be a durable pointer into mutable prose
(§4.1). Themes and Arcs cannot appear this way - manuscript prose is never
extracted, so there are no placements over it to intersect - and are skipped
rather than silently returning nothing (``AppearancesReport``).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, replace as dataclass_replace
from datetime import datetime, timezone

from memoria.records import NormalizedRecord, real_paragraphs, read_all
from memoria.repository import Repository
from memoria.subjects import (
    OverlayAct,
    SubjectError,
    classify_match_term,
    entry_to_markdown,
    find_entry_path,
    load_all_entries,
    load_entry,
    parse_entry,
)
from memoria.write import Actor, Rejected, WriteError, serve, write as write_file

INDEX_RELATIVE_PATH = ".memoria/index.db"

# Editorial records - footnotes, bracketed asides, interpolations, editors'
# introductions - carry this source_type, distinct from the evidence rows
# they annotate. Nothing produces editorial records today: the extractor was
# written for the retired Thoreau corpus (docs/open-problems.md §2.4). The
# source_type survives it deliberately - the contemporaneous/retrospective
# split is how §6's temporal discipline reaches retrieval (#12), and it is
# part of the record schema rather than of any one corpus.


# --- the database file's shape ----------------------------------------------
#
# Two lists, and between them they *are* the rebuild rule (#17, ADR-0005
# build shape 1): a rebuild drops every derived table and recreates it, and
# leaves the preserved ones alone. A table that appears in neither list is a
# bug, and `tests/test_index.py` fails on one - which is what catches the
# real failure mode here, someone adding a table and forgetting to say which
# side of the line it falls on.

# The memo cache and its schema marker - **the only rows in this file a
# rebuild does not throw away**. Everything else here can be recomputed from
# evidence plus the author's durable acts, and the memo cache cannot be
# recomputed at all without a model. That is the whole predicate - not
# "paragraph rows versus cluster rows" - which is why one table with a
# `kind` column carries both (part 06 §8.12's "one cache, two key
# compositions"). The pin/exclude overlay used to be a third preserved
# table here (#18); #21 moved it onto the entry file instead
# (`memoria.subjects.OverlayAct`), because "preserved by a rebuild" is not
# the same guarantee as "survives `.memoria/` being deleted outright", which
# is what part 04 §42 actually demands of an attributed author act.
PRESERVED_TABLES = ("memoria_schema", "memo")

# Everything else. Dropped and regenerated on every `memoria rebuild`, which
# is §42's contract made mechanical.
DERIVED_TABLES = (
    "records",
    "paragraphs",
    "placements",
    "unplaced_forms",
    "relations",
    "candidates",
    "candidate_forms",
    "candidate_paragraphs",
    "proposed_match_terms",
    "clusters",
    "cluster_members",
    "cluster_relations",
    "cluster_paragraphs",
    "extraction_meta",
    "appearances",
)

# Bumped when the *shape* of a memo row changes in a way that makes an
# existing cache unreadable. It is not bumped when a prompt changes - a
# prompt change moves every key instead (memoria.extraction), which is a
# miss rather than a corruption, and the old rows sit inert.
MEMO_SCHEMA_VERSION = "1"

_PRESERVED_DDL = (
    "CREATE TABLE IF NOT EXISTS memoria_schema("
    "key TEXT PRIMARY KEY, value TEXT NOT NULL"
    ")",
    # `key` is the composed hash and nothing else: a memo row is addressed by
    # what it depends on, never by where it happens to sit. That is what lets
    # a cluster summary survive a re-clustering that lands on the same
    # membership, and what makes an orphaned row (a paragraph that was
    # renormalized out from under it) inert rather than wrong - nothing ever
    # looks a row up by `anchor`.
    "CREATE TABLE IF NOT EXISTS memo("
    "key TEXT PRIMARY KEY, "
    "kind TEXT NOT NULL CHECK (kind IN ('paragraph', 'cluster_summary')), "
    "anchor TEXT NOT NULL DEFAULT '', "
    "value TEXT NOT NULL, "
    "written_at TEXT NOT NULL"
    ")",
    "CREATE INDEX IF NOT EXISTS memo_kind_anchor ON memo(kind, anchor)",
)

_DERIVED_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS records USING fts5("
    "src_id UNINDEXED, anchor UNINDEXED, source_type UNINDEXED, text"
    ")",
    # A plain (non-FTS) table keyed by anchor, carrying the filterable
    # metadata. #81 (a sqlite-vec table) and the extraction's placements put
    # more paragraph-keyed rows in this same database file and must honour
    # these same filters; if the metadata lived only inside the FTS5 virtual
    # table, every one of those queries would either join into a virtual
    # table or keep a second copy of it - the §40.1 duplication this table
    # exists to avoid.
    "CREATE TABLE IF NOT EXISTS paragraphs("
    "anchor TEXT PRIMARY KEY, src_id TEXT, source_type TEXT, "
    "event_date TEXT, recorded_date TEXT, contemporaneous INTEGER, "
    "email_from TEXT, email_to TEXT"
    ")",
    # A placement the entry's match terms license (part 06 §8.4). `licensed_by`
    # names *which* term did it, so "adding a match term changed placements"
    # is inspectable rather than merely countable.
    "CREATE TABLE IF NOT EXISTS placements("
    "anchor TEXT NOT NULL, entry_id TEXT NOT NULL, "
    "surface_form TEXT NOT NULL, licensed_by TEXT NOT NULL, "
    "PRIMARY KEY (anchor, entry_id, surface_form)"
    ")",
    "CREATE INDEX IF NOT EXISTS placements_entry ON placements(entry_id)",
    # Every mention that did not become a placement, and why. This table is
    # the placement-recall mitigation: unreported recall is survivable only
    # because the misses stay countable (ADR-0005 consequences).
    "CREATE TABLE IF NOT EXISTS unplaced_forms("
    "anchor TEXT NOT NULL, surface_form TEXT NOT NULL, "
    "subject_id TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL, "
    "proposed_entry_id TEXT NOT NULL DEFAULT '', "
    "PRIMARY KEY (anchor, surface_form, reason, proposed_entry_id)"
    ")",
    # `from_ref`/`to_ref` rather than subject/object: `subject` means People
    # or Themes in this codebase, and CONTEXT.md's avoid list rules out
    # "edge" and "triple". A ref is an entry id or `CAND:<candidate_id>`.
    "CREATE TABLE IF NOT EXISTS relations("
    "anchor TEXT NOT NULL, from_ref TEXT NOT NULL, verb TEXT NOT NULL, "
    "to_ref TEXT NOT NULL, "
    "PRIMARY KEY (anchor, from_ref, verb, to_ref)"
    ")",
    "CREATE INDEX IF NOT EXISTS relations_from ON relations(from_ref)",
    "CREATE INDEX IF NOT EXISTS relations_to ON relations(to_ref)",
    # `above_threshold` is a column rather than a filter applied on the way
    # in, because a candidate the recurrence filter rejects has to stay
    # enumerable (part 06 §8.4): the filter is a guaranteed miss generator
    # and the misses are the mitigation.
    "CREATE TABLE IF NOT EXISTS candidates("
    "candidate_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, "
    "label TEXT NOT NULL, gloss TEXT NOT NULL, "
    "recurrence INTEGER NOT NULL, above_threshold INTEGER NOT NULL"
    ")",
    "CREATE INDEX IF NOT EXISTS candidates_subject ON candidates("
    "subject_id, above_threshold, recurrence DESC)",
    # Separate tables rather than a JSON blob on the candidate, so a rejected
    # candidate's forms and paragraphs are queryable without decoding it.
    "CREATE TABLE IF NOT EXISTS candidate_forms("
    "candidate_id TEXT NOT NULL, surface_form TEXT NOT NULL, "
    "occurrences INTEGER NOT NULL, "
    "PRIMARY KEY (candidate_id, surface_form)"
    ")",
    "CREATE TABLE IF NOT EXISTS candidate_paragraphs("
    "candidate_id TEXT NOT NULL, anchor TEXT NOT NULL, "
    "PRIMARY KEY (candidate_id, anchor)"
    ")",
    "CREATE TABLE IF NOT EXISTS proposed_match_terms("
    "entry_id TEXT NOT NULL, term TEXT NOT NULL, term_kind TEXT NOT NULL, "
    "occurrences INTEGER NOT NULL, "
    "PRIMARY KEY (entry_id, term)"
    ")",
    # `summary_key` points at a memo row - derived pointing at preserved,
    # never the other way. That direction is what makes dropping this table
    # safe: the summary it names outlives the cluster row entirely, and is
    # found again by membership rather than by cluster id (which does not
    # survive re-clustering, ADR-0005 decision 6).
    "CREATE TABLE IF NOT EXISTS clusters("
    "cluster_id TEXT PRIMARY KEY, level INTEGER NOT NULL, "
    "parent_id TEXT NOT NULL DEFAULT '', label TEXT NOT NULL, "
    "membership_hash TEXT NOT NULL, summary_key TEXT NOT NULL DEFAULT ''"
    ")",
    "CREATE INDEX IF NOT EXISTS clusters_level ON clusters(level)",
    "CREATE INDEX IF NOT EXISTS clusters_parent ON clusters(parent_id)",
    # `member_ref` is an entry reference or a `candidate:` ref - a cluster's
    # members are placed entries and candidates together (see
    # `extraction.build_clusters`), which is why the column is not `entry_id`.
    "CREATE TABLE IF NOT EXISTS cluster_members("
    "cluster_id TEXT NOT NULL, member_ref TEXT NOT NULL, "
    "PRIMARY KEY (cluster_id, member_ref)"
    ")",
    "CREATE TABLE IF NOT EXISTS cluster_relations("
    "cluster_id TEXT NOT NULL, from_ref TEXT NOT NULL, verb TEXT NOT NULL, "
    "to_ref TEXT NOT NULL, weight INTEGER NOT NULL, "
    "PRIMARY KEY (cluster_id, from_ref, verb, to_ref)"
    ")",
    "CREATE TABLE IF NOT EXISTS cluster_paragraphs("
    "cluster_id TEXT NOT NULL, anchor TEXT NOT NULL, "
    "PRIMARY KEY (cluster_id, anchor)"
    ")",
    # What the last derive ran with: the recurrence threshold, the prompt
    # hashes, the clustering backend that happened to be installed, and the
    # raw/filtered counts. A surface reporting a candidate list has to be
    # able to say what produced it.
    "CREATE TABLE IF NOT EXISTS extraction_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    # One row per (entry, passage) an entry's lexical match terms find among
    # the audit targets (#19, part 06 §8.11). `note` names the term that
    # matched - the "short note on how it appears" the acceptance criteria
    # ask for, the same shape as `placements.licensed_by`. Unlike the memo
    # cache and the gather overlay this is plain derived state: it carries no
    # author act, so it is dropped and recomputed like everything else here.
    "CREATE TABLE IF NOT EXISTS appearances("
    "entry_id TEXT NOT NULL, anchor TEXT NOT NULL, note TEXT NOT NULL, "
    "PRIMARY KEY (entry_id, anchor)"
    ")",
    "CREATE INDEX IF NOT EXISTS appearances_entry ON appearances(entry_id)",
)


class IndexSchemaError(Exception):
    """The index file on disk cannot be opened under this build's rules."""


@dataclass
class SearchResult:
    """One hit: where the match is, and optionally what it looks like.

    ``snippet`` is a **match locator, not evidence** (#95). It is a truncated,
    marked-up fragment of the FTS5 copy of the paragraph - the same category
    of thing as the line ``grep`` prints - and it is served only when a caller
    asks for it. Evidence is read through ``read(ref)`` with ``anchor``, which
    reads the record file itself; the index is derived state that carries no
    authority (part 04 §42), so a snippet out of it is a pointer that may go
    stale, never a quotation that may go wrong. Nothing ledgers a snippet as
    served (``memoria.ledger``), and ``references.parse`` does not accept one.
    """

    src_id: str
    anchor: str
    source_type: str
    snippet: str | None = None


# The marks FTS5 puts around matched terms inside a snippet. C0 control
# characters, because a normalized record is prose and never contains one:
# any printable marker could also be the evidence's own punctuation, and
# brackets - the obvious choice - are real editorial syntax in this schema
# (docs/normalized-record-schema.md's bracketed spans). A client splits on
# these; nothing interpolates them into markup, so evidence text can never
# be mistaken for the marker or for HTML.
SNIPPET_MATCH_START = "\x01"
SNIPPET_MATCH_END = "\x02"

# The ellipsis FTS5 puts where it truncated, which is what keeps a snippet
# visibly partial - a fragment that looked whole would be a quotation.
SNIPPET_ELLIPSIS = "..."

# How much of the paragraph a snippet may show, in FTS5 tokens (64 is the
# maximum the function accepts).
SNIPPET_TOKENS = 30

# ``text`` is the fourth column of the ``records`` FTS5 table, and
# ``snippet()`` takes that index rather than the column name.
_SNIPPET_TEXT_COLUMN = 3


@dataclass
class SearchFilters:
    """The §25 filters #12 ships, plus #111's two header filters, over the
    plain ``paragraphs`` table.

    All six compose (ANDed together) and are all optional. ``event_date``
    and ``recorded_date`` match the verbatim frontmatter string exactly - the
    schema gives dates no sortable value (``date_confidence`` runs from
    ``exact`` to ``unresolved``), so a range filter has nothing ordered to
    compare against; exact match is what the field actually supports
    (docs/tool-surface.md records the choice).

    ``from_`` and ``to`` are a case-insensitive substring match against the
    record's verbatim ``from`` / ``to`` frontmatter string (#111) - metadata
    retrieval, not entity resolution. `docs/corpora/enron.md` finding 3: half
    the correspondents in a real export are bare display names in mixed
    order, so this matches strings and resolves no person; that stays entry
    match-term work. ``from_`` rather than ``from``, which is a reserved
    word. An empty string is not a filter: it is treated exactly like
    ``None``, because a substring match on ``""`` would otherwise return
    every record that merely *has* the header (see ``filter_predicate``).

    ``level`` is the seventh, added 2026-09-01 for ``search_global`` (#74,
    ADR-0005 "Build shape" 4) - a cluster level, not a column on
    ``paragraphs``. It rides on this dataclass so one ``filters`` argument
    still covers everything a caller might narrow by (part 11 §25's filter
    list groups it with the other six), but ``filter_predicate`` below never
    references it: search_global consults it directly against ``clusters``,
    and ``search_text`` has no cluster to filter by, so it is silently
    unconsulted there rather than refused.
    """

    event_date: str | None = None
    recorded_date: str | None = None
    source_type: str | None = None
    contemporaneous: bool | None = None
    from_: str | None = None
    to: str | None = None
    level: int | None = None


@dataclass(frozen=True)
class RebuildReport:
    """What one ``memoria rebuild`` regenerated.

    ``rebuild`` used to return the bare record list, which was enough when
    the only derived thing was an FTS5 table. It now also runs the
    extraction's derive step, and #17 asks that the raw and filtered
    candidate counts be *reported* - so there has to be something to report
    them in. ``counts`` is ``extraction.DerivedCounts``, typed loosely here
    only to keep this module's imports one-way.

    ``appearances`` is ``AppearancesReport`` (#19) - what the appearances
    pass produced, and what it skipped.

    ``elapsed_seconds`` is wall-clock time over the whole function (#21's
    "reports what it regenerated and how long it took"), timed with
    ``time.monotonic`` rather than ``time.time`` so a clock adjustment
    mid-rebuild cannot report a negative duration.
    """

    records: list[NormalizedRecord]
    counts: object
    appearances: AppearancesReport
    elapsed_seconds: float


def build_index(
    repository: Repository,
    records: list[NormalizedRecord],
    *,
    reset_cache: bool = False,
) -> None:
    """(Re)build the derived tables in ``repository``'s index from ``records``.

    Takes the frozen ``Repository`` value, like ``search`` and every other
    core function that names a location (ADR-0004): the index path is a fact
    about a repository, not an argument a caller composes.

    Each record is indexed under its own ``source_type``, which is what
    ``SearchFilters.source_type`` filters on - an editorial record is a
    record whose source_type says so, not a separate kind of argument.

    **This used to delete the database file**, which was three jobs at once:
    it dropped the derived tables, it regenerated the FTS5 virtual table, and
    it migrated away any older schema. It cannot any more, because the memo
    cache (#17) lives in this file and is the one thing here a rebuild may
    not throw away - it holds model output, and a rebuild has no model to
    regenerate it with. So the three jobs are now done separately:

    - the derived tables are dropped by name from ``DERIVED_TABLES``;
    - ``DROP TABLE records`` takes the FTS5 shadow tables (``records_data``,
      ``records_idx``, ...) with it, which is SQLite's own behaviour and is
      what replaces the unlink for full-text search;
    - a schema this build does not recognise raises rather than being
      silently discarded.

    ``reset_cache=True`` restores the old behaviour and deletes the file
    outright. It is the only way to lose the cache, and it is spelled as an
    argument rather than happening by default because that cache is the
    single most expensive thing in the repository to reproduce.

    Everything else is still a clean regeneration: derived state has no
    authority of its own (§42).
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if reset_cache and db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        _ensure_preserved(con)
        for table in DERIVED_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        for statement in _DERIVED_DDL:
            con.execute(statement)
        for record in records:
            # A pdf page marker earns no index row (docs/
            # normalized-record-schema.md, "pdf page markers are not
            # paragraphs"), so this walks the real paragraphs only.
            for paragraph_number, paragraph in enumerate(
                real_paragraphs(record), start=1
            ):
                anchor = record.anchor_id(paragraph_number)
                con.execute(
                    "INSERT INTO records (src_id, anchor, source_type, text) "
                    "VALUES (?, ?, ?, ?)",
                    (record.id, anchor, record.source_type, paragraph),
                )
                con.execute(
                    "INSERT INTO paragraphs "
                    "(anchor, src_id, source_type, event_date, recorded_date, "
                    "contemporaneous, email_from, email_to) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        anchor,
                        record.id,
                        record.source_type,
                        record.event_date,
                        record.recorded_date,
                        1 if record.contemporaneous else 0,
                        record.email_from,
                        record.email_to,
                    ),
                )
        con.commit()
    finally:
        con.close()


def _ensure_preserved(con: sqlite3.Connection) -> None:
    """Create the preserved tables if they are missing, and refuse a cache
    this build cannot read.

    An index file from before #17 simply has no ``memoria_schema`` row, and
    gains an empty cache here - that is the whole migration. A file carrying
    a version this build does not know is the case that must **not** be
    guessed at: dropping a cache the author paid a model to fill is the one
    unrecoverable mistake available in this module, so it raises and names
    the flag that would do it deliberately.
    """
    for statement in _PRESERVED_DDL:
        con.execute(statement)
    row = con.execute(
        "SELECT value FROM memoria_schema WHERE key = 'memo_version'"
    ).fetchone()
    if row is None:
        con.execute(
            "INSERT INTO memoria_schema (key, value) VALUES ('memo_version', ?)",
            (MEMO_SCHEMA_VERSION,),
        )
        return
    if row[0] != MEMO_SCHEMA_VERSION:
        raise IndexSchemaError(
            f"{INDEX_RELATIVE_PATH} holds a memo cache at schema version "
            f"{row[0]!r}; this build writes {MEMO_SCHEMA_VERSION!r}. The cache "
            "holds model output and is not regenerable, so it is not discarded "
            "automatically - rebuild with --reset-cache to throw it away and "
            "re-run the extraction, or use a build that reads this version."
        )


def _check_paragraphs_shape(con: sqlite3.Connection) -> None:
    """Refuse a ``paragraphs`` table built before #111 rather than let a
    header filter surface a bare ``sqlite3.OperationalError``.

    Every earlier derived-schema change added a whole new table, which the
    ``IF NOT EXISTS`` statements below create outright. This one added
    columns to an existing table, which ``IF NOT EXISTS`` leaves exactly as
    it is - so an index built by an older version of this module still has a
    six-column ``paragraphs`` table, and the ``email_from``/``email_to``
    clauses ``filter_predicate`` emits fail with no hint of what to do about
    it. Only ``build_index`` can safely regenerate the table (it rebuilds
    every derived table together); this just names the fix.
    """
    columns = {row[1] for row in con.execute("PRAGMA table_info(paragraphs)")}
    if columns and not {"email_from", "email_to"} <= columns:
        raise IndexSchemaError(
            f"{INDEX_RELATIVE_PATH} holds a 'paragraphs' table built before "
            "the from/to header filters (#111) and is missing the "
            "'email_from'/'email_to' columns. Run `memoria rebuild` to "
            "regenerate the derived tables."
        )


def connect(repository: Repository) -> sqlite3.Connection:
    """Open the index, creating the file and every table it should have.

    The one place outside ``build_index`` that opens this database, so
    ``memoria.extraction`` does not carry a second copy of the create-or-open
    rule.

    It creates the **derived** tables as well as the preserved ones, which
    matters more than it sounds: an extraction can legitimately run on a
    repository where ``memoria rebuild`` has never been run - the pass reads
    record files, not the index - and the first thing the skill does is ask
    for a status. Without this, that call comes back as a bare "no such
    table" that the session has no way to act on. Every derived statement is
    ``IF NOT EXISTS`` for the same reason; ``build_index`` drops them first,
    so it still gets a clean regeneration rather than an update in place.
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        _ensure_preserved(con)
        for statement in _DERIVED_DDL:
            con.execute(statement)
        _check_paragraphs_shape(con)
        con.commit()
    except BaseException:
        con.close()
        raise
    return con


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
    # An empty header string is no filter at all, not a filter that matches
    # everything: `INSTR(x, "") > 0` holds for every non-null `x`, so
    # `from_=""` would have quietly narrowed a search to "every record that
    # has a `from` header" and answered as if that were the caller's
    # question. The four filters above take `None` for "not applied"; an
    # empty substring carries no more constraint than `None` does, so it is
    # treated the same way rather than raised on - nothing else in
    # `SearchFilters` validates a value, and a raise here would surface
    # through `search_text` (#12) as a bare exception.
    if filters.from_:
        clauses.append("INSTR(LOWER(paragraphs.email_from), LOWER(?)) > 0")
        params.append(filters.from_)
    if filters.to:
        clauses.append("INSTR(LOWER(paragraphs.email_to), LOWER(?)) > 0")
        params.append(filters.to)
    return " AND ".join(clauses), params


def search(
    repository: Repository,
    query: str,
    filters: SearchFilters | None = None,
    *,
    snippet: bool = False,
) -> list[SearchResult]:
    """Full-text search the index, returning matching records with their
    ``SRC-`` ID and the paragraph anchor that matched, ranked by relevance.

    Takes the frozen ``Repository`` value, like every other core read
    (ADR-0004), rather than a bare ``db_path`` - #74 and #81 inherit this
    shape.

    ``filters`` narrows by event date, recorded date, source type,
    contemporaneous/retrospective and the ``from``/``to`` header strings
    (``SearchFilters``); all compose. Applied in the core so one predicate
    builder serves every caller - the MCP tool (#12), the web API (#64) and
    cross-layer search (#24) - without a second, divergent copy in any of
    them (§40.1). A caller still chooses which filters it exposes: the MCP
    tool passes a whole ``SearchFilters``, while #64's route enumerates the
    original four query params and does not yet pass ``from_``/``to``.

    ``snippet`` is opt-in and off by default, so a hit carries identifiers
    and nothing else unless a caller asks otherwise (#95). It is a match
    locator rather than evidence - see ``SearchResult`` - which is why the
    default is off: ``search_text`` (#12) leaves it off and keeps rendering
    and ledgering anchors alone, and the web adapter turns it on to draw the
    search dialog's hit rows (part 19 §19.8). No caller gets paragraph text
    out of this function; that is what ``read(ref)`` is for.

    A missing index - every fresh clone, since ``.memoria/`` is gitignored -
    returns no results rather than raising or creating the database file:
    "the corpus is not built" is an answer, not a driver exception.
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        _check_paragraphs_shape(con)
        predicate, predicate_params = filter_predicate(filters)
        # The snippet is computed by FTS5 over the row it already matched,
        # in the query that already runs - it costs a column, not a second
        # pass and not a file read.
        columns = "records.src_id, records.anchor, records.source_type"
        params: list = []
        if snippet:
            columns += ", snippet(records, ?, ?, ?, ?, ?)"
            params.extend(
                [
                    _SNIPPET_TEXT_COLUMN,
                    SNIPPET_MATCH_START,
                    SNIPPET_MATCH_END,
                    SNIPPET_ELLIPSIS,
                    SNIPPET_TOKENS,
                ]
            )
        sql = (
            f"SELECT {columns} "
            "FROM records JOIN paragraphs ON paragraphs.anchor = records.anchor "
            "WHERE records MATCH ?"
        )
        params.append(query)
        if predicate:
            sql += f" AND {predicate}"
            params.extend(predicate_params)
        sql += " ORDER BY rank"
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [
        SearchResult(
            src_id=r[0],
            anchor=r[1],
            source_type=r[2],
            snippet=r[3] if snippet else None,
        )
        for r in rows
    ]


def rebuild(
    repository: Repository,
    *,
    recurrence_threshold: int | None = None,
    reset_cache: bool = False,
) -> RebuildReport:
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

    It now also runs the extraction's **derive** step (#17), which recomputes
    placements, candidates, relations and clusters from the memo cache plus
    the entries' current match terms. That step calls no model: accepting a
    proposed match term changes what is placed here without re-reading a
    single paragraph, which is the whole point of leaving match terms out of
    the memo key (part 06 §8.12).

    **It does not promote anything.** Auto-promotion materializes durable
    entry files and commits them, and it belongs to the author-launched pass
    (``extraction.finish_pass``), never to a command whose contract is that
    everything it touches is disposable. This function never names
    ``auto_promote``, and a test holds that.
    """
    started = time.monotonic()
    records = read_all(repository)
    build_index(repository, records, reset_cache=reset_cache)
    # Imported here rather than at module scope: `memoria.extraction` imports
    # this module for the schema and the connection, so the module-level
    # direction has to stay one-way. Nothing else is fetched from it - an
    # absent threshold is left to `derive`'s own default rather than copied.
    from memoria import extraction

    if recurrence_threshold is None:
        counts = extraction.derive(repository)
    else:
        counts = extraction.derive(
            repository, recurrence_threshold=recurrence_threshold
        )
    appearances_report = compute_appearances(repository)
    return RebuildReport(
        records=records,
        counts=counts,
        appearances=appearances_report,
        elapsed_seconds=time.monotonic() - started,
    )


# --- the gathered set and its pin/exclude overlay (#18, #21, part 06 §8.3) --


@dataclass(frozen=True)
class GatheredSource:
    """One paragraph in an entry's gathered set.

    The gathered set itself has no stable ID - it asserts nothing, so
    nothing outside this function ever needs to name one (§8.3's sixth
    criterion). ``anchor`` is what is already addressable, and it is enough:
    a caller that wants to read the evidence reads it through ``read(ref)``.
    """

    src_id: str
    anchor: str
    pinned: bool = False


@dataclass(frozen=True)
class OverlayEntry:
    """One row of the pin/exclude overlay - the attributed act, not the
    resulting membership. ``memoria validate`` reads these to check that
    every row carries attribution."""

    entry_id: str
    anchor: str
    action: str
    actor_name: str
    actor_email: str
    at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record_overlay(
    repository: Repository, entry_id: str, anchor: str, action: str, actor: Actor
) -> None:
    """Durably record one pin or exclusion on ``entry_id``'s own file,
    through the write path (ADR-0003) - not in this index at all (#21). A
    later act against the same ``anchor`` replaces the earlier one; the row
    order is by ``anchor`` so the file is stable to diff.

    Refuses an unattributed ``actor`` outright, before the file is touched
    at all. Relying on ``write_file``'s commit to catch this (it refuses an
    empty git author identity) is not enough: ``_replace_atomically`` runs
    *before* the commit, so the unattributed act would land on disk and be
    staged even though the commit that was supposed to attribute it never
    happens - a partially-applied durable write, exactly what part 04 §3's
    write path exists to rule out.
    """
    if not actor.name.strip() or not actor.email.strip():
        raise WriteError(
            f"cannot record {action} of {anchor} on {entry_id}: an author "
            "act must be attributed - actor name and email may not be "
            "empty"
        )
    subject_id, entry_slug = entry_id.split("/", 1)
    path = find_entry_path(repository, subject_id, entry_slug)
    if path is None:
        raise SubjectError(f"no such entry: {entry_id}")
    relative_path = path.relative_to(repository.root).as_posix()

    served = serve(repository, relative_path)
    entry = parse_entry(served.text, source=relative_path)
    overlay = sorted(
        [act for act in entry.overlay if act.anchor != anchor]
        + [
            OverlayAct(
                anchor=anchor,
                action=action,
                actor_name=actor.name,
                actor_email=actor.email,
                at=_now(),
            )
        ],
        key=lambda act: act.anchor,
    )
    content = entry_to_markdown(dataclass_replace(entry, overlay=overlay))

    result = write_file(repository, relative_path, served.token, content, actor)
    if isinstance(result, Rejected):
        raise WriteError(
            f"cannot record {action} of {anchor} on {entry_id}: "
            f"{relative_path} changed since it was read"
        )


def pin(repository: Repository, entry_id: str, anchor: str, actor: Actor) -> None:
    """Author act: ``anchor`` stays in ``entry_id``'s gathered set regardless
    of what the matching pass finds (part 06 §8.3's overlay).

    Recorded on the entry file itself (``memoria.subjects.OverlayAct``), not
    in the index (#21) - part 04 §42 requires a pin to survive
    ``.memoria/`` being deleted outright, not merely a ``memoria rebuild``
    against it, and only a durable, committed file can promise that.

    Overwrites a prior pin or exclusion of the same source against the same
    entry, attributed and timestamped to this call - the author's later act
    supersedes their earlier one rather than stacking a history of them,
    the same shape as a settlement (§8.7).
    """
    _record_overlay(repository, entry_id, anchor, "pin", actor)


def exclude(repository: Repository, entry_id: str, anchor: str, actor: Actor) -> None:
    """Author act: ``anchor`` stays out of ``entry_id``'s gathered set even
    if the matching pass would otherwise include it. See ``pin``."""
    _record_overlay(repository, entry_id, anchor, "exclude", actor)


def list_overlay(repository: Repository) -> list[OverlayEntry]:
    """Every pin/exclude row across every entry, read off the entry files
    themselves (#21).

    Only ``memoria validate``'s attribution check needs every row at once;
    ``gather`` reads its own entry's rows directly, off the ``Entry`` it
    already loaded.
    """
    return sorted(
        (
            OverlayEntry(
                entry_id=entry_id,
                anchor=act.anchor,
                action=act.action,
                actor_name=act.actor_name,
                actor_email=act.actor_email,
                at=act.at,
            )
            for entry_id, entry in load_all_entries(repository).items()
            for act in entry.overlay
        ),
        key=lambda row: (row.entry_id, row.anchor),
    )


def _lexical_match(con: sqlite3.Connection, term: str) -> list[str]:
    """Anchors whose paragraph text contains ``term`` - the deterministic
    lexical pass part 06 §8.3 says gathering "stays" as, over and above
    whatever the extraction placed. Quoted as an FTS5 phrase so a term with
    more than one word, or one that happens to collide with FTS5 query
    syntax, is still matched literally.

    Scoped away from ``source_type: book`` paragraphs - the inverse of
    ``_lexical_match_book``'s scoping - because those are audit targets
    (docs/normalized-record-schema.md: "never evidence to write from"), and
    §8.11 keeps the gathered set and appearances "separately queryable and
    never cross": a book paragraph an appearance names must not also surface
    through gather's own lexical pass."""
    query = '"' + term.replace('"', '""') + '"'
    return [
        row[0]
        for row in con.execute(
            "SELECT records.anchor FROM records "
            "JOIN paragraphs ON paragraphs.anchor = records.anchor "
            "WHERE records MATCH ? AND paragraphs.source_type != 'book'",
            (query,),
        )
    ]


def gather(repository: Repository, entry_id: str) -> list[GatheredSource]:
    """The gathered set (part 06 §8.3): every paragraph this entry's subject
    matched, plus the author's pin/exclude overlay.

    No model call, ever: ``memoria.extraction.derive`` already ran whatever
    reading a model call needed and left its verdict in ``placements`` and
    ``relations``; this only recombines what is already durable or already
    in the index, over three sources unioned by anchor:

    - ``placements`` already licensed under ``entry_id`` - built from the
      entry's *word*-shaped match terms plus its implicit name
      (``memoria.extraction._licensing_terms``);
    - a direct lexical match against each of the entry's own word-shaped
      match terms, the deterministic pass that gathering "stays" as (§8.3) -
      catching a literal mention the model missed, which is the recall this
      module's docstring calls the design's central risk. Scoped away from
      ``source_type: book`` paragraphs (``_lexical_match``): those are audit
      targets, appearances' side of the §8.11 separation, and must never
      cross into the gathered set;
    - for the ``entry``- and ``relation``-shaped match terms together, the
      **intersection** of what each one names - the placements rows for
      every named entry and the relations rows for every named relation.
      This is how a Theme or Arc promoted from a cluster gathers (ADR-0005,
      2026-09-01 amendment): its match terms are the entries and relations
      that defined the cluster, and the intersection is what makes the
      result "exactly the paragraphs where those co-occur" rather than
      every paragraph any one of them appears in alone. A Theme with only
      one such match term still gets that term's own anchors, since an
      intersection of one set is itself. ``extraction.read_placements``
      deliberately does not consult these two shapes - a Theme is never
      itself placed - so this function is the only place they are.

    Word-shaped match terms stay unioned in, both with each other and with
    the entry/relation intersection above: they are a separate recall
    mitigation (the literal mention above), not a claim about co-occurrence.

    Then the overlay: an excluded anchor is dropped even if matched above,
    and a pinned one is added even if nothing above found it.

    Ordered by anchor for a stable, reproducible result. A missing index -
    every fresh clone - returns no results, matching ``search``.
    """
    entry = load_entry(repository, *entry_id.split("/", 1))

    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        return []
    con = connect(repository)
    try:
        anchors: set[str] = {
            row[0]
            for row in con.execute(
                "SELECT anchor FROM placements WHERE entry_id = ?", (entry_id,)
            )
        }
        # Entry/relation-shaped match terms are intersected with each other
        # (co-occurrence), then unioned into `anchors` alongside the
        # word-shaped terms' lexical matches - see the docstring.
        cooccurrence: set[str] | None = None
        for term in entry.match_terms:
            kind = classify_match_term(term)
            if kind == "word":
                anchors.update(_lexical_match(con, term))
            elif kind == "entry":
                term_anchors = {
                    row[0]
                    for row in con.execute(
                        "SELECT anchor FROM placements WHERE entry_id = ?", (term,)
                    )
                }
                cooccurrence = (
                    term_anchors
                    if cooccurrence is None
                    else cooccurrence & term_anchors
                )
            else:  # "relation"
                left, verb, right = (part.strip() for part in term.split(" -> "))
                term_anchors = {
                    row[0]
                    for row in con.execute(
                        "SELECT anchor FROM relations "
                        "WHERE from_ref = ? AND verb = ? AND to_ref = ?",
                        (left, verb, right),
                    )
                }
                cooccurrence = (
                    term_anchors
                    if cooccurrence is None
                    else cooccurrence & term_anchors
                )
        if cooccurrence:
            anchors.update(cooccurrence)

        # The overlay lives on the entry itself (#21), already loaded above
        # - no query against this index needed.
        overlay = {act.anchor: act.action for act in entry.overlay}
        for anchor, action in overlay.items():
            if action == "exclude":
                anchors.discard(anchor)
            else:
                anchors.add(anchor)

        if not anchors:
            return []
        placeholders = ",".join("?" for _ in anchors)
        rows = con.execute(
            f"SELECT anchor, src_id FROM paragraphs WHERE anchor IN ({placeholders})",
            tuple(anchors),
        ).fetchall()
    finally:
        con.close()

    pinned = {anchor for anchor, action in overlay.items() if action == "pin"}
    return sorted(
        (
            GatheredSource(src_id=src_id, anchor=anchor, pinned=anchor in pinned)
            for anchor, src_id in rows
        ),
        key=lambda gathered: gathered.anchor,
    )


@dataclass(frozen=True)
class ReadOverlay:
    """The curated overlay a decorated evidence read carries (#20, part 06
    §8.3 / ``poc-plan.md`` §7): which entries this paragraph is currently
    gathered into, which entries have excluded it, and which settlements
    cite it.

    ``citing_settlements`` is always empty in this build. Settlements are an
    M4 concept (``docs/plan/16-build-order.md``) with no durable storage yet
    to query - the field exists now so the overlay's shape does not change
    again when M4 lands one.
    """

    entry_links: list[str]
    exclusions: list[str]
    citing_settlements: list[str]


def overlay_for_anchor(repository: Repository, anchor: str) -> ReadOverlay | None:
    """The curated overlay for one paragraph's anchor (#20).

    ``entry_links`` is the **gathered-set-inverse**: every entry currently
    on disk whose ``gather`` result includes this anchor - the same word-,
    entry- and relation-shaped recall ``gather`` runs for a placement's
    intended entry, and the same pin/exclude overlay it applies, just read
    backwards from the anchor rather than forward from one entry. A
    placements-only version under-reports exactly the recall ``gather``
    itself exists to mitigate (part 06 §8.3's "central risk"), so this calls
    ``gather`` once per entry rather than duplicating its matching logic - a
    second, drifting copy of that logic would be worse than the extra
    queries.

    ``exclusions`` names every entry that has excluded this anchor, whether
    or not it was otherwise gathered - the curator act itself, not just its
    effect on membership.

    Both are scoped to ``load_all_entries`` - entries actually on disk -
    rather than to whatever ``placements``/``gather_overlay`` happen to
    still name, so a deleted or renamed entry never surfaces from a stale
    index.

    Returns an empty overlay when there is no index yet (no ``memoria
    rebuild`` has run), the same no-index behaviour ``search`` and
    ``gather`` already give. Returns ``None`` - never raises - when the
    index exists but cannot be read right now: a schema older than this
    build (``IndexSchemaError``) or a concurrent writer holding it locked
    (``sqlite3.Error``). The overlay is best-effort decoration; the
    paragraph's own verbatim text is never conditioned on it, so a caller
    degrades to an undecorated read rather than losing the read entirely -
    ``poc-plan.md`` §7's verbatim-text guarantee may not weaken, and
    decorating it was never license to.
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        return ReadOverlay(entry_links=[], exclusions=[], citing_settlements=[])
    try:
        con = connect(repository)
        try:
            excluded_rows = con.execute(
                "SELECT entry_id FROM gather_overlay "
                "WHERE anchor = ? AND action = 'exclude'",
                (anchor,),
            ).fetchall()
        finally:
            con.close()
        entries = load_all_entries(repository)
        entry_links = sorted(
            entry_id
            for entry_id in entries
            if any(g.anchor == anchor for g in gather(repository, entry_id))
        )
    except (IndexSchemaError, sqlite3.Error):
        return None
    exclusions = sorted(
        entry_id for (entry_id,) in excluded_rows if entry_id in entries
    )
    return ReadOverlay(
        entry_links=entry_links, exclusions=exclusions, citing_settlements=[]
    )


# --- appearances, lexical engine only (#19, part 06 §8.11) ------------------


@dataclass(frozen=True)
class Appearance:
    """One manuscript passage an entry turns out to touch, with a short note
    on how (part 06 §8.11). ``note`` names the match term that found it -
    ``placements.licensed_by``'s shape, not a model judgement: there is no
    model in this engine.

    Carries no pin/exclude flag - unlike ``GatheredSource`` - because
    appearances take no overlay at all (§8.11's third property: an author act
    against one passage would be a durable pointer into mutable prose)."""

    src_id: str
    anchor: str
    note: str


@dataclass(frozen=True)
class AppearancesReport:
    """What one ``compute_appearances`` pass produced, and what it could not.

    Themes and Arcs cannot appear yet (§8.11: manuscript prose is never
    extracted, so there is nothing to intersect their entry/relation match
    terms against), and #19's seventh acceptance criterion is that this gap
    is *reported*, not folded silently into an empty result - a caller adds
    ``entries_skipped`` and ``skipped_subjects`` to a candidate list report
    the same way ``DerivedCounts`` already reports the recurrence filter's
    cost.
    """

    appearances: int
    entries_computed: int
    entries_skipped: int
    skipped_subjects: tuple[str, ...]


def _appearance_note(term: str) -> str:
    return f'matched "{term}"'


def _lexical_match_book(con: sqlite3.Connection, term: str) -> list[str]:
    """Anchors among the audit targets (``source_type: book``) whose
    paragraph text contains ``term`` verbatim - ``_lexical_match``'s FTS5
    phrase query, scoped to book paragraphs the way ``paragraphs.source_type``
    already lets ``search`` scope by kind (docs/normalized-record-schema.md:
    ``book`` marks an audit target)."""
    query = '"' + term.replace('"', '""') + '"'
    return [
        row[0]
        for row in con.execute(
            "SELECT records.anchor FROM records "
            "JOIN paragraphs ON paragraphs.anchor = records.anchor "
            "WHERE records MATCH ? AND paragraphs.source_type = 'book'",
            (query,),
        )
    ]


def compute_appearances(repository: Repository) -> AppearancesReport:
    """Recompute the ``appearances`` table: every audit-target passage a
    lexically-matchable entry's word-shaped match terms - or its own
    implicit name - find, stored with a note naming the term.

    This is the lexical engine part 06 §8.11 says appearances share with the
    gathered set - "an appearance is a match... using the same lexical
    machinery" - but it cannot reuse ``gather``'s ``placements``/``relations``
    union, because the extraction never reads audit targets (only evidence
    records), so those tables carry no rows for a book paragraph to begin
    with. What is left is the deterministic lexical pass alone, run directly
    against book paragraphs.

    Entries under ``memoria.extraction.CO_OCCURRENCE_SUBJECTS`` (Themes,
    Arcs) are skipped rather than matched on nothing: their match terms name
    entries and relations, and appearances has no placements over the
    manuscript to intersect those against (the same reason ``gather``'s
    co-occurrence branch cannot run here either). The skip is counted and
    named in the returned report - #19's seventh acceptance criterion - not
    silently absorbed into zero appearances.

    Stored in the ``appearances`` table and never merged into the gathered
    set (§8.11): the two stay separately queryable by construction, since
    nothing here writes to ``placements`` or ``relations``, and ``gather``
    never reads this table. Nothing here writes to an entry file either
    (unlike ``pin``/``exclude``, #21) - appearances are read-only about the
    manuscript, never fed back into it.

    Regenerated identically on every call: existing rows are dropped and
    recomputed from the entries and audit-target paragraphs currently on
    disk, the same throwaway contract every other derived table in this file
    keeps (§42).
    """
    # Imported here, not at module scope, for the same reason `rebuild` does
    # it: `memoria.extraction` imports this module, so the reverse import
    # must stay local to avoid a cycle.
    from memoria.extraction import CO_OCCURRENCE_SUBJECTS, implicit_name_term

    entries = load_all_entries(repository)
    con = connect(repository)
    try:
        con.execute("DELETE FROM appearances")
        computed = 0
        skipped = 0
        skipped_subjects: set[str] = set()
        for entry_id, entry in sorted(entries.items()):
            subject_id = entry_id.split("/", 1)[0]
            if subject_id in CO_OCCURRENCE_SUBJECTS:
                skipped += 1
                skipped_subjects.add(subject_id)
                continue

            terms = {implicit_name_term(entry_id)}
            for term in entry.match_terms:
                if classify_match_term(term) == "word":
                    terms.add(term)

            # Each anchor gets one note, from the first (alphabetically) term
            # that matched it - deterministic, and enough to say how it was
            # found without a row per matching term.
            matched: dict[str, str] = {}
            for term in sorted(terms):
                for anchor in _lexical_match_book(con, term):
                    matched.setdefault(anchor, term)

            for anchor, term in matched.items():
                con.execute(
                    "INSERT INTO appearances (entry_id, anchor, note) "
                    "VALUES (?, ?, ?)",
                    (entry_id, anchor, _appearance_note(term)),
                )
                computed += 1
        con.commit()
    finally:
        con.close()

    return AppearancesReport(
        appearances=computed,
        entries_computed=len(entries) - skipped,
        entries_skipped=skipped,
        skipped_subjects=tuple(sorted(skipped_subjects)),
    )


def list_appearances(repository: Repository, entry_id: str) -> list[Appearance]:
    """One entry's appearances, read back from the ``appearances`` table -
    the query side of ``compute_appearances``. Ordered by anchor, matching
    ``gather``'s ordering.

    A missing index - every fresh clone - returns no results, matching
    ``gather`` and ``search``."""
    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        return []
    con = connect(repository)
    try:
        rows = con.execute(
            "SELECT paragraphs.src_id, appearances.anchor, appearances.note "
            "FROM appearances JOIN paragraphs "
            "ON paragraphs.anchor = appearances.anchor "
            "WHERE appearances.entry_id = ? "
            "ORDER BY appearances.anchor",
            (entry_id,),
        ).fetchall()
    finally:
        con.close()
    return [Appearance(src_id=src_id, anchor=anchor, note=note) for src_id, anchor, note in rows]
