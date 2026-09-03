"""The M5 gate walk's core steps (docs/gates/m5-gate-walk.md), run by
scripts/gate-m5.sh inside the scratch repository, with this checkout's own
`.venv` python.

Everything here is the manuscript layer doing what the gate says it does -
no browser and no model - and each act appends what it *observed* to the
artifact named by MEMORIA_GATE_ARTIFACT, in the same bullet form the
Playwright steps use, so the run's record reads as one walk.

    records.py before    import the legacy chapter under a no-network guard,
                         write the piece's brief and assemble it, authorize
                         and write the draft, trace a paragraph (acts 1-4)
    records.py audit     audit the section from its button - the MCP pair -
                         with hand-written judgements (act 5)
    records.py reaudit   after the browser settled a finding: only a
                         re-audit brings the section current (act 6), then
                         validate (act 7)

Every assertion is against bytes on disk, a return value or a git commit,
never against this script's own expectations of itself; every reading that
is compared "before and after" is taken before the act (gate/README.md).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from memoria import audit, index, ledger, trace
from memoria.assembly import ScopeFallback, assemble
from memoria.authorship import (
    Applied,
    Authorization,
    ParagraphTarget,
    Refused,
    SectionTarget,
    write_draft,
)
from memoria.legacy_import import import_chapter
from memoria.manuscript import create_book, create_chapter, create_section, parse_brief
from memoria.mcp import server
from memoria.repository import Repository
from memoria.review import review_section
from memoria.sessions import derive_session
from memoria.write import Checkpointed, checkpoint

SESSION_ID = "SES-20260903-1100"
ENTRY_ID = "SUB-people/skilling"
ENTRY_FILE = "subjects/people/skilling.md"
LEGACY_SECTION = "SEC-0001"
PIECE_SECTION = "SEC-0002"
FIXTURE_DIR = Path(__file__).resolve().parent
LEGACY_PROSE = (FIXTURE_DIR / "legacy.md").read_text(encoding="utf-8")
LEGACY_BRIEF = "The Skilling thread, as first drafted."
PIECE_CHAPTER_BRIEF = "The deck, the thread, and who read what."
# Names Skilling (an entry) and Fastow (a candidate the extraction found
# and nobody promoted) - the "something with no entry" the gate asks for.
PIECE_BRIEF = "How the deck reached Skilling, and what Fastow did with it before the Friday thread."
CANDIDATE_ID = "CAN-0001"
CANDIDATE_LABEL = "Fastow"
AUTHORIZING_SENTENCE = "Go ahead and draft the section from the context you assembled."
FINDING_STATEMENT = (
    "The draft has Skilling reading the deck the night it went up; the thread has it "
    "revised twice before it reached him."
)
CONTESTED_PARAGRAPH = 3

# 24 paragraphs: long enough that the Section page scrolls at 1280x720, with
# the third the one the audit will disagree with.
DRAFT = "\n\n".join(
    "Skilling read the deck the night it went up, and the draft says so plainly."
    if n == CONTESTED_PARAGRAPH
    else f"Paragraph {n} of the draft. The deck went up, and what the thread says about "
    "who touched it before it reached the top floor is the question this section holds open."
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


def memo_rows(repository: Repository) -> int:
    con = index.connect(repository)
    try:
        return con.execute("SELECT COUNT(*) FROM memo").fetchone()[0]
    finally:
        con.close()


def memoria_commits(root: Path) -> int:
    return sum(1 for line in git(root, "log", "--format=%an").splitlines() if line == "Memoria")


def legacy_judgements(repository: Repository) -> tuple[audit.NotCurrentJudgement, ...]:
    return tuple(
        item for item in audit.compute_staleness_map(repository).not_current if item.chapter_number == 1
    )


class _NoNetwork:
    """The observation the gate asks for: while the import runs, any socket,
    any subprocess - the only two ways this process could reach a model -
    raises. The same guard tests/test_legacy_import.py holds; here it is
    held over the act itself."""

    def __enter__(self):
        self.saved = (socket.socket, subprocess.run, subprocess.Popen)

        def refuse(*_args, **_kwargs):
            raise AssertionError("the legacy import touched the network or a process")

        socket.socket = refuse  # type: ignore[assignment]
        subprocess.run = refuse  # type: ignore[assignment]
        subprocess.Popen = refuse  # type: ignore[assignment]
        return self

    def __exit__(self, *_exc):
        socket.socket, subprocess.run, subprocess.Popen = self.saved  # type: ignore[assignment]
        return False


def seed_candidate(repository: Repository) -> None:
    """The row the extraction would have written for a surface form it
    could not place: an unpromoted candidate under People, labelled
    Fastow. gate/README.md: add the rows, not a larger corpus."""
    con = index.connect(repository)
    try:
        con.execute(
            "INSERT INTO candidates (candidate_id, subject_id, label, gloss, recurrence, "
            "above_threshold) VALUES (?, 'SUB-people', ?, '', 1, 0)",
            (CANDIDATE_ID, CANDIDATE_LABEL),
        )
        con.commit()
    finally:
        con.close()


def before(repository: Repository) -> None:
    root = repository.root
    seed_candidate(repository)
    create_book(repository, "A short piece on the deck that went up unchanged.")

    # Act 1: the legacy import, observed under the no-network guard.
    memo_before = memo_rows(repository)
    head_before = git(root, "rev-parse", "HEAD")
    with _NoNetwork():
        imported = import_chapter(repository, LEGACY_PROSE, LEGACY_BRIEF)
    assert imported.section.brief.id == LEGACY_SECTION, imported.section.brief.id
    chapter_brief = parse_brief((root / "chapters" / "01" / "chapter.md").read_text(encoding="utf-8"))
    section_brief = parse_brief(imported.section.path.read_text(encoding="utf-8"))
    assert chapter_brief.unconfirmed and section_brief.unconfirmed, (chapter_brief, section_brief)
    assert section_brief.text == LEGACY_BRIEF
    draft_bytes = (imported.section.dir / "draft.md").read_bytes()
    assert draft_bytes == LEGACY_PROSE.encode("utf-8"), "the imported prose is not byte-for-byte"
    paragraphs = LEGACY_PROSE.strip().count("\n\n") + 1
    assert imported.paragraph_count == paragraphs, imported.paragraph_count
    judgements = legacy_judgements(repository)
    assert judgements, "the imported chapter carries no not-current judgement"
    assert {item.cause for item in judgements} == {"never_audited"}, {item.cause for item in judgements}
    assert {item.paragraph_index for item in judgements} == set(range(1, paragraphs + 1))
    assert memo_rows(repository) == memo_before, "the import wrote a judgement"
    assert git(root, "rev-parse", "HEAD") == head_before and memoria_commits(root) == 0
    git(root, "add", "--", "chapters", "book.md")
    checkpointed = checkpoint(repository)
    assert isinstance(checkpointed, Checkpointed), checkpointed
    artifact(
        "Act 1 — the legacy chapter is imported, and nothing ran unasked",
        f"`import_chapter` under a guard that fails any socket or subprocess: "
        f"`chapters/01/chapter.md` and `{imported.section.path.relative_to(root).as_posix()}` "
        f"both carry `unconfirmed: true`, `draft.md` is the {len(draft_bytes)}-byte prose "
        f"byte-for-byte, the count is {imported.paragraph_count}; the staleness map reads "
        f"every one of the {paragraphs} paragraphs `never_audited` against `{ENTRY_ID}`; the "
        f"memo table still holds {memo_before} row(s), HEAD did not move and no commit is "
        f"Memoria's; the author's import checkpointed as `{checkpointed.change_id}`",
    )

    # Act 2: the piece's brief, and what assembly resolved it to.
    chapter = create_chapter(repository, PIECE_CHAPTER_BRIEF)
    section = create_section(repository, chapter.number, PIECE_BRIEF)
    assert section.brief.id == PIECE_SECTION and not section.brief.unconfirmed
    git(root, "add", "--", "chapters")
    checkpointed = checkpoint(repository)
    assert isinstance(checkpointed, Checkpointed), checkpointed
    events = ledger.event_path(repository, SESSION_ID)
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text(
        '{"session_id": "%s", "timestamp": "2026-09-03T11:00:30+00:00", '
        '"tool": "read", "ref": "%s", "served": ["%s"]}\n' % (SESSION_ID, PIECE_SECTION, PIECE_SECTION),
        encoding="utf-8",
    )
    context = assemble(repository, SESSION_ID, section.brief)
    (resolved,) = context.resolved_entries
    assert resolved.entry_id == ENTRY_ID, resolved
    assert {term.lower() for term in resolved.matched_by} == {"skilling"}, resolved.matched_by
    assert resolved.gathered_set, "the entry gathered nothing from the corpus"
    assert context.fallbacks == (
        ScopeFallback(subject_id="SUB-people", candidate_id=CANDIDATE_ID, label=CANDIDATE_LABEL),
    ), context.fallbacks
    assert not context.unconfirmed and not context.empty
    assembly_line = [line for line in events.read_text(encoding="utf-8").splitlines() if '"assemble"' in line]
    assert len(assembly_line) == 1, events.read_text(encoding="utf-8")
    artifact(
        "Act 2 — the piece's brief, and assembly's report",
        f"`{PIECE_SECTION}` written confirmed as “{PIECE_BRIEF}” and checkpointed as "
        f"`{checkpointed.change_id}`; `assemble` resolved the scope to 1 entry - `{ENTRY_ID}` "
        f"named by `{', '.join(resolved.matched_by)}`, gathered set of {len(resolved.gathered_set)} source(s) reported "
        f"as identifiers ({', '.join(source.anchor for source in resolved.gathered_set)}) - and "
        f"1 fallback: “{CANDIDATE_LABEL}” named no entry, so assembly fell back to the unpromoted "
        f"candidate `{CANDIDATE_ID}` under `SUB-people`, its identity only; the resolution is one "
        f"`assemble` line on the session's ledger and nothing durable",
    )

    # Act 3: the draft is written under authorization, and refused without.
    derived = derive_session(repository, SESSION_ID, FIXTURE_DIR / "session.jsonl")
    assert derived.turns == 2, derived.turns
    commit_as_author(root, "derive the writing session", "sessions")
    refused_bare = write_draft(repository, PIECE_SECTION, DRAFT)
    assert isinstance(refused_bare, Refused), refused_bare
    narrow = Authorization(SESSION_ID, 1, frozenset({ParagraphTarget(PIECE_SECTION, 3)}))
    refused_narrow = write_draft(repository, PIECE_SECTION, DRAFT, narrow)
    assert isinstance(refused_narrow, Refused), refused_narrow
    assert not (section.dir / "draft.md").exists(), "a refused write left a draft"
    authorization = Authorization(SESSION_ID, 1, frozenset({SectionTarget(PIECE_SECTION)}))
    applied = write_draft(repository, PIECE_SECTION, DRAFT, authorization)
    assert isinstance(applied, Applied), applied
    assert (section.dir / "draft.md").read_text(encoding="utf-8") == DRAFT
    head = git(root, "log", "-1", "--format=%an%n%B")
    commit_author, body = head.split("\n", 1)
    assert commit_author == "Memoria", commit_author
    assert f"authorized-by: {SESSION_ID}#T001" in body, body
    assert f"authorized-scope: {PIECE_SECTION} draft" in body, body
    assert "change-id:" not in body, body
    draft_sha = git(root, "rev-parse", "--short", "HEAD")
    artifact(
        "Act 3 — the draft is written under authorization",
        f"`{SESSION_ID}` derived from the fixture ({derived.turns} turns, T001 the author's); "
        f"`write_draft` with no authorization was refused (“{refused_bare.reason}”), and with "
        f"one covering only ¶3 was refused (“{refused_narrow.reason}”), leaving no draft; under "
        f"an authorization covering the section it wrote 24 paragraphs, and commit `{draft_sha}` "
        f"by `Memoria` carries `authorized-by: {SESSION_ID}#T001` and `authorized-scope: "
        f"{PIECE_SECTION} draft` and no `change-id`",
    )

    # Act 4: why does ¶3 say what it says.
    result = trace.trace(repository, f"{PIECE_SECTION} ¶{CONTESTED_PARAGRAPH}")
    assert result.uncommitted_lines == 0, result
    (step,) = result.steps
    assert step.sha == draft_sha and step.author == "Memoria", step
    assert step.authorized_by == f"{SESSION_ID}#T001", step
    assert step.authorized_scope == f"{PIECE_SECTION} draft", step
    assert step.authorizing_turn and AUTHORIZING_SENTENCE in step.authorizing_turn, step.authorizing_turn
    sentences = [s for s in step.authorizing_turn.replace("\n", " ").split(". ") if s]
    assert len(sentences) >= 3 and AUTHORIZING_SENTENCE.rstrip(".") in sentences[1], sentences
    assert step.assembled_from[0] == ENTRY_ID, step.assembled_from
    served_sources = tuple(ref for ref in step.assembled_from[1:] if ref.startswith("SRC-"))
    assert served_sources, step.assembled_from
    server._repository = repository
    server._session_id = SESSION_ID
    rendered = server.trace(f"{PIECE_SECTION} P{CONTESTED_PARAGRAPH}")
    assert f"authorized by: {SESSION_ID}#T001" in rendered, rendered
    assert "assembled from:" in rendered and ENTRY_ID in rendered, rendered
    assert AUTHORIZING_SENTENCE in rendered, rendered
    trace_lines = [line for line in events.read_text(encoding="utf-8").splitlines() if '"trace"' in line]
    assert len(trace_lines) == 1, events.read_text(encoding="utf-8")
    legacy = trace.trace(repository, f"{LEGACY_SECTION} ¶1")
    (legacy_step,) = legacy.steps
    assert legacy_step.change_id and legacy_step.authorized_by is None, legacy_step
    artifact(
        "Act 4 — why ¶3 says what it says",
        f"`trace({PIECE_SECTION} ¶{CONTESTED_PARAGRAPH})`: one step, commit `{step.sha}` by "
        f"`Memoria`, authorized by `{step.authorized_by}` over `{step.authorized_scope}`; the "
        f"authorizing turn is served verbatim and the sentence that authorized - "
        f"“{AUTHORIZING_SENTENCE}” - sits between two others in it; assembled from "
        f"`{ENTRY_ID}` and then {len(served_sources)} source record(s) "
        f"({', '.join(served_sources)}); the `trace` tool renders the same chain and ledgered "
        f"one `trace` line on `{SESSION_ID}`; the legacy `{LEGACY_SECTION} ¶1` traces to "
        f"`{legacy_step.change_id}` and stops, with no session",
    )


def _record_all(repository: Repository, *, contested_finding: bool) -> tuple[int, str | None]:
    """Answer every pending judgement on the piece's section through the
    MCP pair - engagement everywhere, clear verdicts everywhere but ¶3 when
    a finding is asked for - looping until nothing is pending, since a
    verdict is only asked for once its engagement is recorded."""
    recorded = 0
    source_ref: str | None = None
    for _round in range(4):
        tasks = audit.audit_tasks_for_target(
            repository, chapter_number=2, section_number=1, limit=10_000
        )
        if not tasks:
            break
        items = []
        for task in tasks:
            paragraph_index = int(task.anchor.split("#", 1)[1].split("|", 1)[0])
            if task.kind == "engagement":
                items.append(audit.RecordedAuditItem(anchor=task.anchor, kind=task.kind, engages=True))
            elif contested_finding and paragraph_index == CONTESTED_PARAGRAPH:
                assert task.gathered_anchors, "the audit had no evidence to disagree with"
                source_ref = task.gathered_anchors[0]
                slot = task.anchor.split("|", 1)[0]
                items.append(
                    audit.RecordedAuditItem(
                        anchor=task.anchor,
                        kind=task.kind,
                        clear=False,
                        finding=audit.RecordedFinding(
                            disagreement_set=[
                                audit.RecordedDisagreementMember("passage", slot),
                                audit.RecordedDisagreementMember("entry", ENTRY_ID),
                                audit.RecordedDisagreementMember("source", source_ref),
                            ],
                            statement=FINDING_STATEMENT,
                            confidence="high",
                        ),
                    )
                )
            else:
                items.append(audit.RecordedAuditItem(anchor=task.anchor, kind=task.kind, clear=True))
        outcome = server.audit_record(items)
        assert outcome.startswith(f"accepted {len(items)} of {len(items)}"), outcome
        recorded += len(items)
    assert not audit.audit_tasks_for_target(repository, chapter_number=2, section_number=1, limit=1)
    return recorded, source_ref


def audit_phase(repository: Repository) -> None:
    server._repository = repository
    server._session_id = SESSION_ID
    legacy_before = legacy_judgements(repository)
    rendered = server.audit_pending(chapter_number=2, section_number=1)
    assert "awaiting audit:" in rendered and DRAFT.split("\n\n")[0] in rendered, rendered[:400]
    assert "Skilling" in rendered
    recorded, source_ref = _record_all(repository, contested_finding=True)
    assert source_ref
    review = review_section(repository, PIECE_SECTION)
    (finding,) = review.findings
    assert finding.paragraph_index == CONTESTED_PARAGRAPH and finding.entry_id == ENTRY_ID, finding
    assert finding.finding.statement == FINDING_STATEMENT
    assert list(finding.finding.available_resolutions) == [
        "settle toward the entry", "settle toward the source", "settle toward the passage",
    ], finding.finding.available_resolutions
    assert review.verdicts_not_current == 0 and review.verdicts_current == 24, review
    assert review.entry_staleness[ENTRY_ID] and SESSION_ID in review.sessions, review
    assert legacy_judgements(repository) == legacy_before, "the audit reached the legacy chapter"
    artifact(
        "Act 5 — the audit, from its button",
        f"`audit_pending(2, 1)` served the section's paragraphs with the People subject's own "
        f"questions; {recorded} judgements recorded through `audit_record` in hand-written "
        f"batches, every one accepted: engagement everywhere, clear verdicts everywhere but ¶"
        f"{CONTESTED_PARAGRAPH}, where a three-way finding - the passage, `{ENTRY_ID}`, "
        f"`{source_ref}` - states “{FINDING_STATEMENT}”; Review serves it with the three "
        f"`settle toward …` resolutions, 24 judgements current and 0 not; the legacy chapter's "
        f"{len(legacy_before)} judgements are still `never_audited` - the audit ran only where "
        "it was asked",
    )


def reaudit(repository: Repository) -> None:
    root = repository.root
    server._repository = repository
    server._session_id = SESSION_ID
    entry_text = (root / ENTRY_FILE).read_text(encoding="utf-8")
    settled = [line for line in entry_text.splitlines() if line.startswith("[settled] ")]
    assert len(settled) == 1, entry_text
    assert f"— {SESSION_ID}" in entry_text, entry_text
    claim = root / "claims" / "CLM-0001.md"
    assert claim.is_file(), "the settlement accreted no claim"
    settle_author = git(root, "log", "-1", "--format=%an", "--", ENTRY_FILE)

    pending = audit.pending_for_target(repository, chapter_number=2, section_number=1)
    assert pending, "settling left the section current - the tint would have cleared without a re-audit"
    assert {item.cause for item in pending} == {"entry_changed"}, {item.cause for item in pending}
    assert {item.paragraph_index for item in pending} == set(range(1, 25))
    assert audit.findings_in_scope(repository) == ()
    recorded, _ = _record_all(repository, contested_finding=False)
    assert not audit.pending_for_target(repository, chapter_number=2, section_number=1)
    assert audit.findings_in_scope(repository) == ()
    review = review_section(repository, PIECE_SECTION)
    assert review.findings == () and review.verdicts_current == 24, review
    legacy = legacy_judgements(repository)
    assert legacy and {item.cause for item in legacy} == {"never_audited"}
    artifact(
        "Act 6 — settled, and current only through re-audit",
        f"the browser's settlement is on `{ENTRY_FILE}` as “{settled[0]}” citing `{SESSION_ID}`, "
        f"committed by `{settle_author}`, with `claims/CLM-0001.md` beside it; that moved the "
        f"entry, so all 24 paragraphs were pending with cause `entry_changed` and the settled "
        f"finding was silenced; {recorded} fresh judgements through `audit_record` brought the "
        f"section current with no finding; the legacy chapter's {len(legacy)} judgements are "
        "still `never_audited`",
    )

    memoria = os.environ["MEMORIA_BIN"]
    run = subprocess.run([memoria, "validate"], cwd=root, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "validate: OK" in run.stdout, run.stdout
    artifact(
        "Act 7 — validate",
        "`memoria validate` over the scratch repository: OK - the AI draft carries its "
        "authorization, the settlement parses with its session, every `#T` citation resolves",
    )


def main() -> int:
    repository = Repository(
        root=Path.cwd(), evidence_root=Path(os.environ["MEMORIA_EVIDENCE_ROOT"])
    )
    {"before": before, "audit": audit_phase, "reaudit": reaudit}[sys.argv[1]](repository)
    return 0


if __name__ == "__main__":
    sys.exit(main())
