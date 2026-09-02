"""The extraction's tools and the skill that drives them (#17)."""

import ast
import asyncio
import json
import pathlib
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from memoria import extraction as ex
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.mcp import server
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = REPO_ROOT / ".claude" / "skills" / "extraction" / "SKILL.md"

EXTRACTION_TOOLS = (
    "extraction_brief",
    "extraction_next_paragraphs",
    "extraction_record",
    "extraction_derive",
    "extraction_next_summary",
    "extraction_record_summary",
    "extraction_status",
    "extraction_finish",
    "extraction_candidates",
    "extraction_unplaced_forms",
    "extraction_cluster",
    "extraction_promote_candidate",
    "extraction_promote_cluster",
)


@pytest.fixture(autouse=True)
def _reset_server():
    server._repository = None
    server._session_id = None
    yield
    server._repository = None
    server._session_id = None


def _serve(tmp_path, paragraphs, entries=(), auto_promote=()):
    repository = Repository(root=tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_builtin_subjects(repository)
    for subject_id in auto_promote:
        path = tmp_path / "subjects" / subject_id[len("SUB-") :] / "_subject.md"
        path.write_text(
            path.read_text().replace("auto-promote: false", "auto-promote: true")
        )
    for entry in entries:
        subject_slug, slug = entry.id[len("SUB-") :].split("/", 1)
        (tmp_path / "subjects" / subject_slug / f"{slug}.md").write_text(
            entry_to_markdown(entry)
        )
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.email=a@b.test", "-c",
         "user.name=A", "commit", "-qm", "seed"],
        check=True,
    )
    record = NormalizedRecord(
        id="SRC-000001",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=paragraphs,
    )
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    server._repository = repository
    return repository


def _recorded(anchor, unplaced=(), placements=(), relations=()):
    return ex.RecordedParagraph(
        anchor=anchor,
        placements=[ex.RecordedPlacement(*p) for p in placements],
        unplaced=[ex.RecordedForm(*u) for u in unplaced],
        relations=[ex.RecordedRelation(*r) for r in relations],
    )


def _ledger(repository):
    path = event_path(repository, server.session_id())
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# --- the surface -------------------------------------------------------------


def test_the_server_registers_every_extraction_tool_with_its_arguments():
    """One SDK-touching test for all of them, so a rename breaks one place."""
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}

    for name in EXTRACTION_TOOLS:
        assert name in tools

    assert set(tools["extraction_record_summary"].input_schema["required"]) == {
        "cluster_id",
        "membership",
        "summary",
    }
    results = tools["extraction_record"].input_schema["properties"]["results"]
    assert results["type"] == "array"
    recorded = tools["extraction_record"].input_schema["$defs"]["RecordedParagraph"]
    assert set(recorded["properties"]) == {
        "anchor",
        "placements",
        "unplaced",
        "relations",
    }


def test_each_extraction_tool_calls_one_core_function_and_renders():
    """The adapter is an adapter (§40.1). It holds no rule the CLI and the web
    app lack, so each tool body reaches into `memoria.extraction` at most a
    couple of times and renders what comes back - it does not compute."""
    source = (REPO_ROOT / "src" / "memoria" / "mcp" / "server.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in EXTRACTION_TOOLS:
            continue
        core_calls = [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "extraction"
        ]
        assert core_calls, f"{node.name} calls no core function"
        assert len(core_calls) <= 3, (
            f"{node.name} makes {len(core_calls)} core calls - the logic is "
            "drifting into the adapter"
        )


def test_the_adapter_still_opens_no_database_with_the_extraction_tools_in_it():
    """The three purity tests in `test_mcp_server.py` cover this by allowlist;
    this states the consequence that matters for #17 specifically, since the
    extraction is the first thing on this server backed by SQL."""
    source = (REPO_ROOT / "src" / "memoria" / "mcp" / "server.py").read_text()
    assert "sqlite3" not in source
    assert "INDEX_RELATIVE_PATH" not in source


# --- serving -----------------------------------------------------------------


def test_the_brief_serves_the_extraction_prompt_verbatim(tmp_path):
    """The bytes served are the bytes hashed into every memo row. If they ever
    diverge, the cache describes a prompt nobody ran."""
    _serve(tmp_path, ["A paragraph."])

    assert ex.EXTRACTION_PROMPT in server.extraction_brief()


def test_the_brief_serves_the_subjects_and_the_entries_that_exist(tmp_path):
    _serve(
        tmp_path,
        ["A paragraph."],
        entries=[Entry(id="SUB-people/bob", match_terms=["Bob"], body="")],
    )

    rendered = server.extraction_brief()

    assert "SUB-people" in rendered
    assert "Do not merge people sharing a surname" in rendered or "surname" in rendered
    assert "SUB-people/bob" in rendered


def test_the_brief_says_so_when_no_entry_exists_yet(tmp_path):
    """A fresh archive, which is the state the extraction exists for."""
    _serve(tmp_path, ["A paragraph."])

    assert "None yet" in server.extraction_brief()


def test_next_paragraphs_serves_only_what_has_not_been_read(tmp_path):
    _serve(tmp_path, ["One.", "Two."])
    server.extraction_record([_recorded("src-000001-p1")])

    rendered = server.extraction_next_paragraphs()

    assert "src-000001-p2" in rendered
    assert "src-000001-p1" not in rendered


def test_next_paragraphs_serves_the_text_verbatim_and_contiguously(tmp_path):
    """The same contract `read` keeps: never wrapped, re-indented or escaped."""
    text = "A paragraph with  odd   spacing and a — dash."
    _serve(tmp_path, [text])

    assert text in server.extraction_next_paragraphs()


def test_a_fully_read_corpus_says_so_rather_than_returning_nothing(tmp_path):
    _serve(tmp_path, ["One."])
    server.extraction_record([_recorded("src-000001-p1")])

    assert server.extraction_next_paragraphs() == "No paragraphs need extraction."


# --- recording ---------------------------------------------------------------


def test_recording_a_batch_accepts_the_good_and_names_the_rejected(tmp_path):
    """Batch in, per element out. A malformed reading costs one paragraph
    rather than the nineteen good ones beside it."""
    _serve(tmp_path, ["One.", "Two.", "Three."])

    rendered = server.extraction_record(
        [
            _recorded("src-000001-p1", unplaced=[("Bob", "SUB-people")]),
            _recorded("src-000001-p2", placements=[("SUB-people/ghost", "Ghost")]),
            _recorded("src-000001-p3"),
        ]
    )

    assert "accepted 2 of 3" in rendered
    assert "not a promoted entry" in rendered
    assert len(ex.pending_paragraphs(tmp_path and server.repository())) == 1


def test_a_relation_to_something_not_placed_here_is_rejected(tmp_path):
    """The mistake most worth being told about - reaching past this paragraph
    into another one, or into what the model already knows."""
    _serve(
        tmp_path,
        ["One."],
        entries=[Entry(id="SUB-people/bob", match_terms=["Bob"], body="")],
    )

    rendered = server.extraction_record(
        [
            _recorded(
                "src-000001-p1",
                placements=[("SUB-people/bob", "Bob")],
                relations=[("SUB-people/bob", "meets", "SUB-people/carol")],
            )
        ]
    )

    assert "accepted 0 of 1" in rendered
    assert "not among this paragraph's placements" in rendered


def test_a_relation_cannot_name_a_second_paragraph_at_all():
    """Held by the type rather than by the prompt: there is no field for it."""
    fields = ex.RecordedRelation.__dataclass_fields__
    assert set(fields) == {"from_ref", "verb", "to_ref"}
    assert "anchor" not in fields


def test_an_unknown_anchor_reaches_the_model_with_its_reason_intact(tmp_path):
    _serve(tmp_path, ["One."])

    rendered = server.extraction_record([_recorded("src-999999-p1")])

    assert "not a paragraph of this archive" in rendered


def test_an_empty_batch_is_a_tool_error(tmp_path):
    _serve(tmp_path, ["One."])

    with pytest.raises(ToolError):
        server.extraction_record([])


# --- derive, summaries, finish -----------------------------------------------


def test_derive_reports_raw_and_filtered_candidate_counts(tmp_path):
    """AC 5 at the surface. The gap between the two numbers is the size of
    what the recurrence filter is setting aside, and a filter whose cost is
    never printed is one nobody argues with."""
    _serve(tmp_path, ["One.", "Two."])
    server.extraction_record(
        [
            _recorded(f"src-000001-p{n}", unplaced=[("Bob", "SUB-people")])
            for n in (1, 2)
        ]
    )

    rendered = server.extraction_derive(recurrence_threshold=2)

    assert "SUB-people: raw 1 -> filtered 1 (threshold 2)" in rendered


def test_a_parent_summary_task_serves_no_paragraph_text(tmp_path):
    """AC 15 at the surface: an upper level is a compression of a compression,
    so there is nothing below for it to reach for."""
    task = ex.PendingSummary(
        cluster_id="CL-abc",
        level=0,
        label="SUB-people/bob",
        memo_key="k",
        child_summaries=("A child summary.",),
    )

    rendered = server.render_summary_task(task, 1, ex.CLUSTER_SUMMARY_PROMPT)

    assert "A child summary." in rendered
    assert "Its member paragraphs" not in rendered


def test_recording_a_summary_under_a_stale_membership_is_a_tool_error(tmp_path):
    _serve(tmp_path, ["Bob."] * 3)
    server.extraction_record(
        [
            _recorded(f"src-000001-p{n}", unplaced=[("Bob", "SUB-people")])
            for n in (1, 2, 3)
        ]
    )
    server.extraction_derive(recurrence_threshold=1)
    cluster_id = ex.pending_cluster_summaries(server.repository())[0].cluster_id

    with pytest.raises(ToolError, match="re-clustered"):
        server.extraction_record_summary(cluster_id, "stale", "A summary.")


def test_finish_promotes_only_under_a_subject_that_declares_it(tmp_path):
    _serve(tmp_path, ["Bob."] * 3, auto_promote=["SUB-people"])
    server.extraction_record(
        [
            _recorded(
                f"src-000001-p{n}",
                unplaced=[("Bob", "SUB-people"), ("the acquisition", "SUB-events")],
            )
            for n in (1, 2, 3)
        ]
    )

    rendered = server.extraction_finish(recurrence_threshold=1)

    assert "SUB-people/bob" in rendered
    assert "SUB-events" not in rendered.split("auto-promoted:")[1]
    assert "asserted nothing" in rendered


def test_finish_before_the_corpus_is_read_is_a_tool_error(tmp_path):
    _serve(tmp_path, ["One.", "Two."])
    server.extraction_record([_recorded("src-000001-p1")])

    with pytest.raises(ToolError, match="not fully extracted"):
        server.extraction_finish()


# --- the ledger --------------------------------------------------------------


def test_the_author_can_list_and_promote_a_waiting_candidate(tmp_path):
    """AC 8 and the issue's "wait, ranked, for a one-key promotion": the
    surface has to reach the candidate, or nothing under a subject declaring
    `auto-promote: no` can ever become an entry."""
    _serve(tmp_path, ["Carol."] * 3)
    server.extraction_record(
        [_recorded(f"src-000001-p{n}", unplaced=[("Carol", "SUB-people")]) for n in (1, 2, 3)]
    )
    server.extraction_derive(recurrence_threshold=2)

    listed = server.extraction_candidates()
    candidate_id = listed.split()[0]
    assert "SUB-people" in listed and "x3" in listed
    assert server.extraction_candidates(rejected=True) == "No candidates below the filter."

    rendered = server.extraction_promote_candidate(candidate_id)

    assert rendered.startswith("promoted SUB-people/carol")
    assert (tmp_path / "subjects" / "people" / "carol.md").exists()
    server.extraction_derive(recurrence_threshold=2)
    assert server.extraction_candidates() == "No candidates waiting."


def test_rejected_candidates_and_unplaced_forms_are_enumerable(tmp_path):
    """AC 9. Both miss rates are countable only if the misses can be listed."""
    _serve(tmp_path, ["One.", "Two."])
    server.extraction_record(
        [
            _recorded("src-000001-p1", unplaced=[("Bob", "SUB-people")]),
            _recorded("src-000001-p2", unplaced=[("Bob", "SUB-people"), ("Zed", "")]),
        ]
    )
    server.extraction_derive(recurrence_threshold=5)

    assert "Bob  x2" in server.extraction_candidates(rejected=True)
    unplaced = server.extraction_unplaced_forms()
    assert "src-000001-p2  'Zed'" in unplaced
    assert "src-000001-p1  'Bob'" in unplaced


def test_a_cluster_opens_to_its_members_paragraphs_and_children(tmp_path):
    """AC 12 at the surface, and how the author reads a cluster before
    promoting it."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    _serve(tmp_path, ["Bob and the acquisition."] * 3, entries=entries)
    server.extraction_record(
        [
            _recorded(
                f"src-000001-p{n}",
                placements=[
                    ("SUB-people/bob", "Bob"),
                    ("SUB-events/acquisition", "the acquisition"),
                ],
            )
            for n in (1, 2, 3)
        ]
    )
    server.extraction_derive(recurrence_threshold=1)
    task = server.extraction_next_summary()
    cluster_id = task.split("cluster: ")[1].split()[0]

    rendered = server.extraction_cluster(cluster_id)

    assert "members: SUB-events/acquisition, SUB-people/bob" in rendered
    assert "paragraphs: src-000001-p1, src-000001-p2, src-000001-p3" in rendered
    assert "summary: not yet written" in rendered
    with pytest.raises(ToolError):
        server.extraction_cluster("CL-nope")

    rendered = server.extraction_promote_cluster(cluster_id, subject_id="SUB-arcs")

    assert rendered.startswith("promoted SUB-arcs/")
    assert "SUB-people/bob" in rendered


def test_a_served_batch_is_ledgered_by_anchor(tmp_path):
    """Across a pass this is the largest delivery of evidence into a model's
    context anywhere in the system; an account that omitted it would be
    confidently wrong about the one session that read everything."""
    repository = _serve(tmp_path, ["One.", "Two."])

    server.extraction_next_paragraphs()

    entries = [e for e in _ledger(repository) if e["tool"] == "extraction_next_paragraphs"]
    assert entries[0]["served"] == ["src-000001-p1", "src-000001-p2"]


def test_a_memo_hit_is_never_ledgered(tmp_path):
    """Falls out rather than being arranged: the batch only ever carries
    paragraphs with no cached reading."""
    repository = _serve(tmp_path, ["One."])
    server.extraction_record([_recorded("src-000001-p1")])
    before = len(_ledger(repository))

    server.extraction_next_paragraphs()

    assert len(_ledger(repository)) == before


def test_recording_and_deriving_ledger_nothing(tmp_path):
    """The ledger records what was served to the model, not what it did."""
    repository = _serve(tmp_path, ["One."])
    server.extraction_record([_recorded("src-000001-p1")])
    before = len(_ledger(repository))

    server.extraction_derive()
    server.extraction_status()

    assert len(_ledger(repository)) == before


# --- the skill ---------------------------------------------------------------


def test_the_skill_exists_and_declares_its_name():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: extraction" in text


def test_the_skill_names_every_extraction_tool():
    """A tool rename must not silently orphan the skill that drives it."""
    text = SKILL.read_text(encoding="utf-8")
    for name in EXTRACTION_TOOLS:
        assert name in text, f"the skill never mentions {name}"


def test_the_skill_carries_no_copy_of_the_extraction_prompt():
    """Two copies would mean the hash covers the one nobody read."""
    text = SKILL.read_text(encoding="utf-8")
    for paragraph in ex.EXTRACTION_PROMPT.split("\n\n"):
        stripped = paragraph.strip()
        if len(stripped) > 120:
            assert stripped not in text


def test_the_skill_makes_the_author_confirm_before_the_pass_runs():
    """Part 08 §12.1: nothing needing a model runs unasked. The tools are
    registered in every session, so this gate is where that rule lives."""
    text = SKILL.read_text(encoding="utf-8")
    assert "extraction_status()" in text
    assert "ask" in text.lower()
