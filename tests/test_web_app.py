"""The FastAPI adapter: thin over the core, and provably so (#64).

Same discipline `test_mcp_server.py` already keeps for the MCP server: an
allowlist over the package's own imports, so a route calling `sqlite3` or
opening a file directly fails a test rather than drifting in unnoticed.
"""

import ast
import dataclasses
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoria.index import (
    SNIPPET_MATCH_END,
    SNIPPET_MATCH_START,
    SearchResult,
    build_index,
    compute_appearances,
    exclude,
    pin,
)
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    LaunchError,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import (
    serve_entry,
    BUILTIN_SUBJECTS,
    Entry,
    OverlayAct,
    entry_to_markdown,
    write_builtin_subjects,
)
from memoria.web.app import create_app
from memoria.web.schemas import SearchResultOut
from memoria.write import Actor

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
    # #26: the web is an adapter over the write path as well as the read
    # side. It shapes `memoria.write`'s outcomes - a stale token becomes a
    # 409, an unattributed actor a 500 - and never writes anything itself;
    # the two tests below still hold, so a route that opened a file or
    # built a path of its own would fail one of them.
    "memoria.write",
    # #43: the Section and Review surfaces. Both are compositions over the
    # core (`memoria.section`, `memoria.review`); the adapter shapes them
    # and maps `ManuscriptError` to a 404, the same way it maps `ReadError`.
    "memoria.manuscript",
    "memoria.review",
    "memoria.section",
    # #61: the supplied-context surface, a projection of the session
    # ledgers composed in the core; the adapter shapes it and nothing else.
    "memoria.supplied_context",
    # The ingestion surface (ADR-0009): a derived, model-free status the
    # core computes and two local-only runs the adapter forwards to it. The
    # adapter shapes the status and maps the runs' outcomes - a held lock
    # becomes a 409, a missing corpus a 404 - and computes no state, opens
    # no database and touches no file itself; the two tests below still
    # hold.
    "memoria.ingestion",
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


def test_list_sources_over_an_un_normalized_checkout_says_it_is_not_built(tmp_path):
    """An honest empty state, not an error (#64's acceptance criteria) - and
    since #157 one that says which empty it is, so the client can name the
    command to run rather than guess."""
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
        "is_built": False,
    }


def test_list_sources_over_a_normalized_corpus_that_holds_no_records_says_it_is_built(
    tmp_path,
):
    """The other half of #157: `memoria normalize` ran and produced nothing.

    Indistinguishable from the test above without the flag - both are an
    empty `items` - and a different thing to tell the author.
    """
    (tmp_path / NORMALIZED_RELATIVE_PATH).mkdir(parents=True)
    client = _client(Repository(root=tmp_path))

    body = client.get("/api/sources").json()

    assert body["items"] == []
    assert body["is_built"] is True


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


def test_search_over_an_unbuilt_index_says_the_index_is_not_built(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/search", params={"q": "anything"})

    assert response.status_code == 200
    assert response.json() == {"results": [], "is_built": False}


def test_search_over_a_built_index_with_no_matches_says_the_index_is_built(tmp_path):
    """"Never indexed" and "nothing matched" are the same empty list and
    different facts (#157)."""
    repository = _indexed(tmp_path, [_record()])
    client = _client(repository)

    body = client.get(
        "/api/search", params={"q": "wordthatappearsnowhere"}
    ).json()

    assert body["results"] == []
    assert body["is_built"] is True


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


def test_list_subjects_over_an_unseeded_repository_says_it_is_not_seeded(tmp_path):
    """No `memoria seed-subjects` run yet - honest empty state, not an
    error (#24's acceptance criteria), and one that says so (#157)."""
    repository = Repository(root=tmp_path)
    client = _client(repository)

    response = client.get("/api/subjects")

    assert response.status_code == 200
    assert response.json() == {"items": [], "is_built": False}


def test_list_subjects_over_a_seeded_repository_says_it_is_built(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    client = _client(repository)

    body = client.get("/api/subjects").json()

    assert body["is_built"] is True


def test_list_entries_carries_no_build_signal(tmp_path):
    """A subject that exists with no entries is genuinely empty - there is
    no third state, so `EntryListResponse` carries no flag (#157). Pinned so
    the omission reads as a decision rather than an oversight."""
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    client = _client(repository)

    body = client.get("/api/subjects/SUB-timeline/entries").json()

    assert body == {"items": []}


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


# --- read one entry (#64's third subject read, built in #148 and #157) -----


def test_read_one_entry_serves_its_id_match_terms_statements_and_overlay(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(
        tmp_path,
        "people",
        "bob",
        match_terms=["Bob", "Robert"],
        body="Bob kept the ledger.",
        overlay=[
            OverlayAct(
                anchor="src-000184-p17",
                action="pin",
                actor_name="A Person",
                actor_email="person@example.com",
                at="2026-09-02T00:00:00Z",
            )
        ],
    )
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob").json()

    assert body["id"] == "SUB-people/bob"
    assert body["match_terms"] == ["Bob", "Robert"]
    assert body["statements"] == [{"badge": None, "text": "Bob kept the ledger."}]
    assert body["overlay"] == [
        {
            "anchor": "src-000184-p17",
            "action": "pin",
            "actor_name": "A Person",
            "at": "2026-09-02T00:00:00Z",
        }
    ]
    # Opaque, but it has to be *there*: it is what a match-term write
    # presents back, and an entry served without one cannot be edited.
    assert body["token"]


def test_read_one_entry_serves_the_actors_name_but_never_their_address(tmp_path):
    """Part 06 §8.3 requires the overlay to be attributable where it is
    rendered, and #26's entry view renders it - so the name crosses. The
    address does not: ADR-0002 forbids assuming the browser and the
    repository share a machine, and no rendering needs it."""
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(
        tmp_path,
        "people",
        "bob",
        overlay=[
            OverlayAct(
                anchor="src-000184-p17",
                action="exclude",
                actor_name="A Person",
                actor_email="person@example.com",
                at="2026-09-02T00:00:00Z",
            )
        ],
    )
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob").json()

    assert body["overlay"][0]["actor_name"] == "A Person"
    assert "actor_email" not in body["overlay"][0]
    assert "person@example.com" not in client.get(
        "/api/subjects/SUB-people/entries/bob"
    ).text


def test_read_one_entry_marks_author_testimony_with_a_null_badge(tmp_path):
    """The absence of a badge *is* the attribution (part 06 §9.5), so it is
    a null field rather than an omitted one - and a badged statement arrives
    with its prefix stripped and the badge named."""
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(
        tmp_path,
        "people",
        "bob",
        body="Bob kept the ledger.\n\n[inferred] He may have kept two.",
    )
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob").json()

    assert body["statements"] == [
        {"badge": None, "text": "Bob kept the ledger."},
        {"badge": "inferred", "text": "He may have kept two."},
    ]


def test_read_one_entry_serves_neither_extra_nor_the_raw_body(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(
        tmp_path,
        "people",
        "bob",
        body="Bob kept the ledger.",
        extra={"a_key_this_module_does_not_model": "kept on disk, not published"},
    )
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob").json()

    assert "extra" not in body
    assert "body" not in body


def test_read_one_entry_resolves_a_file_that_has_been_renamed(tmp_path):
    """#16's stable `SUB-x/y` IDs survive a rename on disk, and this route
    inherits that from `load_entry` rather than repeating it."""
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(tmp_path, "people", "bob", body="Bob kept the ledger.")
    (tmp_path / "subjects" / "people" / "bob.md").rename(
        tmp_path / "subjects" / "people" / "robert.md"
    )
    client = _client(repository)

    response = client.get("/api/subjects/SUB-people/entries/bob")

    assert response.status_code == 200
    assert response.json()["id"] == "SUB-people/bob"


def test_read_one_entry_for_an_unknown_subject_is_a_404(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    client = _client(repository)

    response = client.get("/api/subjects/SUB-nonexistent/entries/bob")

    assert response.status_code == 404
    assert "SUB-nonexistent" in response.json()["detail"]


def test_read_one_entry_over_an_unseeded_repository_is_a_404_not_a_crash(tmp_path):
    """No `memoria seed-subjects` run yet, and no `subjects/` directory at
    all - the honest-empty-state discipline #64 gives every other read,
    landing here as a 404 rather than an unhandled exception."""
    repository = Repository(root=tmp_path)
    client = _client(repository)

    response = client.get("/api/subjects/SUB-people/entries/bob")

    assert response.status_code == 404


def test_read_one_entry_for_an_unknown_entry_is_a_404(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(tmp_path, "people", "bob")
    client = _client(repository)

    response = client.get("/api/subjects/SUB-people/entries/nobody")

    assert response.status_code == 404
    assert "nobody" in response.json()["detail"]


def test_read_one_entry_serves_more_than_the_generic_reference_read(tmp_path):
    """The two reads are not collapsible (#157).

    `/api/read?ref=SUB-x/y` is the slide-over panel's read: the entry's raw
    text, with `record`/`paragraph`/`overlay` all null and no match terms and
    no badges. This test is what stops a later reader deleting one of them.
    """
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _write_entry(
        tmp_path,
        "people",
        "bob",
        match_terms=["Bob"],
        body="[source] Bob kept the ledger.",
    )
    client = _client(repository)

    citation = client.get("/api/read", params={"ref": "SUB-people/bob"}).json()
    entry = client.get("/api/subjects/SUB-people/entries/bob").json()

    assert citation["record"] is None
    assert citation["paragraph"] is None
    assert citation["overlay"] is None
    assert "match_terms" not in citation
    assert "statements" not in citation

    assert entry["match_terms"] == ["Bob"]
    assert entry["statements"] == [{"badge": "source", "text": "Bob kept the ledger."}]


def _derived_session(repository, session_id, turns):
    """A derived transcript with one ``## Tnnn`` block per ``(role, text)``."""
    import json as _json

    from memoria.sessions import derive_session

    entries, parent = [], None
    for number, (role, text) in enumerate(turns, start=1):
        uuid = f"u{number}"
        entries.append({
            "uuid": uuid, "parentUuid": parent, "type": role,
            "timestamp": f"2026-09-12T14:{30 + number:02d}:00+00:00",
            "sessionId": "claude-code-session-uuid",
            "message": {"role": role, "content": text},
        })
        parent = uuid
    jsonl_path = repository.root / "session.jsonl"
    jsonl_path.write_text("\n".join(_json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    derive_session(repository, session_id, jsonl_path)


def test_read_serves_one_transcript_turn_for_a_decisions_citation(tmp_path):
    """#34: a decision cites `SES-...#T002`, and the Section view's chip opens
    the panel on that turn - so the panel's read serves it, verbatim, with
    no record and no overlay. A bare session is still not citable here."""
    repository = Repository(root=tmp_path)
    turn = "We should decide this now. Keep Bob's knowledge ambiguous until chapter 9. Nothing else changes."
    _derived_session(repository, "SES-20260912-1432", [("user", "Where were we?"), ("user", turn)])
    client = _client(repository)

    response = client.get("/api/read", params={"ref": "SES-20260912-1432#T002"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == turn
    assert body["citation"] == "SES-20260912-1432#T002"
    assert body["record"] is None and body["overlay"] is None and body["anchor"] is None

    bare = client.get("/api/read", params={"ref": "SES-20260912-1432"})
    assert bare.status_code == 404 and "SES-...#T turns" in bare.json()["detail"]
    missing = client.get("/api/read", params={"ref": "SES-20260912-1432#T009"})
    assert missing.status_code == 404 and "no T009" in missing.json()["detail"]


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


# --- the entry view's index reads, and its one write (#26) -------------------


AUTHOR = Actor(name="Author", email="author@memoria.test")


def _entry_repo(tmp_path, records=(), entries=()):
    """A real git repository with subjects seeded, entries on disk and an
    index built - what the entry view reads over.

    Real git, because #26's write commits (ADR-0003 decision 2) and a fake
    repository would exercise everything except that.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    for key, value in (("user.name", "Local Author"), ("user.email", "local@memoria.test")):
        subprocess.run(
            ["git", "config", key, value], cwd=tmp_path, check=True, capture_output=True
        )
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    for subject_slug, entry_slug, overrides in entries:
        _write_entry(tmp_path, subject_slug, entry_slug, **overrides)
    if records:
        write_normalized_records(list(records), tmp_path / NORMALIZED_RELATIVE_PATH)
        build_index(repository, list(records))
        compute_appearances(repository)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True
    )
    return repository


def _bob_repo(tmp_path, **overrides):
    record = _record(
        id="SRC-000184",
        paragraphs=["Bob called on July 17.", "Nothing about anyone here."],
    )
    return record, _entry_repo(
        tmp_path,
        records=[record],
        entries=[("people", "bob", {"match_terms": ["Bob"], **overrides})],
    )


def test_the_gathered_set_serves_the_anchors_the_pass_matched(tmp_path):
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob/gathered").json()

    assert [item["anchor"] for item in body["items"]] == ["src-000184-p1"]
    assert body["items"][0]["src_id"] == "SRC-000184"
    assert body["is_built"] is True


def test_a_pinned_anchor_is_marked_and_attributed(tmp_path):
    """Part 06 §8.3's overlay is attributable, and #26 renders it - a row
    marked "pinned" with no account of who pinned it is half an act."""
    _, repository = _bob_repo(tmp_path)
    pin(repository, "SUB-people/bob", "src-000184-p2", AUTHOR)
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob/gathered").json()

    pinned = [item for item in body["items"] if item["anchor"] == "src-000184-p2"]
    assert pinned and pinned[0]["pinned"] is True
    assert pinned[0]["overlay_action"] == "pin"
    assert pinned[0]["actor_name"] == "Author"
    assert pinned[0]["at"]


def test_an_excluded_anchor_is_absent_from_the_set_but_still_accounted_for(tmp_path):
    """`gather` drops it, which is correct; serving only the list would show
    a shorter set with no reason for it, so the act is served alongside."""
    _, repository = _bob_repo(tmp_path)
    exclude(repository, "SUB-people/bob", "src-000184-p1", AUTHOR)
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob/gathered").json()

    assert [item["anchor"] for item in body["items"]] == []
    assert body["excluded"] == [
        {
            "anchor": "src-000184-p1",
            "action": "exclude",
            "actor_name": "Author",
            "at": body["excluded"][0]["at"],
        }
    ]


def test_an_unbuilt_index_says_so_rather_than_serving_a_bare_empty_set(tmp_path):
    """An entry with an empty gathered set is a valid state (part 06 §8.2);
    a corpus that was never indexed is a different fact, and they are the
    same empty list without the flag (#157)."""
    repository = _entry_repo(tmp_path, entries=[("people", "bob", {"match_terms": ["Bob"]})])
    client = _client(repository)

    body = client.get("/api/subjects/SUB-people/entries/bob/gathered").json()

    assert body["items"] == []
    assert body["is_built"] is False


def test_appearances_are_served_from_their_own_route_never_the_gathered_set(tmp_path):
    """Part 06 §8.11's separation, at the API boundary: a gathered set is
    evidence to write from, appearances are prose already written."""
    book = _record(
        id="SRC-000900", source_type="book", paragraphs=["Bob is barely in this chapter."]
    )
    evidence = _record(id="SRC-000184", paragraphs=["Bob called on July 17."])
    repository = _entry_repo(
        tmp_path,
        records=[book, evidence],
        entries=[("people", "bob", {"match_terms": ["Bob"]})],
    )
    client = _client(repository)

    appearances = client.get("/api/subjects/SUB-people/entries/bob/appearances").json()
    gathered = client.get("/api/subjects/SUB-people/entries/bob/gathered").json()

    assert [item["anchor"] for item in appearances["items"]] == ["src-000900-p1"]
    assert appearances["items"][0]["note"]
    assert appearances["engine_supported"] is True
    assert [item["anchor"] for item in gathered["items"]] == ["src-000184-p1"]
    assert "src-000900-p1" not in {item["anchor"] for item in gathered["items"]}


def test_a_theme_reports_that_its_appearances_engine_does_not_exist_yet(tmp_path):
    """Not an empty list. Themes and Arcs cannot be matched against
    manuscript prose at all until the audit at M5 (part 06 §8.11), and a
    surface told only "no appearances" would say the archive is silent when
    nothing has looked."""
    repository = _entry_repo(
        tmp_path, entries=[("themes", "control", {"match_terms": ["SUB-people/bob"]})]
    )
    client = _client(repository)

    body = client.get("/api/subjects/SUB-themes/entries/control/appearances").json()

    assert body["items"] == []
    assert body["engine_supported"] is False


@pytest.mark.parametrize("suffix", ["", "/gathered", "/appearances"])
def test_an_unknown_entry_is_a_404_on_every_entry_read(tmp_path, suffix):
    repository = _entry_repo(tmp_path, entries=[("people", "bob", {})])
    client = _client(repository)

    assert client.get(f"/api/subjects/SUB-people/entries/nobody{suffix}").status_code == 404


def test_editing_match_terms_writes_them_and_serves_a_fresh_token(tmp_path):
    """The author's first durable write. The new token is served because the
    write has just invalidated the one the client presented, and the editor
    is still open over the file."""
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)
    served = client.get("/api/subjects/SUB-people/entries/bob").json()

    response = client.put(
        "/api/subjects/SUB-people/entries/bob/match-terms",
        json={"token": served["token"], "match_terms": ["Bob", "Robert"]},
    )

    assert response.status_code == 200
    assert response.json()["match_terms"] == ["Bob", "Robert"]
    assert response.json()["token"] != served["token"]
    assert client.get("/api/subjects/SUB-people/entries/bob").json()["match_terms"] == [
        "Bob",
        "Robert",
    ]


def test_a_match_term_write_against_a_file_changed_underneath_is_a_409(tmp_path):
    """#26's fifth acceptance criterion, over HTTP: entry files are editable
    in Obsidian too, so the write is checked against the file the client
    read - and a rejection is total, never partial."""
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)
    served = client.get("/api/subjects/SUB-people/entries/bob").json()

    path = tmp_path / "subjects" / "people" / "bob.md"
    obsidian = path.read_text(encoding="utf-8").replace("- Bob", "- Bobby")
    path.write_text(obsidian, encoding="utf-8")

    response = client.put(
        "/api/subjects/SUB-people/entries/bob/match-terms",
        json={"token": served["token"], "match_terms": ["Robert"]},
    )

    assert response.status_code == 409
    assert "subjects/people/bob.md" in response.json()["detail"]
    assert path.read_text(encoding="utf-8") == obsidian


def test_a_409_carries_neither_the_current_content_nor_a_fresh_token(tmp_path):
    """ADR-0003 decision 5: the rejection names the file and nothing else.
    Returning the content would put a second copy of the read inside the
    write endpoint, and #64 already builds that read."""
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)
    served = client.get("/api/subjects/SUB-people/entries/bob").json()
    path = tmp_path / "subjects" / "people" / "bob.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nEdited elsewhere.\n", encoding="utf-8")

    body = client.put(
        "/api/subjects/SUB-people/entries/bob/match-terms",
        json={"token": served["token"], "match_terms": ["Robert"]},
    ).json()

    assert set(body) == {"detail"}
    assert "token" not in body["detail"].lower()


def test_a_malformed_match_term_is_a_400_and_writes_nothing(tmp_path):
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)
    served = client.get("/api/subjects/SUB-people/entries/bob").json()
    path = tmp_path / "subjects" / "people" / "bob.md"
    before = path.read_text(encoding="utf-8")

    response = client.put(
        "/api/subjects/SUB-people/entries/bob/match-terms",
        json={"token": served["token"], "match_terms": ["SUB-people/"]},
    )

    assert response.status_code == 400
    assert path.read_text(encoding="utf-8") == before


def test_a_match_term_write_to_an_unknown_entry_is_a_404(tmp_path):
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)

    response = client.put(
        "/api/subjects/SUB-people/entries/nobody/match-terms",
        json={"token": "whatever", "match_terms": ["Bob"]},
    )

    assert response.status_code == 404


def test_an_accepted_write_commits_so_the_tree_is_left_clean(tmp_path):
    """ADR-0003 decision 2. Without the commit, every file the author
    touches in the app carries uncommitted modifications and #32's
    dirty-tree rule closes it to the Curator until someone commits by
    hand."""
    _, repository = _bob_repo(tmp_path)
    client = _client(repository)
    served = client.get("/api/subjects/SUB-people/entries/bob").json()

    client.put(
        "/api/subjects/SUB-people/entries/bob/match-terms",
        json={"token": served["token"], "match_terms": ["Robert"]},
    )

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert author == "Local Author"


def test_nothing_but_the_match_terms_route_writes(tmp_path):
    """Pins and exclusions are author acts with their own attribution and
    belong to #18 - #26 renders them, it does not author them. A route that
    grew a second write would show up here."""
    import memoria.web.routes as routes_module

    write_methods = [
        method
        for route in routes_module.router.routes
        for method in route.methods
        if method not in {"GET", "HEAD", "OPTIONS"}
    ]
    paths = sorted(
        route.path
        for route in routes_module.router.routes
        if route.methods & {"POST", "PUT", "PATCH", "DELETE"}
    )
    assert write_methods
    assert paths == [
        # ADR-0009: the two model-free derived-state passes the adapter may
        # launch on the author's own machine. Neither is a durable write -
        # normalized records and the index are Derived (§42), outside the
        # write path - and neither computes anything here: the core runs
        # the pass and this forwards its report.
        "/ingestion/normalize",
        "/ingestion/rebuild",
        # #43: the author applying a proposed rewrite from Review - the
        # Section/Review surfaces' one write, through the same write path.
        "/sections/{section_id}/paragraphs/{paragraph_index}",
        # #33 / #45: the author settling a finding from Review - lands on
        # the entry, through the same write path, with the entry's token.
        "/sections/{section_id}/settlements",
        "/sources/{record_id}/reveal",
        "/subjects/{subject_id}/entries/{entry_slug}/match-terms",
    ]


# --- the manuscript: outline, Section, Review (#43) ---------------------------


def _manuscript_repo(tmp_path, *, draft="Bob went to town.\n\nHe came back.\n"):
    """`_entry_repo` plus one chapter and one section whose brief resolves
    to the Bob entry and whose draft holds ``draft`` - committed, since the
    rewrite route writes through the same git-backed path #26's does."""
    from memoria.manuscript import create_chapter, create_section

    repository = _entry_repo(
        tmp_path, entries=[("people", "bob", {"match_terms": ["Bob"]})]
    )
    chapter = create_chapter(repository, "The first chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    if draft is not None:
        (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "manuscript"], cwd=tmp_path, check=True, capture_output=True
    )
    return repository, chapter, section


def test_the_manuscript_outline_over_a_fresh_repository_is_not_built(tmp_path):
    client = _client(_repo(tmp_path))

    assert client.get("/api/manuscript").json() == {"chapters": [], "is_built": False}


def test_the_manuscript_outline_lists_chapters_and_sections_by_their_briefs(tmp_path):
    repository, chapter, section = _manuscript_repo(tmp_path)
    client = _client(repository)

    body = client.get("/api/manuscript").json()

    assert body["is_built"] is True
    assert body["chapters"] == [
        {
            "id": chapter.brief.id,
            "number": 1,
            "excerpt": "The first chapter.",
            "sections": [
                {"id": section.brief.id, "number": 1, "excerpt": "About Bob.", "has_draft": True}
            ],
        }
    ]


def test_read_section_serves_brief_draft_scope_and_not_current_causes(tmp_path):
    repository, chapter, section = _manuscript_repo(tmp_path)
    client = _client(repository)

    body = client.get(f"/api/sections/{section.brief.id}").json()

    assert body["id"] == section.brief.id
    assert body["chapter_id"] == chapter.brief.id
    assert body["brief"] == "About Bob."
    assert body["unconfirmed"] is False
    assert body["has_draft"] is True
    assert [p["text"] for p in body["paragraphs"]] == ["Bob went to town.", "He came back."]
    assert {(n["entry_id"], n["kind"], n["cause"]) for n in body["paragraphs"][0]["not_current"]} == {
        ("SUB-people/bob", "engagement", "never_audited"),
        ("SUB-people/bob", "audit_verdict", "never_audited"),
    }
    assert body["scope"] == [{"entry_id": "SUB-people/bob", "matched_by": ["bob", "Bob"]}]
    assert body["scope_empty"] is False
    assert body["sessions"] == [] and body["decisions"] == [] and body["questions"] == []
    # No checkpoint or unresolved-impacts state is served (part 12 §39).
    assert not any(key for key in body if "checkpoint" in key or "impact" in key)


def test_read_section_for_an_unknown_id_is_a_404(tmp_path):
    repository, _, _ = _manuscript_repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/sections/SEC-9999")

    assert response.status_code == 404
    assert "SEC-9999" in response.json()["detail"]


def test_read_review_over_an_unaudited_section_has_no_findings_and_says_so(tmp_path):
    repository, _, section = _manuscript_repo(tmp_path)
    client = _client(repository)

    body = client.get(f"/api/sections/{section.brief.id}/review").json()

    assert body["findings"] == []
    assert (body["verdicts_current"], body["verdicts_not_current"]) == (0, 2)
    assert isinstance(body["token"], str) and body["token"]


def test_read_review_serves_findings_as_disagreement_sets_with_resolutions(tmp_path):
    from memoria.audit import (
        DisagreementMember,
        Finding,
        ManuscriptParagraph,
        finding_verdict,
        record_audit_verdict,
    )

    repository, chapter, section = _manuscript_repo(tmp_path)
    paragraph = ManuscriptParagraph(chapter.number, section.number, 2, "He came back.")
    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("source", "src-000184-p1"),
        ),
        statement="The source has him back a day later.",
        confidence="high",
        subject_id="SUB-people",
        patch="He came back the next day.",
    )
    record_audit_verdict(repository, paragraph, "SUB-people/bob", finding_verdict(finding))
    client = _client(repository)

    body = client.get(f"/api/sections/{section.brief.id}/review").json()

    assert body["findings"] == [
        {
            "paragraph_index": 2,
            "paragraph_text": "He came back.",
            "entry_id": "SUB-people/bob",
            "subject_id": "SUB-people",
            "confidence": "high",
            "statement": "The source has him back a day later.",
            "disagreement_set": [
                {"kind": "passage", "ref": "01/01#2"},
                {"kind": "source", "ref": "src-000184-p1"},
            ],
            "resolutions": ["rewrite the passage", "exclude the source"],
            "patch": "He came back the next day.",
            "entry_token": serve_entry(repository, "SUB-people", "bob")[1],
        }
    ]
    assert (body["verdicts_current"], body["verdicts_not_current"]) == (1, 1)
    assert body["sessions"] == []


# --- settling a finding from Review (#33, walked by #45) ----------------------


def _three_way_finding(repository, chapter, section):
    """An audit's three-way finding on paragraph 2 - the one shape whose
    resolutions are settlements (part 06 §8.10)."""
    from memoria.audit import (
        DisagreementMember,
        Finding,
        ManuscriptParagraph,
        finding_verdict,
        record_audit_verdict,
    )

    paragraph = ManuscriptParagraph(chapter.number, section.number, 2, "He came back.")
    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("entry", "SUB-people/bob"),
            DisagreementMember("source", "src-000184-p1"),
        ),
        statement="The source has him back a day later.",
        confidence="high",
        subject_id="SUB-people",
    )
    record_audit_verdict(repository, paragraph, "SUB-people/bob", finding_verdict(finding))
    return finding


def _settle_payload(finding_out, **overrides):
    payload = {
        "entry_id": finding_out["entry_id"],
        "disagreement_set": finding_out["disagreement_set"],
        "side": "entry",
        "proposition": "he came back the same day",
        "reason": "the author's own recollection outranks the letter",
        "session_id": "SES-20260912-1432",
        "entry_token": finding_out["entry_token"],
    }
    payload.update(overrides)
    return payload


def test_settling_a_finding_lands_on_the_entry_and_commits_as_the_author(tmp_path):
    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]
    assert finding["resolutions"] == [
        "settle toward the entry", "settle toward the source", "settle toward the passage"
    ]

    response = client.post(
        f"/api/sections/{section.brief.id}/settlements", json=_settle_payload(finding)
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["entry_id"] == "SUB-people/bob"
    assert body["claim_id"] == "CLM-0001"
    assert body["settled_line"].startswith(
        "[settled] he came back the same day — SUB-people/bob, chosen over SRC-000184 ¶1,"
    )
    entry_text = (tmp_path / "subjects" / "people" / "bob.md").read_text(encoding="utf-8")
    assert body["settled_line"] in entry_text
    assert "— SES-20260912-1432" in entry_text
    assert (tmp_path / "claims" / "CLM-0001.md").is_file()
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert author == "Local Author"
    # The settlement moved the entry: the finding is silenced and every
    # judgement against the entry is stale until the audit runs again.
    after = client.get(f"/api/sections/{section.brief.id}/review").json()
    assert after["findings"] == []
    assert (after["verdicts_current"], after["verdicts_not_current"]) == (0, 2)


def test_settling_with_a_stale_entry_token_is_a_409_and_writes_nothing(tmp_path):
    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    entry_path.write_text(
        entry_path.read_text(encoding="utf-8") + "\nEdited in Obsidian.\n", encoding="utf-8"
    )
    before = entry_path.read_text(encoding="utf-8")

    response = client.post(
        f"/api/sections/{section.brief.id}/settlements", json=_settle_payload(finding)
    )

    assert response.status_code == 409
    assert "bob.md" in response.json()["detail"]
    assert entry_path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "claims").exists()


def test_settling_toward_a_side_the_set_does_not_carry_is_a_400(tmp_path):
    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]

    response = client.post(
        f"/api/sections/{section.brief.id}/settlements",
        json=_settle_payload(finding, side="decision"),
    )

    assert response.status_code == 400
    assert "cannot settle toward 'decision'" in response.json()["detail"]
    assert not (tmp_path / "claims").exists()


def test_settling_on_an_unknown_section_is_a_404(tmp_path):
    repository, _, _ = _manuscript_repo(tmp_path)
    client = _client(repository)

    response = client.post(
        "/api/sections/SEC-9999/settlements",
        json=_settle_payload(
            {"entry_id": "SUB-people/bob", "disagreement_set": [], "entry_token": "x"}
        ),
    )

    assert response.status_code == 404


def test_a_finding_whose_entry_cannot_be_served_still_renders_with_no_token(
    tmp_path, monkeypatch
):
    """A finding stands on the index's judgement, but the token for a
    settlement is minted off the entry's file: an entry that cannot be
    served (``SubjectError``) leaves the review served whole, the finding
    carrying no token, so Settle is not offered on it rather than the page
    failing. (A file moved between subject directories with its id kept
    is refused earlier, by the audit's own scoping through ``index.gather``
    - the same lookup - so the condition is injected at the seam here.)"""
    from memoria import review as review_module
    from memoria.subjects import SubjectError

    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)

    def cannot_serve(repository, subject_id, entry_slug):
        raise SubjectError(f"no such entry: {subject_id}/{entry_slug}")

    monkeypatch.setattr(review_module, "serve_entry", cannot_serve)
    response = client.get(f"/api/sections/{section.brief.id}/review")

    assert response.status_code == 200, response.json()
    (finding,) = response.json()["findings"]
    assert finding["entry_id"] == "SUB-people/bob"
    assert finding["entry_token"] is None


def _settle_rejected(tmp_path, section, client, finding, **overrides):
    """Post a settlement expected to be refused, and hold that nothing was
    written: no claim, and the entry as it was."""
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    before = entry_path.read_text(encoding="utf-8")
    response = client.post(
        f"/api/sections/{section.brief.id}/settlements",
        json=_settle_payload(finding, **overrides),
    )
    assert entry_path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "claims").exists()
    return response


def test_settling_on_an_entry_that_is_not_the_sets_own_is_a_400(tmp_path):
    """The token was checked against ``entry_id``, so a set whose entry
    member names another entry would land the write somewhere unchecked."""
    repository, chapter, section = _manuscript_repo(tmp_path)
    _write_entry(tmp_path, "people", "alice", match_terms=["Alice"])
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]
    disagreement_set = [
        {"kind": "entry", "ref": "SUB-people/alice"} if member["kind"] == "entry" else member
        for member in finding["disagreement_set"]
    ]

    response = _settle_rejected(
        tmp_path, section, client, finding, disagreement_set=disagreement_set
    )

    assert response.status_code == 400
    assert "SUB-people/alice" in response.json()["detail"]
    alice = (tmp_path / "subjects" / "people" / "alice.md").read_text(encoding="utf-8")
    assert "[settled]" not in alice


def test_an_entry_that_moves_between_the_check_and_the_write_is_a_409(tmp_path, monkeypatch):
    """ADR-0003: the write path's own staleness check is the last word. An
    edit that lands after the route's pre-check and before the write is the
    same outcome as one that landed before it - 409, nothing written."""
    from memoria import review as review_module

    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]
    entry_path = tmp_path / "subjects" / "people" / "bob.md"
    real_settle = review_module.settle

    def settle_after_an_edit(*args, **kwargs):
        entry_path.write_text(
            entry_path.read_text(encoding="utf-8") + "\nEdited in Obsidian.\n", encoding="utf-8"
        )
        return real_settle(*args, **kwargs)

    monkeypatch.setattr(review_module, "settle", settle_after_an_edit)

    response = client.post(
        f"/api/sections/{section.brief.id}/settlements", json=_settle_payload(finding)
    )

    assert response.status_code == 409
    assert "bob.md" in response.json()["detail"]
    assert "[settled]" not in entry_path.read_text(encoding="utf-8")
    assert not (tmp_path / "claims").exists()


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"entry_id": "bob"}, "names bob"),
        ({"reason": ""}, "reason"),
        ({"session_id": "SES-20260912-1432#T003"}, "not a turn"),
    ],
)
def test_a_settlement_the_set_does_not_admit_is_a_400_and_writes_nothing(
    tmp_path, overrides, detail
):
    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]

    response = _settle_rejected(tmp_path, section, client, finding, **overrides)

    assert response.status_code == 400
    assert detail in response.json()["detail"]


def test_a_set_carrying_a_brief_is_never_settled(tmp_path):
    """Part 06 §8.10: a brief is not a resolution target; the set offers a
    conversation about the brief, and the route refuses the settlement."""
    repository, chapter, section = _manuscript_repo(tmp_path)
    _three_way_finding(repository, chapter, section)
    client = _client(repository)
    (finding,) = client.get(f"/api/sections/{section.brief.id}/review").json()["findings"]
    disagreement_set = finding["disagreement_set"] + [
        {"kind": "brief", "ref": section.brief.id}
    ]

    response = _settle_rejected(
        tmp_path, section, client, finding, disagreement_set=disagreement_set
    )

    assert response.status_code == 400
    assert "brief" in response.json()["detail"]


# --- the supplied-context surface (#61) --------------------------------------


def test_the_supplied_context_of_a_section_no_session_assembled_is_empty(tmp_path):
    repository, _, section = _manuscript_repo(tmp_path)
    client = _client(repository)

    body = client.get(f"/api/sections/{section.brief.id}/supplied-context").json()

    assert body == {"section_id": section.brief.id, "sessions": []}


def test_the_supplied_context_serves_both_halves_apart_and_no_token_figure(tmp_path):
    """A session assembles the section, then reads beyond its assembly.
    The route serves the working context and the reads since as two
    fields, and - although the ``read`` ledger line carries a token count
    for the context manifest - no token, byte, percentage or capacity
    figure anywhere in the response (ADR-0001's file boundary)."""
    from memoria import ledger
    from memoria.assembly import assemble
    from memoria.records import Read

    repository, _, section = _manuscript_repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    ledger.append_read(
        repository,
        session_id,
        Read(ref="src-000184-p1", citation="SRC-000184 ¶1", text="Bob called on July 17."),
    )
    client = _client(repository)

    response = client.get(f"/api/sections/{section.brief.id}/supplied-context")

    assert response.status_code == 200
    body = response.json()
    (session,) = body["sessions"]
    assert session["session_id"] == session_id
    assert session["briefs"] == [section.brief.id]
    assert session["entries"] == [
        {"entry_id": "SUB-people/bob", "matched_by": ["bob", "Bob"], "sources": []}
    ]
    assert session["fallbacks"] == []
    assert session["served_since"] == [
        {"tool": "read", "ref": "src-000184-p1", "served": ["SRC-000184 ¶1"]}
    ]
    lowered = response.text.lower()
    assert not any(word in lowered for word in ("token", "byte", "percent", "%", "capacity"))


def test_the_supplied_context_of_an_unknown_section_is_a_404(tmp_path):
    repository, _, _ = _manuscript_repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/sections/SEC-9999/supplied-context")

    assert response.status_code == 404
    assert "SEC-9999" in response.json()["detail"]


def test_applying_a_rewrite_replaces_the_paragraph_and_commits_as_the_author(tmp_path):
    repository, _, section = _manuscript_repo(tmp_path)
    client = _client(repository)
    token = client.get(f"/api/sections/{section.brief.id}/review").json()["token"]

    response = client.put(
        f"/api/sections/{section.brief.id}/paragraphs/2",
        json={"token": token, "text": "He came back the next day."},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["paragraph_index"] == 2
    assert body["text"] == "He came back the next day."
    assert body["token"] and body["token"] != token
    assert (section.dir / "draft.md").read_text(encoding="utf-8") == (
        "Bob went to town.\n\nHe came back the next day.\n"
    )
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert author == "Local Author"
    # The brief beside the draft is untouched: no route edits a brief.
    assert "About Bob." in section.path.read_text(encoding="utf-8")


def test_applying_a_rewrite_with_a_stale_token_is_a_409_and_writes_nothing(tmp_path):
    repository, _, section = _manuscript_repo(tmp_path)
    client = _client(repository)
    token = client.get(f"/api/sections/{section.brief.id}/review").json()["token"]
    (section.dir / "draft.md").write_text("Edited in Obsidian.\n", encoding="utf-8")

    response = client.put(
        f"/api/sections/{section.brief.id}/paragraphs/1",
        json={"token": token, "text": "Rewritten."},
    )

    assert response.status_code == 409
    assert (section.dir / "draft.md").read_text(encoding="utf-8") == "Edited in Obsidian.\n"


def test_applying_a_rewrite_to_a_missing_paragraph_is_a_400(tmp_path):
    repository, _, section = _manuscript_repo(tmp_path)
    client = _client(repository)
    token = client.get(f"/api/sections/{section.brief.id}/review").json()["token"]

    response = client.put(
        f"/api/sections/{section.brief.id}/paragraphs/7",
        json={"token": token, "text": "Rewritten."},
    )

    assert response.status_code == 400
    assert "no paragraph 7" in response.json()["detail"]


def test_applying_a_rewrite_to_an_unknown_section_is_a_404(tmp_path):
    repository, _, _ = _manuscript_repo(tmp_path)
    client = _client(repository)

    response = client.put(
        "/api/sections/SEC-9999/paragraphs/1", json={"token": "x", "text": "Rewritten."}
    )

    assert response.status_code == 404
