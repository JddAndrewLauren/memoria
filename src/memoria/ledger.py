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
    now = datetime.now(timezone.utc)
    return f"SES-{now:%Y%m%d-%H%M%S}"


def event_path(repository: Repository, session_id: str) -> Path:
    """Where this session's ledger lives (part 04 §2)."""
    return repository.root / "sessions" / session_id / "events.jsonl"


def append_read(repository: Repository, session_id: str, result: Read) -> None:
    """Ledger one served ``read(ref)`` call."""
    _append(
        repository,
        session_id,
        {"tool": "read", "ref": result.ref, "served": [result.citation]},
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


def _filters_dict(filters: SearchFilters | None) -> dict | None:
    if filters is None:
        return None
    return {
        "event_date": filters.event_date,
        "recorded_date": filters.recorded_date,
        "source_type": filters.source_type,
        "contemporaneous": filters.contemporaneous,
    }


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
