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
# rejects them is the shape rule above, not this list.
NOT_YET_IMPLEMENTED_KINDS = ("SES", "CHG", "CLM", "RES", "DEC", "SUB")


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
class UnknownReference:
    """A reference whose kind this build cannot resolve.

    ``kind`` is the prefix as the caller wrote it, so the error can quote it
    back. ``known`` distinguishes a kind part 04 §4 defines but nothing
    implements yet from one that is not a kind at all.
    """

    kind: str
    known: bool


Reference = SourceReference | PathReference | UnknownReference


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
    if isinstance(reference, PathReference):
        return str(reference.path)
    return f"{reference.kind}-"
