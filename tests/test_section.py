"""The Section view, composed live (#43, part 19 §19.5 / §19.11).

Covers #43's Section-side acceptance criteria: the view renders the brief,
the draft, the entries in scope and every paragraph's not-current state with
its cause; decisions and questions come from the session records that
touched the section, not from anything stored on it; and no checkpoint or
unresolved-impacts state exists anywhere in the value served.
"""

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from memoria.audit import ManuscriptParagraph, record_audit_verdict, record_engagement
from memoria.manuscript import ManuscriptError, create_chapter, create_section
from memoria.repository import Repository
from memoria.section import (
    Outline,
    SectionView,
    compose_section,
    outline,
    sessions_that_touched,
)
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _repo(tmp_path, *, brief_text="About Bob.", draft="Bob went to town.\n\nHe came back."):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall."))
    chapter = create_chapter(repository, "The first chapter.\n\nMore about it.")
    section = create_section(repository, chapter.number, brief_text)
    if draft is not None:
        (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    return repository, chapter, section


def _ledger(repository: Repository, session_id: str, refs: list[str]) -> None:
    """A session's ``events.jsonl`` recording one served read per ref, in
    the nested form ``memoria.ledger.event_path`` writes."""
    directory = repository.root / "sessions" / "2026" / "09" / session_id
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "session_id": session_id,
                "timestamp": "2026-09-02T10:00:00+00:00",
                "tool": "read",
                "ref": ref,
                "served": [ref],
                "tokens": 12,
            }
        )
        for ref in refs
    ]
    (directory / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _decisions(repository: Repository, *entries: tuple[str, str, str]) -> None:
    blocks = [
        f'<a id="{decision_id.lower()}"></a>\n\n## {decision_id}\n\n[author] {text}\n\n— {citation}\n\n'
        for decision_id, text, citation in entries
    ]
    (repository.root / "decisions.md").write_text("".join(blocks), encoding="utf-8")


def _questions(repository: Repository, *entries: tuple[str, str]) -> None:
    blocks = [f"[open] {text}\n\n— {citation}\n\n" for text, citation in entries]
    (repository.root / "questions.md").write_text("".join(blocks), encoding="utf-8")


# --- AC: brief, draft, in-scope entries, not-current tint with its cause -------


def test_the_section_view_carries_the_brief_the_draft_and_the_scope(tmp_path):
    repository, chapter, section = _repo(tmp_path)

    view = compose_section(repository, section.brief.id)

    assert isinstance(view, SectionView)
    assert view.id == section.brief.id
    assert view.chapter_id == chapter.brief.id
    assert (view.chapter_number, view.section_number) == (1, 1)
    assert view.brief == "About Bob."
    assert view.unconfirmed is False
    assert view.has_draft is True
    assert [p.text for p in view.paragraphs] == ["Bob went to town.", "He came back."]
    assert [(e.entry_id, e.matched_by) for e in view.scope] == [
        ("SUB-people/bob", ("bob", "Bob"))
    ]
    assert view.scope_empty is False


def test_every_paragraph_starts_not_current_and_says_why(tmp_path):
    repository, _, section = _repo(tmp_path)

    view = compose_section(repository, section.brief.id)

    for paragraph in view.paragraphs:
        causes = {(item.entry_id, item.kind, item.cause) for item in paragraph.not_current}
        assert causes == {
            ("SUB-people/bob", "engagement", "never_audited"),
            ("SUB-people/bob", "audit_verdict", "never_audited"),
        }


def test_an_audited_paragraph_is_current_and_an_edited_one_names_the_edit(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    first = ManuscriptParagraph(chapter.number, section.number, 1, "Bob went to town.")
    second = ManuscriptParagraph(chapter.number, section.number, 2, "He came back.")
    for paragraph in (first, second):
        record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True, "note": ""})
        record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    assert all(p.not_current == () for p in compose_section(repository, section.brief.id).paragraphs)

    (section.dir / "draft.md").write_text(
        "Bob went to town.\n\nHe came back later.", encoding="utf-8"
    )
    view = compose_section(repository, section.brief.id)

    assert view.paragraphs[0].not_current == ()
    assert {item.cause for item in view.paragraphs[1].not_current} == {"paragraph_edited"}


def test_a_section_without_a_draft_is_a_planned_section_not_an_error(tmp_path):
    repository, _, section = _repo(tmp_path, draft=None)

    view = compose_section(repository, section.brief.id)

    assert view.has_draft is False
    assert view.paragraphs == ()


def test_an_unconfirmed_brief_is_reported_and_an_empty_scope_is_explicit(tmp_path):
    repository, chapter, section = _repo(tmp_path, brief_text="Nothing named here.")
    section.path.write_text(
        section.path.read_text(encoding="utf-8").replace(
            "unconfirmed: false", "unconfirmed: true"
        ),
        encoding="utf-8",
    )

    view = compose_section(repository, section.brief.id)

    assert view.unconfirmed is True
    assert view.scope == ()
    assert view.scope_empty is True


def test_an_unknown_section_is_a_named_error(tmp_path):
    repository, _, _ = _repo(tmp_path)
    with pytest.raises(ManuscriptError):
        compose_section(repository, "SEC-9999")


# --- AC: decisions and questions composed from session records -----------------


def test_decisions_and_questions_come_from_the_sessions_that_touched_the_section(tmp_path):
    repository, _, section = _repo(tmp_path)
    _ledger(repository, "SES-20260901-1000-aaaa", [section.brief.id])
    _ledger(
        repository,
        "SES-20260901-1100-bbbb",
        ["chapters/01/sections/01/draft.md"],
    )
    _ledger(repository, "SES-20260901-1200-cccc", ["SUB-people/bob"])
    _decisions(
        repository,
        ("DEC-0001", "Keep Bob's knowledge ambiguous here.", "SES-20260901-1000-aaaa#T003"),
        ("DEC-0002", "Unrelated to this section.", "SES-20260901-1200-cccc#T002"),
        ("DEC-0003", "Do not reveal Alice's account yet.", "SES-20260901-1100-bbbb#T007"),
    )
    _questions(
        repository,
        ("Did Bob receive the July 14 document?", "SES-20260901-1000-aaaa#T004"),
        ("Something about someone else.", "SES-20260901-1200-cccc#T001"),
    )

    view = compose_section(repository, section.brief.id)

    assert view.sessions == ("SES-20260901-1000-aaaa", "SES-20260901-1100-bbbb")
    assert [(d.id, d.text) for d in view.decisions] == [
        ("DEC-0001", "Keep Bob's knowledge ambiguous here."),
        ("DEC-0003", "Do not reveal Alice's account yet."),
    ]
    assert [q.text for q in view.questions] == ["Did Bob receive the July 14 document?"]


def test_a_section_no_session_touched_has_no_decisions_and_no_questions(tmp_path):
    repository, _, section = _repo(tmp_path)
    _decisions(repository, ("DEC-0001", "A decision.", "SES-20260901-1000-aaaa#T003"))

    view = compose_section(repository, section.brief.id)

    assert view.sessions == ()
    assert view.decisions == ()
    assert view.questions == ()


def test_sessions_that_touched_matches_the_id_case_insensitively_and_by_path(tmp_path):
    repository, _, section = _repo(tmp_path)
    _ledger(repository, "SES-20260901-1000-aaaa", [section.brief.id.lower()])
    _ledger(repository, "SES-20260901-1100-bbbb", ["chapters/01/sections/01/section.md"])
    _ledger(repository, "SES-20260901-1200-cccc", ["chapters/01/chapter.md"])

    assert sessions_that_touched(repository, section) == (
        "SES-20260901-1000-aaaa",
        "SES-20260901-1100-bbbb",
    )


def test_a_ledger_line_that_does_not_parse_is_skipped(tmp_path):
    repository, _, section = _repo(tmp_path)
    directory = repository.root / "sessions" / "SES-custom"
    directory.mkdir(parents=True)
    (directory / "events.jsonl").write_text(
        "{not json\n"
        + json.dumps({"session_id": "SES-custom", "tool": "read", "ref": section.brief.id})
        + "\n",
        encoding="utf-8",
    )

    assert sessions_that_touched(repository, section) == ("SES-custom",)


# --- AC: no checkpoint or unresolved-impacts state is stored or displayed ------


def test_the_section_view_has_no_checkpoint_or_impacts_field():
    """Part 12 §39 and part 19 §19.11: both are withdrawn, not empty. The
    value the surface renders has no field for either to be filled in."""
    names = {field.name for field in dataclasses.fields(SectionView)}
    for withdrawn in ("checkpoint", "next", "impact", "impacts", "unresolved"):
        assert not any(withdrawn in name for name in names), names


def test_section_py_reads_no_stored_section_state_and_writes_nothing():
    """The composition reads a brief, a draft, the ledger, `decisions.md`
    and `questions.md` - and never a state file of its own. And it writes
    nothing: no file-writing call appears in its source."""
    tree = ast.parse((SRC_ROOT / "section.py").read_text(encoding="utf-8"))
    strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not {s for s in strings if s.endswith(".md") and "state" in s}
    assert "state.md" not in strings and "checkpoint.md" not in strings
    calls = {
        getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not calls & {"write_text", "write_bytes", "open", "replace", "rename"}


# --- the outline, for the MANUSCRIPT tree -------------------------------------


def test_the_outline_is_the_tree_of_chapters_and_sections_with_their_briefs(tmp_path):
    repository, chapter, section = _repo(tmp_path)
    planned = create_section(repository, chapter.number, "A planned section, no draft yet.")

    result = outline(repository)

    assert isinstance(result, Outline)
    assert result.is_built is True
    (only,) = result.chapters
    assert (only.id, only.number, only.excerpt) == (chapter.brief.id, 1, "The first chapter.")
    assert [(s.id, s.number, s.excerpt, s.has_draft) for s in only.sections] == [
        (section.brief.id, 1, "About Bob.", True),
        (planned.brief.id, 2, "A planned section, no draft yet.", False),
    ]


def test_a_repository_with_no_chapters_directory_is_not_built(tmp_path):
    result = outline(Repository(root=tmp_path))

    assert result == Outline(chapters=(), is_built=False)


def test_a_long_brief_is_excerpted_on_its_first_line(tmp_path):
    repository, chapter, _ = _repo(tmp_path)
    long = create_section(repository, chapter.number, "x" * 200 + "\n\nSecond line.")

    (only,) = outline(repository).chapters
    excerpt = next(s.excerpt for s in only.sections if s.id == long.brief.id)

    assert excerpt.endswith("…") and len(excerpt) <= 80
