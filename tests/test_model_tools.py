"""The direct-run tools (ADR-0010): ``model_status`` and the three ``*_run``
tools, exercised through the server's own functions the way
``test_extraction_tools`` does. Every run refuses until the author switched
direct runs on; with the switch on, the seam is replaced by a scripted fake
and no socket is opened.
"""

import json
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from memoria import extraction as ex, model, style
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.manuscript import create_chapter, create_section
from memoria.mcp import server
from memoria.model import ModelError, ModelReply, ModelUsage
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.write import Actor

AUTHOR = Actor(name="Local Author", email="local@memoria.test")
RUN_TOOLS = ("model_status", "extraction_run", "audit_run", "style_run")


@pytest.fixture(autouse=True)
def _reset_server(monkeypatch):
    monkeypatch.delenv(model.API_KEY_ENV_VAR, raising=False)
    server._repository = None
    server._session_id = None
    yield
    server._repository = None
    server._session_id = None


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _serve(tmp_path, paragraphs=("Bob and the acquisition.", "Bob again."), entries=()):
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
    server._repository = repository
    return repository


def _switch_on(repository, monkeypatch, handler):
    """The author's switch, plus a fake standing where the SDK would."""
    model.save_settings(repository, model.ModelSettings(enabled=True, api_key="sk-test"))
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


def _ledger(repository):
    path = event_path(repository, server.session_id())
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# --- off by default --------------------------------------------------------------


def test_the_server_registers_the_run_tools():
    import asyncio

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert set(RUN_TOOLS) <= names


def test_model_status_says_off_on_a_fresh_repository(tmp_path):
    _serve(tmp_path)
    rendered = server.model_status()
    assert rendered.startswith("direct runs: off")
    assert "not ready" in rendered
    assert model.SETTINGS_SURFACE in rendered
    assert "API key: not set" in rendered


@pytest.mark.parametrize(
    "call",
    [
        lambda: server.extraction_run(),
        lambda: server.audit_run(chapter_number=1),
        lambda: server.style_run(),
    ],
)
def test_every_run_refuses_while_direct_runs_are_off(tmp_path, call):
    _serve(tmp_path)
    with pytest.raises(ToolError) as caught:
        call()
    assert model.SETTINGS_SURFACE in str(caught.value)
    assert model.REASON_OFF in str(caught.value)
    assert _ledger(server._repository) == [], "a refused run ledgers nothing"


def test_a_key_in_the_environment_does_not_switch_direct_runs_on(tmp_path, monkeypatch):
    _serve(tmp_path)
    monkeypatch.setenv(model.API_KEY_ENV_VAR, "sk-env")
    rendered = server.model_status()
    assert "direct runs: off" in rendered
    assert "API key: set (from the environment)" in rendered
    with pytest.raises(ToolError):
        server.extraction_run()


def test_model_status_names_the_missing_key_when_switched_on_without_one(tmp_path):
    repository = _serve(tmp_path)
    model.save_settings(repository, model.ModelSettings(enabled=True))
    rendered = server.model_status()
    assert "direct runs: on" in rendered
    assert model.REASON_NO_KEY in rendered
    with pytest.raises(ToolError) as caught:
        server.style_run()
    assert model.REASON_NO_KEY in str(caught.value)


def test_model_status_never_shows_the_key(tmp_path, monkeypatch):
    repository = _serve(tmp_path)
    _switch_on(repository, monkeypatch, _reading)
    rendered = server.model_status()
    assert "ready" in rendered and "sk-test" not in rendered
    assert "API key: set (from the settings)" in rendered
    assert "model: claude-opus-5" in rendered


# --- with the switch on ------------------------------------------------------------


def test_extraction_run_steps_through_the_pass_and_ledgers_spend(tmp_path, monkeypatch):
    repository = _serve(tmp_path)
    seen = _switch_on(repository, monkeypatch, _reading)

    first = server.extraction_run(limit=1)
    assert first.startswith("phase: paragraphs")
    assert "paragraphs read: 1, recorded: 1, still awaiting extraction: 1" in first
    assert "metered: 1 call(s), 7 tokens in / 3 out, on fake-model" in first
    assert "call extraction_run again" in first

    server.extraction_run(limit=1)
    closing = server.extraction_run(limit=10)
    assert closing.startswith("phase: ")
    assert "pass closed" in closing

    while "phase: done" not in (last := server.extraction_run(limit=10)):
        pass
    assert "The extraction asserted nothing." in last
    assert "metered: no calls made" in last
    assert ex.pending_paragraphs(repository) == []
    assert len(seen) >= 2

    calls = [e for e in _ledger(repository) if e["tool"] == "model_call"]
    assert calls and calls[0]["pass"] == "extraction"
    assert all("served" not in c for c in calls)


def test_extraction_run_reports_a_refused_paragraph_by_anchor(tmp_path, monkeypatch):
    repository = _serve(tmp_path, paragraphs=("Bob refused.", "Bob fine."))

    def handler(request):
        if "refused" in request.user:
            return ModelReply(
                text="",
                stop_reason="refusal",
                usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=0),
                refusal="general_harms",
            )
        return _reading(request)

    _switch_on(repository, monkeypatch, handler)
    rendered = server.extraction_run()
    assert "rejected src-000001-p1 - the model refused: general_harms" in rendered
    assert "recorded: 1" in rendered


def test_extraction_run_rejects_a_limit_below_one(tmp_path, monkeypatch):
    repository = _serve(tmp_path)
    _switch_on(repository, monkeypatch, _reading)
    with pytest.raises(ToolError):
        server.extraction_run(limit=0)


def test_a_provider_failure_becomes_a_tool_error(tmp_path, monkeypatch):
    repository = _serve(tmp_path)

    def failing(request):
        raise ModelError("anthropic rate-limited the call - try again later")

    _switch_on(repository, monkeypatch, failing)
    with pytest.raises(ToolError) as caught:
        server.extraction_run()
    assert "rate-limited" in str(caught.value)


def test_audit_run_records_a_sections_judgements(tmp_path, monkeypatch):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _serve(tmp_path, entries=(entry,))
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text("Bob went to town.", encoding="utf-8")

    def handler(request):
        if "kind: engagement" in request.user:
            return {"engages": True, "note": "names Bob"}
        return {"clear": True, "finding": {"disagreement_set": [], "statement": "", "confidence": "", "patch": ""}}

    _switch_on(repository, monkeypatch, handler)
    rendered = server.audit_run(chapter_number=chapter.number, section_number=section.number)
    assert "judgements recorded: 2 (0 finding(s)); still awaiting audit: 0" in rendered
    assert "metered: 2 call(s)" in rendered
    assert "call audit_run again" not in rendered
    assert server.audit_pending(chapter_number=chapter.number, section_number=section.number) == (
        "Nothing to audit in this target - every judgement is current."
    )


def test_audit_run_refuses_a_passage_without_its_section(tmp_path, monkeypatch):
    repository = _serve(tmp_path)
    _switch_on(repository, monkeypatch, _reading)
    with pytest.raises(ToolError):
        server.audit_run(chapter_number=1, paragraph_index=1)
    with pytest.raises(ToolError):
        server.audit_run(chapter_number=1, limit=0)


def test_style_run_proposes_observations_for_settings(tmp_path, monkeypatch):
    repository = _serve(tmp_path, paragraphs=("The deck went up unchanged.", "Nobody dared touch it."))
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
    rendered = server.style_run()
    assert rendered.startswith("observations proposed: 1 - awaiting the author in Settings")
    assert "rejected 2 - example is not in the samples verbatim" in rendered
    assert len(style.pending_observations(repository)) == 1


def test_style_run_refuses_with_nothing_to_analyse(tmp_path, monkeypatch):
    repository = _serve(tmp_path)
    _switch_on(repository, monkeypatch, lambda request: {"observations": []})
    with pytest.raises(ToolError) as caught:
        server.style_run()
    assert "no samples to analyse" in str(caught.value)
