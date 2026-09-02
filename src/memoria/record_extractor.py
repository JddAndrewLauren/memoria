"""The record extractor: the Curator's second half (part 08 §12, #30).

Where ``memoria.extraction`` is the **index maintainer** - the subject
system's candidate engine, writing only rebuildable derived state that
asserts nothing (ADR-0005) - this module is the half part 08 §12 names
separately because it carries a different risk profile: it writes **durable
records** - post-session decisions, questions and research memos - and it is
the only half the curation restraint rules bind. Writing badged statements
into entry bodies is a further piece of the same half, built to its own
issue (#31) against the write matrix (part 06 §8.2); this module's scope is
the three record kinds part 08 §13 names on their own: decisions, questions,
research memos.

**One rule does the work** (part 08 §13.1, §13.4, part 06 §9.2): an
``[author]`` statement needs a citing transcript turn that is identifiably
the author's, never the assistant's own suggestion mistaken for one -
"There must be identifiable author evidence." That is a fact about the
transcript (``sessions.turn_role``), not a judgement about the prose, so it
is checked mechanically, here, without a model call - the same discipline
``memoria.extraction``'s own docstring states for its half: classifying a
turn as a decision, a question or a research finding is a driving session's
model judgement, made through Claude Code and hand-checked against a turn
number; recording what it decided, safely, is this module's job.

A decision is the sharpest case (part 08 §13.1): "the author actually
decides something" is definitionally an author act, so ``record_decision``
requires an author-spoken citing turn and refuses otherwise - a musing that
does not clear that bar is never written as a decision at all, exactly as
§13.1 says it "does not qualify". What "everything else... is ``[open]``"
(part 08 §13, this issue) means for this module's scope is
``record_question``: the durable landing place for a musing, an interim
interpretation, or an actual question - none of them assertions, all of
them ``[open]`` - which is why ``questions.md`` is described as a queue
(part 12 §34.4) rather than a ledger of settled fact.

**The limit of the mechanical check**: ``turn_role`` establishes *who
spoke* the citing turn, not *what it says*. An author-spoken musing ("Maybe
we could keep it ambiguous") routed to ``record_decision`` cannot be refused
here - the turn is identifiably the author's, and whether its words decide
something or only wonder is the model judgement above. Choosing
``record_question`` for it is the driving session's call, made before
either function is reached; this module guarantees only that nothing the
assistant said is ever badged ``[author]``.

**The dirty-tree guard is pass-level, not per-write** (part 08 §14.2):
"the Curator never writes into a file with uncommitted human modifications
... the pass waits." ``memoria.write``'s general write path absorbs a dirty
tree instead, via an automatic checkpoint (ADR-0008) - right for an
ordinary machine write, because the checkpoint commits the author's
in-progress edit as theirs before anything else touches the file. The
record extractor is held to the stricter, older rule instead: it refuses to
run at all against any uncommitted human modification, anywhere in the
repository, rather than checkpointing one out of the way and proceeding.
``ensure_clean_tree`` is that refusal, and every public write in this
module calls it first.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime

from memoria import references, sessions, write
from memoria.repository import Repository
from memoria.write import Actor, Rejected

DECISIONS_FILENAME = "decisions.md"
QUESTIONS_FILENAME = "questions.md"
RESEARCH_MEMOS_RELATIVE_PATH = "research/memos"

# Who a record-extractor commit is attributed to - the same Curator identity
# `memoria.extraction.CURATOR` uses, kept as its own value rather than an
# import so the two Curator halves stay free to run without each other (part
# 08 §12: "one agent, one pass" is vocabulary, not a code dependency).
CURATOR = Actor(name="Memoria", email="curator@memoria.local", human=False)

# §34.1's own enumeration of valid research-memo conclusions - "insufficient
# evidence" is a successful research result, not a missing one, so it is
# checked here rather than left to convention.
VALID_CONFIDENCE = (
    "supported",
    "probably supported",
    "mixed",
    "probably false",
    "contradicted",
    "insufficient evidence",
    "unknowable from current archive",
)

_DECISION_ID = re.compile(r"^DEC-(\d{4})$")
_DECISION_ENTRY = re.compile(r'<a id="(?P<anchor>dec-\d{4})"></a>\n\n## (?P<id>DEC-\d{4})')
_RESEARCH_MEMO_ID = re.compile(r"^RES-(\d{8})-(\d{3})$")


class RecordExtractorError(Exception):
    """Raised when the record extractor refuses to run, or to record
    something - a bad citation, a decision with no author evidence, or a
    write the underlying write path itself rejected."""


@dataclass(frozen=True)
class DecisionRecord:
    """A decision as written to ``decisions.md``."""

    id: str
    citation: str
    text: str


@dataclass(frozen=True)
class QuestionRecord:
    """A question, or an open musing, as written to ``questions.md``."""

    citation: str
    text: str


@dataclass(frozen=True)
class ResearchMemo:
    """§35's durable research memo, before it is minted an id and written.

    Every field but ``question``, ``interpretation`` and ``confidence`` is
    optional: a memo may close as "insufficient evidence" with nothing yet
    in ``supporting_evidence``, and that is itself a successful result
    (§34.1), not a partially-filled-in one.
    """

    question: str
    interpretation: str
    confidence: str
    research_plan: str = ""
    scope: str = ""
    searches_performed: tuple[str, ...] = ()
    sources_inspected: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchMemoRecord:
    """A research memo as written to ``research/memos/``."""

    id: str
    citation: str
    path: str


def ensure_clean_tree(repository: Repository) -> None:
    """Refuse rather than run against a repository with uncommitted human
    modifications (part 08 §14.2, #30's own acceptance criterion).

    Unscoped, deliberately: not just ``decisions.md``/``questions.md``/
    ``research/**``, but the whole repository, since a dirty file anywhere
    means the author is mid-thought (§14.2's own words) whether or not this
    pass is about to touch it. ``??`` (untracked) files do not count - the
    dirty-tree rule is about work in progress on files git already tracks
    (``write.dirty_tracked_paths``'s own convention).
    """
    dirty = write.dirty_tracked_paths(repository)
    if dirty:
        raise RecordExtractorError(
            "the record extractor will not run against a repository with "
            f"uncommitted human modifications ({', '.join(dirty)}) - commit "
            "or `memoria checkpoint` first (part 08 §14.2)"
        )


def _cite_turn(repository: Repository, session_id: str, turn: int) -> tuple[str, str]:
    """Validate that ``session_id#T<turn>`` is a real, resolvable turn, and
    return its role alongside the canonical citation string.

    The one place this module touches the transcript: everything downstream
    of this call works from the role and the citation, never from re-parsing
    ``transcript.md`` itself.
    """
    try:
        role = sessions.turn_role(repository, session_id, turn)
    except sessions.SessionError as exc:
        raise RecordExtractorError(str(exc)) from exc
    citation = references.format_citation(references.SessionReference(session_id, turn))
    return role, citation


def _escape(text: str) -> str:
    """``&`` then ``<`` as entities - ``sessions._escape_turn_text``'s exact
    pair, so free text can never open a ``<a id="...">`` and forge a second
    entry boundary in ``decisions.md``."""
    return text.replace("&", "&amp;").replace("<", "&lt;")


def _append(repository: Repository, relative_path: str, block: str, actor: Actor) -> None:
    """Append ``block`` to ``relative_path``, creating it if this is its
    first entry - both directions going through ``memoria.write`` so every
    entry lands committed and attributed, never a bare filesystem write."""
    full_path = repository.root / relative_path
    if full_path.is_file():
        served = write.serve(repository, relative_path)
        result = write.write(repository, relative_path, served.token, served.text + block, actor)
    else:
        result = write.create(repository, relative_path, block, actor)
    if isinstance(result, Rejected):
        raise RecordExtractorError(
            f"could not write {relative_path}: {result.outcome} - re-run the pass"
        )


# --- decisions ----------------------------------------------------------------


def next_decision_id(repository: Repository) -> str:
    """Mint the next ``DEC-NNNN`` id: one more than the highest id already
    in ``decisions.md`` (the same "one more than the highest on disk" scheme
    ``memoria.manuscript`` mints ``CHP-``/``SEC-`` ids with, and the same
    admitted gap - a deleted highest decision lets its id be re-minted, since
    neither ADR-0006's manifest nor a separate allocation file owns this
    number)."""
    path = repository.root / DECISIONS_FILENAME
    highest = 0
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        for match in _DECISION_ENTRY.finditer(text):
            highest = max(highest, int(_DECISION_ID.match(match.group("id")).group(1)))
    return f"DEC-{highest + 1:04d}"


def record_decision(
    repository: Repository,
    session_id: str,
    turn: int,
    text: str,
    actor: Actor | None = None,
) -> DecisionRecord:
    """Record a decision - part 08 §13.1's bar, enforced: the citing turn
    must be the author's own, or this refuses rather than write anything.

    "Maybe we could keep it ambiguous" does not qualify (§13.1's own
    example) because an assistant-spoken turn is not identifiable author
    evidence (part 06 §9.2) - and neither does an author turn cited by
    mistake for the wrong one. There is no ``[open]`` decision: a candidate
    that does not clear this bar is not a decision, and belongs in
    ``record_question`` instead.
    """
    actor = actor or CURATOR
    ensure_clean_tree(repository)
    role, citation = _cite_turn(repository, session_id, turn)
    if role != "Author":
        raise RecordExtractorError(
            f"{citation} is the {role}'s turn, not the author's - a decision "
            "needs identifiable author evidence (part 06 §9.2); record this "
            "as an open item with record_question instead"
        )
    decision_id = next_decision_id(repository)
    block = (
        f'<a id="{decision_id.lower()}"></a>\n\n'
        f"## {decision_id}\n\n"
        f"[author] {_escape(text)}\n\n"
        f"— {citation}\n\n"
    )
    _append(repository, DECISIONS_FILENAME, block, actor)
    return DecisionRecord(id=decision_id, citation=citation, text=text)


def read_decision(repository: Repository, decision_id: str) -> str:
    """Serve one decision's entry, verbatim - what ``records.read`` gives a
    ``DEC-`` reference, the same "one turn out of a transcript" shape
    ``sessions.read_session`` already gives a ``SES-...#T`` reference."""
    path = repository.root / DECISIONS_FILENAME
    if not path.is_file():
        raise RecordExtractorError(f"no such decision: {decision_id}")
    text = path.read_text(encoding="utf-8")
    entries = list(_DECISION_ENTRY.finditer(text))
    for position, match in enumerate(entries):
        if match.group("id") != decision_id:
            continue
        start = match.end()
        stop = entries[position + 1].start() if position + 1 < len(entries) else len(text)
        return html.unescape(text[start:stop].strip("\n"))
    raise RecordExtractorError(f"no such decision: {decision_id}")


# --- questions (the queue) -----------------------------------------------------


def record_question(
    repository: Repository,
    session_id: str,
    turn: int,
    text: str,
    actor: Actor | None = None,
) -> QuestionRecord:
    """Record a question, or a musing that did not clear ``record_decision``'s
    author-evidence bar, into the queue (part 12 §34.4).

    Always ``[open]`` (part 08 §13, part 06 §9.4): nothing here is an
    assertion, whichever role's turn it cites - a question is never
    doctrine, and an interim interpretation stays exploratory until an
    author turn earns it ``[author]`` through ``record_decision``.
    """
    actor = actor or CURATOR
    ensure_clean_tree(repository)
    _, citation = _cite_turn(repository, session_id, turn)
    block = f"[open] {_escape(text)}\n\n— {citation}\n\n"
    _append(repository, QUESTIONS_FILENAME, block, actor)
    return QuestionRecord(citation=citation, text=text)


# --- research memos -------------------------------------------------------------


def next_research_memo_id(repository: Repository, *, today: str | None = None) -> str:
    """Mint the next ``RES-YYYYMMDD-NNN`` id: a per-day sequence counted
    from today's memo files already on disk - ``memoria.changes``'s
    ``next_change_id`` scheme, off the filesystem rather than git history,
    since a research memo is not a commit."""
    today = today or datetime.now().strftime("%Y%m%d")
    directory = repository.root / RESEARCH_MEMOS_RELATIVE_PATH
    count = 0
    if directory.is_dir():
        for path in directory.iterdir():
            match = _RESEARCH_MEMO_ID.match(path.stem)
            if match and match.group(1) == today:
                count += 1
    return f"RES-{today}-{count + 1:03d}"


def _render_research_memo(memo_id: str, memo: ResearchMemo, citation: str) -> str:
    def section(title: str, value: str) -> list[str]:
        return [f"## {title}", "", value, ""] if value else []

    def list_section(title: str, values: tuple[str, ...]) -> list[str]:
        if not values:
            return []
        return [f"## {title}", "", *(f"- {v}" for v in values), ""]

    lines = [f"# {memo_id}", "", "## Question", "", memo.question, ""]
    lines += section("Interpretation", memo.interpretation)
    lines += section("Confidence", memo.confidence)
    lines += section("Research plan", memo.research_plan)
    lines += section("Scope", memo.scope)
    lines += list_section("Searches performed", memo.searches_performed)
    lines += list_section("Sources inspected", memo.sources_inspected)
    lines += list_section("Supporting evidence", memo.supporting_evidence)
    lines += list_section("Contradicting evidence", memo.contradicting_evidence)
    lines += list_section("Unresolved questions", memo.unresolved_questions)
    lines += ["## Provenance", "", citation, ""]
    return "\n".join(lines)


def record_research_memo(
    repository: Repository,
    session_id: str,
    turn: int,
    memo: ResearchMemo,
    actor: Actor | None = None,
) -> ResearchMemoRecord:
    """Write a durable research memo (§35) to ``research/memos/``, citing the
    turn the research was launched or reported from."""
    actor = actor or CURATOR
    if memo.confidence not in VALID_CONFIDENCE:
        raise RecordExtractorError(
            f"{memo.confidence!r} is not a valid research-memo confidence - "
            f"expected one of {', '.join(VALID_CONFIDENCE)} (part 12 §34.1)"
        )
    ensure_clean_tree(repository)
    _, citation = _cite_turn(repository, session_id, turn)
    memo_id = next_research_memo_id(repository)
    relative_path = f"{RESEARCH_MEMOS_RELATIVE_PATH}/{memo_id}.md"
    content = _render_research_memo(memo_id, memo, citation)
    result = write.create(repository, relative_path, content, actor)
    if isinstance(result, Rejected):
        raise RecordExtractorError(
            f"could not write {relative_path}: {result.outcome} - re-run the pass"
        )
    return ResearchMemoRecord(id=memo_id, citation=citation, path=relative_path)


def read_research_memo(repository: Repository, memo_id: str) -> str:
    """Serve one research memo's file, verbatim - the same whole-file
    contract a bare ``SRC-`` or ``CLM-`` read gives."""
    path = repository.root / RESEARCH_MEMOS_RELATIVE_PATH / f"{memo_id}.md"
    if not path.is_file():
        raise RecordExtractorError(f"no such research memo: {memo_id}")
    return path.read_text(encoding="utf-8")
