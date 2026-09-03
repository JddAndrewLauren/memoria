"""The audit's tools, on demand only (#40).

Exercises `audit_pending`/`audit_record` through the real MCP-decorated
functions, the way `test_extraction_tools.py` exercises the extraction's -
`memoria.audit`'s own tests cover the core module directly; this file covers
what the adapter adds: rendering, `ToolError` on bad input, and that the
served text carries the author-testimony policy and the subject's own
questions verbatim.
"""

from mcp.server.mcpserver.exceptions import ToolError
import pytest

from memoria.audit import (
    RecordedAuditItem,
    RecordedDisagreementMember,
    RecordedFinding,
    manuscript_paragraphs,
)
from memoria.manuscript import create_chapter, create_section
from memoria.mcp import server
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, load_subject, write_builtin_subjects


@pytest.fixture(autouse=True)
def _reset_server():
    server._repository = None
    server._session_id = None
    yield
    server._repository = None
    server._session_id = None


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _serve_one_section(tmp_path, *, brief_text, draft, entry):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, entry)
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, brief_text)
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    server._repository = repository
    return repository, chapter, section


def test_audit_pending_serves_nothing_for_an_empty_manuscript(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    create_chapter(repository, "A chapter.")
    server._repository = repository

    assert server.audit_pending(chapter_number=1) == (
        "Nothing to audit in this target - every judgement is current."
    )


def test_audit_pending_serves_the_paragraph_and_the_subjects_own_questions(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository, chapter, section = _serve_one_section(
        tmp_path, brief_text="About Bob.", draft="Bob went to town.", entry=entry
    )

    rendered = server.audit_pending(chapter_number=chapter.number, section_number=section.number)

    assert "Bob went to town." in rendered
    assert "Bob is tall." in rendered
    people_subject = load_subject(repository, "SUB-people")
    assert people_subject.audit_questions in rendered
    assert "author testimony" in rendered.lower()
    assert "outranks" in rendered.lower()
    assert "awaiting audit:" in rendered


def test_audit_pending_rejects_a_passage_without_its_section():
    with pytest.raises(ToolError):
        server.audit_pending(chapter_number=1, paragraph_index=1)


def test_audit_pending_rejects_a_limit_below_one(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    server._repository = repository
    with pytest.raises(ToolError):
        server.audit_pending(chapter_number=1, limit=0)


def test_audit_record_round_trips_an_engagement_and_a_clear_verdict(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository, chapter, section = _serve_one_section(
        tmp_path, brief_text="About Bob.", draft="Bob went to town.", entry=entry
    )
    paragraph = manuscript_paragraphs(repository)[0]
    anchor = f"{paragraph.slot}|SUB-people/bob"

    rendered = server.audit_record(
        [
            RecordedAuditItem(anchor=anchor, kind="engagement", engages=True, note="mentions Bob"),
            RecordedAuditItem(anchor=anchor, kind="audit_verdict", clear=True),
        ]
    )

    assert "accepted 2 of 2" in rendered
    assert server.audit_pending(chapter_number=chapter.number, section_number=section.number) == (
        "Nothing to audit in this target - every judgement is current."
    )


def test_audit_record_records_a_finding_and_reports_it_per_element(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository, chapter, section = _serve_one_section(
        tmp_path, brief_text="About Bob.", draft="Bob went to town.", entry=entry
    )
    paragraph = manuscript_paragraphs(repository)[0]
    anchor = f"{paragraph.slot}|SUB-people/bob"

    rendered = server.audit_record(
        [
            RecordedAuditItem(
                anchor=anchor,
                kind="audit_verdict",
                finding=RecordedFinding(
                    disagreement_set=[
                        RecordedDisagreementMember(kind="passage", ref=paragraph.slot),
                        RecordedDisagreementMember(kind="entry", ref="SUB-people/bob"),
                    ],
                    statement="Contradicts the entry.",
                    confidence="high",
                ),
            ),
            RecordedAuditItem(anchor="not-an-anchor", kind="engagement", engages=True),
        ]
    )

    assert "accepted 1 of 2" in rendered
    assert "rejected not-an-anchor" in rendered


def test_audit_record_refuses_an_empty_batch():
    with pytest.raises(ToolError):
        server.audit_record([])


def test_the_audit_tools_never_write_to_the_ledger(tmp_path):
    """Unlike the extraction tools, serving an audit task writes nothing to
    `events.jsonl` - a manuscript paragraph carries no durable reference for
    a ledger entry to name (memoria.audit's module docstring). No session is
    ever minted for it, so no `sessions/` directory appears at all."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository, chapter, section = _serve_one_section(
        tmp_path, brief_text="About Bob.", draft="Bob went to town.", entry=entry
    )

    server.audit_pending(chapter_number=chapter.number, section_number=section.number)

    assert not (repository.root / "sessions").exists()
