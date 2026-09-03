import dataclasses
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime

import pytest
import sqlite_vec

from memoria import extraction as ex
from memoria import index as idx
from memoria.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME
from memoria.index import (
    INDEX_RELATIVE_PATH,
    SEMANTIC_SEARCH_LIMIT,
    SNIPPET_ELLIPSIS,
    SNIPPET_MATCH_END,
    SNIPPET_MATCH_START,
    Appearance,
    GatheredSource,
    IndexBuildError,
    SearchFilters,
    appeared_entry_ids,
    appearances_supported,
    build_index,
    compute_appearances,
    exclude,
    filter_predicate,
    gather,
    is_built,
    list_appearances,
    list_overlay,
    pin,
    rebuild,
    search,
    search_semantic,
)
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import Entry, OverlayAct, entry_to_markdown, load_entry
from memoria.write import Actor, WriteError


def _basis_vector(index, dim=EMBEDDING_DIMENSIONS):
    """A unit vector along axis ``index`` - together, an orthonormal basis
    lets a fake embedder place fixture texts at exact, known distances from
    each other with no dependence on a real model (#81's "the test path is
    deterministic")."""
    vector = [0.0] * dim
    vector[index % dim] = 1.0
    return vector


def _fake_embed_fn(vectors):
    """A deterministic ``EmbedFn`` (#81) over a caller-supplied ``{text:
    vector}`` mapping - never touches ``fastembed`` or the network. Raises on
    a text the test forgot to place, rather than silently embedding it as
    all-zero, so a fixture gap fails loudly."""

    def embed(texts):
        return [vectors[text] for text in texts]

    return embed


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


# --- is_built (#157) --------------------------------------------------------


def test_a_repository_with_no_index_file_is_not_built(tmp_path):
    """The unbuilt half of the pair `search`'s empty list cannot express -
    and asking must not create the file any more than searching does."""
    repository = Repository(root=tmp_path)

    assert is_built(repository) is False
    assert not (tmp_path / INDEX_RELATIVE_PATH).exists()


def test_an_index_built_over_no_records_is_built_and_finds_nothing(tmp_path):
    """The other half, and the state the flag exists to name: `rebuild` ran,
    there was nothing to index, and that is not the same fact as never
    having run it."""
    repository = _index(tmp_path, [])

    assert is_built(repository) is True
    assert search(repository, "fox") == []


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


def test_an_empty_from_or_to_filter_is_no_filter_rather_than_a_match_all(tmp_path):
    """`INSTR(x, "") > 0` is true of every non-null `x`, so an empty header
    filter used to sweep in every record that merely *has* that header - a
    silently wrong answer to "who wrote to Scholtes?". An empty string is
    treated like `None`: no clause at all, so the result is the unfiltered
    one, non-email record included."""
    records = [
        _record(
            "SRC-000023",
            ["A message about a heron."],
            email_from="Dave Perrino <dperrino@example.com>",
            email_to="Diana Scholtes <dscholtes@example.com>",
        ),
        _record("SRC-000024", ["A heron by the pond, no email header."]),
    ]
    repository = _index(tmp_path, records)

    unfiltered = sorted(r.src_id for r in search(repository, "heron"))
    assert unfiltered == ["SRC-000023", "SRC-000024"]

    for filters in (
        SearchFilters(from_=""),
        SearchFilters(to=""),
        SearchFilters(from_="", to=""),
    ):
        hits = search(repository, "heron", filters)
        assert sorted(r.src_id for r in hits) == unfiltered


def test_an_empty_header_filter_adds_no_clause_to_the_predicate():
    """The predicate builder is the one place the rule lives (#74/#81 join
    the same table through it), so an empty header filter must produce no
    SQL at all rather than a clause that happens to match everything."""
    assert filter_predicate(SearchFilters(from_="", to="")) == ("", [])

    sql, params = filter_predicate(SearchFilters(from_="", to="scholtes"))
    assert sql == "INSTR(LOWER(paragraphs.email_to), LOWER(?)) > 0"
    assert params == ["scholtes"]


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


def test_semantic_results_feed_straight_into_read_with_no_reconstruction(tmp_path):
    """#81's key interfaces: the same anchor scheme as `search` - a semantic
    hit resolves through `read(ref)` exactly like a lexical one, with no
    reconstruction step."""
    from memoria import references

    records = [_record("SRC-000012", ["A fox by the pond."])]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {"A fox by the pond.": _basis_vector(0), "fox": _basis_vector(0)}
    )
    build_index(repository, records, embed_fn=embed_fn)

    (hit,) = search_semantic(repository, "fox", embed_fn=embed_fn).results

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


# --- the semantic index (#81, ADR-0007) --------------------------------------


def test_build_index_with_no_embed_fn_leaves_the_vector_table_empty(tmp_path):
    """The documented default: `build_index` is called by most of this
    file's other tests with no `embed_fn` at all, and none of them should pay
    for - or need - a model."""
    records = [_record("SRC-000001", ["A blue heron flew over the pond."])]
    repository = _index(tmp_path, records)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        assert con.execute("SELECT COUNT(*) FROM paragraph_vectors").fetchone()[0] == 0
    finally:
        con.close()


def test_build_index_populates_one_vector_per_real_paragraph(tmp_path):
    records = [
        _record(
            "SRC-000001",
            ["A blue heron flew over the pond.", "Nothing about birds here."],
        )
    ]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {
            "A blue heron flew over the pond.": _basis_vector(0),
            "Nothing about birds here.": _basis_vector(1),
        }
    )

    build_index(repository, records, embed_fn=embed_fn)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        anchors = {
            row[0] for row in con.execute("SELECT anchor FROM paragraph_vectors")
        }
    finally:
        con.close()
    assert anchors == {"src-000001-p1", "src-000001-p2"}


def test_build_index_raises_when_embedder_returns_fewer_vectors_than_paragraphs(
    tmp_path,
):
    """#154: an embedder that drops a paragraph must fail the build loudly,
    naming both counts, rather than silently truncating the semantic index -
    ``zip`` would otherwise stop at the shorter sequence and leave later
    paragraphs unsearchable with no error at all. Checked against a rebuild
    over an already-populated vector table, so "no partially populated
    vector table is left behind" has a prior, known-good state to fail out
    of rather than an empty file."""
    records = [
        _record(
            "SRC-000001",
            ["A blue heron flew over the pond.", "Nothing about birds here."],
        )
    ]
    repository = Repository(root=tmp_path)
    good_embed_fn = _fake_embed_fn(
        {
            "A blue heron flew over the pond.": _basis_vector(0),
            "Nothing about birds here.": _basis_vector(1),
        }
    )
    build_index(repository, records, embed_fn=good_embed_fn)

    def _short_embed_fn(texts):
        return [_basis_vector(0)]  # one vector for two paragraphs

    with pytest.raises(IndexBuildError, match="1 vector.*2 paragraph"):
        build_index(repository, records, embed_fn=_short_embed_fn)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        assert con.execute("SELECT COUNT(*) FROM paragraph_vectors").fetchone()[0] == 0
    finally:
        con.close()


def test_search_semantic_finds_the_nearest_paragraph_by_meaning(tmp_path):
    """The point of the feature: a query with none of a paragraph's own
    wording still finds it, because the two embed close together."""
    records = [
        _record("SRC-000001", ["A blue heron flew low over the pond."]),
        _record("SRC-000002", ["The stock market fell sharply today."]),
    ]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {
            "A blue heron flew low over the pond.": _basis_vector(0),
            "The stock market fell sharply today.": _basis_vector(1),
            "a wading bird by the water": _basis_vector(0),
        }
    )
    build_index(repository, records, embed_fn=embed_fn)

    result = search_semantic(
        repository, "a wading bird by the water", embed_fn=embed_fn
    )

    assert [r.anchor for r in result.results][0] == "src-000001-p1"


def test_search_semantic_returns_the_specific_paragraph_anchor(tmp_path):
    records = [
        _record(
            "SRC-000002",
            ["Unrelated.", "A blue heron flew over the pond."],
        )
    ]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {
            "Unrelated.": _basis_vector(1),
            "A blue heron flew over the pond.": _basis_vector(0),
            "heron": _basis_vector(0),
        }
    )
    build_index(repository, records, embed_fn=embed_fn)

    hit = search_semantic(repository, "heron", embed_fn=embed_fn).results[0]

    assert hit.src_id == "SRC-000002"
    assert hit.anchor == "src-000002-p2"
    assert hit.source_type == "journal"


def test_search_semantic_reuses_search_filters(tmp_path):
    """#12's filter representation, not a new one (docs/tool-surface.md's
    "Key interfaces") - a `source_type` filter excludes the nearer paragraph
    exactly as it would for `search`."""
    records = [
        _record(
            "SRC-000001", ["A heron by the pond."], source_type="editorial"
        ),
        _record("SRC-000002", ["A heron by the pond, said plainly."], source_type="journal"),
    ]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {
            "A heron by the pond.": _basis_vector(0),
            "A heron by the pond, said plainly.": _basis_vector(0),
            "heron": _basis_vector(0),
        }
    )
    build_index(repository, records, embed_fn=embed_fn)

    result = search_semantic(
        repository,
        "heron",
        SearchFilters(source_type="journal"),
        embed_fn=embed_fn,
    )

    assert [r.src_id for r in result.results] == ["SRC-000002"]
    assert "filters: source_type=journal" in result.scope


def test_search_semantic_over_a_missing_index_returns_no_results(tmp_path):
    repository = Repository(root=tmp_path)

    def _must_not_be_called(texts):
        raise AssertionError("embed_fn must not run against a missing index")

    result = search_semantic(repository, "heron", embed_fn=_must_not_be_called)

    assert result.results == ()
    assert "0 paragraphs" in result.scope


def test_search_semantic_with_no_vectors_built_does_not_call_embed_fn(tmp_path):
    """`build_index` ran with no embedder (the default), so the vector table
    exists but is empty - there is nothing to compare a query vector
    against, so nothing should pay to compute one."""
    records = [_record("SRC-000001", ["A blue heron flew over the pond."])]
    repository = _index(tmp_path, records)

    def _must_not_be_called(texts):
        raise AssertionError("embed_fn must not run with nothing embedded")

    result = search_semantic(repository, "heron", embed_fn=_must_not_be_called)

    assert result.results == ()
    assert "0 paragraphs" in result.scope


def test_search_semantic_scope_line_names_embedded_and_matched_counts(tmp_path):
    """§33.1: "an index reports nothing about its own recall" on its own -
    this is the one place a session can state what the semantic index
    covered. Nearest-neighbour search has no notion of "no match" below
    `SEMANTIC_SEARCH_LIMIT` - every embedded paragraph is a candidate, so
    both counts show here (`test_search_semantic_caps_at_the_documented_limit`
    is where they diverge)."""
    records = [
        _record("SRC-000001", ["A blue heron flew over the pond."]),
        _record("SRC-000002", ["The stock market fell sharply."]),
    ]
    repository = Repository(root=tmp_path)
    embed_fn = _fake_embed_fn(
        {
            "A blue heron flew over the pond.": _basis_vector(0),
            "The stock market fell sharply.": _basis_vector(1),
            "heron": _basis_vector(0),
        }
    )
    build_index(repository, records, embed_fn=embed_fn)

    result = search_semantic(repository, "heron", embed_fn=embed_fn)

    assert result.scope == (
        f"embedded 2 paragraphs with {EMBEDDING_MODEL_NAME}; "
        "filters: none; 2 semantic hits"
    )


def test_search_semantic_caps_at_the_documented_limit(tmp_path):
    paragraphs = [f"paragraph number {i}." for i in range(SEMANTIC_SEARCH_LIMIT + 5)]
    records = [_record("SRC-000001", paragraphs)]
    repository = Repository(root=tmp_path)
    vectors = {text: _basis_vector(0) for text in paragraphs}
    vectors["query"] = _basis_vector(0)
    embed_fn = _fake_embed_fn(vectors)
    build_index(repository, records, embed_fn=embed_fn)

    result = search_semantic(repository, "query", embed_fn=embed_fn)

    assert len(result.results) == SEMANTIC_SEARCH_LIMIT


def test_no_cluster_summary_is_ever_embedded(tmp_path):
    """One of #81's own acceptance criteria: cluster summaries are
    `[inferred]` text, never evidence, and must never reach the embedder -
    `build_index`'s embedding loop walks `NormalizedRecord.paragraphs` only,
    never the `memo` table, so a planted cluster summary is the regression
    check that this stays true even though nothing here queries `memo` at
    all today."""
    records = [_record("SRC-000001", ["Bob went to town."])]
    repository = _index(tmp_path, records)

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute(
        "INSERT INTO memo (key, kind, anchor, value, written_at) "
        "VALUES ('a-cluster', 'cluster_summary', '', "
        "'[inferred] Bob travelled to several towns this year.', '')"
    )
    con.commit()
    con.close()

    seen_texts: list[str] = []

    def _recording_embed_fn(texts):
        seen_texts.extend(texts)
        return [_basis_vector(0) for _ in texts]

    build_index(repository, records, embed_fn=_recording_embed_fn)

    assert seen_texts == ["Bob went to town."]


# --- the sqlite-vec extension is optional outside semantic search (#153) ----


class _NoExtensionConnection:
    """Wraps a real ``sqlite3.Connection`` but raises on
    ``enable_load_extension``, simulating an interpreter whose ``sqlite3`` was
    built with no loadable-extension support at all - the method itself
    raises (``AttributeError`` on some builds, ``sqlite3.NotSupportedError``
    on others) rather than merely failing to find an extension."""

    def __init__(self, real):
        self._real = real

    def enable_load_extension(self, flag):
        raise AttributeError("enable_load_extension is not available")

    def __getattr__(self, name):
        return getattr(self._real, name)


def _patch_no_extension_sqlite(monkeypatch):
    real_connect = sqlite3.connect
    monkeypatch.setattr(
        "memoria.index.sqlite3.connect",
        lambda *a, **k: _NoExtensionConnection(real_connect(*a, **k)),
    )


def test_text_search_survives_an_interpreter_with_no_extension_support(
    tmp_path, monkeypatch
):
    """#153: opening the index for text search must never call
    `enable_load_extension` or load `sqlite-vec` - `search_semantic` is the
    only caller that needs the extension, and it degrades instead of
    raising, so a session without loadable-extension support still gets
    lexical search."""
    records = [_record("SRC-000001", ["A fox ran through the woods."])]
    repository = _index(tmp_path, records)

    _patch_no_extension_sqlite(monkeypatch)

    results = search(repository, "fox")
    assert len(results) == 1
    assert results[0].src_id == "SRC-000001"

    def _must_not_be_called(texts):
        raise AssertionError("embed_fn must not run when the extension can't load")

    semantic = search_semantic(repository, "fox", embed_fn=_must_not_be_called)
    assert semantic.results == ()
    assert "cannot load extensions" in semantic.scope


def test_connect_degrades_when_the_load_extension_capability_is_missing(
    tmp_path, monkeypatch
):
    """`connect` serves extraction, audit, and every `read(ref)`'s overlay
    decoration - none of which touch the vector table - so it must still
    produce a working index on an interpreter that cannot load extensions,
    just without `paragraph_vectors`."""
    from memoria.index import connect

    repository = Repository(root=tmp_path)
    _patch_no_extension_sqlite(monkeypatch)

    con = connect(repository)
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        con.close()

    assert "paragraphs" in tables
    assert "paragraph_vectors" not in tables


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
    # FTS5 and sqlite-vec each keep their own shadow tables beside their
    # virtual table; they are SQLite's/the extension's, not ours, and are
    # dropped with their parent (verified below by
    # test_rebuild_regenerates_the_vector_table_without_orphan_shadow_tables).
    # `sqlite_sequence` is SQLite's own bookkeeping table for the vec0
    # module's internal rowid sequence and outlives any single vec0 table's
    # drop/recreate cycle - it is not derived state to name either way.
    ours = {
        name
        for name in _tables(repository)
        if not name.startswith("records_")
        and not name.startswith("paragraph_vectors_")
        and name != "sqlite_sequence"
    }
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


def test_rebuild_regenerates_the_vector_table_without_orphan_shadow_tables(tmp_path):
    """The vec0 counterpart of the FTS5 check above: `paragraph_vectors` is
    dropped and recreated by name on every rebuild (#81; §42's "delete and
    regenerate all derived state"), and its shadow tables must go with it -
    a second and third rebuild leave exactly one set, and the rows are the
    latest build's, not an accumulation."""
    records = [_record("SRC-000001", ["The fox ran through the woods."])]
    embed_fn = _fake_embed_fn(
        {"The fox ran through the woods.": _basis_vector(0), "fox": _basis_vector(0)}
    )
    repository = Repository(root=tmp_path)
    build_index(repository, records, embed_fn=embed_fn)
    build_index(repository, records, embed_fn=embed_fn)
    build_index(repository, records, embed_fn=embed_fn)

    shadows = {
        name for name in _tables(repository) if name.startswith("paragraph_vectors_")
    }
    assert shadows == {
        "paragraph_vectors_chunks",
        "paragraph_vectors_info",
        "paragraph_vectors_rowids",
        "paragraph_vectors_vector_chunks00",
    }
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        assert con.execute("SELECT COUNT(*) FROM paragraph_vectors").fetchone()[0] == 1
    finally:
        con.close()
    assert len(search_semantic(repository, "fox", embed_fn=embed_fn).results) == 1


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


def test_a_stale_paragraphs_table_is_refused_rather_than_a_bare_sqlite_error(
    tmp_path,
):
    """A `paragraphs` table built before #111's `email_from`/`email_to`
    columns is not a new table `CREATE TABLE IF NOT EXISTS` will create -
    it is left exactly as it is, so both `connect` and `search` must catch
    the stale shape themselves rather than let a query against those
    columns fail as a bare, unactionable `sqlite3.OperationalError`."""
    from memoria.index import INDEX_RELATIVE_PATH, IndexSchemaError, connect

    records = [_record("SRC-000001", ["A message about a heron."])]
    repository = _index(tmp_path, records)
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("DROP TABLE paragraphs")
    con.execute(
        "CREATE TABLE paragraphs("
        "anchor TEXT PRIMARY KEY, src_id TEXT, source_type TEXT, "
        "event_date TEXT, recorded_date TEXT, contemporaneous INTEGER"
        ")"
    )
    con.execute(
        "INSERT INTO paragraphs "
        "(anchor, src_id, source_type, event_date, recorded_date, contemporaneous) "
        "VALUES ('src-000001-p1', 'SRC-000001', 'journal', 'Oct. 22.', 'Oct. 22.', 1)"
    )
    con.commit()
    con.close()

    with pytest.raises(IndexSchemaError, match="memoria rebuild"):
        search(repository, "heron")
    with pytest.raises(IndexSchemaError, match="memoria rebuild"):
        connect(repository)


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


# --- the gathered set and its pin/exclude overlay (#18, #21) -----------------


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _write_entry(tmp_path, entry):
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry))


def _gather_repo(tmp_path, paragraphs, entries, record_id="SRC-000001"):
    """A repository with an index and some entries, normalized-record-backed
    so `memoria rebuild` (not just `build_index`) works against it. A real
    (uncommitted) git repository: `pin`/`exclude` now write the entry file
    through the durable write path (#21), which commits."""
    _git(tmp_path, "init", "-q")
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
    survives because it lives on the entry file (#21), which `rebuild`
    never touches at all."""
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


def test_a_pin_survives_rebuild_too(tmp_path):
    """AC 3/4's other half: a pin is as durable as an exclusion. Not
    derivable from `test_excluding_a_source_survives_rebuild` alone - pin
    and exclude write to opposite ends of an entry's overlay list
    (`_record_overlay` drops any existing row for the anchor before
    appending the new one), so only a pin actually exercises that half of
    the write."""
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
    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == [
        "src-000001-p1",
        "src-000001-p2",
    ]

    rebuild(repository)

    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == [
        "src-000001-p1",
        "src-000001-p2",
    ]


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


def test_paragraphs_by_anchor_chunks_under_sqlites_own_variable_ceiling(
    tmp_path, monkeypatch
):
    """#132: the paragraphs-by-anchor query used to build one
    `anchor IN (?,?...)` list sized to the whole gathered set - unbounded
    with the paragraph count, and able to exceed SQLite's own
    bound-parameter ceiling on the real archive, at which point the query
    raised and the overlay was silently dropped archive-wide. Lowered here
    to a real, tiny ceiling via `setlimit` (Python's sqlite3, 3.11+) so this
    proves the fix against SQLite's actual enforcement, not an assumption
    about what it is: an unchunked query over these anchors genuinely fails
    against this connection, while `_paragraphs_by_anchor` still returns
    every row, correctly."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    paragraphs = [f"Bob was here, paragraph {i}." for i in range(10)]
    repository = _gather_repo(tmp_path, paragraphs, [entry])
    anchors = {f"src-000001-p{i}" for i in range(1, 11)}
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 3)
    placeholders = ",".join("?" for _ in anchors)
    with pytest.raises(sqlite3.OperationalError, match="too many SQL variables"):
        con.execute(
            f"SELECT anchor, src_id FROM paragraphs WHERE anchor IN ({placeholders})",
            tuple(anchors),
        )
    monkeypatch.setattr(idx, "_ANCHOR_CHUNK_SIZE", 2)

    rows = idx._paragraphs_by_anchor(con, anchors)

    assert {anchor for anchor, _ in rows} == anchors


def test_gather_is_correct_past_a_forced_anchor_chunk_boundary(tmp_path, monkeypatch):
    """#132 AC 1/3: the same chunking, exercised through the public
    `gather()` with the real chunk size forced tiny, so the gathered set
    spans several chunks without needing tens of thousands of paragraphs -
    the result must still be the full, correctly-ordered set, not silently
    truncated to one chunk."""
    monkeypatch.setattr(idx, "_ANCHOR_CHUNK_SIZE", 2)
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    paragraphs = [f"Bob was here, paragraph {i}." for i in range(5)]
    repository = _gather_repo(tmp_path, paragraphs, [entry])

    result = gather(repository, "SUB-people/bob")

    assert [g.anchor for g in result] == [f"src-000001-p{i}" for i in range(1, 6)]


def test_overlay_for_anchor_opens_one_connection_regardless_of_entry_count(
    tmp_path, monkeypatch
):
    """#132 AC 2: the per-read fan-out over entries must not multiply
    `gather`'s own per-entry cost - a fresh `connect()` (DDL plus commit)
    for every entry on disk, on every non-raw read. One shared connection,
    regardless of how many entries there are."""
    entries = [
        Entry(id=f"SUB-people/e{i}", match_terms=[f"word{i}"], body="")
        for i in range(20)
    ]
    repository = _gather_repo(tmp_path, ["Nothing relevant here."], entries)
    calls = []
    real_connect = idx.connect

    def counting_connect(repo):
        calls.append(repo)
        return real_connect(repo)

    monkeypatch.setattr(idx, "connect", counting_connect)

    idx.overlay_for_anchor(repository, "src-000001-p1")

    assert len(calls) == 1


def test_the_gathered_set_carries_no_id():
    """AC 6: nothing here mints an identifier for the set itself - a
    `GatheredSource` names only the paragraph and the overlay flag on it."""
    fields = {f.name for f in dataclasses.fields(GatheredSource)}
    assert fields == {"src_id", "anchor", "pinned"}


def test_pin_refuses_an_unattributed_actor(tmp_path):
    """AC 7 (round 1 review, finding 2): a pin/exclusion with an empty actor
    name or email is rejected *before* the entry file is touched at all -
    not left as an unattributed row that only fails to commit. Relying on
    the underlying git commit to refuse an empty author identity was not
    enough: ``write.write`` replaces the file on disk before it commits, so
    that alone would have left a partially-applied write behind."""
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    before = entry_path.read_text(encoding="utf-8")

    with pytest.raises(WriteError, match="attributed"):
        pin(repository, "SUB-people/bob", "src-000001-p1", Actor(name="", email=""))
    assert entry_path.read_text(encoding="utf-8") == before

    with pytest.raises(WriteError, match="attributed"):
        exclude(
            repository,
            "SUB-people/bob",
            "src-000001-p1",
            Actor(name="Author", email="   "),
        )
    assert entry_path.read_text(encoding="utf-8") == before
    assert list_overlay(repository) == []


def test_a_pin_does_not_drop_unknown_frontmatter_keys(tmp_path):
    """Non-blocking finding, round 1 review: ``_record_overlay`` is the
    first code path that rewrites an *existing* entry file - promotion only
    ever creates one - so a frontmatter key this module does not itself
    model (``Entry.extra``) must round-trip through a pin rather than being
    silently dropped by the parse/serialize cycle."""
    entry = Entry(
        id="SUB-people/bob",
        match_terms=["Bob"],
        body="Some testimony.",
        extra={"custom_key": "keep-me"},
    )
    repository = _gather_repo(tmp_path, ["Bob went to town."], [entry])

    pin(repository, "SUB-people/bob", "src-000001-p1", _AUTHOR)

    reloaded = load_entry(repository, "SUB-people", "bob")
    assert reloaded.extra == {"custom_key": "keep-me"}
    assert reloaded.body == "Some testimony."
    assert [act.anchor for act in reloaded.overlay] == ["src-000001-p1"]


def test_validate_fails_a_pin_lacking_attribution(tmp_path):
    """AC 7. ``pin``/``exclude`` themselves now refuse an unattributed
    ``Actor`` before touching the file at all (`test_pin_refuses_an_
    unattributed_actor`), but a hand-edited entry file still can carry an
    empty ``actor_name``/``actor_email``, and `validate` is what catches
    that."""
    from memoria.validate import validate

    entry = Entry(
        id="SUB-people/bob",
        match_terms=[],
        body="",
        overlay=[
            OverlayAct(
                anchor="src-000001-p1",
                action="pin",
                actor_name="",
                actor_email="",
                at="2026-09-01T00:00:00+00:00",
            )
        ],
    )
    _write_entry(tmp_path, entry)
    (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw" / "manifest.yaml").write_text("units: []\n")

    errors = validate(evidence_root=tmp_path, repo_root=tmp_path)
    assert any("attribution" in error for error in errors)


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


# --- rebuild grows to the derived state (#21) --------------------------------


def test_deleting_memoria_entirely_loses_no_pin_exclusion_or_promotion(tmp_path):
    """AC 4: "Nothing durable is stored only in the index." Part 04 §42 is
    explicit that deleting ``.memoria/index.db`` must never destroy
    intellectual work - so this deletes the whole ``.memoria/`` directory,
    not merely the derived tables a plain ``memoria rebuild`` already
    preserves, and checks that a rebuild afterward still finds every author
    act.

    The promoted entry itself (``subjects/people/bob.md``) was never inside
    ``.memoria/`` to begin with - the real risk this test guards is the
    pin and the exclusion, which used to live only in the index (#18) and
    now live on the entry file (#21).
    """
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _gather_repo(
        tmp_path, ["Bob went to town.", "An unrelated paragraph."], [entry]
    )
    # The exclusion drops the one paragraph the entry's own word-shaped
    # match term would otherwise find lexically; the pin adds one it would
    # not. Neither depends on the memo cache, which is not expected to
    # survive `.memoria/` being deleted (§42's "cost, accepted knowingly" -
    # a memo miss costs a model call, not lost author intent).
    exclude(repository, "SUB-people/bob", "src-000001-p1", _AUTHOR)
    pin(repository, "SUB-people/bob", "src-000001-p2", _AUTHOR)
    before = [g.anchor for g in gather(repository, "SUB-people/bob")]
    assert before == ["src-000001-p2"]

    memoria_dir = tmp_path / ".memoria"
    assert memoria_dir.is_dir()
    shutil.rmtree(memoria_dir)
    assert not memoria_dir.exists()

    rebuild(repository)

    assert [g.anchor for g in gather(repository, "SUB-people/bob")] == before
    rows = {(o.action, o.anchor) for o in list_overlay(repository)}
    assert rows == {("exclude", "src-000001-p1"), ("pin", "src-000001-p2")}
    assert (tmp_path / "subjects" / "people" / "bob.md").is_file()


def _dump_derived(repository):
    """Every derived table's rows, sorted - the whole content a full
    rebuild is supposed to reproduce byte-for-byte against the incremental
    path (#21 AC 2), ``records`` (the FTS5 full-text index) included:
    ``SELECT *`` works on an fts5 table the same as on any other.

    ``extraction_meta.derived_at`` is dropped: it is a wall-clock reading
    of *when* a derive ran, not content the derive computed, and two
    derives never run at the same instant. Comparing it would make the
    parity assertion a coin flip on whether the two calls happened to
    land in the same second.
    """
    from memoria.index import DERIVED_TABLES

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        dump = {
            table: sorted(con.execute(f"SELECT * FROM {table}").fetchall())
            for table in DERIVED_TABLES
        }
    finally:
        con.close()
    dump["extraction_meta"] = [
        row for row in dump["extraction_meta"] if row[0] != "derived_at"
    ]
    return dump


def test_a_full_rebuild_is_byte_identical_to_the_incremental_path(tmp_path):
    """AC 2: whether the corpus arrives all at once - a fresh ``memoria
    rebuild`` over the whole evidence root, done once - or paragraph by
    paragraph, the way normal operation does it (normalize, extract, then
    ``memoria rebuild`` again after every new record), the final derived
    state must be the same.

    This is a real property, not a tautology: ``extraction.derive`` and
    ``compute_appearances`` both recompute wholesale from the memo cache and
    the current entries on every call rather than appending, so nothing
    about *when* a paragraph was memoized should be visible in what a later
    rebuild produces. A rebuild that quietly depended on call history would
    fail this test without failing any other in this suite.
    """
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    records = [
        _record("SRC-000001", ["Bob went to town.", "Nothing about him here."]),
        _record("SRC-000002", ["Bob wrote a letter."]),
    ]
    readings = {
        "src-000001-p1": {"placements": [_place("SUB-people/bob", "Bob")]},
        "src-000001-p2": {},
        "src-000002-p1": {"placements": [_place("SUB-people/bob", "Bob")]},
    }

    incremental = tmp_path / "incremental"
    incremental.mkdir()
    _write_entry(incremental, entry)
    repo_incremental = Repository(root=incremental)
    for count in range(1, len(records) + 1):
        write_normalized_records(
            records[:count], incremental / NORMALIZED_RELATIVE_PATH
        )
        build_index(repo_incremental, records[:count])
        prefix = records[count - 1].id.lower()
        for anchor, kwargs in readings.items():
            if anchor.startswith(prefix):
                _memo(repo_incremental, anchor, **kwargs)
        ex.derive(repo_incremental)
        compute_appearances(repo_incremental)

    full = tmp_path / "full"
    full.mkdir()
    _write_entry(full, entry)
    repo_full = Repository(root=full)
    write_normalized_records(records, full / NORMALIZED_RELATIVE_PATH)
    for anchor, kwargs in readings.items():
        _memo(repo_full, anchor, **kwargs)
    rebuild(repo_full)

    assert _dump_derived(repo_incremental) == _dump_derived(repo_full)
    assert gather(repo_incremental, "SUB-people/bob") == gather(
        repo_full, "SUB-people/bob"
    )


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
    overlay of its own (AC 5) and ``compute_appearances`` never touches an
    entry file."""
    _git(tmp_path, "init", "-q")
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
    # writes to the entry file, so the only overlay row anywhere is the
    # exclude just made.
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


@pytest.mark.parametrize("entry_id", ["SUB-themes/control", "SUB-arcs/departure"])
def test_themes_and_arcs_have_no_appearances_engine(entry_id):
    assert appearances_supported(entry_id) is False


@pytest.mark.parametrize(
    "entry_id", ["SUB-people/bob", "SUB-events/acquisition", "SUB-timeline/1962"]
)
def test_every_lexically_matchable_subject_has_one(entry_id):
    assert appearances_supported(entry_id) is True


def test_an_empty_appearances_list_means_two_different_things(tmp_path):
    """The predicate exists because `list_appearances` cannot say which.
    For a Person an empty list means the lexical pass found nothing; for a
    Theme it means the pass never ran, and will not until the audit at M5 -
    and a surface that renders both as "no appearances" is telling the
    author something false about their own archive."""
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    control = Entry(id="SUB-themes/control", match_terms=["SUB-people/bob"], body="")
    repository = Repository(root=tmp_path)
    _write_entry(tmp_path, bob)
    _write_entry(tmp_path, control)
    book = _record("SRC-000001", ["Carol argued with Dave."], source_type="book")
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])
    compute_appearances(repository)

    assert list_appearances(repository, "SUB-people/bob") == []
    assert list_appearances(repository, "SUB-themes/control") == []
    assert appearances_supported("SUB-people/bob") is True
    assert appearances_supported("SUB-themes/control") is False


def test_appeared_entry_ids_over_a_missing_index_returns_no_entries(tmp_path):
    """#155: the branch `list_appearances` and `appeared_entry_ids` share -
    a fresh clone, no `.memoria/index.db` yet - is exercised by every
    `list_appearances` caller in this file but never directly for
    `appeared_entry_ids` itself, the read `drift.compute_drift` uses for
    the covered side of a brief's drift."""
    repository = Repository(root=tmp_path)

    assert appeared_entry_ids(repository) == frozenset()
    assert not (tmp_path / INDEX_RELATIVE_PATH).exists()


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
