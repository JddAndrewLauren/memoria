"""The FastAPI adapter: thin over the core, and provably so (#64).

Same discipline `test_mcp_server.py` already keeps for the MCP server: an
allowlist over the package's own imports, so a route calling `sqlite3` or
opening a file directly fails a test rather than drifting in unnoticed.
"""

import ast
import dataclasses
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoria.index import (
    SNIPPET_MATCH_END,
    SNIPPET_MATCH_START,
    SearchResult,
    build_index,
)
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    LaunchError,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import BUILTIN_SUBJECTS, Entry, entry_to_markdown, write_builtin_subjects
from memoria.web.app import create_app
from memoria.web.schemas import SearchResultOut

WEB_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "memoria" / "web"

ALLOWED_IMPORTS = {
    "__future__",
    "collections",
    "collections.abc",
    "contextlib",
    "ipaddress",
    "pathlib",
    "fastapi",
    "pydantic",
    "memoria.web",
    "memoria.records",
    "memoria.references",
    "memoria.repository",
    "memoria.index",
    "memoria.subjects",
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


def _local_client(repository):
    """A client whose peer address is a loopback address - what a real
    browser on the same machine as the server looks like to it. The
    default `TestClient` peer, `("testclient", 50000)`, is not a loopback
    address, so an ordinary `_client` already exercises the "not local"
    case #65's locality gate must refuse."""
    app = create_app(repository=repository)
    return TestClient(app, client=("127.0.0.1", 55001)).__enter__()


def _client_with_peer(repository, host):
    """A client whose peer address is exactly `host` - for probing
    `_is_local`'s edge cases (#146: `127/8` and IPv4-mapped IPv6 forms)."""
    app = create_app(repository=repository)
    return TestClient(app, client=(host, 55001)).__enter__()


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


# --- locality and reveal in editor (#65) ------------------------------------


def test_locality_reports_not_local_for_an_ordinary_client(tmp_path):
    """`TestClient`'s default peer is not a loopback address - the same
    "not local" fact a real hosted deployment sees."""
    repository = _repo(tmp_path)
    client = _client(repository)

    body = client.get("/api/locality").json()

    assert body == {"is_local": False}


def test_locality_reports_local_for_a_loopback_peer(tmp_path):
    repository = _repo(tmp_path)
    client = _local_client(repository)

    body = client.get("/api/locality").json()

    assert body == {"is_local": True}


@pytest.mark.parametrize(
    "host",
    [
        "::ffff:127.0.0.1",  # the IPv4-mapped form a dual-stack bind hands you (#146)
        "127.5.5.5",  # any address in 127/8 is loopback, not just 127.0.0.1
    ],
)
def test_locality_reports_local_for_the_rest_of_the_loopback_range(tmp_path, host):
    repository = _repo(tmp_path)
    client = _client_with_peer(repository, host)

    body = client.get("/api/locality").json()

    assert body == {"is_local": True}


@pytest.mark.parametrize("host", ["not-an-ip", ""])
def test_locality_reports_not_local_for_an_unparseable_host(tmp_path, host):
    """Fails closed: a host `_is_local` cannot even parse is not-local, the
    same as any other address that is not loopback (#146)."""
    repository = _repo(tmp_path)
    client = _client_with_peer(repository, host)

    body = client.get("/api/locality").json()

    assert body == {"is_local": False}


def test_reveal_is_refused_for_a_non_local_client_without_launching_anything(
    tmp_path, monkeypatch
):
    """The server never trusts the client's own idea of whether it is
    local - a request from a non-loopback peer is refused outright, even
    if it names a source that exists (#65's acceptance criteria: absent
    for the UI, refused for the API underneath it)."""
    monkeypatch.setattr(
        "memoria.records._launch", lambda path: pytest.fail("must not launch when refused")
    )
    repository = _repo(tmp_path, _record())
    client = _client(repository)

    response = client.post("/api/sources/SRC-000184/reveal")

    assert response.status_code == 403


def test_reveal_launches_the_original_file_for_a_local_client(tmp_path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    original = evidence_root / "raw" / "vol-01" / "text.txt"
    original.write_text("The unnormalized text.\n", encoding="utf-8")
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=evidence_root)
    launched = []
    monkeypatch.setattr("memoria.records._launch", lambda path: launched.append(path))
    client = _local_client(repository)

    response = client.post("/api/sources/SRC-000184/reveal")

    assert response.status_code == 200
    assert response.json() == {"opened": True}
    assert launched == [original]


def test_reveal_without_an_evidence_root_is_a_404_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "memoria.records._launch", lambda path: pytest.fail("must not launch")
    )
    repository = _repo(tmp_path, _record())
    client = _local_client(repository)

    response = client.post("/api/sources/SRC-000184/reveal")

    assert response.status_code == 404


def test_reveal_of_an_unknown_record_is_a_404(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "memoria.records._launch", lambda path: pytest.fail("must not launch")
    )
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=tmp_path / "evidence")
    client = _local_client(repository)

    response = client.post("/api/sources/SRC-000999/reveal")

    assert response.status_code == 404


def test_reveal_of_a_launch_that_fails_immediately_is_a_handled_error_not_opened_true(
    tmp_path, monkeypatch
):
    """#146: an opener that starts and exits right away (e.g. `xdg-open`
    with no handler registered) must not come back as `{"opened": true}` -
    the server cannot stand behind a launch it just watched fail."""
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text(
        "The unnormalized text.\n", encoding="utf-8"
    )
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=evidence_root)

    def _fail(path):
        raise LaunchError("xdg-open exited immediately with status 3")

    monkeypatch.setattr("memoria.records._launch", _fail)
    client = _local_client(repository)

    response = client.post("/api/sources/SRC-000184/reveal")

    assert response.status_code == 502
    assert response.json() != {"opened": True}


def test_reveal_with_a_missing_opener_binary_is_a_handled_error_not_a_500(
    tmp_path, monkeypatch
):
    """#146: the route handler used to catch only `ReadError` and
    `NoEvidenceRoot`, so a missing opener binary raised an uncaught
    `FileNotFoundError` and 500'd. It must come back as a real error
    response instead."""
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw" / "vol-01").mkdir(parents=True)
    (evidence_root / "raw" / "vol-01" / "text.txt").write_text(
        "The unnormalized text.\n", encoding="utf-8"
    )
    repository = _repo(tmp_path, _record())
    repository = Repository(root=repository.root, evidence_root=evidence_root)

    def _missing_opener(path):
        raise LaunchError("no opener available on this host: xdg-open")

    monkeypatch.setattr("memoria.records._launch", _missing_opener)
    client = _local_client(repository)

    response = client.post("/api/sources/SRC-000184/reveal")

    assert response.status_code == 502


# --- search ----------------------------------------------------------------


def _indexed(tmp_path, records):
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    repository = Repository(root=tmp_path)
    build_index(repository, records)
    return repository


def test_search_returns_a_snippet_and_never_the_paragraph(tmp_path):
    """A hit carries a match locator, never the evidence (#95).

    The route asks for the snippet the search dialog draws (part 19 §19.8),
    and that is all the text it ever serves: the paragraph itself arrives
    through `read(ref)` on the anchor, which reads the record file rather
    than the index's derived copy.
    """
    paragraph = (
        "A blue heron flew over the pond, and I watched it until the far bank "
        "hid it from me entirely, which took the better part of a minute."
    )
    repository = _indexed(tmp_path, [_record(paragraphs=[paragraph])])
    client = _client(repository)

    body = client.get("/api/search", params={"q": "heron"}).json()

    (result,) = body["results"]
    assert result["src_id"] == "SRC-000184"
    assert result["anchor"] == "src-000184-p1"
    assert result["source_type"] == "journal"

    # The matched term is marked, and the paragraph is not served whole.
    assert f"{SNIPPET_MATCH_START}heron{SNIPPET_MATCH_END}" in result["snippet"]
    assert paragraph not in result["snippet"]
    assert set(result) == {"src_id", "anchor", "source_type", "snippet"}


def test_every_core_search_result_field_has_a_response_field():
    """The generated-types check cannot catch a field this layer dropped.

    `SearchResultOut` enumerates its fields, so a field added to
    `index.SearchResult` is served only if someone remembers this model too -
    and `test_web_types.py` stays green either way, because the schema
    remains self-consistent, just impoverished. This is the check that does
    not (the handoff that #95 closes, item 2).
    """
    core = {field.name for field in dataclasses.fields(SearchResult)}
    served = set(SearchResultOut.model_fields)

    assert core <= served, (
        f"index.SearchResult fields not served by the web API: {core - served} - "
        "add them to memoria.web.schemas.SearchResultOut and the /search route"
    )


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


# --- subjects and entries ---------------------------------------------------


def _write_entry(tmp_path, subject_slug, entry_slug, **overrides):
    fields = dict(id=f"SUB-{subject_slug}/{entry_slug}", match_terms=[], body="")
    fields.update(overrides)
    entry = Entry(**fields)
    path = tmp_path / "subjects" / subject_slug / f"{entry_slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry_to_markdown(entry), encoding="utf-8")
    return entry


def test_list_subjects_returns_the_five_builtins_with_computed_entry_counts(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(tmp_path, "people", "bob", match_terms=["Bob", "Robert"])
    _write_entry(tmp_path, "people", "alice")
    client = _client(repository)

    body = client.get("/api/subjects").json()

    ids = {item["id"] for item in body["items"]}
    assert ids == {subject.id for subject in BUILTIN_SUBJECTS}
    people = next(item for item in body["items"] if item["id"] == "SUB-people")
    assert people["entry_count"] == 2
    other = next(item for item in body["items"] if item["id"] == "SUB-timeline")
    assert other["entry_count"] == 0


def test_list_subjects_over_an_unseeded_repository_is_an_empty_list(tmp_path):
    """No `memoria seed-subjects` run yet - honest empty state, not an
    error (#24's acceptance criteria)."""
    repository = Repository(root=tmp_path)
    client = _client(repository)

    response = client.get("/api/subjects")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_entries_returns_one_subjects_entries_with_match_terms(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(tmp_path, "people", "bob", match_terms=["Bob", "Robert"])
    _write_entry(tmp_path, "events", "the-acquisition")
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries").json()

    assert body == {
        "items": [{"id": "SUB-people/bob", "match_terms": ["Bob", "Robert"]}]
    }


def test_list_entries_for_an_unknown_subject_is_a_404(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    client = _client(repository)

    response = client.get("/api/subjects/SUB-nonexistent/entries")

    assert response.status_code == 404
    assert "SUB-nonexistent" in response.json()["detail"]


# --- serving the built ui/ client -------------------------------------------


def _fake_ui_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>the app shell</body></html>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log('hi')", encoding="utf-8")
    return dist


def test_create_app_serves_no_ui_when_no_build_exists(tmp_path, monkeypatch):
    """`create_app` still works with `npm run build` never having run - the
    API-only tests, and any test that does not care about the client, never
    need it."""
    import memoria.web.app as app_module

    monkeypatch.setattr(app_module, "_UI_DIST", tmp_path / "no-such-dist")
    client = _client(_repo(tmp_path / "repo"))

    response = client.get("/")

    assert response.status_code == 404


def test_the_built_client_is_served_at_the_root(tmp_path, monkeypatch):
    import memoria.web.app as app_module

    monkeypatch.setattr(app_module, "_UI_DIST", _fake_ui_dist(tmp_path))
    client = _client(_repo(tmp_path / "repo"))

    response = client.get("/")

    assert response.status_code == 200
    assert "the app shell" in response.text


def test_an_unmatched_client_route_falls_back_to_the_app_shell(tmp_path, monkeypatch):
    """React Router routes like `/sources/SRC-000184` have no file on disk -
    the SPA fallback (#24) serves `index.html` for them rather than 404ing."""
    import memoria.web.app as app_module

    monkeypatch.setattr(app_module, "_UI_DIST", _fake_ui_dist(tmp_path))
    client = _client(_repo(tmp_path / "repo"))

    response = client.get("/sources/SRC-000184")

    assert response.status_code == 200
    assert "the app shell" in response.text


def test_an_unmatched_api_route_is_a_404_not_the_app_shell(tmp_path, monkeypatch):
    """A typo'd or removed API endpoint must not come back 200 with HTML."""
    import memoria.web.app as app_module

    monkeypatch.setattr(app_module, "_UI_DIST", _fake_ui_dist(tmp_path))
    client = _client(_repo(tmp_path / "repo"))

    response = client.get("/api/no-such-route")

    assert response.status_code == 404
    assert "the app shell" not in response.text


def test_a_built_asset_file_is_served_from_disk(tmp_path, monkeypatch):
    import memoria.web.app as app_module

    monkeypatch.setattr(app_module, "_UI_DIST", _fake_ui_dist(tmp_path))
    client = _client(_repo(tmp_path / "repo"))

    response = client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "console.log" in response.text


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
