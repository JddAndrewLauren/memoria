"""AI manuscript writing under explicit authorization (#42, part 10 §19-§21
and §37, Invariants 8 and 9).

Memoria may propose a rewrite on its own; it may not apply one until an
**identifiable authorization** exists. This module is the only place an AI
writes manuscript-class files - a section's ``draft.md`` or one of the three
briefs - and every write it makes needs an ``Authorization``: the session
turn in which the author gave it, and exactly what it covers.

**Authorization is scoped** (§19.3). A request to rewrite one paragraph does
not authorize unrelated changes elsewhere, so an ``Authorization`` names its
targets - a paragraph, a section's whole draft, or one brief - and a write
that is not covered is ``Refused`` rather than applied. The paragraph write
splices only the authorized paragraph's bytes into the draft it read; every
other byte of the file is left exactly as it was, which is what makes "one
paragraph authorized, unrelated prose untouched" (§43.13) a byte-level
property a test can assert rather than a policy a caller remembers.

**A brief is authorized one level below prose, and separately** (§19.3):
its AI write path is a conversation whose purpose is that brief - Memoria
interviewing the author and writing down the conclusion - so the
authorization for a brief covers that brief and nothing else. Never prose
alongside it, never two briefs, never a batch: a finding card or a batch
action cannot reach ``write_brief_from_conversation`` with an authorization
it would accept.

**Authorization is recorded durably on the commit** (§41, ADR-0008's
pattern). Each write goes through ``memoria.write`` as a machine actor and
carries two trailers: ``authorized-by: SES-...#T008``, the turn that
authorized it, and ``authorized-scope:`` naming the one target this write
covered. Git history is the ledger; nothing else points at the paragraph
(part 04 §4.1), so nothing needs migrating when prose moves. A batch
(§21) is many such writes - one commit per paragraph, each with its own
trailers - never one opaque act, and ``memoria validate`` (#42) fails any
manuscript commit that carries neither a ``change-id`` (human) nor an
``authorized-by`` (AI) trailer.

**Positional targets, guarded twice.** A paragraph number is a position,
not an identity (§4.1), so a proposal pins the text it read, and applying
it refuses if that paragraph no longer says that - an insert above it would
otherwise land the rewrite on the wrong prose. The write path's own
staleness token (ADR-0003) guards the file as a whole underneath that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from memoria import manuscript, references, write
from memoria.audit import DRAFT_FILENAME
from memoria.manuscript import Brief, brief_to_markdown, parse_brief
from memoria.repository import Repository
from memoria.write import Actor, Rejected

AUTHORIZED_BY_TRAILER = "authorized-by"
AUTHORIZED_SCOPE_TRAILER = "authorized-scope"

# The machine actor an AI manuscript write commits as (§41: "AI manuscript
# changes are committed with references to their authorizing interaction").
# `human=False`, so the commit carries no change-id and the write path
# checkpoints the author's outside edits first (ADR-0008).
WRITER = Actor(name="Memoria", email="writer@memoria.local", human=False)

# The same blank-line split `memoria.audit.manuscript_paragraphs` numbers
# paragraphs by, applied here to byte offsets rather than text so a rewrite
# can be spliced in place. A test asserts the two agree on every paragraph.
_BLANK_LINE = re.compile(r"\n\s*\n")


class AuthorshipError(Exception):
    """A proposal or write that cannot be attempted at all - a section or
    paragraph that does not exist, a brief id that names no brief, or an
    authorization that is not identifiable. Distinct from ``Refused``,
    which is the normal, handled outcome of an unauthorized or uncovered
    write."""


# --- what an authorization covers ------------------------------------------


@dataclass(frozen=True)
class ParagraphTarget:
    """One paragraph of a section's prose - "rewrite that paragraph"."""

    section_id: str
    paragraph: int

    @property
    def citation(self) -> str:
        return f"{self.section_id} ¶{self.paragraph}"


@dataclass(frozen=True)
class SectionTarget:
    """A section's whole draft - "draft section 8.3 from the source
    packet", or "take a pass at" one. Covers every paragraph in it."""

    section_id: str

    @property
    def citation(self) -> str:
        return f"{self.section_id} draft"


@dataclass(frozen=True)
class BriefTarget:
    """One brief - ``BOOK``, a ``CHP-`` or a ``SEC-`` id - written from a
    conversation the author answered about it."""

    brief_id: str

    @property
    def citation(self) -> str:
        return f"{self.brief_id} brief"


Target = ParagraphTarget | SectionTarget | BriefTarget


@dataclass(frozen=True)
class Authorization:
    """An identifiable authorization: the session turn in which the author
    gave it, and exactly what it covers.

    Identifiable means citable - ``session_id`` in part 04 §4's ``SES-``
    form and a 1-based ``turn`` - so that what the commit records
    (``citation``) is something ``read(ref)`` resolves once the session is
    derived, and something ``trace()`` walks back to. An authorization that
    is not citable cannot be constructed.
    """

    session_id: str
    turn: int
    covers: frozenset[Target]

    def __post_init__(self) -> None:
        if self.turn < 1:
            raise AuthorshipError(f"a turn is 1-based; there is no T{self.turn}")
        try:
            reference = references.parse(f"{self.session_id}#T{self.turn}")
        except references.BadReference as exc:
            raise AuthorshipError(f"not a citable session id: {self.session_id!r}") from exc
        if not isinstance(reference, references.SessionReference):
            raise AuthorshipError(f"not a citable session id: {self.session_id!r}")
        if not self.covers:
            raise AuthorshipError("an authorization covers at least one target")

    @property
    def citation(self) -> str:
        """The ``SES-...#T008`` form the commit trailer carries."""
        return references.format_citation(
            references.parse(f"{self.session_id}#T{self.turn}")
        )

    def covers_paragraph(self, section_id: str, paragraph: int) -> bool:
        return (
            ParagraphTarget(section_id, paragraph) in self.covers
            or SectionTarget(section_id) in self.covers
        )


# --- outcomes ------------------------------------------------------------


@dataclass(frozen=True)
class Applied:
    """A write applied and committed, with its authorization on the commit."""

    path: str
    target: Target
    authorized_by: str


@dataclass(frozen=True)
class Refused:
    """A write not applied, and why. The normal outcome of an unauthorized
    or uncovered write (§19.3), not an error: nothing was written and no
    commit was made."""

    reason: str
    target: Target


ApplyResult = Applied | Refused


# --- the prose, read positionally --------------------------------------------


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` character offsets of every paragraph's stripped text,
    in order - the byte-level twin of ``audit._split_paragraphs``: the same
    blank-line separator, the same stripping, so ¶N here is ¶N there."""
    spans: list[tuple[int, int]] = []
    position = 0
    for match in _BLANK_LINE.finditer(text):
        _add_span(spans, text, position, match.start())
        position = match.end()
    _add_span(spans, text, position, len(text))
    return spans


def _add_span(spans: list[tuple[int, int]], text: str, start: int, end: int) -> None:
    chunk = text[start:end]
    stripped = chunk.strip()
    if not stripped:
        return
    lead = len(chunk) - len(chunk.lstrip())
    spans.append((start + lead, start + lead + len(stripped)))


def draft_relative_path(repository: Repository, section: manuscript.SectionEntry) -> str:
    """Where a section's prose lives, repository-relative - the form
    ``memoria.write`` takes."""
    return (section.dir / DRAFT_FILENAME).relative_to(repository.root).as_posix()


def _draft(repository: Repository, section_id: str) -> tuple[manuscript.SectionEntry, str, Path]:
    try:
        section = manuscript.resolve_section(repository, section_id)
    except manuscript.ManuscriptError as exc:
        raise AuthorshipError(str(exc)) from exc
    return section, draft_relative_path(repository, section), section.dir / DRAFT_FILENAME


def read_paragraph(repository: Repository, section_id: str, paragraph: int) -> str:
    """One paragraph of a section's prose, verbatim, as it is right now.

    What ``read(SEC-0001 ¶7)`` serves and what ``propose_rewrite`` pins.
    """
    _, relative, path = _draft(repository, section_id)
    if not path.is_file():
        raise AuthorshipError(f"{section_id} has no prose yet: no {relative}")
    text = path.read_text(encoding="utf-8")
    spans = paragraph_spans(text)
    if not 1 <= paragraph <= len(spans):
        raise AuthorshipError(
            f"{section_id} has {len(spans)} paragraph(s); there is no ¶{paragraph}"
        )
    start, end = spans[paragraph - 1]
    return text[start:end]


# --- proposing, which writes nothing -----------------------------------------


@dataclass(frozen=True)
class Proposal:
    """A rewrite Memoria proposes for one paragraph: what it read there, and
    what it would put in its place. Text only - nothing here applies it
    (§19.2, "preparing prose is not the same as modifying canonical prose").
    """

    section_id: str
    paragraph: int
    current_text: str
    proposed_text: str

    @property
    def target(self) -> ParagraphTarget:
        return ParagraphTarget(self.section_id, self.paragraph)


def propose_rewrite(
    repository: Repository, section_id: str, paragraph: int, proposed_text: str
) -> Proposal:
    """Propose a rewrite of ¶``paragraph`` of ``section_id``. Reads the
    paragraph so the proposal is pinned to what it says now; writes nothing
    and commits nothing."""
    current = read_paragraph(repository, section_id, paragraph)
    return Proposal(
        section_id=section_id,
        paragraph=paragraph,
        current_text=current,
        proposed_text=proposed_text,
    )


# --- applying, which needs an authorization ----------------------------------


def _trailers(authorization: Authorization, target: Target) -> tuple[tuple[str, str], ...]:
    """The authorization boundary, recorded on the commit before the write
    lands (§19.3: "Memoria records the authorization boundary before
    writing")."""
    return (
        (AUTHORIZED_BY_TRAILER, authorization.citation),
        (AUTHORIZED_SCOPE_TRAILER, target.citation),
    )


def _not_covered(authorization: Authorization, target: Target) -> str:
    covered = ", ".join(sorted(t.citation for t in authorization.covers))
    return (
        f"not covered: {authorization.citation} authorizes {covered}, "
        f"not {target.citation}"
    )


def apply_rewrite(
    repository: Repository,
    proposal: Proposal,
    authorization: Authorization | None = None,
) -> ApplyResult:
    """Apply one proposed rewrite, if - and only if - ``authorization``
    covers that paragraph.

    ``Refused`` without an authorization, with one that does not cover this
    paragraph (§19.3's scoping), or when the paragraph no longer says what
    the proposal read (moved underneath: an edit above it shifted the
    numbering, or the author changed it) - in every case nothing is written
    and no commit is made. Applied, it replaces exactly the bytes of that
    paragraph and commits through the write path with the authorization on
    the commit.
    """
    target = proposal.target
    if authorization is None:
        return Refused("no authorization: a proposal is not an authorization", target)
    if not authorization.covers_paragraph(proposal.section_id, proposal.paragraph):
        return Refused(_not_covered(authorization, target), target)

    _, relative, path = _draft(repository, proposal.section_id)
    if not path.is_file():
        return Refused(f"moved: {relative} no longer exists", target)
    served = write.serve(repository, relative)
    spans = paragraph_spans(served.text)
    if proposal.paragraph > len(spans):
        return Refused(
            f"moved: {proposal.section_id} now has {len(spans)} paragraph(s); "
            f"there is no ¶{proposal.paragraph}",
            target,
        )
    start, end = spans[proposal.paragraph - 1]
    if served.text[start:end] != proposal.current_text:
        return Refused(
            f"moved: {target.citation} no longer says what the proposal read", target
        )

    content = served.text[:start] + proposal.proposed_text.strip() + served.text[end:]
    result = write.write(
        repository, relative, served.token, content, WRITER,
        trailers=_trailers(authorization, target),
    )
    if isinstance(result, Rejected):
        return Refused(f"{result.outcome}: {result.path} changed underneath the write", target)
    return Applied(path=relative, target=target, authorized_by=authorization.citation)


def apply_rewrites(
    repository: Repository,
    proposals: list[Proposal],
    authorization: Authorization | None = None,
) -> tuple[ApplyResult, ...]:
    """Apply a batch of proposals under one authorization (§21) - each as
    its own write and its own commit, individually covered, individually
    traceable, never one opaque act.

    Applied bottom-up within a section (highest paragraph first), so a
    rewrite that changes one paragraph's line count cannot shift the
    numbering of a later target before it is reached. Results come back in
    the order the proposals were given. A batch carries prose rewrites only:
    a ``Proposal`` names a paragraph, so no batch can reach a brief (§19.3).
    """
    order = sorted(
        range(len(proposals)),
        key=lambda i: (proposals[i].section_id, -proposals[i].paragraph),
    )
    results: dict[int, ApplyResult] = {}
    for index in order:
        results[index] = apply_rewrite(repository, proposals[index], authorization)
    return tuple(results[index] for index in range(len(proposals)))


def write_draft(
    repository: Repository,
    section_id: str,
    text: str,
    authorization: Authorization | None = None,
) -> ApplyResult:
    """Write a section's whole draft - new prose for a planned section, or a
    pass over an existing one - under an authorization that covers the
    section (``SectionTarget``). A paragraph authorization does not: the
    whole draft is more than one paragraph's scope."""
    target = SectionTarget(section_id)
    if authorization is None:
        return Refused("no authorization", target)
    if target not in authorization.covers:
        return Refused(_not_covered(authorization, target), target)

    _, relative, path = _draft(repository, section_id)
    trailers = _trailers(authorization, target)
    if path.is_file():
        served = write.serve(repository, relative)
        result = write.write(repository, relative, served.token, text, WRITER, trailers=trailers)
    else:
        result = write.create(repository, relative, text, WRITER, trailers=trailers)
    if isinstance(result, Rejected):
        return Refused(f"{result.outcome}: {result.path} changed underneath the write", target)
    return Applied(path=relative, target=target, authorized_by=authorization.citation)


# --- the brief's AI write path -------------------------------------------------


def _brief_path(repository: Repository, brief_id: str) -> Path:
    try:
        if brief_id == manuscript.BOOK_ID:
            path = manuscript.book_path(repository)
            if not path.is_file():
                raise AuthorshipError("no book brief yet; creating one is the author's act")
            return path
        if brief_id.startswith("CHP-"):
            return manuscript.resolve_chapter(repository, brief_id).path
        if brief_id.startswith("SEC-"):
            return manuscript.resolve_section(repository, brief_id).path
    except manuscript.ManuscriptError as exc:
        raise AuthorshipError(str(exc)) from exc
    raise AuthorshipError(f"not a brief id: {brief_id!r} (BOOK, CHP-nnnn or SEC-nnnn)")


def write_brief_from_conversation(
    repository: Repository,
    brief_id: str,
    text: str,
    authorization: Authorization | None = None,
) -> ApplyResult:
    """The brief's own AI write path (part 04 §2.1, §19.3): an AI writes a
    brief from a conversation the author answered about it.

    Authorized one level below prose and separately from it: the
    authorization must cover **exactly this brief** - a ``BriefTarget`` for
    it and nothing else. One that also covers prose, or another brief, is
    refused, which is what keeps a batch (§21) and a finding card (§19.3)
    structurally unable to write one. The conversation is the deliberate act
    on the brief, so the result is the author's - ``unconfirmed`` is cleared,
    the same as when the author edits it (``manuscript.write_brief``) - and
    the commit names the turn that concluded it.
    """
    target = BriefTarget(brief_id)
    if authorization is None:
        return Refused("no authorization", target)
    if authorization.covers != frozenset({target}):
        covered = ", ".join(sorted(t.citation for t in authorization.covers))
        return Refused(
            "a brief is authorized separately, by an act on that brief alone: "
            f"{authorization.citation} authorizes {covered}, and writing "
            f"{target.citation} needs an authorization covering it and nothing else",
            target,
        )

    path = _brief_path(repository, brief_id)
    relative = path.relative_to(repository.root).as_posix()
    served = write.serve(repository, relative)
    try:
        existing = parse_brief(served.text, source=relative)
    except manuscript.ManuscriptError as exc:
        raise AuthorshipError(str(exc)) from exc
    content = brief_to_markdown(Brief(id=existing.id, text=text, unconfirmed=False))
    result = write.write(
        repository, relative, served.token, content, WRITER,
        trailers=_trailers(authorization, target),
    )
    if isinstance(result, Rejected):
        return Refused(f"{result.outcome}: {result.path} changed underneath the write", target)
    return Applied(path=relative, target=target, authorized_by=authorization.citation)
