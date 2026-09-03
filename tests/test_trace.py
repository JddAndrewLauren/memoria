"""`trace(ref)`: provenance composed from git blame, the commit's trailers,
the session's transcript and its context manifest (#42, part 10 §20).

Real git repositories throughout: the chain starts at `git blame`, and the
point is what blame actually attributes.
"""

import asyncio
import json
import subprocess

import pytest

from memoria import manuscript
from memoria.authorship import (
    Authorization,
    ParagraphTarget,
    apply_rewrite,
    propose_rewrite,
)
from memoria.mcp import server
from memoria.repository import Repository
from memoria.sessions import session_dir
from memoria.trace import TraceError, trace
from memoria.write import checkpoint

SESSION = "SES-20260912-1432"
TURN_TEXT = "Rewrite it using the corrected timeline."


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(tmp_path, draft="Bob went to town.\n\nBob came home late.\n\nCarol wrote.\n"):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    repository = Repository(root=tmp_path)
    chapter = manuscript.create_chapter(repository, "Chapter one.")
    section = manuscript.create_section(repository, chapter.number, "Section one.")
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    checkpoint(repository)
    return repository, section


def _write_session(repository, session_id, turns, events=()):
    """A derived transcript and a ledger for `session_id`, in the shape
    `memoria.sessions` renders and `memoria.ledger` appends."""
    directory = session_dir(repository, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    blocks = [
        f'<a id="t{number:03d}"></a>\n\n## T{number:03d} — {role}\n\n{text}'
        for number, role, text in turns
    ]
    (directory / "transcript.md").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    if events:
        (directory / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )


def _read_event(ref, citation):
    return {
        "session_id": SESSION,
        "timestamp": "2026-09-12T14:33:00+00:00",
        "tool": "read",
        "ref": ref,
        "served": [citation],
        "tokens": 12,
    }


def _ai_rewrite(repository, section, paragraph, text, turn=8):
    proposal = propose_rewrite(repository, section.brief.id, paragraph, text)
    return apply_rewrite(
        repository, proposal,
        Authorization(SESSION, turn, frozenset({ParagraphTarget(section.brief.id, paragraph)})),
    )


# --- the chain, composed ------------------------------------------------------


def test_an_ai_written_paragraph_traces_to_its_commit_turn_and_manifest(tmp_path):
    repository, section = _repo(tmp_path)
    _write_session(
        repository, SESSION,
        [(7, "Assistant", "Shall I?"), (8, "Author", TURN_TEXT)],
        [_read_event("SUB-people/bob", "SUB-people/bob"), _read_event("SRC-000184", "SRC-000184")],
    )
    _ai_rewrite(repository, section, 2, "Bob came home at dusk, by the corrected timeline.")

    result = trace(repository, f"{section.brief.id} ¶2")

    assert result.citation == f"{section.brief.id} ¶2"
    assert result.path == "chapters/01/sections/01/draft.md"
    assert result.text == "Bob came home at dusk, by the corrected timeline."
    assert result.uncommitted_lines == 0
    (step,) = result.steps
    assert step.sha == _git(tmp_path, "log", "-1", "--format=%h").strip()
    assert step.author == "Memoria"
    assert step.lines == 1
    assert step.change_id is None
    assert step.authorized_by == "SES-20260912-1432#T008"
    assert step.authorized_scope == f"{section.brief.id} ¶2"
    assert step.authorizing_turn == TURN_TEXT
    assert step.assembled_from == ("SUB-people/bob", "SRC-000184")


def test_a_paragraph_written_from_assembled_context_traces_to_what_assembly_resolved(tmp_path):
    """Found by the M5 gate walk (#45): a draft authorized from the working
    context assembly produced (#38) - a session that assembled the section
    and read nothing else - traced to an empty `assembled from`, because
    only `read` lines were projected. The `assemble` line names the
    entries and the sources the draft was written from, and the trace
    names them: entries first, then records, as its contract says."""
    repository, section = _repo(tmp_path)
    _write_session(
        repository, SESSION,
        [(8, "Author", TURN_TEXT)],
        [
            {
                "session_id": SESSION,
                "timestamp": "2026-09-12T14:32:30+00:00",
                "tool": "assemble",
                "section_id": section.brief.id,
                "entries": [
                    {
                        "entry_id": "SUB-people/bob",
                        "matched_by": ["bob"],
                        "sources": ["src-000184-p12", "src-000190-p1"],
                    }
                ],
                "fallbacks": [],
                "unconfirmed": False,
                "empty": False,
            },
            _read_event("SRC-000200", "SRC-000200"),
        ],
    )
    _ai_rewrite(repository, section, 2, "Bob came home at dusk, by the corrected timeline.")

    (step,) = trace(repository, f"{section.brief.id} ¶2").steps

    assert step.assembled_from == (
        "SUB-people/bob", "SRC-000200", "SRC-000184 ¶12", "SRC-000190 ¶1"
    )


def test_a_human_written_paragraph_traces_to_its_change_id_and_stops(tmp_path):
    repository, section = _repo(tmp_path)

    result = trace(repository, f"{section.brief.id} ¶1")

    (step,) = result.steps
    assert step.change_id == _git(tmp_path, "log", "-1", "--format=%(trailers:key=change-id,valueonly)").strip()
    assert step.change_id.startswith("CHG-")
    assert step.authorized_by is None
    assert step.authorizing_turn is None
    assert step.assembled_from == ()


def test_an_unrelated_paragraph_keeps_its_own_provenance_after_an_ai_write(tmp_path):
    repository, section = _repo(tmp_path)
    _ai_rewrite(repository, section, 2, "Bob came home at dusk.")

    untouched = trace(repository, f"{section.brief.id} ¶3")

    (step,) = untouched.steps
    assert step.change_id is not None
    assert step.authorized_by is None


def test_a_session_not_yet_derived_leaves_the_turn_unknown_but_the_commit_known(tmp_path):
    repository, section = _repo(tmp_path)
    _ai_rewrite(repository, section, 2, "Bob came home at dusk.")

    (step,) = trace(repository, f"{section.brief.id} ¶2").steps

    assert step.authorized_by == "SES-20260912-1432#T008"
    assert step.authorizing_turn is None
    assert step.assembled_from == ()


def test_a_multi_line_paragraph_touched_by_two_commits_lists_both_most_recent_first(tmp_path):
    repository, section = _repo(
        tmp_path, draft="First line of one,\nsecond line of one.\n\nTwo.\n"
    )
    # A human edits the first line only, so blame splits the paragraph
    # between the checkpoint and this second checkpoint.
    (section.dir / "draft.md").write_text(
        "First line of one, edited,\nsecond line of one.\n\nTwo.\n", encoding="utf-8"
    )
    checkpoint(repository)

    result = trace(repository, f"{section.brief.id} ¶1")

    assert [s.lines for s in result.steps] == [1, 1]
    assert result.steps[0].change_id != result.steps[1].change_id
    assert result.steps[0].change_id == _git(
        tmp_path, "log", "-1", "--format=%(trailers:key=change-id,valueonly)"
    ).strip()


def test_uncommitted_lines_are_counted_not_traced(tmp_path):
    repository, section = _repo(tmp_path)
    (section.dir / "draft.md").write_text(
        "Bob went to town.\n\nBob came home, edited in Obsidian.\n\nCarol wrote.\n",
        encoding="utf-8",
    )

    result = trace(repository, f"{section.brief.id} ¶2")

    assert result.text == "Bob came home, edited in Obsidian."
    assert result.uncommitted_lines == 1
    assert result.steps == ()


def test_a_draft_git_has_never_seen_is_all_uncommitted(tmp_path):
    repository, section = _repo(tmp_path)
    planned = manuscript.create_section(repository, 1, "Planned.")
    (planned.dir / "draft.md").write_text("Never added.\n", encoding="utf-8")

    result = trace(repository, f"{planned.brief.id} ¶1")

    assert result.uncommitted_lines == 1
    assert result.steps == ()


# --- the accepted cost: blame coarsens under reflow (§20) -------------------


def test_a_human_rewrap_after_an_ai_write_is_what_blame_reports(tmp_path):
    """After the author rewraps the AI-written paragraph, every line of it
    was last touched by the rewrap, and the AI commit drops out of the
    chain. The trace says so rather than pretending: the rewrap *is* the
    last thing that touched those lines. This is the documented loss of
    precision, not a defect - and if blame ever attributed a paragraph so
    badly that the account misled, §20 names that as the falsifying
    observation."""
    repository, section = _repo(tmp_path)
    _ai_rewrite(
        repository, section, 2,
        "Bob came home at dusk, by the corrected timeline, and said nothing to Carol.",
    )
    (section.dir / "draft.md").write_text(
        "Bob went to town.\n\n"
        "Bob came home at dusk,\nby the corrected timeline,\nand said nothing to Carol.\n\n"
        "Carol wrote.\n",
        encoding="utf-8",
    )
    checkpoint(repository)

    result = trace(repository, f"{section.brief.id} ¶2")

    assert all(step.change_id is not None for step in result.steps)
    assert all(step.authorized_by is None for step in result.steps)
    assert sum(step.lines for step in result.steps) == 3


# --- what trace refuses ---------------------------------------------------------


@pytest.mark.parametrize("ref", ["SEC-0001", "CHP-0001", "SRC-000184 ¶1", "docs/plan.md", "BOOK"])
def test_trace_takes_only_a_section_paragraph(tmp_path, ref):
    repository, _ = _repo(tmp_path)

    with pytest.raises(TraceError, match="one paragraph of a section"):
        trace(repository, ref)


def test_trace_names_a_missing_section_or_paragraph(tmp_path):
    repository, section = _repo(tmp_path)

    with pytest.raises(TraceError, match="SEC-0042"):
        trace(repository, "SEC-0042 ¶1")
    with pytest.raises(TraceError, match="no ¶9"):
        trace(repository, f"{section.brief.id} ¶9")


def test_trace_stores_nothing(tmp_path):
    repository, section = _repo(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts}

    trace(repository, f"{section.brief.id} ¶1")

    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert after == before
    assert _git(tmp_path, "status", "--porcelain") == ""


# --- the MCP tool ---------------------------------------------------------------


@pytest.fixture
def _server_repository(tmp_path):
    previous = server._repository, server._session_id
    yield
    server._repository, server._session_id = previous


def test_the_server_registers_a_trace_tool():
    tools = asyncio.run(server.mcp.list_tools())

    (tool,) = [t for t in tools if t.name == "trace"]
    assert set(tool.input_schema["properties"]) == {"ref"}
    assert "why" in (tool.description or "").lower()


def test_the_trace_tool_renders_the_chain_and_ledgers_what_it_served(tmp_path, _server_repository):
    repository, section = _repo(tmp_path)
    _write_session(
        repository, SESSION, [(8, "Author", TURN_TEXT)],
        [_read_event("SUB-people/bob", "SUB-people/bob")],
    )
    _ai_rewrite(repository, section, 2, "Bob came home at dusk.")
    server._repository = repository
    server._session_id = "SES-20260913-0900"

    rendered = server.trace(f"{section.brief.id} P2")

    assert rendered.startswith(
        f"ref: {section.brief.id} ¶2\npath: chapters/01/sections/01/draft.md\n---\n"
        "Bob came home at dusk.\n---\n"
    )
    assert "authorized by: SES-20260912-1432#T008" in rendered
    assert TURN_TEXT in rendered
    assert "assembled from: SUB-people/bob" in rendered
    events = (session_dir(repository, "SES-20260913-0900") / "events.jsonl").read_text()
    (event,) = [json.loads(line) for line in events.splitlines()]
    assert event["tool"] == "trace"
    assert event["served"] == [f"{section.brief.id} ¶2", "SES-20260912-1432#T008"]


def test_the_trace_tool_maps_a_core_error_onto_one_the_model_can_read(tmp_path, _server_repository):
    from mcp.server.mcpserver.exceptions import ToolError

    repository, _ = _repo(tmp_path)
    server._repository = repository

    with pytest.raises(ToolError, match="SEC-0042"):
        server.trace("SEC-0042 ¶1")
