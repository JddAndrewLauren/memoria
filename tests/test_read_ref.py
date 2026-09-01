"""`read(ref)` - the composed read, and the constraint it may not weaken.

`docs/poc-plan.md` §7: **retrieval is a superset of grep.** An evidence read
returns verbatim source text, never a summary in its place, and a raw
undecorated full-source read stays available. These tests are what make that
checkable rather than merely asserted, so they compare bytes rather than
substrings.
"""

import pytest
import yaml

from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    ReadError,
    parse_record,
    read,
    record_to_markdown,
    write_normalized_records,
)
from memoria.repository import Repository

# Whitespace chosen to break a naive parser: a paragraph that contains its own
# blank line (so blank-line splitting would cut it in two), one with leading
# indentation and internal newlines (so .strip() would eat the verse's shape),
# and one with trailing spaces.
AWKWARD = [
    "A blue heron flew over the pond.",
    "    Indented verse line one,\n      deeper line two,\nand back out again.",
    "A paragraph carrying\n\nits own blank line.",
    "Trailing spaces survive.   ",
]


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
        paragraphs=list(AWKWARD),
    )
    fields.update(overrides)
    return NormalizedRecord(**fields)


def _repo(tmp_path, *records):
    write_normalized_records(
        list(records) or [_record()], tmp_path / NORMALIZED_RELATIVE_PATH
    )
    return Repository(root=tmp_path)


# --- the parser is the serializer's exact inverse --------------------------


def test_parse_record_is_the_exact_inverse_of_record_to_markdown():
    """Round-trips the record, and then the bytes.

    Dataclass equality alone would pass a parser that normalized whitespace
    consistently in both directions; comparing the re-serialized text as well
    is what pins the format itself.
    """
    original = _record(
        recipient="MRS. LUCY BROWN", dateline="Concord", salutation="Dear friend,"
    )
    text = record_to_markdown(original)

    assert parse_record(text) == original
    assert record_to_markdown(parse_record(text)) == text


@pytest.mark.parametrize(
    "record",
    [
        NormalizedRecord(
            id="SRC-000002",
            source_type="journal",
            recorded_date="",
            event_date="",
            date_confidence="chapter-only",
            contemporaneous=True,
            original_file="raw/vol-01/text.txt",
            original_locator="Chapter I, undated fragment 3 of 29",
            paragraphs=[],
        ),
        NormalizedRecord(
            id="SRC-000700",
            source_type="book",
            recorded_date="1854",
            event_date="1854",
            date_confidence="published",
            contemporaneous=False,
            original_file="raw/books/walden.txt",
            original_locator="Walden, Economy",
            paragraphs=["One paragraph."],
            work="Walden",
            chapter="Economy",
        ),
    ],
    ids=["no-paragraphs", "book-fields"],
)
def test_every_shape_the_schema_allows_round_trips(record):
    text = record_to_markdown(record)
    assert parse_record(text) == record
    assert record_to_markdown(parse_record(text)) == text


def test_contemporaneous_must_be_a_real_boolean():
    """A truthy string would silently invert the retrospective filter (#12)."""
    text = record_to_markdown(_record()).replace(
        "contemporaneous: true", "contemporaneous: 'false'"
    )
    with pytest.raises(ReadError, match="must be a YAML boolean"):
        parse_record(text)


def test_a_field_the_schema_does_not_define_is_named_not_swallowed():
    text = record_to_markdown(_record()).replace(
        "source_type: journal", "source_type: journal\nmood: pensive"
    )
    with pytest.raises(ReadError, match="mood"):
        parse_record(text)


def test_an_anchor_the_records_id_contradicts_is_refused():
    """Anchors are derivable, so a file asserting a different one is corrupt."""
    text = record_to_markdown(_record()).replace(
        '<a id="src-000184-p1">', '<a id="src-000999-p1">'
    )
    with pytest.raises(ReadError, match="anchors do not match"):
        parse_record(text)


# --- verbatim ---------------------------------------------------------------


@pytest.mark.parametrize("number", range(1, len(AWKWARD) + 1))
def test_a_paragraph_read_is_byte_identical_to_the_paragraph(tmp_path, number):
    repository = _repo(tmp_path)

    result = read(repository, f"SRC-000184 P{number}")

    assert result.text == AWKWARD[number - 1]
    assert result.text.encode("utf-8") == AWKWARD[number - 1].encode("utf-8")


def test_a_paragraph_read_carries_no_envelope_in_its_text(tmp_path):
    """`text` is the payload and nothing else, so adapters cannot smuggle
    anything into what a byte comparison checks."""
    result = read(_repo(tmp_path), "SRC-000184 P1")

    assert result.text == AWKWARD[0]
    assert "ref:" not in result.text
    assert "<a id=" not in result.text


def test_a_full_source_read_is_byte_identical_to_the_file(tmp_path):
    """The undecorated full-source read: exactly what `cat` gives.

    Nothing decorates a read yet, so this is trivially true today - and it is
    pinned here precisely so that it cannot quietly stop being true when the
    curated overlay arrives (#20).
    """
    repository = _repo(tmp_path)
    path = tmp_path / NORMALIZED_RELATIVE_PATH / "SRC-000184.md"

    result = read(repository, "SRC-000184")

    assert result.text.encode("utf-8") == path.read_bytes()
    assert result.paragraph is None


def test_a_full_source_read_contains_every_paragraph_verbatim(tmp_path):
    result = read(_repo(tmp_path), "SRC-000184")

    for paragraph in AWKWARD:
        assert paragraph in result.text


def test_a_path_read_is_byte_identical_to_the_file(tmp_path):
    (tmp_path / "docs").mkdir()
    contents = "# A note\n\n    indented\n\nend\n"
    (tmp_path / "docs" / "note.md").write_text(contents, encoding="utf-8")

    result = read(Repository(root=tmp_path), "docs/note.md")

    assert result.text.encode("utf-8") == (tmp_path / "docs" / "note.md").read_bytes()


def test_reading_a_record_by_path_and_by_id_agree_byte_for_byte(tmp_path):
    repository = _repo(tmp_path)

    by_id = read(repository, "SRC-000184")
    by_path = read(repository, f"{NORMALIZED_RELATIVE_PATH}/SRC-000184.md")

    assert by_id.text == by_path.text


@pytest.mark.parametrize(
    "ref",
    ["SRC-000184#SRC-000184-P17", "#SRC-000184-P17", "SRC-000184 P1"],
)
def test_a_citation_retyped_in_capitals_still_resolves(tmp_path, ref):
    """A model retyping a markdown citation will capitalise it.

    The anchor patterns were always case-insensitive; taking the number off
    the end was not, so these used to crash with a ValueError that escaped
    the ReadError boundary and reached the model reason-stripped.
    """
    paragraph = 17 if "17" in ref else 1
    record = _record(paragraphs=[f"Paragraph {n}." for n in range(1, 18)])
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)

    assert read(Repository(root=tmp_path), ref).paragraph == paragraph


def test_a_search_result_anchor_reads_the_paragraph_that_matched(tmp_path):
    from memoria.index import INDEX_RELATIVE_PATH, build_index, search

    repository = _repo(tmp_path)
    build_index(repository.root / INDEX_RELATIVE_PATH, [_record()])

    (hit,) = search(repository, "heron")

    assert read(repository, hit.anchor).text == AWKWARD[0]


# --- errors name what went wrong -------------------------------------------


@pytest.mark.parametrize(
    ("ref", "kind"),
    [
        ("SES-20260912-1432", "SES"),
        ("SES-20260912-1432#T017", "SES"),
        ("CHG-20261014-0917", "CHG"),
        ("CLM-0041", "CLM"),
        ("RES-20261018-003", "RES"),
        ("DEC-0088", "DEC"),
        ("SUB-people", "SUB"),
        ("SUB-people/bob", "SUB"),
    ],
)
def test_a_not_yet_existing_kind_names_the_kind(tmp_path, ref, kind):
    with pytest.raises(ReadError) as caught:
        read(_repo(tmp_path), ref)

    assert kind in str(caught.value)
    assert "not resolvable in this build yet" in str(caught.value)


def test_an_unknown_kind_is_named_rather_than_treated_as_a_path(tmp_path):
    with pytest.raises(ReadError, match="unknown reference kind FOO-"):
        read(_repo(tmp_path), "FOO-0001")


def test_a_missing_record_and_an_un_normalized_repository_differ(tmp_path):
    """An empty corpus is an honest state, not a missing file (ADR-0004)."""
    with pytest.raises(ReadError, match="no such record"):
        read(_repo(tmp_path), "SRC-000999")

    empty = Repository(root=tmp_path / "fresh-checkout")
    with pytest.raises(ReadError, match="no normalized records"):
        read(empty, "SRC-000184")


def test_a_paragraph_past_the_end_says_how_many_there_are(tmp_path):
    with pytest.raises(ReadError, match="has 4 paragraphs"):
        read(_repo(tmp_path), "SRC-000184 P99")


def test_a_missing_repository_file_is_a_clear_error(tmp_path):
    with pytest.raises(ReadError, match="no such file in this repository"):
        read(Repository(root=tmp_path), "docs/absent.md")


@pytest.mark.parametrize(
    "ref",
    [
        "../escape",
        "/etc/passwd",
        "SRC-184",
        "",
        ".",                            # PurePosixPath('.').parts is empty
        "./",
        "docs\\..\\x",                  # backslash separators
        "C:/Windows/x",
    ],
)
def test_a_reference_that_cannot_be_parsed_is_a_read_error(tmp_path, ref):
    """One error type crosses the core boundary, so an adapter catching
    ReadError cannot miss a case and strip its message."""
    with pytest.raises(ReadError):
        read(_repo(tmp_path), ref)


# --- reads stay inside the repository --------------------------------------


def test_a_symlink_out_of_the_repository_is_refused(tmp_path):
    """The case the reference check cannot see.

    `link.md` is an ordinary relative path; only the resolved target leaves
    the tree. Refusing it is what makes "reads are confined to the
    repository" true rather than merely intended.
    """
    root = tmp_path / "repo"
    root.mkdir()
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("SECRET\n", encoding="utf-8")
    (root / "link.md").symlink_to(secret)

    with pytest.raises(ReadError, match="escapes the repository"):
        read(Repository(root=root), "link.md")


def test_a_symlink_inside_the_repository_still_reads(tmp_path):
    """Confinement, not a ban on symlinks."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "real.md").write_text("# real\n", encoding="utf-8")
    (root / "alias.md").symlink_to(root / "docs" / "real.md")

    assert read(Repository(root=root), "alias.md").text == "# real\n"


def test_a_symlinked_repository_root_is_not_refused_wholesale(tmp_path):
    """Both roots resolve before comparison.

    A worktree reached through a symlink would otherwise fail every read.
    """
    real = tmp_path / "real-repo"
    real.mkdir()
    (real / "note.md").write_text("# note\n", encoding="utf-8")
    link = tmp_path / "via-link"
    link.symlink_to(real)

    assert read(Repository(root=link), "note.md").text == "# note\n"


@pytest.mark.parametrize(
    "paragraphs",
    [
        ['Quoting <a id="src-000184-p2"></a> inline.', "Second."],
        # The dangerous shape: at a paragraph boundary this reads back as two
        # paragraphs AND re-serializes byte-identically, so a round-trip
        # assertion sees nothing wrong while every later citation index is off
        # by one.
        ['A\n\n<a id="src-000184-p2"></a>\n\nB'],
    ],
    ids=["inline", "at-a-boundary"],
)
def test_a_paragraph_containing_an_anchor_is_refused_at_write_time(paragraphs):
    """The one input the format cannot represent.

    The format has no escaping, so by read time the two cases are the same
    bytes and cannot be told apart. Writing is therefore the only place the
    ambiguity can be caught with certainty - which is why the refusal lives in
    the serializer rather than the parser.
    """
    with pytest.raises(ValueError, match="contains a paragraph anchor"):
        record_to_markdown(_record(paragraphs=paragraphs))


def test_the_boundary_case_is_why_a_round_trip_assertion_is_not_enough():
    """Guards the reasoning above, not just the behaviour.

    If someone ever relaxes the write-time refusal, this records why a
    round-trip test would not have caught the regression.
    """
    record = _record(paragraphs=['A\n\n<a id="src-000184-p2"></a>\n\nB'])
    text = (
        "---\n"
        + yaml.safe_dump(
            {
                "id": record.id,
                "source_type": record.source_type,
                "recorded_date": record.recorded_date,
                "event_date": record.event_date,
                "date_confidence": record.date_confidence,
                "contemporaneous": record.contemporaneous,
                "original_file": record.original_file,
                "original_locator": record.original_locator,
            },
            sort_keys=False,
        )
        + "---\n\n"
        + f'<a id="src-000184-p1"></a>\n\n{record.paragraphs[0]}\n'
    )

    parsed = parse_record(text)

    assert len(parsed.paragraphs) == 2          # not 1, as written
    assert record_to_markdown(parsed) == text   # and the round trip agrees
