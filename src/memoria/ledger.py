"""The read ledger: what the tool surface served, and to whom (#13).

``events.jsonl`` is what makes the context manifest a *record* rather than a
*request* (§33, CONTEXT.md's "Supplied context"). It is core, not adapter,
for the same reason the rest of the read side is (ADR-0004): the MCP server
is not the only future caller of ``read`` and ``search`` (#64's web app is
another), and every caller should ledger through one function rather than
each opening its own file.

**Only what was served is ledgered.** A failed read or search supplied
nothing - ``CONTEXT.md``'s "Supplied context" is explicit that the account is
of what Memoria *supplied*, and that is the definition #29's manifest is
built on. So a caller ledgers after a call succeeds, never on the exception
path; there is no "failed" event shape here to begin with.

**Author reads are out of scope.** The ledger records what the tool surface
served *to a session* (§10.4). The UI's own browsing (#25) reads through the
same core but is served to nobody, and passes through nothing that appends
here - there is no session for an author's own click to belong to.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from memoria.index import SearchFilters, SearchResult
from memoria.records import Read
from memoria.repository import Repository

# The hook a spawner uses to tell this process which session its calls
# belong to. Unset in ordinary use today: Claude Code's own session id lives
# in its transcript JSONL path, not in the MCP protocol (docs/poc-plan.md
# §3), so there is no protocol-level way for a tool call to learn it. This
# is where that wiring lands once something sets it.
SESSION_ID_ENV_VAR = "MEMORIA_SESSION_ID"


def estimate_tokens(text: str) -> int:
    """A rough token count for one served item (#29, ADR-0001).

    Four characters per token is the usual rule of thumb for English prose
    under a GPT-family tokenizer. Exactness is not the point - what this
    number feeds is a hypothetical budget cap (``poc-plan.md`` §6 risk 1),
    not a bill - and a fixed, dependency-free heuristic keeps the core's
    only runtime dependency PyYAML (``pyproject.toml``), consistent across
    every item it is measured on rather than exact for any one of them.
    """
    stripped = text.strip()
    return (len(stripped) + 3) // 4 if stripped else 0


def session_id_from_env() -> str:
    """The session this process's served calls belong to.

    Falls back to one id generated for the process's whole lifetime, rather
    than per call: a stdio MCP server is spawned per client (docs/poc-plan.md
    §3), so the process boundary is the session boundary until a spawner
    sets ``MEMORIA_SESSION_ID`` explicitly. Generating fresh per call would
    scatter one session's reads across many files, which is exactly what
    "the session it belongs to" (#13's acceptance criteria) rules out.
    """
    configured = os.environ.get(SESSION_ID_ENV_VAR)
    if configured:
        return configured
    return _generate_session_id()


def _generate_session_id() -> str:
    """A fresh id in part 04 §4's citable form, plus entropy.

    ``SES-20260912-1432`` is minute granularity, not second: two servers
    spawned in the same minute with no suffix would generate the *same* id
    and silently append to one shared ``events.jsonl``, merging two
    sessions' reads into one. The random suffix - 48 bits, checked
    collision-free across 200 ids in the same minute by a test - is what
    keeps the id unique while the documented prefix stays intact and
    parseable. 24 bits would pass that test only about 839 times in 840,
    which is a flaky test, not a passing one.
    """
    now = datetime.now(timezone.utc)
    suffix = secrets.token_hex(6)
    return f"SES-{now:%Y%m%d-%H%M}-{suffix}"


# Part 04 §4's citable session id: SES-YYYYMMDD-HHMM, with this module's own
# random suffix. Matched loosely enough to accept a caller-supplied id that
# carries no suffix at all - only the date and the SES- prefix are load-
# bearing for nesting.
_DATED_SESSION_ID = re.compile(r"^SES-(?P<year>\d{4})(?P<month>\d{2})\d{2}-\d{4}")


def event_path(repository: Repository, session_id: str) -> Path:
    """Where this session's ledger lives.

    Part 04 §2's tree nests a session under ``sessions/<YYYY>/<MM>/SES-.../``
    - the directory #29's context-manifest.json and M4's transcript.md must
    later land in beside this file. Nesting is derived from the session id
    itself, since the documented form (part 04 §4) already carries the date.

    A ``session_id`` that does not carry that form - a caller-supplied
    ``MEMORIA_SESSION_ID`` free of it - has no year/month to nest by, so the
    ledger falls back to ``sessions/<session_id>/events.jsonl`` directly.
    This is a documented deviation (docs/tool-surface.md), not a guess.
    """
    match = _DATED_SESSION_ID.match(session_id)
    if match is None:
        return repository.root / "sessions" / session_id / "events.jsonl"
    return (
        repository.root
        / "sessions"
        / match.group("year")
        / match.group("month")
        / session_id
        / "events.jsonl"
    )


def append_read(repository: Repository, session_id: str, result: Read) -> None:
    """Ledger one served ``read(ref)`` call, and its size.

    ``tokens`` (#29) is measured here, from the text actually served, rather
    than re-derived later from whatever the evidence looks like by the time
    a manifest is built - the count this way always describes what this
    session was actually given, not a later edit of the same record.
    """
    _append(
        repository,
        session_id,
        {
            "tool": "read",
            "ref": result.ref,
            "served": [result.citation],
            "tokens": estimate_tokens(result.text),
        },
    )


def append_search(
    repository: Repository,
    session_id: str,
    query: str,
    filters: SearchFilters | None,
    results: list[SearchResult],
) -> None:
    """Ledger one served ``search_text(query, filters)`` call.

    ``served`` names each hit by its paragraph anchor - the same identifier
    ``read(ref)`` accepts verbatim, so the ledger line and the citation a
    reader follows are the same string.
    """
    _append(
        repository,
        session_id,
        {
            "tool": "search_text",
            "query": query,
            "filters": _filters_dict(filters),
            "served": [result.anchor for result in results],
        },
    )


def append_search_semantic(
    repository: Repository,
    session_id: str,
    query: str,
    filters: SearchFilters | None,
    results: list[SearchResult],
) -> None:
    """Ledger one served ``search_semantic(query, filters)`` call (#81).

    Same shape as ``append_search`` - ``served`` names each hit by its
    paragraph anchor - with its own ``tool`` name so a reader of
    ``events.jsonl`` can tell a lexical hit from a semantic one; the two
    never share a ledger line even when the same query text produced both.
    """
    _append(
        repository,
        session_id,
        {
            "tool": "search_semantic",
            "query": query,
            "filters": _filters_dict(filters),
            "served": [result.anchor for result in results],
        },
    )


def append_search_global(
    repository: Repository,
    session_id: str,
    query: str | None,
    filters: SearchFilters | None,
    summarize: bool,
    summary_served: bool,
    clusters: list[str],
    anchors: list[str],
) -> None:
    """Ledger one served ``search_global(query, filters, summarize)`` call
    (#74). Names the mode that ran - ``summarize`` - and, since ADR-0005's
    "Build shape" 3 records that a summary is *served*, not run, whether the
    call actually served one: ``summarize=True`` over clusters with no
    summary yet still ran in that mode and served none.

    ``clusters`` names the matched cluster ids in their own field rather than
    in ``served`` - the same call ``append_extraction_summary_task`` makes,
    for the same reason: a cluster id is not something ``read(ref)`` accepts
    (ADR-0005 decision 6), so it does not belong beside the anchors that are.
    """
    _append(
        repository,
        session_id,
        {
            "tool": "search_global",
            "query": query,
            "filters": _filters_dict(filters),
            "summarize": summarize,
            "summary_served": summary_served,
            "clusters": clusters,
            "served": anchors,
        },
    )


def _filters_dict(filters: SearchFilters | None) -> dict | None:
    """``asdict`` rather than a hand-picked field list: a filter `#12` adds
    later is ledgered automatically, instead of silently dropping until
    someone remembers to update this function too."""
    if filters is None:
        return None
    return asdict(filters)


def _append(repository: Repository, session_id: str, event: dict) -> None:
    """Append one line, and only append.

    Opened in append mode and written as a single ``write`` call of one
    newline-terminated line: nothing here ever reads the file back to
    rewrite it, which is what makes "append-only" true of every line already
    in it, not just of this function's intent.
    """
    path = event_path(repository, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def append_extraction_brief(
    repository: Repository, session_id: str, subject_ids: list[str]
) -> None:
    """Ledger one served extraction brief.

    It serves every subject prompt verbatim, which is the same category of
    thing as ``read("SUB-people")`` - and that is ledgered, so this is too.
    ``served`` names the subject references for the same reason a search line
    names anchors: the ledger entry and the citation a reader follows are the
    same string.
    """
    _append(
        repository,
        session_id,
        {"tool": "extraction_brief", "served": subject_ids},
    )


def append_extraction_batch(
    repository: Repository, session_id: str, anchors: list[str]
) -> None:
    """Ledger one served batch of paragraphs for extraction.

    Across a whole pass this is the largest delivery of evidence into a
    model's context anywhere in the system - every paragraph of the archive,
    once. Leaving it out would make the supplied-context account (ADR-0001)
    confidently wrong about the one session that read everything, which is
    the failure that account exists to prevent.

    A memo hit is never ledgered, and that falls out rather than being
    arranged: the batch only ever carries paragraphs with no cached reading,
    so a re-run over an already-extracted corpus appends nothing. The ledger
    records what entered a context, not what the pass considered.
    """
    _append(
        repository,
        session_id,
        {"tool": "extraction_next_paragraphs", "served": anchors},
    )


def append_extraction_summary_task(
    repository: Repository,
    session_id: str,
    cluster_id: str,
    anchors: list[str],
) -> None:
    """Ledger one served cluster-summary task.

    ``served`` names the member anchors, which is empty for a parent cluster:
    a parent is served its children's summaries and no evidence at all, and
    the ledger should say so rather than implying it saw paragraphs.

    The cluster id rides in its own field rather than in ``served``, because
    ``served`` names things ``read(ref)`` accepts and a cluster id is
    deliberately not one - cluster identity does not survive re-clustering
    (ADR-0005 decision 6), so it is not a reference anything may keep.
    """
    _append(
        repository,
        session_id,
        {
            "tool": "extraction_next_summary",
            "cluster": cluster_id,
            "served": anchors,
        },
    )
