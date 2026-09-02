import dataclasses
import sqlite3
import time
from datetime import datetime

import pytest

from memoria import extraction as ex
from memoria.index import (
    INDEX_RELATIVE_PATH,
    SNIPPET_ELLIPSIS,
    SNIPPET_MATCH_END,
    SNIPPET_MATCH_START,
    Appearance,
    GatheredSource,
    SearchFilters,
    build_index,
    compute_appearances,
    exclude,
    filter_predicate,
    gather,
    list_appearances,
    list_overlay,
    pin,
    rebuild,
    search,
)
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown
from memoria.write import Actor


def _record(
    record_id,
    paragraphs,
    source_type="journal",
    event_date="Oct. 22.",
    recorded_date="Oct. 22.",
    contemporaneous=True,
    email_from=None,
    email_to=None,
):
    return NormalizedRecord(
        id=record_id,
        source_type=source_type,
        recorded_date=recorded_date,
        event_date=event_date,
        date_confidence="unresolved",
        contemporaneous=contemporaneous,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=paragraphs,
        email_from=email_from,
        email_to=email_to,
    )


def _index(tmp_path, records):
    repository = Repository(root=tmp_path)
    build_index(repository, records)
    return repository


def test_search_finds_a_record_by_its_paragraph_text(tmp_path):
    records = [_record("SRC-000001", ["The fox ran through the woods."])]
    repository = _index(tmp_path, records)

    results = search(repository, "fox")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000001"


def test_search_returns_the_specific_paragraph_anchor_that_matched(tmp_path):
    records = [
        _record(
            "SRC-000002",
            ["First paragraph, no match here.", "Second paragraph mentions a badger."],
        )
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "badger")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000002"
    assert results[0].anchor == "src-000002-p2"


def test_build_index_skips_page_markers(tmp_path):
    """A pdf page marker earns no index row and shifts no anchor
    (docs/normalized-record-schema.md, "pdf page markers are not
    paragraphs") - the marker between the two real paragraphs here must not
    become a phantom p2 that pushes the second real paragraph to p3."""
    records = [
        _record(
            "SRC-000003",
            ["Page one paragraph.", "<!-- page 2 -->", "Page two paragraph."],
        )
    ]
    repository = _index(tmp_path, records)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    rows = con.execute("SELECT anchor, text FROM records ORDER BY anchor").fetchall()
    con.close()

    assert rows == [
        ("src-000003-p1", "Page one paragraph."),
        ("src-000003-p2", "Page two paragraph."),
    ]


def test_search_does_not_match_a_page_marker(tmp_path):
    records = [
        _record("SRC-000004", ["Real text.", "<!-- page 2 -->", "More real text."])
    ]
    repository = _index(tmp_path, records)

    assert search(repository, "page") == []


def test_search_over_a_missing_index_returns_no_results_rather_than_raising(tmp_path):
    """A fresh clone has no `.memoria/index.db` - `.memoria/` is gitignored.

    That is the state of every fresh clone, not an error: the corpus not
    being built yet is an answer, not a driver exception.
    """
    repository = Repository(root=tmp_path)

    assert search(repository, "fox") == []
    assert not (tmp_path / INDEX_RELATIVE_PATH).exists()


def test_search_filters_by_source_type(tmp_path):
    records = [
        _record("SRC-000003", ["He saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "heron", SearchFilters(source_type="journal"))

    assert [r.src_id for r in results] == ["SRC-000003"]


def test_search_with_no_filters_returns_everything_that_matches(tmp_path):
    records = [
        _record("SRC-000003", ["He saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "heron")

    assert {r.src_id for r in results} == {"SRC-000003", "SRC-000004"}


def test_a_retrospective_excluded_search_returns_the_evidence_and_not_the_annotation(
    tmp_path,
):
    """§6's temporal discipline enforced at retrieval: `contemporaneous=False`
    filters out later editorial commentary added over the same ground."""
    records = [
        _record(
            "SRC-000003",
            ["He saw a heron by the pond."],
            source_type="journal",
            contemporaneous=True,
        ),
        _record(
            "SRC-000004",
            ["The editor notes, years later, that a heron was a common sight."],
            source_type="editorial",
            contemporaneous=False,
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "heron", SearchFilters(contemporaneous=True))

    assert [r.src_id for r in results] == ["SRC-000003"]


def test_search_filters_by_event_date(tmp_path):
    records = [
        _record("SRC-000005", ["A fox in October."], event_date="Oct. 22., 1845"),
        _record("SRC-000006", ["A fox in November."], event_date="Nov. 3., 1845"),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "fox", SearchFilters(event_date="Oct. 22., 1845"))

    assert [r.src_id for r in results] == ["SRC-000005"]


def test_search_filters_by_recorded_date(tmp_path):
    records = [
        _record("SRC-000007", ["A fox recorded in October."], recorded_date="Oct. 22."),
        _record("SRC-000008", ["A fox recorded in November."], recorded_date="Nov. 3."),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "fox", SearchFilters(recorded_date="Oct. 22."))

    assert [r.src_id for r in results] == ["SRC-000007"]


def test_search_filters_compose(tmp_path):
    records = [
        _record(
            "SRC-000009",
            ["A fox by the journal."],
            source_type="journal",
            event_date="Oct. 22., 1845",
            contemporaneous=True,
        ),
        _record(
            "SRC-000010",
            ["A fox by the editor."],
            source_type="editorial",
            event_date="Oct. 22., 1845",
            contemporaneous=False,
        ),
        _record(
            "SRC-000011",
            ["A fox on a different day."],
            source_type="journal",
            event_date="Nov. 3., 1845",
            contemporaneous=True,
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(
        repository,
        "fox",
        SearchFilters(
            source_type="journal", event_date="Oct. 22., 1845", contemporaneous=True
        ),
    )

    assert [r.src_id for r in results] == ["SRC-000009"]


def test_build_index_writes_the_header_strings_into_paragraphs(tmp_path):
    """#111: `from`/`to` are written into the plain `paragraphs` table so the
    predicate needs no join into the FTS5 table and no record file read."""
    records = [
        _record(
            "SRC-000012",
            ["A message about a heron."],
            email_from="Dave Perrino <dperrino@example.com>",
            email_to="Diana Scholtes",
        )
    ]
    repository = _index(tmp_path, records)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    row = con.execute(
        "SELECT email_from, email_to FROM paragraphs WHERE anchor = ?",
        ("src-000012-p1",),
    ).fetchone()
    con.close()

    assert row == ("Dave Perrino <dperrino@example.com>", "Diana Scholtes")


def test_search_filters_by_from_case_insensitive_substring(tmp_path):
    records = [
        _record(
            "SRC-000015",
            ["A message about a heron."],
            email_from="Dave Perrino <dperrino@example.com>",
        ),
        _record(
            "SRC-000016",
            ["Another message about a heron."],
            email_from="Diana Scholtes <dscholtes@example.com>",
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "heron", SearchFilters(from_="perrino"))

    assert [r.src_id for r in results] == ["SRC-000015"]


def test_search_filters_by_to_case_insensitive_substring(tmp_path):
    records = [
        _record(
            "SRC-000017",
            ["A message about a heron."],
            email_to="Diana Scholtes <dscholtes@example.com>",
        ),
        _record(
            "SRC-000018",
            ["Another message about a heron."],
            email_to="Sean Crandall <scrandall@example.com>",
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(repository, "heron", SearchFilters(to="scholtes"))

    assert [r.src_id for r in results] == ["SRC-000017"]


def test_search_from_and_to_filters_compose_with_each_other(tmp_path):
    """The shape the M1 gate walk (#15) observed: "messages from X to Y" -
    built from three email records, a query that matches every body, and
    both header filters - gets exactly the one record's anchors back."""
    records = [
        _record(
            "SRC-000019",
            ["Perrino wrote to Scholtes about the pond."],
            email_from="Dave Perrino <dperrino@example.com>",
            email_to="Diana Scholtes <dscholtes@example.com>",
        ),
        _record(
            "SRC-000020",
            ["Perrino wrote to Crandall about the pond."],
            email_from="Dave Perrino <dperrino@example.com>",
            email_to="Sean Crandall <scrandall@example.com>",
        ),
        _record(
            "SRC-000021",
            ["Semperger wrote to Scholtes about the pond."],
            email_from="Cara Semperger <csemperger@example.com>",
            email_to="Diana Scholtes <dscholtes@example.com>",
        ),
    ]
    repository = _index(tmp_path, records)

    results = search(
        repository, "pond", SearchFilters(from_="perrino", to="scholtes")
    )

    assert [r.src_id for r in results] == ["SRC-000019"]
    assert [r.anchor for r in results] == ["src-000019-p1"]


def test_a_non_email_record_does_not_match_a_from_or_to_filter(tmp_path):
    """`email_from`/`email_to` are `None` on a non-email record - `INSTR`
    over a `NULL` column is `NULL`, so the row is excluded rather than
    matching every filter value."""
    records = [_record("SRC-000022", ["A fox by the pond, no email header."])]
    repository = _index(tmp_path, records)

    assert search(repository, "fox", SearchFilters(from_="perrino")) == []
    assert search(repository, "fox", SearchFilters(to="scholtes")) == []


def test_filter_predicate_is_reusable_by_a_query_that_is_not_fts5(tmp_path):
    """#74 joins cluster membership, #81 joins a vector search - neither is
    an FTS5 query. The same predicate builder must serve a plain SELECT
    against the ``paragraphs`` table directly."""
    records = [
        _record("SRC-000013", ["Evidence."], source_type="journal"),
        _record("SRC-000014", ["Commentary."], source_type="editorial"),
    ]
    repository = _index(tmp_path, records)

    predicate, params = filter_predicate(SearchFilters(source_type="journal"))
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    try:
        rows = con.execute(
            f"SELECT src_id FROM paragraphs WHERE {predicate}", params
        ).fetchall()
    finally:
        con.close()

    assert [r[0] for r in rows] == ["SRC-000013"]


def test_results_feed_straight_into_read_with_no_reconstruction(tmp_path):
    from memoria import references

    records = [_record("SRC-000012", ["A fox by the pond."])]
    repository = _index(tmp_path, records)

    (hit,) = search(repository, "fox")

    reference = references.parse(hit.anchor)
    assert reference.record_id == hit.src_id


def test_rebuild_regenerates_an_index_deleted_from_disk(tmp_path):
    """§42: derived state carries no authority and can always be thrown away.

    The contract survives the retirement of the corpus even though no
    normalizer feeds it any more (docs/open-problems.md 2.4).
    """
    from memoria.records import NORMALIZED_RELATIVE_PATH, write_normalized_records

    records = [
        NormalizedRecord(
            id="SRC-000184",
            source_type="journal",
            recorded_date="Oct. 22.",
            event_date="Oct. 22., 1845",
            date_confidence="inferred",
            contemporaneous=True,
            original_file="raw/vol-01/text.txt",
            original_locator="Journal I, entry dated Oct. 22.",
            paragraphs=["A blue heron flew over."],
        )
    ]
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)

    repository = Repository(root=tmp_path)
    rebuild(repository)
    db_path = tmp_path / INDEX_RELATIVE_PATH
    before = [(r.src_id, r.anchor) for r in search(repository, "heron")]
    assert before

    db_path.unlink()
    rebuild(repository)

    assert [(r.src_id, r.anchor) for r in search(repository, "heron")] == before


def test_rebuild_reports_no_records_when_none_exist(tmp_path):
    """With no corpus chosen there is nothing to index, and that is not an
    error - it is the honest state."""
    assert rebuild(Repository(root=tmp_path)).records == []


def test_search_over_the_full_corpus_returns_well_under_a_second(tmp_path):
    records = [
        _record(
            f"SRC-{n:06d}",
            [f"Paragraph {n} mentions a heron by the pond."],
            email_from="Dave Perrino <dperrino@example.com>",
            email_to="Diana Scholtes <dscholtes@example.com>",
        )
        for n in range(1, 2001)
    ]
    repository = _index(tmp_path, records)

    start = time.monotonic()
    results = search(
        repository, "heron", SearchFilters(from_="perrino", to="scholtes")
    )
    elapsed = time.monotonic() - start

    assert results
    assert elapsed < 0.5


# --- the snippet: a match locator, not evidence (#95) -----------------------


def test_a_hit_carries_no_snippet_unless_one_is_asked_for(tmp_path):
    """Off by default, so `search_text` and every existing caller are
    unchanged: a hit is identifiers and nothing else."""
    repository = _index(tmp_path, [_record("SRC-000184", ["A blue heron flew over."])])

    (hit,) = search(repository, "heron")

    assert hit.snippet is None
    assert (hit.src_id, hit.anchor, hit.source_type) == (
        "SRC-000184",
        "src-000184-p1",
        "journal",
    )


def test_a_snippet_marks_the_match_and_truncates_the_paragraph(tmp_path):
    """A fragment with the matched term marked - the line `grep` prints, not
    the paragraph. A snippet that came back whole would be a quotation."""
    paragraph = " ".join(
        ["The pond was still."] * 10
        + ["A blue heron flew over."]
        + ["The far bank was hidden."] * 10
    )
    repository = _index(tmp_path, [_record("SRC-000184", [paragraph])])

    (hit,) = search(repository, "heron", snippet=True)

    assert f"{SNIPPET_MATCH_START}heron{SNIPPET_MATCH_END}" in hit.snippet
    assert SNIPPET_ELLIPSIS in hit.snippet
    assert paragraph not in hit.snippet


def test_the_snippet_marks_cannot_collide_with_evidence(tmp_path):
    """The marks are C0 controls precisely so a paragraph cannot contain
    them - brackets, the obvious alternative, are real editorial syntax."""
    paragraph = "A blue heron [sic] flew over <mark>the pond</mark>."
    repository = _index(tmp_path, [_record("SRC-000184", [paragraph])])

    (hit,) = search(repository, "heron", snippet=True)

    assert hit.snippet.count(SNIPPET_MATCH_START) == 1
    assert hit.snippet.count(SNIPPET_MATCH_END) == 1


def test_a_snippet_does_not_change_which_rows_match(tmp_path):
    """Asking for a snippet is a column, not a different search - the same
    hits in the same order, with the filters still applied."""
    records = [
        _record("SRC-000001", ["A heron by the pond."], source_type="journal"),
        _record("SRC-000002", ["A heron, the editor notes."], source_type="editorial"),
    ]
    repository = _index(tmp_path, records)
    filters = SearchFilters(source_type="journal")

    thin = search(repository, "heron", filters)
    with_snippet = search(repository, "heron", filters, snippet=True)

    assert [(r.src_id, r.anchor) for r in with_snippet] == [
        (r.src_id, r.anchor) for r in thin
    ]
    assert all(r.snippet for r in with_snippet)


# --- the rebuild rule (#17) --------------------------------------------------


def _tables(repository):
    from memoria.index import INDEX_RELATIVE_PATH

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    try:
        return {
            name
            for name, in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        con.close()


def test_every_table_is_either_preserved_or_derived(tmp_path):
    """The rebuild rule, as a closed set.

    `build_index` drops `DERIVED_TABLES` by name and leaves `PRESERVED_TABLES`
    alone, so a table in neither list is silently outside the rule - it would
    survive a rebuild without anyone having decided it should. That is the
    failure worth catching, and it is the one a test of "the cache survives"
    would miss entirely.
    """
    from memoria.index import DERIVED_TABLES, PRESERVED_TABLES

    repository = _index(tmp_path, [_record("SRC-000001", ["A paragraph."])])

    named = set(PRESERVED_TABLES) | set(DERIVED_TABLES)
    # FTS5 keeps its own shadow tables beside the virtual table; they are
    # SQLite's, not ours, and are dropped with their parent.
    ours = {name for name in _tables(repository) if not name.startswith("records_")}
    assert ours == named


def test_rebuild_regenerates_the_fts5_table_without_orphan_shadow_tables(tmp_path):
    """`build_index` used to delete the whole file, which regenerated the FTS5
    virtual table for free. It cannot any more - the memo cache lives in that
    file - so the shadow tables are now dropped by `DROP TABLE records`
    instead, and this is the check that they really are."""
    records = [_record("SRC-000001", ["The fox ran through the woods."])]
    repository = _index(tmp_path, records)
    build_index(repository, records)
    build_index(repository, records)

    shadows = {name for name in _tables(repository) if name.startswith("records_")}
    assert shadows == {
        "records_data",
        "records_idx",
        "records_content",
        "records_docsize",
        "records_config",
    }
    assert len(search(repository, "fox")) == 1


def test_build_index_no_longer_deletes_the_database_file(tmp_path):
    """The file is long-lived now, because the memo cache is in it."""
    from memoria.index import INDEX_RELATIVE_PATH

    records = [_record("SRC-000001", ["A paragraph."])]
    repository = _index(tmp_path, records)
    db_path = repository.root / INDEX_RELATIVE_PATH
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO memo (key, kind, anchor, value, written_at) "
        "VALUES ('k', 'paragraph', 'a', '{}', '')"
    )
    con.commit()
    con.close()

    build_index(repository, records)

    con = sqlite3.connect(db_path)
    try:
        assert con.execute("SELECT COUNT(*) FROM memo").fetchone()[0] == 1
    finally:
        con.close()


def test_a_cache_this_build_cannot_read_is_refused_rather_than_dropped(tmp_path):
    """Discarding a cache the author paid a model to fill is the one
    unrecoverable mistake this module can make, so an unknown schema version
    stops and names the flag that would do it on purpose."""
    from memoria.index import INDEX_RELATIVE_PATH, IndexSchemaError

    records = [_record("SRC-000001", ["A paragraph."])]
    repository = _index(tmp_path, records)
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("UPDATE memoria_schema SET value = '99' WHERE key = 'memo_version'")
    con.commit()
    con.close()

    with pytest.raises(IndexSchemaError, match="reset-cache"):
        build_index(repository, records)


def test_reset_cache_discards_it_deliberately(tmp_path):
    from memoria.index import INDEX_RELATIVE_PATH

    records = [_record("SRC-000001", ["A paragraph."])]
    repository = _index(tmp_path, records)
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("UPDATE memoria_schema SET value = '99' WHERE key = 'memo_version'")
    con.commit()
    con.close()

    build_index(repository, records, reset_cache=True)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    try:
        assert con.execute(
            "SELECT value FROM memoria_schema WHERE key = 'memo_version'"
        ).fetchone()[0] == "1"
    finally:
        con.close()


# --- the gathered set and its pin/exclude overlay (#18) ----------------------


def _write_entry(tmp_path, entry):
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry))


def _gather_repo(tmp_path, paragraphs, entries, record_id="SRC-000001"):
    """A repository with an index and some entries, normalized-record-backed
    so `memoria rebuild` (not just `build_index`) works against it."""
    repository = Repository(root=tmp_path)
    for entry in entries:
        _write_entry(tmp_path, entry)
    record = _record(record_id, paragraphs)
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    return repository


def _memo(repository, anchor, **kwargs):
    ex.record_extraction(repository, anchor, ex.ParagraphExtraction(**kwargs))


def _place(entry_id, surface_form):
    return ex.ProposedPlacement(entry_id, surface_form)


def _form(surface_form, subject_id="SUB-people"):
    return ex.ProposedForm(surface_form, subject_id)


_AUTHOR = Actor(name="Author", email="author@example.com")


def test_gather_returns_the_paragraphs_the_match_terms_matched(tmp_path):
    """AC 1: the gathered set is built from the entry's match terms."""
    entry = Entry(id="SUB-people/robert", match_terms=["Bob"], body="")
    repository = _gather_repo(
        tmp_path, ["Bob went to town.", "Nothing relevant here."], [entry]
    )
    _memo(
        repository,
        "src-000001-p1",
        placements=[_place("SUB-people/robert", "Bob")],
    )
    _memo(repository, "src-000001-p2")
    ex.derive(repository)

    result = gather(repository, "SUB-people/robert")

    assert [g.anchor for g in result] == ["src-000001-p1"]
    assert result[0] == GatheredSource(
        src_id="SRC-000001", anchor="src-000001-p1", pinned=False
    )


def test_adding_a_match_term_extends_the_gathered_set_on_the_next_pass(tmp_path):
    """AC 2. The entry's own slug ("robert") deliberately does not license
    "Bob" implicitly, so the extension can only be the added match term."""
    entry = Entry(id="SUB-people/robert", match_terms=[], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])
    _memo(repository, "src-000001-p1", unplaced=[_form("Bob")])
    ex.derive(repository)
    assert gather(repository, "SUB-people/robert") == []

    _write_entry(
        tmp_path, Entry(id="SUB-people/robert", match_terms=["Bob"], body="")
    )
    ex.derive(repository)

    assert [g.anchor for g in gather(repository, "SUB-people/robert")] == [
        "src-000001-p1"
    ]


def test_pin_and_exclude_are_recorded_with_actor_and_timestamp(tmp_path):
    """AC 3."""
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])

    pin(repository, "SUB-people/bob", "src-000001-p1", _AUTHOR)

    rows = list_overlay(repository)
    assert len(rows) == 1
    row = rows[0]
    assert row.entry_id == "SUB-people/bob"
    assert row.anchor == "src-000001-p1"
    assert row.action == "pin"
    assert row.actor_name == "Author"
    assert row.actor_email == "author@example.com"
    # Raises if unparseable - the attribution is a real timestamp, not a
    # placeholder.
    datetime.fromisoformat(row.at)


def test_excluding_a_source_survives_rebuild(tmp_path):
    """AC 4: an exclusion is still in force after `memoria rebuild` -
    survives because `gather_overlay` is a preserved table, not a derived
    one."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])
    _memo(repository, "src-000001-p1", placements=[_place("SUB-people/bob", "Bob")])
    ex.derive(repository)
    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == [
        "src-000001-p1"
    ]

    exclude(repository, "SUB-people/bob", "src-000001-p1", _AUTHOR)
    assert gather(repository, "SUB-people/bob") == []

    rebuild(repository)

    assert gather(repository, "SUB-people/bob") == []


def test_a_pinned_source_stays_in_the_set_even_when_matching_would_not_find_it(
    tmp_path,
):
    """AC 5."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _gather_repo(
        tmp_path, ["Bob went to town.", "An unrelated paragraph."], [entry]
    )
    _memo(repository, "src-000001-p1", placements=[_place("SUB-people/bob", "Bob")])
    _memo(repository, "src-000001-p2")
    ex.derive(repository)
    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == [
        "src-000001-p1"
    ]

    pin(repository, "SUB-people/bob", "src-000001-p2", _AUTHOR)

    result = {g.anchor: g.pinned for g in gather(repository, "SUB-people/bob")}
    assert result == {"src-000001-p1": False, "src-000001-p2": True}


def test_the_gathered_set_carries_no_id():
    """AC 6: nothing here mints an identifier for the set itself - a
    `GatheredSource` names only the paragraph and the overlay flag on it."""
    fields = {f.name for f in dataclasses.fields(GatheredSource)}
    assert fields == {"src_id", "anchor", "pinned"}


def test_validate_fails_a_pin_lacking_attribution(tmp_path):
    """AC 7. The schema's ``NOT NULL`` only rules out ``NULL`` - an actor
    with an empty name/email still writes a row, and `validate` is what
    actually holds the requirement."""
    from memoria.validate import validate

    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw" / "manifest.yaml").write_text("units: []\n")
    pin(
        repository,
        "SUB-people/bob",
        "src-000001-p1",
        Actor(name="", email=""),
    )

    errors = validate(evidence_root=tmp_path, repo_root=tmp_path)
    assert any("attribution" in error for error in errors)


def test_gather_and_validate_do_not_crash_on_an_index_predating_the_overlay_table(
    tmp_path,
):
    """`gather_overlay` did not exist before this issue's index. An index
    built by an older version of `memoria rebuild` still has every other
    table, and `list_overlay`/`gather` must create the missing table on the
    fly (through `connect`, not a bare `sqlite3.connect`) rather than raise
    `sqlite3.OperationalError: no such table`."""
    from memoria.validate import validate

    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("DROP TABLE gather_overlay")
    con.commit()
    con.close()
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw" / "manifest.yaml").write_text("units: []\n")

    assert list_overlay(repository) == []
    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == [
        "src-000001-p1"
    ]
    # `validate` returns rather than raising - it may still report unrelated
    # findings (e.g. from other validators), but never "no such table".
    errors = validate(evidence_root=tmp_path, repo_root=tmp_path)
    assert not any("gather_overlay" in error or "no such table" in error for error in errors)


def test_a_theme_gathers_exactly_where_its_match_terms_co_occur(tmp_path):
    """AC 8: a Theme promoted from a cluster - match terms naming two
    entries and the relation between them - gathers the paragraph where
    they co-occur, and nothing else, with no model call in `gather` itself.

    A solo appearance of one of the named entries, without the other, is
    not co-occurrence and must not be gathered - the entry-shaped match
    terms are intersected with each other and with the relation, not
    unioned.
    """
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    carol = Entry(id="SUB-people/carol", match_terms=["Carol"], body="")
    tension = Entry(
        id="SUB-themes/tension",
        match_terms=[
            "SUB-people/bob",
            "SUB-people/carol",
            "SUB-people/bob -> pressures -> SUB-people/carol",
        ],
        body="",
    )
    repository = _gather_repo(
        tmp_path,
        ["Bob pressures Carol.", "Bob walked alone."],
        [bob, carol, tension],
    )
    _memo(
        repository,
        "src-000001-p1",
        placements=[_place("SUB-people/bob", "Bob"), _place("SUB-people/carol", "Carol")],
        relations=[ex.ProposedRelation("SUB-people/bob", "pressures", "SUB-people/carol")],
    )
    _memo(
        repository,
        "src-000001-p2",
        placements=[_place("SUB-people/bob", "Bob")],
    )
    ex.derive(repository)

    result = gather(repository, "SUB-themes/tension")

    assert [g.anchor for g in result] == ["src-000001-p1"]


def test_re_deriving_does_not_change_a_themes_gathered_set(tmp_path):
    """AC 9: re-running the extraction (and re-clustering) is a no-op on a
    promoted Theme's gathered set when placements have not changed."""
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    carol = Entry(id="SUB-people/carol", match_terms=["Carol"], body="")
    tension = Entry(
        id="SUB-themes/tension",
        match_terms=["SUB-people/bob -> pressures -> SUB-people/carol"],
        body="",
    )
    repository = _gather_repo(
        tmp_path, ["Bob pressures Carol."], [bob, carol, tension]
    )
    _memo(
        repository,
        "src-000001-p1",
        placements=[_place("SUB-people/bob", "Bob"), _place("SUB-people/carol", "Carol")],
        relations=[ex.ProposedRelation("SUB-people/bob", "pressures", "SUB-people/carol")],
    )
    ex.derive(repository)
    before = gather(repository, "SUB-themes/tension")

    ex.derive(repository)
    ex.derive(repository)
    after = gather(repository, "SUB-themes/tension")

    assert before == after == [
        GatheredSource(src_id="SRC-000001", anchor="src-000001-p1", pinned=False)
    ]


def test_adding_an_entry_or_relation_match_term_extends_a_themes_gathered_set(
    tmp_path,
):
    """AC 10."""
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    carol = Entry(id="SUB-people/carol", match_terms=["Carol"], body="")
    tension = Entry(id="SUB-themes/tension", match_terms=[], body="")
    repository = _gather_repo(
        tmp_path, ["Bob pressures Carol."], [bob, carol, tension]
    )
    _memo(
        repository,
        "src-000001-p1",
        placements=[_place("SUB-people/bob", "Bob"), _place("SUB-people/carol", "Carol")],
        relations=[ex.ProposedRelation("SUB-people/bob", "pressures", "SUB-people/carol")],
    )
    ex.derive(repository)
    assert gather(repository, "SUB-themes/tension") == []

    _write_entry(
        tmp_path,
        Entry(
            id="SUB-themes/tension",
            match_terms=["SUB-people/bob -> pressures -> SUB-people/carol"],
            body="",
        ),
    )
    ex.derive(repository)

    assert [g.anchor for g in gather(repository, "SUB-themes/tension")] == [
        "src-000001-p1"
    ]


# --- appearances, lexical engine only (#19, part 06 §8.11) ------------------


def test_compute_appearances_matches_lexically_over_book_source_type_only(tmp_path):
    """AC 1: appearances are computed over the audit targets - records with
    ``source_type: book`` - and stored in the index. The same term appearing
    in a journal (evidence, not an audit target) earns no appearance."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, entry)
    records = [
        _record("SRC-000001", ["Bob went to the market."], source_type="journal"),
        _record(
            "SRC-000002",
            ["Bob argued with Carol.", "Nothing relevant here."],
            source_type="book",
        ),
    ]
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, records)

    report = compute_appearances(repository)

    assert [a.anchor for a in list_appearances(repository, "SUB-people/bob")] == [
        "src-000002-p1"
    ]
    assert report.appearances == 1


def test_each_appearance_carries_the_passage_and_a_note_on_how(tmp_path):
    """AC 2: an appearance carries the entry (by construction of the query),
    the passage, and a short note naming what matched."""
    entry = Entry(id="SUB-people/bob", match_terms=["Robert"], body="")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, entry)
    book = _record("SRC-000001", ["Robert argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])

    compute_appearances(repository)
    (appearance,) = list_appearances(repository, "SUB-people/bob")

    assert appearance.src_id == "SRC-000001"
    assert appearance.anchor == "src-000001-p1"
    assert "Robert" in appearance.note


def test_appearances_are_unaffected_by_the_gather_overlay_and_vice_versa(tmp_path):
    """AC 3: the gathered set and appearances are separately queryable and
    never cross - the overlay that exists only for the gathered set (§8.3)
    has no reach into the ``appearances`` table, since appearances has no
    overlay of its own (AC 5) and nothing here reads ``gather_overlay``."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, entry)
    book = _record("SRC-000001", ["Bob argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])

    compute_appearances(repository)
    appeared_before = list_appearances(repository, "SUB-people/bob")
    assert [a.anchor for a in appeared_before] == ["src-000001-p1"]

    # An author act against the gathered set - there is no such act against
    # an appearance at all - must not touch the appearances table.
    exclude(repository, "SUB-people/bob", "src-000001-p1", _AUTHOR)

    assert list_appearances(repository, "SUB-people/bob") == appeared_before
    # And the reverse holds by construction: `compute_appearances` never
    # writes to `gather_overlay`, so the only row there is the exclude just
    # made.
    assert [o.action for o in list_overlay(repository)] == ["exclude"]


def test_appearances_and_gather_never_return_the_same_anchor(tmp_path):
    """AC 3, in the criterion's own words: appearances and the gathered set
    are "separately queryable and never cross". One entry, one ``book``
    record, no placements - the anchor the lexical pass finds must show up
    on exactly one of the two sides, never both, since a book paragraph is
    an audit target (docs/normalized-record-schema.md) and never evidence
    ``gather`` may cite."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, entry)
    book = _record("SRC-000001", ["Bob argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])

    compute_appearances(repository)
    appeared = {a.anchor for a in list_appearances(repository, "SUB-people/bob")}
    gathered = {g.anchor for g in gather(repository, "SUB-people/bob")}

    assert appeared == {"src-000001-p1"}
    assert gathered.isdisjoint(appeared)


def test_computing_appearances_does_not_write_to_the_entry_file(tmp_path):
    """AC 4: nothing writes an appearance back into an entry."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Some testimony.")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, entry)
    book = _record("SRC-000001", ["Bob argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    before = entry_path.read_text(encoding="utf-8")

    compute_appearances(repository)

    assert entry_path.read_text(encoding="utf-8") == before


def test_appearances_carry_no_pin_or_exclude_overlay():
    """AC 5: there is no author act against an appearance (§8.11's third
    property) - no pin/exclude functions for it, and no flag on the row."""
    import memoria.index as index_module

    assert not hasattr(index_module, "pin_appearance")
    assert not hasattr(index_module, "exclude_appearance")
    fields = {f.name for f in dataclasses.fields(Appearance)}
    assert fields == {"src_id", "anchor", "note"}


def test_appearances_are_regenerated_identically_by_rebuild(tmp_path):
    """AC 6."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    _write_entry(tmp_path, entry)
    book = _record("SRC-000001", ["Bob argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    repository = Repository(root=tmp_path)

    report = rebuild(repository)
    before = list_appearances(repository, "SUB-people/bob")
    assert [a.anchor for a in before] == ["src-000001-p1"]
    assert report.appearances.appearances == 1

    report2 = rebuild(repository)

    assert list_appearances(repository, "SUB-people/bob") == before
    assert report2.appearances == report.appearances


def test_appearances_report_names_the_themes_and_arcs_gap(tmp_path):
    """AC 7: Themes and Arcs produce no appearances yet, and the gap is
    reported rather than silently folded into zero."""
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    tension = Entry(
        id="SUB-themes/tension", match_terms=["SUB-people/bob"], body=""
    )
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, bob)
    _write_entry(tmp_path, tension)
    book = _record("SRC-000001", ["Bob argued with Carol."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])

    report = compute_appearances(repository)

    assert list_appearances(repository, "SUB-themes/tension") == []
    assert report.entries_skipped == 1
    assert report.skipped_subjects == ("SUB-themes",)
    # The lexically-matchable entry alongside it is unaffected by the skip.
    assert report.entries_computed == 1
    assert report.appearances == 1
