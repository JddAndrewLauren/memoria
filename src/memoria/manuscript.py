"""The manuscript's briefs: `book.md`, `chapter.md`, `section.md`.

Part 04 §2.1: the same artifact at three scales, and the manuscript layer's
entire durable footprint besides the prose itself. A brief holds **exactly
one editable prose field** - no scope field, no checkpoint field, no
next-step field; part 39's seventeen-field state record is withdrawn, and
what survives of it is regenerable from the session records and git.

**The outline is not an artifact.** There is no `outline.md` and no
`state.md` anywhere in this module or the tree it writes. The ordered tree of
chapters and sections, with their briefs, *is* the outline; reordering
renumbers directories (`reorder_chapters`, `reorder_sections`) and the
stable IDs in frontmatter keep every ``CHP-``/``SEC-`` reference intact
across the move.

**Only a deliberate act on the brief may write one** (part 04 §2.1 /
part 10 §19): the author writing or editing it, or an AI writing it from a
conversation the author answered - the latter in ``memoria.authorship``
(#42), under an authorization covering that one brief. No finding card and
no batch action may write a brief. This module is the only one that knows
the brief filenames (``book.md``, ``chapter.md``, ``section.md``) and, with
``authorship``, the only one that writes them; ``tests/test_manuscript.py``
asserts both over the package's sources, so a finding-resolution module
that reached for ``Path.write_text`` on a brief, or for ``write_brief``
itself, would fail the suite rather than pass unnoticed.

**Stable IDs, with one admitted gap.** ``CHP-``/``SEC-`` IDs are minted as
one more than the highest ID found on disk. That contradicts ADR-0006, which
settles that a number is reserved forever and never reused even when its
unit is deleted: here, deleting the highest-numbered chapter or section (in
Obsidian, say) lets the next ``create_*`` mint that ID again, and a stale
reference to the deleted one then resolves to the newcomer. The choice is
deliberate for this slice and pinned by a test, not an oversight: the
durable fix is a high-water source that survives deletion, and the two
sources this repository allows - ADR-0006's committed manifest, ADR-0008's
git history - are each a design decision of their own, while a separate
allocation file is what both ADRs reject. Until that decision is taken,
this is the gap.

The ``create_*``/``write_brief``/``confirm_brief`` functions are the brief's
own write path, built to issue #35's scope: **not** issue #66's single write
coordinator - no staleness token, no commit - and kept for the legacy import
and the gates that exercise the on-disk shape directly. ``plan_section`` and
``add_section`` (ADR-0012) are the same creation put behind #66's mechanism:
the brief's bytes go through ``memoria.write.create``, so a section an author
adds from a surface is committed and attributed the moment it exists, and a
section an AI writes from a conversation carries its authorization on the
commit (``memoria.authorship.write_section_from_conversation``).
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from memoria import write
from memoria.repository import Repository
from memoria.write import Actor, Rejected

# Where the book's own brief lives - the one singleton, so it carries a fixed
# ID rather than a minted one.
BOOK_RELATIVE_PATH = "book.md"
BOOK_ID = "BOOK"

CHAPTERS_RELATIVE_PATH = "chapters"

_REQUIRED_FIELDS = ("id", "unconfirmed")
_DIRECTORY_NUMBER = re.compile(r"^\d+$")
BRIEF_FILENAMES = ("book.md", "chapter.md", "section.md")
_SCRATCH_PREFIX = ".reorder-"
_CHAPTER_ID_PATTERN = re.compile(r"^CHP-(\d{4})$")
_SECTION_ID_PATTERN = re.compile(r"^SEC-(\d{4})$")


class ManuscriptError(Exception):
    """A brief could not be read, resolved or written, and why.

    Kept local to this module rather than reusing ``memoria.records.ReadError``,
    so that ``manuscript`` does not import ``records`` - ``records.read``
    imports ``manuscript`` the other way, to dispatch chapter and section
    references, and a two-way import would be a cycle.
    """


@dataclass
class Brief:
    """One brief: a stable ID, the unconfirmed state, and its prose.

    ``text`` is the entire editable field - the declared scope, craft
    direction, anything else the next session needs, all as prose the author
    writes rather than fields Memoria parses. There are no other fields.
    """

    id: str
    text: str
    unconfirmed: bool = False


# --- the on-disk form, both directions --------------------------------------


def brief_to_markdown(brief: Brief) -> str:
    """Serialize a brief to its on-disk Markdown form.

    Frontmatter carrying only ``id`` and ``unconfirmed``, then the prose
    verbatim. No other frontmatter key is ever written - that is what keeps
    "no scope field, no checkpoint field, no next-step field" true on disk
    and not just in the dataclass.
    """
    frontmatter = {"id": brief.id, "unconfirmed": brief.unconfirmed}
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + brief.text + "\n"


def parse_brief(text: str, *, source: str = "<string>") -> Brief:
    """Parse a brief's Markdown back into a ``Brief``.

    The inverse of ``brief_to_markdown``: ``brief_to_markdown(parse_brief(text))
    == text`` for any text that function wrote. A frontmatter field the
    schema does not define is named rather than swallowed, for the same
    reason ``records.parse_record`` refuses one - a stray ``scope:`` here
    would be exactly the withdrawn field this artifact exists to not have.
    """
    if text.startswith("---\r\n"):
        raise ManuscriptError(
            f"{source}: brief has CRLF line endings - the record format is LF"
        )
    if not text.startswith("---\n"):
        raise ManuscriptError(f"{source}: not a brief - no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ManuscriptError(f"{source}: frontmatter is not terminated")

    try:
        frontmatter = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise ManuscriptError(f"{source}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ManuscriptError(f"{source}: frontmatter is not a mapping")

    for name in _REQUIRED_FIELDS:
        if name not in frontmatter:
            raise ManuscriptError(f"{source}: frontmatter is missing {name!r}")
    unexpected = set(frontmatter) - set(_REQUIRED_FIELDS)
    if unexpected:
        raise ManuscriptError(
            f"{source}: frontmatter carries fields a brief does not define: "
            + ", ".join(sorted(unexpected))
        )

    brief_id = frontmatter["id"]
    if not isinstance(brief_id, str) or not brief_id:
        raise ManuscriptError(f"{source}: 'id' is required and must not be empty")
    unconfirmed = frontmatter["unconfirmed"]
    if not isinstance(unconfirmed, bool):
        raise ManuscriptError(
            f"{source}: 'unconfirmed' must be a YAML boolean, got {unconfirmed!r}"
        )

    # Two newlines separate the frontmatter close from the body (the blank
    # line `brief_to_markdown` always writes); the `\n---\n` match above
    # consumes only the first of them.
    body = text[end + len("\n---\n") :]
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]
    return Brief(id=brief_id, text=body, unconfirmed=unconfirmed)


def _load(path: Path) -> Brief:
    if not path.is_file():
        raise ManuscriptError(f"no brief at {path}")
    return parse_brief(path.read_text(encoding="utf-8"), source=str(path))


def _write_brief_file(path: Path, brief: Brief) -> None:
    """The one place any brief's bytes reach disk.

    Atomic - written to a temp file in the same directory, then ``rename()``
    into place - so a crash never leaves a half-written brief and no reader
    ever sees one (the same shape ADR-0003 settles for the write path
    proper).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = brief_to_markdown(brief)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


# --- paths --------------------------------------------------------------


def book_path(repository: Repository) -> Path:
    return repository.root / BOOK_RELATIVE_PATH


def chapters_root(repository: Repository) -> Path:
    return repository.root / CHAPTERS_RELATIVE_PATH


def chapter_dir(repository: Repository, number: int) -> Path:
    return chapters_root(repository) / f"{number:02d}"


def chapter_path(repository: Repository, number: int) -> Path:
    return chapter_dir(repository, number) / "chapter.md"


def sections_root(repository: Repository, chapter_number: int) -> Path:
    return chapter_dir(repository, chapter_number) / "sections"


def section_dir(repository: Repository, chapter_number: int, section_number: int) -> Path:
    return sections_root(repository, chapter_number) / f"{section_number:02d}"


def section_path(repository: Repository, chapter_number: int, section_number: int) -> Path:
    return section_dir(repository, chapter_number, section_number) / "section.md"


def draft_relative_path(repository: Repository, section: "SectionEntry") -> str:
    """Where a section's prose lives, repository-relative - the form
    ``memoria.write`` takes.

    ``draft.md``'s filename stays ``memoria.audit``'s to own (its module
    docstring explains why: prose is outside the three briefs this module's
    docstring scopes itself to) - imported locally, not at module level, so
    that ownership doesn't reopen the audit/manuscript import cycle #194
    just closed. Safe: this only runs after both modules have finished
    initializing, never during either one's import."""
    from memoria.audit import DRAFT_FILENAME

    return (section.dir / DRAFT_FILENAME).relative_to(repository.root).as_posix()


# --- discovery ------------------------------------------------------------


@dataclass(frozen=True)
class ChapterEntry:
    number: int
    dir: Path
    path: Path
    brief: Brief


@dataclass(frozen=True)
class SectionEntry:
    number: int
    dir: Path
    path: Path
    brief: Brief


def _numbered_dirs(root: Path) -> list[tuple[int, Path]]:
    """This root's numbered subdirectories, in numeric order.

    Numeric order rather than name order, so a chapter directory that grows
    past two digits still sorts correctly (``chapters/9`` before
    ``chapters/10`` reads wrong as strings and right as ints). Any run of
    digits counts: an author who creates ``chapters/9`` by hand is in the
    outline, not silently missing from it.
    """
    if not root.is_dir():
        return []
    found = [
        (int(entry.name), entry)
        for entry in root.iterdir()
        if entry.is_dir() and _DIRECTORY_NUMBER.match(entry.name)
    ]
    return sorted(found)


def list_chapters(repository: Repository) -> list[ChapterEntry]:
    """Every chapter, in directory order - the outline's top level."""
    entries = []
    for number, directory in _numbered_dirs(chapters_root(repository)):
        path = directory / "chapter.md"
        if path.is_file():
            entries.append(
                ChapterEntry(number=number, dir=directory, path=path, brief=_load(path))
            )
    return entries


def list_sections(repository: Repository, chapter_number: int) -> list[SectionEntry]:
    """Every section of one chapter, in directory order."""
    entries = []
    for number, directory in _numbered_dirs(sections_root(repository, chapter_number)):
        path = directory / "section.md"
        if path.is_file():
            entries.append(
                SectionEntry(number=number, dir=directory, path=path, brief=_load(path))
            )
    return entries


def _next_directory_number(root: Path) -> int:
    numbers = [number for number, _ in _numbered_dirs(root)]
    return max(numbers, default=0) + 1


# --- ID minting -------------------------------------------------------------
#
# One more than the highest ID on disk. Contradicts ADR-0006 (a deleted
# unit keeps its number reserved; no number is ever reused): delete the
# highest chapter and the next one re-mints its ID. Admitted for this slice
# and pinned by ``test_deleting_the_highest_chapter_lets_its_id_be_reminted``;
# the module docstring says why and what the durable fix would take.


def _mint_id(prefix: str, pattern: re.Pattern[str], existing_ids: list[str]) -> str:
    highest = 0
    for existing in existing_ids:
        match = pattern.match(existing)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:04d}"


def _mint_chapter_id(repository: Repository) -> str:
    return _mint_id(
        "CHP", _CHAPTER_ID_PATTERN, [entry.brief.id for entry in list_chapters(repository)]
    )


def _mint_section_id(repository: Repository) -> str:
    ids = [
        entry.brief.id
        for chapter in list_chapters(repository)
        for entry in list_sections(repository, chapter.number)
    ]
    return _mint_id("SEC", _SECTION_ID_PATTERN, ids)


# --- creation, the author write path ----------------------------------------
#
# Every creator below is a deliberate act on the brief being created and
# always writes ``unconfirmed=False`` by default: the author path is direct
# and supreme (part 04 §2.1). The one exception is ``unconfirmed=True``,
# reserved for the future summarize-from-existing-prose draft path (#35's
# "unconfirmed state" acceptance criterion covers marking and clearing it,
# not that summarizer, which is out of this slice's scope).


def create_book(repository: Repository, text: str, *, unconfirmed: bool = False) -> Brief:
    """Write the book's brief for the first time. Refuses if one exists:
    replacing an author's brief is ``write_brief``'s job, and creating over
    one would discard its text and its unconfirmed state without a word."""
    path = book_path(repository)
    if path.exists():
        raise ManuscriptError(f"a book brief already exists at {path}; use write_brief")
    brief = Brief(id=BOOK_ID, text=text, unconfirmed=unconfirmed)
    _write_brief_file(path, brief)
    return brief


def create_chapter(
    repository: Repository, text: str, *, unconfirmed: bool = False
) -> ChapterEntry:
    number = _next_directory_number(chapters_root(repository))
    brief = Brief(id=_mint_chapter_id(repository), text=text, unconfirmed=unconfirmed)
    path = chapter_path(repository, number)
    _write_brief_file(path, brief)
    return ChapterEntry(number=number, dir=path.parent, path=path, brief=brief)


def create_section(
    repository: Repository, chapter_number: int, text: str, *, unconfirmed: bool = False
) -> SectionEntry:
    number = _next_directory_number(sections_root(repository, chapter_number))
    brief = Brief(id=_mint_section_id(repository), text=text, unconfirmed=unconfirmed)
    path = section_path(repository, chapter_number, number)
    _write_brief_file(path, brief)
    return SectionEntry(number=number, dir=path.parent, path=path, brief=brief)


# --- creation through the write path (ADR-0012) ----------------------------
#
# The author-facing create: a section added from a surface, or written by an
# AI from a conversation the author answered. Two steps, so the caller can
# know the minted ``SEC-`` id before anything is written - an authorization
# (``memoria.authorship``) names its target, and the target is that id.
# Nothing here bypasses the guards above: these are the deliberate acts on a
# brief that part 04 §2.1 allows, and the bytes still reach disk only through
# ``memoria.write``, committed and attributed.

# How much of the prose stands in for a brief the author did not write.
BRIEF_FROM_PROSE_LIMIT = 200


@dataclass(frozen=True)
class PlannedSection:
    """A section about to be created: where it will live and the id it will
    carry, minted but not yet written. Nothing on disk changes until
    ``add_section`` is called with it."""

    chapter: ChapterEntry
    number: int
    brief_id: str
    dir: Path
    path: Path


def plan_section(repository: Repository, chapter_id: str) -> PlannedSection:
    """Where the next section of ``chapter_id`` goes: appended after the
    chapter's last section (position is the directory number, part 04
    §2.1), with the next ``SEC-`` id. Pure - reads the tree, writes
    nothing. ``ManuscriptError`` for a chapter id no chapter carries."""
    chapter = resolve_chapter(repository, chapter_id)
    number = _next_directory_number(sections_root(repository, chapter.number))
    path = section_path(repository, chapter.number, number)
    return PlannedSection(
        chapter=chapter,
        number=number,
        brief_id=_mint_section_id(repository),
        dir=path.parent,
        path=path,
    )


def add_section(
    repository: Repository,
    planned: PlannedSection,
    text: str,
    actor: Actor,
    *,
    unconfirmed: bool = False,
    trailers: tuple[tuple[str, str], ...] = (),
) -> SectionEntry:
    """Bring a planned section's brief into being through the write path:
    one file, one commit, attributed to ``actor`` (ADR-0003's "creation is
    a second door, not a bypass"). ``unconfirmed`` is for a brief nobody
    wrote - one derived from the prose by ``brief_from_prose`` - and is
    ``False`` for a brief the author or a conversation produced."""
    brief = Brief(id=planned.brief_id, text=text, unconfirmed=unconfirmed)
    relative = planned.path.relative_to(repository.root).as_posix()
    result = write.create(
        repository, relative, brief_to_markdown(brief), actor, trailers=trailers
    )
    if isinstance(result, Rejected):
        raise ManuscriptError(
            f"{relative} appeared underneath the create ({result.outcome}); "
            "plan the section again"
        )
    return SectionEntry(number=planned.number, dir=planned.dir, path=planned.path, brief=brief)


def add_draft(
    repository: Repository,
    section: SectionEntry,
    text: str,
    actor: Actor,
    *,
    trailers: tuple[tuple[str, str], ...] = (),
) -> str:
    """Bring a section's ``draft.md`` into being through the write path -
    the prose of a section that had none. Returns the repository-relative
    path written. A draft already there is a ``ManuscriptError``: replacing
    prose is ``memoria.authorship``'s job, under an authorization, or the
    author's own in their editor."""
    relative = draft_relative_path(repository, section)
    result = write.create(repository, relative, text, actor, trailers=trailers)
    if isinstance(result, Rejected):
        raise ManuscriptError(f"{relative} already exists ({result.outcome}); nothing written")
    return relative


def brief_from_prose(text: str) -> str:
    """The brief a section gets when the author wrote prose and no brief:
    the prose's first paragraph, shortened. This is CONTEXT.md's
    *unconfirmed brief* - "drafted by summarizing existing prose, not yet
    confirmed" - so a caller writes it with ``unconfirmed=True``, and the
    author's first edit or confirmation makes it theirs."""
    paragraphs = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    first = " ".join(paragraphs[0].split()) if paragraphs else ""
    if len(first) <= BRIEF_FROM_PROSE_LIMIT:
        return first
    return first[: BRIEF_FROM_PROSE_LIMIT - 1].rstrip() + "…"


# --- the author write path, for briefs that already exist ------------------


def write_brief(path: Path, text: str) -> Brief:
    """The author writes or edits a brief: direct, unconditional, supreme.

    Replaces the brief's prose whole and **always** clears ``unconfirmed`` -
    editing an unconfirmed brief is one of the two acts part 04 §2.1 says
    makes it the author's (the other is ``confirm_brief``). Nothing about
    this call can be redirected at a brief other than the one ``path``
    names, which is what keeps it out of reach of a batch action or a
    finding card operating over many files at once.

    ``path`` is a bare path, not a repository-relative reference: this is
    the author's own act on a file the author already holds, unlike the
    read side, which confines a caller-supplied reference to the repository
    (``records.read``). The parse in ``_load`` limits what the call can
    touch to a file that already is a brief; a caller that hands it a path
    outside the repository has stepped outside the author path, not found a
    hole in it.
    """
    existing = _load(path)
    brief = Brief(id=existing.id, text=text, unconfirmed=False)
    _write_brief_file(path, brief)
    return brief


def confirm_brief(path: Path) -> Brief:
    """The author confirms a brief as-is: clears ``unconfirmed``, text
    untouched. The other of the two acts part 04 §2.1 names."""
    existing = _load(path)
    brief = Brief(id=existing.id, text=existing.text, unconfirmed=False)
    _write_brief_file(path, brief)
    return brief


# --- reordering: directories renumber, IDs and references do not ----------


def _renumber_directories(root: Path, ordered_dirs: list[Path]) -> None:
    """Move ``ordered_dirs`` to ``root/01``, ``root/02``, ... in that order.

    Two passes: every directory moves to a scratch name first, then into its
    final slot. One pass would let a swap (01 <-> 02) have the second rename
    clobber the first, since the destination of one move is the source of
    another.

    Not atomic: a crash between the passes leaves chapters parked under
    ``.reorder-N`` names the outline cannot see, and the next reorder would
    trip over them. So the leftover is named up front rather than stumbled
    into, and the fix is a hand rename back into numbered slots.
    """
    leftover = sorted(
        entry.name for entry in root.iterdir() if entry.name.startswith(_SCRATCH_PREFIX)
    )
    if leftover:
        raise ManuscriptError(
            f"{root} holds {', '.join(leftover)} from an interrupted reorder; "
            "rename them back into numbered directories before reordering again"
        )
    scratch = []
    for index, directory in enumerate(ordered_dirs):
        holding = root / f"{_SCRATCH_PREFIX}{index}"
        directory.rename(holding)
        scratch.append(holding)
    for index, holding in enumerate(scratch, start=1):
        holding.rename(root / f"{index:02d}")


def reorder_chapters(repository: Repository, order: list[str]) -> None:
    """Reorder the book's chapters to match ``order``, a list of every
    existing chapter's stable ``CHP-`` ID in the desired final order.

    Renumbers directories only. Frontmatter IDs, and therefore every
    ``CHP-``/``SEC-`` reference, are untouched by the move.
    """
    current = {entry.brief.id: entry for entry in list_chapters(repository)}
    if sorted(order) != sorted(current):
        raise ManuscriptError(
            "reorder must name exactly the book's existing chapters: got "
            f"{sorted(order)}, have {sorted(current)}"
        )
    _renumber_directories(chapters_root(repository), [current[id_].dir for id_ in order])


def reorder_sections(repository: Repository, chapter_number: int, order: list[str]) -> None:
    """Reorder one chapter's sections to match ``order``, a list of every
    existing section's stable ``SEC-`` ID in the desired final order."""
    current = {entry.brief.id: entry for entry in list_sections(repository, chapter_number)}
    if sorted(order) != sorted(current):
        raise ManuscriptError(
            f"reorder must name exactly chapter {chapter_number}'s existing "
            f"sections: got {sorted(order)}, have {sorted(current)}"
        )
    _renumber_directories(
        sections_root(repository, chapter_number), [current[id_].dir for id_ in order]
    )


# --- resolution by stable ID, for read(ref) (#35's acceptance criterion) ---


def resolve_chapter(repository: Repository, chapter_id: str) -> ChapterEntry:
    for entry in list_chapters(repository):
        if entry.brief.id == chapter_id:
            return entry
    raise ManuscriptError(f"no such chapter: {chapter_id}")


def resolve_section(repository: Repository, section_id: str) -> SectionEntry:
    for chapter in list_chapters(repository):
        for entry in list_sections(repository, chapter.number):
            if entry.brief.id == section_id:
                return entry
    raise ManuscriptError(f"no such section: {section_id}")
