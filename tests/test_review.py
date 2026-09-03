"""The Review surface: results of an audit the author ran, and applying a
rewrite through the one write path (#43, part 19 §19.3 / §19.11, part 09
§18, part 10 §19.3).

Covers #43's Review-side acceptance criteria: Review renders only what an
audit actually recorded, findings are served as disagreement sets with the
resolutions their shape admits, counts come from the recorded data, applying
a change goes through ``memoria.write`` scoped to one paragraph, and no path
in this module can write a brief.
"""

import ast
import subprocess
from pathlib import Path

import pytest

from memoria.audit import (
    DisagreementMember,
    Finding,
    ManuscriptParagraph,
    clear_verdict,
    finding_verdict,
    record_audit_verdict,
    record_engagement,
)
from memoria.manuscript import ManuscriptError, create_chapter, create_section
from memoria.repository import Repository
from memoria.review import (
    Review,
    ReviewError,
    apply_rewrite,
    paragraph_spans,
    review_section,
)
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.write import Actor, Rejected, Written

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"
AUTHOR = Actor(name="Author", email="author@memoria.test")
DRAFT = "Bob went to town.\n\nHe came back.\n\n\nAnd then some.\n"


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _git(tmp_path, *args):
    subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)


def _repo(tmp_path, *, draft=DRAFT):
    """A real git repository: `apply_rewrite` commits (ADR-0003)."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall."))
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    if draft is not None:
        (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return repository, chapter, section


def _paragraph(chapter, section, index, text):
    return ManuscriptParagraph(chapter.number, section.number, index, text)


def _finding(members, statement="They disagree.", confidence="moderate", patch=None):
    return Finding(
        disagreement_set=tuple(DisagreementMember(kind, ref) for kind, ref in members),
        statement=statement,
        confidence=confidence,
        subject_id="SUB-people",
        patch=patch,
    )


# --- AC: Review renders only the results of an audit the author ran -----------


def test_a_section_nobody_audited_has_no_findings_and_no_current_verdicts(tmp_path):
    repository, _, section = _repo(tmp_path)

    review = review_section(repository, section.brief.id)

    assert isinstance(review, Review)
    assert review.findings == ()
    assert review.verdicts_current == 0
    assert review.verdicts_not_current == 3


def test_an_audit_that_found_nothing_is_current_with_no_findings(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    for index, text in enumerate(["Bob went to town.", "He came back.", "And then some."], 1):
        record_audit_verdict(
            repository, _paragraph(chapter, section, index, text), "SUB-people/bob", clear_verdict()
        )

    review = review_section(repository, section.brief.id)

    assert review.findings == ()
    assert (review.verdicts_current, review.verdicts_not_current) == (3, 0)


def test_findings_are_served_as_disagreement_sets_with_their_resolutions(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    second = _paragraph(chapter, section, 2, "He came back.")
    finding = _finding(
        [("passage", second.slot), ("entry", "SUB-people/bob"), ("source", "src-000184-p17")],
        confidence="high",
        patch="He came back on the eighteenth.",
    )
    record_audit_verdict(repository, second, "SUB-people/bob", finding_verdict(finding))

    review = review_section(repository, section.brief.id)

    (located,) = review.findings
    assert (located.paragraph_index, located.paragraph_text) == (2, "He came back.")
    assert located.entry_id == "SUB-people/bob"
    assert located.finding == finding
    assert located.finding.available_resolutions == (
        "settle toward the entry",
        "settle toward the source",
        "settle toward the passage",
    )
    assert (review.verdicts_current, review.verdicts_not_current) == (1, 2)


def test_findings_are_ordered_by_confidence_not_position(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    first = _paragraph(chapter, section, 1, "Bob went to town.")
    third = _paragraph(chapter, section, 3, "And then some.")
    record_audit_verdict(
        repository, first, "SUB-people/bob",
        finding_verdict(_finding([("passage", first.slot), ("entry", "SUB-people/bob")], confidence="low")),
    )
    record_audit_verdict(
        repository, third, "SUB-people/bob",
        finding_verdict(_finding([("passage", third.slot), ("entry", "SUB-people/bob")], confidence="high")),
    )

    review = review_section(repository, section.brief.id)

    assert [(f.paragraph_index, f.finding.confidence) for f in review.findings] == [
        (3, "high"),
        (1, "low"),
    ]


def test_a_finding_against_prose_since_edited_is_not_served(tmp_path):
    """Findings are derived, not accumulated (part 09 §18): a verdict whose
    paragraph has moved is stale, contributes nothing, and the paragraph
    reads as not current until the author audits it again."""
    repository, chapter, section = _repo(tmp_path)
    first = _paragraph(chapter, section, 1, "Bob went to town.")
    record_audit_verdict(
        repository, first, "SUB-people/bob",
        finding_verdict(_finding([("passage", first.slot), ("entry", "SUB-people/bob")])),
    )
    assert len(review_section(repository, section.brief.id).findings) == 1

    (section.dir / "draft.md").write_text(DRAFT.replace("town", "the city"), encoding="utf-8")

    review = review_section(repository, section.brief.id)
    assert review.findings == ()
    assert review.verdicts_not_current == 3


def test_review_py_cannot_run_or_record_an_audit():
    """Nothing populates Review in the background: the module imports no
    recording function and no model client, and `test_audit.py`'s sweep
    already refuses a call to one from anywhere but audit.py and the MCP
    server."""
    tree = ast.parse((SRC_ROOT / "review.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not imported & {
        "record_engagement",
        "record_audit_verdict",
        "record_audit_batch",
        "anthropic",
        "openai",
        "httpx",
        "requests",
    }


# --- AC: applying a change goes through the authorization path ---------------


def test_apply_rewrite_replaces_one_paragraph_and_leaves_every_other_byte(tmp_path):
    repository, _, section = _repo(tmp_path)
    token = review_section(repository, section.brief.id).token

    result = apply_rewrite(
        repository, section.brief.id, 2, token, "  He came back on the eighteenth.\n", AUTHOR
    )

    assert isinstance(result, Written)
    assert (section.dir / "draft.md").read_text(encoding="utf-8") == (
        "Bob went to town.\n\nHe came back on the eighteenth.\n\n\nAnd then some.\n"
    )
    log = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>%n%s"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    ).stdout
    assert log.splitlines()[0] == "Author <author@memoria.test>"
    assert "chapters/01/sections/01/draft.md" in log
    # Nothing tracked is left dirty (the index the read side creates is
    # untracked derived state, not part of the write).
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=tmp_path, capture_output=True, text=True,
    ).stdout
    assert status == ""


def test_apply_rewrite_against_a_draft_changed_underneath_is_rejected_whole(tmp_path):
    repository, _, section = _repo(tmp_path)
    token = review_section(repository, section.brief.id).token
    edited = DRAFT.replace("town", "the city")
    (section.dir / "draft.md").write_text(edited, encoding="utf-8")

    result = apply_rewrite(repository, section.brief.id, 2, token, "Rewritten.", AUTHOR)

    assert result == Rejected(outcome="stale", path="chapters/01/sections/01/draft.md")
    assert (section.dir / "draft.md").read_text(encoding="utf-8") == edited


def test_apply_rewrite_refuses_a_paragraph_the_draft_does_not_have(tmp_path):
    repository, _, section = _repo(tmp_path)
    token = review_section(repository, section.brief.id).token

    with pytest.raises(ReviewError, match="no paragraph 9"):
        apply_rewrite(repository, section.brief.id, 9, token, "Rewritten.", AUTHOR)
    with pytest.raises(ReviewError, match="cannot be empty"):
        apply_rewrite(repository, section.brief.id, 1, token, "   \n", AUTHOR)


def test_apply_rewrite_on_a_section_with_no_draft_is_a_named_error(tmp_path):
    repository, _, section = _repo(tmp_path, draft=None)

    assert review_section(repository, section.brief.id).token is None
    with pytest.raises(ReviewError, match="no draft"):
        apply_rewrite(repository, section.brief.id, 1, "anything", "Rewritten.", AUTHOR)


def test_an_unknown_section_is_a_named_error(tmp_path):
    repository, _, _ = _repo(tmp_path)
    with pytest.raises(ManuscriptError):
        review_section(repository, "SEC-9999")


def test_paragraph_spans_match_the_audits_own_split():
    from memoria.audit import _split_paragraphs

    for text in (
        DRAFT,
        "\n\n  leading blank lines\n\nthen more \n",
        "one\n \nsplit on a whitespace-only line",
        "a single paragraph",
        "",
    ):
        spans = paragraph_spans(text)
        assert [text[s:e] for s, e in spans] == _split_paragraphs(text)


# --- AC: no path edits a brief ------------------------------------------------


def test_apply_rewrite_cannot_reach_a_brief(tmp_path):
    """The only file this module writes is a section's draft: applying a
    rewrite never touches `section.md`, and the module names no brief
    filename and imports no brief writer (`test_manuscript.py`'s guards
    cover the second half over the whole package)."""
    repository, _, section = _repo(tmp_path)
    before = section.path.read_text(encoding="utf-8")
    token = review_section(repository, section.brief.id).token

    apply_rewrite(repository, section.brief.id, 1, token, "Rewritten.", AUTHOR)

    assert section.path.read_text(encoding="utf-8") == before
    tree = ast.parse((SRC_ROOT / "review.py").read_text(encoding="utf-8"))
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(tree)
        if isinstance(node, (ast.Attribute, ast.Name))
    }
    assert not names & {"write_brief", "confirm_brief", "create_section", "create_chapter", "create_book"}


def test_engagement_judgements_do_not_count_as_verdicts(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    for index, text in enumerate(["Bob went to town.", "He came back.", "And then some."], 1):
        record_engagement(
            repository, _paragraph(chapter, section, index, text), "SUB-people/bob",
            {"engages": True, "note": ""},
        )

    review = review_section(repository, section.brief.id)

    assert (review.verdicts_current, review.verdicts_not_current) == (0, 3)
