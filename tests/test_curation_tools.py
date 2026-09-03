"""The record extractor's MCP tools (#34): the driving session's surface over
``memoria.record_extractor``, exercised through the server's tool functions
the way ``test_mcp_server`` exercises the read tools - the core does the
work, the adapter renders it, and a refusal reaches the model as a
``ToolError`` carrying the reason rather than a bare exception."""

import json
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from memoria.mcp import server
from memoria.record_extractor import (
    MEMORIA_NOTE_CLOSE,
    RecordExtractorError,
    curation_status,
    find_statement,
)
from memoria.repository import Repository
from memoria.sessions import derive_session, list_sessions
from memoria.subjects import Entry, entry_to_markdown, parse_statements, serve_entry

SESSION_ID = "SES-20260912-1432"
MUSING = "Maybe the deck went up unchanged because nobody dared touch it."
DECISION = "The deck went up unchanged; that is the fact this chapter turns on."
BOB = "SUB-people/bob"
TESTIMONY = "Bob was born in 1962 in Cleveland."
INFERRED = "Fear of losing control appears to intensify after the call."


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    _git(
        tmp_path, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", "initial", "--allow-empty",
    )
    repository = Repository(root=tmp_path)
    server._repository = repository
    return repository


@pytest.fixture(autouse=True)
def _restore_server_repository():
    original = server._repository
    yield
    server._repository = original


def _session(repository: Repository, turns: list[tuple[str, str]]) -> None:
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
    jsonl_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    derive_session(repository, SESSION_ID, jsonl_path)
    _git(repository.root, "add", "sessions")
    _git(repository.root, "commit", "-q", "-m", "derive the session")


def _entry(repository: Repository, entry_id: str, body: str) -> str:
    subject_slug, entry_slug = entry_id[len("SUB-"):].split("/")
    relative_path = f"subjects/{subject_slug}/{entry_slug}.md"
    path = repository.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry_to_markdown(Entry(id=entry_id, body=body)), encoding="utf-8")
    _git(repository.root, "add", relative_path)
    _git(
        repository.root, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", f"add {entry_id}",
    )
    return relative_path


def _hand_edit(repository: Repository, relative_path: str, old: str, new: str) -> None:
    path = repository.root / relative_path
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    _git(repository.root, "add", relative_path)
    _git(repository.root, "commit", "-q", "-m", "hand edit")


# --- decisions and questions -------------------------------------------------


def test_the_musing_lands_open_and_the_decision_lands_author_through_the_tools(tmp_path):
    repository = _repo(tmp_path)
    _session(repository, [("user", MUSING), ("user", DECISION)])

    question = server.record_question(SESSION_ID, 1, MUSING)
    decision = server.record_decision(SESSION_ID, 2, DECISION)

    assert f"[open] {MUSING}" in question and f"{SESSION_ID}#T001" in question
    assert "DEC-0001" in decision and f"[author] {DECISION}" in decision
    assert f"{SESSION_ID}#T002" in decision
    assert f"[open] {MUSING}" in (tmp_path / "questions.md").read_text(encoding="utf-8")
    assert f"[author] {DECISION}" in (tmp_path / "decisions.md").read_text(encoding="utf-8")


def test_an_assistant_turn_offered_as_a_decision_is_refused_with_the_reason(tmp_path):
    """The refusal is the model's only guidance, so it must arrive as a
    ToolError carrying the core's own words - and those words already name
    record_question as where the item belongs."""
    repository = _repo(tmp_path)
    _session(repository, [("assistant", MUSING)])

    with pytest.raises(ToolError, match="record_question"):
        server.record_decision(SESSION_ID, 1, MUSING)

    assert not (tmp_path / "decisions.md").exists()


def test_a_dirty_tree_refuses_through_the_tool_and_status_names_the_file(tmp_path):
    repository = _repo(tmp_path)
    _session(repository, [("user", DECISION)])
    (tmp_path / "decisions.md").write_text("[author] scratch\n", encoding="utf-8")
    _git(tmp_path, "add", "decisions.md")
    _git(tmp_path, "commit", "-q", "-m", "a tracked file")
    (tmp_path / "decisions.md").write_text("[author] scratch, edited\n", encoding="utf-8")

    with pytest.raises(ToolError, match="decisions.md"):
        server.record_decision(SESSION_ID, 1, DECISION)
    assert "uncommitted human modifications: decisions.md" in server.curation_status()


def test_curation_status_lists_sessions_with_and_without_a_transcript(tmp_path):
    repository = _repo(tmp_path)
    ledger_only = tmp_path / "sessions" / "2026" / "09" / "SES-20260901-0900"
    ledger_only.mkdir(parents=True)
    (ledger_only / "events.jsonl").write_text("", encoding="utf-8")
    _session(repository, [("user", DECISION)])
    server.record_decision(SESSION_ID, 1, DECISION)

    status = curation_status(repository)
    assert [(s.session_id, s.has_transcript) for s in status.sessions] == [
        ("SES-20260901-0900", False), (SESSION_ID, True),
    ]
    assert status.decisions == 1 and status.questions == 0 and status.dirty == ()
    rendered = server.curation_status()
    assert "SES-20260901-0900 - no transcript yet" in rendered
    assert f"{SESSION_ID} - transcript derived" in rendered
    assert "decisions recorded: 1" in rendered and "working tree: clean" in rendered


def test_list_sessions_is_empty_without_a_sessions_directory(tmp_path):
    assert list_sessions(_repo(tmp_path)) == []


# --- entry statements ---------------------------------------------------------


def test_record_statement_serves_its_own_token_and_appends(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)

    rendered = server.record_statement(BOB, "inferred", INFERRED, ["SRC-000184 P17"])

    assert f"[inferred] {INFERRED}\n— SRC-000184 ¶17" in rendered
    body = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert f"{TESTIMONY}\n\n[inferred] {INFERRED}\n— SRC-000184 ¶17" in body


def test_an_assertion_without_provenance_is_refused_through_the_tool(tmp_path):
    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    with pytest.raises(ToolError, match="needs provenance"):
        server.record_statement(BOB, "source", INFERRED)


def test_find_statement_matches_a_reflowed_paragraph_and_names_the_rest_on_a_miss(tmp_path):
    repository = _repo(tmp_path)
    _entry(repository, BOB, f"{TESTIMONY}\n\n[inferred] Fear of losing control\nappears to intensify after the call.\n— SRC-000184 ¶17")
    entry, _ = serve_entry(repository, "SUB-people", "bob")

    found = find_statement(entry, "inferred", INFERRED)
    assert found in parse_statements(entry.body)

    with pytest.raises(RecordExtractorError, match=r"the entry has: \[None\] Bob was born"):
        find_statement(entry, "inferred", "Something the entry never said.")


def test_a_hand_edited_statement_is_flagged_and_a_conflict_becomes_a_note(tmp_path):
    """The gate's third act (#34), through the tools: hand-edit a badged
    statement; `curation_flag` reports it; `revise_statement` with
    conflicting evidence appends a Memoria note and leaves the statement's
    bytes exactly as the author left them."""
    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _session(repository, [("user", DECISION)])
    server.record_statement(BOB, "inferred", INFERRED, ["SRC-000184 P17"])
    edited = "Fear of losing control appears to intensify after the call, and never eases."
    _hand_edit(repository, relative_path, INFERRED, edited)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")

    flagged = server.curation_flag()
    assert "newly flagged human-touched: 1" in flagged
    assert f"- {BOB}: [inferred] {edited}" in flagged

    rendered = server.revise_statement(
        BOB, "inferred", edited, "source",
        "Later letters show the fear easing by spring.",
        ["SRC-000190 P2", f"{SESSION_ID}#T1"],
    )

    assert rendered.startswith("not rewritten:")
    assert MEMORIA_NOTE_CLOSE in rendered
    after = (tmp_path / relative_path).read_text(encoding="utf-8")
    statement_end = before.index(edited) + len(edited) + len("\n— SRC-000184 ¶17")
    assert after[:statement_end] == before[:statement_end]
    assert "> **Memoria note — " in after[statement_end:]
    assert f"> See SRC-000190 ¶2 and {SESSION_ID}#T001." in after


def test_a_free_statement_is_rewritten_in_place_through_the_tool(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    server.record_statement(BOB, "inferred", INFERRED, ["SRC-000184 P17"])

    rendered = server.revise_statement(
        BOB, "inferred", INFERRED, "source", "The fear eased by spring.", ["SRC-000190 P2"]
    )

    assert rendered.startswith("rewritten in")
    body = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert "[source] The fear eased by spring.\n— SRC-000190 ¶2" in body
    assert INFERRED not in body


def test_revising_a_statement_that_is_not_there_names_what_is(tmp_path):
    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    with pytest.raises(ToolError, match="no such statement in SUB-people/bob"):
        server.revise_statement(BOB, "inferred", "never written", "open", "x")


# --- the gaps the wrap-up named ------------------------------------------------


def test_list_sessions_sees_the_flat_nesting_the_ledger_falls_back_to(tmp_path):
    """``memoria.ledger.event_path`` nests a dated id under ``sessions/<YYYY>/
    <MM>/`` and an undated one directly under ``sessions/``; both are
    sessions to the pass."""
    repository = _repo(tmp_path)
    flat = tmp_path / "sessions" / "SES-custom"
    flat.mkdir(parents=True)
    (flat / "events.jsonl").write_text("", encoding="utf-8")
    _session(repository, [("user", DECISION)])

    assert [(s.session_id, s.has_transcript) for s in list_sessions(repository)] == [
        (SESSION_ID, True), ("SES-custom", False),
    ]


def test_curation_flag_over_a_repository_with_no_commits_says_so(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    server._repository = Repository(root=tmp_path)

    assert server.curation_flag() == "no commits yet - nothing to flag"


def test_record_statement_author_badge_needs_an_author_turn_through_the_tool(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _session(repository, [("assistant", MUSING), ("user", DECISION)])

    with pytest.raises(ToolError, match="Assistant"):
        server.record_statement(BOB, "author", MUSING, [f"{SESSION_ID}#T1"])

    rendered = server.record_statement(BOB, "author", DECISION, [f"{SESSION_ID}#T2"])

    assert f"[author] {DECISION}\n— {SESSION_ID}#T002" in rendered
    assert f"[author] {DECISION}" in (tmp_path / relative_path).read_text(encoding="utf-8")
