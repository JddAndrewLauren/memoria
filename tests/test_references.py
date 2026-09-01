"""Reference parsing: the grammar `read(ref)` dispatches on.

Every accepted form is one a document or another slice actually produces, and
the test names say which - a form nobody emits would be surface area with no
caller.
"""

import pytest

from memoria import references
from memoria.index import build_index, search
from memoria.records import NormalizedRecord
from memoria.references import (
    BadReference,
    PathReference,
    SourceReference,
    UnknownReference,
)


def test_parse_resolves_a_bare_src_id():
    assert references.parse("SRC-000184") == SourceReference("SRC-000184", None)


@pytest.mark.parametrize(
    "ref",
    [
        "SRC-000184 ¶17",       # part 04 §4's prose citation
        "SRC-000184 ¶ 17",
        "SRC-000184 P17",       # NormalizedRecord.anchor_id's docstring form
        "SRC-000184#src-000184-p17",   # part 04 §4's markdown link
        "#src-000184-p17",             # the fragment alone
        "src-000184-p17",              # SearchResult.anchor, verbatim
    ],
)
def test_parse_resolves_every_paragraph_anchor_form(ref):
    assert references.parse(ref) == SourceReference("SRC-000184", 17)


def test_parse_is_case_insensitive_and_canonicalises_the_id():
    assert references.parse("src-000184") == SourceReference("SRC-000184", None)


def test_parse_resolves_a_repository_path():
    reference = references.parse("docs/poc-plan.md")
    assert isinstance(reference, PathReference)
    assert str(reference.path) == "docs/poc-plan.md"


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
def test_a_kind_the_archive_defines_but_this_build_lacks_is_a_value_not_a_path(
    ref, kind
):
    """Part 04 §4 defines these; nothing resolves them yet.

    They must not fall through to the path branch, which would turn "not
    built" into "no such file" and hide the real answer.
    """
    assert references.parse(ref) == UnknownReference(kind=kind, known=True)


def test_an_unheard_of_id_shaped_reference_is_unknown_rather_than_a_path():
    assert references.parse("FOO-0001") == UnknownReference(kind="FOO", known=False)


def test_a_malformed_src_id_says_so_rather_than_claiming_the_kind_is_unknown():
    with pytest.raises(BadReference, match="six-digit"):
        references.parse("SRC-184")


def test_a_reference_naming_two_different_records_is_refused():
    """Both halves of the markdown form carry the ID, so they can disagree.

    Silently preferring one would resolve a citation the author did not write.
    """
    with pytest.raises(BadReference, match="two different records"):
        references.parse("SRC-000184#src-000999-p1")


@pytest.mark.parametrize("ref", ["../secrets", "docs/../../secrets", "a/../../b"])
def test_parse_rejects_a_path_that_escapes_the_repository(ref):
    with pytest.raises(BadReference, match="escapes the repository"):
        references.parse(ref)


@pytest.mark.parametrize("ref", ["/etc/passwd", "/tmp/x", "C:/Windows/x"])
def test_parse_rejects_an_absolute_path(ref):
    with pytest.raises(BadReference, match="not a repository-relative path"):
        references.parse(ref)


@pytest.mark.parametrize(
    "ref", ["docs\\..\\..\\secrets", "..\\secrets", "a\\b"]
)
def test_parse_rejects_a_backslash_path(ref):
    """One component here, three on Windows.

    Treated as a filename, `docs\\..\\..\\secrets` is confined on Linux and
    an escape on Windows - a rule that holds only on the developer's platform
    is not a rule. No legitimate reference contains a backslash.
    """
    with pytest.raises(BadReference, match="not a repository-relative path"):
        references.parse(ref)


def test_anchor_and_split_anchor_are_inverses():
    assert references.anchor("SRC-000184", 17) == "src-000184-p17"
    assert references.split_anchor("src-000184-p17") == ("SRC-000184", 17)


def test_a_search_result_anchor_is_a_reference_with_no_reconstruction(tmp_path):
    """What #12 needs: a hit feeds straight back in.

    `SearchResult` carries (src_id, anchor, source_type). If a bare anchor
    were not a reference, search would have to reassemble a citation string
    inside an adapter - the duplication §40.1 exists to forbid.
    """
    record = NormalizedRecord(
        id="SRC-000184",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22., 1845",
        date_confidence="inferred",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=["Nothing here.", "A blue heron flew over."],
    )
    build_index(tmp_path / "index.db", [record])

    (hit,) = search(tmp_path / "index.db", "heron")

    assert references.parse(hit.anchor) == SourceReference("SRC-000184", 2)
