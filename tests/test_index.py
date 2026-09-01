import sqlite3
import time

from memoria.index import (
    INDEX_RELATIVE_PATH,
    SNIPPET_ELLIPSIS,
    SNIPPET_MATCH_END,
    SNIPPET_MATCH_START,
    SearchFilters,
    build_index,
    filter_predicate,
    rebuild,
    search,
)
from memoria.repository import Repository
from memoria.records import NormalizedRecord


def _record(
    record_id,
    paragraphs,
    source_type="journal",
    event_date="Oct. 22.",
    recorded_date="Oct. 22.",
    contemporaneous=True,
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
    assert rebuild(Repository(root=tmp_path)) == []


def test_search_over_the_full_corpus_returns_well_under_a_second(tmp_path):
    records = [
        _record(f"SRC-{n:06d}", [f"Paragraph {n} mentions a heron by the pond."])
        for n in range(1, 2001)
    ]
    repository = _index(tmp_path, records)

    start = time.monotonic()
    results = search(repository, "heron")
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
