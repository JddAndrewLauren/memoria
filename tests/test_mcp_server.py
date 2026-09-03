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
    Read,
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
    "json",  # #29: rendering a session's context manifest
    "sys",
    "mcp",
    "memoria.mcp",       # the package's own modules
    "memoria.records",
    "memoria.repository",
    "memoria.index",      # #12: search_text calls memoria.index.search
    "memoria.ledger",      # #13: every served call is ledgered
    "memoria.extraction",  # #17: the extraction pass's tools
    "memoria.embeddings",  # #81: the local embedder search_semantic wires in
    "memoria.audit",  # #40: the audit pass's tools
    "memoria.trace",  # #42: trace(ref), provenance composed from git and the session
    "memoria.record_extractor",  # #34: the record extractor's tools, driven by the curation skill
    "memoria.human_touched",  # #34: curation_flag, the flagging step on its own
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


def _repo_with_evidence(tmp_path):
    """A repository whose evidence root holds the original the record was
    normalized from - what a raw read serves (#113)."""
    write_normalized_records([_record()], tmp_path / NORMALIZED_RELATIVE_PATH)
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text(
        "The unnormalized text.\n", encoding="utf-8"
    )
    return Repository(root=tmp_path, evidence_root=evidence_root)


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


def test_no_read_writes_the_index_either_when_one_already_exists(tmp_path):
    """Retry item 3: the test above's repo has no index at all, so it never
    exercises `overlay_for_anchor`'s `connect()` (mkdir + DDL + commit) path
    the curated overlay (#20) added. This one pre-builds an index and
    asserts a decorated read leaves it byte-identical."""
    from memoria.index import build_index

    repo_root = tmp_path / "repo"
    record = _record()
    write_normalized_records([record], repo_root / NORMALIZED_RELATIVE_PATH)
    repository = Repository(root=repo_root)
    build_index(repository, [record])
    server._repository = repository

    before = _snapshot(repo_root)
    server.read("SRC-000184 P1")
    after = {
        path: content
        for path, content in _snapshot(repo_root).items()
        if repo_root / "sessions" not in path.parents
    }

    assert set(after) == set(before), "a read created or removed a file outside sessions/"
    assert after == before, "a read changed a file's bytes"


# --- what the model sees ----------------------------------------------------


def test_the_envelope_carries_the_verbatim_text_contiguously(tmp_path):
    """The header may grow, and the overlay (#20) now follows the payload
    behind its own delimiter - but the payload itself may not be touched,
    and must appear contiguously between the two. Split from the end for
    the text/overlay boundary and from the start for the header/text one -
    `render`'s own docstring names why."""
    repository = _repo(tmp_path)
    result = read(repository, "SRC-000184 P2")

    rendered = server.render(result)

    header, _, rest = rendered.partition("\n---\n")
    payload, _, overlay = rest.rpartition("\n---\n")
    assert payload == result.text
    assert "original_locator: Journal I, entry dated Oct. 22." in header
    assert overlay == server.render_overlay(result.overlay)


def test_a_paragraph_containing_its_own_delimiter_line_still_splits_correctly(
    tmp_path,
):
    """AC 4: `render_overlay`'s output never contains a bare `---` line, so
    the *last* delimiter is always the true text/overlay boundary - even
    when the paragraph text has its own `---` line in the middle, the exact
    shape that made a naive first-delimiter split ambiguous."""
    write_normalized_records(
        [_record(paragraphs=["Above.\n---\nBelow.", "Unrelated."])],
        tmp_path / NORMALIZED_RELATIVE_PATH,
    )
    result = read(Repository(root=tmp_path), "SRC-000184 P1")

    rendered = server.render(result)

    header, _, rest = rendered.partition("\n---\n")
    payload, _, overlay = rest.rpartition("\n---\n")
    assert payload == result.text == "Above.\n---\nBelow."
    assert overlay == server.render_overlay(result.overlay)


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


def test_a_raw_read_is_rendered_bare(tmp_path):
    """The pre-normalization original, indistinguishable from `cat` at the
    surface - same contract as the full-source read (#113)."""
    rendered = server.render(read(_repo_with_evidence(tmp_path), "SRC-000184", raw=True))

    assert rendered == "The unnormalized text.\n"


def test_a_path_read_is_rendered_bare(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("# note\n", encoding="utf-8")

    rendered = server.render(read(Repository(root=tmp_path), "docs/note.md"))

    assert rendered == "# note\n"


def test_a_session_reads_context_manifest_is_appended_after_the_transcript(tmp_path):
    """#29: a session's manifest rides the same appended-after-the-text
    convention as the curated overlay (#20), a third `---`-delimited
    block, never mixed into `text` itself."""
    manifest = {"session_id": "SES-test", "records_loaded": [{"ref": "SRC-000184", "tokens": 6}]}
    result = Read(
        ref="SES-test",
        citation="SES-test",
        text="## T001 — Author\n\nHello?\n",
        context_manifest=manifest,
    )

    rendered = server.render(result)

    text_part, _, manifest_part = rendered.partition("\n---\n")
    assert text_part == result.text
    assert json.loads(manifest_part) == manifest


def test_a_turn_read_with_no_manifest_is_rendered_bare(tmp_path):
    result = Read(ref="SES-test#T001", citation="SES-test#T001", text="Hello?")

    assert server.render(result) == "Hello?"


def test_a_stale_index_does_not_surface_as_a_stripped_tool_error(tmp_path):
    """Retry item 1: this server's `read` tool catches only `(ReadError,
    NoEvidenceRoot)` - if `IndexSchemaError`/`sqlite3.Error` ever escaped
    `records.read`, the model would see "Error executing tool read" with
    the reason stripped, the silent-failure shape #11 forbids. They don't:
    `memoria.index.overlay_for_anchor` degrades to `None` instead, so the
    tool call succeeds and still serves the paragraph."""
    import sqlite3

    from memoria.index import INDEX_RELATIVE_PATH, build_index

    repository = _repo(tmp_path)
    build_index(repository, [_record()])
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("DROP TABLE paragraphs")
    con.execute(
        "CREATE TABLE paragraphs("
        "anchor TEXT PRIMARY KEY, src_id TEXT, source_type TEXT, "
        "event_date TEXT, recorded_date TEXT, contemporaneous INTEGER"
        ")"
    )
    con.commit()
    con.close()
    server._repository = repository

    rendered = server.read("SRC-000184 P1")

    assert "A blue heron flew over." in rendered
    assert "entry links" not in rendered


def test_the_tool_maps_a_core_error_onto_one_the_model_can_read(tmp_path):
    """A bare exception is reported as "Error executing tool read" with the
    reason stripped - the silent failure #11 forbids. ToolError keeps it."""
    from mcp.server.mcpserver.exceptions import ToolError

    server._repository = _repo(tmp_path)

    with pytest.raises(ToolError, match="SUB"):
        server.read("SUB-people/bob")

    with pytest.raises(ReadError):
        read(server.repository(), "SUB-people/bob")


def test_a_raw_read_without_an_evidence_root_maps_to_the_named_tool_error(tmp_path):
    """`NoEvidenceRoot` reaches the model as a `ToolError` too (#113) - the
    same named refusal every other evidence read gives, not a second failure
    shape it has to learn, and nothing else on the surface changes."""
    from mcp.server.mcpserver.exceptions import ToolError

    server._repository = _repo(tmp_path)

    with pytest.raises(ToolError, match="MEMORIA_EVIDENCE_ROOT"):
        server.read("SRC-000184", raw=True)


def test_the_server_registers_a_read_tool(tmp_path):
    """The one test that touches the SDK, so a rename breaks one thing."""
    tools = asyncio.run(server.mcp.list_tools())

    (tool,) = [t for t in tools if t.name == "read"]
    assert set(tool.input_schema["properties"]) == {"ref", "raw"}
    assert tool.input_schema["required"] == ["ref"]
    assert "verbatim" in (tool.description or "")


def test_the_tool_surface_is_the_read_tools_and_the_extraction_tools():
    """Part 11 §25 withdrew the per-type read tools; there is no read_source.

    #12 adds exactly one more read tool, search_text - not one per filter or
    one per source type. #81 adds search_semantic, the nearest-neighbour half
    beside it. #74 adds search_global, the one global tool over the
    extraction's clusters. #17 adds the extraction pass's tools, which are a
    second class on the same server: they write, and they are driven by the
    `extraction` skill rather than reached for by a writing session. #40 adds
    a third class of the same shape, the audit's tools - driven by an
    explicit on-demand request, never by a skill running on its own. #42
    adds trace, the one provenance tool part 11 §26 names - a read of what
    git and the session records already hold, storing nothing. #34 adds the
    record extractor's tools - the Curator's other half (part 08 §13),
    driven by the `curation` skill after a session: each one a durable
    record that commits, never a read.

    Pinned as an exact set, so a tool added without a decision fails here.
    """
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {
        "read",
        "search_text",
        "search_semantic",
        "search_global",
        "trace",
        "extraction_brief",
        "extraction_next_paragraphs",
        "extraction_record",
        "extraction_derive",
        "extraction_next_summary",
        "extraction_record_summary",
        "extraction_status",
        "extraction_finish",
        "extraction_candidates",
        "extraction_unplaced_forms",
        "extraction_cluster",
        "extraction_promote_candidate",
        "extraction_promote_cluster",
        "audit_pending",
        "audit_record",
        "curation_status",
        "record_decision",
        "record_question",
        "record_statement",
        "revise_statement",
        "curation_flag",
    }


# --- search_text --------------------------------------------------------


def _index(tmp_path, records):
    from memoria.index import build_index

    repository = Repository(root=tmp_path)
    build_index(repository, records)
    return repository


def test_search_text_returns_the_src_id_and_anchor_of_each_hit(tmp_path):
    repository = _index(
        tmp_path,
        [_record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])],
    )
    server._repository = repository

    rendered = server.search_text("heron")

    assert "SRC-000184" in rendered
    assert "src-000184-p1" in rendered


def test_search_text_serves_no_snippet_and_ledgers_none(tmp_path):
    """The snippet is the web adapter's, not the model's (#95).

    `search()` can compute one, and this tool does not ask: the model gets
    identifiers and reads evidence through `read(ref)`, so a search over an
    unbounded result set can never dump the corpus into the context. What is
    ledgered stays anchors, which is what keeps `served` meaning supplied.
    """
    from memoria.index import SNIPPET_MATCH_END, SNIPPET_MATCH_START
    from memoria.ledger import event_path

    repository = _index(
        tmp_path,
        [_record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])],
    )
    server._repository = repository
    server._session_id = "SES-test"

    rendered = server.search_text("heron")

    assert SNIPPET_MATCH_START not in rendered
    assert SNIPPET_MATCH_END not in rendered
    assert "flew over" not in rendered

    (line,) = (
        event_path(repository, "SES-test").read_text(encoding="utf-8").splitlines()
    )
    event = json.loads(line)
    assert event["served"] == ["src-000184-p1"]
    assert "snippet" not in line


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


def test_search_text_answers_messages_from_x_to_y_with_the_header_filters_alone(
    tmp_path,
):
    """#111: the M1 gate walk on #15 - "how many messages did Dave Perrino
    send to Diana Scholtes" - fell back to Bash because `search_text` could
    not see the `from`/`to` header fields at all. This is the same shape
    answered by `search_text` alone: three email records, a query that
    matches every body, both header filters, and exactly the one record's
    anchor comes back."""
    from memoria.index import SearchFilters

    repository = _index(
        tmp_path,
        [
            _record(
                id="SRC-000003",
                paragraphs=["Perrino wrote to Scholtes about the pond."],
                email_from="Dave Perrino <dperrino@example.com>",
                email_to="Diana Scholtes <dscholtes@example.com>",
            ),
            _record(
                id="SRC-000004",
                paragraphs=["Perrino wrote to Crandall about the pond."],
                email_from="Dave Perrino <dperrino@example.com>",
                email_to="Sean Crandall <scrandall@example.com>",
            ),
            _record(
                id="SRC-000005",
                paragraphs=["Semperger wrote to Scholtes about the pond."],
                email_from="Cara Semperger <csemperger@example.com>",
                email_to="Diana Scholtes <dscholtes@example.com>",
            ),
        ],
    )
    server._repository = repository

    rendered = server.search_text(
        "pond", SearchFilters(from_="perrino", to="scholtes")
    )

    assert "SRC-000003" in rendered
    assert "SRC-000004" not in rendered
    assert "SRC-000005" not in rendered


def test_search_text_ledgers_the_header_filters_exactly_as_the_existing_four(
    tmp_path,
):
    from memoria.index import SearchFilters
    from memoria.ledger import event_path

    repository = _index(
        tmp_path,
        [
            _record(
                id="SRC-000006",
                paragraphs=["Perrino wrote to Scholtes about the pond."],
                email_from="Dave Perrino <dperrino@example.com>",
                email_to="Diana Scholtes <dscholtes@example.com>",
            )
        ],
    )
    server._repository = repository
    server._session_id = "SES-test"

    server.search_text("pond", SearchFilters(from_="perrino", to="scholtes"))

    (line,) = (
        event_path(repository, "SES-test").read_text(encoding="utf-8").splitlines()
    )
    event = json.loads(line)
    assert event["filters"]["from_"] == "perrino"
    assert event["filters"]["to"] == "scholtes"


# --- search_semantic (#81, ADR-0007) -----------------------------------------


def _basis_vector(index, dim=384):
    """A unit vector along axis ``index`` - see ``tests/test_index.py``'s
    version of the same helper for why."""
    vector = [0.0] * dim
    vector[index % dim] = 1.0
    return vector


def _semantic_index(tmp_path, records, vectors):
    """Like ``_index``, but also populates the vector table from a
    caller-supplied ``{text: vector}`` mapping - the fake ``EmbedFn`` this
    also returns, for ``monkeypatch.setattr(server, "default_embed_fn",
    ...)`` to stand in for the real one (never exercised by this file: it
    would need network)."""
    from memoria.index import build_index

    repository = Repository(root=tmp_path)

    def embed_fn(texts):
        return [vectors[text] for text in texts]

    build_index(repository, records, embed_fn=embed_fn)
    return repository, embed_fn


def test_search_semantic_returns_the_src_id_and_anchor_of_each_hit(tmp_path, monkeypatch):
    records = [
        _record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])
    ]
    repository, embed_fn = _semantic_index(
        tmp_path,
        records,
        {
            "A blue heron flew over.": _basis_vector(0),
            "Nothing to do with birds.": _basis_vector(1),
            "a wading bird by the water": _basis_vector(0),
        },
    )
    server._repository = repository
    monkeypatch.setattr(server, "default_embed_fn", embed_fn)

    rendered = server.search_semantic("a wading bird by the water")

    assert "SRC-000184" in rendered
    assert "src-000184-p1" in rendered


def test_search_semantic_carries_a_scope_line_naming_what_was_embedded(
    tmp_path, monkeypatch
):
    """§33.1: the one place a session can say what the semantic index
    covered, since a nearest-neighbour hit says nothing about its own
    recall on its own."""
    records = [_record(paragraphs=["A blue heron flew over."])]
    repository, embed_fn = _semantic_index(
        tmp_path,
        records,
        {"A blue heron flew over.": _basis_vector(0), "heron": _basis_vector(0)},
    )
    server._repository = repository
    monkeypatch.setattr(server, "default_embed_fn", embed_fn)

    rendered = server.search_semantic("heron")

    assert "embedded 1 paragraph" in rendered
    assert "1 semantic hit" in rendered


def test_search_semantic_over_an_unbuilt_index_never_calls_the_embedder(
    tmp_path, monkeypatch
):
    from memoria.embeddings import EMBEDDING_MODEL_NAME

    server._repository = Repository(root=tmp_path)

    def _must_not_run(texts):
        raise AssertionError("embed_fn must not run against an unbuilt index")

    monkeypatch.setattr(server, "default_embed_fn", _must_not_run)

    rendered = server.search_semantic("anything")

    assert rendered == (
        f"embedded 0 paragraphs with {EMBEDDING_MODEL_NAME}; "
        "filters: none; 0 semantic hits"
    )


def test_search_semantic_is_ledgered_with_its_own_tool_name(tmp_path, monkeypatch):
    from memoria.ledger import event_path

    records = [_record(paragraphs=["A blue heron flew over."])]
    repository, embed_fn = _semantic_index(
        tmp_path,
        records,
        {"A blue heron flew over.": _basis_vector(0), "heron": _basis_vector(0)},
    )
    server._repository = repository
    server._session_id = "SES-test"
    monkeypatch.setattr(server, "default_embed_fn", embed_fn)

    server.search_semantic("heron")

    (line,) = (
        event_path(repository, "SES-test").read_text(encoding="utf-8").splitlines()
    )
    event = json.loads(line)
    assert event["tool"] == "search_semantic"
    assert event["served"] == ["src-000184-p1"]


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


def test_a_served_raw_read_is_ledgered_with_its_citation_marked_raw(tmp_path):
    """The raw read is ledgered like any other, and the served citation
    names it as the original rather than the record (#113)."""
    server._repository = _repo_with_evidence(tmp_path)
    server._session_id = "SES-test"

    server.read("SRC-000184", raw=True)

    (event,) = _events(tmp_path, "SES-test")
    assert event["tool"] == "read"
    assert event["ref"] == "SRC-000184"
    assert event["served"] == ["SRC-000184 raw"]


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
    from memoria.index import build_index
    from memoria.index import search as search_core
    from mcp.server.mcpserver.exceptions import ToolError

    records = [
        _record(paragraphs=["A blue heron flew over.", "Nothing to do with birds."])
    ]
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    repository = Repository(root=tmp_path)
    build_index(repository, records)
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
