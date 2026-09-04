"""The writing-style tools and the skill that drives them (ADR-0009):
``writing_style`` served to a writer, and the ``style_*`` analysis - the
same serve-then-record shape as the extraction, exercised through the
server's own tool functions the way ``test_extraction_tools`` does."""

import json
import pathlib
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from memoria import style
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.manuscript import create_chapter, create_section
from memoria.mcp import server
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.write import Actor

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".claude" / "skills" / "writing-style" / "SKILL.md"
AUTHOR = Actor(name="Local Author", email="local@memoria.test")
STYLE_TOOLS = ("writing_style", "style_status", "style_brief", "style_record")


@pytest.fixture(autouse=True)
def _reset_server():
    server._repository = None
    server._session_id = None
    yield
    server._repository = None
    server._session_id = None


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _serve(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
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
    _git(tmp_path, "commit", "-q", "-m", "seed")
    server._repository = repository
    return repository


def _ledger(repository):
    path = event_path(repository, server.session_id())
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _set_style(repository, **overrides):
    fields = dict(direction="Stay in the moment.", observations=(), sample_sources=("SRC-000001",))
    fields.update(overrides)
    return style.set_style(repository, style.WritingStyle(**fields), None, AUTHOR)


# --- writing_style ------------------------------------------------------------


def test_writing_style_says_when_none_is_set_and_ledgers_nothing(tmp_path):
    repository = _serve(tmp_path)

    assert server.writing_style().startswith("No writing style is set.")
    assert _ledger(repository) == []


def test_writing_style_serves_the_one_rendering_and_ledgers_the_file(tmp_path):
    repository = _serve(tmp_path)
    _set_style(repository, observations=("Keep sentences short.",))

    served = server.writing_style()

    assert served == style.writing_style_prompt(style.load_style(repository))
    assert "Keep sentences short." in served
    (line,) = _ledger(repository)
    assert line["tool"] == "writing_style"
    assert line["served"] == [style.STYLE_RELATIVE_PATH]


def test_audit_pending_prints_the_style_above_a_batch_and_never_on_an_empty_target(tmp_path):
    repository = _serve(tmp_path)
    directory = tmp_path / "subjects" / "people"
    (directory / "bob.md").write_text(
        entry_to_markdown(Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")),
        encoding="utf-8",
    )
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text("Bob went to town.", encoding="utf-8")
    _set_style(repository, observations=("Keep sentences short.",))

    served = server.audit_pending(chapter_number=chapter.number)
    assert served.startswith("A proposed rewrite (a finding's patch) follows this writing style.")
    assert "Keep sentences short." in served
    assert "anchor:" in served

    empty = create_chapter(repository, "Empty.")
    assert server.audit_pending(chapter_number=empty.number) == (
        "Nothing to audit in this target - every judgement is current."
    )


# --- the analysis -------------------------------------------------------------


def test_style_status_names_the_empty_state(tmp_path):
    _serve(tmp_path)
    status = server.style_status()
    assert "writing style: none yet" in status
    assert "Nothing to analyse" in status


def test_style_brief_refuses_with_nothing_chosen(tmp_path):
    repository = _serve(tmp_path)
    with pytest.raises(ToolError, match="choose sources or upload"):
        server.style_brief()
    assert _ledger(repository) == []


def test_style_brief_serves_the_prompt_the_samples_and_ledgers_them(tmp_path):
    repository = _serve(tmp_path)
    _set_style(repository)
    style.add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)

    served = server.style_brief()

    assert served.startswith(style.STYLE_ANALYSIS_PROMPT)
    assert "Stay in the moment." in served
    assert "### SRC-000001 - Journal I" in served
    assert "The deck went up unchanged.\n\nNobody dared touch it." in served
    assert "### style/samples/letter.md - letter" in served
    (line,) = _ledger(repository)
    assert line["tool"] == "style_brief"
    assert line["served"] == ["SRC-000001", "style/samples/letter.md"]


def test_style_record_reports_per_element_and_writes_no_style(tmp_path):
    repository = _serve(tmp_path)
    _set_style(repository)

    outcome = server.style_record(
        [
            style.RecordedObservation("rhythm", "Keep it short.", "Nobody dared touch it."),
            style.RecordedObservation("rhythm", "Made up.", "With love, as ever."),
        ]
    )

    assert outcome.splitlines()[0] == "accepted 1 of 2 - awaiting the author in Settings"
    assert "rejected #2 - example is not in the samples verbatim" in outcome
    assert style.load_style(repository).observations == ()
    assert [o.observation for o in style.pending_observations(repository)] == ["Keep it short."]
    assert "observations proposed, awaiting the author: 1" in server.style_status()


def test_style_record_refuses_an_empty_batch_and_nothing_chosen(tmp_path):
    _serve(tmp_path)
    with pytest.raises(ToolError, match="no observations"):
        server.style_record([])
    with pytest.raises(ToolError, match="choose sources or upload"):
        server.style_record([style.RecordedObservation("a", "b", "c")])


# --- the skill ----------------------------------------------------------------


def test_the_skill_names_every_analysis_tool_and_holds_no_copy_of_the_prompt():
    text = SKILL.read_text(encoding="utf-8")
    # `writing_style` is the writer's tool, not the skill's: the skill
    # names it only to say a writing session calls it itself.
    for tool in STYLE_TOOLS:
        assert tool in text, tool
    for tool in STYLE_TOOLS[1:]:
        assert f"`{tool}" in text, tool
    # The prompt is a package constant served by style_brief; a second copy
    # would be the one nobody read (docs/tool-surface.md).
    first_rule = style.STYLE_ANALYSIS_PROMPT.splitlines()[2]
    assert first_rule not in text
    assert "ask" in text.lower() and "Settings" in text
