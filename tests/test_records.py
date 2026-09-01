"""The on-disk record format, both directions.

Both halves live in ``memoria.records`` (ADR-0004). These tests pin the
contract between them, which is the only thing keeping the format
round-trippable now that no normalizer produces records
(docs/open-problems.md 2.4).

The read side proper - the composed ``read(ref)``, its reference forms and
its errors - is exercised in ``test_read_ref.py``.
"""

import pytest

from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    ReadError,
    list_sources,
    read_all,
    read_raw_source,
    record_to_markdown,
    write_normalized_records,
)
from memoria.repository import NoEvidenceRoot, Repository


def _record(**overrides):
    fields = dict(
        id="SRC-000184",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22., 1845",
        date_confidence="inferred",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=["A blue heron flew over.", "Second paragraph here."],
    )
    fields.update(overrides)
    return NormalizedRecord(**fields)


def test_paragraph_anchors_use_the_documented_form():
    record = _record()
    assert record.anchor_id(1) == "src-000184-p1"
    assert record.anchor_id(17) == "src-000184-p17"


def test_serialized_record_carries_frontmatter_and_anchored_paragraphs():
    markdown = record_to_markdown(_record())
    assert markdown.startswith("---\n")
    assert "id: SRC-000184" in markdown
    assert '<a id="src-000184-p1"></a>' in markdown
    assert '<a id="src-000184-p2"></a>' in markdown


def test_type_specific_fields_are_absent_when_unset():
    """A journal record carries no empty recipient/work keys."""
    markdown = record_to_markdown(_record())
    for absent in ("recipient:", "dateline:", "salutation:", "work:", "chapter:"):
        assert absent not in markdown


def test_type_specific_fields_are_written_when_set():
    markdown = record_to_markdown(
        _record(source_type="letter", recipient="MRS. LUCY BROWN", dateline="Concord")
    )
    assert "recipient: MRS. LUCY BROWN" in markdown
    assert "dateline: Concord" in markdown


def test_record_carries_raw_sha256_and_converter():
    markdown = record_to_markdown(
        _record(raw_sha256="a" * 64, converter="plain-text 1")
    )
    assert f"raw_sha256: {'a' * 64}" in markdown
    assert "converter: plain-text 1" in markdown


def test_records_round_trip_through_disk(tmp_path):
    """Every field the index reads survives a write/read cycle."""
    original = _record()
    output_root = tmp_path / NORMALIZED_RELATIVE_PATH
    write_normalized_records([original], output_root)

    (loaded,) = read_all(Repository(root=tmp_path))

    # Every field, not a listed subset: the reader recovers the whole record
    # now, so anything it dropped would be a regression rather than a known
    # limit of the placeholder this replaced.
    assert loaded == original


def test_contemporaneous_round_trips_as_a_bool_not_a_string(tmp_path):
    """It is how temporal discipline reaches retrieval (#12), so a truthy
    string here would silently break the retrospective filter."""
    output_root = tmp_path / NORMALIZED_RELATIVE_PATH
    write_normalized_records(
        [_record(contemporaneous=True), _record(id="SRC-000185", contemporaneous=False)],
        output_root,
    )

    first, second = read_all(Repository(root=tmp_path))

    assert first.contemporaneous is True
    assert second.contemporaneous is False


def test_writing_removes_records_a_later_run_no_longer_produces(tmp_path):
    """A shrinking corpus must not leave stale orphans behind."""
    output_root = tmp_path / NORMALIZED_RELATIVE_PATH
    write_normalized_records(
        [_record(), _record(id="SRC-000185")], output_root
    )
    assert (output_root / "SRC-000185.md").exists()

    write_normalized_records([_record()], output_root)

    assert not (output_root / "SRC-000185.md").exists()
    assert (output_root / "SRC-000184.md").exists()


def test_reading_a_directory_that_does_not_exist_is_empty_not_an_error(tmp_path):
    """An un-normalized checkout is an empty corpus, not a failure."""
    assert read_all(Repository(root=tmp_path / "nothing-here")) == []


# --- list_sources (#64) -----------------------------------------------------


def _write(tmp_path, *records):
    write_normalized_records(list(records), tmp_path / NORMALIZED_RELATIVE_PATH)
    return Repository(root=tmp_path)


def test_list_sources_with_no_filters_returns_every_record(tmp_path):
    repository = _write(
        tmp_path, _record(id="SRC-000001"), _record(id="SRC-000002")
    )
    ids = {record.id for record in list_sources(repository)}
    assert ids == {"SRC-000001", "SRC-000002"}


def test_list_sources_filters_by_source_type(tmp_path):
    repository = _write(
        tmp_path,
        _record(id="SRC-000001", source_type="journal"),
        _record(id="SRC-000002", source_type="letter"),
    )
    (record,) = list_sources(repository, source_type="letter")
    assert record.id == "SRC-000002"


def test_list_sources_filters_by_date_confidence(tmp_path):
    repository = _write(
        tmp_path,
        _record(id="SRC-000001", date_confidence="exact"),
        _record(id="SRC-000002", date_confidence="unresolved"),
    )
    (record,) = list_sources(repository, date_confidence="unresolved")
    assert record.id == "SRC-000002"


def test_list_sources_filters_by_contemporaneous(tmp_path):
    repository = _write(
        tmp_path,
        _record(id="SRC-000001", contemporaneous=True),
        _record(id="SRC-000002", contemporaneous=False),
    )
    (record,) = list_sources(repository, contemporaneous=False)
    assert record.id == "SRC-000002"


def test_list_sources_filters_compose(tmp_path):
    repository = _write(
        tmp_path,
        _record(id="SRC-000001", source_type="journal", contemporaneous=True),
        _record(id="SRC-000002", source_type="journal", contemporaneous=False),
        _record(id="SRC-000003", source_type="letter", contemporaneous=True),
    )
    (record,) = list_sources(repository, source_type="journal", contemporaneous=True)
    assert record.id == "SRC-000001"


def test_list_sources_over_an_un_normalized_checkout_is_empty_not_an_error(tmp_path):
    """The same honest-empty-state discipline ``read_all`` has (ADR-0004)."""
    assert list_sources(Repository(root=tmp_path / "nothing-here")) == []


# --- read_raw_source (#64) --------------------------------------------------


def test_read_raw_source_returns_the_original_file_verbatim(tmp_path):
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    original = evidence_root / "raw" / "vol-01" / "text.txt"
    original.write_text("The unnormalized text.\n", encoding="utf-8")

    repository = _write(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=evidence_root)

    raw = read_raw_source(repository, "SRC-000184")

    assert raw.text == "The unnormalized text.\n"
    assert raw.original_locator == "Journal I, entry dated Oct. 22."


def test_read_raw_source_refuses_an_unknown_record(tmp_path):
    repository = _write(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=tmp_path / "evidence")

    with pytest.raises(ReadError):
        read_raw_source(repository, "SRC-000999")


def test_read_raw_source_refuses_a_missing_original_file(tmp_path):
    repository = _write(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=tmp_path / "evidence")

    with pytest.raises(ReadError):
        read_raw_source(repository, "SRC-000184")


def test_read_raw_source_without_an_evidence_root_is_a_named_refusal(tmp_path):
    repository = _write(tmp_path, _record())

    with pytest.raises(NoEvidenceRoot):
        read_raw_source(repository, "SRC-000184")


def test_read_raw_source_refuses_an_original_file_that_escapes_the_evidence_root(
    tmp_path,
):
    repository = _write(
        tmp_path, _record(original_file="../outside.txt")
    )
    repository = Repository(root=repository.root, evidence_root=tmp_path / "evidence")

    with pytest.raises(ReadError):
        read_raw_source(repository, "SRC-000184")
