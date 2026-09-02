"""Brief drift as a set difference (#41, part 06 §8.5 / part 11 §32).

A brief's declared scope names what a section of the manuscript covers; drift
is what fires when the prose stops matching that description. Part 11 §32
settles the shape: **"Drift is a set difference, not a check."** Assembly
already resolves a brief to a set of entries (``scope.resolve_scope``, #36),
and ``appearances`` (part 06 §8.11) already knows which entries the
manuscript prose touches - so drift is subtracting two sets that exist for
other reasons, never a bespoke question and never a model call.

Two accepted costs, both kept visible in the report rather than collapsed
into a boolean (#41's own framing): a deliberately loose brief resolves to
few entries and reports drift constantly - the intended pressure, not noise
to suppress - and nothing repairs a stale brief but drift detection actually
firing, so silence here would make the whole mechanism decorative.

This module owns nothing of its own: it calls ``scope.resolve_scope`` for
the declared side (the one scope resolver, #36 - ``test_scope.py``'s
isolation guard is what would catch a second copy of that resolution) and
``index.appeared_entry_ids`` for the covered side, which is exactly as
model-free or as memoized as ``compute_appearances`` already is. It writes
nothing: a finding may not be resolved by editing the brief from a review
card (part 06 §8.10), and this module never imports a brief-writing
function.
"""

from __future__ import annotations

from dataclasses import dataclass

from memoria.extraction import CO_OCCURRENCE_SUBJECTS
from memoria.index import appeared_entry_ids
from memoria.manuscript import Brief
from memoria.repository import Repository
from memoria.scope import resolve_scope

_UNCONFIRMED_REASON = (
    "brief is unconfirmed: a brief summarized from the prose agrees with it "
    "by construction, so comparing the prose against it would be circular "
    "(part 11 §32)"
)


@dataclass(frozen=True)
class DriftReport:
    """What one ``compute_drift`` call found.

    ``skipped``/``reason`` carry the one case drift refuses to run against -
    an unconfirmed brief. When ``skipped`` is true the two sets below are
    empty because nothing was checked, not because nothing drifted.

    ``covered_but_undeclared`` is prose touching an entry the brief's
    resolved scope never named - part 11 §32's own example ("prose appearing
    under SUB-events/acquisition in a section whose brief never names it is
    drift"). ``declared_but_uncovered`` is the reverse: an entry the brief
    resolved to that the prose never turns out to touch. Reporting both
    directions, rather than a single boolean, is what keeps a stale brief and
    a deliberately loose one diagnosable as the different problems they are.

    ``unmatchable`` is the declared entries the covered side is structurally
    incapable of ever containing: ``compute_appearances`` never indexes
    entries under ``extraction.CO_OCCURRENCE_SUBJECTS`` (Themes and Arcs are
    shown by co-occurrence, not lexical match), while ``resolve_scope``
    resolves them like any other. Left in the subtraction they would read as
    "the prose never touches this" permanently, for any brief that names a
    theme - a false finding, not the intended pressure. So, as #19's
    ``AppearancesReport`` names its skipped subjects rather than absorbing
    them into zero appearances, drift names them here rather than absorbing
    them into ``declared_but_uncovered``.
    """

    skipped: bool
    reason: str | None
    covered_but_undeclared: tuple[str, ...]
    declared_but_uncovered: tuple[str, ...]
    unmatchable: tuple[str, ...]


def compute_drift(repository: Repository, brief: Brief) -> DriftReport:
    """Compute ``brief``'s drift from the manuscript prose.

    Never evaluated against an unconfirmed brief (part 11 §32): resolution
    over one still works for assembly, but a brief drafted by summarizing the
    very prose it would constrain agrees with that prose by construction, so
    the comparison reports zero drift precisely when the brief is least
    trustworthy - reporting ``skipped`` instead is the honest answer.

    Otherwise this is nothing but a set difference between what
    ``resolve_scope`` resolves the brief to and what ``appeared_entry_ids``
    reports the prose already touches - both computed fresh from the current
    entries, brief text and index on every call, so drift is recomputed
    whenever any of the three changes without this module holding a cache of
    its own to go stale.
    """
    if brief.unconfirmed:
        return DriftReport(
            skipped=True,
            reason=_UNCONFIRMED_REASON,
            covered_but_undeclared=(),
            declared_but_uncovered=(),
            unmatchable=(),
        )

    resolved = set(resolve_scope(repository, brief).entry_ids)
    unmatchable = {
        entry_id
        for entry_id in resolved
        if entry_id.split("/", 1)[0] in CO_OCCURRENCE_SUBJECTS
    }
    declared = resolved - unmatchable
    covered = set(appeared_entry_ids(repository))
    return DriftReport(
        skipped=False,
        reason=None,
        covered_but_undeclared=tuple(sorted(covered - declared)),
        declared_but_uncovered=tuple(sorted(declared - covered)),
        unmatchable=tuple(sorted(unmatchable)),
    )
