"""`read(ref)` - the composed read, and the constraint it may not weaken.

`docs/poc-plan.md` §7: **retrieval is a superset of grep.** An evidence read
returns verbatim source text, never a summary in its place, and a raw
undecorated full-source read stays available. These tests are what make that
checkable rather than merely asserted, so they compare bytes rather than
substrings.
"""

import sqlite3
import subprocess

import pytest
import yaml

from memoria import extraction as ex
from memoria.index import INDEX_RELATIVE_PATH, ReadOverlay, build_index, exclude, pin
from memoria.manuscript import create_chapter, create_section
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
from memoria.subjects import Entry, entry_to_markdown
from memoria.write import Actor

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
    from memoria.index import build_index, search

    repository = _repo(tmp_path)
    build_index(repository, [_record()])

    (hit,) = search(repository, "heron")

    assert read(repository, hit.anchor).text == AWKWARD[0]


# --- chapters and sections resolve by stable ID (#35) -----------------------


def test_read_resolves_a_chapter_by_its_stable_id(tmp_path):
    repository = Repository(root=tmp_path)
    chapter = create_chapter(repository, "This chapter covers 1839 to 1841.")

    result = read(repository, chapter.brief.id)

    assert result.text == (tmp_path / "chapters" / "01" / "chapter.md").read_text(
        encoding="utf-8"
    )
    assert result.citation == chapter.brief.id


def test_read_resolves_a_section_by_its_stable_id(tmp_path):
    repository = Repository(root=tmp_path)
    chapter = create_chapter(repository, "Chapter.")
    section = create_section(repository, chapter.number, "The section's own brief.")

    result = read(repository, section.brief.id)

    assert "The section's own brief." in result.text


def test_a_chapter_reference_still_resolves_after_a_reorder(tmp_path):
    """The stable ID, not the directory position, is what read(ref) uses."""
    from memoria.manuscript import reorder_chapters

    repository = Repository(root=tmp_path)
    first = create_chapter(repository, "First.")
    second = create_chapter(repository, "Second.")

    reorder_chapters(repository, [second.brief.id, first.brief.id])

    assert read(repository, first.brief.id).text.endswith("First.\n")
    assert read(repository, second.brief.id).text.endswith("Second.\n")


def test_reading_an_unresolvable_chapter_or_section_id_names_it(tmp_path):
    repository = Repository(root=tmp_path)
    with pytest.raises(ReadError, match="CHP-0001"):
        read(repository, "CHP-0001")
    with pytest.raises(ReadError, match="SEC-0001"):
        read(repository, "SEC-0001")


# --- errors name what went wrong -------------------------------------------


@pytest.mark.parametrize(
    ("ref", "kind"),
    [
        ("CLM-0041", "CLM"),
    ],
)
def test_a_not_yet_existing_kind_names_the_kind(tmp_path, ref, kind):
    with pytest.raises(ReadError) as caught:
        read(_repo(tmp_path), ref)

    assert kind in str(caught.value)
    assert "not resolvable in this build yet" in str(caught.value)


def test_reading_a_nonexistent_decision_or_research_memo_names_it(tmp_path):
    """DEC-/RES- are implemented (#30); an id that does not exist is an
    ordinary named refusal, not the generic "not resolvable" message."""
    repository = _repo(tmp_path)
    with pytest.raises(ReadError, match="DEC-0088"):
        read(repository, "DEC-0088")
    with pytest.raises(ReadError, match="RES-20261018-003"):
        read(repository, "RES-20261018-003")


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


def test_a_paragraph_reference_skips_page_markers(tmp_path):
    """¶2 addresses the second real paragraph, not the marker between them -
    a marker earns no extraction read (docs/normalized-record-schema.md,
    "pdf page markers are not paragraphs")."""
    repository = _repo(
        tmp_path,
        _record(paragraphs=["Page one.", "<!-- page 2 -->", "Page two."]),
    )

    result = read(repository, "SRC-000184 P2")

    assert result.text == "Page two."


def test_a_paragraph_count_past_the_end_excludes_page_markers(tmp_path):
    repository = _repo(
        tmp_path,
        _record(paragraphs=["Page one.", "<!-- page 2 -->", "Page two."]),
    )

    with pytest.raises(ReadError, match="has 2 paragraphs"):
        read(repository, "SRC-000184 P99")


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
                "raw_sha256": record.raw_sha256,
                "converter": record.converter,
            },
            sort_keys=False,
        )
        + "---\n\n"
        + f'<a id="src-000184-p1"></a>\n\n{record.paragraphs[0]}\n'
    )

    parsed = parse_record(text)

    assert len(parsed.paragraphs) == 2          # not 1, as written
    assert record_to_markdown(parsed) == text   # and the round trip agrees


# --- SUB- subjects and entries (issue #16) ----------------------------------


def test_a_subject_read_is_byte_identical_to_the_file(tmp_path):
    from memoria.subjects import subject_to_markdown, write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    path = tmp_path / "subjects" / "people" / "_subject.md"

    result = read(repository, "SUB-people")

    assert result.text.encode("utf-8") == path.read_bytes()


def test_an_entry_read_is_byte_identical_to_the_file(tmp_path):
    from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    entry_path.write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["Bob"], body="Testimony.")
        ),
        encoding="utf-8",
    )

    result = read(repository, "SUB-people/bob")

    assert result.text.encode("utf-8") == entry_path.read_bytes()


def test_an_entry_read_resolves_even_after_the_file_is_renamed(tmp_path):
    from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    entry_path = tmp_path / "subjects" / "people" / "some-other-name.md"
    entry_path.write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["Bob"], body="Testimony.")
        ),
        encoding="utf-8",
    )

    result = read(repository, "SUB-people/bob")

    assert result.text.encode("utf-8") == entry_path.read_bytes()


def test_a_missing_subject_names_the_subject(tmp_path):
    with pytest.raises(ReadError, match="no such subject: SUB-nonesuch"):
        read(Repository(root=tmp_path), "SUB-nonesuch")


def test_a_missing_entry_names_the_entry(tmp_path):
    from memoria.subjects import write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)

    with pytest.raises(ReadError, match="no such entry: SUB-people/nonesuch"):
        read(repository, "SUB-people/nonesuch")


def test_reading_a_renamed_entry_survives_an_unrelated_malformed_sibling(tmp_path):
    """Reproduces PR #84 review round 1: a typo'd match term in a sibling
    file must not stop read() from finding a validly renamed entry."""
    from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    subjects_dir = tmp_path / "subjects" / "people"
    (subjects_dir / "bob.md").write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["SUB-People/Bob"], body="Bob.")
        ),
        encoding="utf-8",
    )
    carol_path = subjects_dir / "renamed-carol.md"
    carol_path.write_text(
        entry_to_markdown(Entry(id="SUB-people/carol", body="Carol.")),
        encoding="utf-8",
    )

    result = read(repository, "SUB-people/carol")

    assert result.text.encode("utf-8") == carol_path.read_bytes()


def test_a_malformed_entry_file_reaches_read_as_a_readerror_not_a_subjecterror(
    tmp_path,
):
    """A SubjectError from the subjects module must never cross read()'s
    boundary - the same rule already enforced for references.BadReference,
    and load-bearing at the MCP tool boundary, which catches ReadError
    alone (docs/tool-surface.md)."""
    from memoria.subjects import SubjectError, write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    subjects_dir = tmp_path / "subjects" / "people"
    (subjects_dir / "bob.md").write_text(
        "---\nid: SUB-people/bob\nmatch_terms: [SUB-People/Bob]\n---\n\nBob.\n",
        encoding="utf-8",
    )

    try:
        read(repository, "SUB-people/bob")
        raised = None
    except Exception as exc:
        raised = exc

    assert isinstance(raised, ReadError)
    assert not isinstance(raised, SubjectError)


def test_a_snippet_is_not_a_reference(tmp_path):
    """A snippet can never be round-tripped into `read` (#95).

    It is a match locator, not an identifier: it falls through to the
    documented path fallback (`references.parse`) and fails as a read, rather
    than resolving to anything. The anchor beside it is what `read` takes.
    """
    from memoria.index import (
        SNIPPET_MATCH_END,
        SNIPPET_MATCH_START,
        build_index,
        search,
    )

    repository = _repo(tmp_path)
    build_index(repository, [_record()])

    (hit,) = search(repository, "heron", snippet=True)
    assert SNIPPET_MATCH_START in hit.snippet and SNIPPET_MATCH_END in hit.snippet

    with pytest.raises(ReadError):
        read(repository, hit.snippet)

    # The anchor on the same hit does resolve - that is the path evidence takes.
    assert read(repository, hit.anchor).text


# --- raw: the pre-normalization original (#113) -----------------------------


def _repo_with_evidence(tmp_path, *records):
    write_normalized_records(
        list(records) or [_record()], tmp_path / NORMALIZED_RELATIVE_PATH
    )
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text(
        "The unnormalized text.\n", encoding="utf-8"
    )
    return Repository(root=tmp_path, evidence_root=evidence_root)


def test_raw_read_serves_the_pre_normalization_original(tmp_path):
    result = read(_repo_with_evidence(tmp_path), "SRC-000184", raw=True)

    assert result.text == "The unnormalized text.\n"


def test_raw_read_is_bare_like_the_full_source_read(tmp_path):
    """No header, no delimiter - the same undecorated contract (#113)."""
    result = read(_repo_with_evidence(tmp_path), "SRC-000184", raw=True)

    assert result.paragraph is None
    assert "ref:" not in result.text
    assert "original_locator" not in result.text


def test_raw_reads_citation_is_marked_raw(tmp_path):
    """The ledger names a raw read as the original, not the record (#113)."""
    result = read(_repo_with_evidence(tmp_path), "SRC-000184", raw=True)

    assert result.citation == "SRC-000184 raw"


def test_raw_serves_a_paragraph_undecorated(tmp_path):
    """#20's second meaning for the same flag: a paragraph `raw` read
    succeeds, with no curated overlay attached and the same text a plain
    read gives."""
    repository = _repo_with_evidence(tmp_path)

    result = read(repository, "SRC-000184 P1", raw=True)

    assert result.overlay is None
    assert result.paragraph == 1
    assert result.text == read(repository, "SRC-000184 P1").text
    assert result.citation == "SRC-000184 ¶1 raw"


def test_raw_is_refused_for_a_path_reference(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("# note\n", encoding="utf-8")

    with pytest.raises(ReadError, match="raw only serves a SRC- reference"):
        read(Repository(root=tmp_path), "docs/note.md", raw=True)


def test_raw_is_refused_for_a_subject_reference(tmp_path):
    from memoria.subjects import write_builtin_subjects

    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)

    with pytest.raises(ReadError, match="raw only serves a SRC- reference"):
        read(repository, "SUB-people", raw=True)


def test_raw_without_an_evidence_root_raises_the_named_refusal(tmp_path):
    """The same `NoEvidenceRoot`, not a `ReadError` in its shape (#113)."""
    from memoria.repository import NoEvidenceRoot

    with pytest.raises(NoEvidenceRoot):
        read(_repo(tmp_path), "SRC-000184", raw=True)


def test_raw_refuses_a_binary_original_naming_its_type(tmp_path):
    write_normalized_records(
        [_record(original_file="raw/vol-01/letter.docx")],
        tmp_path / NORMALIZED_RELATIVE_PATH,
    )
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "letter.docx").write_bytes(
        b"\xff\xfenot valid utf-8"
    )
    repository = Repository(root=tmp_path, evidence_root=evidence_root)

    with pytest.raises(ReadError, match=r"\.docx"):
        read(repository, "SRC-000184", raw=True)


def test_raw_over_an_unresolvable_reference_names_the_reference(tmp_path):
    """The reference is judged before the raw capability is (#113 review).

    `CLM-` resolves to no kind here, so that - not the raw refusal - is what
    the caller has to fix first.
    """
    with pytest.raises(ReadError) as caught:
        read(_repo(tmp_path), "CLM-0041", raw=True)

    assert "not resolvable in this build yet" in str(caught.value)
    assert "raw only serves" not in str(caught.value)


def test_raw_over_an_unknown_kind_names_the_kind(tmp_path):
    with pytest.raises(ReadError, match="unknown reference kind FOO-"):
        read(_repo(tmp_path), "FOO-0001", raw=True)


def test_raw_refuses_a_resolvable_session_reference(tmp_path):
    """`SES-` resolves (#28), so the raw guard - not "not resolvable" - is
    what fires: a transcript carries neither an `original_file` nor an
    overlay to strip."""
    with pytest.raises(ReadError, match="raw only serves"):
        read(_repo(tmp_path), "SES-20260912-1432", raw=True)


def test_raw_refuses_a_non_utf8_text_original_without_calling_it_binary(tmp_path):
    """A latin-1 .txt is text, just not UTF-8 - say that (#113 review)."""
    write_normalized_records(
        [_record(original_file="raw/vol-01/letter.txt")],
        tmp_path / NORMALIZED_RELATIVE_PATH,
    )
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "letter.txt").write_bytes(
        "A caf\N{LATIN SMALL LETTER E WITH ACUTE} in Concord.\n".encode("latin-1")
    )
    repository = Repository(root=tmp_path, evidence_root=evidence_root)

    with pytest.raises(ReadError) as caught:
        read(repository, "SRC-000184", raw=True)

    message = str(caught.value)
    assert "does not decode as UTF-8" in message
    assert "text in another encoding" in message


# --- the curated overlay (#20) -----------------------------------------------

_AUTHOR = Actor(name="Author", email="author@example.com")


def _write_entry(tmp_path, entry):
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry))


def _overlay_repo(tmp_path, entries=()):
    """The default `_record()`, indexed, with `entries` written to disk -
    the shape a decorated read's overlay needs beneath it. A real
    (uncommitted) git repository: `pin`/`exclude` now write the entry file
    through the durable write path (#21), which commits."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    for entry in entries:
        _write_entry(tmp_path, entry)
    record = _record()
    repository = _repo(tmp_path, record)
    build_index(repository, [record])
    return repository


def test_a_decorated_paragraph_read_names_the_entries_it_is_placed_in(tmp_path):
    """AC 1: entry links come back alongside the verbatim text."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    ex.record_extraction(
        repository,
        "src-000184-p1",
        ex.ParagraphExtraction(
            placements=(ex.ProposedPlacement("SUB-people/bob", "heron"),)
        ),
    )
    ex.derive(repository)

    result = read(repository, "SRC-000184 P1")

    assert result.overlay == ReadOverlay(
        entry_links=["SUB-people/bob"], exclusions=[], citing_settlements=[]
    )


def test_the_decorated_texts_verbatim_text_is_byte_identical_to_the_undecorated_read(
    tmp_path,
):
    """AC 2, with an overlay actually present - decoration is a sibling
    field, never folded into `text`."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    ex.record_extraction(
        repository,
        "src-000184-p1",
        ex.ParagraphExtraction(
            placements=(ex.ProposedPlacement("SUB-people/bob", "heron"),)
        ),
    )
    ex.derive(repository)

    decorated = read(repository, "SRC-000184 P1")
    undecorated = read(repository, "SRC-000184 P1", raw=True)

    assert decorated.overlay is not None
    assert undecorated.overlay is None
    assert decorated.text == undecorated.text == AWKWARD[0]


def test_a_full_source_read_is_unaffected_by_the_overlay(tmp_path):
    """AC 3: the raw undecorated full-source read stays exactly what it was
    - `read`'s overlay only ever attaches to a paragraph."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    ex.record_extraction(
        repository,
        "src-000184-p1",
        ex.ParagraphExtraction(
            placements=(ex.ProposedPlacement("SUB-people/bob", "heron"),)
        ),
    )
    ex.derive(repository)

    result = read(repository, "SRC-000184")

    assert result.overlay is None


def test_a_paragraph_with_no_overlay_gets_an_explicit_empty_one(tmp_path):
    """AC 5: no overlay is a fully-shaped, empty `ReadOverlay`, not `None`
    and not a different return shape."""
    repository = _overlay_repo(tmp_path)

    result = read(repository, "SRC-000184 P1")

    assert result.overlay == ReadOverlay(
        entry_links=[], exclusions=[], citing_settlements=[]
    )


def test_entry_links_reflect_lexical_recall_not_just_placements(tmp_path):
    """Retry item 2 / AC 1: entry links are the gathered-set-inverse, not a
    placements-only narrowing of it - a paragraph an entry gathers purely
    through its word-shaped match terms' lexical recall (no extraction
    placement, no `ex.derive` at all) still names the entry, matching
    `gather`'s own membership exactly."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])

    result = read(repository, "SRC-000184 P1")

    assert result.overlay.entry_links == ["SUB-people/bob"]


def test_a_pin_adds_an_entry_link_with_no_placement_behind_it(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _overlay_repo(tmp_path, [entry])
    pin(repository, "SUB-people/bob", "src-000184-p1", _AUTHOR)

    result = read(repository, "SRC-000184 P1")

    assert result.overlay.entry_links == ["SUB-people/bob"]
    assert result.overlay.exclusions == []


def test_a_pin_or_exclusion_against_an_entry_no_longer_on_disk_is_dropped(tmp_path):
    """Retry item 3: a stale index must not name an entry that has been
    deleted or renamed since - `entry_links`/`exclusions` are scoped to
    `load_all_entries`, not to whatever the index rows still say.

    Both entries have to exist to be curated at all: since #21 the overlay
    lives on the entry file, so `pin`/`exclude` refuse an entry that is not
    on disk. The stale-row case is therefore reached by deleting the files
    afterwards, not by curating an entry that never existed."""
    bob = Entry(id="SUB-people/bob", match_terms=[], body="")
    carol = Entry(id="SUB-people/carol", match_terms=[], body="")
    repository = _overlay_repo(tmp_path, [bob, carol])
    pin(repository, "SUB-people/bob", "src-000184-p1", _AUTHOR)
    exclude(repository, "SUB-people/carol", "src-000184-p1", _AUTHOR)
    (tmp_path / "subjects" / "people" / "bob.md").unlink()
    (tmp_path / "subjects" / "people" / "carol.md").unlink()

    result = read(repository, "SRC-000184 P1")

    assert result.overlay.entry_links == []
    assert result.overlay.exclusions == []


def test_an_exclusion_drops_the_entry_link_but_is_still_named(tmp_path):
    """A curator act against a placement is reported, not hidden - the
    reader sees both that the entry excluded this paragraph and that it
    would otherwise have been linked."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    ex.record_extraction(
        repository,
        "src-000184-p1",
        ex.ParagraphExtraction(
            placements=(ex.ProposedPlacement("SUB-people/bob", "heron"),)
        ),
    )
    ex.derive(repository)
    exclude(repository, "SUB-people/bob", "src-000184-p1", _AUTHOR)

    result = read(repository, "SRC-000184 P1")

    assert result.overlay.entry_links == []
    assert result.overlay.exclusions == ["SUB-people/bob"]


def test_citing_settlements_is_always_empty_in_this_build(tmp_path):
    """Settlements are an M4 concept (docs/plan/16-build-order.md) with no
    durable storage yet - the field is served, not populated."""
    repository = _overlay_repo(tmp_path)

    result = read(repository, "SRC-000184 P1")

    assert result.overlay.citing_settlements == []


def test_a_decorated_read_is_rendered_with_the_overlay_delimited_from_text(tmp_path):
    """AC 4, at the adapter surface: the model-facing render, not just the
    core value, keeps decoration out of the verbatim text."""
    from memoria.mcp.server import render

    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    ex.record_extraction(
        repository,
        "src-000184-p1",
        ex.ParagraphExtraction(
            placements=(ex.ProposedPlacement("SUB-people/bob", "heron"),)
        ),
    )
    ex.derive(repository)

    rendered = render(read(repository, "SRC-000184 P1"))

    header, _, rest = rendered.partition("\n---\n")
    payload, _, overlay_block = rest.rpartition("\n---\n")
    assert payload == AWKWARD[0]
    assert "entry links: SUB-people/bob" in overlay_block


def test_a_stale_index_schema_degrades_the_overlay_rather_than_failing_the_read(
    tmp_path,
):
    """Retry item 1 (BLOCKER): an index predating #111's `email_from`/
    `email_to` columns must not turn a paragraph read that used to succeed
    into an `IndexSchemaError` - decoration is best-effort, and the
    verbatim text is never conditioned on it (poc-plan.md §7)."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("DROP TABLE paragraphs")
    con.execute(
        "CREATE TABLE paragraphs("
        "anchor TEXT PRIMARY KEY, src_id TEXT, source_type TEXT, "
        "event_date TEXT, recorded_date TEXT, contemporaneous INTEGER"
        ")"
    )
    con.commit()
    con.close()

    result = read(repository, "SRC-000184 P1")

    assert result.text == AWKWARD[0]
    assert result.overlay is None


def test_an_unreadable_index_file_degrades_the_overlay_rather_than_failing_the_read(
    tmp_path,
):
    """The same guarantee against a corrupted or mid-write index file, not
    just a stale schema - a `sqlite3.Error` of any kind degrades the
    overlay rather than the read, the same as a locked one held by a
    concurrent `memoria rebuild`."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _overlay_repo(tmp_path, [entry])
    (repository.root / INDEX_RELATIVE_PATH).write_bytes(b"not a sqlite file")

    result = read(repository, "SRC-000184 P1")

    assert result.text == AWKWARD[0]
    assert result.overlay is None
