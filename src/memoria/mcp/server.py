"""The `memoria` MCP server, exposing `read(ref)` and `search_text(query, filters)`.

The second adapter over the core, after the CLI and before the FastAPI app
(#64). §40.1 asks that business logic not be duplicated between them, and
this module is where that stops being an aspiration: it holds no rule the
other two lack, it imports only ``memoria.records``, ``memoria.repository``,
(#12) ``memoria.index`` and (#13) ``memoria.ledger``, and it opens no file
and speaks to no database itself. Everything it does is call one core
function and render what comes back.

`read(ref)` is the single read tool (part 11 §25). Dispatch is read off the
reference, because the ID scheme already names the type; there are no
per-type read tools. What it returns is constrained by ``docs/poc-plan.md``
§7, and the constraint may not be weakened: **retrieval is a superset of
grep**. The verbatim text is served unmodified and contiguously, and a
full-source read gives back the record file exactly as it sits on disk. If
reading through the tool were ever worse than ``cat``, the routing hook would
stop being a router and become a wall, and people would go around it.

`search_text(query, filters)` is the retrieval half (#12). The four §25
filters - event date, recorded date, source type, contemporaneous/
retrospective - are implemented in ``memoria.index.search``, not here: the
tool shapes results, the core computes them, so the same filters reach #64's
web layer without a second, divergent copy.

The ``extraction_*`` tools (#17) are a second class on the same server, and
they are here because there is nowhere else: no model-driving service
(``docs/poc-plan.md`` §3), and the session agent is the only model in the
system. The server is still an adapter - **it cannot call a model and does
not** - so the pass is a conversation: the tools hand paragraphs out, and
every model output arrives back as tool arguments. There is no ``generate_``
anything here, and ``extraction_derive`` and ``extraction_finish`` are local
computation over rows.

See ``docs/tool-surface.md`` for the forced signatures and what is still open.
"""

from __future__ import annotations

import argparse
import sys

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import memoria.extraction as extraction
from memoria.index import SearchFilters, SearchResult, search as search_index
from memoria.ledger import (
    append_extraction_batch,
    append_extraction_brief,
    append_extraction_summary_task,
    append_read,
    append_search,
    session_id_from_env,
)
from memoria.records import Read, ReadError, read as read_ref, real_paragraphs
from memoria.repository import NoEvidenceRoot, Repository, from_env

mcp = MCPServer(
    "memoria",
    instructions=(
        "Memoria serves the evidence archive. Read any stable reference with "
        "read(ref): a SRC- record ID, a paragraph of one, or a repository "
        "path. Evidence comes back verbatim, never summarized. Find text "
        "with search_text(query, filters); each hit's anchor feeds straight "
        "into read(ref). The extraction_* tools run the archive-wide "
        "extraction pass, and are driven by the `extraction` skill rather "
        "than reached for directly."
    ),
)

# Set by main() before the server runs. A module-level value rather than a
# lifespan context: ADR-0004 makes the repository a frozen value precisely so
# that nothing has to hold live state, and the SDK's typed-context idiom would
# buy nothing here but a layer to unwrap.
_repository: Repository | None = None

# Set lazily, the first time a served call needs it, and held for the rest of
# this process's life - a stdio server is spawned per client (docs/poc-plan.md
# §3), so the process is the session (#13).
_session_id: str | None = None


def repository() -> Repository:
    """The repository this server serves.

    Falls back to discovering it, so that importing the module in a test does
    not require main() to have run.
    """
    return _repository if _repository is not None else from_env()


def session_id() -> str:
    """The session this server's served calls belong to (#13)."""
    global _session_id
    if _session_id is None:
        _session_id = session_id_from_env()
    return _session_id


def render(result: Read) -> str:
    """Shape one read into what the model sees.

    **A full-source read is returned bare** - the file, and nothing else.
    That is the whole point of it: it is the undecorated read, and it should
    be indistinguishable from ``cat``. It carried a ``ref:`` line and a
    ``---`` delimiter until the first live session, where a reader saw those
    sitting directly above the record's own frontmatter opener, read the two
    consecutive ``---`` lines as an empty pair, and reported the payload as
    corrupted. The envelope was correct and the report was wrong, which is
    exactly why it matters: an envelope that reads as damage costs the tool
    the trust the routing hook depends on. The line was redundant anyway -
    the record's own frontmatter states its ``id``. Path reads are bare for
    the same reason.

    **A paragraph read keeps a header**, because a paragraph genuinely does
    not carry the fields a reader needs to judge it. Two properties of that
    header are contracts rather than styling, and ``docs/tool-surface.md``
    states them: the verbatim text appears **contiguously and unmodified** -
    never wrapped, re-indented or escaped - and there is exactly one
    delimiter convention, which the curated overlay (#20) must reuse by
    appending after the text rather than interleaving.

    ``original_locator`` is printed and never parsed: it is a pointer a person
    follows, not an offset (#25).
    """
    record = result.record
    if record is None or result.paragraph is None:
        return result.text
    header = [
        f"ref: {result.citation}",
        f"source_type: {record.source_type}",
        f"event_date: {record.event_date}",
        f"date_confidence: {record.date_confidence}",
        f"contemporaneous: {'true' if record.contemporaneous else 'false'}",
        f"original_file: {record.original_file}",
        f"original_locator: {record.original_locator}",
        f"paragraphs_in_record: {len(real_paragraphs(record))}",
    ]
    return "\n".join(header) + "\n---\n" + result.text


@mcp.tool()
def read(ref: str, raw: bool = False) -> str:
    """Read any stable reference, verbatim.

    Accepts a normalized source record by ID (`SRC-000184`), one paragraph of
    one (`SRC-000184 P17`, `#src-000184-p17`, or a search result's anchor
    `src-000184-p17` as-is), a subject or one of its entries
    (`SUB-people`, `SUB-people/bob`), or a repository-relative path
    (`docs/poc-plan.md`).

    A record ID with no paragraph, or a SUB- reference, returns the whole
    file exactly as it is on disk, frontmatter included - the undecorated
    full-source read. Evidence text is never summarized, abridged or
    reformatted.

    `raw=True`, for a bare record ID only, serves the pre-normalization
    original behind that record instead - the file the normalizer read, not
    what it produced. Refused for anything else, and for a binary original
    (docx, pdf) rather than handed back as bytes.

    Reference kinds the archive defines but this build does not resolve yet -
    SES-, CHG-, CLM-, RES-, DEC- - return an error naming the kind.
    """
    try:
        result = read_ref(repository(), ref, raw=raw)
    except (ReadError, NoEvidenceRoot) as exc:
        # ToolError is the SDK's anticipated-failure type: it reaches the
        # model as is_error with this message intact. A bare exception would
        # be reported as "Error executing tool read" with the reason stripped,
        # which is the silent failure #11 exists to forbid. NoEvidenceRoot is
        # the one other core exception a raw read can raise (#113): the same
        # named refusal every evidence read gives, not a second failure
        # shape the model has to learn.
        #
        # Not ledgered: the ledger records what was served (#13), and a
        # failed read served nothing.
        raise ToolError(str(exc)) from exc
    append_read(repository(), session_id(), result)
    return render(result)


def render_search(results: list[SearchResult]) -> str:
    """Shape search hits into what the model sees.

    One line per hit, ranked, carrying both the `SRC-` ID and the paragraph
    anchor - the anchor is what `read(ref)` accepts verbatim, with no
    reconstruction by the caller (docs/tool-surface.md).

    `SearchResult` carries no text (memoria.index): whatever evidence the
    model wants, it reads through `read(ref)` with the anchor this line
    gives it - the same evidence-is-never-summarized discipline `read`
    itself keeps.
    """
    if not results:
        return "No results."
    return "\n".join(f"{r.src_id} {r.anchor}" for r in results)


@mcp.tool()
def search_text(query: str, filters: SearchFilters | None = None) -> str:
    """Full-text search the evidence archive (FTS5), ranked by relevance.

    Returns each hit's `SRC-` ID and paragraph anchor - the anchor feeds
    straight into `read(ref)` with no reconstruction. Carries no text of its
    own: evidence is read, not summarized.

    `filters` narrows by `event_date`, `recorded_date`, `source_type` and
    `contemporaneous` (true excludes retrospective editorial commentary);
    all compose. Dates match the record's verbatim frontmatter string
    exactly.

    Returns "No results." rather than an empty string when nothing matches.
    An unbuilt corpus (no `.memoria/index.db` yet) is the same as an empty
    one - not an error.
    """
    results = search_index(repository(), query, filters)
    append_search(repository(), session_id(), query, filters, results)
    return render_search(results)


# --- the extraction (#17) ----------------------------------------------------


def _tool_error(exc: extraction.ExtractionError) -> ToolError:
    return ToolError(str(exc))


@mcp.tool()
def extraction_brief() -> str:
    """The briefing for one extraction pass: fetch it once and hold it.

    Carries the extraction prompt verbatim, every subject prompt, and the
    names of the entries that already exist. The prompt served here is the
    prompt hashed into every row the pass writes - there is no second copy of
    it anywhere, and nothing paraphrases it.

    Cheap to re-fetch. A session that was compacted or interrupted asks for
    this again and is back where it was; nothing else is needed to resume.
    """
    result = extraction.brief(repository())
    append_extraction_brief(
        repository(), session_id(), [subject.id for subject in result.subjects]
    )
    return render_brief(result)


def render_brief(result: extraction.Brief) -> str:
    lines = [result.extraction_prompt, "", "## The subjects", ""]
    for subject in result.subjects:
        lines += [
            f"### {subject.id}",
            "",
            f"Match: {subject.match}",
            f"Hazards: {subject.hazards}",
            f"auto-promote: {'yes' if subject.auto_promote else 'no'}",
            "",
        ]
    lines += ["## The entries that exist", ""]
    if result.entry_names:
        lines += [f"- {entry_id} ({name})" for entry_id, name in result.entry_names]
    else:
        lines.append(
            "None yet. Every mention is an unplaced surface form, which is the "
            "expected state of a fresh archive."
        )
    lines += ["", f"paragraphs awaiting extraction: {result.pending}"]
    return "\n".join(lines)


@mcp.tool()
def extraction_next_paragraphs(limit: int = 20) -> str:
    """The next paragraphs with no cached reading, verbatim.

    Each comes back as its anchor and its text. Read each one **alone**, per
    the brief, and send the results back with extraction_record.

    Paragraphs already read under the current prompts are never served, so
    calling this again after an interruption resumes rather than repeats, and
    a corpus that is fully read says so.
    """
    if limit < 1:
        raise ToolError("limit must be at least 1")
    # One call, then sliced: asking twice - once for the batch and once for a
    # count - would read every record file in the archive twice per batch.
    pending = extraction.pending_paragraphs(repository())
    remaining = len(pending)
    pending = pending[:limit]
    if pending:
        # A call that served nothing gets no line. The ledger is an account of
        # what reached a context (#13), and a pass over an already-read corpus
        # reaches one with nothing - writing "served: []" would pad the file
        # with the absence of evidence.
        append_extraction_batch(
            repository(), session_id(), [paragraph.anchor for paragraph in pending]
        )
    return render_batch(pending, remaining)


def render_batch(pending: list[extraction.PendingParagraph], remaining: int) -> str:
    """One paragraph per block, text contiguous and unmodified.

    The same contract ``read`` keeps: the text is never wrapped, re-indented
    or escaped, and it comes from the record file rather than the index copy.
    """
    if not pending:
        return "No paragraphs need extraction."
    blocks = [f"anchor: {p.anchor}\n---\n{p.text}" for p in pending]
    # Counted before recording, so this batch is still in it - a paragraph is
    # not read until its reading is cached.
    return (
        "\n\n".join(blocks)
        + f"\n\nawaiting extraction: {remaining} (including this batch)"
    )


@mcp.tool()
def extraction_record(results: list[extraction.RecordedParagraph]) -> str:
    """Cache one batch of paragraph readings.

    Send the whole batch in one call. Each element is accepted or rejected on
    its own: a malformed reading names its reason and the rest are kept, so a
    bad element costs one paragraph rather than the batch. Re-send only what
    was rejected, corrected against the reason given.

    A relation whose ends are not both placed in that same paragraph is
    rejected rather than quietly dropped - reaching across paragraphs is the
    mistake worth being told about.
    """
    if not results:
        raise ToolError("no results to record")
    outcome = extraction.record_batch(
        repository(),
        [(result.anchor, result.to_extraction()) for result in results],
    )
    return render_record_outcome(outcome, len(results))


def render_record_outcome(outcome: extraction.RecordOutcome, total: int) -> str:
    """Per-element outcomes, so a rejected reading names its reason and the
    good ones beside it are still kept."""
    lines = [f"accepted {len(outcome.accepted)} of {total}"]
    lines += [f"rejected - {reason}" for _, reason in outcome.rejected]
    return "\n".join(lines)


@mcp.tool()
def extraction_derive(
    recurrence_threshold: int = extraction.RECURRENCE_THRESHOLD_DEFAULT,
) -> str:
    """Recompute placements, candidates, relations and clusters. No model.

    Runs after the paragraph loop and before the summary loop. Calls nothing
    outside this machine, and is safe to re-run: it recomputes derived state
    and destroys nothing else.
    """
    counts = extraction.derive(
        repository(), recurrence_threshold=recurrence_threshold
    )
    return render_counts(counts)


def render_counts(counts: extraction.DerivedCounts) -> str:
    lines = [
        f"paragraphs read: {counts.memo_hits} of {counts.paragraphs} "
        f"({counts.memo_misses} not current)",
        f"placements: {counts.placements}",
        f"unplaced surface forms: {counts.unplaced_forms}",
        f"relations: {counts.relations}",
        f"proposed match terms: {counts.proposed_match_terms}",
    ]
    for subject_id, (raw, kept) in sorted(counts.per_subject.items()):
        lines.append(
            f"{subject_id}: raw {raw} -> filtered {kept} "
            f"(threshold {counts.recurrence_threshold})"
        )
    lines.append(f"clusters: {counts.clusters} [{counts.clustering_backend}]")
    return "\n".join(lines)


@mcp.tool()
def extraction_next_summary() -> str:
    """The next cluster needing a summary, with what to write it from.

    A leaf cluster serves its member paragraphs. A parent serves its
    children's summaries **and no paragraph text at all** - an upper level is
    a compression of a compression, so there is nothing below to reach for.

    Echo the `membership` value back to extraction_record_summary exactly as
    given.
    """
    pending = extraction.pending_cluster_summaries(repository())
    if not pending:
        return "No cluster needs a summary."
    task = pending[0]
    append_extraction_summary_task(
        repository(), session_id(), task.cluster_id, list(task.member_anchors)
    )
    return render_summary_task(
        task, len(pending), extraction.CLUSTER_SUMMARY_PROMPT
    )


def render_summary_task(
    task: extraction.PendingSummary, remaining: int, prompt: str
) -> str:
    lines = [
        prompt,
        "",
        f"cluster: {task.cluster_id}",
        f"level: {task.level}",
        f"membership: {task.memo_key}",
        f"defined by: {task.label}",
        f"remaining: {remaining}",
        "",
    ]
    if task.child_summaries:
        lines.append("## Its child clusters' summaries")
        lines.append("")
        lines += [f"- {summary}" for summary in task.child_summaries]
    else:
        lines.append("## Its member paragraphs")
        lines.append("")
        lines += [f"- {anchor}" for anchor in task.member_anchors]
        lines.append("")
        lines.append("Read them with read(ref) before writing.")
    return "\n".join(lines)


@mcp.tool()
def extraction_record_summary(
    cluster_id: str, membership: str, summary: str
) -> str:
    """Store one cluster's summary. The text is `[inferred]`: stored and
    served as written, and never evidence.

    `membership` must be the value served with the task. A mismatch means the
    clusters were recomputed in between and this text is about different
    members, which is refused rather than filed.
    """
    try:
        extraction.record_summary(repository(), cluster_id, membership, summary)
    except extraction.ExtractionError as exc:
        raise _tool_error(exc) from exc
    remaining = len(extraction.pending_cluster_summaries(repository()))
    return f"recorded {cluster_id}; {remaining} cluster(s) still need a summary"


@mcp.tool()
def extraction_status() -> str:
    """Where the extraction stands. Reads only; changes nothing.

    Call this before starting a pass and show the author the numbers. A pass
    reads every un-read paragraph of the archive with a model, so it happens
    because someone asked for it, not because a tool was available.
    """
    return render_status(extraction.status(repository()))


def render_status(state: extraction.Status) -> str:
    lines = [
        f"paragraphs: {state.extracted} of {state.paragraphs} read "
        f"({state.pending} awaiting extraction)",
        f"candidates: {state.candidates_raw} raw, "
        f"{state.candidates_above_threshold} above the recurrence filter "
        f"(threshold {state.recurrence_threshold})",
    ]
    for subject_id, (raw, kept) in sorted(state.per_subject.items()):
        lines.append(f"  {subject_id}: raw {raw} -> filtered {kept}")
    lines += [
        f"unplaced surface forms: {state.unplaced_forms}",
        f"proposed match terms awaiting the author: {state.proposed_match_terms}",
    ]
    if state.clusters_by_level:
        levels = ", ".join(
            f"level {level}: {count}"
            for level, count in sorted(state.clusters_by_level.items())
        )
        lines.append(f"clusters: {levels} [{state.clustering_backend}]")
    lines.append(
        f"summaries: {state.summaries_done} written, "
        f"{state.summaries_pending} pending"
    )
    if not state.derived:
        lines.append("nothing derived yet - run extraction_derive")
    return "\n".join(lines)


@mcp.tool()
def extraction_finish(
    recurrence_threshold: int = extraction.RECURRENCE_THRESHOLD_DEFAULT,
) -> str:
    """Close the pass: promote what the subjects say may promote, and report.

    Only subjects declaring `auto-promote: yes` create entries, and only from
    candidates above the recurrence filter. Everything else waits, ranked, for
    the author.

    Refuses while any paragraph is still unread - nothing promotes off a
    partial reading of the archive. A partial *summary* set is fine and is
    reported rather than refused.
    """
    try:
        report = extraction.finish_pass(
            repository(), recurrence_threshold=recurrence_threshold
        )
    except extraction.ExtractionError as exc:
        raise _tool_error(exc) from exc
    return render_pass_report(report)


def render_pass_report(report: extraction.PassReport) -> str:
    lines = [render_counts(report.counts), ""]
    if report.promotions:
        lines.append("auto-promoted:")
        lines += [f"  {render_promotion(promotion)}" for promotion in report.promotions]
    else:
        lines.append(
            "auto-promoted: nothing - no subject declares auto-promote: yes, "
            "or none of its candidates cleared the filter"
        )
    lines.append(f"clusters still needing a summary: {report.summaries_pending}")
    lines.append(
        "The extraction asserted nothing. Every candidate above is a "
        "proposal; match terms decide what is placed."
    )
    return "\n".join(lines)


def render_promotion(promotion: extraction.Promotion) -> str:
    terms = ", ".join(promotion.match_terms) or "none"
    line = f"{promotion.entry_id} (match terms: {terms})"
    if promotion.dropped:
        line += (
            f" - {promotion.dropped} proposed term(s) not seeded; the cap is "
            f"{extraction.MAX_SEEDED_MATCH_TERMS}, edit the entry to add more"
        )
    return line


@mcp.tool()
def extraction_candidates(
    subject_id: str | None = None,
    rejected: bool = False,
    limit: int = 25,
) -> str:
    """List candidates ranked by recurrence, with the id a promotion takes.

    By default those above the recurrence filter, waiting for the author;
    `rejected=True` lists the ones the filter set aside instead, which #17
    keeps enumerable because the filter is a guaranteed miss generator.
    """
    rows = extraction.candidates(
        repository(),
        subject_id=subject_id,
        above_threshold=not rejected,
        limit=limit,
    )
    if not rows:
        return "No candidates" + (" below the filter." if rejected else " waiting.")
    return "\n".join(
        f"{c.candidate_id}  {c.subject_id}  {c.label}  x{c.recurrence}"
        + (f"  - {c.gloss}" if c.gloss else "")
        for c in rows
    )


@mcp.tool()
def extraction_unplaced_forms(limit: int = 50) -> str:
    """List the mentions the pass could not tie to an entry, by anchor."""
    rows = extraction.unplaced_forms(repository(), limit=limit)
    if not rows:
        return "No unplaced surface forms."
    return "\n".join(
        f"{f.anchor}  {f.surface_form!r}  {f.subject_id or '-'}  {f.reason}"
        + (f" ({f.proposed_entry_id})" if f.proposed_entry_id else "")
        for f in rows
    )


@mcp.tool()
def extraction_cluster(cluster_id: str) -> str:
    """Open one cluster: its members, its paragraphs, its children, and its
    summary if one has been written. What an author reads before promoting
    it; the paragraphs are anchors for `read(ref)`, never text."""
    try:
        cluster = extraction.cluster_members(repository(), cluster_id)
    except extraction.ExtractionError as exc:
        raise _tool_error(exc) from exc
    return render_cluster(cluster)


def render_cluster(cluster: extraction.ClusterMembers) -> str:
    lines = [
        f"{cluster.cluster_id} level {cluster.level}"
        + (f" under {cluster.parent_id}" if cluster.parent_id else ""),
        f"label: {cluster.label}",
        f"members: {', '.join(cluster.members)}",
        f"paragraphs: {', '.join(cluster.anchors)}",
        f"children: {', '.join(cluster.children) or 'none'}",
        f"summary: {cluster.summary if cluster.summary else 'not yet written'}",
    ]
    return "\n".join(lines)


@mcp.tool()
def extraction_promote_candidate(
    candidate_id: str, entry_slug: str | None = None
) -> str:
    """The author's one-key promotion: make one candidate an entry, seeded
    with the match terms the extraction proposed for it.

    An author act, never the pass's own. Call it only when the author has
    named the candidate; run `extraction_derive` afterwards so the new
    entry's placements land.
    """
    try:
        promotion = extraction.promote_candidate(
            repository(), candidate_id, extraction.CURATOR, entry_slug=entry_slug
        )
    except extraction.ExtractionError as exc:
        raise _tool_error(exc) from exc
    return "promoted " + render_promotion(promotion)


@mcp.tool()
def extraction_promote_cluster(
    cluster_id: str, subject_id: str = "SUB-themes", entry_slug: str | None = None
) -> str:
    """The author's one-key promotion of a cluster into a Theme or an Arc,
    seeded with the entries and relations that defined it.

    `subject_id` is the author's choice between the two; the cluster itself
    belongs to neither until this call.
    """
    try:
        promotion = extraction.promote_cluster(
            repository(),
            cluster_id,
            extraction.CURATOR,
            subject_id=subject_id,
            entry_slug=entry_slug,
        )
    except extraction.ExtractionError as exc:
        raise _tool_error(exc) from exc
    return "promoted " + render_promotion(promotion)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="memoria-mcp", description="Serve the Memoria tool surface over stdio."
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help=(
            "The Memoria repository to serve. Defaults to walking up from the "
            "working directory; pass it explicitly when the server is spawned "
            "by a client, whose working directory is not a contract."
        ),
    )
    args = parser.parse_args(argv)

    global _repository
    _repository = from_env(args.repo_root)
    # stdout is the JSON-RPC channel: anything printed to it corrupts the
    # protocol. Startup goes to stderr, which the client logs.
    print(f"memoria-mcp: serving {_repository.root}", file=sys.stderr)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
