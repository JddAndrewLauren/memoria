"""The grilling: a writing interview that ends in a new section (ADR-0011).

The ``/grilling`` skill's shape - interview relentlessly, one question at a
time, a recommended answer with each, look facts up rather than ask, the
decisions are the author's - repurposed for writing. The interviewer asks
the author what the section they are about to write is, covers and is for,
until the two share an understanding, and then drafts it: a **brief** and
the **prose**. It is the "AI writes it from a grilling conversation the
author answered" write path CONTEXT.md names for a brief, extended to the
prose beneath it.

This module is the **serve half** only, in the shape ``memoria.style`` keeps
for the writing-style analysis: what the interviewer is told, rendered once
(``render_brief``) for both of ADR-0010's shapes. A **session run** is the
``grill-writing`` skill - the ``grill_brief`` tool serves this text, the
Claude Code session is the interviewer, and ``section_create`` writes what
the author confirmed under an authorization citing their turn. A **direct
run** is ``memoria.drivers.run_grill`` - the app's dialog holds the
transcript, each answer is one metered call with this text as the system
prompt, and the draft it ends in goes back to the author to edit and write
as their own act. Nothing here calls a model, stores an interview, or
writes a file: the transcript is the client's for as long as it lasts.
"""

from __future__ import annotations

from dataclasses import dataclass

from memoria import manuscript, records, references, style
from memoria.audit import DRAFT_FILENAME
from memoria.repository import Repository

# The prompt, a package constant like ``style.STYLE_ANALYSIS_PROMPT``: served
# verbatim to a session and used verbatim as a direct run's system text, so
# there is exactly one version of it.
GRILL_PROMPT = """\
You are interviewing the author of a book about a section they are about to write, so that the two of you reach a shared understanding of what it says before a word of it is drafted. This is the grilling: relentless, one question at a time, and the author's decisions are the author's.

How to interview:
- Ask exactly one question per turn. Several at once is bewildering.
- With every question, give your recommended answer, and say in a sentence why. The author may take it or overrule it.
- Walk down the branches of what the section must settle - what it is about, what period and events it covers, who is in it, what the reader should know or feel by its end, where it opens and closes, what it must not say yet - and resolve them one at a time, each depending on the last.
- A fact that is in the context below - the chapter's brief, the neighbouring sections, the source - is looked up there, never asked. Only a decision is put to the author.
- Do not draft until the understanding is shared, or until the author tells you to write.

When the understanding is shared, or the author asks you to write:
- Stop asking and draft the section.
- The brief is one short paragraph in the author's own terms: what this section is, what it covers, and what it is for. It is prose, not a list, and it names no fields.
- The prose is the section itself, written to the writing style below where there is one, and otherwise plainly and in keeping with the neighbouring sections. It is first-class manuscript prose: complete, not an outline, not notes for a draft.
- Everything the prose asserts about the world comes from the context below or from what the author said in this interview. Invent nothing.\
"""

# The interviewer sees at most this many paragraphs of a source - the same
# bound the writing-style analysis keeps for a chosen source.
SOURCE_PARAGRAPH_LIMIT = style.SAMPLE_PARAGRAPH_LIMIT


class GrillError(Exception):
    """A brief that cannot be served: a chapter id no chapter carries, or a
    source reference that names no record."""


@dataclass(frozen=True)
class NeighbourSection:
    """One section already in the chapter, as the interviewer sees it: its
    brief and whether prose exists yet - a planned section is one whose
    brief is written and whose draft is empty."""

    id: str
    number: int
    brief: str
    has_draft: bool


@dataclass(frozen=True)
class SourceContext:
    """The source the interview was opened from, verbatim and bounded.
    ``paragraph`` is the cited paragraph when the reference named one."""

    id: str
    title: str
    text: str
    truncated: bool
    paragraph: int | None


@dataclass(frozen=True)
class Brief:
    """Everything the interviewer is told: the prompt, the book and chapter
    briefs, the chapter's existing sections, the writing style, and the
    source if any. ``served`` names what was read, for the ledger."""

    prompt: str
    chapter_id: str
    chapter_number: int
    next_section_number: int
    book_brief: str | None
    chapter_brief: str
    neighbours: tuple[NeighbourSection, ...]
    writing_style: str | None
    source: SourceContext | None

    @property
    def served(self) -> list[str]:
        refs = [self.chapter_id]
        if self.source is not None:
            refs.append(self.source.id)
        return refs


def _book_brief(repository: Repository) -> str | None:
    path = manuscript.book_path(repository)
    if not path.is_file():
        return None
    return manuscript.parse_brief(path.read_text(encoding="utf-8"), source=str(path)).text


def _source(repository: Repository, source_ref: str) -> SourceContext:
    try:
        reference = references.parse(source_ref)
    except references.BadReference as exc:
        raise GrillError(f"not a source reference: {source_ref!r}") from exc
    if not isinstance(reference, references.SourceReference):
        raise GrillError(f"not a source reference: {source_ref!r} - a grilling takes a SRC- id")
    try:
        record = records.load(repository, reference.record_id)
    except records.ReadError as exc:
        raise GrillError(str(exc)) from exc
    paragraphs = records.real_paragraphs(record)
    return SourceContext(
        id=record.id,
        title=record.subject or record.original_locator or record.original_file,
        text="\n\n".join(paragraphs[:SOURCE_PARAGRAPH_LIMIT]),
        truncated=len(paragraphs) > SOURCE_PARAGRAPH_LIMIT,
        paragraph=reference.paragraph,
    )


def brief(repository: Repository, chapter_id: str, source_ref: str | None = None) -> Brief:
    """The briefing for one interview about a new section of ``chapter_id``,
    with ``source_ref``'s text when the interview was opened from a source.
    ``GrillError`` for an unknown chapter or source."""
    try:
        chapter = manuscript.resolve_chapter(repository, chapter_id)
    except manuscript.ManuscriptError as exc:
        raise GrillError(str(exc)) from exc
    sections = manuscript.list_sections(repository, chapter.number)
    neighbours = tuple(
        NeighbourSection(
            id=section.brief.id,
            number=section.number,
            brief=section.brief.text,
            has_draft=(section.dir / DRAFT_FILENAME).is_file(),
        )
        for section in sections
    )
    return Brief(
        prompt=GRILL_PROMPT,
        chapter_id=chapter.brief.id,
        chapter_number=chapter.number,
        next_section_number=max((s.number for s in sections), default=0) + 1,
        book_brief=_book_brief(repository),
        chapter_brief=chapter.brief.text,
        neighbours=neighbours,
        writing_style=style.writing_style_prompt(style.load_style(repository)),
        source=_source(repository, source_ref) if source_ref else None,
    )


def render_context(served: Brief) -> str:
    """Everything but the prompt: the manuscript around the new section,
    the writing style, and the source - each block verbatim, under a
    heading, in the shape ``mcp.server.render_style_brief`` keeps."""
    lines = [
        "## The section being written",
        "",
        f"Section {served.chapter_number}.{served.next_section_number} of chapter "
        f"{served.chapter_id}, appended after the chapter's existing sections.",
        "",
        "## The book's brief",
        "",
        served.book_brief if served.book_brief else "No book brief yet.",
        "",
        f"## The chapter's brief ({served.chapter_id})",
        "",
        served.chapter_brief,
        "",
        f"## Sections already in this chapter ({len(served.neighbours)})",
        "",
    ]
    if not served.neighbours:
        lines.append("None yet - this will be the chapter's first section.")
    for neighbour in served.neighbours:
        state = "drafted" if neighbour.has_draft else "planned, no prose yet"
        lines += [
            f"### {served.chapter_number}.{neighbour.number} - {neighbour.id} ({state})",
            "",
            neighbour.brief,
            "",
        ]
    lines += ["", "## The writing style", ""]
    if served.writing_style is None:
        lines.append(
            "No writing style is set. Write plainly and match the prose already in the chapter."
        )
    else:
        lines.append(served.writing_style)
    if served.source is not None:
        source = served.source
        lines += ["", f"## The source this interview was opened from ({source.id})", ""]
        lines.append(f"{source.title}")
        if source.paragraph is not None:
            lines.append(f"The author was reading paragraph {source.paragraph} of it.")
        if source.truncated:
            lines.append(
                f"(the first {SOURCE_PARAGRAPH_LIMIT} paragraphs; the source runs longer)"
            )
        lines += ["", source.text]
    return "\n".join(lines).rstrip("\n")


def render_brief(served: Brief) -> str:
    """The prompt, then the context - the whole of what an interviewer is
    told, in one rendering shared by the tool and the driver."""
    return served.prompt + "\n\n" + render_context(served)
