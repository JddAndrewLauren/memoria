"""Assembly (#38, part 06 §8.5, part 11 §32-33.1): a section's declared scope
resolved through the one scope resolver into a working context to write
from, and - the part that matters most - a report of what it resolved.

*"Bring the whole archive, ask the real question, Memoria handles the
context."* Assembly is what makes that true at write time, in service of one
session. It is not curation, and it writes nothing durable: nothing here
touches a manuscript file, an entry file, or any of ``memoria.write``'s
durable state classes (``memoria.write.DURABLE_PATHS``) - the one thing this
module produces is a value, handed back to its caller, plus a line appended
to the session's own ledger (``memoria.ledger``), which is Interaction
record, not a durable state class either (``memoria.write``'s own docstring).

**Resolution is the one scope resolver's job, not this module's** (#36).
``assemble`` calls ``memoria.scope.resolve_scope`` and reports what it found;
it never re-scans a brief's text against entries itself -
``tests/test_scope.py``'s content-based guard is what would catch a copy of
that scan under a different name.

**Loaded content is the audit-visible body only** (CONTEXT.md's
"Audit-visible body"): testimony, settlements and every badged statement
except ``[open]`` - ``memoria.audit.audit_visible_body``, the same function
the audit itself loads a paragraph's comparison text from (#37), so the two
consumers agree on what an entry's body even is without either growing its
own copy. Memoria notes join the exclusion once part 08 §14.2 writes them;
today there is nothing else to exclude, per that function's own docstring.

**Gathered sets are reported, not loaded.** An entry's gathered set
(``memoria.index.gather``) rides on the working context as identifiers - its
sources' anchors - never as the paragraph text they name. Tier 4 stays on
demand (part 11 §32): a caller that wants the evidence itself reads it
through ``read(ref)``, which is also what ledgers it as served. Reporting the
gathered set's membership here is what lets a caller say *how many* sources
back an entry without pretending assembly loaded them.

**Assembly never dead-ends** (part 06 §8.4, part 11 §32): a declared scope
naming something with no entry falls back to the unpromoted candidate whose
label the brief text contains, and says that it did (``ScopeFallback``
below) - without loading anything about the candidate beyond its identity.
Context stays safe: an unpromoted candidate never enters a session either
way.

**§33.1's obligation, discharged in countable domain units.** The working
context states how many entries, sources and fallbacks it found - never a
token figure (ADR-0001, part 14 §40 as amended) - and claims only what this
call **supplied**: an entry's audit-visible body and a gathered set's
identifiers, nothing about what a model still holds from an earlier turn.
That broader claim belongs to the supplied-context surface (#61), which folds
this call's own ledger line in with every read served since; assembly's own
report is only ever about what one ``assemble`` call itself resolved.

**Reproducible per session, not globally deterministic** (part 11 §32): the
same brief against the same entries, subjects and candidates on disk answers
the same way every time, because ``resolve_scope`` already carries that
property and nothing here adds a second source of variation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from memoria import ledger
from memoria.audit import audit_visible_body
from memoria.extraction import candidates as list_candidates
from memoria.index import GatheredSource, gather
from memoria.manuscript import Brief
from memoria.repository import Repository
from memoria.scope import resolve_scope
from memoria.subjects import load_entry


@dataclass(frozen=True)
class ResolvedEntry:
    """One entry the declared scope resolved to.

    ``matched_by`` is ``resolve_scope``'s own report of how - carried through
    unchanged, so a caller sees the same "which phrase found it" account the
    resolver already computed. ``audit_visible_body`` is what Tier 2 actually
    loads; ``gathered_set`` is Tier 4's membership, reported as identifiers
    for the countable half of §33.1's obligation, not loaded as text.
    """

    entry_id: str
    matched_by: tuple[str, ...]
    audit_visible_body: str
    gathered_set: tuple[GatheredSource, ...]


@dataclass(frozen=True)
class ScopeFallback:
    """A phrase the declared scope names that resolved to no entry, but
    matched an unpromoted candidate's label - part 06 §8.4's "assembly never
    dead-ends". Carries the candidate's identity only: its content, if any,
    never enters a session (candidates are index rows, CONTEXT.md's
    "Candidate")."""

    subject_id: str
    candidate_id: str
    label: str


@dataclass(frozen=True)
class WorkingContext:
    """What one ``assemble`` call produced: the resolution, in the form both
    the working context and its own report take, since here they are the
    same value. ``unconfirmed`` and ``empty`` carry ``ScopeResolution``'s own
    fields through unchanged - see ``memoria.scope.ScopeResolution`` for what
    each means to a caller.
    """

    resolved_entries: tuple[ResolvedEntry, ...]
    fallbacks: tuple[ScopeFallback, ...]
    unconfirmed: bool
    empty: bool


def _label_matches(brief_text: str, label: str) -> bool:
    """Whether ``label`` appears in ``brief_text`` as a whole word or phrase,
    case-insensitively - a candidate's label is free-form surface text, not a
    match term, so it gets the same lookaround-bounded scan
    ``scope._contains_term`` uses for the same reason: a trailing period in a
    label must not need a word-character after it to still count."""
    pattern = r"(?<!\w)" + re.escape(label) + r"(?!\w)"
    return re.search(pattern, brief_text, re.IGNORECASE) is not None


def _fallbacks(repository: Repository, brief: Brief) -> tuple[ScopeFallback, ...]:
    """Every unpromoted candidate whose label the brief text names - part 06
    §8.4's fallback, computed independently of which entries resolved: a
    candidate is by definition an unplaced surface form, so it can never
    collide with an entry's own match terms (``extraction.build_candidates``
    only ever groups forms that were *not* licensed by one)."""
    found = [
        ScopeFallback(candidate.subject_id, candidate.candidate_id, candidate.label)
        for candidate in list_candidates(repository)
        if _label_matches(brief.text, candidate.label)
    ]
    return tuple(sorted(found, key=lambda fallback: (fallback.subject_id, fallback.label)))


def assemble(repository: Repository, session_id: str, brief: Brief) -> WorkingContext:
    """Resolve ``brief``'s declared scope and load Tier 2 for it (#38).

    Ledgers the resolution against ``session_id`` (``memoria.ledger``) before
    returning, which is what lets ``memoria.context_manifest`` project it
    onto that session's manifest - "recorded in that session's context
    manifest, never written back onto the section" (CONTEXT.md's "Declared
    scope"). Nothing here writes to ``brief`` or to any file the brief names.
    """
    resolution = resolve_scope(repository, brief)
    resolved_entries = tuple(
        ResolvedEntry(
            entry_id=entry_id,
            matched_by=resolution.matched_by[entry_id],
            audit_visible_body=audit_visible_body(
                load_entry(repository, *entry_id.split("/", 1))
            ),
            gathered_set=tuple(gather(repository, entry_id)),
        )
        for entry_id in resolution.entry_ids
    )
    fallbacks = _fallbacks(repository, brief)

    ledger.append_assembly(
        repository,
        session_id,
        entries=[
            {
                "entry_id": resolved.entry_id,
                "matched_by": list(resolved.matched_by),
                "sources": [source.anchor for source in resolved.gathered_set],
            }
            for resolved in resolved_entries
        ],
        fallbacks=[
            {
                "subject_id": fallback.subject_id,
                "candidate_id": fallback.candidate_id,
                "label": fallback.label,
            }
            for fallback in fallbacks
        ],
        unconfirmed=resolution.unconfirmed,
        empty=resolution.empty,
    )

    return WorkingContext(
        resolved_entries=resolved_entries,
        fallbacks=fallbacks,
        unconfirmed=resolution.unconfirmed,
        empty=resolution.empty,
    )
