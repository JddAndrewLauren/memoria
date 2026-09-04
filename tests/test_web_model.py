"""Settings > Model and the direct-run routes (ADR-0010), through the
FastAPI adapter. The key never leaves the server; every run route is a 409
until the author switches direct runs on; with the switch on, the seam is
replaced by a scripted fake and no socket is opened.
"""

import json
import pathlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from memoria import model, style
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.manuscript import create_chapter, create_section
from memoria.model import ModelError, ModelReply, ModelUsage
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.web.app import create_app
from memoria.write import Actor

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTHOR = Actor(name="Local Author", email="local@memoria.test")
KEY = "sk-ant-secret-never-shown"


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    monkeypatch.delenv(model.API_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv("MEMORIA_SESSION_ID", raising=False)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, paragraphs=("Bob and the acquisition.", "Bob again."), entries=()):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    for entry in entries:
        subject_slug, slug = entry.id[len("SUB-") :].split("/", 1)
        (tmp_path / "subjects" / subject_slug / f"{slug}.md").write_text(entry_to_markdown(entry))
    record = NormalizedRecord(
        id="SRC-000001",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=list(paragraphs),
    )
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed")
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
        if isinstance(answer, dict):
            answer = json.dumps(answer)
        return ModelReply(
            text=answer,
            stop_reason="end_turn",
            usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=3),
        )

    monkeypatch.setattr(model, "anthropic_model", lambda settings, key: fake)
    return seen


def _reading(request):
    if request.pass_name == "cluster_summary":
        return "Bob, throughout."
    return {
        "placements": [],
        "unplaced": [{"surface_form": "Bob", "subject_id": "SUB-people"}],
        "relations": [],
    }


# --- Settings > Model -------------------------------------------------------------


def test_the_model_settings_read_off_by_default(tmp_path):
    client = _client(_repo(tmp_path))
    body = client.get("/api/model").json()
    assert body == {
        "enabled": False,
        "provider": "anthropic",
        "model": "claude-opus-5",
        "effort": None,
        "api_key_set": False,
        "api_key_source": None,
        "ready": False,
        "reason": model.REASON_OFF,
    }


def test_the_effort_level_round_trips_and_an_unknown_one_is_refused(tmp_path):
    client = _client(_repo(tmp_path))
    saved = client.put("/api/model", json={"enabled": True, "model": "claude-opus-5", "effort": "low"})
    assert saved.json()["effort"] == "low"
    assert client.get("/api/model").json()["effort"] == "low"
    cleared = client.put("/api/model", json={"enabled": True, "model": "claude-opus-5"})
    assert cleared.json()["effort"] is None
    refused = client.put("/api/model", json={"enabled": True, "model": "claude-opus-5", "effort": "extreme"})
    assert refused.status_code == 422


def test_the_key_is_stored_owner_only_and_never_returned(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    monkeypatch.setattr(model, "sdk_available", lambda: True)
    client = _client(repository)

    saved = client.put("/api/model", json={"enabled": True, "model": "claude-opus-5", "api_key": KEY})
    assert saved.status_code == 200, saved.text
    assert saved.json()["api_key_set"] is True
    assert saved.json()["api_key_source"] == "settings"
    assert saved.json()["ready"] is True
    assert KEY not in saved.text
    assert KEY not in client.get("/api/model").text

    path = model.settings_path(repository)
    assert path.is_file()
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert model.load_settings(repository).api_key == KEY
    # Never in a commit: this project's own `.gitignore` ignores the index
    # directory whole, and the settings file sits inside it.
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", model.MODEL_SETTINGS_RELATIVE_PATH],
        cwd=REPO_ROOT, capture_output=True,
    )
    assert ignored.returncode == 0, f"{model.MODEL_SETTINGS_RELATIVE_PATH} is not gitignored"


def test_an_absent_key_leaves_the_stored_one_and_an_empty_key_clears_it(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)
    client.put("/api/model", json={"enabled": True, "model": "claude-opus-5", "api_key": KEY})

    kept = client.put("/api/model", json={"enabled": False, "model": "claude-sonnet-5"})
    assert kept.json()["api_key_set"] is True
    assert kept.json()["enabled"] is False
    assert kept.json()["model"] == "claude-sonnet-5"
    assert model.load_settings(repository).api_key == KEY

    cleared = client.put("/api/model", json={"enabled": True, "model": "claude-opus-5", "api_key": ""})
    assert cleared.json()["api_key_set"] is False
    assert cleared.json()["reason"] == model.REASON_NO_KEY
    assert model.load_settings(repository).api_key is None


def test_a_key_in_the_environment_is_reported_and_never_written(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    monkeypatch.setenv(model.API_KEY_ENV_VAR, "sk-env")
    client = _client(repository)
    body = client.get("/api/model").json()
    assert body["api_key_set"] is True and body["api_key_source"] == "environment"
    assert body["ready"] is False, "a key alone never switches direct runs on"

    client.put("/api/model", json={"enabled": True, "model": "claude-opus-5"})
    assert "sk-env" not in model.settings_path(repository).read_text(encoding="utf-8")
    assert client.get("/api/model").json()["api_key_source"] == "environment"


def test_an_empty_model_id_is_refused(tmp_path):
    client = _client(_repo(tmp_path))
    assert client.put("/api/model", json={"enabled": True, "model": ""}).status_code == 422


# --- the run routes, off ------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("post", "/api/extraction/run", {"limit": 5}),
        ("post", "/api/sections/SEC-0001/audit", {"limit": 5}),
        ("post", "/api/style/analyse", None),
    ],
)
def test_every_run_route_is_a_409_naming_settings_while_off(tmp_path, method, path, body):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "About Bob.")
    client = _client(repository)
    response = client.post(path, json=body)
    assert response.status_code == 409, response.text
    assert model.SETTINGS_SURFACE in response.json()["detail"]
    assert model.REASON_OFF in response.json()["detail"]


def test_spend_on_this_surface_is_calls_and_model_never_a_token_figure():
    """Part 14 §40 (ADR-0001) keeps token figures off every author-facing
    view; the ledger's `model_call` lines hold them. `SpendOut` is the one
    place spend reaches this surface, so it is pinned here as well as by
    `test_context_manifest.py`'s scan of the whole package."""
    from memoria.web.schemas import SpendOut

    assert set(SpendOut.model_fields) == {"calls", "model"}


def test_the_extraction_status_is_a_read(tmp_path):
    client = _client(_repo(tmp_path))
    body = client.get("/api/extraction").json()
    assert body["paragraphs"] == 2 and body["pending"] == 2 and body["extracted"] == 0
    assert body["summaries_pending"] == 0
    assert body["derived"] is False


# --- the run routes, on --------------------------------------------------------------


def test_the_extraction_runs_in_steps_and_ledgers_under_the_servers_session(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    monkeypatch.setenv("MEMORIA_SESSION_ID", "SES-20260904-1300-web")
    _switch_on(repository, monkeypatch, _reading)
    client = _client(repository)

    first = client.post("/api/extraction/run", json={"limit": 1})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["phase"] == "paragraphs"
    assert (body["paragraphs_read"], body["paragraphs_accepted"], body["paragraphs_remaining"]) == (1, 1, 1)
    assert body["spend"] == {"calls": 1, "model": "fake-model"}
    assert body["rejected"] == []

    while (body := client.post("/api/extraction/run", json={"limit": 10}).json())["phase"] != "done":
        pass
    assert body["finished"] is True
    assert client.get("/api/extraction").json()["pending"] == 0

    events = [
        json.loads(line)
        for line in event_path(repository, "SES-20260904-1300-web").read_text().splitlines()
        if line
    ]
    calls = [e for e in events if e["tool"] == "model_call"]
    assert calls and calls[0]["pass"] == "extraction" and "served" not in calls[0]


def test_a_refused_paragraph_is_reported_by_anchor(tmp_path, monkeypatch):
    repository = _repo(tmp_path, paragraphs=("Bob refused.", "Bob fine."))

    def handler(request):
        if "refused" in request.user:
            return ModelReply(
                text="", stop_reason="refusal",
                usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=0),
                refusal="general_harms",
            )
        return _reading(request)

    _switch_on(repository, monkeypatch, handler)
    body = _client(repository).post("/api/extraction/run", json={}).json()
    assert body["paragraphs_accepted"] == 1
    assert body["rejected"] == [{"anchor": "src-000001-p1", "reason": "the model refused: general_harms"}]


def test_a_provider_failure_is_a_502(tmp_path, monkeypatch):
    repository = _repo(tmp_path)

    def failing(request):
        raise ModelError("anthropic rate-limited the call - try again later")

    _switch_on(repository, monkeypatch, failing)
    response = _client(repository).post("/api/extraction/run", json={})
    assert response.status_code == 502
    assert "rate-limited" in response.json()["detail"]


def test_a_limit_out_of_range_is_a_422(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(repository, monkeypatch, _reading)
    client = _client(repository)
    assert client.post("/api/extraction/run", json={"limit": 0}).status_code == 422
    assert client.post("/api/extraction/run", json={"limit": 999}).status_code == 422


def test_the_audit_button_records_a_sections_judgements(tmp_path, monkeypatch):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _repo(tmp_path, entries=(entry,))
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text("Bob went to town.", encoding="utf-8")

    def handler(request):
        if "kind: engagement" in request.user:
            return {"engages": True, "note": "names Bob"}
        slot = request.user.split("\n", 1)[0].removeprefix("anchor: ").split("|")[0]
        return {
            "clear": False,
            "finding": {
                "disagreement_set": [
                    {"kind": "passage", "ref": slot},
                    {"kind": "entry", "ref": "SUB-people/bob"},
                ],
                "statement": "Town, not market.",
                "confidence": "moderate",
                "patch": "",
            },
        }

    _switch_on(repository, monkeypatch, handler)
    client = _client(repository)
    response = client.post(f"/api/sections/{section.brief.id}/audit", json={"limit": 20})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 2 and body["findings"] == 1 and body["remaining"] == 0
    assert body["spend"]["calls"] == 2
    review = client.get(f"/api/sections/{section.brief.id}/review").json()
    assert any(f["statement"] == "Town, not market." for f in review["findings"])


def test_the_audit_button_on_an_unknown_section_is_a_404(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(repository, monkeypatch, _reading)
    response = _client(repository).post("/api/sections/SEC-0099/audit", json={})
    assert response.status_code == 404


def test_analyse_now_proposes_observations_and_returns_the_style(tmp_path, monkeypatch):
    repository = _repo(tmp_path, paragraphs=("The deck went up unchanged.", "Nobody dared touch it."))
    style.set_style(
        repository,
        style.WritingStyle(direction="Stay in the moment.", sample_sources=("SRC-000001",)),
        None,
        AUTHOR,
    )
    _switch_on(
        repository,
        monkeypatch,
        lambda request: {
            "observations": [
                {"aspect": "rhythm", "observation": "End on the noun.", "example": "Nobody dared touch it."},
                {"aspect": "register", "observation": "Stay plain.", "example": "Never said."},
            ]
        },
    )
    response = _client(repository).post("/api/style/analyse")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"][0]["anchor"] == "2"
    assert [o["observation"] for o in body["style"]["pending"]] == ["End on the noun."]
    assert body["style"]["direction"] == "Stay in the moment."


def test_analyse_now_with_nothing_to_read_is_a_400(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    _switch_on(repository, monkeypatch, lambda request: {"observations": []})
    response = _client(repository).post("/api/style/analyse")
    assert response.status_code == 400
    assert "no samples to analyse" in response.json()["detail"]
