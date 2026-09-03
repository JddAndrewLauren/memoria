"""The record extractor: decisions, questions, research memos (#30).

A real git repository, like ``test_write.py``'s own fixture: the point under
test is what actually lands on disk and in git, not a mock of either. A real
derived session, via ``sessions.derive_session`` from a hand-built JSONL, the
same shape ``test_sessions.py`` uses - so a turn's role here is exactly what
``transcript.md`` itself says it is, never asserted independently of it.
"""

import json
import subprocess
from pathlib import Path

import pytest

from memoria.record_extractor import (
    CURATOR,
    RecordExtractorError,
    ResearchMemo,
    next_decision_id,
    next_research_memo_id,
    read_decision,
    read_research_memo,
    record_decision,
    record_question,
    record_research_memo,
    record_statement,
)
from memoria.records import ReadError
from memoria.records import read as records_read
from memoria.repository import Repository
from memoria.sessions import derive_session

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "memoria"

MUSING = "Maybe we could keep Bob's knowledge ambiguous until chapter 9."
DECISION = "Let's keep Bob's knowledge ambiguous until chapter 9."


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
    return Repository(root=tmp_path)


def _jsonl_entry(uuid, parent, role, text, timestamp):
    return {
        "uuid": uuid,
        "parentUuid": parent,
        "type": role,
        "timestamp": timestamp,
        "sessionId": "claude-code-session-uuid",
        "message": {"role": role, "content": text},
    }


def _session(repository: Repository, session_id: str, turns: list[tuple[str, str]]) -> str:
    """Derive a session whose turns are ``(role, text)`` pairs - ``role`` is
    ``"user"`` (renders ``Author``) or ``"assistant"``."""
    entries = []
    parent = None
    for number, (role, text) in enumerate(turns, start=1):
        uuid = f"u{number}"
        entries.append(
            _jsonl_entry(uuid, parent, role, text, f"2026-09-12T14:{30 + number:02d}:00+00:00")
        )
        parent = uuid
    jsonl_path = repository.root / "session.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    derive_session(repository, session_id, jsonl_path)
    return session_id


SESSION_ID = "SES-20260912-1432"


# --- decisions require identifiable author evidence (§13.1, §9.2) -----------


def test_record_decision_writes_an_author_badged_entry_citing_the_turn(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION)])

    record = record_decision(repository, session_id, 1, DECISION)

    assert record.id == "DEC-0001"
    assert record.citation == "SES-20260912-1432#T001"
    decisions_text = (tmp_path / "decisions.md").read_text(encoding="utf-8")
    assert "[author] Let's keep Bob's knowledge ambiguous until chapter 9." in decisions_text
    assert "SES-20260912-1432#T001" in decisions_text
    assert "## DEC-0001" in decisions_text


def test_record_decision_refuses_a_turn_that_is_not_the_authors(tmp_path):
    """§13.1's own example: "Maybe we could keep it ambiguous" does not
    qualify as a decision. Here it is the assistant's own turn, which part
    06 §9.2 rules out on its own terms - "There must be identifiable author
    evidence" - independent of what the words say."""
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("assistant", MUSING)])

    with pytest.raises(RecordExtractorError, match="Assistant"):
        record_decision(repository, session_id, 1, MUSING)

    assert not (tmp_path / "decisions.md").exists()


def test_the_musing_lands_open_while_the_assertion_lands_author(tmp_path):
    """The acceptance test: one session carries a musing and an assertion,
    both spoken by the author (part 08 §13.1's own example is the author
    musing). The musing is recorded through the queue and lands `[open]`;
    the assertion is recorded as a decision and lands `[author]`."""
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", MUSING), ("user", DECISION)])

    question = record_question(repository, session_id, 1, MUSING)
    decision = record_decision(repository, session_id, 2, DECISION)

    questions_text = (tmp_path / "questions.md").read_text(encoding="utf-8")
    assert f"[open] {MUSING}" in questions_text
    assert question.citation == "SES-20260912-1432#T001"

    decisions_text = (tmp_path / "decisions.md").read_text(encoding="utf-8")
    assert f"[author] {DECISION}" in decisions_text
    assert decision.citation == "SES-20260912-1432#T002"

    # And the musing was never recorded as a decision under either turn.
    assert "[author]" not in questions_text
    assert MUSING not in decisions_text


def test_record_question_accepts_either_role_since_nothing_it_writes_is_an_assertion(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", "Should Bob know by chapter 5?")])

    record_question(repository, session_id, 1, "Should Bob know by chapter 5?")

    assert "[open] Should Bob know by chapter 5?" in (tmp_path / "questions.md").read_text(
        encoding="utf-8"
    )


# --- every record cites its turn, and read(ref) resolves it back (#11, #30) -


def test_read_ref_resolves_a_decision_back_to_what_was_written(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION)])
    record_decision(repository, session_id, 1, DECISION)

    served = records_read(repository, "DEC-0001")

    assert "[author]" in served.text
    assert DECISION in served.text
    assert "SES-20260912-1432#T001" in served.text
    # And the citation itself resolves, independently, back to the turn.
    turn = records_read(repository, "SES-20260912-1432#T001")
    assert turn.text == DECISION


def test_read_ref_resolves_a_research_memo_back_to_what_was_written(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", "Did Bob know before July 17?")])
    memo = ResearchMemo(
        question="Did Bob know about the acquisition before July 17?",
        interpretation="Probably, based on the July 12 letter.",
        confidence="probably supported",
    )

    record = record_research_memo(repository, session_id, 1, memo)

    served = records_read(repository, record.id)
    assert "Did Bob know about the acquisition before July 17?" in served.text
    assert "probably supported" in served.text
    assert "SES-20260912-1432#T001" in served.text


def test_reading_a_decision_that_does_not_exist_is_a_named_refusal(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(ReadError, match="DEC-0001"):
        records_read(repository, "DEC-0001")


def test_reading_one_decision_does_not_leak_a_sibling_decisions_text(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION), ("user", "Cut chapter 4.")])
    first = record_decision(repository, session_id, 1, DECISION)
    second = record_decision(repository, session_id, 2, "Cut chapter 4.")

    assert "Cut chapter 4." not in read_decision(repository, first.id)
    assert DECISION not in read_decision(repository, second.id)


def test_a_decision_with_markup_characters_round_trips_verbatim(tmp_path):
    text = 'a < b && c > d, and a literal &lt; too, next to <a id="dec-0088"></a>'
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", text)])

    record = record_decision(repository, session_id, 1, text)

    decisions_text = (tmp_path / "decisions.md").read_text(encoding="utf-8")
    # Only the two real, un-escaped anchors this module rendered itself.
    assert decisions_text.count("<") == 2
    assert f"[author] {text}\n\n— {record.citation}" == read_decision(repository, record.id)


# --- DEC- and RES- are durable files, not index rows -------------------------


def test_decisions_and_research_memos_are_plain_files(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION)])
    record_decision(repository, session_id, 1, DECISION)
    record_research_memo(
        repository, session_id, 1,
        ResearchMemo(question="Q", interpretation="I", confidence="mixed"),
    )

    assert (tmp_path / "decisions.md").is_file()
    memo_files = list((tmp_path / "research" / "memos").glob("RES-*.md"))
    assert len(memo_files) == 1
    # And both are committed - not left dirty, not staged only.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "decisions.md" not in status
    assert "research/memos" not in status


def test_next_decision_id_mints_one_more_than_the_highest_on_disk(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION), ("user", "Cut chapter 4.")])
    assert next_decision_id(repository) == "DEC-0001"
    record_decision(repository, session_id, 1, DECISION)
    assert next_decision_id(repository) == "DEC-0002"
    record_decision(repository, session_id, 2, "Cut chapter 4.")
    assert next_decision_id(repository) == "DEC-0003"


def test_next_research_memo_id_is_a_per_day_sequence(tmp_path):
    repository = _repo(tmp_path)
    assert next_research_memo_id(repository, today="20261018") == "RES-20261018-001"
    session_id = _session(repository, SESSION_ID, [("user", "Q")])
    record_research_memo(
        repository, session_id, 1,
        ResearchMemo(question="Q", interpretation="I", confidence="mixed"),
    )
    # Today's count grew; a different day starts its own sequence at 1.
    assert next_research_memo_id(repository, today="20261018") == "RES-20261018-001"


def test_record_research_memo_refuses_an_invalid_confidence(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", "Q")])

    with pytest.raises(RecordExtractorError, match="not a valid research-memo confidence"):
        record_research_memo(
            repository, session_id, 1,
            ResearchMemo(question="Q", interpretation="I", confidence="pretty sure"),
        )
    assert not (tmp_path / "research" / "memos").exists()


# --- the extractor never runs against a dirty tree (§14.2) -------------------


def test_record_decision_refuses_when_the_repository_is_dirty(tmp_path):
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION)])
    (tmp_path / "subjects").mkdir()
    tracked = tmp_path / "subjects" / "people.md"
    tracked.write_text("Bob\n", encoding="utf-8")
    _git(tmp_path, "add", "subjects/people.md")
    _git(
        tmp_path, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", "add bob",
    )
    tracked.write_text("Bob (mid-edit)\n", encoding="utf-8")  # uncommitted

    with pytest.raises(RecordExtractorError, match="uncommitted human modifications"):
        record_decision(repository, session_id, 1, DECISION)

    assert not (tmp_path / "decisions.md").exists()


def test_an_untracked_file_does_not_count_as_dirty(tmp_path):
    """Only files git already tracks trip the guard - the same convention
    `write.checkpoint` already keeps for its own dirty-tree scan."""
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("user", DECISION)])
    (tmp_path / "scratch.md").write_text("not tracked, never staged\n", encoding="utf-8")

    record_decision(repository, session_id, 1, DECISION)

    assert (tmp_path / "decisions.md").is_file()


# --- the two Curator halves are separable (part 08 §12) ----------------------


def test_the_index_maintainer_never_imports_the_record_extractor():
    """A run can invoke the maintainer without the extractor: grepping the
    maintainer's own source is the direct check that it never grew a
    dependency the acceptance criterion rules out."""
    for module_name in ("index.py", "extraction.py"):
        source = (SRC_ROOT / module_name).read_text(encoding="utf-8")
        assert "record_extractor" not in source


def test_curator_actor_identity_matches_the_maintainers(tmp_path):
    """Both halves are "one agent" (part 08 §12) - same committer identity,
    kept as an independent value here rather than an import, so this
    module stays free of the other half's dependency graph."""
    from memoria.extraction import CURATOR as MAINTAINER_CURATOR

    assert CURATOR.name == MAINTAINER_CURATOR.name
    assert CURATOR.email == MAINTAINER_CURATOR.email
    assert CURATOR.human is False


# --- badged statements into entry bodies, per the write matrix (#31) ---------


def _entry(repository: Repository, entry_id: str, body: str) -> str:
    """Commit an entry file, the way one already exists before the extractor
    reaches it, and return its repository-relative path."""
    from memoria.subjects import Entry, entry_to_markdown

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


def _served(repository: Repository, entry_id: str):
    from memoria.subjects import serve_entry

    subject_id, entry_slug = entry_id.split("/")
    return serve_entry(repository, subject_id, entry_slug)


BOB = "SUB-people/bob"
TESTIMONY = "Bob was born in 1962 in Cleveland."


def test_record_statement_appends_a_badged_statement_with_its_provenance(tmp_path):
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)

    record = record_statement(
        repository, BOB, "source", "Bob called on July 17.", ("SRC-000184 P17",), token
    )

    text = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert TESTIMONY in text
    assert "[source] Bob called on July 17.\n— SRC-000184 ¶17" in text
    assert record.provenance == ("SRC-000184 ¶17",)
    # Committed through the write path, as the Curator - never left dirty.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert status == ""
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    assert author == f"{CURATOR.name} <{CURATOR.email}>"


def test_the_written_statement_is_in_the_audit_visible_body_and_open_is_not(tmp_path):
    """The seventh checkbox: what the extractor writes lands where the audit
    and assembly read - badged statements and their provenance in, `[open]`
    out - through the one predicate `subjects.is_audit_visible` owns."""
    from memoria.audit import audit_visible_body
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "source", "Bob called on July 17.", ("SRC-000184 P17",), token)
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "open", "Maybe he called twice.", (), token)

    entry, _ = _served(repository, BOB)
    visible = audit_visible_body(entry)

    assert TESTIMONY in visible
    assert "[source] Bob called on July 17.\n— SRC-000184 ¶17" in visible
    assert "Maybe he called twice." not in visible
    assert "[open] Maybe he called twice." in entry.body


@pytest.mark.parametrize("badge", [None, "", "testimony", "AUTHOR"])
def test_a_machine_write_to_testimony_fails_loudly(tmp_path, badge):
    """Part 06 §8.2: the Curator never writes unbadged text, no exceptions.
    There is no badge value that writes testimony, and nothing lands."""
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="testimony"):
        record_statement(repository, BOB, badge, "Heavyset, slow-spoken.", ("SRC-000184 P17",), token)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before


def test_a_statement_cannot_smuggle_an_unbadged_paragraph_after_itself(tmp_path):
    """A blank line inside the text would end the badged paragraph and start
    an unbadged one - testimony by another route. Refused the same way."""
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="one paragraph"):
        record_statement(
            repository, BOB, "source", "Bob called.\n\nHeavyset, slow-spoken.",
            ("SRC-000184 P17",), token,
        )

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "reference", ["CHP-0001", "SEC-0003", "chapters/08/draft.md", "book.md"]
)
def test_manuscript_prose_cannot_be_harvested_without_a_settlement(tmp_path, reference):
    """Part 06 §8.8 / part 08 §13.4: the book saying something is not
    evidence that it is true. A manuscript reference is never provenance
    for a statement; changing what an entry says needs a settlement (#33)."""
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="settlement"):
        record_statement(repository, BOB, "source", "Bob knew by chapter 5.", (reference,), token)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "reference", ["DEC-0001", "RES-20261018-003", "CLM-0041", "SUB-people/alice"]
)
def test_provenance_may_not_terminate_in_a_derived_artifact(tmp_path, reference):
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="original material"):
        record_statement(repository, BOB, "inferred", "Bob feared losing control.", (reference,), token)


@pytest.mark.parametrize("badge", ["source", "inferred"])
def test_an_assertion_badge_needs_provenance_and_open_does_not(tmp_path, badge):
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="provenance"):
        record_statement(repository, BOB, badge, "Bob called on July 17.", (), token)

    record_statement(repository, BOB, "open", "Did Bob call twice?", (), token)
    assert "[open] Did Bob call twice?" in (tmp_path / relative_path).read_text(encoding="utf-8")


def test_an_author_statement_needs_an_author_spoken_citing_turn(tmp_path):
    """Part 06 §9.2, the same bar `record_decision` holds: a source alone is
    not author evidence, and neither is the assistant's own turn."""
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    session_id = _session(repository, SESSION_ID, [("assistant", MUSING), ("user", DECISION)])
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="citing transcript turn"):
        record_statement(repository, BOB, "author", DECISION, ("SRC-000184 P17",), token)
    with pytest.raises(RecordExtractorError, match="Assistant"):
        record_statement(repository, BOB, "author", DECISION, (f"{session_id}#T001",), token)

    record = record_statement(repository, BOB, "author", DECISION, (f"{session_id}#T2",), token)

    assert record.provenance == ("SES-20260912-1432#T002",)
    assert f"[author] {DECISION}\n— SES-20260912-1432#T002" in (
        tmp_path / relative_path
    ).read_text(encoding="utf-8")


def test_record_statement_is_rejected_when_the_entry_moved_underneath(tmp_path):
    """ADR-0003's second gate: an author edit committed between the
    extractor's read and its write leaves a clean tree, which the
    dirty-tree rule cannot see - the token can."""
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)
    _entry(repository, BOB, TESTIMONY + " Heavyset, slow-spoken.")  # a committed edit

    with pytest.raises(RecordExtractorError, match="stale"):
        record_statement(repository, BOB, "source", "Bob called.", ("SRC-000184 P17",), token)

    assert "[source]" not in (tmp_path / relative_path).read_text(encoding="utf-8")


def test_record_statement_refuses_a_dirty_tree(tmp_path):
    from memoria.record_extractor import record_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)
    (tmp_path / relative_path).write_text("mid-edit\n", encoding="utf-8")  # uncommitted

    with pytest.raises(RecordExtractorError, match="uncommitted human modifications"):
        record_statement(repository, BOB, "source", "Bob called.", ("SRC-000184 P17",), token)


# --- revising a statement: the matrix's other column, gated by the flag (#32) --


INFERRED = "Fear of losing control appears to intensify after the call."


def _statement_in(repository: Repository, entry_id: str, badge, prefix: str):
    """The one parsed statement of ``entry_id``'s body with this badge whose
    text starts with ``prefix`` - the handle ``revise_statement`` takes."""
    from memoria.subjects import parse_statements

    entry, token = _served(repository, entry_id)
    (statement,) = [
        s for s in parse_statements(entry.body)
        if s.badge == badge and s.text.startswith(prefix)
    ]
    return statement, token


def _hand_edit(repository: Repository, relative_path: str, old: str, new: str) -> None:
    """The author edits the entry in place and commits by hand - the case
    the badges cannot see (#32), landing in history as a non-Curator
    commit."""
    path = repository.root / relative_path
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    _git(repository.root, "add", relative_path)
    _git(repository.root, "commit", "-q", "-m", "hand edit")


def test_revise_rewrites_a_free_statement_in_place_and_nothing_else(tmp_path):
    """Part 06 §8.2: `[source]`/`[inferred]`/`[open]` are the Curator's to
    revise freely while nothing has flagged them."""
    from memoria.record_extractor import StatementRecord, revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "inferred", INFERRED, ("SRC-000184 P17",), token)
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "open", "Did Bob call twice?", (), token)
    statement, token = _statement_in(repository, BOB, "inferred", "Fear")

    record = revise_statement(
        repository, BOB, statement, "source", "Bob feared losing control; he said so.",
        ("SRC-000190 P2",), token,
    )

    assert isinstance(record, StatementRecord)
    text = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert INFERRED not in text
    assert (
        f"{TESTIMONY}\n\n[source] Bob feared losing control; he said so.\n— SRC-000190 ¶2"
        "\n\n[open] Did Bob call twice?\n"
    ) in text
    assert subprocess.run(
        ["git", "log", "-1", "--format=%ae"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip() == CURATOR.email


def test_a_conflict_with_a_human_touched_statement_becomes_a_memoria_note(tmp_path):
    """The fourth checkbox, part 08 §14.2 end to end: the author hand-edits
    a Curator statement; the pass flags it; when evidence later conflicts,
    the Curator appends a Memoria note after it and the statement is left
    byte-identical."""
    from memoria.record_extractor import MEMORIA_NOTE_CLOSE, MemoriaNoteRecord, revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "inferred", INFERRED, ("SRC-000184 P17",), token)
    edited = "Fear of losing control appears to intensify after the call, and never eases."
    _hand_edit(repository, relative_path, INFERRED, edited)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")
    statement, token = _statement_in(repository, BOB, "inferred", "Fear")

    record = revise_statement(
        repository, BOB, statement, "source", "Later letters show the fear easing by spring.",
        ("SRC-000190 P2", "SES-20260912-1432#T3"), token, today="2026-10-18",
    )

    assert isinstance(record, MemoriaNoteRecord)
    assert record.statement == statement
    note = (
        "> **Memoria note — 2026-10-18**\n"
        ">\n"
        "> Later letters show the fear easing by spring.\n"
        "> See SRC-000190 ¶2 and SES-20260912-1432#T003.\n"
        f"> {MEMORIA_NOTE_CLOSE}"
    )
    assert record.note == note
    after = (tmp_path / relative_path).read_text(encoding="utf-8")
    # Byte-identical up to and including the statement; the note follows it.
    statement_end = before.index(edited) + len(edited) + len("\n— SRC-000184 ¶17")
    assert after[:statement_end] == before[:statement_end]
    assert after[statement_end:] == f"\n\n{note}" + before[statement_end:]


def test_a_conflict_with_testimony_becomes_a_memoria_note(tmp_path):
    """Author-supreme: testimony outranks documentary evidence
    (CONTEXT.md), and the Curator never writes unbadged text - so a
    conflict with it is a note, never a rewrite."""
    from memoria.record_extractor import MemoriaNoteRecord, revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")
    statement, token = _statement_in(repository, BOB, None, "Bob was born")

    record = revise_statement(
        repository, BOB, statement, "source", "The register gives 1961.", ("SRC-000002 P1",), token,
    )

    assert isinstance(record, MemoriaNoteRecord)
    after = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n") + "\n\n> **Memoria note — ")
    assert "The register gives 1961." in after
    assert TESTIMONY in after


def test_an_author_statement_is_revised_only_on_a_new_citing_turn(tmp_path):
    """The matrix's `[author]` row: revised by the Curator "only on a new
    citing turn". Evidence alone earns a note; a new author-spoken turn,
    offered as `[author]`, earns the revision."""
    from memoria.record_extractor import MemoriaNoteRecord, StatementRecord, revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, TESTIMONY)
    session_id = _session(
        repository, SESSION_ID, [("user", DECISION), ("user", "Actually, make it chapter 10.")]
    )
    _, token = _served(repository, BOB)
    record_statement(repository, BOB, "author", DECISION, (f"{session_id}#T1",), token)
    statement, token = _statement_in(repository, BOB, "author", "Let's keep")

    noted = revise_statement(
        repository, BOB, statement, "source", "Chapter 9 already reveals it.", ("SRC-000184 P17",), token,
    )
    assert isinstance(noted, MemoriaNoteRecord)
    assert f"[author] {DECISION}" in (tmp_path / relative_path).read_text(encoding="utf-8")

    statement, token = _statement_in(repository, BOB, "author", "Let's keep")
    revised = revise_statement(
        repository, BOB, statement, "author", "Keep Bob's knowledge ambiguous until chapter 10.",
        (f"{session_id}#T2",), token,
    )
    assert isinstance(revised, StatementRecord)
    text = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert f"[author] {DECISION}" not in text
    assert "[author] Keep Bob's knowledge ambiguous until chapter 10.\n— SES-20260912-1432#T002" in text


def test_a_memoria_note_is_outside_the_audit_visible_body_and_write_side_assembly(tmp_path):
    """The fifth checkbox, both halves: the note is in the file, and neither
    the audit's comparison text nor assembly's loaded Tier 2 carries it."""
    from memoria.assembly import assemble
    from memoria.audit import audit_visible_body
    from memoria.manuscript import Brief
    from memoria.record_extractor import revise_statement

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    statement, token = _statement_in(repository, BOB, None, "Bob was born")
    revise_statement(
        repository, BOB, statement, "source", "The register gives 1961.", ("SRC-000002 P1",), token,
    )

    entry, _ = _served(repository, BOB)
    assert "Memoria note" in entry.body
    visible = audit_visible_body(entry)
    assert TESTIMONY in visible
    assert "Memoria note" not in visible and "1961" not in visible

    context = assemble(repository, "SES-test", Brief(id="SEC-0001", text="My years with Bob."))
    (resolved,) = context.resolved_entries
    assert resolved.entry_id == BOB
    assert TESTIMONY in resolved.audit_visible_body
    assert "Memoria note" not in resolved.audit_visible_body
    assert "1961" not in resolved.audit_visible_body


def test_a_memoria_note_is_retrievable_through_read_ref_on_the_entry(tmp_path):
    """The sixth checkbox: author-facing means reachable. `read(SUB-x/y)`
    serves the entry file verbatim, note included."""
    from memoria.record_extractor import revise_statement

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    statement, token = _statement_in(repository, BOB, None, "Bob was born")
    revise_statement(
        repository, BOB, statement, "source", "The register gives 1961.", ("SRC-000002 P1",), token,
        today="2026-10-18",
    )

    served = records_read(repository, BOB)

    assert "> **Memoria note — 2026-10-18**" in served.text
    assert "> The register gives 1961.\n> See SRC-000002 ¶1.\n" in served.text


def test_revise_refuses_a_dirty_tree_and_says_so(tmp_path):
    """The third checkbox holds for the revision write too - one rule, one
    place, at the top of every write."""
    from memoria.record_extractor import revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, f"{TESTIMONY}\n\n[inferred] {INFERRED}")
    statement, token = _statement_in(repository, BOB, "inferred", "Fear")
    (tmp_path / "decisions.md").write_text("mid-thought\n", encoding="utf-8")
    _git(tmp_path, "add", "decisions.md")
    _git(tmp_path, "commit", "-q", "-m", "track decisions")
    (tmp_path / "decisions.md").write_text("mid-thought, still\n", encoding="utf-8")
    before = (tmp_path / relative_path).read_text(encoding="utf-8")

    with pytest.raises(RecordExtractorError, match="uncommitted human modifications \\(decisions.md\\)"):
        revise_statement(repository, BOB, statement, "source", "Bob said so.", ("SRC-000184 P17",), token)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before


def test_revise_refuses_a_statement_that_is_no_longer_in_the_body(tmp_path):
    from memoria.record_extractor import revise_statement
    from memoria.subjects import Statement

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    _, token = _served(repository, BOB)

    with pytest.raises(RecordExtractorError, match="no such statement"):
        revise_statement(
            repository, BOB, Statement(badge="inferred", text="Never written."),
            "source", "Bob said so.", ("SRC-000184 P17",), token,
        )


def test_a_memoria_note_itself_is_not_revised(tmp_path):
    from memoria.record_extractor import revise_statement
    from memoria.subjects import MEMORIA_NOTE

    repository = _repo(tmp_path)
    _entry(repository, BOB, TESTIMONY)
    statement, token = _statement_in(repository, BOB, None, "Bob was born")
    revise_statement(
        repository, BOB, statement, "source", "The register gives 1961.", ("SRC-000002 P1",), token,
    )
    note, token = _statement_in(repository, BOB, MEMORIA_NOTE, "> **Memoria note")

    with pytest.raises(RecordExtractorError, match="not a statement"):
        revise_statement(repository, BOB, note, "source", "Again.", ("SRC-000002 P1",), token)


def test_a_revision_validates_the_replacement_exactly_as_an_append(tmp_path):
    """No badge value revises into testimony, and an assertion badge still
    needs provenance - the same `_statement_block` both writes go through."""
    from memoria.record_extractor import revise_statement

    repository = _repo(tmp_path)
    relative_path = _entry(repository, BOB, f"{TESTIMONY}\n\n[inferred] {INFERRED}")
    statement, token = _statement_in(repository, BOB, "inferred", "Fear")
    before = (tmp_path / relative_path).read_text(encoding="utf-8")

    with pytest.raises(RecordExtractorError, match="testimony"):
        revise_statement(repository, BOB, statement, None, "Bob feared it.", (), token)
    with pytest.raises(RecordExtractorError, match="provenance"):
        revise_statement(repository, BOB, statement, "source", "Bob feared it.", (), token)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before
