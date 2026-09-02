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
    """The acceptance test: one session carries a musing and an assertion.
    The musing is recorded through the queue and lands `[open]`; the
    assertion is recorded as a decision and lands `[author]`."""
    repository = _repo(tmp_path)
    session_id = _session(repository, SESSION_ID, [("assistant", MUSING), ("user", DECISION)])

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
