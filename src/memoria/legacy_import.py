"""Legacy import: a pre-Memoria chapter enters the system (#39, part 04 §2.1
third brief write path / part 06 §8.12).

Importing an existing chapter of hand-written prose gets it two things and
nothing else: an **unconfirmed brief**, drafted by summarizing the prose
that already exists, and a **cold cache** - every paragraph reads as never
audited, because nothing has ever judged it. **No model pass runs.** The
result is a tinted chapter and a count, not ten thousand model calls - this
module mints stable IDs and writes files; it never reads a paragraph to
decide anything about it.

**The summary is supplied, not generated here.** Part 04 §2.1's brief table
names the third write path "an AI drafts it by summarizing prose that
already exists" - but the AI step, if any, is the caller's, exactly the way
`memoria.extraction.record_summary` accepts a cluster summary some other
session already wrote rather than producing one itself (`extraction.py`:
"Never generated on the call: no adapter can reach a model"). This module
takes `brief_text` as an argument and writes it verbatim, marked
unconfirmed; whether a human typed it, an AI drafted it in a prior turn, or
it is a bare placeholder is not this module's question, and this is what
keeps `test_no_core_module_imports_a_model_client` (mirroring
`test_audit.py`'s) true of it - the same AST sweep, over this file.

**One chapter, one section.** "An existing chapter of prose" is one blob of
prose; it becomes one chapter and the one section holding it, each minted a
stable ID by `memoria.manuscript` - the only module that knows a brief's
filename or writes one (its own docstring's guard). `brief_text` is written
to both the chapter's and the section's brief: at this grain they describe
the same content, and inventing two independent summaries the caller did
not supply would be more than "drafted by summarizing" asks for.

**Everything else is free.** Once the chapter, section and unconfirmed brief
exist, `memoria.drift` already refuses to evaluate drift against an
unconfirmed brief (part 11 §32) and `memoria.audit.compute_staleness_map`
already reports every paragraph "never_audited" for any entry the brief's
resolved scope names (#36, #37) - both by hash comparison, both already
built. This module does not call either: it has nothing to add to a
staleness map that a cold cache already produces on its own, and re-deriving
that here would be the second copy #36's docstring warns against, just one
level up.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from memoria.audit import DRAFT_FILENAME, manuscript_paragraphs
from memoria.manuscript import ChapterEntry, SectionEntry, create_chapter, create_section
from memoria.repository import Repository


@dataclass(frozen=True)
class ImportResult:
    """What one `import_chapter` call produced: the chapter and section it
    created, and a paragraph count - a number the author reads, not a queue
    of per-paragraph work items to clear (#39's fifth acceptance criterion).
    """

    chapter: ChapterEntry
    section: SectionEntry
    paragraph_count: int


def _write_draft(path: Path, prose: str) -> None:
    """The one write of a freshly imported chapter's prose.

    Atomic, the same crash-safe shape `manuscript._write_brief_file` keeps
    for a brief: a temp file in the same directory, then `rename()`.
    `draft.md` has no write path of its own yet (#43, still open, and #39 is
    not blocked on it) - this is only ever a *new* file, since `path`'s
    parent directory was just minted by `create_section`, so there is
    nothing here to stage a staleness token against.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prose)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def import_chapter(repository: Repository, prose: str, brief_text: str) -> ImportResult:
    """Import one chapter of pre-Memoria prose (#39's first acceptance
    criterion).

    Mints a chapter and its one section (`memoria.manuscript`'s own stable
    IDs), writes `brief_text` to both briefs marked `unconfirmed=True`
    (second criterion), and writes `prose` to the section's `draft.md`
    verbatim. Reports the paragraph count by reading it back through
    `memoria.audit.manuscript_paragraphs` - the same split the staleness map
    and the audit will use, rather than a second paragraph splitter counting
    it differently.
    """
    chapter = create_chapter(repository, brief_text, unconfirmed=True)
    section = create_section(repository, chapter.number, brief_text, unconfirmed=True)
    _write_draft(section.dir / DRAFT_FILENAME, prose)
    paragraph_count = sum(
        1
        for paragraph in manuscript_paragraphs(repository)
        if paragraph.chapter_number == chapter.number
        and paragraph.section_number == section.number
    )
    return ImportResult(chapter=chapter, section=section, paragraph_count=paragraph_count)
