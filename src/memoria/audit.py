"""Memoized judgements and the staleness map (#37, part 06 §8.12).

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
(``memoria.scope.resolve_scope``), the same bounding the audit itself and
drift detection will use once they exist (#40, #41). This is why #37 was
blocked on #36 rather than growing its own copy.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

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
    row = con.execute(
        "SELECT value FROM memo WHERE kind = ? AND anchor = ? ORDER BY written_at DESC LIMIT 1",
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
    entries = load_all_entries(repository)
    subject_cache: dict[str, str] = {}
    entry_hash_cache: dict[str, str] = {}
    gathered_hash_cache: dict[str, str] = {}

    con = connect(repository)
    try:
        not_current: list[NotCurrentJudgement] = []
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
                        p_hash = paragraph_hash(text)
                        anchor = f"{chapter.number:02d}/{section.number:02d}#{index}|{entry_id}"

                        engagement_cause = _staleness_cause(
                            con,
                            kind="engagement",
                            anchor=anchor,
                            current_key=engagement_key(p_hash, e_hash, s_hash),
                            p_hash=p_hash,
                            e_hash=e_hash,
                            s_hash=s_hash,
                            g_hash=None,
                        )
                        if engagement_cause is not None:
                            not_current.append(
                                NotCurrentJudgement(
                                    chapter_number=chapter.number,
                                    section_number=section.number,
                                    paragraph_index=index,
                                    entry_id=entry_id,
                                    kind="engagement",
                                    cause=engagement_cause,
                                )
                            )

                        audit_cause = _staleness_cause(
                            con,
                            kind="audit_verdict",
                            anchor=anchor,
                            current_key=audit_verdict_key(p_hash, e_hash, s_hash, g_hash),
                            p_hash=p_hash,
                            e_hash=e_hash,
                            s_hash=s_hash,
                            g_hash=g_hash,
                        )
                        if audit_cause is not None:
                            not_current.append(
                                NotCurrentJudgement(
                                    chapter_number=chapter.number,
                                    section_number=section.number,
                                    paragraph_index=index,
                                    entry_id=entry_id,
                                    kind="audit_verdict",
                                    cause=audit_cause,
                                )
                            )
        return StalenessMap(tuple(not_current))
    finally:
        con.close()
