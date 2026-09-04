"""The grilling's session run (ADR-0011): ``grill_brief`` and
``section_create`` on the MCP server, and the ``grill-writing`` skill that
drives them - exercised through the server's own tool functions the way
``test_style_tools`` does."""

import json
import pathlib
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from memoria import grill, manuscript
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.mcp import server
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import write_builtin_subjects

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".claude" / "skills" / "grill-writing" / "SKILL.md"
GRILL_TOOLS = ("grill_brief", "section_create")


@pytest.fixture(autouse=True)
def _reset_server():
    server._repository = None
    server._session_id = None
    yield
    server._repository = None
    server._session_id = None


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _serve(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
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
    _git(tmp_path, "commit", "-q", "-m", "seed")
    server._repository = repository
    return repository


def _ledger(repository):
    path = event_path(repository, server.session_id())
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# --- grill_brief ---------------------------------------------------------------------


def test_grill_brief_serves_the_one_rendering_and_ledgers_what_it_read(tmp_path):
    repository = _serve(tmp_path)

    served = server.grill_brief("CHP-0001", "SRC-000001")

    assert served == grill.render_brief(grill.brief(repository, "CHP-0001", "SRC-000001"))
    assert served.startswith(grill.GRILL_PROMPT)
    assert "The deck went up unchanged." in served
    (line,) = _ledger(repository)
    assert line["tool"] == "grill_brief"
    assert line["served"] == ["CHP-0001", "SRC-000001"]


def test_grill_brief_refuses_an_unknown_chapter_or_source_and_ledgers_nothing(tmp_path):
    repository = _serve(tmp_path)
    with pytest.raises(ToolError, match="no such chapter"):
        server.grill_brief("CHP-0042")
    with pytest.raises(ToolError, match="SRC-000042"):
        server.grill_brief("CHP-0001", "SRC-000042")
    assert _ledger(repository) == []


# --- section_create ----------------------------------------------------------------


def test_section_create_writes_the_section_under_the_confirming_turn(tmp_path):
    repository = _serve(tmp_path)
    session = server.session_id()

    report = server.section_create("CHP-0001", "The evening the street saw it.", "Prose.", 9)

    assert report.startswith("created SEC-0002")
    assert f"authorized by {session}#T009 (SEC-0002 brief)" in report
    assert f"authorized by {session}#T009 (SEC-0002 draft)" in report
    section = manuscript.resolve_section(repository, "SEC-0002")
    assert section.brief.text == "The evening the street saw it."
    assert (section.dir / "draft.md").read_text() == "Prose.\n"
    messages = _git(tmp_path, "log", "--format=%B%x00").split("\x00")
    assert f"authorized-by: {session}#T009" in messages[0]
    assert "authorized-scope: SEC-0002 draft" in messages[0]
    assert "authorized-scope: SEC-0002 brief" in messages[1]


@pytest.mark.parametrize(
    "arguments, message",
    [
        (("CHP-0042", "Brief.", "Prose.", 3), "no such chapter"),
        (("CHP-0001", "", "Prose.", 3), "needs its brief"),
        (("CHP-0001", "Brief.", "", 3), "needs its prose"),
        (("CHP-0001", "Brief.", "Prose.", 0), "1-based"),
    ],
)
def test_section_create_refuses_rather_than_writes_when_it_cannot_be_authorized(
    tmp_path, arguments, message
):
    repository = _serve(tmp_path)
    with pytest.raises(ToolError, match=message):
        server.section_create(*arguments)
    assert len(manuscript.list_sections(repository, 1)) == 1
    assert _git(tmp_path, "status", "--porcelain").strip() == ""


# --- the skill -----------------------------------------------------------------------


def test_the_skill_names_both_tools_waits_for_confirmation_and_holds_no_copy_of_the_prompt():
    text = SKILL.read_text(encoding="utf-8")
    for tool in GRILL_TOOLS:
        assert f"`{tool}" in text, tool
    # The prompt is a package constant served by grill_brief; a second copy
    # would be the one nobody read (docs/tool-surface.md).
    first_rule = grill.GRILL_PROMPT.splitlines()[3]
    assert first_rule not in text
    # One question at a time, a recommended answer with each, the decisions
    # the author's - the /grilling shape - and nothing written before the
    # author confirms.
    assert "one question" in text.lower()
    assert "recommend" in text.lower()
    assert "confirm" in text.lower()
    assert text.index("wait") < text.index("`section_create")
    assert "turn" in text
