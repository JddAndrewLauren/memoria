"""Settlements, and the claims they accrete into (#33, part 06 §8.7-§8.9).

A **settlement** is the author's recorded resolution of a surfaced conflict:
which side was chosen, against what, why, and when. It is **click-authorized**
- an explicit author act, never a heuristic - so ``settle`` takes a human,
attributed ``Actor`` and commits as theirs through the one write path
(ADR-0003), the same shape ``subjects.set_match_terms`` and the pin/exclude
overlay already have. A machine actor is refused: the Curator may write a
badged statement (#31), never a settlement.

**It lives on the entry, inside the audit-visible body**, as one
``[settled]`` paragraph (``subjects.parse_statements`` knows the badge, and
``subjects.is_audit_visible`` keeps it in). Part 06 §8.7's own illustration
is the first line's form, ``birth year 1962 — chosen over SRC-0184 ¶12,
2026-08-31``, with the winning side named in front of ``chosen over`` so the
same line serves all three of part 09 §18's directions::

    [settled] birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-09-02
    Reason: the author's own recollection outranks the letter's guess
    — SES-20260912-1432

**The passage is provenance, never a pointer.** A finding's disagreement set
carries the passage as a positional slot (``memoria.audit``: "no paragraph
carries a durable identity"), and nothing here writes that slot anywhere.
The side chosen or lost is written as the literal ``the passage``, and the
act's provenance is the **session** it happened in - a bare ``SES-`` id, not
a turn, because the click is not a turn and the transcript it would cite is
not derived until the session ends (#28). ``memoria validate`` holds the
form on what is on disk (``parse_settlement``), so a hand-edited settlement
without its session fails the same way a badged statement without provenance
does.

**Silence** (§8.7: "silences every downstream passage that relies on it")
is the audit's job, read from here: ``is_settled`` says whether a
disagreement set is one the entry has already settled, and
``memoria.audit.findings_in_scope`` drops such a finding rather than serve
it. The identity compared is the set's *evidence* members - its sources,
canonicalised - because the set is the finding's identity (§8.10)
and the passage has none: the same entry-versus-source disagreement raised
from any paragraph is the same settled disagreement. A set carrying only the
passage and the entry is therefore never mechanically silenced - settling it
toward the passage rewrote what the entry says, and the next audit reads
that; settling it toward the entry is refused outright as the plain rewrite
part 09 §18 says it is, since a settlement recording it would silence every
later passage that disagrees with the entry.

**Claims are the accretion layer** (§8.9), not a subject. A settlement *is*
a claim - a proposition, a status, supporting and contradicting evidence, a
date and reasoning - so ``settle`` writes one ``claims/CLM-NNNN.md`` as a
byproduct of the click, via ``claim_from_settlement`` and ``record_claim``,
which is also the door a claim the author asserts outright comes through.
The two writes are two path-scoped commits with no atomicity between them
(``memoria.write``'s own rule): a claim that fails to land after its
settlement did is reported naming the settled entry, and ``record_claim``
is what recovers it. A settlement-born claim's status is ``author`` - the
author decided, whichever side's content won - and its confidence ``high``,
which is what "settled" means. Its provenance names the entry and the
session, the ``THEME -> CLM -> SRC`` chain §26's ``trace()`` wants, recorded
at the click rather than reconstructed afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from datetime import date as date_type
from typing import TYPE_CHECKING, Iterable, Sequence

from memoria import references, subjects, write
from memoria.repository import Repository
from memoria.subjects import Entry, Statement
from memoria.write import Actor, Rejected

if TYPE_CHECKING:
    # Annotation only: ``memoria.audit`` imports this module for
    # ``is_settled``, so importing it back at runtime would cycle. A member
    # is anything carrying ``kind`` and ``ref``.
    from memoria.audit import DisagreementMember

SETTLED_BADGE = "settled"
CLAIMS_RELATIVE_PATH = "claims"
# What a settlement writes in place of the passage - a word, never a locator.
THE_PASSAGE = "the passage"
# The member kinds a settlement can name as chosen or chosen against, and
# the reference kind each one's ``ref`` must parse as - part 09 §18's rows
# that carry an entry name a passage, the entry and sources, nothing else.
# "brief" is absent on purpose (a brief is never a resolution target, part
# 06 §8.10) and so is "decision": its row carries no entry to settle on, and
# "revise the decision" is ``decisions.md``'s own affair.
_MEMBER_REFERENCE_KINDS = {
    "entry": references.SubjectReference,
    "source": references.SourceReference,
}
_MEMBER_KINDS = ("passage", *_MEMBER_REFERENCE_KINDS)

# The epistemic statuses a claim may carry - the three assertion badges of
# part 06 §9, since ownership everywhere in this system is read off the
# badge; and the three confidence tiers the audit already uses.
CLAIM_STATUSES = ("author", "source", "inferred")
CLAIM_CONFIDENCES = ("low", "moderate", "high")

_REASON_PREFIX = "Reason: "
_SESSION_PREFIX = "— "
_AND = " and "
_FIRST_LINE = re.compile(
    r"^(?P<proposition>.+) — (?P<chosen>.+?), chosen over (?P<against>.+?), "
    r"(?P<date>\d{4}-\d{2}-\d{2})$"
)
_CLAIM_ID = re.compile(r"^CLM-(\d{4})$")


class SettlementError(Exception):
    """Raised when a settlement or a claim cannot be recorded, or a recorded
    one cannot be read back - a set with nowhere to settle, an unattributed
    actor, a malformed ``[settled]`` paragraph, a write the write path
    rejected."""


@dataclass(frozen=True)
class Settlement:
    """One settlement as it stands on an entry.

    ``chosen`` and ``against`` are canonical citations - an entry id or a
    ``SRC-000184 ¶12`` paragraph - or the literal ``the passage``. ``date`` is ``YYYY-MM-DD``; ``session_id`` is the bare
    session the act happened in.
    """

    proposition: str
    chosen: tuple[str, ...]
    against: tuple[str, ...]
    reason: str
    date: str
    session_id: str

    def evidence_refs(self) -> frozenset[str]:
        """The identity of the disagreement this settled: its source
        members - never the passage, never the entry it sits on."""
        return frozenset(
            ref
            for ref in (*self.chosen, *self.against)
            if ref != THE_PASSAGE and not ref.startswith("SUB-")
        )


@dataclass(frozen=True)
class Claim:
    """A claim before it is minted an id and written (part 06 §8.9's file
    format, field for field). ``session_id`` is the session it was asserted
    or settled in; ``settled_on`` is the entry a settlement-born claim came
    from, ``None`` for one asserted directly."""

    proposition: str
    status: str
    confidence: str
    supporting: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    reasoning: str = ""
    session_id: str | None = None
    settled_on: str | None = None


@dataclass(frozen=True)
class ClaimRecord:
    """A claim as written to ``claims/``."""

    claim_id: str
    path: str
    claim: Claim


@dataclass(frozen=True)
class SettlementRecord:
    """What one ``settle`` call did: the settlement now on ``entry_id``, and
    the claim it accreted into."""

    entry_id: str
    settlement: Settlement
    claim_id: str
    claim: Claim


# --- the grammar, both directions ----------------------------------------------


def render_settlement(settlement: Settlement) -> str:
    """The ``[settled]`` paragraph ``parse_settlement`` reads back."""
    return "\n".join(
        [
            f"[{SETTLED_BADGE}] {settlement.proposition} — {_AND.join(settlement.chosen)}, "
            f"chosen over {_AND.join(settlement.against)}, {settlement.date}",
            f"{_REASON_PREFIX}{settlement.reason}",
            f"{_SESSION_PREFIX}{settlement.session_id}",
        ]
    )


def parse_settlement(statement: Statement) -> Settlement:
    """A ``[settled]`` statement back into a ``Settlement``, or a
    ``SettlementError`` naming what is missing - the check ``memoria
    validate`` applies to what is on disk."""
    if statement.badge != SETTLED_BADGE:
        raise SettlementError(f"not a settlement: [{statement.badge}]")
    lines = statement.text.splitlines()
    if len(lines) != 3:
        raise SettlementError(
            "a settlement is three lines - what was chosen over what and when, "
            f"'{_REASON_PREFIX.strip()}', and its '— SES-' session - got {len(lines)}"
        )
    first, reason_line, session_line = lines
    match = _FIRST_LINE.match(first)
    if match is None:
        raise SettlementError(
            "a settlement's first line is '<proposition> — <chosen>, chosen over "
            f"<against>, YYYY-MM-DD', got {first!r}"
        )
    try:
        date_type.fromisoformat(match.group("date"))
    except ValueError as exc:
        raise SettlementError(f"a settlement's date is not a date: {match.group('date')!r}") from exc
    if not reason_line.startswith(_REASON_PREFIX) or not reason_line[len(_REASON_PREFIX):].strip():
        raise SettlementError(f"a settlement's second line is its reason, got {reason_line!r}")
    session_id = session_line[len(_SESSION_PREFIX):].strip() if session_line.startswith(_SESSION_PREFIX) else ""
    return Settlement(
        proposition=match.group("proposition"),
        chosen=tuple(match.group("chosen").split(_AND)),
        against=tuple(match.group("against").split(_AND)),
        reason=reason_line[len(_REASON_PREFIX):].strip(),
        date=match.group("date"),
        session_id=_session_provenance(session_id),
    )


def _session_provenance(session_id: str) -> str:
    """The canonical bare session id, or a ``SettlementError``: the
    provenance of the act is the session it happened in, whole."""
    try:
        reference = references.parse(session_id) if session_id else None
    except references.BadReference:
        reference = None
    if not isinstance(reference, references.SessionReference) or reference.turn is not None:
        raise SettlementError(
            f"a settlement's provenance is the session it happened in - a bare "
            f"SES- id, not a turn - got {session_id!r}"
        )
    return references.format_citation(reference)


def settlements_on(entry: Entry) -> list[Settlement]:
    """Every settlement an entry's body carries. A malformed one raises -
    ``memoria validate`` is where it is reported as a finding."""
    return [
        parse_settlement(statement)
        for statement in subjects.parse_statements(entry.body)
        if statement.badge == SETTLED_BADGE
    ]


# --- the act ---------------------------------------------------------------------


def _canonical(ref: str) -> str:
    """A member's ref as a citation, if it parses; verbatim otherwise. Used on
    the read side (``is_settled``), which compares and never refuses."""
    try:
        reference = references.parse(ref)
    except references.BadReference:
        return ref
    if isinstance(reference, (references.UnknownReference, references.PathReference)):
        return ref
    return references.format_citation(reference)


def _member_citation(member: DisagreementMember) -> str:
    """A chosen-or-against member's canonical citation, refusing a ref that
    is not the reference kind its member kind names - a durable record
    should not carry a locator nothing can resolve."""
    expected = _MEMBER_REFERENCE_KINDS[member.kind]
    try:
        reference = references.parse(member.ref)
    except references.BadReference as exc:
        raise SettlementError(f"cannot settle over {member.ref!r}: {exc}") from exc
    if not isinstance(reference, expected) or (
        member.kind == "entry" and reference.entry_slug is None
    ):
        raise SettlementError(
            f"cannot settle over {member.ref!r}: a {member.kind} member is not "
            f"a {expected.__name__}"
        )
    return references.format_citation(reference)


def settle(
    repository: Repository,
    disagreement_set: Sequence[DisagreementMember],
    *,
    side: str,
    proposition: str,
    reason: str,
    session_id: str,
    token: str,
    actor: Actor,
    today: str | None = None,
) -> SettlementRecord | Rejected:
    """Settle a surfaced conflict toward ``side`` - see the module docstring.

    ``disagreement_set`` is the finding's own (``memoria.audit.Finding``);
    the one ``entry`` member is where the settlement lands, the ``passage``
    member is dropped, and every other member is what was chosen or chosen
    against. ``token`` is the one ``subjects.serve_entry`` minted for the
    read the author acted on (ADR-0003); an entry changed since is
    ``memoria.write``'s ``Rejected``, returned rather than raised, because a
    stale read is the normal outcome the caller tells apart from a refusal.
    The settlement is written first and the claim accreted second.
    """
    if not actor.human:
        raise SettlementError(
            "a settlement is an author act (part 06 §8.7): a machine actor "
            "cannot make one"
        )
    if not actor.name.strip() or not actor.email.strip():
        raise SettlementError(
            "a settlement is an author act and must be attributed - actor name "
            "and email may not be empty"
        )
    session_id = _session_provenance(session_id)
    proposition = proposition.strip()
    reason = reason.strip()
    if not proposition or "\n" in proposition or " — " in proposition:
        raise SettlementError(
            "a settlement's proposition is one line, non-empty, and carries no "
            "' — ' of its own (it is the line's separator)"
        )
    if not reason or "\n" in reason:
        raise SettlementError("a settlement's reason is one non-empty line")
    date = today or date_type.today().isoformat()
    try:
        date_type.fromisoformat(date)
    except ValueError as exc:
        raise SettlementError(f"a settlement's date is not a date: {date!r}") from exc

    kinds = {member.kind for member in disagreement_set}
    if "brief" in kinds:
        raise SettlementError(
            "a brief is never a resolution target (part 06 §8.10): a set naming "
            "one offers a conversation about the brief, not a settlement"
        )
    if not kinds <= set(_MEMBER_KINDS):
        raise SettlementError(
            "a settlement is over a passage, an entry and sources (part 09 §18); "
            f"this set carries {', '.join(sorted(kinds - set(_MEMBER_KINDS)))}"
        )
    entry_members = [member for member in disagreement_set if member.kind == "entry"]
    if len(entry_members) != 1:
        raise SettlementError(
            "a settlement is stored on the entry (part 06 §8.7), and this set "
            f"names {'no entry' if not entry_members else 'more than one'} - "
            "its resolutions are a rewrite or an exclusion, not a settlement"
        )
    if side not in kinds:
        raise SettlementError(
            f"cannot settle toward {side!r}: the set carries "
            f"{', '.join(sorted(kinds))}"
        )
    entry_id = _member_citation(entry_members[0])
    chosen = tuple(
        THE_PASSAGE if member.kind == "passage" else _member_citation(member)
        for member in disagreement_set
        if member.kind == side
    )
    against = tuple(
        _member_citation(member)
        for member in disagreement_set
        if member.kind not in (side, "passage")
    )
    if not against:
        raise SettlementError(
            f"nothing to settle {proposition!r} against but the passage - "
            "rewrite the passage instead; that is not a settlement (part 09 §18)"
        )

    settlement = Settlement(
        proposition=proposition,
        chosen=chosen,
        against=against,
        reason=reason,
        date=date,
        session_id=session_id,
    )
    subject_id, entry_slug = entry_id.split("/", 1)
    try:
        relative_path = subjects.entry_relative_path(repository, subject_id, entry_slug)
        entry, _minted_here_and_unused = subjects.serve_entry(repository, subject_id, entry_slug)
    except subjects.SubjectError as exc:
        raise SettlementError(str(exc)) from exc
    block = render_settlement(settlement)
    body = f"{entry.body.rstrip()}\n\n{block}" if entry.body.strip() else block
    content = subjects.entry_to_markdown(dataclass_replace(entry, body=body))
    result = write.write(repository, relative_path, token, content, actor)
    if isinstance(result, Rejected):
        return result

    claim = claim_from_settlement(entry_id, settlement)
    try:
        claim_record = record_claim(repository, claim, actor, today=date)
    except SettlementError as exc:
        raise SettlementError(
            f"the settlement landed on {entry_id} but its claim did not: {exc} - "
            "record it with record_claim"
        ) from exc
    return SettlementRecord(
        entry_id=entry_id, settlement=settlement, claim_id=claim_record.claim_id, claim=claim
    )


def is_settled(entry: Entry, disagreement_set: Iterable[DisagreementMember]) -> bool:
    """Whether ``entry`` already carries a settlement of this disagreement -
    the rule ``memoria.audit.findings_in_scope`` stays silent by. Identity
    is the set's evidence members, canonicalised (see the module docstring);
    a set with none is never settled here. A malformed settlement on the
    entry counts for nothing rather than raising out of a read."""
    refs = frozenset(
        _canonical(member.ref)
        for member in disagreement_set
        if member.kind not in ("passage", "entry")
    )
    if not refs:
        return False
    for statement in subjects.parse_statements(entry.body):
        if statement.badge != SETTLED_BADGE:
            continue
        try:
            settlement = parse_settlement(statement)
        except SettlementError:
            continue
        if settlement.evidence_refs() == refs:
            return True
    return False


# --- claims ------------------------------------------------------------------------


def claim_from_settlement(entry_id: str, settlement: Settlement) -> Claim:
    """The claim a settlement accretes into (part 06 §8.9): the chosen side is
    its supporting evidence, the losing side its contradicting evidence, the
    reason its reasoning. ``the passage`` contributes nothing - it is not a
    pointer, on either list."""
    return Claim(
        proposition=settlement.proposition,
        status="author",
        confidence="high",
        supporting=tuple(ref for ref in settlement.chosen if ref != THE_PASSAGE),
        contradicting=tuple(ref for ref in settlement.against if ref != THE_PASSAGE),
        reasoning=settlement.reason,
        session_id=settlement.session_id,
        settled_on=entry_id,
    )


def next_claim_id(repository: Repository) -> str:
    """Mint the next ``CLM-NNNN``: one more than the highest already in
    ``claims/`` - ``record_extractor.next_decision_id``'s scheme, with the
    same admitted gap."""
    directory = repository.root / CLAIMS_RELATIVE_PATH
    highest = 0
    if directory.is_dir():
        for path in directory.iterdir():
            match = _CLAIM_ID.match(path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"CLM-{highest + 1:04d}"


def _check_evidence(ref: str) -> None:
    """A claim's evidence is what an entry statement's provenance may be
    (#31's ``check_provenance``) plus an entry itself - the settled side of
    a settlement - and never manuscript prose or another derived artifact."""
    # Imported here, not at module scope: `memoria.record_extractor` reaches
    # this module (via `human_touched` -> `index` -> `records`), so the
    # reverse import must stay local to avoid a cycle.
    from memoria.record_extractor import RecordExtractorError, check_provenance

    try:
        reference = references.parse(ref)
    except references.BadReference as exc:
        raise SettlementError(f"claim evidence {ref!r}: {exc}") from exc
    if isinstance(reference, references.SubjectReference) and reference.entry_slug is not None:
        return
    try:
        check_provenance(ref)
    except RecordExtractorError as exc:
        raise SettlementError(f"claim evidence {exc}") from exc


def _render_claim(claim_id: str, claim: Claim, date: str) -> str:
    def section(title: str, value: str) -> list[str]:
        return [f"## {title}", "", value, ""]

    def list_section(title: str, values: tuple[str, ...]) -> list[str]:
        return [f"## {title}", "", *(f"- {v}" for v in values), ""] if values else []

    lines = [f"# {claim_id}", ""]
    lines += section("Claim", claim.proposition)
    lines += section("Status", claim.status)
    lines += section("Confidence", claim.confidence)
    lines += list_section("Supporting evidence", claim.supporting)
    lines += list_section("Contradicting evidence", claim.contradicting)
    if claim.reasoning:
        lines += section("Reasoning", claim.reasoning)
    provenance = (
        f"settlement on {claim.settled_on}, {date}"
        if claim.settled_on
        else f"asserted directly, {date}"
    )
    lines += list_section(
        "Provenance", (provenance, *((claim.session_id,) if claim.session_id else ()))
    )
    return "\n".join(lines)


def record_claim(
    repository: Repository, claim: Claim, actor: Actor, *, today: str | None = None
) -> ClaimRecord:
    """Write one claim to ``claims/CLM-NNNN.md`` through the write path,
    committed and attributed to ``actor`` - the direct door (part 06 §8.9:
    "the author may still assert one outright"), and the one
    ``settle`` uses."""
    if not actor.name.strip() or not actor.email.strip():
        raise SettlementError("a claim must be attributed - actor name and email may not be empty")
    if not claim.proposition.strip():
        raise SettlementError("a claim needs a proposition")
    if claim.status not in CLAIM_STATUSES:
        raise SettlementError(
            f"{claim.status!r} is not a claim status - expected one of {', '.join(CLAIM_STATUSES)}"
        )
    if claim.confidence not in CLAIM_CONFIDENCES:
        raise SettlementError(
            f"{claim.confidence!r} is not a claim confidence - expected one of "
            f"{', '.join(CLAIM_CONFIDENCES)}"
        )
    for ref in (*claim.supporting, *claim.contradicting):
        _check_evidence(ref)
    if claim.session_id is not None:
        claim = dataclass_replace(claim, session_id=_session_provenance(claim.session_id))

    claim_id = next_claim_id(repository)
    relative_path = f"{CLAIMS_RELATIVE_PATH}/{claim_id}.md"
    content = _render_claim(claim_id, claim, today or date_type.today().isoformat())
    result = write.create(repository, relative_path, content, actor)
    if isinstance(result, Rejected):
        raise SettlementError(f"could not write {relative_path}: {result.outcome}")
    return ClaimRecord(claim_id=claim_id, path=relative_path, claim=claim)


def read_claim(repository: Repository, claim_id: str) -> str:
    """Serve one claim's file, verbatim - what ``records.read`` gives a
    ``CLM-`` reference, the same whole-file contract a research memo has."""
    path = repository.root / CLAIMS_RELATIVE_PATH / f"{claim_id}.md"
    if not path.is_file():
        raise SettlementError(f"no such claim: {claim_id}")
    return path.read_text(encoding="utf-8")
