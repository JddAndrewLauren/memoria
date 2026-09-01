"""The `memoria` MCP server, exposing `read(ref)`.

The second adapter over the core, after the CLI and before the FastAPI app
(#64). §40.1 asks that business logic not be duplicated between them, and
this module is where that stops being an aspiration: it holds no rule the
other two lack, it imports only ``memoria.records`` and ``memoria.repository``,
and it opens no file and speaks to no database. Everything it does is call one
core function and render what comes back.

`read(ref)` is the single read tool (part 11 §25). Dispatch is read off the
reference, because the ID scheme already names the type; there are no
per-type read tools. What it returns is constrained by ``docs/poc-plan.md``
§7, and the constraint may not be weakened: **retrieval is a superset of
grep**. The verbatim text is served unmodified and contiguously, and a
full-source read gives back the record file exactly as it sits on disk. If
reading through the tool were ever worse than ``cat``, the routing hook would
stop being a router and become a wall, and people would go around it.

See ``docs/tool-surface.md`` for the forced signature and what is still open.
"""

from __future__ import annotations

import argparse
import sys

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from memoria.records import Read, ReadError, read as read_ref
from memoria.repository import Repository, from_env

mcp = MCPServer(
    "memoria",
    instructions=(
        "Memoria serves the evidence archive. Read any stable reference with "
        "read(ref): a SRC- record ID, a paragraph of one, or a repository "
        "path. Evidence comes back verbatim, never summarized."
    ),
)

# Set by main() before the server runs. A module-level value rather than a
# lifespan context: ADR-0004 makes the repository a frozen value precisely so
# that nothing has to hold live state, and the SDK's typed-context idiom would
# buy nothing here but a layer to unwrap.
_repository: Repository | None = None


def repository() -> Repository:
    """The repository this server serves.

    Falls back to discovering it, so that importing the module in a test does
    not require main() to have run.
    """
    return _repository if _repository is not None else from_env()


def render(result: Read) -> str:
    """Shape one read into what the model sees.

    A short header, then the delimiter the record format already uses, then
    the payload. Two properties of this are contracts rather than styling,
    and ``docs/tool-surface.md`` states them: the verbatim text appears
    **contiguously and unmodified** - never wrapped, re-indented or escaped -
    and there is exactly one delimiter convention, which the curated overlay
    (#20) must reuse by appending after the text rather than interleaving.

    ``original_locator`` is printed and never parsed: it is a pointer a person
    follows, not an offset (#25).
    """
    header = [f"ref: {result.citation}"]
    record = result.record
    if record is not None and result.paragraph is not None:
        # A paragraph read carries no frontmatter of its own, so the fields a
        # reader needs to judge the evidence travel with it. A full-source
        # read does not repeat them: they are in the text already.
        header += [
            f"source_type: {record.source_type}",
            f"event_date: {record.event_date}",
            f"date_confidence: {record.date_confidence}",
            f"contemporaneous: {'true' if record.contemporaneous else 'false'}",
            f"original_file: {record.original_file}",
            f"original_locator: {record.original_locator}",
            f"paragraphs_in_record: {len(record.paragraphs)}",
        ]
    return "\n".join(header) + "\n---\n" + result.text


@mcp.tool()
def read(ref: str) -> str:
    """Read any stable reference, verbatim.

    Accepts a normalized source record by ID (`SRC-000184`), one paragraph of
    one (`SRC-000184 P17`, `#src-000184-p17`, or a search result's anchor
    `src-000184-p17` as-is), or a repository-relative path
    (`docs/poc-plan.md`).

    A record ID with no paragraph returns the whole record file exactly as it
    is on disk, frontmatter and anchors included - the undecorated full-source
    read. Evidence text is never summarized, abridged or reformatted.

    Reference kinds the archive defines but this build does not resolve yet -
    SES-, CHG-, CLM-, RES-, DEC-, SUB- - return an error naming the kind.
    """
    try:
        return render(read_ref(repository(), ref))
    except ReadError as exc:
        # ToolError is the SDK's anticipated-failure type: it reaches the
        # model as is_error with this message intact. A bare exception would
        # be reported as "Error executing tool read" with the reason stripped,
        # which is the silent failure #11 exists to forbid.
        raise ToolError(str(exc)) from exc


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
