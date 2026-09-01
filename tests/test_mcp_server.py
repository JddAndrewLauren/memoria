"""The MCP adapter: thin over the core, and provably so.

ADR-0002's consequence is "domain logic stays in `memoria.*`; the CLI, the
FastAPI app and the MCP server are all thin over it". The isolation test below
is what turns that from a claim into a check.

Behaviour is exercised through `server.render` and the core, and through the
SDK exactly once - `test_the_server_registers_a_read_tool` - so that an SDK
release can break one test rather than the file. The SDK renamed its server
class between 1.x and 2.x, which is not a hypothetical risk.
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest

from memoria.mcp import server
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    ReadError,
    read,
    write_normalized_records,
)
from memoria.repository import Repository

MCP_PACKAGE = Path(server.__file__).parent
REPO_ROOT = Path(__file__).resolve().parent.parent

# What the adapter is allowed to reach. An allowlist rather than a blocklist:
# a blocklist only catches the violations someone thought of, and the point is
# to catch the next one.
ALLOWED_IMPORTS = {
    "__future__",
    "argparse",
    "sys",
    "mcp",
    "memoria.mcp",       # the package's own modules
    "memoria.records",
    "memoria.repository",
    "memoria.index",      # #12: search_text calls memoria.index.search
    "memoria.ledger",      # #13: every served call is ledgered
}

FILE_OPENING_CALLS = {"open", "read_text", "read_bytes", "write_text", "write_bytes"}


def _record(**overrides):
    fields = dict(
        id="SRC-000184",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22., 1845",
        date_confidence="inferred",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=["A blue heron flew over.", "    Indented verse.\n    Second line."],
    )
    fields.update(overrides)
    return NormalizedRecord(**fields)


def _repo(tmp_path):
    write_normalized_records([_record()], tmp_path / NORMALIZED_RELATIVE_PATH)
    return Repository(root=tmp_path)


@pytest.fixture(autouse=True)
def _restore_server_repository():
    """`server._repository` is a module global; leaking it across tests would
    make them order-dependent."""
    original_repository = server._repository
    original_session_id = server._session_id
    yield
    server._repository = original_repository
    server._session_id = original_session_id


# --- the adapter reaches nothing on its own --------------------------------


def test_the_mcp_package_imports_only_the_core_and_opens_no_file_itself():
    """#11: the MCP package imports no SQLite driver and opens no evidence
    file directly.

    Implemented as an allowlist over the package's own source. What it cannot
    see, deliberately, is transitive imports through `memoria.*`: the core
    legitimately owns sqlite3, and #12 will legitimately have this server call
    `memoria.index.search`. A `sys.modules` check after import would look
    stronger and is a trap - it is order-dependent inside a shared pytest
    session, and it would start failing on correct code the day #12 lands.

    It also cannot see `__import__("sqlite3")` or a `getattr`-assembled
    attribute name, which evade the call check below by the same token. Those
    are defeatable by anyone deliberately trying; the test is a guard against
    drift, not an adversary.

    So the claim this makes is the honest one: the adapter's own source
    reaches nothing but the two core modules it is allowed to reach, and
    performs no file access of its own.
    """
    sources = sorted(MCP_PACKAGE.rglob("*.py"))
    assert sources, "no MCP package sources found - has the package moved?"

    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert any(
                    name == allowed or name.startswith(allowed + ".")
                    for allowed in ALLOWED_IMPORTS
                ), f"{path.name} imports {name}, which the adapter may not reach"


def test_the_mcp_package_performs_no_file_access_of_its_own():
    for path in sorted(MCP_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in FILE_OPENING_CALLS, (
                f"{path.name} calls {name}(): reads go through memoria.records"
            )


def test_the_adapter_declares_no_sqlite_dependency():
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in MCP_PACKAGE.rglob("*.py")
    )
    assert "sqlite3" not in text


# --- serving does not write ------------------------------------------------


def _snapshot(*roots):
    return {
        path: path.read_bytes()
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_no_read_writes_anything_under_either_root_but_the_ledger(tmp_path):
    """#11: the server never writes to the evidence repo. #13 adds the one
    intentional write: the ledger, under `sessions/**`.

    Snapshots both roots and asserts no changed bytes *and no new paths*
    outside `sessions/` - what would catch a stray `.memoria/index.db`
    appearing as a side effect of a read, which `search()` is already known
    to do on an empty corpus.
    """
    repo_root = tmp_path / "repo"
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text("raw evidence\n")
    write_normalized_records([_record()], repo_root / NORMALIZED_RELATIVE_PATH)
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "note.md").write_text("# note\n")
    repository = Repository(root=repo_root, evidence_root=evidence_root)
    server._repository = repository

    before = _snapshot(repo_root, evidence_root)
    for ref in [
        "SRC-000184",
        "SRC-000184 P1",
        "src-000184-p2",
        "docs/note.md",
        "SUB-people/bob",
        "SRC-000999",
        "FOO-1",
        "../escape",
    ]:
        try:
            server.read(ref)
        except Exception:
            pass
    after = {
        path: content
        for path, content in _snapshot(repo_root, evidence_root).items()
        if repo_root / "sessions" not in path.parents
    }

    assert set(after) == set(before), "a read created or removed a file outside sessions/"
    assert after == before, "a read changed a file's bytes"


# --- what the model sees ----------------------------------------------------


def test_the_envelope_carries_the_verbatim_text_contiguously(tmp_path):
    """The header may grow; the payload may not be touched."""
    repository = _repo(tmp_path)
    result = read(repository, "SRC-000184 P2")

    rendered = server.render(result)

    header, _, payload = rendered.partition("\n---\n")
    assert payload == result.text
    assert "original_locator: Journal I, entry dated Oct. 22." in header


def test_a_full_source_read_is_rendered_bare(tmp_path):
    """Indistinguishable from `cat`, at the surface and not just in `text`.

    It used to carry a `ref:` line and a `---`. In the first live session a
    reader saw those above the record's own frontmatter opener, read the two
    consecutive `---` lines as an empty pair, and reported the payload as
    corrupted. The envelope was correct and the report was wrong - which is
    the point: an envelope that reads as damage costs the tool the trust the
    routing hook depends on.
    """
    repository = _repo(tmp_path)
    path = tmp_path / NORMALIZED_RELATIVE_PATH / "SRC-000184.md"

    rendered = server.render(read(repository, "SRC-000184"))

    assert rendered.encode("utf-8") == path.read_bytes()


def test_a_path_read_is_rendered_bare(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("# note\n", encoding="utf-8")

    rendered = server.render(read(Repository(root=tmp_path), "docs/note.md"))

    assert rendered == "# note\n"


def test_the_tool_maps_a_core_error_onto_one_the_model_can_read(tmp_path):
    """A bare exception is reported as "Error executing tool read" with the
    reason stripped - the silent failure #11 forbids. ToolError keeps it."""
    from mcp.server.mcpserver.exceptions import ToolError

    server._repository = _repo(tmp_path)

    with pytest.raises(ToolError, match="SUB"):
        server.read("SUB-people/bob")

    with pytest.raises(ReadError):
        read(server.repository(), "SUB-people/bob")


def test_the_server_registers_a_read_tool(tmp_path):
    """The one test that touches the SDK, so a rename breaks one thing."""
    tools = asyncio.run(server.mcp.list_tools())

    (tool,) = [t for t in tools if t.name == "read"]
    assert set(tool.input_schema["properties"]) == {"ref"}
    assert tool.input_schema["required"] == ["ref"]
    assert "verbatim" in (tool.description or "")


def test_the_tool_surface_is_read_and_search_text():
    """Part 11 §25 withdrew the per-type read tools; there is no read_source.

    #12 adds exactly one more tool, search_text - not one per filter or one
    per source type.
    """
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"read", "search_text"}


# --- search_text --------------------------------------------------------


def _index(tmp_path, records):
    from memoria.index import INDEX_RELATIVE_PATH, build_index

    build_index(tmp_path / INDEX_RELATIVE_PATH, records)
    return Repository(root=tmp_path)


def test_search_text_returns_the_src_id_and_anchor_of_each_hit(tmp_path):
    repository = _index(
        tmp_path,
        [_record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])],
    )
    server._repository = repository

    rendered = server.search_text("heron")

    assert "SRC-000184" in rendered
    assert "src-000184-p1" in rendered


def test_search_text_returns_no_results_rather_than_an_empty_string(tmp_path):
    server._repository = _index(tmp_path, [_record()])

    rendered = server.search_text("nonexistentterm")

    assert rendered == "No results."


def test_search_text_over_an_unbuilt_index_returns_no_results(tmp_path):
    server._repository = Repository(root=tmp_path)

    assert server.search_text("anything") == "No results."


def test_search_text_filters_compose(tmp_path):
    from memoria.index import SearchFilters

    repository = _index(
        tmp_path,
        [
            _record(id="SRC-000001", source_type="journal", paragraphs=["A fox ran."]),
            _record(
                id="SRC-000002", source_type="editorial", paragraphs=["A fox, noted."]
            ),
        ],
    )
    server._repository = repository

    rendered = server.search_text("fox", SearchFilters(source_type="journal"))

    assert "SRC-000001" in rendered
    assert "SRC-000002" not in rendered


# --- the ledger (#13) -------------------------------------------------------


def _events(tmp_path, session_id):
    path = tmp_path / "sessions" / session_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_served_read_is_ledgered_full_source_included(tmp_path):
    """The undecorated full-source path is not an unlogged path."""
    server._repository = _repo(tmp_path)
    server._session_id = "SES-test"

    server.read("SRC-000184")

    (event,) = _events(tmp_path, "SES-test")
    assert event["tool"] == "read"
    assert event["ref"] == "SRC-000184"
    assert event["served"] == ["SRC-000184"]


def test_a_failed_read_is_not_ledgered(tmp_path):
    """Only what was served is ledgered - a ToolError supplied nothing."""
    from mcp.server.mcpserver.exceptions import ToolError

    server._repository = _repo(tmp_path)
    server._session_id = "SES-test"

    with pytest.raises(ToolError):
        server.read("SRC-000999")

    assert not (tmp_path / "sessions").exists()


def test_a_served_search_is_ledgered(tmp_path):
    server._repository = _index(
        tmp_path, [_record(paragraphs=["A blue heron flew over."])]
    )
    server._session_id = "SES-test"

    server.search_text("heron")

    (event,) = _events(tmp_path, "SES-test")
    assert event["tool"] == "search_text"
    assert event["query"] == "heron"
    assert event["served"] == ["src-000184-p1"]


def test_several_served_tool_calls_reconstruct_exactly_what_the_server_returned(tmp_path):
    """Drives real `server.read` / `server.search_text` tool calls - not
    `ledger.append_*` directly with hand-built values - against a fixture
    repo, then checks the ledger against what the server *actually*
    returned for each call, independently recomputed through the core.
    """
    from memoria.index import INDEX_RELATIVE_PATH, build_index
    from memoria.index import search as search_core
    from mcp.server.mcpserver.exceptions import ToolError

    records = [
        _record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])
    ]
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(tmp_path / INDEX_RELATIVE_PATH, records)
    repository = Repository(root=tmp_path)
    server._repository = repository
    server._session_id = "SES-test"

    full = read(repository, "SRC-000184")
    rendered_full = server.read("SRC-000184")

    paragraph = read(repository, "SRC-000184 P1")
    rendered_paragraph = server.read("SRC-000184 P1")

    hits = search_core(repository, "heron")
    rendered_search = server.search_text("heron")

    with pytest.raises(ToolError):
        server.read("SRC-000999")

    events = _events(tmp_path, "SES-test")
    assert [e["tool"] for e in events] == ["read", "read", "search_text"]

    assert events[0]["served"] == [full.citation]
    assert server.render(full) == rendered_full

    assert events[1]["served"] == [paragraph.citation]
    assert server.render(paragraph) == rendered_paragraph

    assert events[2]["served"] == [hit.anchor for hit in hits]
    assert server.render_search(hits) == rendered_search


def test_the_server_registers_a_search_text_tool():
    """The one other test that touches the SDK for this tool."""
    tools = asyncio.run(server.mcp.list_tools())

    (tool,) = [t for t in tools if t.name == "search_text"]
    assert set(tool.input_schema["properties"]) == {"query", "filters"}
    assert tool.input_schema["required"] == ["query"]
    assert "ranked" in (tool.description or "")


# --- the committed registration ---------------------------------------------


def test_mcp_json_registers_the_server_by_module_path():
    """A package rename must not silently orphan the committed registration."""
    config = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))

    entry = config["mcpServers"]["memoria"]

    assert entry["type"] == "stdio"
    assert entry["args"][:2] == ["-m", "memoria.mcp"]

    # Relative, and therefore correct in every worktree: a project server is
    # launched with the project directory as its working directory (measured,
    # not assumed - see docs/tool-surface.md).
    assert not entry["command"].startswith("/")
    assert (REPO_ROOT / entry["command"]).name == "python"

    # No ${...} expansion: `.mcp.json` does not substitute CLAUDE_PROJECT_DIR,
    # and a config referencing it is reported as a missing variable.
    assert "$" not in json.dumps(entry)

    # No env block: read(ref) resolves everything from the repository root, so
    # the committed file carries nothing machine-specific.
    assert "env" not in entry
