"""The dialog's two routes (ADR-0012) through the FastAPI adapter: a new
section written as the author, and one interviewer turn of a grilling run
directly - a 409 until the author switches direct runs on, the seam a
scripted fake once they have.
"""

import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from memoria import manuscript, model
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.model import ModelError, ModelReply, ModelUsage
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import write_builtin_subjects
from memoria.web.app import create_app

KEY = "sk-ant-secret-never-shown"
PROSE = "The deck went up unchanged.\n\nBy evening the whole street had seen it."


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv(model.API_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv("MEMORIA_SESSION_ID", raising=False)


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
    manuscript.create_book(repository, "A book about the street.")
    chapter = manuscript.create_chapter(repository, "The summer the deck went up.")
    manuscript.create_section(repository, chapter.number, "How it started.")
    record = NormalizedRecord(
        id="SRC-000001",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=["The deck went up unchanged.", "Nobody dared touch it."],
    )
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    _git(tmp_path, "add", "-A")
    env = {"GIT_AUTHOR_NAME": "seed", "GIT_AUTHOR_EMAIL": "seed@x", "GIT_COMMITTER_NAME": "seed", "GIT_COMMITTER_EMAIL": "seed@x"}
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True, env={**__import__("os").environ, **env})
    return repository


def _client(repository):
    return TestClient(create_app(repository=repository)).__enter__()


def _switch_on(repository, monkeypatch, handler):
    model.save_settings(repository, model.ModelSettings(enabled=True, api_key=KEY))
    monkeypatch.setattr(model, "sdk_available", lambda: True)
    seen = []

    def fake(request):
        seen.append(request)
        answer = handler(request)
        if isinstance(answer, ModelReply):
            return answer
        if isinstance(answer, Exception):
            raise answer
        return ModelReply(
            text=json.dumps(answer),
            stop_reason="end_turn",
            usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=3),
        )

    monkeypatch.setattr(model, "anthropic_model", lambda settings, key: fake)
    return seen


# --- POST /chapters/{id}/sections --------------------------------------------------


def test_writing_a_section_with_a_brief_commits_both_files_as_the_author(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.post(
        "/api/chapters/CHP-0001/sections",
        json={"brief": "The evening the street saw it.", "draft": PROSE},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": "SEC-0002",
        "chapter_id": "CHP-0001",
        "chapter_number": 1,
        "section_number": 2,
        "unconfirmed": False,
    }
    section = manuscript.resolve_section(repository, "SEC-0002")
    assert section.brief.text == "The evening the street saw it."
    assert (section.dir / "draft.md").read_text() == PROSE + "\n"
    assert _git(tmp_path, "log", "-2", "--format=%an <%ae>").split() == [
        "Local", "Author", "<local@memoria.test>",
        "Local", "Author", "<local@memoria.test>",
    ]
    assert _git(tmp_path, "status", "--porcelain").strip() == ""
    # The outline serves it, appended.
    outline = client.get("/api/manuscript").json()
    assert [s["id"] for s in outline["chapters"][0]["sections"]] == ["SEC-0001", "SEC-0002"]
    assert outline["chapters"][0]["sections"][1]["has_draft"] is True


def test_writing_prose_alone_derives_an_unconfirmed_brief(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.post("/api/chapters/CHP-0001/sections", json={"draft": PROSE})

    assert response.status_code == 200, response.text
    assert response.json()["unconfirmed"] is True
    section = manuscript.resolve_section(repository, "SEC-0002")
    assert section.brief.text == "The deck went up unchanged."
    assert section.brief.unconfirmed is True
    view = client.get("/api/sections/SEC-0002").json()
    assert view["unconfirmed"] is True
    assert view["brief"] == "The deck went up unchanged."


def test_writing_into_an_unknown_chapter_is_a_404_and_writes_nothing(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.post("/api/chapters/CHP-0042/sections", json={"draft": PROSE})

    assert response.status_code == 404
    assert "no such chapter" in response.json()["detail"]
    assert len(manuscript.list_sections(repository, 1)) == 1


def test_empty_prose_is_refused_at_the_boundary(tmp_path):
    client = _client(_repo(tmp_path))
    assert client.post("/api/chapters/CHP-0001/sections", json={"draft": ""}).status_code == 422
    assert client.post("/api/chapters/CHP-0001/sections", json={}).status_code == 422


def test_writing_without_a_git_identity_is_a_500_that_names_the_fix(tmp_path, monkeypatch):
    # The global and system files are pointed at nothing, as test_write does:
    # `git config --get` falls through to them otherwise.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-global"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent-system"))
    repository = _repo(tmp_path, identity=False)
    client = _client(repository)

    response = client.post("/api/chapters/CHP-0001/sections", json={"draft": PROSE})

    assert response.status_code == 500
    assert "user.name" in response.json()["detail"]
    assert len(manuscript.list_sections(repository, 1)) == 1


# --- POST /grill ---------------------------------------------------------------------


def test_grilling_is_a_409_naming_settings_while_direct_runs_are_off(tmp_path):
    client = _client(_repo(tmp_path))

    response = client.post("/api/grill", json={"chapter_id": "CHP-0001", "turns": []})

    assert response.status_code == 409
    assert model.SETTINGS_SURFACE in response.json()["detail"]


def test_a_grilling_turn_carries_the_transcript_and_the_source_and_returns_the_question(
    tmp_path, monkeypatch
):
    repository = _repo(tmp_path)
    seen = _switch_on(
        repository,
        monkeypatch,
        lambda request: {
            "done": False,
            "question": "Where does the section open?",
            "recommended_answer": "On the street at dusk, before anyone speaks.",
            "brief": "",
            "draft": "",
        },
    )
    client = _client(repository)

    response = client.post(
        "/api/grill",
        json={
            "chapter_id": "CHP-0001",
            "source_ref": "SRC-000001",
            "turns": [
                {"role": "interviewer", "text": "What is this section about?"},
                {"role": "author", "text": "The evening the street saw the deck."},
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["done"] is False
    assert body["question"] == "Where does the section open?"
    assert body["recommended_answer"].startswith("On the street")
    assert body["brief"] == "" and body["draft"] == ""
    assert body["rejected"] == []
    assert body["spend"] == {"calls": 1, "model": "fake-model"}
    (request,) = seen
    assert "The deck went up unchanged." in request.system
    assert "The evening the street saw the deck." in request.user
    # Nothing written, and the spend ledgered under the app's session.
    assert len(manuscript.list_sections(repository, 1)) == 1
    lines = [
        json.loads(line)
        for path in (tmp_path / "sessions").rglob("events.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert [line["tool"] for line in lines] == ["grill_brief", "model_call"]
    assert lines[1]["pass"] == "grill"


def test_a_finished_grilling_returns_the_draft_for_the_author_to_write(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(
        repository,
        monkeypatch,
        lambda request: {
            "done": True,
            "question": "",
            "recommended_answer": "",
            "brief": "The evening the street saw the deck.",
            "draft": PROSE,
        },
    )
    client = _client(repository)

    body = client.post("/api/grill", json={"chapter_id": "CHP-0001", "turns": []}).json()

    assert body["done"] is True
    assert body["brief"] == "The evening the street saw the deck."
    assert body["draft"] == PROSE
    assert len(manuscript.list_sections(repository, 1)) == 1


def test_a_grilling_about_an_unknown_chapter_or_source_is_a_404(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(repository, monkeypatch, lambda request: {})
    client = _client(repository)

    assert client.post("/api/grill", json={"chapter_id": "CHP-0042", "turns": []}).status_code == 404
    assert (
        client.post(
            "/api/grill", json={"chapter_id": "CHP-0001", "source_ref": "SRC-000042", "turns": []}
        ).status_code
        == 404
    )


def test_a_provider_failure_is_a_502(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(repository, monkeypatch, lambda request: ModelError("rate-limited"))
    client = _client(repository)

    response = client.post("/api/grill", json={"chapter_id": "CHP-0001", "turns": []})

    assert response.status_code == 502
    assert "rate-limited" in response.json()["detail"]


def test_a_malformed_turn_role_is_refused_at_the_boundary(tmp_path):
    client = _client(_repo(tmp_path))
    response = client.post(
        "/api/grill",
        json={"chapter_id": "CHP-0001", "turns": [{"role": "system", "text": "x"}]},
    )
    assert response.status_code == 422
