"""The §47 health report (#44, docs/plan/15-validation-and-health.md §47).

Covers the acceptance criteria: every listed category is present on the
report; no model call anywhere in the call graph; not-current items are
sourced from the staleness map (#37) rather than a second scan; unconfirmed
briefs are listed; the report says it is safe to run autonomously; and
computing it writes no durable state.

"Nothing in it is an approve/dismiss action" is verified only in the two
mechanical senses available: computing the report writes no durable state
(``test_computing_the_report_writes_no_durable_state``) and ``health.py``
imports no write-path module, so it has no means to approve or dismiss
anything (``test_the_report_has_no_write_path``). No approve/dismiss
mechanism exists in this codebase yet, so there is nothing else to assert
against.
"""

import ast
import dataclasses
import json
import subprocess
from pathlib import Path

import pytest

from memoria import cli
from memoria.audit import StalenessMap, compute_staleness_map
from memoria.health import (
    HealthReport,
    OLD_QUESTION_DAYS_DEFAULT,
    STALE_SECTION_DAYS_DEFAULT,
    compute_health_report,
)
from memoria.manuscript import create_book, create_chapter, create_section
from memoria.record_extractor import record_question
from memoria.repository import Repository
from memoria.sessions import derive_session
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _git(cwd, *args, env=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


def _git_repo(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    return Repository(root=tmp_path)


def _commit_all(tmp_path, message: str, *, date: str | None = None) -> None:
    _git(tmp_path, "add", "-A")
    env = None
    if date is not None:
        import os

        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    _git(
        tmp_path, "-c", "user.name=Author", "-c", "user.email=author@memoria.test",
        "commit", "-q", "-m", message, env=env,
    )


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


# --- AC: no item requires a model call ----------------------------------------


def test_no_model_client_is_importable_from_health_py():
    """AC: zero model calls for a full report. Mirrors `test_audit.py`'s AST
    sweep. Subprocess is not forbidden - a git fact (#47's own words) is one
    of the three inputs this report is allowed to use."""
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib"}
    tree = ast.parse((SRC_ROOT / "health.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] not in forbidden


def test_computing_the_report_opens_no_socket(tmp_path, monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("health report computation touched the network")

    monkeypatch.setattr(socket, "socket", _blocked)

    repository = _repo(tmp_path)
    write_builtin_subjects(repository)

    report = compute_health_report(repository)

    assert isinstance(report, HealthReport)


# --- AC: writes no durable state ----------------------------------------------


def test_computing_the_report_writes_no_durable_state(tmp_path):
    """``.memoria/`` is excluded: it is the gitignored, derived index cache
    (CONTEXT.md's "Index maintainer... writes derived state only... every
    read - `compute_staleness_map` included - opens it via `index.connect`),
    never the durable, git-tracked state this acceptance criterion means -
    the same distinction `write.py`'s durable file classes draw."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    create_chapter(repository, "A chapter.")

    def _snapshot():
        return {
            str(path.relative_to(tmp_path)): path.read_bytes()
            for path in sorted(tmp_path.rglob("*"))
            if path.is_file() and ".memoria" not in path.relative_to(tmp_path).parts
        }

    before = _snapshot()
    compute_health_report(repository)
    after = _snapshot()

    assert before == after


def test_the_report_has_no_write_path(tmp_path):
    """AC: nothing in the report is an approve/dismiss action. There is no
    approve/dismiss mechanism in this codebase to call, so what is
    assertable is that `health.py` imports none of the modules that write
    durable state - it has no means to act on anything - and that the report
    it hands back is frozen, so a caller cannot turn it into a decision
    either."""
    write_path_modules = {"memoria.write", "memoria.changes", "memoria.ledger", "memoria.sessions"}
    tree = ast.parse((SRC_ROOT / "health.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not write_path_modules & {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in write_path_modules

    report = compute_health_report(_repo(tmp_path))
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.open_questions = ()


# --- AC: not-current is sourced from the staleness map, not a scan -----------


def test_not_current_is_the_same_staleness_map_37_computes(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, entry)
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text("Bob went to town.", encoding="utf-8")

    report = compute_health_report(repository)
    direct = compute_staleness_map(repository)

    assert isinstance(report.not_current, StalenessMap)
    assert report.not_current.not_current == direct.not_current
    assert report.not_current.paragraphs_not_current == 1


def test_themes_and_arcs_are_the_staleness_map_filtered_by_subject(tmp_path):
    theme = Entry(id="SUB-themes/control", match_terms=["control"], body="Control is a theme.")
    arc = Entry(id="SUB-arcs/betrayal", match_terms=["betrayal"], body="Betrayal is an arc.")
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, theme)
    _write_entry(repository, arc)
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About control and betrayal.")
    (section.dir / "draft.md").write_text("Control returned after betrayal.", encoding="utf-8")

    report = compute_health_report(repository)

    assert report.themes_not_current
    assert all(item.entry_id.startswith("SUB-themes/") for item in report.themes_not_current)
    assert report.arcs_not_current
    assert all(item.entry_id.startswith("SUB-arcs/") for item in report.arcs_not_current)
    # Both are subsets of the one staleness map, never a second scan.
    assert set(report.themes_not_current) <= set(report.not_current.not_current)
    assert set(report.arcs_not_current) <= set(report.not_current.not_current)


# --- AC: unconfirmed briefs are listed -----------------------------------------


def test_unconfirmed_briefs_are_listed_at_all_three_scales(tmp_path):
    repository = _repo(tmp_path)
    create_book(repository, "The book.", unconfirmed=True)
    chapter = create_chapter(repository, "A chapter.", unconfirmed=True)
    create_section(repository, chapter.number, "Confirmed section.")
    create_section(repository, chapter.number, "Unconfirmed section.", unconfirmed=True)

    report = compute_health_report(repository)

    levels = {item.level for item in report.unconfirmed_briefs}
    assert levels == {"book", "chapter", "section"}
    assert len(report.unconfirmed_briefs) == 3


def test_a_confirmed_repository_lists_no_unconfirmed_briefs(tmp_path):
    repository = _repo(tmp_path)
    create_book(repository, "The book.")
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "A section.")

    report = compute_health_report(repository)

    assert report.unconfirmed_briefs == ()


# --- old unresolved questions --------------------------------------------------


def test_open_questions_are_read_from_the_queue_and_aged(tmp_path):
    repository = _repo(tmp_path)
    old_date = f"{2020}0101"
    recent_date = f"{2099}0101"  # comfortably "not old" against any real clock
    (repository.root / "questions.md").write_text(
        f"[open] Was the acquisition contested?\n\n— SES-{old_date}-0900#T003\n\n"
        f"[open] Did Bob attend?\n\n— SES-{recent_date}-0900#T001\n\n",
        encoding="utf-8",
    )

    report = compute_health_report(repository, old_question_days=30)

    assert len(report.open_questions) == 2
    old = report.old_questions()
    assert len(old) == 1
    assert old[0].text == "Was the acquisition contested?"
    assert old[0].date == "2020-01-01"


def test_a_question_with_markup_characters_reaches_the_report_byte_equal(tmp_path):
    """Pins the two-sided invariant #151 left behind: ``record_question``
    writes its text unescaped, and ``_open_questions`` no longer unescapes.
    Driven through the real writer so either side drifting fails it - an
    escape re-introduced in the writer surfaces as ``&amp;``, an unescape
    re-introduced in the reader decodes the literal ``&amp;`` in the text."""
    repository = _git_repo(tmp_path)
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    _git(tmp_path, "commit", "-q", "-m", "initial", "--allow-empty")
    text = 'Does <a id="dec-0088"></a> "x & y" < z, and a literal &amp; too?'
    jsonl_path = tmp_path / "session.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "uuid": "u1",
                "parentUuid": None,
                "type": "user",
                "timestamp": "2026-09-12T14:31:00+00:00",
                "sessionId": "claude-code-session-uuid",
                "message": {"role": "user", "content": text},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    derive_session(repository, "SES-20260912-1431", jsonl_path)

    record_question(repository, "SES-20260912-1431", 1, text)
    report = compute_health_report(repository)

    assert [q.text for q in report.open_questions] == [text]


def test_a_final_question_block_ending_at_eof_is_still_read(tmp_path):
    """`record_question` always writes the trailing blank line, but a
    hand-edited `questions.md` need not - a final block ending at EOF is
    read, not silently skipped."""
    repository = _repo(tmp_path)
    (repository.root / "questions.md").write_text(
        "[open] Was the acquisition contested?\n\n— SES-20200101-0900#T003\n\n"
        "[open] Did Bob attend?\n\n— SES-20200102-0900#T001",
        encoding="utf-8",
    )

    report = compute_health_report(repository)

    assert [q.text for q in report.open_questions] == [
        "Was the acquisition contested?",
        "Did Bob attend?",
    ]
    assert report.open_questions[1].date == "2020-01-02"


def test_no_questions_file_means_no_open_questions(tmp_path):
    repository = _repo(tmp_path)

    report = compute_health_report(repository)

    assert report.open_questions == ()
    assert report.old_questions() == ()


# --- incomplete research projects ----------------------------------------------


def test_research_memos_with_unresolved_questions_are_incomplete(tmp_path):
    repository = _repo(tmp_path)
    memos = repository.root / "research" / "memos"
    memos.mkdir(parents=True)
    (memos / "RES-20260901-001.md").write_text(
        "# RES-20260901-001\n\n## Question\n\nWas it Bob?\n\n"
        "## Unresolved questions\n\n- Which Bob?\n",
        encoding="utf-8",
    )
    (memos / "RES-20260901-002.md").write_text(
        "# RES-20260901-002\n\n## Question\n\nWas it Bob?\n\n## Confidence\n\nsupported\n",
        encoding="utf-8",
    )

    report = compute_health_report(repository)

    assert [m.id for m in report.incomplete_research_memos] == ["RES-20260901-001"]


# --- broken provenance and unprocessed source additions: degrade gracefully --


def test_provenance_and_unprocessed_sources_are_none_without_an_evidence_root(tmp_path):
    repository = _repo(tmp_path)

    report = compute_health_report(repository)

    assert report.broken_provenance is None
    assert report.unprocessed_source_additions is None


def test_unprocessed_source_additions_reads_the_manifest_against_normalized(tmp_path):
    evidence_root = tmp_path / "evidence"
    (evidence_root / "raw").mkdir(parents=True)
    (evidence_root / "raw" / "one.txt").write_text("hello", encoding="utf-8")
    import hashlib

    sha = hashlib.sha256(b"hello").hexdigest()
    (evidence_root / "raw" / "manifest.yaml").write_text(
        f"units:\n- id: SRC-000001\n  path: raw/one.txt\n  sha256: {sha}\n",
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repository = Repository(root=repo_root, evidence_root=evidence_root)

    report = compute_health_report(repository)

    assert report.unprocessed_source_additions == ("SRC-000001",)
    assert report.broken_provenance == ()


# --- sections not worked on recently (a git fact) ------------------------------


def test_sections_never_committed_are_reported_stale(tmp_path):
    repository = _repo(tmp_path)  # not a git repository at all
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "A section.")

    report = compute_health_report(repository)

    assert len(report.stale_sections) == 1
    assert report.stale_sections[0].last_touched is None


def test_a_recently_committed_section_is_not_stale(tmp_path):
    repository = _git_repo(tmp_path)
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "A section.")
    _commit_all(tmp_path, "add section")

    report = compute_health_report(repository, stale_after_days=STALE_SECTION_DAYS_DEFAULT)

    assert report.stale_sections == ()


def test_an_old_commit_still_reports_the_section_stale(tmp_path):
    repository = _git_repo(tmp_path)
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "A section.")
    _commit_all(tmp_path, "add section", date="2000-01-01T00:00:00")

    report = compute_health_report(repository, stale_after_days=30)

    assert len(report.stale_sections) == 1
    assert report.stale_sections[0].last_touched == "2000-01-01"


# --- the two not-yet-built categories are reported, honestly empty -----------


def test_the_two_unbuilt_categories_are_present_and_empty(tmp_path):
    repository = _repo(tmp_path)

    report = compute_health_report(repository)

    assert report.human_curator_conflicts == ()
    assert report.unsupported_statements == ()


# --- CLI ------------------------------------------------------------------------


def test_cli_health_says_it_is_safe_to_run_autonomously(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    exit_code = cli.main(["health"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "safe to run autonomously" in out
    assert "no model call" in out


def test_cli_health_reports_both_evidence_backed_checks_as_not_checked(tmp_path, capsys, monkeypatch):
    """Both fields are ``None`` for the same reason - no evidence corpus -
    so both say so; neither is silent."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    assert cli.main(["health"]) == 0

    out = capsys.readouterr().out
    assert "provenance not checked" in out
    assert "source additions not checked" in out


def test_cli_health_accepts_threshold_overrides(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    exit_code = cli.main(["health", "--stale-after-days", "5", "--old-question-after-days", "5"])

    assert exit_code == 0
