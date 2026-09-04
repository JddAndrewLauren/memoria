"""The direct runs: each serve/record pass, executed here against a model
the author switched on (ADR-0010).

A session run is a conversation - the tools hand paragraphs out, the
session model reads them, the tools take structured results back - and
the loop lives in skill prose (``.claude/skills/extraction/SKILL.md`` and
its siblings). A **direct run** is the same loop with Memoria holding the
model's end of it: the same ``brief``, ``pending_*`` and ``record_*`` core
functions, called in the same order, with a ``ModelFn`` (``memoria.model``)
between the serve and the record. Nothing about what is stored changes.
The prompts are served verbatim and unchanged - they are hashed into every
memo key - and every reading still goes through the core's own validation
in ``record_batch``, ``record_audit_batch`` and ``record_observations``,
which is where the honesty checks live. The schemas here mirror the tool
argument dataclasses exactly; they shape the reply, they are not in any
memo key.

**Every call is bounded and every run is resumable.** One call of a driver
makes at most ``limit`` model calls and then returns a report, so a button
or a tool can loop and show progress, a capacity limit leaves nothing
half-done, and "what is left" stays a query over what is absent (the
extraction's own rule). An item the model refused, truncated or answered
with something the core rejects is one ``Rejection`` in the report; the
bounded step goes on, but its caller stops continuation when the report
contains a rejection. A provider failure (``ModelError``) stops the run
where it is, and what was recorded before it stays recorded.

**Metered spend is ledgered per call** (``ledger.append_model_call``), and
what entered the model's context is ledgered by the same lines a session's
tools write - the brief, the batch, the summary task, a gathered read - so
the supplied-context account is as true of a direct run as of a session.

This module never imports the SDK. ``memoria.model`` is reached for its
types alone; the ``ModelFn`` a caller hands in is the whole of the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from memoria import audit, extraction, grill, ledger, records, style
from memoria.model import ModelError, ModelFn, ModelReply, ModelRequest
from memoria.repository import Repository

PASS_EXTRACTION = "extraction"
PASS_CLUSTER_SUMMARY = "cluster_summary"
PASS_AUDIT = "audit"
PASS_STYLE = "style"
PASS_GRILL = "grill"

# Room for the reply, per pass. A paragraph's reading is a short JSON
# object; a summary is a paragraph or two of prose; an audit verdict may
# carry a proposed rewrite; a style analysis lists every observation at
# once, with a quoted example each.
MAX_TOKENS = {
    PASS_EXTRACTION: 4096,
    PASS_CLUSTER_SUMMARY: 2048,
    PASS_AUDIT: 4096,
    PASS_STYLE: 8192,
    # A grilling turn is one question, or at its end a brief and a whole
    # section's prose.
    PASS_GRILL: 8192,
}

# --- the schemas ---------------------------------------------------------------
#
# Each is the JSON shape of the corresponding ``Recorded*`` dataclass the MCP
# tool takes as an argument - `extraction.RecordedParagraph`,
# `audit.RecordedAuditItem`, `style.RecordedObservation` - minus the fields
# the driver already knows (the anchor, the kind). ``additionalProperties``
# is false throughout so the model cannot invent a field the core would
# silently ignore.

_STRING = {"type": "string"}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "placements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"entry_id": _STRING, "surface_form": _STRING},
                "required": ["entry_id", "surface_form"],
                "additionalProperties": False,
            },
        },
        "unplaced": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"surface_form": _STRING, "subject_id": _STRING},
                "required": ["surface_form", "subject_id"],
                "additionalProperties": False,
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"from_ref": _STRING, "verb": _STRING, "to_ref": _STRING},
                "required": ["from_ref", "verb", "to_ref"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["placements", "unplaced", "relations"],
    "additionalProperties": False,
}

ENGAGEMENT_SCHEMA = {
    "type": "object",
    "properties": {"engages": {"type": "boolean"}, "note": _STRING},
    "required": ["engages", "note"],
    "additionalProperties": False,
}

# ``clear`` true means no finding and ``finding`` is ignored; ``patch`` empty
# means no proposed rewrite. Both stand in for "null" so the schema needs
# no nullable types.
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "clear": {"type": "boolean"},
        "finding": {
            "type": "object",
            "properties": {
                "disagreement_set": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"kind": _STRING, "ref": _STRING},
                        "required": ["kind", "ref"],
                        "additionalProperties": False,
                    },
                },
                "statement": _STRING,
                "confidence": _STRING,
                "patch": _STRING,
            },
            "required": ["disagreement_set", "statement", "confidence", "patch"],
            "additionalProperties": False,
        },
    },
    "required": ["clear", "finding"],
    "additionalProperties": False,
}

STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"aspect": _STRING, "observation": _STRING, "example": _STRING},
                "required": ["aspect", "observation", "example"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["observations"],
    "additionalProperties": False,
}

# One interviewer turn. ``done`` false: ``question`` and
# ``recommended_answer`` carry the turn and the draft fields are empty;
# ``done`` true: ``brief`` and ``draft`` carry the section and the question
# fields are empty. Empty strings stand in for null, as in ``VERDICT_SCHEMA``.
GRILL_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean"},
        "question": _STRING,
        "recommended_answer": _STRING,
        "brief": _STRING,
        "draft": _STRING,
    },
    "required": ["done", "question", "recommended_answer", "brief", "draft"],
    "additionalProperties": False,
}


# --- the reports ---------------------------------------------------------------


@dataclass(frozen=True)
class Rejection:
    """One item the run could not record, and why - the model refused it,
    ran out of room, answered off-schema, or the core rejected the reading."""

    anchor: str
    reason: str


@dataclass(frozen=True)
class Spend:
    """What one driver call cost: the calls made and the tokens they used,
    on the model that answered (which may differ from the one asked for)."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class ExtractionRun:
    """One bounded step of the extraction. ``phase`` is what this call did:
    ``paragraphs`` (read up to ``limit``), ``summaries`` (closed the pass if
    it was open, then wrote up to ``limit`` summaries), or ``done``."""

    phase: str
    paragraphs_read: int
    paragraphs_accepted: int
    paragraphs_remaining: int
    summaries_written: int
    summaries_remaining: int
    finished: bool
    promotions: tuple[str, ...]
    rejected: tuple[Rejection, ...]
    spend: Spend


@dataclass(frozen=True)
class AuditRun:
    accepted: int
    findings: int
    remaining: int
    rejected: tuple[Rejection, ...]
    spend: Spend


@dataclass(frozen=True)
class StyleRun:
    accepted: int
    rejected: tuple[Rejection, ...]
    spend: Spend


@dataclass(frozen=True)
class GrillTurn:
    """One turn of the interview as the client holds it. ``role`` is
    ``author`` or ``interviewer``; the transcript is the client's, so a
    driver call receives the whole of it and stores none of it."""

    role: str
    text: str


@dataclass(frozen=True)
class GrillRun:
    """One interviewer turn (ADR-0012). While ``done`` is false it is the
    next ``question`` with its ``recommended_answer``; once true it is the
    ``brief`` and the ``draft``, for the author to edit and write. A reply
    the driver could not use is the one ``rejected`` item, and every other
    field is empty."""

    done: bool
    question: str
    recommended_answer: str
    brief: str
    draft: str
    rejected: tuple[Rejection, ...]
    spend: Spend


# --- the machinery -------------------------------------------------------------


class _Rejected(Exception):
    """A reply that cannot become a recorded item. Internal: it becomes a
    ``Rejection`` in the report, never an exception a caller sees."""


@dataclass
class _Meter:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    rejected: list[Rejection] = field(default_factory=list)

    def spend(self) -> Spend:
        return Spend(
            calls=self.calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model=self.model,
        )


def _call(
    repository: Repository,
    session_id: str,
    model: ModelFn,
    request: ModelRequest,
    meter: _Meter,
    *,
    provider: str,
    anchor: str | None = None,
) -> ModelReply:
    """One model call, ledgered whatever it returned - a refusal was billed
    for its input, so it is spend too. A call the provider failed is
    ledgered as well, with ``stop_reason`` ``error`` and no usage figures
    (the provider reported none), so a billed-then-failed call is never a
    call the ledger does not know about; the ``ModelError`` then goes on
    to stop the run."""
    try:
        reply = model(request)
    except ModelError as exc:
        ledger.append_model_call(
            repository,
            session_id,
            pass_name=request.pass_name,
            provider=provider,
            model="",
            input_tokens=0,
            output_tokens=0,
            stop_reason="error",
            anchor=anchor,
            error=str(exc),
        )
        raise
    usage = reply.usage
    ledger.append_model_call(
        repository,
        session_id,
        pass_name=request.pass_name,
        provider=provider,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        stop_reason=reply.stop_reason,
        anchor=anchor,
    )
    meter.calls += 1
    meter.input_tokens += usage.input_tokens
    meter.output_tokens += usage.output_tokens
    meter.model = usage.model
    return reply


def _text(reply: ModelReply) -> str:
    if reply.stop_reason == "refusal":
        raise _Rejected(f"the model refused: {reply.refusal or 'no reason given'}")
    if reply.stop_reason == "max_tokens":
        raise _Rejected("the reply was cut off at max_tokens")
    if not reply.text.strip():
        raise _Rejected("the model returned nothing")
    return reply.text


def _object(reply: ModelReply) -> dict:
    text = _text(reply)
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise _Rejected(f"the reply was not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise _Rejected("the reply was not a JSON object")
    return value


def _rows(value: dict, key: str, fields: tuple[str, ...]) -> list[dict]:
    """The list under ``key``, each element checked to carry exactly
    ``fields`` as strings - the schema promises this, and a fake or a
    provider that ignores the schema must not crash the run."""
    rows = value.get(key, [])
    if not isinstance(rows, list):
        raise _Rejected(f"{key!r} is not a list")
    out = []
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(f), str) for f in fields):
            raise _Rejected(f"an element of {key!r} is malformed: {row!r}")
        out.append({f: row[f] for f in fields})
    return out


# --- the extraction ------------------------------------------------------------


def extraction_system_text(brief: extraction.Brief) -> str:
    """The brief as a session sees it - the core's own rendering, the one
    ``extraction_brief`` serves - plus how to answer. Identical across every
    call of a run, hence the system block."""
    return (
        extraction.render_brief(brief)
        + "\n\n"
        + "You will be given one paragraph at a time. Read it alone - carry "
        "nothing over from any other paragraph - and answer with its "
        "placements, its unplaced surface forms and its relations, as JSON."
    )


def _paragraph_user_text(paragraph: extraction.PendingParagraph) -> str:
    return f"anchor: {paragraph.anchor}\n---\n{paragraph.text}"


def _reading(anchor: str, value: dict) -> extraction.RecordedParagraph:
    return extraction.RecordedParagraph(
        anchor=anchor,
        placements=[
            extraction.RecordedPlacement(**row)
            for row in _rows(value, "placements", ("entry_id", "surface_form"))
        ],
        unplaced=[
            extraction.RecordedForm(**row)
            for row in _rows(value, "unplaced", ("surface_form", "subject_id"))
        ],
        relations=[
            extraction.RecordedRelation(**row)
            for row in _rows(value, "relations", ("from_ref", "verb", "to_ref"))
        ],
    )


def summary_user_text(task: extraction.PendingSummary, texts: dict[str, str]) -> str:
    """The summary task as a session sees it - the core's own rendering -
    with a leaf's member paragraphs inlined: a session would ``read(ref)``
    each; here they are served in the same call."""
    return extraction.render_summary_task(task, texts)


def run_extraction(
    repository: Repository,
    model: ModelFn,
    session_id: str,
    *,
    limit: int = 20,
    recurrence_threshold: int = extraction.RECURRENCE_THRESHOLD_DEFAULT,
    provider: str = "anthropic",
) -> ExtractionRun:
    """One bounded step of the extraction, in the skill's order.

    While paragraphs await extraction: read up to ``limit`` of them, one
    call each, and record the batch. Once none do: close the pass
    (``finish_pass`` - derive, auto-promote, derive again; idempotent, so
    it is simply run again on every summary-phase call rather than any
    state being carried between calls), then write up to ``limit`` cluster
    summaries, leaves first. When nothing remains, ``phase`` is ``done``.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    meter = _Meter()
    pending = extraction.pending_paragraphs(repository, limit=limit)
    if pending:
        brief = extraction.brief(repository)
        system = extraction_system_text(brief)
        results: list[tuple[str, extraction.ParagraphExtraction]] = []
        for paragraph in pending:
            # Each paragraph is a separate model context. Ledger only the
            # brief and paragraph that are about to enter this call; if a
            # provider failure stops the loop, untouched anchors never read
            # as supplied.
            ledger.append_extraction_brief(
                repository, session_id, [subject.id for subject in brief.subjects]
            )
            ledger.append_extraction_batch(repository, session_id, [paragraph.anchor])
            reply = _call(
                repository,
                session_id,
                model,
                ModelRequest(
                    system=system,
                    user=_paragraph_user_text(paragraph),
                    schema=EXTRACTION_SCHEMA,
                    max_tokens=MAX_TOKENS[PASS_EXTRACTION],
                    pass_name=PASS_EXTRACTION,
                ),
                meter,
                provider=provider,
                anchor=paragraph.anchor,
            )
            try:
                results.append((paragraph.anchor, _reading(paragraph.anchor, _object(reply)).to_extraction()))
            except _Rejected as exc:
                meter.rejected.append(Rejection(paragraph.anchor, str(exc)))
        accepted = 0
        if results:
            outcome = extraction.record_batch(repository, results)
            accepted = len(outcome.accepted)
            meter.rejected += [Rejection(anchor, reason) for anchor, reason in outcome.rejected]
        return ExtractionRun(
            phase="paragraphs",
            paragraphs_read=len(pending),
            paragraphs_accepted=accepted,
            paragraphs_remaining=len(extraction.pending_paragraphs(repository)),
            summaries_written=0,
            summaries_remaining=len(extraction.pending_cluster_summaries(repository)),
            finished=False,
            promotions=(),
            rejected=tuple(meter.rejected),
            spend=meter.spend(),
        )

    report = extraction.finish_pass(repository, recurrence_threshold=recurrence_threshold)
    promotions = tuple(p.entry_id for p in report.promotions)
    tasks = extraction.pending_cluster_summaries(repository)[:limit]
    written = 0
    if tasks:
        texts = extraction.paragraph_texts(repository)
        for task in tasks:
            ledger.append_extraction_summary_task(
                repository, session_id, task.cluster_id, list(task.member_anchors)
            )
            reply = _call(
                repository,
                session_id,
                model,
                ModelRequest(
                    system=extraction.CLUSTER_SUMMARY_PROMPT,
                    user=summary_user_text(task, texts),
                    max_tokens=MAX_TOKENS[PASS_CLUSTER_SUMMARY],
                    pass_name=PASS_CLUSTER_SUMMARY,
                ),
                meter,
                provider=provider,
                anchor=task.cluster_id,
            )
            try:
                extraction.record_summary(repository, task.cluster_id, task.memo_key, _text(reply).strip())
                written += 1
            except (_Rejected, extraction.ExtractionError) as exc:
                meter.rejected.append(Rejection(task.cluster_id, str(exc)))
    remaining = len(extraction.pending_cluster_summaries(repository))
    return ExtractionRun(
        phase="summaries" if tasks else "done",
        paragraphs_read=0,
        paragraphs_accepted=0,
        paragraphs_remaining=0,
        summaries_written=written,
        summaries_remaining=remaining,
        finished=True,
        promotions=promotions,
        rejected=tuple(meter.rejected),
        spend=meter.spend(),
    )


# --- the audit -----------------------------------------------------------------


def audit_system_text(repository: Repository) -> str:
    """What a session's ``audit_pending`` prints once above a batch - the
    author's writing style, because a finding's patch is manuscript prose -
    plus how to answer as JSON. The testimony policy is not here: each
    audit-verdict task carries it, as the core renders it, and an
    engagement task does not."""
    lines = [
        "You are auditing manuscript prose against the entries it draws on. "
        "Each task is one paragraph and one entry. Answer as JSON.",
        "",
        "An engagement task asks whether the paragraph engages the entry at "
        "all: answer with engages (true or false) and a short note on how.",
        "",
        "An audit-verdict task asks the subject's own audit questions of the "
        "paragraph against the entry's audit-visible body and the gathered "
        "evidence. Answer clear: true when nothing disagrees. Otherwise "
        "clear: false and a finding - the disagreement set (each member a "
        "kind, passage or entry or source, and its ref), a statement of how "
        "they disagree, a confidence (low, moderate or high), and a patch "
        "holding a proposed rewrite of the paragraph, or empty if you "
        "propose none.",
    ]
    rendered = style.writing_style_prompt(style.load_style(repository))
    if rendered is not None:
        lines += [
            "",
            "A proposed rewrite (a finding's patch) follows this writing style.",
            "",
            rendered,
        ]
    return "\n".join(lines)


def audit_user_text(task: audit.AuditTask, gathered: dict[str, str]) -> str:
    """One task as ``audit_pending`` prints it - the core's own rendering -
    with each gathered anchor's text inlined where a session would
    ``read(ref)`` it."""
    return audit.render_task(task, gathered)


def _audit_item(task: audit.AuditTask, value: dict) -> audit.RecordedAuditItem:
    if task.kind == "engagement":
        engages = value.get("engages")
        if not isinstance(engages, bool):
            raise _Rejected("'engages' is not a boolean")
        note = value.get("note", "")
        return audit.RecordedAuditItem(
            anchor=task.anchor, kind=task.kind, engages=engages, note=str(note)
        )
    clear = value.get("clear")
    if not isinstance(clear, bool):
        raise _Rejected("'clear' is not a boolean")
    if clear:
        return audit.RecordedAuditItem(anchor=task.anchor, kind=task.kind, clear=True)
    finding = value.get("finding")
    if not isinstance(finding, dict):
        raise _Rejected("a verdict that is not clear needs a finding")
    members = _rows(finding, "disagreement_set", ("kind", "ref"))
    patch = finding.get("patch")
    return audit.RecordedAuditItem(
        anchor=task.anchor,
        kind=task.kind,
        clear=False,
        finding=audit.RecordedFinding(
            disagreement_set=[audit.RecordedDisagreementMember(**m) for m in members],
            statement=str(finding.get("statement", "")),
            confidence=str(finding.get("confidence", "moderate")),
            patch=patch if isinstance(patch, str) and patch.strip() else None,
        ),
    )


def run_audit(
    repository: Repository,
    model: ModelFn,
    session_id: str,
    *,
    chapter_number: int,
    section_number: int | None = None,
    paragraph_index: int | None = None,
    limit: int = 20,
    provider: str = "anthropic",
) -> AuditRun:
    """Answer up to ``limit`` of a target's not-current judgements and
    record them. ``ValueError`` for a target that names a passage without
    its section, as ``audit.pending_for_target`` refuses it."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    meter = _Meter()
    tasks = audit.audit_tasks_for_target(
        repository,
        chapter_number=chapter_number,
        section_number=section_number,
        paragraph_index=paragraph_index,
        limit=limit,
    )
    items: list[audit.RecordedAuditItem] = []
    if tasks:
        system = audit_system_text(repository)
        gathered: dict[str, str] = {}
        gathered_failures: dict[str, str] = {}
        for task in tasks:
            unreadable: list[tuple[str, str]] = []
            for anchor in task.gathered_anchors:
                if anchor in gathered:
                    continue
                if anchor in gathered_failures:
                    unreadable.append((anchor, gathered_failures[anchor]))
                    continue
                try:
                    served = records.read(repository, anchor)
                except records.ReadError as exc:
                    gathered_failures[anchor] = str(exc)
                    unreadable.append((anchor, str(exc)))
                    continue
                gathered[anchor] = served.text
                ledger.append_read(repository, session_id, served)
            if unreadable:
                details = "; ".join(
                    f"{anchor} could not be read: {reason}" for anchor, reason in unreadable
                )
                meter.rejected.append(
                    Rejection(task.anchor, f"gathered evidence {details}")
                )
                continue
            reply = _call(
                repository,
                session_id,
                model,
                ModelRequest(
                    system=system,
                    user=audit_user_text(task, gathered),
                    schema=ENGAGEMENT_SCHEMA if task.kind == "engagement" else VERDICT_SCHEMA,
                    max_tokens=MAX_TOKENS[PASS_AUDIT],
                    pass_name=PASS_AUDIT,
                ),
                meter,
                provider=provider,
                anchor=task.anchor,
            )
            try:
                items.append(_audit_item(task, _object(reply)))
            except _Rejected as exc:
                meter.rejected.append(Rejection(task.anchor, str(exc)))
    accepted = 0
    findings = 0
    if items:
        outcome = audit.record_audit_batch(repository, items)
        accepted = len(outcome.accepted)
        accepted_anchors = set(outcome.accepted)
        findings = sum(
            1 for item in items if item.finding is not None and item.anchor in accepted_anchors
        )
        meter.rejected += [Rejection(anchor, reason) for anchor, reason in outcome.rejected]
    remaining = len(
        audit.pending_for_target(
            repository,
            chapter_number=chapter_number,
            section_number=section_number,
            paragraph_index=paragraph_index,
        )
    )
    return AuditRun(
        accepted=accepted,
        findings=findings,
        remaining=remaining,
        rejected=tuple(meter.rejected),
        spend=meter.spend(),
    )


# --- the writing-style analysis -------------------------------------------------


def style_system_text(served: style.Brief) -> str:
    """The prompt and what the style already says - the instruction half of
    the brief, as the core renders it for ``style_brief`` - plus how to
    answer."""
    return (
        style.render_brief_prompt(served)
        + "\n\nAnswer as JSON: a list of observations, each with its aspect, "
        "the observation and its example."
    )


def style_user_text(served: style.Brief) -> str:
    """Every sample contiguous and unmodified - the other half, as the core
    renders it."""
    return style.render_brief_samples(served)


def run_style(
    repository: Repository,
    model: ModelFn,
    session_id: str,
    *,
    provider: str = "anthropic",
) -> StyleRun:
    """One analysis: the samples in, the proposed observations recorded for
    the author to confirm in Settings. ``StyleError`` when there is nothing
    to analyse, as ``style.brief`` refuses it."""
    meter = _Meter()
    served = style.brief(repository)
    ledger.append_style_brief(repository, session_id, [sample.ref for sample in served.samples])
    reply = _call(
        repository,
        session_id,
        model,
        ModelRequest(
            system=style_system_text(served),
            user=style_user_text(served),
            schema=STYLE_SCHEMA,
            max_tokens=MAX_TOKENS[PASS_STYLE],
            pass_name=PASS_STYLE,
        ),
        meter,
        provider=provider,
    )
    try:
        rows = _rows(_object(reply), "observations", ("aspect", "observation", "example"))
    except _Rejected as exc:
        return StyleRun(
            accepted=0,
            rejected=(Rejection("analysis", str(exc)),),
            spend=meter.spend(),
        )
    observations = [style.RecordedObservation(**row) for row in rows]
    if not observations:
        return StyleRun(
            accepted=0,
            rejected=(Rejection("analysis", "the model proposed no observations"),),
            spend=meter.spend(),
        )
    # The key the brief served, as a session echoes it back to style_record:
    # the record is bound to the samples the model read.
    outcome = style.record_observations(repository, observations, served.analysis_key)
    return StyleRun(
        accepted=len(outcome.accepted),
        rejected=tuple(Rejection(str(ordinal), reason) for ordinal, reason in outcome.rejected),
        spend=meter.spend(),
    )


# --- the grilling ----------------------------------------------------------------

GRILL_ROLE_AUTHOR = "author"
GRILL_ROLE_INTERVIEWER = "interviewer"


def grill_system_text(served: grill.Brief) -> str:
    """The whole briefing - prompt and context - as ``grill_brief`` serves
    it to a session, plus the reply shape. Identical across every turn of
    one interview, so it is the cached system block."""
    return (
        grill.render_brief(served)
        + "\n\nAnswer as JSON. While the understanding is not yet shared: done false, "
        "the next question and your recommended answer, brief and draft empty. "
        "Once it is, or once the author asks you to write: done true, the brief and "
        "the draft, question and recommended_answer empty."
    )


def grill_user_text(turns: tuple[GrillTurn, ...]) -> str:
    """The interview so far, verbatim, oldest first - or the opening, when
    there is none yet."""
    if not turns:
        return "The interview is starting. Ask your first question."
    lines = ["## The interview so far", ""]
    for turn in turns:
        speaker = "Author" if turn.role == GRILL_ROLE_AUTHOR else "Interviewer"
        lines += [f"### {speaker}", "", turn.text, ""]
    lines.append("Reply with your next turn.")
    return "\n".join(lines)


def run_grill(
    repository: Repository,
    model: ModelFn,
    session_id: str,
    *,
    chapter_id: str,
    source_ref: str | None,
    turns: tuple[GrillTurn, ...],
    provider: str = "anthropic",
) -> GrillRun:
    """One interviewer turn of a grilling about a new section of
    ``chapter_id`` (ADR-0012): the briefing as the system text, the
    client's transcript as the user text, one metered call. Stateless -
    nothing is kept between calls but what the client sends back. The
    briefing is ledgered as served every call, since every call serves it.
    ``grill.GrillError`` for an unknown chapter or source, as ``grill.brief``
    refuses it."""
    meter = _Meter()
    served = grill.brief(repository, chapter_id, source_ref)
    ledger.append_grill_brief(repository, session_id, served.served)
    reply = _call(
        repository,
        session_id,
        model,
        ModelRequest(
            system=grill_system_text(served),
            user=grill_user_text(turns),
            schema=GRILL_SCHEMA,
            max_tokens=MAX_TOKENS[PASS_GRILL],
            pass_name=PASS_GRILL,
        ),
        meter,
        provider=provider,
    )
    try:
        value = _object(reply)
        done = value.get("done")
        if not isinstance(done, bool):
            raise _Rejected("'done' is not a boolean")
        fields = {}
        for name in ("question", "recommended_answer", "brief", "draft"):
            text = value.get(name, "")
            if not isinstance(text, str):
                raise _Rejected(f"{name!r} is not a string")
            fields[name] = text.strip()
        if done and not fields["draft"]:
            raise _Rejected("the interviewer said it was done and drafted nothing")
        if not done and not fields["question"]:
            raise _Rejected("the interviewer asked nothing")
    except _Rejected as exc:
        return GrillRun(
            done=False,
            question="",
            recommended_answer="",
            brief="",
            draft="",
            rejected=(Rejection("interview", str(exc)),),
            spend=meter.spend(),
        )
    return GrillRun(
        done=done,
        question=fields["question"] if not done else "",
        recommended_answer=fields["recommended_answer"] if not done else "",
        brief=fields["brief"] if done else "",
        draft=fields["draft"] if done else "",
        rejected=(),
        spend=meter.spend(),
    )
