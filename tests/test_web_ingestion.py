"""``GET /api/ingestion`` and the two runs beside it (ADR-0011).

The adapter shapes ``memoria.ingestion``'s status and forwards two
local-only, model-free passes; these tests exercise the shaping and the
gating, not the derivation ``tests/test_ingestion.py`` already covers.
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

import memoria.web.routes as routes
from memoria.ingestion import _RUN_LOCK
from memoria.normalize import normalize
from memoria.repository import Repository
from memoria.web.app import create_app
from test_normalize import _write_raw_file


def _corpus(tmp_path, *files):
    evidence_root = tmp_path / "evidence"
    for rel_path, content in files:
        _write_raw_file(evidence_root, rel_path, content)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return Repository(root=repo_root, evidence_root=evidence_root), evidence_root


def _client(repository):
    return TestClient(create_app(repository=repository)).__enter__()


# --- the status ----------------------------------------------------------------


def test_status_is_null_without_an_evidence_root(tmp_path):
    client = _client(Repository(root=tmp_path))

    body = client.get("/api/ingestion").json()

    assert body["units"] is None
    assert body["is_normalized"] is False
    assert body["is_indexed"] is False
    assert "current" in body["counts"]


def test_status_lists_every_ledger_unit_with_its_three_stages(tmp_path):
    repository, evidence_root = _corpus(
        tmp_path, ("one.txt", "hello\n\nworld"), ("bad.pdf", "not a pdf")
    )
    normalize(repository, evidence_root)
    client = _client(repository)

    body = client.get("/api/ingestion").json()

    by_id = {unit["id"]: unit for unit in body["units"]}
    assert by_id["SRC-000001"]["converted"] == "failed"
    assert by_id["SRC-000001"]["failure_reason"]
    assert by_id["SRC-000001"]["record_paragraphs"] is None
    assert by_id["SRC-000002"] == {
        "id": "SRC-000002",
        "path": "raw/one.txt",
        "deleted": False,
        "converted": "current",
        "failure_reason": None,
        "record_paragraphs": 2,
        "indexed_paragraphs": None,
        "extracted_paragraphs": 0,
        "email_message_index": None,
    }
    assert body["counts"]["current"] == 1
    assert body["counts"]["failed"] == 1
    assert body["is_normalized"] is True
    assert body["is_indexed"] is False


# --- the runs ------------------------------------------------------------------


def test_the_runs_are_refused_for_a_non_local_client(tmp_path):
    """TestClient's peer is the literal ``testclient``, which
    ``_is_local`` fails closed on - the same as ``reveal``."""
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"))
    client = _client(repository)

    assert client.post("/api/ingestion/normalize").status_code == 403
    assert client.post("/api/ingestion/rebuild").status_code == 403


def test_normalize_runs_the_pass_and_returns_its_report(tmp_path, monkeypatch):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    monkeypatch.setattr(routes, "_is_local", lambda request: True)
    client = _client(repository)

    response = client.post("/api/ingestion/normalize")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "normalize"
    assert body["summary"]["converted"] == 1
    assert body["elapsed_seconds"] >= 0
    status = client.get("/api/ingestion").json()
    assert status["units"][0]["converted"] == "current"


def test_normalize_is_a_404_without_an_evidence_root(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "_is_local", lambda request: True)
    client = _client(Repository(root=tmp_path))

    assert client.post("/api/ingestion/normalize").status_code == 404


def test_rebuild_indexes_the_records(tmp_path, monkeypatch):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    normalize(repository, evidence_root)
    monkeypatch.setattr(routes, "_is_local", lambda request: True)
    client = _client(repository)

    response = client.post("/api/ingestion/rebuild")

    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "rebuild"
    assert response.json()["summary"]["records"] == 1
    status = client.get("/api/ingestion").json()
    assert status["is_indexed"] is True
    assert status["units"][0]["indexed_paragraphs"] == 2


def test_a_run_is_a_409_while_another_holds_the_lock(tmp_path, monkeypatch):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"))
    monkeypatch.setattr(routes, "_is_local", lambda request: True)
    client = _client(repository)
    assert _RUN_LOCK.acquire(blocking=False)
    try:
        assert client.post("/api/ingestion/normalize").status_code == 409
        assert client.post("/api/ingestion/rebuild").status_code == 409
    finally:
        _RUN_LOCK.release()


# --- adding a raw unit (ADR-0013) ------------------------------------------------


def _upload(path: str, data: bytes) -> dict:
    return {"path": path, "content": base64.b64encode(data).decode("ascii")}


def test_add_unit_places_the_bytes_under_raw_and_says_where(tmp_path):
    """The TestClient's peer is non-local, and that is the point: unlike the
    two runs, adding a unit is not gated - the bytes travel (ADR-0002)."""
    repository, evidence_root = _corpus(tmp_path)
    client = _client(repository)

    response = client.post("/api/ingestion/units", json=_upload("box 3/note.txt", b"hello"))

    assert response.status_code == 200, response.text
    assert response.json() == {"path": "raw/box 3/note.txt", "size": 5}
    assert (evidence_root / "raw" / "box 3" / "note.txt").read_bytes() == b"hello"


def test_add_unit_is_a_409_for_a_path_already_taken(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "original"))
    client = _client(repository)

    response = client.post("/api/ingestion/units", json=_upload("one.txt", b"other"))

    assert response.status_code == 409
    assert "raw/one.txt already exists" in response.json()["detail"]
    assert (evidence_root / "raw" / "one.txt").read_text() == "original"


def test_add_unit_is_a_400_for_a_path_that_climbs_out_or_hides(tmp_path):
    repository, _ = _corpus(tmp_path)
    client = _client(repository)

    assert client.post("/api/ingestion/units", json=_upload("../x.txt", b"x")).status_code == 400
    assert client.post("/api/ingestion/units", json=_upload(".DS_Store", b"x")).status_code == 400


def test_add_unit_is_a_404_without_an_evidence_root(tmp_path):
    client = _client(Repository(root=tmp_path))

    assert client.post("/api/ingestion/units", json=_upload("x.txt", b"x")).status_code == 404


def test_add_unit_refuses_an_oversize_or_malformed_body_at_the_boundary(tmp_path):
    repository, _ = _corpus(tmp_path)
    client = _client(repository)

    too_big = base64.b64encode(b"x" * (64 * 1024 * 1024 + 1)).decode("ascii")
    assert client.post("/api/ingestion/units", json={"path": "x.txt", "content": too_big}).status_code == 422
    assert client.post("/api/ingestion/units", json={"path": "x.txt", "content": "not base64!"}).status_code == 422


def test_status_carries_the_unnumbered_raw_files(tmp_path):
    repository, _ = _corpus(tmp_path, ("waiting.txt", "hello"))
    client = _client(repository)

    body = client.get("/api/ingestion").json()

    assert body["units"] == []
    assert body["unnumbered"] == ["raw/waiting.txt"]
    assert _client(Repository(root=tmp_path)).get("/api/ingestion").json()["unnumbered"] is None
