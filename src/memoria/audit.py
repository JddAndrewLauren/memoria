"""The audit, on demand only, and its memoized judgements (#37, #40, part 06
§8.12 / §8.10 / §8.11).

Both the appearances pass and the audit evaluate the same unit: one
paragraph against one entry. This module owns the memo key each kind of
judgement is cached under, the write side that records one, and the
**staleness map** - the hash comparison that tells, for the whole manuscript
at once and without a model, which of those judgements are missing or stale,
and why.

Two kinds of judgement, one cache (part 06 §8.12's "one cache, two key
compositions" - the same table `memoria.extraction` already keeps its own
two kinds in, see ``memoria.index``'s ``memo`` table):

- an **engagement judgement** asks whether a paragraph engages an entry at
  all. Its key is ``hash(paragraph) + hash(entry audit-visible body) +
  hash(subject prompt)``.
- an **audit verdict** asks the subject's audit questions of the paragraph,
  and its answer can turn on evidence. Its key carries a fourth hash:
  ``hash(gathered-set membership, pins and exclusions applied)``.

**This module never calls a model.** Recording a judgement's *value* is a
model-free write - the model call that produced the value already happened
elsewhere, the same way ``memoria.extraction.record_paragraph_memo`` never
reads a paragraph itself - and computing the staleness map is a pure hash
comparison. ``test_audit.py`` holds both halves of that claim: an AST sweep
against a model-client import, and a run of the whole map computation with
sockets and subprocesses made to raise.

**No paragraph carries a durable identity.** Part 04 §4.1 withdrew
``chapters/02/draft.md#p7`` as something other material may point at, so a
manuscript paragraph is never addressed by anything but its own content and,
transiently, its position - unlike an evidence paragraph's ``SRC-000184-p17``
anchor, nothing here is stable across an edit. Every paragraph in this module
is therefore read fresh off ``draft.md`` on every call
(``manuscript_paragraphs``) rather than looked up by a stored id, and a
judgement's ``anchor`` column (``chapter/section#index|entry_id``) is a
diagnostic aid recomputed the same way each time - never a reference a
surface could cite or a caller outside this module could rely on surviving a
reorder.

**The audit's bounding comes from the one scope resolver** (#36): a
paragraph is judged only against the entries its section's brief resolves to
(``memoria.scope.resolve_scope``), the same bounding drift detection (#41)
also uses. This is why #37 was blocked on #36 rather than growing its own
copy.

**#40 adds the audit itself, on demand only.** Nothing in this module can
call a model (see above), so "running the audit" is a conversation the same
shape ``memoria.extraction`` already has with a session: ``mcp.server``'s
``audit_pending`` tool hands out the paragraph/entry pairs a target (a
section, a chapter, or one highlighted passage) needs judged - bounded by
``pending_for_target``, a narrowing of the same ``compute_staleness_map``
an entry-changed impact check reads, never a second computation - and
``audit_record`` takes the judgements back through ``record_audit_batch``. A
**finding** is a disagreement set plus prose (``Finding``, part 06 §8.10):
it carries no category, and everything a caller needs - which resolutions
apply, which subject raised it - is read from the set's member kinds
(``Finding.available_resolutions``), never stored as a separate label. A
brief is never a resolution target (part 06 §8.10): the only row a brief can
appear in offers "open a conversation about the brief", not a rewrite, and
this module imports no brief-writing function to make that structural.
Findings are derived, not accumulated: nothing here stores a ``Finding``
anywhere, only the same memoized audit verdict §8.12 already caches, decoded
back on every read (``findings_in_scope``). Themes and Arcs, which cannot be
matched lexically (§8.11), get their appearances the same way: read back
from the engagement judgements the audit already recorded for them
(``model_engine_appearances``) rather than a model call of its own.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Literal

from memoria.index import connect, gather
from memoria.manuscript import list_chapters, list_sections
from memoria.repository import Repository
from memoria.scope import resolve_scope
from memoria.subjects import (
    Entry,
    Subject,
    load_all_entries,
    load_subject,
    parse_statements,
    subject_to_markdown,
)

# The prose file a section carries alongside its brief (part 04 §2). Read
# here, not owned by `memoria.manuscript`: that module's docstring scopes it
# to the three briefs, and draft.md has no write path yet (#43) for it to
# guard.
DRAFT_FILENAME = "draft.md"

# Bumped when the *composition* of a judgement key changes - which hashes go
# into it, or in what order - the same discipline `extraction.MEMO_KEY_VERSION`
# keeps. Changing this moves every key, which is honest: a judgement computed
# under different rules is not this judgement.
MEMO_KEY_VERSION = "memoria-audit-v1"

StalenessCause = Literal[
    "never_audited",
    "paragraph_edited",
    "entry_changed",
    "subject_changed",
    "gathered_set_changed",
]

# In the order §8.12 and CONTEXT.md's "Not current" both state them, and the
# order `_staleness_cause` checks in when more than one input moved at once -
# an edge case with no natural priority of its own, resolved by picking the
# same order the prose already lists them in rather than inventing a second
# one.
STALENESS_CAUSES: tuple[StalenessCause, ...] = (
    "never_audited",
    "paragraph_edited",
    "entry_changed",
    "subject_changed",
    "gathered_set_changed",
)

JudgementKind = Literal["engagement", "audit_verdict"]


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- manuscript paragraphs, read fresh every call ----------------------------

_BLANK_LINE = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class ManuscriptParagraph:
    """One paragraph of one section's ``draft.md``, as read this call.

    ``paragraph_index`` is 1-based and positional within the section, not a
    stable id - see the module docstring. ``slot`` is the position half of a
    judgement's diagnostic anchor; entry-scoping (``|entry_id``) is added by
    whoever writes or reads a judgement, since one slot carries a different
    judgement per entry it is checked against.
    """

    chapter_number: int
    section_number: int
    paragraph_index: int
    text: str

    @property
    def slot(self) -> str:
        return f"{self.chapter_number:02d}/{self.section_number:02d}#{self.paragraph_index}"


def _split_paragraphs(text: str) -> list[str]:
    """Blank-line paragraph splitting - draft.md is plain prose, carrying
    none of the anchor comments a normalized evidence record's body does, so
    ``records._parse_paragraphs``'s anchor-aware split does not apply here."""
    return [p.strip() for p in _BLANK_LINE.split(text.strip()) if p.strip()]


def manuscript_paragraphs(repository: Repository) -> list[ManuscriptParagraph]:
    """Every paragraph of every section's prose, in outline order.

    Prose lives only at section scope (part 04 §2's tree has no
    ``chapters/<N>/draft.md``), so this walks ``list_chapters`` /
    ``list_sections`` rather than the filesystem directly - the same
    traversal the outline itself uses. A section with no ``draft.md`` yet
    (a planned section, CONTEXT.md's "Outline") contributes nothing rather
    than erroring: an empty draft is a valid state, not a corruption.
    """
    paragraphs: list[ManuscriptParagraph] = []
    for chapter in list_chapters(repository):
        for section in list_sections(repository, chapter.number):
            draft_path = section.dir / DRAFT_FILENAME
            if not draft_path.is_file():
                continue
            text = draft_path.read_text(encoding="utf-8")
            for index, paragraph_text in enumerate(_split_paragraphs(text), start=1):
                paragraphs.append(
                    ManuscriptParagraph(
                        chapter_number=chapter.number,
                        section_number=section.number,
                        paragraph_index=index,
                        text=paragraph_text,
                    )
                )
    return paragraphs


# --- the four input hashes (part 06 §8.12) -----------------------------------


def paragraph_hash(paragraph_text: str) -> str:
    return _h(paragraph_text)


def audit_visible_body(entry: Entry) -> str:
    """The part of an entry's body the audit compares prose against
    (CONTEXT.md's "Audit-visible body"): testimony and every badged
    statement except ``[open]``. Memoria notes are not yet a construct this
    codebase writes (part 08 §14.2 is not built), so there is nothing else
    to exclude today; when they land, they join `[open]` here rather than
    changing the judgement key's shape.
    """
    statements = [s for s in parse_statements(entry.body) if s.badge != "open"]
    return "\n\n".join(
        f"[{s.badge}] {s.text}" if s.badge else s.text for s in statements
    )


def entry_hash(entry: Entry) -> str:
    return _h(audit_visible_body(entry))


def subject_hash(subject: Subject) -> str:
    """Hashes the whole serialized prompt, the same choice
    ``extraction._subject_digest`` makes and for the same reason: match/
    hazards/audit-questions/auto-promote move together as "the subject
    prompt" rather than separately, so editing any one of them re-prices
    every judgement resting on it, matching part 06 §8.1's stated cost of
    editing a subject.
    """
    return _h(subject_to_markdown(subject))


def gathered_set_hash(repository: Repository, entry_id: str) -> str:
    """Hashes an entry's current gathered set, overlay applied
    (``memoria.index.gather`` already folds in pins/exclusions) - part 06
    §8.12's fourth hash, audit verdicts only. Sorted by anchor for a stable
    digest independent of ``gather``'s own (already sorted) return order.
    """
    sources = gather(repository, entry_id)
    return _h("\n".join(sorted(source.anchor for source in sources)))


# --- the memo key, both compositions -----------------------------------------


def engagement_key(paragraph_hash_: str, entry_hash_: str, subject_hash_: str) -> str:
    return _h(
        "\n".join([MEMO_KEY_VERSION, "engagement", paragraph_hash_, entry_hash_, subject_hash_])
    )


def audit_verdict_key(
    paragraph_hash_: str, entry_hash_: str, subject_hash_: str, gathered_set_hash_: str
) -> str:
    return _h(
        "\n".join(
            [
                MEMO_KEY_VERSION,
                "audit_verdict",
                paragraph_hash_,
                entry_hash_,
                subject_hash_,
                gathered_set_hash_,
            ]
        )
    )


# --- recording a judgement ----------------------------------------------------
#
# Writing a *value* is out of this issue's scope - the audit that produces
# one is #40, still open - but the memoization these functions give it is
# not, so both are built against whatever value the caller already has
# (a test's fixture today, the audit's finding or engagement note tomorrow).


def _write_memo(
    repository: Repository,
    *,
    key: str,
    kind: JudgementKind,
    anchor: str,
    value: dict,
) -> None:
    con = connect(repository)
    try:
        con.execute(
            "INSERT OR REPLACE INTO memo (key, kind, anchor, value, written_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, kind, anchor, json.dumps(value, sort_keys=True), _now()),
        )
        con.commit()
    finally:
        con.close()


def record_engagement(
    repository: Repository,
    paragraph: ManuscriptParagraph,
    entry_id: str,
    verdict: dict,
) -> None:
    """Cache one paragraph's engagement judgement against one entry.

    ``verdict`` is opaque to this module - whatever the pass that produced it
    wants to keep (part 06 §8.12 shows ``{engages, note}``) - stored beside
    the three input hashes the staleness map compares against, under the key
    those hashes compose.
    """
    entry = load_all_entries(repository)[entry_id]
    subject = load_subject(repository, entry_id.split("/", 1)[0])
    p_hash = paragraph_hash(paragraph.text)
    e_hash = entry_hash(entry)
    s_hash = subject_hash(subject)
    _write_memo(
        repository,
        key=engagement_key(p_hash, e_hash, s_hash),
        kind="engagement",
        anchor=f"{paragraph.slot}|{entry_id}",
        value={
            "paragraph_hash": p_hash,
            "entry_hash": e_hash,
            "subject_hash": s_hash,
            "verdict": verdict,
        },
    )


def record_audit_verdict(
    repository: Repository,
    paragraph: ManuscriptParagraph,
    entry_id: str,
    verdict: dict,
) -> None:
    """Cache one paragraph's audit verdict against one entry - see
    ``record_engagement``; carries the fourth, gathered-set hash."""
    entry = load_all_entries(repository)[entry_id]
    subject = load_subject(repository, entry_id.split("/", 1)[0])
    p_hash = paragraph_hash(paragraph.text)
    e_hash = entry_hash(entry)
    s_hash = subject_hash(subject)
    g_hash = gathered_set_hash(repository, entry_id)
    _write_memo(
        repository,
        key=audit_verdict_key(p_hash, e_hash, s_hash, g_hash),
        kind="audit_verdict",
        anchor=f"{paragraph.slot}|{entry_id}",
        value={
            "paragraph_hash": p_hash,
            "entry_hash": e_hash,
            "subject_hash": s_hash,
            "gathered_set_hash": g_hash,
            "verdict": verdict,
        },
    )


# --- the staleness map --------------------------------------------------------


@dataclass(frozen=True)
class NotCurrentJudgement:
    """One (paragraph, entry, judgement kind) that is not current, and why."""

    chapter_number: int
    section_number: int
    paragraph_index: int
    entry_id: str
    kind: JudgementKind
    cause: StalenessCause


@dataclass(frozen=True)
class StalenessMap:
    """Every not-current judgement across the whole manuscript, as of one
    call. Current judgements are not enumerated - CONTEXT.md's "Not current"
    is the exception state a map reports, not the default one a caller has
    to filter out."""

    not_current: tuple[NotCurrentJudgement, ...]

    @property
    def paragraphs_not_current(self) -> int:
        """Distinct paragraphs carrying at least one not-current judgement -
        the top-line count part 06 §8.12's summary line reports ("142
        paragraphs not current"), as opposed to the finer (paragraph, entry,
        kind) count `not_current` itself carries."""
        return len(
            {
                (item.chapter_number, item.section_number, item.paragraph_index)
                for item in self.not_current
            }
        )

    def count_by_cause(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.not_current:
            counts[item.cause] = counts.get(item.cause, 0) + 1
        return counts


def _prior_value(con: sqlite3.Connection, kind: JudgementKind, anchor: str) -> dict | None:
    """The most recently written judgement at this (kind, anchor) - used
    only to name *why* the current key misses, never to decide whether it
    does. ``written_at`` has second resolution, so two writes to the same
    anchor inside one on-demand run (an audit and its immediate re-audit,
    both well within a second) can tie on it; ``rowid`` breaks the tie,
    since a fresh row - this is always an insert of a new key, never a
    replace of the row it is compared against - gets a strictly higher one
    than anything written before it, tie or not."""
    row = con.execute(
        "SELECT value FROM memo WHERE kind = ? AND anchor = ? "
        "ORDER BY written_at DESC, rowid DESC LIMIT 1",
        (kind, anchor),
    ).fetchone()
    return json.loads(row[0]) if row is not None else None


def _staleness_cause(
    con: sqlite3.Connection,
    *,
    kind: JudgementKind,
    anchor: str,
    current_key: str,
    p_hash: str,
    e_hash: str,
    s_hash: str,
    g_hash: str | None,
) -> StalenessCause | None:
    """``None`` if the judgement is current; otherwise which of §8.12's four
    causes it is - by finding the most recent judgement previously recorded
    at this paragraph's position for this entry (if any) and comparing each
    of its stored input hashes against the current one, in the order
    ``STALENESS_CAUSES`` lists them.
    """
    hit = con.execute(
        "SELECT 1 FROM memo WHERE key = ? AND kind = ?", (current_key, kind)
    ).fetchone()
    if hit is not None:
        return None

    prior = _prior_value(con, kind, anchor)
    if prior is None:
        return "never_audited"
    if prior.get("paragraph_hash") != p_hash:
        return "paragraph_edited"
    if prior.get("entry_hash") != e_hash:
        return "entry_changed"
    if prior.get("subject_hash") != s_hash:
        return "subject_changed"
    if kind == "audit_verdict" and prior.get("gathered_set_hash") != g_hash:
        return "gathered_set_changed"
    # Every tracked input still matches and the key still missed - only
    # reachable by bumping MEMO_KEY_VERSION itself, not by any input moving.
    # Nothing recorded under the new composition survives to compare against,
    # so this reads the same as a paragraph that was never audited.
    return "never_audited"


@dataclass(frozen=True)
class ScopedParagraph:
    """One (paragraph, entry) pair the audit is bounded to check - one row
    of the traversal every audit-bounded computation walks (#40's fifth
    acceptance criterion: impact analysis is not a second mechanism, so
    there is exactly one place that decides what the audit's bounding is).
    Carries the paragraph's position and text, the entry it is checked
    against, and the three or four input hashes precomputed once per entry
    rather than once per paragraph.
    """

    chapter_number: int
    section_number: int
    paragraph_index: int
    text: str
    entry_id: str
    p_hash: str
    e_hash: str
    s_hash: str
    g_hash: str

    @property
    def anchor(self) -> str:
        return (
            f"{self.chapter_number:02d}/{self.section_number:02d}"
            f"#{self.paragraph_index}|{self.entry_id}"
        )


def _iter_scoped_paragraphs(repository: Repository) -> Iterator[ScopedParagraph]:
    """Every (paragraph, entry) pair the audit is bounded to check, in
    outline order - every section's ``draft.md`` paragraphs against the
    entries its brief resolves to (``resolve_scope``, #36). Both
    ``compute_staleness_map`` and finding derivation walk this one
    traversal rather than each growing its own copy - the audit and impact
    analysis are the same mechanism (part 06 §8.12), and this is why.

    A section with no ``draft.md``, an empty draft, or a brief that resolves
    to no entries contributes nothing, matching ``compute_staleness_map``'s
    prior behaviour.
    """
    entries = load_all_entries(repository)
    subject_cache: dict[str, str] = {}
    entry_hash_cache: dict[str, str] = {}
    gathered_hash_cache: dict[str, str] = {}

    for chapter in list_chapters(repository):
        for section in list_sections(repository, chapter.number):
            draft_path = section.dir / DRAFT_FILENAME
            if not draft_path.is_file():
                continue
            paragraphs = _split_paragraphs(draft_path.read_text(encoding="utf-8"))
            if not paragraphs:
                continue
            scope = resolve_scope(repository, section.brief)
            for entry_id in scope.entry_ids:
                entry = entries.get(entry_id)
                if entry is None:
                    continue
                subject_id = entry_id.split("/", 1)[0]
                if entry_id not in entry_hash_cache:
                    if subject_id not in subject_cache:
                        subject_cache[subject_id] = subject_hash(
                            load_subject(repository, subject_id)
                        )
                    entry_hash_cache[entry_id] = entry_hash(entry)
                    gathered_hash_cache[entry_id] = gathered_set_hash(
                        repository, entry_id
                    )
                e_hash = entry_hash_cache[entry_id]
                s_hash = subject_cache[subject_id]
                g_hash = gathered_hash_cache[entry_id]

                for index, text in enumerate(paragraphs, start=1):
                    yield ScopedParagraph(
                        chapter_number=chapter.number,
                        section_number=section.number,
                        paragraph_index=index,
                        text=text,
                        entry_id=entry_id,
                        p_hash=paragraph_hash(text),
                        e_hash=e_hash,
                        s_hash=s_hash,
                        g_hash=g_hash,
                    )


def compute_staleness_map(repository: Repository) -> StalenessMap:
    """The staleness map for the whole manuscript, at this call, as a hash
    comparison - no model, no cache of its own (it is recomputed in full
    every time, which is what "known across the whole manuscript at all
    times" (CONTEXT.md) means in practice: nothing here can go stale itself).

    A paragraph is checked only against the entries its section's brief
    resolves to (``resolve_scope``, #36) - the audit's bounding - so a
    section with an empty or unconfirmed-but-empty scope contributes no
    judgements, and neither does a section with no ``draft.md`` yet.
    """
    con = connect(repository)
    try:
        not_current: list[NotCurrentJudgement] = []
        for item in _iter_scoped_paragraphs(repository):
            engagement_cause = _staleness_cause(
                con,
                kind="engagement",
                anchor=item.anchor,
                current_key=engagement_key(item.p_hash, item.e_hash, item.s_hash),
                p_hash=item.p_hash,
                e_hash=item.e_hash,
                s_hash=item.s_hash,
                g_hash=None,
            )
            if engagement_cause is not None:
                not_current.append(
                    NotCurrentJudgement(
                        chapter_number=item.chapter_number,
                        section_number=item.section_number,
                        paragraph_index=item.paragraph_index,
                        entry_id=item.entry_id,
                        kind="engagement",
                        cause=engagement_cause,
                    )
                )

            audit_cause = _staleness_cause(
                con,
                kind="audit_verdict",
                anchor=item.anchor,
                current_key=audit_verdict_key(
                    item.p_hash, item.e_hash, item.s_hash, item.g_hash
                ),
                p_hash=item.p_hash,
                e_hash=item.e_hash,
                s_hash=item.s_hash,
                g_hash=item.g_hash,
            )
            if audit_cause is not None:
                not_current.append(
                    NotCurrentJudgement(
                        chapter_number=item.chapter_number,
                        section_number=item.section_number,
                        paragraph_index=item.paragraph_index,
                        entry_id=item.entry_id,
                        kind="audit_verdict",
                        cause=audit_cause,
                    )
                )
        return StalenessMap(tuple(not_current))
    finally:
        con.close()


# --- an on-demand audit target (#40, CONTEXT.md's "Audit") -------------------
#
# "A button on a section or a chapter, or on a highlighted passage." A target
# is never resolved automatically - every function below is reached only by
# something naming one explicitly, and nothing in this module or elsewhere in
# the codebase calls into this section on its own (test_audit.py's AST sweep
# checks that claim the same way it checks the no-model-client one above).


def pending_for_target(
    repository: Repository,
    *,
    chapter_number: int | None = None,
    section_number: int | None = None,
    paragraph_index: int | None = None,
) -> tuple[NotCurrentJudgement, ...]:
    """The not-current judgements bounded to one on-demand audit target.

    Reads the same ``compute_staleness_map`` an entry-changed impact check
    would read - this only narrows which of its rows the caller asked to
    see, never a second computation (#40's fifth acceptance criterion: the
    audit and impact analysis are one mechanism). Omitting every keyword
    scopes to the whole manuscript - a chapter-level "audit everything"
    button reads the same way a highlighted passage does, through the same
    function.
    """
    if section_number is not None and chapter_number is None:
        raise ValueError("section_number requires chapter_number")
    if paragraph_index is not None and section_number is None:
        raise ValueError("paragraph_index requires section_number")
    items = compute_staleness_map(repository).not_current
    if chapter_number is not None:
        items = tuple(i for i in items if i.chapter_number == chapter_number)
    if section_number is not None:
        items = tuple(i for i in items if i.section_number == section_number)
    if paragraph_index is not None:
        items = tuple(i for i in items if i.paragraph_index == paragraph_index)
    return items


def paragraph_at(
    repository: Repository, chapter_number: int, section_number: int, paragraph_index: int
) -> ManuscriptParagraph | None:
    """The one paragraph a (chapter, section, index) triple names, read
    fresh off ``draft.md`` like every other paragraph this module handles -
    ``None`` if the position no longer exists (the draft shrank since a
    judgement was served)."""
    for paragraph in manuscript_paragraphs(repository):
        if (
            paragraph.chapter_number,
            paragraph.section_number,
            paragraph.paragraph_index,
        ) == (chapter_number, section_number, paragraph_index):
            return paragraph
    return None


# --- findings: disagreement sets, no category (part 06 §8.10, §18) -----------

Confidence = Literal["low", "moderate", "high"]

# A member's kind names what part of a disagreement it is, never a category
# of problem (§8.10: "finding types are never enumerated; the set is read").
# "brief" is deliberately never a resolution target on its own - see
# `_RESOLUTIONS_BY_SHAPE`.
DisagreementMemberKind = Literal["passage", "entry", "source", "decision", "brief"]


@dataclass(frozen=True)
class DisagreementMember:
    """One member of a finding's disagreement set - what disagrees, and a
    reference to it. ``ref`` is a paragraph's ``slot`` for ``"passage"``, an
    ``entry_id`` for ``"entry"``, a normalized-record anchor for
    ``"source"``, a ``DEC-####`` id for ``"decision"``, or a section/chapter
    id for ``"brief"`` - whatever the member kind's own reference form is;
    this module does not itself validate the shape of ``ref``, the same way
    ``record_engagement``'s ``verdict`` is opaque to the memo layer."""

    kind: DisagreementMemberKind
    ref: str


# The resolutions part 09 §18's table gives, keyed by the *shape* of a
# disagreement set - the sorted set of member kinds it carries - never by an
# enumerated finding type. A set shaped any other way has no declared
# resolution and is refused loudly (`UnresolvableDisagreementShape`) rather
# than silently offered none.
#
# The "passage" + "brief" row is deliberately not symmetrical with the rest:
# every other row offers a rewrite alongside updating the other member,
# where this one offers only a conversation. Rewriting a passage is bounded
# and reviewable in a diff; rewriting a brief silently changes what every
# future audit checks (part 06 §8.10) - so no combination here ever resolves
# by writing one, which is #40's eighth acceptance criterion made structural
# rather than a rule a caller has to remember.
_RESOLUTIONS_BY_SHAPE: dict[frozenset[DisagreementMemberKind], tuple[str, ...]] = {
    frozenset({"passage", "source"}): ("rewrite the passage", "exclude the source"),
    frozenset({"passage", "entry", "source"}): (
        "settle toward the entry",
        "settle toward the source",
        "settle toward the passage",
    ),
    frozenset({"passage", "entry"}): ("rewrite the passage", "update the entry"),
    frozenset({"passage", "decision"}): ("rewrite the passage", "revise the decision"),
    frozenset({"passage", "brief"}): (
        "rewrite the passage",
        "open a conversation about the brief",
    ),
}


class UnresolvableDisagreementShape(Exception):
    """A disagreement set whose member kinds match no row part 09 §18 gives
    resolutions for."""


@dataclass(frozen=True)
class Finding:
    """A disagreement set plus prose saying how they disagree (part 06
    §8.10) - a finding carries no category. Everything else a surface needs
    is read from the set: ``available_resolutions`` below, and ``subject_id``
    for which subject raised it (already known, since the audit is
    subject-bounded). Ordering across findings is by ``confidence``, per
    §21's tiers, not by anything this class computes.

    ``patch`` is an optional proposed rewrite (part 09 §17: "Memoria may
    prepare a proposed rewrite. It may not apply that rewrite ... without
    authorization") - text only, never applied by anything in this module.
    """

    disagreement_set: tuple[DisagreementMember, ...]
    statement: str
    confidence: Confidence
    subject_id: str
    patch: str | None = None

    @property
    def available_resolutions(self) -> tuple[str, ...]:
        shape = frozenset(member.kind for member in self.disagreement_set)
        try:
            return _RESOLUTIONS_BY_SHAPE[shape]
        except KeyError:
            raise UnresolvableDisagreementShape(
                f"no resolutions declared for a disagreement set shaped {sorted(shape)}"
            ) from None


def _member_to_dict(member: DisagreementMember) -> dict:
    return {"kind": member.kind, "ref": member.ref}


def _member_from_dict(raw: dict) -> DisagreementMember:
    return DisagreementMember(kind=raw["kind"], ref=raw["ref"])


def clear_verdict() -> dict:
    """The audit verdict value for a paragraph the audit found nothing to
    disagree with (part 06 §8.12's key-value shape: "clear, or a
    finding")."""
    return {"clear": True}


def finding_verdict(finding: Finding) -> dict:
    """The audit verdict value for a paragraph the audit raised a finding
    against. Raises ``UnresolvableDisagreementShape`` rather than caching a
    finding no surface could ever offer a resolution for."""
    _ = finding.available_resolutions
    return {
        "clear": False,
        "finding": {
            "disagreement_set": [_member_to_dict(m) for m in finding.disagreement_set],
            "statement": finding.statement,
            "confidence": finding.confidence,
            "subject_id": finding.subject_id,
            "patch": finding.patch,
        },
    }


def finding_from_verdict(verdict: dict) -> Finding | None:
    """The inverse of ``clear_verdict``/``finding_verdict``: ``None`` for a
    clear verdict, the ``Finding`` it carries otherwise."""
    if verdict.get("clear", False):
        return None
    raw = verdict["finding"]
    return Finding(
        disagreement_set=tuple(_member_from_dict(m) for m in raw["disagreement_set"]),
        statement=raw["statement"],
        confidence=raw["confidence"],
        subject_id=raw["subject_id"],
        patch=raw.get("patch"),
    )


def findings_in_scope(
    repository: Repository,
    *,
    chapter_number: int | None = None,
    section_number: int | None = None,
    paragraph_index: int | None = None,
) -> tuple[Finding, ...]:
    """Every current finding within one on-demand audit target.

    A plain read over whatever ``record_audit_verdict`` last cached under
    each in-scope (paragraph, entry) pair's *current* key - a stale
    judgement contributes nothing until the audit is re-run over it, which
    is what makes findings derived rather than accumulated (part 09 §18):
    nothing named "finding" is stored anywhere, only the same memoized audit
    verdict §8.12 already keeps, decoded back on every call. Changing an
    entry and re-running the audit therefore updates what this returns
    exactly the way editing prose does - the same mechanism, read from
    either end (#40's fifth acceptance criterion).
    """
    con = connect(repository)
    try:
        findings: list[Finding] = []
        for item in _iter_scoped_paragraphs(repository):
            if chapter_number is not None and item.chapter_number != chapter_number:
                continue
            if section_number is not None and item.section_number != section_number:
                continue
            if paragraph_index is not None and item.paragraph_index != paragraph_index:
                continue
            key = audit_verdict_key(item.p_hash, item.e_hash, item.s_hash, item.g_hash)
            row = con.execute(
                "SELECT value FROM memo WHERE key = ? AND kind = 'audit_verdict'",
                (key,),
            ).fetchone()
            if row is None:
                continue
            value = json.loads(row[0])
            finding = finding_from_verdict(value["verdict"])
            if finding is not None:
                findings.append(finding)
        return tuple(findings)
    finally:
        con.close()


# --- serving and recording an audit run (#40, driven by an MCP session) ------
#
# The same conversation shape ``memoria.extraction`` already has with a
# session (module docstring, and ``mcp.server``'s own): this module hands
# out what needs judging and takes structured judgements back. It never
# calls a model itself - `test_audit.py`'s AST sweep covers this file
# whole, additions included.

# Policy text every served audit-verdict task carries verbatim (part 06
# §8.6): the audit must never report author testimony as wrong, only
# surface the disagreement.
AUTHOR_TESTIMONY_POLICY = (
    "Author testimony (unbadged statements in the entry) outranks "
    "documentary evidence. If they conflict, report a disagreement - never "
    "an error, and never a finding that says the author is wrong."
)


@dataclass(frozen=True)
class AuditTask:
    """One pending (paragraph, entry) judgement, packaged to hand to a
    session the way ``extraction.PendingParagraph`` is - text served
    verbatim, nothing summarized."""

    anchor: str
    kind: JudgementKind
    cause: StalenessCause
    paragraph_text: str
    entry_id: str
    entry_audit_visible_body: str
    subject_prompt: str
    gathered_anchors: tuple[str, ...] = ()


def audit_tasks_for_target(
    repository: Repository,
    *,
    chapter_number: int | None = None,
    section_number: int | None = None,
    paragraph_index: int | None = None,
    limit: int = 20,
) -> tuple[AuditTask, ...]:
    """The next ``limit`` pending judgements for one on-demand target,
    packaged for a session to answer. ``subject_prompt`` is the subject's
    match and hazards declarations for an ``"engagement"`` task (is this
    entry engaged at all) or its audit questions for an ``"audit_verdict"``
    one (what does the subject want asked); ``gathered_anchors`` names the
    entry's current gathered set for an audit-verdict task, evidence to
    ``read(ref)`` before answering - never the source text itself, which
    this module does not hold.
    """
    entries = load_all_entries(repository)
    tasks: list[AuditTask] = []
    pending = pending_for_target(
        repository,
        chapter_number=chapter_number,
        section_number=section_number,
        paragraph_index=paragraph_index,
    )
    # ``limit`` bounds the tasks served, not the pending rows walked: a row
    # whose paragraph or entry has gone since the map was computed is dropped
    # here, and dropping it must not silently under-fill the batch a caller
    # asked for.
    for item in pending:
        if len(tasks) >= limit:
            break
        paragraph = paragraph_at(
            repository, item.chapter_number, item.section_number, item.paragraph_index
        )
        entry = entries.get(item.entry_id)
        if paragraph is None or entry is None:
            continue
        subject = load_subject(repository, item.entry_id.split("/", 1)[0])
        if item.kind == "engagement":
            prompt = f"Match: {subject.match}\n\nHazards: {subject.hazards}"
            gathered: tuple[str, ...] = ()
        else:
            prompt = subject.audit_questions
            gathered = tuple(source.anchor for source in gather(repository, item.entry_id))
        tasks.append(
            AuditTask(
                anchor=f"{item.chapter_number:02d}/{item.section_number:02d}"
                f"#{item.paragraph_index}|{item.entry_id}",
                kind=item.kind,
                cause=item.cause,
                paragraph_text=paragraph.text,
                entry_id=item.entry_id,
                entry_audit_visible_body=audit_visible_body(entry),
                subject_prompt=prompt,
                gathered_anchors=gathered,
            )
        )
    return tuple(tasks)


_TASK_ANCHOR = re.compile(
    r"^(?P<chapter>\d+)/(?P<section>\d+)#(?P<index>\d+)\|(?P<entry_id>SUB-[a-z0-9-]+/[a-z0-9-]+)$"
)


@dataclass
class RecordedDisagreementMember:
    """One disagreement-set member, as a session sends it back."""

    kind: str
    ref: str


@dataclass
class RecordedFinding:
    """A finding, as a session sends it back."""

    disagreement_set: list[RecordedDisagreementMember] = field(default_factory=list)
    statement: str = ""
    confidence: str = "moderate"
    patch: str | None = None


@dataclass
class RecordedAuditItem:
    """One judgement's answer, as one element of a recorded batch - the
    inverse of one ``AuditTask``. ``engages``/``note`` answer an
    ``"engagement"`` task; ``clear``/``finding`` answer an
    ``"audit_verdict"`` one."""

    anchor: str
    kind: str
    engages: bool | None = None
    note: str = ""
    clear: bool | None = None
    finding: RecordedFinding | None = None


@dataclass(frozen=True)
class AuditRecordOutcome:
    """Per-element outcome of one ``record_audit_batch`` call, the same
    accept-what-you-can shape ``extraction.RecordOutcome`` uses."""

    accepted: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]


def record_audit_batch(
    repository: Repository, items: list[RecordedAuditItem]
) -> AuditRecordOutcome:
    """Record one batch of audit judgements, each accepted or rejected on
    its own. Never calls a model - every value here already arrived as an
    argument."""
    entries = load_all_entries(repository)
    accepted: list[str] = []
    rejected: list[tuple[str, str]] = []
    for item in items:
        match = _TASK_ANCHOR.match(item.anchor)
        if match is None:
            rejected.append((item.anchor, "malformed anchor"))
            continue
        chapter_number = int(match.group("chapter"))
        section_number = int(match.group("section"))
        paragraph_index = int(match.group("index"))
        entry_id = match.group("entry_id")
        if entry_id not in entries:
            rejected.append((item.anchor, f"no such entry {entry_id!r}"))
            continue
        paragraph = paragraph_at(repository, chapter_number, section_number, paragraph_index)
        if paragraph is None:
            rejected.append((item.anchor, "no such paragraph"))
            continue

        if item.kind == "engagement":
            if item.engages is None:
                rejected.append((item.anchor, "engagement result missing 'engages'"))
                continue
            record_engagement(
                repository, paragraph, entry_id, {"engages": item.engages, "note": item.note}
            )
        elif item.kind == "audit_verdict":
            if item.clear:
                record_audit_verdict(repository, paragraph, entry_id, clear_verdict())
            elif item.finding is not None:
                try:
                    finding = Finding(
                        disagreement_set=tuple(
                            DisagreementMember(kind=m.kind, ref=m.ref)
                            for m in item.finding.disagreement_set
                        ),
                        statement=item.finding.statement,
                        confidence=item.finding.confidence,
                        subject_id=entry_id.split("/", 1)[0],
                        patch=item.finding.patch,
                    )
                    verdict = finding_verdict(finding)
                except UnresolvableDisagreementShape as exc:
                    rejected.append((item.anchor, str(exc)))
                    continue
                record_audit_verdict(repository, paragraph, entry_id, verdict)
            else:
                rejected.append(
                    (item.anchor, "audit_verdict result needs 'clear' or 'finding'")
                )
                continue
        else:
            rejected.append((item.anchor, f"unknown kind {item.kind!r}"))
            continue
        accepted.append(item.anchor)
    return AuditRecordOutcome(accepted=tuple(accepted), rejected=tuple(rejected))


# --- the model engine for Themes and Arcs (#40, part 06 §8.11) ---------------


@dataclass(frozen=True)
class ModelAppearance:
    """One appearance the model engine found for a Themes/Arcs entry - the
    counterpart to ``index.Appearance`` for the two subjects lexical
    matching cannot reach (§8.11: "a paragraph about the fear of dependence
    need not contain any of the entry's words")."""

    entry_id: str
    slot: str
    note: str


def model_engine_appearances(
    repository: Repository, entry_id: str | None = None
) -> tuple[ModelAppearance, ...]:
    """Themes/Arcs appearances, read back from the engagement judgements the
    audit already cached rather than a model call of its own - "memoized
    like everything else" (#40). An entry under
    ``extraction.CO_OCCURRENCE_SUBJECTS`` appears here once some section
    naming it has been audited and the paragraph was judged to engage it;
    until then it has none, the same honestly-empty state
    ``index.compute_appearances`` reports for these two subjects today.
    Optionally narrowed to one entry, matching ``index.list_appearances``.
    """
    from memoria.extraction import CO_OCCURRENCE_SUBJECTS

    con = connect(repository)
    try:
        found: list[ModelAppearance] = []
        for item in _iter_scoped_paragraphs(repository):
            if item.entry_id.split("/", 1)[0] not in CO_OCCURRENCE_SUBJECTS:
                continue
            if entry_id is not None and item.entry_id != entry_id:
                continue
            key = engagement_key(item.p_hash, item.e_hash, item.s_hash)
            row = con.execute(
                "SELECT value FROM memo WHERE key = ? AND kind = 'engagement'", (key,)
            ).fetchone()
            if row is None:
                continue
            verdict = json.loads(row[0]).get("verdict", {})
            if not verdict.get("engages"):
                continue
            slot = f"{item.chapter_number:02d}/{item.section_number:02d}#{item.paragraph_index}"
            found.append(
                ModelAppearance(
                    entry_id=item.entry_id, slot=slot, note=verdict.get("note", "")
                )
            )
        return tuple(found)
    finally:
        con.close()
