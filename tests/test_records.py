"""The on-disk record format, both directions.

Both halves live in ``memoria.records`` (ADR-0004). These tests pin the
contract between them, which is the only thing keeping the format
round-trippable now that no normalizer produces records
(docs/open-problems.md 2.4).

The read side proper - the composed ``read(ref)``, its reference forms and
its errors - is exercised in ``test_read_ref.py``.
"""

from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    read_all,
    record_to_markdown,
    write_normalized_records,
)
from memoria.repository import Repository


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
