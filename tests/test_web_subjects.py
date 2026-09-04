"""The `+ New subject` route (ADR-0014) through the FastAPI adapter: a
subject prompt written as the author, through the write path's creation
door."""

import subprocess

from fastapi.testclient import TestClient

from memoria.repository import Repository
from memoria.subjects import load_subject, subject_path, write_builtin_subjects
from memoria.web.app import create_app


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(tmp_path, *, identity=True):
    _git(tmp_path, "init", "-q")
    if identity:
        _git(tmp_path, "config", "user.name", "Local Author")
        _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=seed", "-c", "user.email=seed@x", "commit", "-q", "-m", "seed")
    return repository


def _client(repository):
    return TestClient(create_app(repository=repository)).__enter__()


BODY = {
    "name": "Key dates",
    "match": "A date the archive keeps returning to.",
    "hazards": "Do not merge two dates the sources give differently.",
    "audit_questions": "Does the passage date this out of step with the entry?",
    "auto_promote": True,
}


def test_create_subject_writes_the_prompt_as_the_author(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.post("/api/subjects", json=BODY)

    assert response.status_code == 200, response.text
    assert response.json() == {"id": "SUB-key-dates"}
    subject = load_subject(repository, "SUB-key-dates")
    assert subject.match == BODY["match"]
    assert subject.auto_promote is True
    assert _git(tmp_path, "status", "--porcelain").strip() == ""
    assert _git(tmp_path, "log", "-1", "--format=%an").strip() == "Local Author"
    listed = client.get("/api/subjects").json()
    assert {"id": "SUB-key-dates", "entry_count": 0} in listed["items"]


def test_create_subject_is_a_409_when_the_subject_exists(tmp_path):
    repository = _repo(tmp_path)
    before = subject_path(repository, "SUB-people").read_text(encoding="utf-8")

    response = _client(repository).post("/api/subjects", json={**BODY, "name": "People"})

    assert response.status_code == 409
    assert "SUB-people" in response.json()["detail"]
    assert subject_path(repository, "SUB-people").read_text(encoding="utf-8") == before


def test_create_subject_is_a_422_for_a_name_that_makes_no_id(tmp_path):
    response = _client(_repo(tmp_path)).post("/api/subjects", json={**BODY, "name": "---"})

    assert response.status_code == 422


def test_create_subject_is_a_500_without_a_git_identity(tmp_path, monkeypatch):
    # The global and system files are pointed at nothing, as test_write does.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-global"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent-system"))
    repository = _repo(tmp_path, identity=False)

    response = _client(repository).post("/api/subjects", json=BODY)

    assert response.status_code == 500
    assert not subject_path(repository, "SUB-key-dates").exists()
