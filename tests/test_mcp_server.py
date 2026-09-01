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
    original = server._repository
    yield
    server._repository = original


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


def test_no_read_writes_anything_under_either_root(tmp_path):
    """#11: the server never writes to the evidence repo.

    Snapshots both roots and asserts no changed bytes *and no new paths* - the
    second half is what would catch a stray `.memoria/index.db` appearing as a
    side effect of a read, which `search()` is already known to do on an empty
    corpus.
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
    after = _snapshot(repo_root, evidence_root)

    assert set(after) == set(before), "a read created or removed a file"
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


def test_a_full_source_read_renders_the_file_and_no_repeated_metadata(tmp_path):
    repository = _repo(tmp_path)
    result = read(repository, "SRC-000184")

    rendered = server.render(result)

    assert rendered == f"ref: SRC-000184\n---\n{result.text}"


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


def test_the_tool_surface_is_one_read_tool():
    """Part 11 §25 withdrew the per-type read tools; there is no read_source."""
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"read"}


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
