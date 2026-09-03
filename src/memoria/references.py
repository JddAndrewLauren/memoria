"""Parsing and formatting stable references.

``read(ref)`` dispatches on the kind of reference it is given, because the ID
scheme of part 04 §4 already names the type. This module owns that parse, and
nothing else: it imports nothing from ``memoria`` and touches no filesystem.

ADR-0004 puts it here rather than in the record store, and the reason is worth
keeping in view: most reference kinds will never be records - ``SES-`` with an
optional ``#T`` turn, ``CHG-``, ``CLM-``, ``RES-``, ``DEC-``, ``SUB-x``,
``SUB-x/y`` - and a record store should not know what ``SUB-x`` is. Parsing a
reference and resolving one to a record are different jobs.

``parse`` never raises and never returns ``None``. An unsupported reference is
a value - ``UnknownReference``, carrying the kind - which is what lets the
caller name the kind in an error rather than returning a silent empty result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

# Six digits, zero-padded (part 04 §4's SRC-000184 form). Strict: the SRC-0184
# seen in the desktop mockup is a noted divergence, not a second accepted form
# (docs/normalized-record-schema.md).
_ID = r"SRC-\d{6}"
_ANCHOR = r"src-\d{6}-p\d+"

_BARE_ID = re.compile(rf"^(?P<id>{_ID})$", re.IGNORECASE)

# Chapter and section stable IDs (#35). Part 04 §4 says only that chapters and
# sections "carry stable IDs in frontmatter so file renames do not destroy
# identity" - it does not name a form, so this picks one in the four-digit
# style CLM-0041 already uses. Directory numbers (chapters/08/) are a
# different axis entirely: they renumber on reorder, the ID never does.
_CHAPTER_ID = r"CHP-\d{4}"
_SECTION_ID = r"SEC-\d{4}"
_BARE_CHAPTER_ID = re.compile(rf"^(?P<id>{_CHAPTER_ID})$", re.IGNORECASE)
_BARE_SECTION_ID = re.compile(rf"^(?P<id>{_SECTION_ID})$", re.IGNORECASE)
# One paragraph of a section's prose (#42), in the same `¶`/`P` form a
# source paragraph takes below. Positional and deliberately *not* durable:
# part 04 §4.1 says nothing canonical points at a paragraph of manuscript
# prose, so this is a form for a live question - `trace(SEC-0001 ¶7)`, a
# read of what ¶7 says right now - never one to store in a record.
_SECTION_PARAGRAPH = re.compile(
    rf"^(?P<id>{_SECTION_ID})\s*(?:¶|P)\s*(?P<n>\d+)$", re.IGNORECASE
)

# A human-authored commit (ADR-0008): a per-day sequence, not the `HHMM` form
# part 04 §4 originally showed - minute resolution collides once writes
# through the app are frequent.
_CHANGE_ID = r"CHG-\d{8}-\d{3}"
_BARE_CHANGE_ID = re.compile(rf"^(?P<id>{_CHANGE_ID})$", re.IGNORECASE)

# An author decision (#30, part 04 §4): a flat four-digit sequence, the same
# style `CHP-`/`SEC-` already use - `DEC-0088` - rather than `RES-`'s
# per-day one. Decisions live inside one running `decisions.md`, not one
# file each, so unlike `RES-` there is no natural per-day bucket to count
# within.
_DECISION_ID = r"DEC-\d{4}"
_BARE_DECISION_ID = re.compile(rf"^(?P<id>{_DECISION_ID})$", re.IGNORECASE)

# A research memo (#30, part 04 §4): `RES-YYYYMMDD-NNN`, the same per-day
# sequence `CHG-` was given to match (part 04 §4's own note: the `CHG-` form
# was chosen "as a `RES-` ID already uses").
_RESEARCH_MEMO_ID = r"RES-\d{8}-\d{3}"
_BARE_RESEARCH_MEMO_ID = re.compile(rf"^(?P<id>{_RESEARCH_MEMO_ID})$", re.IGNORECASE)

# A claim (#33, part 06 §8.9): the flat four-digit `CLM-0041` the plan has
# always written, one file each under `claims/`.
_CLAIM_ID = r"CLM-\d{4}"
_BARE_CLAIM_ID = re.compile(rf"^(?P<id>{_CLAIM_ID})$", re.IGNORECASE)

# A derived session record (#28, part 04 §4): `SES-YYYYMMDD-HHMM`, plus the
# optional random suffix `memoria.ledger` mints to keep two servers spawned
# in the same minute from colliding. The date and time are canonicalised to
# upper case like every other kind here (they are digits, so that only ever
# touches the `SES` keyword); the suffix is kept in its own group and never
# case-folded, because it is lower-case hex as generated
# (`secrets.token_hex`) and upper-casing it would send a lookup after a
# directory that does not exist.
_SESSION_ID = (
    r"SES-(?P<ses_date>\d{8})-(?P<ses_time>\d{4})(?:-(?P<ses_suffix>[0-9a-fA-F]+))?"
)
_BARE_SESSION_ID = re.compile(rf"^{_SESSION_ID}$", re.IGNORECASE)
# The turn fragment. Case-insensitive on both letters: `#T017` is part 04
# §4's citation form, `#t017` is the lower-case anchor-tag form its own
# markdown-link example uses (the same split `_ANCHOR`/anchor id already
# makes for `SRC-000184 P17` vs `src-000184-p17`).
_SESSION_TURN = re.compile(rf"^{_SESSION_ID}#T(?P<turn>\d+)$", re.IGNORECASE)


def _canonical_session_id(match: re.Match) -> str:
    """The session id a session match carries, upper-cased except for its
    suffix (see ``_SESSION_ID`` above)."""
    canonical = f"SES-{match.group('ses_date')}-{match.group('ses_time')}"
    suffix = match.group("ses_suffix")
    if suffix:
        canonical = f"{canonical}-{suffix}"
    return canonical

# The prose citation form. The pilcrow is what part 04 §4 writes; `P` is
# accepted alongside it because a model retyping a citation drops a non-ASCII
# character often enough to matter. A bare number ("SRC-000184 17") is not
# accepted - it is as easily a typo for a different ID as a paragraph.
_ID_PARAGRAPH = re.compile(
    rf"^(?P<id>{_ID})\s*(?:¶|P)\s*(?P<n>\d+)$", re.IGNORECASE
)
# The markdown link form, whole or fragment-only:
#   [SRC-000184 P17](../../sources/normalized/SRC-000184.md#src-000184-p17)
_ID_FRAGMENT = re.compile(rf"^(?P<id>{_ID})#(?P<anchor>{_ANCHOR})$", re.IGNORECASE)
_FRAGMENT = re.compile(rf"^#?(?P<anchor>{_ANCHOR})$", re.IGNORECASE)

# Anything shaped like a stable ID. Recognising by shape rather than by
# enumerating kinds is what makes an unheard-of prefix an error naming itself
# instead of being mistaken for a relative path.
#
# Upper case only, and that is load-bearing rather than tidy: part 04 §4 writes
# every kind in caps, and this repository contains `open-problems.md` and
# `tool-surface.md`. A case-insensitive rule answered "unknown reference kind
# OPEN-" for a file that exists, which is worse than either correct answer.
# Lower-case `src-000184-p17` still resolves, because the anchor forms are
# matched before this.
_ID_SHAPED = re.compile(r"^(?P<kind>[A-Z]{2,5})-")

# Kinds part 04 §4 defines that nothing implements yet. Used only to tell
# "not built yet" from "never heard of it" in the message; the mechanism that
# rejects them is the shape rule above, not this list. Empty since #33: every
# kind the scheme names is implemented below, each with its own
# malformed-reference message rather than the generic "not resolvable in
# this build yet" one. Kept so the next kind the plan adds has somewhere to
# sit between being named and being built.
NOT_YET_IMPLEMENTED_KINDS: tuple[str, ...] = ()

# A subject or entry slug: lowercase, directory-name shaped (part 04 §2's
# `subjects/people/bob.md`). Uppercase is refused rather than folded, the
# same call `_ID_SHAPED` makes for a kind prefix - a `SUB-People` typo is a
# malformed reference, not a second accepted spelling.
_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_SUBJECT_ID = rf"SUB-{_SLUG}"
_BARE_SUBJECT = re.compile(rf"^(?P<id>{_SUBJECT_ID})$")
_SUBJECT_ENTRY = re.compile(rf"^(?P<subject>{_SUBJECT_ID})/(?P<entry>{_SLUG})$")


@dataclass(frozen=True)
class SourceReference:
    """A normalized source record, optionally one paragraph of it."""

    record_id: str
    paragraph: int | None = None


@dataclass(frozen=True)
class PathReference:
    """A file in the repository, addressed by its repository-relative path."""

    path: PurePosixPath


@dataclass(frozen=True)
class ChapterReference:
    """A chapter, addressed by its stable ``CHP-`` ID rather than its
    (renumberable) directory (#35)."""

    chapter_id: str


@dataclass(frozen=True)
class SectionReference:
    """A section, addressed by its stable ``SEC-`` ID rather than its
    (renumberable) directory (#35), and optionally one paragraph of its
    prose (#42) - positional, 1-based, and never a durable pointer (see
    ``_SECTION_PARAGRAPH``)."""

    section_id: str
    paragraph: int | None = None


@dataclass(frozen=True)
class ChangeReference:
    """A human-authored commit, addressed by its stable ``CHG-`` id
    (ADR-0008)."""

    change_id: str


@dataclass(frozen=True)
class SessionReference:
    """A derived session record, addressed by its ``SES-`` id (#28), and
    optionally one transcript turn of it.

    ``turn`` is ``None`` for a bare session reference, which resolves to the
    whole ``transcript.md``; otherwise it is the 1-based turn number a
    ``#T017`` fragment names.
    """

    session_id: str
    turn: int | None = None


@dataclass(frozen=True)
class DecisionReference:
    """An author decision, addressed by its stable ``DEC-`` id (#30)."""

    decision_id: str


@dataclass(frozen=True)
class ResearchMemoReference:
    """A durable research memo, addressed by its stable ``RES-`` id (#30)."""

    memo_id: str


@dataclass(frozen=True)
class ClaimReference:
    """A claim, addressed by its stable ``CLM-`` id (#33)."""

    claim_id: str


@dataclass(frozen=True)
class SubjectReference:
    """A subject, or one entry under it (part 04 §4's ``SUB-x`` / ``SUB-x/y``).

    ``entry_slug`` is ``None`` for a bare subject reference.
    """

    subject_id: str
    entry_slug: str | None = None


@dataclass(frozen=True)
class UnknownReference:
    """A reference whose kind this build cannot resolve.

    ``kind`` is the prefix as the caller wrote it, so the error can quote it
    back. ``known`` distinguishes a kind part 04 §4 defines but nothing
    implements yet from one that is not a kind at all.
    """

    kind: str
    known: bool


Reference = (
    SourceReference
    | SubjectReference
    | PathReference
    | ChapterReference
    | SectionReference
    | ChangeReference
    | SessionReference
    | DecisionReference
    | ResearchMemoReference
    | ClaimReference
    | UnknownReference
)


class BadReference(Exception):
    """Raised for a reference whose kind is clear but whose form is wrong."""


def anchor(record_id: str, paragraph_number: int) -> str:
    """The stable anchor id for a record's Nth paragraph (1-based).

    The single source of the ``src-000184-p17`` form, in both directions:
    ``NormalizedRecord.anchor_id`` writes through it and ``parse`` reads
    through it, so the grammar can only ever change in one place.
    """
    return f"{record_id.lower()}-p{paragraph_number}"


def split_anchor(anchor_id: str) -> tuple[str, int]:
    """The record ID and paragraph number an anchor names."""
    match = _FRAGMENT.match(anchor_id)
    if match is None:
        raise BadReference(f"not a paragraph anchor: {anchor_id!r}")
    # Lower-cased first: the pattern is case-insensitive, so a retyped
    # `#SRC-000184-P17` reaches here in caps and a case-sensitive split would
    # hand the whole string to int().
    record_id, _, number = match.group("anchor").lower().rpartition("-p")
    return record_id.upper(), int(number)


def parse(ref: str) -> Reference:
    """Read a reference's kind off the reference itself.

    Accepts, for a normalized source record:

    ==================================  ===========================
    ``SRC-000184``                      the whole record
    ``SRC-000184 ¶17`` / ``SRC-000184 P17``  one paragraph
    ``SRC-000184#src-000184-p17``       the markdown link form
    ``#src-000184-p17``                 the fragment alone
    ``src-000184-p17``                  a search result's anchor, verbatim
    ==================================  ===========================

    The last is not a convenience. ``index.SearchResult`` carries
    ``(src_id, anchor, source_type)``, so accepting a bare anchor is what lets
    a search hit be fed straight into ``read`` instead of being reassembled
    into a citation string inside an adapter (#12).

    Anything else that is ID-shaped is an ``UnknownReference``; anything else
    at all is a repository path.
    """
    ref = ref.strip()
    if not ref:
        raise BadReference("empty reference")

    match = _BARE_ID.match(ref)
    if match:
        return SourceReference(match.group("id").upper())

    match = _BARE_CHAPTER_ID.match(ref)
    if match:
        return ChapterReference(match.group("id").upper())

    match = _BARE_SECTION_ID.match(ref)
    if match:
        return SectionReference(match.group("id").upper())

    match = _SECTION_PARAGRAPH.match(ref)
    if match:
        return SectionReference(match.group("id").upper(), int(match.group("n")))

    match = _BARE_CHANGE_ID.match(ref)
    if match:
        return ChangeReference(match.group("id").upper())

    match = _BARE_DECISION_ID.match(ref)
    if match:
        return DecisionReference(match.group("id").upper())

    match = _BARE_RESEARCH_MEMO_ID.match(ref)
    if match:
        return ResearchMemoReference(match.group("id").upper())

    match = _BARE_CLAIM_ID.match(ref)
    if match:
        return ClaimReference(match.group("id").upper())

    match = _SESSION_TURN.match(ref)
    if match:
        return SessionReference(_canonical_session_id(match), int(match.group("turn")))

    match = _BARE_SESSION_ID.match(ref)
    if match:
        return SessionReference(_canonical_session_id(match))

    match = _ID_PARAGRAPH.match(ref)
    if match:
        return SourceReference(match.group("id").upper(), int(match.group("n")))

    match = _ID_FRAGMENT.match(ref)
    if match:
        record_id, paragraph = split_anchor(match.group("anchor"))
        if record_id != match.group("id").upper():
            # Both halves carry the ID, so they can disagree. Preferring one
            # silently would resolve a citation the author did not write.
            raise BadReference(
                f"reference names two different records: {match.group('id')} "
                f"and {record_id}"
            )
        return SourceReference(record_id, paragraph)

    match = _FRAGMENT.match(ref)
    if match:
        record_id, paragraph = split_anchor(match.group("anchor"))
        return SourceReference(record_id, paragraph)

    match = _SUBJECT_ENTRY.match(ref)
    if match:
        return SubjectReference(match.group("subject"), match.group("entry"))

    match = _BARE_SUBJECT.match(ref)
    if match:
        return SubjectReference(match.group("id"), None)

    match = _ID_SHAPED.match(ref)
    if match:
        kind = match.group("kind")
        if kind.upper() == "SRC":
            # It is a source reference and it is malformed - six digits is the
            # form. Saying so beats "no such kind", which would be untrue.
            raise BadReference(
                f"malformed source reference: {ref!r} - expected a six-digit "
                "ID like SRC-000184, optionally with a paragraph "
                "(SRC-000184 P17 or #src-000184-p17)"
            )
        if kind.upper() == "CHP":
            raise BadReference(
                f"malformed chapter reference: {ref!r} - expected a "
                "four-digit ID like CHP-0001"
            )
        if kind.upper() == "SEC":
            raise BadReference(
                f"malformed section reference: {ref!r} - expected a "
                "four-digit ID like SEC-0001"
            )
        if kind.upper() == "CHG":
            raise BadReference(
                f"malformed change reference: {ref!r} - expected a "
                "CHG-YYYYMMDD-NNN ID like CHG-20261014-003"
            )
        if kind.upper() == "DEC":
            raise BadReference(
                f"malformed decision reference: {ref!r} - expected a "
                "four-digit ID like DEC-0088"
            )
        if kind.upper() == "RES":
            raise BadReference(
                f"malformed research memo reference: {ref!r} - expected a "
                "RES-YYYYMMDD-NNN ID like RES-20261018-003"
            )
        if kind.upper() == "CLM":
            raise BadReference(
                f"malformed claim reference: {ref!r} - expected a four-digit "
                "ID like CLM-0041"
            )
        if kind.upper() == "SES":
            raise BadReference(
                f"malformed session reference: {ref!r} - expected a "
                "SES-YYYYMMDD-HHMM ID like SES-20260912-1432, optionally "
                "with a turn (SES-20260912-1432#T017)"
            )
        if kind.upper() == "SUB":
            # Same call as SRC above: this is a subject reference, and it is
            # malformed - lowercase slugs is the form, and neither pattern
            # above matched.
            raise BadReference(
                f"malformed subject reference: {ref!r} - expected SUB-<subject> "
                "or SUB-<subject>/<entry>, with lowercase slugs (e.g. "
                "SUB-people or SUB-people/bob)"
            )
        return UnknownReference(
            kind=kind.upper(), known=kind.upper() in NOT_YET_IMPLEMENTED_KINDS
        )

    return PathReference(_repository_path(ref))


def _repository_path(ref: str) -> PurePosixPath:
    """A repository-relative path, or a refusal.

    Reads are confined to the repository, and this is the first of the two
    checks that make that true. It is a check on the *reference*: an absolute
    path, a drive letter, or a `..` component is refused before anything
    touches the filesystem, so no caller has to remember to check.

    The second check is in ``records.read``, against the resolved path, and
    both are needed. This one cannot see a symlink; that one cannot give as
    good an error message, because by then the reference has become a path.

    Backslashes are refused outright rather than normalized. `docs\\..\\x` is
    one component here and three on Windows, so treating it as a filename
    would confine the read on this machine and not on another - and a rule
    that holds only on the developer's platform is not a rule. No legitimate
    reference contains one: the repository's own link form (part 04 §4) is
    POSIX, and so is every path in the record schema.
    """
    if "\\" in ref:
        raise BadReference(
            f"not a repository-relative path: {ref!r} - use / as the separator"
        )
    path = PurePosixPath(ref)
    if not path.parts:
        # `.` and `./` parse to no components at all. A directory is not a
        # readable reference, and indexing parts[0] here would crash.
        raise BadReference(f"not a file: {ref!r}")
    if path.is_absolute() or ":" in path.parts[0]:
        raise BadReference(f"not a repository-relative path: {ref!r}")
    if ".." in path.parts:
        raise BadReference(f"path escapes the repository: {ref!r}")
    return path


def format_citation(reference: Reference) -> str:
    """The canonical way to write a reference back to a reader."""
    if isinstance(reference, SourceReference):
        if reference.paragraph is None:
            return reference.record_id
        return f"{reference.record_id} ¶{reference.paragraph}"
    if isinstance(reference, SubjectReference):
        if reference.entry_slug is None:
            return reference.subject_id
        return f"{reference.subject_id}/{reference.entry_slug}"
    if isinstance(reference, PathReference):
        return str(reference.path)
    if isinstance(reference, ChapterReference):
        return reference.chapter_id
    if isinstance(reference, SectionReference):
        if reference.paragraph is None:
            return reference.section_id
        return f"{reference.section_id} ¶{reference.paragraph}"
    if isinstance(reference, ChangeReference):
        return reference.change_id
    if isinstance(reference, DecisionReference):
        return reference.decision_id
    if isinstance(reference, ResearchMemoReference):
        return reference.memo_id
    if isinstance(reference, ClaimReference):
        return reference.claim_id
    if isinstance(reference, SessionReference):
        if reference.turn is None:
            return reference.session_id
        return f"{reference.session_id}#T{reference.turn:03d}"
    return f"{reference.kind}-"
