"""The Section view, composed live (#43, part 19 §19.5 as amended by §19.11).

Of the six right-rail cards the design draws for a section, **only one reads
a file**: ``PURPOSE`` is the brief. Everything else composes at read time
from things that already exist for other reasons - the draft's paragraphs
and their not-current state from the staleness map (part 06 §8.12), the
entries in scope from the one scope resolver (#36), and the decisions and
open questions from the session records that touched this section (part 04
§2's ``decisions.md`` / ``questions.md``, each entry citing the session turn
it came from). ``CHECKPOINT`` and ``Unresolved impacts`` are **superseded**
(part 12 §39, part 19 §19.11): neither is stored state, and nothing here
reads, writes or models one. ``tests/test_section.py`` asserts that the
value this module returns has no such field, and ``memoria.manuscript``'s
own parser already refuses a brief carrying one on disk.

**A read, and only a read.** Nothing in this module writes a file: the
Section surface is "reads plus explicit acts", and the one act it offers -
applying a rewrite from Review - lives in ``memoria.review`` and goes through
``memoria.write``. This module imports no writing function of any kind.

**"The sessions that touched it"** is read off the ledger, not off a stored
list. A session touched a section when its ``events.jsonl`` (#13) records a
read served of the section's own ``SEC-`` id or of a file under the
section's directory. A decision or question is the section's when the turn
it cites belongs to such a session. This is the composition part 19 §19.11
promises ("the other five compose live"): nothing on the section names a
decision, and nothing on a decision names a section.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from memoria import references
from memoria.audit import (
    DRAFT_FILENAME,
    NotCurrentJudgement,
    manuscript_paragraphs,
    pending_for_target,
)
from memoria.manuscript import (
    ChapterEntry,
    ManuscriptError,
    SectionEntry,
    chapters_root,
    list_chapters,
    list_sections,
    resolve_section,
)
from memoria.record_extractor import (
    DecisionRecord,
    QuestionRecord,
    list_decisions,
    list_questions,
)
from memoria.repository import Repository
from memoria.scope import resolve_scope

SESSIONS_RELATIVE_PATH = "sessions"
EVENTS_FILENAME = "events.jsonl"


# --- the outline, for the MANUSCRIPT tree -----------------------------------


@dataclass(frozen=True)
class OutlineSection:
    id: str
    number: int
    excerpt: str
    has_draft: bool


@dataclass(frozen=True)
class OutlineChapter:
    id: str
    number: int
    excerpt: str
    sections: tuple[OutlineSection, ...]


@dataclass(frozen=True)
class Outline:
    """The ordered tree of chapters and sections with their briefs - which
    *is* the outline (CONTEXT.md's "Outline": not an artifact). ``is_built``
    is whether a ``chapters/`` directory exists at all, so a fresh repository
    reads as "no manuscript yet" rather than as a book with no chapters."""

    chapters: tuple[OutlineChapter, ...]
    is_built: bool


def _excerpt(text: str, limit: int = 80) -> str:
    """The first line of a brief, shortened - a label for a tree row. A
    brief has no title field (part 04 §2.1: exactly one prose field), so
    the tree shows the prose's own opening rather than inventing one."""
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def outline(repository: Repository) -> Outline:
    chapters = []
    for chapter in list_chapters(repository):
        sections = tuple(
            OutlineSection(
                id=section.brief.id,
                number=section.number,
                excerpt=_excerpt(section.brief.text),
                has_draft=(section.dir / DRAFT_FILENAME).is_file(),
            )
            for section in list_sections(repository, chapter.number)
        )
        chapters.append(
            OutlineChapter(
                id=chapter.brief.id,
                number=chapter.number,
                excerpt=_excerpt(chapter.brief.text),
                sections=sections,
            )
        )
    return Outline(chapters=tuple(chapters), is_built=chapters_root(repository).is_dir())


# --- the section itself -------------------------------------------------------


@dataclass(frozen=True)
class SectionParagraph:
    """One paragraph of the draft as read this call, with every not-current
    judgement the staleness map holds against it - the tint and its cause
    (part 06 §8.12: "shown identically ... with the distinction carried"
    beside it). Positional, never a durable id (part 04 §4.1)."""

    index: int
    text: str
    not_current: tuple[NotCurrentJudgement, ...]


@dataclass(frozen=True)
class ScopeEntry:
    entry_id: str
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class SectionView:
    """Everything the Section surface renders, composed from a brief, a
    draft, the staleness map, the scope resolver and the session records.
    No checkpoint, no next step, no unresolved-impacts field: those are
    withdrawn state, not empty state."""

    id: str
    chapter_id: str
    chapter_number: int
    section_number: int
    brief: str
    unconfirmed: bool
    has_draft: bool
    paragraphs: tuple[SectionParagraph, ...]
    scope: tuple[ScopeEntry, ...]
    scope_empty: bool
    sessions: tuple[str, ...]
    decisions: tuple[DecisionRecord, ...]
    questions: tuple[QuestionRecord, ...]


def _locate(repository: Repository, section_id: str) -> tuple[ChapterEntry, SectionEntry]:
    """The chapter and section a ``SEC-`` id names - ``resolve_section``
    finds the section, but the surface needs its chapter too."""
    section = resolve_section(repository, section_id)
    for chapter in list_chapters(repository):
        if section.dir.parent.parent == chapter.dir:
            return chapter, section
    raise ManuscriptError(f"no chapter holds {section_id}")


def _relative(repository: Repository, path: Path) -> str:
    return path.relative_to(repository.root).as_posix()


def _event_refs(event: dict) -> list[str]:
    refs: list[str] = []
    ref = event.get("ref")
    if isinstance(ref, str):
        refs.append(ref)
    served = event.get("served")
    if isinstance(served, list):
        refs.extend(item for item in served if isinstance(item, str))
    return refs


def sessions_that_touched(repository: Repository, section: SectionEntry) -> tuple[str, ...]:
    """The ids of every session whose ledger records a read served of this
    section - by its ``SEC-`` id, or by any file under its directory.

    Read off ``sessions/**/events.jsonl`` directly: a session's directory
    holds its ledger, transcript and manifest side by side (part 04 §2),
    and walking for the ledger finds every session, whichever of the two
    nesting forms ``memoria.ledger.event_path`` wrote it under. A line that
    does not parse is skipped, not fatal - one truncated append must not
    take the whole card down.
    """
    root = repository.root / SESSIONS_RELATIVE_PATH
    if not root.is_dir():
        return ()
    section_id = section.brief.id.lower()
    section_prefix = _relative(repository, section.dir).lower() + "/"
    found: list[str] = []
    for path in sorted(root.rglob(EVENTS_FILENAME)):
        session_id: str | None = None
        touched = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if session_id is None and isinstance(event.get("session_id"), str):
                session_id = event["session_id"]
            for ref in _event_refs(event):
                lowered = ref.lower()
                if lowered == section_id or lowered.startswith(section_prefix):
                    touched = True
        if touched:
            found.append(session_id or path.parent.name)
    return tuple(found)


def _cited_session(citation: str) -> str | None:
    try:
        reference = references.parse(citation)
    except references.BadReference:
        return None
    if isinstance(reference, references.SessionReference):
        return reference.session_id
    return None


def compose_section(repository: Repository, section_id: str) -> SectionView:
    """The Section view for one ``SEC-`` id, composed at this call.

    Raises ``memoria.manuscript.ManuscriptError`` for an id no section
    carries, the same error ``read(SEC-...)`` gives.
    """
    chapter, section = _locate(repository, section_id)
    draft_path = section.dir / DRAFT_FILENAME

    not_current_by_index: dict[int, list[NotCurrentJudgement]] = {}
    for item in pending_for_target(
        repository, chapter_number=chapter.number, section_number=section.number
    ):
        not_current_by_index.setdefault(item.paragraph_index, []).append(item)
    paragraphs = tuple(
        SectionParagraph(
            index=paragraph.paragraph_index,
            text=paragraph.text,
            not_current=tuple(not_current_by_index.get(paragraph.paragraph_index, ())),
        )
        for paragraph in manuscript_paragraphs(repository)
        if paragraph.chapter_number == chapter.number
        and paragraph.section_number == section.number
    )

    resolution = resolve_scope(repository, section.brief)
    scope = tuple(
        ScopeEntry(entry_id=entry_id, matched_by=resolution.matched_by[entry_id])
        for entry_id in resolution.entry_ids
    )

    sessions = sessions_that_touched(repository, section)
    touched = set(sessions)
    decisions = tuple(
        decision
        for decision in list_decisions(repository)
        if _cited_session(decision.citation) in touched
    )
    questions = tuple(
        question
        for question in list_questions(repository)
        if _cited_session(question.citation) in touched
    )

    return SectionView(
        id=section.brief.id,
        chapter_id=chapter.brief.id,
        chapter_number=chapter.number,
        section_number=section.number,
        brief=section.brief.text,
        unconfirmed=section.brief.unconfirmed,
        has_draft=draft_path.is_file(),
        paragraphs=paragraphs,
        scope=scope,
        scope_empty=resolution.empty,
        sessions=sessions,
        decisions=decisions,
        questions=questions,
    )
