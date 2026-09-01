from memoria.index import INDEX_RELATIVE_PATH, build_index, rebuild, search
from memoria.repository import Repository
from memoria.records import NormalizedRecord


def _record(record_id, paragraphs, source_type="journal"):
    return NormalizedRecord(
        id=record_id,
        source_type=source_type,
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="unresolved",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=paragraphs,
    )


def test_search_finds_a_record_by_its_paragraph_text(tmp_path):
    db_path = tmp_path / "index.db"
    records = [_record("SRC-000001", ["The fox ran through the woods."])]

    build_index(db_path, records)
    results = search(db_path, "fox")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000001"


def test_search_returns_the_specific_paragraph_anchor_that_matched(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record(
            "SRC-000002",
            ["First paragraph, no match here.", "Second paragraph mentions a badger."],
        )
    ]

    build_index(db_path, records)
    results = search(db_path, "badger")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000002"
    assert results[0].anchor == "src-000002-p2"


def test_search_can_exclude_editorial_records(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record("SRC-000003", ["He saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]

    build_index(db_path, records)
    results = search(db_path, "heron", exclude_editorial=True)

    assert [r.src_id for r in results] == ["SRC-000003"]


def test_search_includes_editorial_records_by_default(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record("SRC-000003", ["He saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]

    build_index(db_path, records)
    results = search(db_path, "heron")

    assert {r.src_id for r in results} == {"SRC-000003", "SRC-000004"}


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

    rebuild(Repository(root=tmp_path))
    db_path = tmp_path / INDEX_RELATIVE_PATH
    before = [(r.src_id, r.anchor) for r in search(db_path, "heron")]
    assert before

    db_path.unlink()
    rebuild(Repository(root=tmp_path))

    assert [(r.src_id, r.anchor) for r in search(db_path, "heron")] == before


def test_rebuild_reports_no_records_when_none_exist(tmp_path):
    """With no corpus chosen there is nothing to index, and that is not an
    error - it is the honest state."""
    assert rebuild(Repository(root=tmp_path)) == []
