"""The `memoria` MCP server, exposing `read(ref)` and `search_text(query, filters)`.

The second adapter over the core, after the CLI and before the FastAPI app
(#64). §40.1 asks that business logic not be duplicated between them, and
this module is where that stops being an aspiration: it holds no rule the
other two lack, it imports only ``memoria.records``, ``memoria.repository``,
``memoria.embeddings`` (#81), (#12/#81) ``memoria.index`` and (#13)
``memoria.ledger``, and it opens no file and speaks to no database itself.
Everything it does is call one core function and render what comes back.

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
retrospective - plus #111's `from`/`to` header filters, are implemented in
``memoria.index.search``, not here: the tool shapes results, the core
computes them, so the same filters reach #64's web layer without a second,
divergent copy.

`search_semantic(query, filters)` (#81, ADR-0007) is the nearest-neighbour
half, over the `sqlite-vec` table `memoria rebuild` populates. It reuses the
same `SearchFilters` and the same core predicate builder as `search_text` -
see ``memoria.index.search_semantic``.

The ``extraction_*`` tools (#17) are a second class on the same server, and
they are here because there is nowhere else: no model-driving service
(``docs/poc-plan.md`` §3), and the session agent is the only *generative*
model in the system. The server is still an adapter - **it cannot call a
generative model and does not** - so the pass is a conversation: the tools
hand paragraphs out, and every model output arrives back as tool arguments.
There is no ``generate_`` anything here, and ``extraction_derive`` and
``extraction_finish`` are local computation over rows. `search_semantic` is
the one narrow exception the rule was always going to have: it runs a small,
local, CPU embedding model (``memoria.embeddings``) to turn the query into a
vector, never to generate text, needs no driving service because it needs no
conversation, and costs no metered spend - the distinction ADR-0007 draws
between this and the kind of model call §12.1 forbids running unasked.

See ``docs/tool-surface.md`` for the forced signatures and what is still open.

A bare ``SES-`` read's context manifest (#29) carries a token count per item
(ADR-0001), and this server renders it verbatim. That is not the ban part 14
§40 amends (ADR-0001): §40 bans token figures from the **author-facing**
surfaces - Source viewer, Section view, and the rest #61 will eventually add
- never from this tool, which speaks to the model and to `trace()` (part 04
§4.1), not to the author directly.
"""

from __future__ import annotations

import argparse
import json
import sys

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import memoria.audit as audit
import memoria.extraction as extraction
from memoria.embeddings import default_embed_fn
from memoria.index import (
    ReadOverlay,
    SearchFilters,
    SearchResult,
    SemanticSearchResult,
    search as search_index,
    search_semantic as search_index_semantic,
)
from memoria.ledger import (
    append_extraction_batch,
    append_extraction_brief,
    append_extraction_summary_task,
    append_read,
    append_search,
    append_search_global,
    append_search_semantic,
    append_trace,
    session_id_from_env,
)
from memoria.records import Read, ReadError, read as read_ref, real_paragraphs
from memoria.repository import NoEvidenceRoot, Repository, from_env
from memoria.trace import Trace, TraceError, trace as trace_ref

mcp = MCPServer(
    "memoria",
    instructions=(
        "Memoria serves the evidence archive. Read any stable reference with "
        "read(ref): a SRC- record ID, a paragraph of one, or a repository "
        "path. Evidence comes back verbatim, never summarized. Find text "
        "with search_text(query, filters); each hit's anchor feeds straight "
        "into read(ref). search_semantic(query, filters) finds text by "
        "meaning instead of wording, over the same filters and the same "
        "anchor references. search_global(query, filters, summarize) returns "
        "references grouped by the extraction's clusters instead of a flat "
        "list - with summarize=true it also serves each cluster's memoized "
        "[inferred] summary, never evidence. The extraction_* tools run the "
        "archive-wide extraction pass, and are driven by the `extraction` "
        "skill rather than reached for directly. The audit_* tools run one "
        "on-demand audit of a section, a chapter, or a highlighted passage - "
        "call them only when the author explicitly asked for an audit. "
        "trace(ref) answers why a paragraph of manuscript prose says what it "
        "says: the commit that last touched it, the session turn that "
        "authorized an AI write, and what that session had loaded."
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


def render_overlay(overlay: ReadOverlay) -> str:
    """Shape one curated overlay into what the model sees (#20).

    Every field is printed, even when empty - ``"none"`` rather than an
    absent line - so a paragraph with no overlay comes back the same shape
    as one with one, per ``docs/tool-surface.md``'s "reads of paragraphs
    with no overlay return ... an explicit empty overlay, not a different
    shape".
    """

    def _list(items: list[str]) -> str:
        return ", ".join(items) if items else "none"

    return "\n".join(
        [
            f"entry links: {_list(overlay.entry_links)}",
            f"exclusions: {_list(overlay.exclusions)}",
            f"citing settlements: {_list(overlay.citing_settlements)}",
        ]
    )


def render_context_manifest(manifest: dict) -> str:
    """Shape one session's context manifest (#29) into what the model sees.

    Pretty-printed JSON, not prose: the manifest is a machine record - what
    was loaded, searched and resolved, with a token count per item (#29's
    development instrument, ADR-0001) - and re-rendering that as sentences
    would either drop fields or invent a summary of its own. This tool is
    not one of the author-facing surfaces part 14 §40 bans token figures
    from (see the module docstring's `#61` note); it is the same kind of
    reader `trace()` (part 04 §4.1) is meant to be.
    """
    return json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)


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
    delimiter convention. **The curated overlay (#20) reuses it**, appending
    a second ``---``-delimited block after the text rather than interleaving
    with it. ``render_overlay``'s own output never contains a bare ``---``
    line - every field it prints is an entry id or the literal ``none`` -
    so the *last* ``\\n---\\n`` in a decorated paragraph's rendering is
    always the true text/overlay boundary, even if the paragraph's own
    verbatim text happens to contain one: split from the end, not the
    start, the way ``tests/test_read_ref.py`` and ``tests/test_mcp_server.py``
    do. (The header, symmetrically, never contains one either, so the
    *first* ``\\n---\\n`` is always the header/text boundary.) A
    ``raw=True`` paragraph read, or one whose index could not be read,
    carries no ``overlay`` (``memoria.records.read``), so it stays a bare
    header-plus-text pair, the same shape a plain read had before this
    issue.

    ``original_locator`` is printed and never parsed: it is a pointer a person
    follows, not an offset (#25).
    """
    record = result.record
    if result.context_manifest is not None:
        return result.text + "\n---\n" + render_context_manifest(result.context_manifest)
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
    rendered = "\n".join(header) + "\n---\n" + result.text
    if result.overlay is not None:
        rendered += "\n---\n" + render_overlay(result.overlay)
    return rendered


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

    A paragraph read also carries the curated overlay: which entries it is
    linked to, which have excluded it, and which settlements cite it - a
    second `---`-delimited block after the text, never mixed into it. A
    degraded index (stale schema, or locked by a concurrent rebuild) drops
    only the overlay; the paragraph itself still comes back undecorated
    rather than failing.

    A bare `SES-` reference also carries its context manifest (#29): the
    records it loaded, the entries it resolved, and the searches it ran,
    with which of a search's hits were also read - as a third
    `---`-delimited block, appended the same way.

    `raw=True` serves the least-processed version of what it is given,
    refused for anything but a SRC- reference: for a bare record ID, the
    pre-normalization original behind it - the file the normalizer read, not
    what it produced, refused too for an original that does not decode as
    UTF-8 rather than handed back as bytes; for one paragraph, that
    paragraph with no curated overlay appended.

    A decision (`DEC-0088`) serves that decision's block from `decisions.md`;
    a research memo (`RES-20261018-003`) serves the memo file, verbatim.

    Reference kinds the archive defines but this build does not resolve yet -
    CLM- - return an error naming the kind.
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


def render_trace(result: Trace) -> str:
    """Shape a paragraph's provenance (#42, part 10 §20) into what the model
    sees: the paragraph verbatim between the same ``---`` delimiters a
    paragraph read uses, then one block per commit in its blame, most recent
    first - a human change's ``CHG-`` id, or an AI write's authorizing turn
    quoted verbatim and what its session assembled from. A turn's text is
    session record served to the model, so it is quoted whole rather than
    summarized, the discipline every read keeps."""
    lines = [f"ref: {result.citation}", f"path: {result.path}", "---", result.text, "---"]
    if result.uncommitted_lines:
        lines.append(
            f"uncommitted: {result.uncommitted_lines} line(s) not yet committed - "
            "no provenance until checkpointed"
        )
    if not result.steps and not result.uncommitted_lines:
        lines.append("no commit touches this paragraph")
    for step in result.steps:
        lines.append(
            f"commit: {step.sha} {step.date} by {step.author} ({step.lines} line(s))"
        )
        if step.change_id:
            lines.append(f"  human change: {step.change_id}")
        elif step.authorized_by:
            scope = f" (scope: {step.authorized_scope})" if step.authorized_scope else ""
            lines.append(f"  authorized by: {step.authorized_by}{scope}")
            if step.authorizing_turn is None:
                lines.append("  turn: not derived yet - this session has no transcript")
            else:
                lines.append("  turn:")
                lines.append(step.authorizing_turn)
            lines.append(
                "  assembled from: "
                + (", ".join(step.assembled_from) if step.assembled_from else "nothing ledgered")
            )
        else:
            lines.append(
                "  neither a change-id nor an authorized-by trailer: not a human "
                "change and not an authorized AI write (memoria validate fails this)"
            )
    return "\n".join(lines)


@mcp.tool()
def trace(ref: str) -> str:
    """Why a paragraph of manuscript prose says what it says (#42).

    Takes one paragraph of a section - `SEC-0001 P7` - and composes its
    provenance from facts that already exist, storing nothing: `git blame`
    to the commit(s) that last touched its lines; the commit's trailers to
    a human change (`CHG-`) or to the session turn that authorized an AI
    write; that turn's text, verbatim, once the session is derived; and
    the session's context manifest for what was loaded to write from.

    Blame coarsens under reflow: a human rewrap after an AI rewrite is the
    last thing that touched those lines, and the trace says so.
    """
    try:
        result = trace_ref(repository(), ref)
    except TraceError as exc:
        raise ToolError(str(exc)) from exc
    served = [result.citation] + [
        step.authorized_by
        for step in result.steps
        if step.authorized_by and step.authorizing_turn is not None
    ]
    append_trace(repository(), session_id(), ref, served)
    return render_trace(result)


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

    `filters` narrows by `event_date`, `recorded_date`, `source_type`,
    `contemporaneous` (true excludes retrospective editorial commentary),
    and `from_`/`to` (case-insensitive substring match against the record's
    verbatim `from`/`to` header string - a string filter, not entity
    resolution: it does not resolve a name to a person); all compose. Dates
    match the record's verbatim frontmatter string exactly.

    Returns "No results." rather than an empty string when nothing matches.
    An unbuilt corpus (no `.memoria/index.db` yet) returns no results rather
    than raising - the corpus not being built is an answer, not a driver
    exception. It is not, however, *the same* as an empty one: an earlier
    wording here said so and overreached (#157). The two states are told
    apart by `memoria.index.is_built`, which this tool does not yet report -
    changing what a hit list returns is `docs/tool-surface.md`'s contract and
    its own conversation.
    """
    results = search_index(repository(), query, filters)
    append_search(repository(), session_id(), query, filters, results)
    return render_search(results)


@mcp.tool()
def search_semantic(query: str, filters: SearchFilters | None = None) -> str:
    """Nearest-neighbour search the evidence archive by meaning, ranked
    nearest first (#81, ADR-0007).

    Finds a paragraph whose wording differs from `query` but whose meaning
    is close to it - `search_text`'s FTS5 match cannot. Returns each hit's
    `SRC-` ID and paragraph anchor, exactly like `search_text`: the anchor
    feeds straight into `read(ref)` with no reconstruction, and no result
    carries paragraph text of its own.

    `filters` is the same `SearchFilters` `search_text` takes, and composes
    the same way.

    Every reply ends with a scope line naming how many paragraphs were
    embedded, which filters were applied, and how many this call matched -
    `search_semantic` is an index, and §33.1 is explicit that an index
    reports nothing about its own recall on its own; this is the one place a
    session can say what the semantic index actually covered. An archive
    with no semantic index built yet (`memoria rebuild` has not populated
    it) answers with 0 embedded and 0 matched, the same "not built" shape
    `search_text` gives for a missing index, rather than an error.
    """
    result = search_index_semantic(
        repository(), query, filters, embed_fn=default_embed_fn
    )
    results = list(result.results)
    append_search_semantic(repository(), session_id(), query, filters, results)
    return render_semantic(result)


def render_semantic(result: SemanticSearchResult) -> str:
    """Shape one `search_semantic` result: `render_search`'s hit lines, then
    the scope line naming what was embedded and what was searched (§33.1) -
    always printed, even with no hits, so a caller never mistakes "the index
    has nothing" for "the call failed silently"."""
    if not result.results:
        return result.scope
    return render_search(list(result.results)) + "\n\n" + result.scope


@mcp.tool()
def search_global(
    query: str | None = None,
    filters: SearchFilters | None = None,
    summarize: bool = False,
) -> str:
    """The global tool over the extraction's clusters (part 11 §25, #74).

    Returns paragraph references grouped by cluster rather than `search_text`'s
    flat ranked list, each group labelled by the entries and relations that
    define it - a cluster already promoted into a Theme or Arc is labelled by
    that entry instead. Every reference is an anchor that `read(ref)` accepts
    verbatim, exactly like a `search_text` hit; no reference carries text.

    `query` is optional: given, it full-text searches like `search_text` and
    groups the hits by cluster; omitted, it returns every paragraph of every
    matched cluster - the whole-corpus map step, most useful with
    `filters.level` set. A paragraph nests inside a cluster at every level of
    the hierarchy at once, so exactly one level is grouped per call - the
    level used is always named in the returned scope line, whether or not
    `filters.level` set it.

    `summarize=true` also serves each matched cluster's memoized `[inferred]`
    text - never generated on this call, only served - or says none has been
    written yet. `summarize=false` (the default) never returns cluster text
    at all: a summary is a compression, never evidence, and is served only
    when explicitly asked for.
    """
    result = extraction.search_global(
        repository(), query, filters, summarize=summarize
    )
    clusters = [group.cluster_id for group in result.groups]
    served = [r.anchor for group in result.groups for r in group.results]
    append_search_global(
        repository(),
        session_id(),
        query,
        filters,
        summarize,
        result.summary_served,
        clusters,
        served,
    )
    return render_global(result)


def render_global(result: extraction.GlobalSearchResult) -> str:
    """Shape one `search_global` result into what the model sees: one block
    per matched cluster, then the §33-style scope line naming what ran.

    A cluster routed to a promoted entry (`ClusterGroup.entry_id`) is headed
    by that entry rather than by its own auto-generated label - #74's "a
    promoted cluster routes to the entry, not to its stale label" - but the
    cluster id still rides alongside it. Dropping it would make an over-route
    unverifiable from the served text alone, and would disagree with the
    ledger line for the same call, which always names the cluster
    (`memoria.ledger.append_search_global`'s `clusters` field). A summary
    line appears only when the call asked for one (`result.summarize`), and
    says so explicitly when none has been written yet - it is never left
    silent, which would read as "no summary exists" when it may simply not
    have been asked for.
    """
    if not result.groups:
        return result.scope
    blocks = []
    for group in result.groups:
        header = (
            f"entry: {group.entry_id}  (cluster: {group.cluster_id})"
            if group.entry_id
            else f"cluster: {group.cluster_id}  label: {group.label}"
        )
        lines = [header, f"level: {group.level}"]
        if result.summarize:
            lines.append(
                f"summary: [inferred] {group.summary}"
                if group.summary
                else "summary: not yet written"
            )
        lines += [f"{r.src_id} {r.anchor}" for r in group.results]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n\n" + result.scope


# --- the audit, on demand only (#40) ------------------------------------------
#
# The same shape as the extraction tools above: this server hands out
# paragraph/entry pairs that need judging and takes structured judgements
# back, and never calls a model itself. Reached only by something explicitly
# naming a target - a section, a chapter, or one highlighted passage - never
# by anything scheduled or triggered by ingest (memoria.audit's module
# docstring, test_audit.py's AST sweep).


def render_audit_tasks(tasks: list[audit.AuditTask], remaining: int) -> str:
    if not tasks:
        return "Nothing to audit in this target - every judgement is current."
    blocks = []
    for task in tasks:
        lines = [
            f"anchor: {task.anchor}",
            f"kind: {task.kind}",
            f"not current because: {task.cause}",
            "---",
            "paragraph:",
            task.paragraph_text,
            "",
            f"entry ({task.entry_id}) audit-visible body:",
            task.entry_audit_visible_body,
        ]
        if task.kind == "engagement":
            lines += [
                "",
                "Does this paragraph engage this entry at all? Answer with "
                "engages (yes/no) and a short note on how.",
                "",
                f"subject: {task.subject_prompt}",
            ]
        else:
            lines += [
                "",
                "Audit questions:",
                task.subject_prompt,
            ]
            if task.gathered_anchors:
                lines += [
                    "",
                    "gathered evidence - read each with read(ref) before answering:",
                    *[f"- {a}" for a in task.gathered_anchors],
                ]
            lines += ["", audit.AUTHOR_TESTIMONY_POLICY]
        blocks.append("\n".join(lines))
    return (
        "\n\n===\n\n".join(blocks)
        + f"\n\nawaiting audit: {remaining} (including this batch)"
    )


@mcp.tool()
def audit_pending(
    chapter_number: int,
    section_number: int | None = None,
    paragraph_index: int | None = None,
    limit: int = 20,
) -> str:
    """The next paragraph/entry judgements a target needs, verbatim.

    A target is a chapter (``chapter_number`` alone), a section
    (``+section_number``), or one highlighted passage
    (``+paragraph_index``) - CONTEXT.md's "a button on a section or a
    chapter, or on a highlighted passage". Only judgements that are missing
    or stale (``memoria.audit``'s staleness map) are served; a target with
    nothing not-current says so.

    Send the answers back with ``audit_record``.
    """
    if limit < 1:
        raise ToolError("limit must be at least 1")
    try:
        total = audit.pending_for_target(
            repository(),
            chapter_number=chapter_number,
            section_number=section_number,
            paragraph_index=paragraph_index,
        )
        tasks = audit.audit_tasks_for_target(
            repository(),
            chapter_number=chapter_number,
            section_number=section_number,
            paragraph_index=paragraph_index,
            limit=limit,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return render_audit_tasks(list(tasks), remaining=len(total))


def render_audit_outcome(outcome: audit.AuditRecordOutcome, total: int) -> str:
    lines = [f"accepted {len(outcome.accepted)} of {total}"]
    lines += [f"rejected {anchor} - {reason}" for anchor, reason in outcome.rejected]
    return "\n".join(lines)


@mcp.tool()
def audit_record(results: list[audit.RecordedAuditItem]) -> str:
    """Cache one batch of audit judgements - engagement (``engages``,
    ``note``) or audit verdicts (``clear``, or a ``finding``: its
    disagreement set, a statement, a confidence, and an optional patch).

    Send the whole batch in one call. Each element is accepted or rejected
    on its own, the same shape ``extraction_record`` uses; re-send only what
    was rejected, corrected against the reason given. A finding whose
    disagreement set admits no declared resolution is rejected rather than
    cached - part 06 §8.10's table is authoritative, and there is no row
    that resolves by editing a brief.
    """
    if not results:
        raise ToolError("no results to record")
    outcome = audit.record_audit_batch(repository(), results)
    return render_audit_outcome(outcome, len(results))


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
