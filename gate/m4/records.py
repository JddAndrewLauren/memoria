"""The M4 gate walk's record steps (docs/gates/m4-gate-walk.md), run by
scripts/gate-m4.sh inside the scratch repository, with this checkout's own
`.venv` python.

Everything here is the record extractor doing what the gate says it does -
no browser and no model - and each step appends what it *observed* to the
artifact named by MEMORIA_GATE_ARTIFACT, in the same bullet form the
Playwright steps use, so the run's record reads as one walk.

    records.py before   derive the session, record the musing and the
                        decision, seed the badged statement (acts 1 and 2)
    records.py after    hand-edit the statement, flag it, let a conflict
                        arrive as a Memoria note (act 3), then validate

Every assertion is against bytes on disk or a return value, never against
this script's own expectations of itself: the statement's bytes are read
*before* the revise and compared after it (gate/README.md's third trap).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from memoria import human_touched, records
from memoria.manuscript import create_book, create_chapter, create_section
from memoria.record_extractor import (
    MEMORIA_NOTE_CLOSE,
    MemoriaNoteRecord,
    RecordExtractorError,
    find_statement,
    record_decision,
    record_question,
    record_statement,
    revise_statement,
    serve_entry_for_write,
)
from memoria.repository import Repository
from memoria.sessions import derive_session
from memoria.write import Checkpointed, checkpoint

SESSION_ID = "SES-20260903-1000"
ENTRY_ID = "SUB-people/skilling"
ENTRY_FILE = "subjects/people/skilling.md"
FIXTURE = Path(__file__).resolve().parent / "session.jsonl"

MUSING = "Maybe the deck went up unchanged because nobody below Skilling dared to touch it."
ASSISTANT_MUSING = "Perhaps we could keep the chapter ambiguous about whether he read it at all."
DECISION = "Let's keep it ambiguous whether Skilling read the deck until the Friday thread."
INFERRED = "The deck appears to have reached Skilling without anyone below him editing it."
HAND_EDITED = "The deck reached Skilling without anyone below him editing it, and he read it that night."
CONFLICT = "A later message in the thread has the deck revised twice before it went up."

# Long enough that the Section page scrolls at 1280x720: the walk needs a
# non-zero scroll offset to prove the reader kept their place.
DRAFT = "\n\n".join(
    f"Paragraph {n} of the draft. The deck went up, and what the thread says about "
    "who touched it before it reached Skilling is the question this section holds open."
    for n in range(1, 25)
) + "\n"


def artifact(step: str, detail: str) -> None:
    with open(os.environ["MEMORIA_GATE_ARTIFACT"], "a", encoding="utf-8") as f:
        f.write(f"- **{step}** — {detail}\n")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit_as_author(root: Path, message: str, *paths: str) -> None:
    """A hand commit by the author, path-scoped like every other commit in
    the tree: never `add -A`, which would track the index and make every
    later pass look like an uncommitted human modification."""
    git(root, "add", "--", *paths)
    git(root, "commit", "-q", "-m", message, "--", *paths)


def before(repository: Repository) -> None:
    root = repository.root

    # A manuscript section the session "touched": the Section view composes
    # its Decisions card from the sessions whose ledger served a read of it.
    create_book(repository, "A short piece on the deck that went up unchanged.")
    chapter = create_chapter(repository, "The Friday thread.")
    section = create_section(repository, chapter.number, "Who touched the deck before Skilling saw it.")
    (section.dir / "draft.md").write_text(DRAFT, encoding="utf-8")
    # The author's own manuscript, landed the way an author's outside edit
    # lands: staged, then checkpointed under a CHG- id (ADR-0008) - which is
    # what `memoria validate` reads as a human manuscript write.
    git(root, "add", "--", "chapters", "book.md")
    checkpointed = checkpoint(repository)
    assert isinstance(checkpointed, Checkpointed), checkpointed
    session_dir = root / "sessions" / "2026" / "09" / SESSION_ID
    session_dir.mkdir(parents=True)
    (session_dir / "events.jsonl").write_text(
        '{"session_id": "%s", "timestamp": "2026-09-03T10:02:30+00:00", '
        '"tool": "read", "ref": "%s", "served": ["%s"]}\n'
        % (SESSION_ID, section.brief.id, section.brief.id),
        encoding="utf-8",
    )

    result = derive_session(repository, SESSION_ID, FIXTURE)
    commit_as_author(root, "derive the research session", "sessions")
    transcript = result.transcript_path.read_text(encoding="utf-8")
    assert result.turns == 4, result.turns
    assert "## T001 — Author" in transcript and "## T002 — Assistant" in transcript
    assert "## T003 — Author" in transcript
    artifact(
        "Act 0 — the session is derived",
        f"the manuscript checkpointed as `{checkpointed.change_id}`; `{SESSION_ID}` "
        f"derived from the fixture JSONL: {result.turns} turns, T001 and T003 the "
        f"author's, T002 the assistant's; the section `{section.brief.id}` is in the "
        "session's ledger",
    )

    # Act 1: the musing lands [open].
    question = record_question(repository, SESSION_ID, 1, MUSING)
    questions = (root / "questions.md").read_text(encoding="utf-8")
    assert f"[open] {MUSING}\n\n— {SESSION_ID}#T001" in questions, questions
    assert "[author]" not in questions
    artifact(
        "Act 1 — the musing lands `[open]`",
        f"`questions.md` holds `[open] {MUSING}` citing `{question.citation}`, "
        "and nothing in it is badged `[author]`",
    )

    # The restraint control: the assistant's own musing offered as a decision
    # is refused, and the refusal says where it belongs.
    try:
        record_decision(repository, SESSION_ID, 2, ASSISTANT_MUSING)
    except RecordExtractorError as exc:
        refusal = str(exc)
    else:
        raise AssertionError("an assistant turn was recorded as a decision")
    assert "Assistant" in refusal and "record_question" in refusal, refusal
    assert not (root / "decisions.md").exists()
    artifact(
        "Act 1 — the assistant's musing is refused as a decision",
        f"`record_decision` on T002 refused: “{refusal}”; `decisions.md` does not exist",
    )

    # Act 2: the decision cites the author's exact turn.
    decision = record_decision(repository, SESSION_ID, 3, DECISION)
    decisions = (root / "decisions.md").read_text(encoding="utf-8")
    assert decision.citation == f"{SESSION_ID}#T003", decision.citation
    assert f"[author] {DECISION}\n\n— {SESSION_ID}#T003" in decisions, decisions
    # The turn it cites actually contains the sentence it records.
    turn = records.read(repository, decision.citation).text
    assert DECISION in turn, turn
    artifact(
        "Act 2 — the decision cites its turn",
        f"`{decision.id}` written `[author]` citing `{decision.citation}`; "
        f"`read({decision.citation})` serves the author's turn and the decision's "
        "sentence is in it, between two other sentences",
    )

    # Act 3's subject: a Curator-written [inferred] statement, for the author
    # to hand-edit. Provenance is the first paragraph of the first record the
    # corpus produced, whichever id normalize gave it.
    first = sorted(records.read_all(repository), key=lambda r: r.id)[0]
    _, token = serve_entry_for_write(repository, ENTRY_ID)
    statement = record_statement(
        repository, ENTRY_ID, "inferred", INFERRED, (f"{first.id} P1",), token
    )
    artifact(
        "Act 3 — a badged statement exists to hand-edit",
        f"`[inferred] {INFERRED}` appended to `{ENTRY_FILE}` citing "
        f"`{statement.provenance[0]}`, committed as the Curator",
    )


def after(repository: Repository) -> None:
    root = repository.root
    path = root / ENTRY_FILE

    # The author edits the Curator's statement in place and commits by hand
    # - the one case ownership by badge cannot see (#32).
    text = path.read_text(encoding="utf-8")
    assert INFERRED in text
    path.write_text(text.replace(INFERRED, HAND_EDITED), encoding="utf-8")
    commit_as_author(root, "hand edit of the inferred statement", ENTRY_FILE)
    hand_edit_commit = git(root, "rev-parse", "--short", "HEAD")
    hand_edit_author = git(root, "log", "-1", "--format=%an")

    # The next pass flags it.
    report = human_touched.flag(repository)
    flagged = [f for f in report.flagged if f.entry_id == ENTRY_ID]
    assert flagged, report
    assert HAND_EDITED in flagged[0].statement, flagged[0].statement
    entry, _ = serve_entry_for_write(repository, ENTRY_ID)
    statement = find_statement(entry, "inferred", HAND_EDITED)
    assert human_touched.is_human_touched(repository, ENTRY_ID, statement)
    artifact(
        "Act 3 — the hand edit is flagged human-touched",
        f"commit `{hand_edit_commit}` by `{hand_edit_author}` changed the statement; "
        f"the next pass examined {report.commits} non-Curator commit(s) and flagged "
        f"`{flagged[0].statement[:60]}…` on `{ENTRY_ID}`",
    )

    # Bytes before the conflict arrives - read now, compared after.
    before_bytes = path.read_bytes()
    provenance = statement.text.splitlines()[-1]
    statement_end = before_bytes.index(provenance.encode("utf-8")) + len(provenance.encode("utf-8"))

    first = sorted(records.read_all(repository), key=lambda r: r.id)[0]
    _, token = serve_entry_for_write(repository, ENTRY_ID)
    outcome = revise_statement(
        repository, ENTRY_ID, statement, "source", CONFLICT, (f"{first.id} P2",), token
    )
    assert isinstance(outcome, MemoriaNoteRecord), outcome
    after_bytes = path.read_bytes()
    assert after_bytes[:statement_end] == before_bytes[:statement_end], "the statement's bytes changed"
    assert after_bytes[statement_end:].startswith(b"\n\n> **Memoria note"), after_bytes[statement_end:statement_end + 40]
    assert MEMORIA_NOTE_CLOSE.encode("utf-8") in after_bytes
    assert CONFLICT.encode("utf-8") in after_bytes
    note_commit_author = git(root, "log", "-1", "--format=%an")
    note_paths = git(root, "log", "-1", "--name-only", "--format=")
    assert note_paths.strip() == ENTRY_FILE, note_paths
    artifact(
        "Act 3 — the conflict arrives as a Memoria note",
        f"`revise_statement` with conflicting evidence `{outcome.provenance[0]}` "
        f"returned a Memoria note, not a rewrite; the first {statement_end} bytes of "
        f"`{ENTRY_FILE}` - the author's edited statement included - are identical "
        f"before and after, the note follows it and ends “{MEMORIA_NOTE_CLOSE}”, "
        f"and the note's commit by `{note_commit_author}` touched `{note_paths.strip()}` only",
    )

    # validate over the resulting repository state.
    memoria = os.environ["MEMORIA_BIN"]
    run = subprocess.run([memoria, "validate"], cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "validate: OK" in run.stdout, run.stdout
    artifact(
        "Act 4 — validate",
        "`memoria validate` over the scratch repository: OK - every `#T` citation "
        "resolves and every assertion badge carries original-material provenance",
    )


def main() -> int:
    repository = Repository(
        root=Path.cwd(), evidence_root=Path(os.environ["MEMORIA_EVIDENCE_ROOT"])
    )
    {"before": before, "after": after}[sys.argv[1]](repository)
    return 0


if __name__ == "__main__":
    sys.exit(main())
