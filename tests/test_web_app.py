"""The FastAPI adapter: thin over the core, and provably so (#64).

Same discipline `test_mcp_server.py` already keeps for the MCP server: an
allowlist over the package's own imports, so a route calling `sqlite3` or
opening a file directly fails a test rather than drifting in unnoticed.
"""

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from memoria.index import INDEX_RELATIVE_PATH, build_index
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.web.app import create_app

WEB_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "memoria" / "web"

ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "collections.abc",
    "contextlib",
    "fastapi",
    "pydantic",
    "memoria.web",
    "memoria.records",
    "memoria.repository",
    "memoria.index",
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
        paragraphs=["A blue heron flew over.", "Second paragraph here."],
    )
    fields.update(overrides)
    return NormalizedRecord(**fields)


def _repo(tmp_path, *records):
    if records:
        write_normalized_records(list(records), tmp_path / NORMALIZED_RELATIVE_PATH)
    return Repository(root=tmp_path)


def _client(repository):
    # `with` is required for `TestClient` to run lifespan - otherwise
    # `app.state.repository` is never set and every route 500s.
    return TestClient(create_app(repository=repository)).__enter__()


# --- isolation ---------------------------------------------------------


def test_the_web_package_imports_only_the_core_and_fastapi():
    sources = sorted(WEB_PACKAGE.rglob("*.py"))
    assert sources, "no web package sources found - has the package moved?"

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


def test_the_web_package_performs_no_file_access_of_its_own():
    for path in sorted(WEB_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            assert name not in FILE_OPENING_CALLS, (
                f"{path.name} calls {name}(): reads go through memoria.records"
            )


def test_the_web_package_declares_no_sqlite_dependency():
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in WEB_PACKAGE.rglob("*.py")
    )
    assert "sqlite3" not in text


# --- list sources --------------------------------------------------------


def test_list_sources_returns_frontmatter_only(tmp_path):
    repository = _repo(tmp_path, _record())
    client = _client(repository)

    body = client.get("/api/sources").json()

    (item,) = body["items"]
    assert item["id"] == "SRC-000184"
    assert item["source_type"] == "journal"
    assert item["original_file"] == "raw/vol-01/text.txt"
    assert "paragraphs" not in item


def test_list_sources_filters_by_source_type(tmp_path):
    repository = _repo(
        tmp_path,
        _record(id="SRC-000001", source_type="journal"),
        _record(id="SRC-000002", source_type="letter"),
    )
    client = _client(repository)

    body = client.get("/api/sources", params={"source_type": "letter"}).json()

    (item,) = body["items"]
    assert item["id"] == "SRC-000002"


def test_list_sources_is_paginated(tmp_path):
    repository = _repo(
        tmp_path,
        _record(id="SRC-000001"),
        _record(id="SRC-000002"),
        _record(id="SRC-000003"),
    )
    client = _client(repository)

    body = client.get("/api/sources", params={"limit": 2, "offset": 1}).json()

    assert [item["id"] for item in body["items"]] == ["SRC-000002", "SRC-000003"]
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_list_sources_over_an_un_normalized_checkout_is_an_empty_list(tmp_path):
    """An honest empty state, not an error (#64's acceptance criteria)."""
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


# --- read one source -----------------------------------------------------


def test_read_one_source_carries_frontmatter_paragraphs_and_apparatus(tmp_path):
    repository = _repo(tmp_path, _record())
    client = _client(repository)

    body = client.get("/api/sources/SRC-000184").json()

    assert body["id"] == "SRC-000184"
    assert body["paragraphs"] == [
        {"anchor": "src-000184-p1", "text": "A blue heron flew over."},
        {"anchor": "src-000184-p2", "text": "Second paragraph here."},
    ]
    assert body["apparatus"] == []


def test_read_one_source_that_does_not_exist_is_a_404(tmp_path):
    repository = _repo(tmp_path, _record())
    client = _client(repository)

    response = client.get("/api/sources/SRC-000999")

    assert response.status_code == 404
    assert "SRC-000999" in response.json()["detail"]


def test_reading_a_source_serves_verbatim_text_not_a_summary(tmp_path):
    """§7: retrieval is a superset of grep. Paragraph text is untouched."""
    awkward = "    Indented verse,\n      deeper line.\nand back out."
    repository = _repo(tmp_path, _record(paragraphs=[awkward]))
    client = _client(repository)

    body = client.get("/api/sources/SRC-000184").json()

    assert body["paragraphs"][0]["text"] == awkward


# --- raw source ------------------------------------------------------------


def test_raw_source_serves_the_unnormalized_file_and_its_locator(tmp_path):
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text(
        "The unnormalized text.\n", encoding="utf-8"
    )
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=evidence_root)
    client = _client(repository)

    body = client.get("/api/sources/SRC-000184/raw").json()

    assert body["text"] == "The unnormalized text.\n"
    assert body["original_locator"] == "Journal I, entry dated Oct. 22."


def test_raw_source_without_an_evidence_root_is_a_404_not_a_crash(tmp_path):
    repository = _repo(tmp_path, _record())
    client = _client(repository)

    response = client.get("/api/sources/SRC-000184/raw")

    assert response.status_code == 404


def test_raw_source_with_a_missing_original_file_is_a_404(tmp_path):
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=tmp_path / "evidence")
    client = _client(repository)

    response = client.get("/api/sources/SRC-000184/raw")

    assert response.status_code == 404


# --- search ----------------------------------------------------------------


def _indexed(tmp_path, records):
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(tmp_path / INDEX_RELATIVE_PATH, records)
    return Repository(root=tmp_path)


def test_search_returns_hits_with_no_hydrated_text(tmp_path):
    """`SearchResult` carries no text (memoria.index); the route adds none.

    #64's amendment: hydration is #12's job, not this layer's, and #12's
    `search()` does not hydrate today - so search results here carry exactly
    what `memoria.index.search` returns, unmodified.
    """
    repository = _indexed(
        tmp_path, [_record(paragraphs=["A blue heron flew over the pond."])]
    )
    client = _client(repository)

    body = client.get("/api/search", params={"q": "heron"}).json()

    (result,) = body["results"]
    assert result == {
        "src_id": "SRC-000184",
        "anchor": "src-000184-p1",
        "source_type": "journal",
    }


def test_search_filters_compose(tmp_path):
    records = [
        _record(id="SRC-000001", source_type="journal", paragraphs=["A fox ran."]),
        _record(
            id="SRC-000002", source_type="editorial", paragraphs=["A fox, noted."]
        ),
    ]
    repository = _indexed(tmp_path, records)
    client = _client(repository)

    body = client.get(
        "/api/search", params={"q": "fox", "source_type": "journal"}
    ).json()

    ids = {result["src_id"] for result in body["results"]}
    assert ids == {"SRC-000001"}


def test_search_over_an_unbuilt_index_returns_no_results_not_an_error(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/search", params={"q": "anything"})

    assert response.status_code == 200
    assert response.json() == {"results": []}


# --- dependency injection --------------------------------------------------


def test_the_repository_is_resolved_once_at_lifespan(tmp_path):
    """Two requests against the same client see the same repository value -
    no route re-discovers or rebuilds it per request."""
    repository = _repo(tmp_path, _record())
    app = create_app(repository=repository)

    with TestClient(app) as client:
        client.get("/api/sources")
        assert app.state.repository is repository
        client.get("/api/sources")
        assert app.state.repository is repository
