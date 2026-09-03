"""The one scope resolver (#36, part 06 §8.5 / docs/plan/16-build-order.md M5).

A brief's declared scope (`memoria.manuscript.Brief.text` - prose, not a field
of its own, part 04 §2.1) names what a section covers: *"June 1839 to October
1841, and my interactions with Bob about the conflict in the capital"*. Three
call sites need the same answer to "what entries does that name" - **assembly**
(what to load, #38), **the audit's bounding** (what prose is checked against,
#40) and **drift detection** (whether the brief still describes the prose,
#41) - and three of them independently inferring it would be a divergence bug
scheduled in advance: the kind that shows up as "the audit checked against
something assembly never loaded" months later, with no one wrong line to
point at.

None of those three exist yet (#38, #40, #41 are still open) - this issue is
built first precisely so whichever lands first does not grow its own copy.
`test_scope.py`'s isolation test is the trap for a module that reimplements
this instead of calling `resolve_scope`, the same shape as
`manuscript.py`'s "no module but manuscript knows a brief's filename" guard.

**Resolution is lexical, deterministic, and does no model call** - the same
contract `memoria.index.gather` keeps for a gathered set. A brief names an
entry the way any prose does: by its own implicit name (the words its slug
came from) or by one of its declared match terms (`memoria.subjects`'s "only
alias store"). Entry- and relation-shaped match terms name co-occurrence for
gathering, not a phrase a brief's prose would ever contain, so only the
word-shaped ones - and the implicit name every entry carries regardless of
what it declares - are scanned for.

Given the same brief text against the same entries on disk, the answer is the
same every time: no index, no cache, and no ordering dependency, so "at a
given repository revision" is not a claim resolve_scope has to work to keep -
it falls out of doing nothing but a lexical scan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from memoria.extraction import implicit_name_term
from memoria.manuscript import Brief
from memoria.repository import Repository
from memoria.subjects import Entry, classify_match_term, load_all_entries


@dataclass(frozen=True)
class ScopeResolution:
    """What one `resolve_scope` call found, and how - the report part 11
    §33.1 requires ("assembly must report what it resolved") in a form any of
    the three consumers, and the surface behind them, can display.

    ``entry_ids`` is the resolved set, sorted for a stable, reproducible
    result (matching `index.gather`'s own ordering choice). ``matched_by``
    names, for every resolved entry, which of its match terms - or its
    implicit name - the brief text actually contains, in declaration order:
    the "how" half of the report, the same shape as `index.Appearance.note`.

    ``unconfirmed`` carries the brief's own unconfirmed state
    (`manuscript.Brief.unconfirmed`) through unexamined - resolution over an
    unconfirmed brief still runs (part 11 §32's "assembly uses it"), but a
    caller needs to know to flag the result as resting on a draft rather than
    an author-confirmed scope (the audit does not check drift against one,
    part 11 §32).

    ``empty`` is explicit rather than left to `not entry_ids`: a scope that
    resolves to nothing must be *reported* as that, not returned
    indistinguishably from a resolution nobody has looked at yet (#36's sixth
    acceptance criterion) - `resolution.empty` reads as the resolver telling
    a caller it found nothing, where `not resolution.entry_ids` alone reads as
    "it happened to be empty."
    """

    entry_ids: tuple[str, ...]
    matched_by: dict[str, tuple[str, ...]]
    unconfirmed: bool
    empty: bool


def _terms_for(entry_id: str, entry: Entry) -> list[str]:
    """The phrases this entry can be found by in free prose: its own
    implicit name, then its word-shaped match terms in declaration order.
    Entry- and relation-shaped terms (`classify_match_term`) name
    co-occurrence between placed entries, never a phrase a brief's author
    would type, so they take no part in this scan - the same split
    `index.compute_appearances` already draws for the same reason."""
    terms = [implicit_name_term(entry_id)]
    terms.extend(
        term for term in entry.match_terms if classify_match_term(term) == "word"
    )
    return terms


def contains_term(text: str, term: str) -> bool:
    """Whether ``term`` appears in ``text`` as a whole word or phrase,
    case-insensitively.

    Bounded with lookaround rather than ``\\b`` on both sides: a term ending
    in punctuation - "R." among the initials part 06 §8.1's People hazards
    name - has no word-character/non-word-character transition after its
    final character when followed by a space, so a trailing ``\\b`` would
    reject exactly the sentence-medial mention this is for. ``(?!\\w)`` only
    asks that the next character not itself be a word character, which "R."
    followed by a space satisfies.
    """
    pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def resolve_scope(repository: Repository, brief: Brief) -> ScopeResolution:
    """Resolve ``brief``'s declared scope through the subjects into the
    entries it names (#36's first acceptance criterion).

    Every entry on disk (`load_all_entries`) is checked against the brief's
    whole text - there is no separate scope field to isolate first
    (`manuscript.Brief`'s docstring: the declared scope "is not a field of
    its own") - for whichever of its own name or match terms the text
    contains. No model call and no index read: everything this needs is
    already durable on the entry files themselves.
    """
    entries = load_all_entries(repository)
    matched_by: dict[str, tuple[str, ...]] = {}
    for entry_id, entry in sorted(entries.items()):
        hits = tuple(
            term for term in _terms_for(entry_id, entry)
            if contains_term(brief.text, term)
        )
        if hits:
            matched_by[entry_id] = hits
    entry_ids = tuple(sorted(matched_by))
    return ScopeResolution(
        entry_ids=entry_ids,
        matched_by=matched_by,
        unconfirmed=brief.unconfirmed,
        empty=not entry_ids,
    )
