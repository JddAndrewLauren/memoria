"""The human-touched flag (#32, part 08 §14.2): set at Curator-pass time on
statements changed by non-Curator commits, monotonic, defined over commits
and never over blame.

A real git repository and real commits, as ``test_record_extractor.py``:
the flag is a reading of git history, so the thing under test is what a
commit by the author versus a commit by the Curator does to it.
"""

import re
import subprocess
from pathlib import Path

from memoria import index
from memoria.human_touched import (
    FlagReport,
    flag,
    flagged_statements,
    is_human_touched,
    statement_key,
)
from memoria.record_extractor import CURATOR, record_statement
from memoria.repository import Repository
from memoria.subjects import Entry, Statement, entry_to_markdown, parse_statements, serve_entry

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "memoria"

BOB = "SUB-people/bob"
BOB_PATH = "subjects/people/bob.md"
TESTIMONY = "Bob was born in 1962 in Cleveland."
INFERRED = "[inferred] Fear of losing control appears to intensify after the call."


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    return Repository(root=tmp_path)


def _commit_entry(repository: Repository, body: str, *, path: str = BOB_PATH, as_curator=False):
    """Commit an entry file the way a hand edit lands in history: by the
    author's own git identity, no trailer - or, for the contrast case, as
    the Curator's identity."""
    full = repository.root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(entry_to_markdown(Entry(id=BOB, body=body)), encoding="utf-8")
    _git(repository.root, "add", path)
    identity = (
        ["-c", f"user.name={CURATOR.name}", "-c", f"user.email={CURATOR.email}"]
        if as_curator
        else []
    )
    _git(repository.root, *identity, "commit", "-q", "-m", f"edit {path}")


def _statement(body_paragraph: str) -> Statement:
    (statement,) = parse_statements(body_paragraph)
    return statement


# --- set at pass time on statements changed by non-Curator commits -----------


def test_a_pass_flags_the_badged_statement_a_hand_commit_changed(tmp_path):
    """Part 08 §14.2: "at each Curator pass, statements changed by
    non-Curator commits since the last pass are flagged." The author
    hand-edits a Curator-written `[inferred]` line; the next pass flags the
    edited statement, and the flag names the commit that did it."""
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}", as_curator=True)
    assert flag(repository) == FlagReport(
        head=_head(repository), commits=0, flagged=()
    )
    edited = "[inferred] Fear of losing control appears to intensify after the call, sharply."
    _commit_entry(repository, f"{TESTIMONY}\n\n{edited}")

    report = flag(repository)

    assert report.commits == 1
    (flagged,) = report.flagged
    assert flagged.entry_id == BOB
    assert flagged.statement == edited
    assert flagged.commit_sha == _head(repository)
    assert is_human_touched(repository, BOB, _statement(edited)) is True
    # The Curator's original, now gone from the body, was never flagged.
    assert is_human_touched(repository, BOB, _statement(INFERRED)) is False


def test_a_statement_the_curator_wrote_through_the_write_path_is_not_flagged(tmp_path):
    """The flag is defined over *non-Curator* commits. A statement the
    record extractor writes commits as the Curator, and stays the
    Curator's to revise freely."""
    repository = _repo(tmp_path)
    _commit_entry(repository, TESTIMONY)
    flag(repository)
    _, token = serve_entry(repository, "SUB-people", "bob")
    record_statement(
        repository, BOB, "source", "Bob called on July 17.", ("SRC-000184 P17",), token
    )

    report = flag(repository)

    assert report.commits == 0
    assert report.flagged == ()
    assert flagged_statements(repository, BOB) == frozenset()


def test_an_app_write_committed_as_the_author_is_a_non_curator_commit(tmp_path):
    """ADR-0003's consequence: an accepted write through the write path
    commits as whoever acted, so an author editing a badged statement
    through a surface marks it human-touched exactly like a hand edit."""
    from memoria import write

    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}", as_curator=True)
    flag(repository)
    served = write.serve(repository, BOB_PATH)
    edited = served.text.replace("intensify after the call", "intensify after July 17")
    write.write(repository, BOB_PATH, served.token, edited, write.repository_actor(repository))

    report = flag(repository)

    assert [f.statement for f in report.flagged] == [
        "[inferred] Fear of losing control appears to intensify after July 17."
    ]


def test_testimony_is_never_flagged_and_needs_no_flag(tmp_path):
    """Unbadged text is the author's by definition (part 06 §9.5) and the
    write matrix already forbids the Curator touching it; the flag protects
    badged statements, which are otherwise the Curator's to rewrite."""
    repository = _repo(tmp_path)
    _commit_entry(repository, TESTIMONY)

    report = flag(repository)

    assert report.commits == 1
    assert report.flagged == ()
    assert is_human_touched(repository, BOB, _statement(TESTIMONY)) is False


def test_the_first_pass_walks_the_whole_history(tmp_path):
    """No recorded baseline means every commit counts as "since the
    previous pass": a badged statement the author wrote by hand before the
    first pass ever ran is already theirs, and a fresh index (after
    `--reset-cache`) re-derives every flag from git rather than losing
    them."""
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}")
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}\n\n[open] Did Bob call twice?")

    report = flag(repository)

    assert report.commits == 2
    assert {f.statement for f in report.flagged} == {INFERRED, "[open] Did Bob call twice?"}


def test_a_second_pass_examines_only_the_commits_since_the_first(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}")
    first = flag(repository)
    second = flag(repository)

    assert first.commits == 1 and first.head == _head(repository)
    assert second == FlagReport(head=_head(repository), commits=0, flagged=())


def test_a_repository_with_no_commits_is_an_empty_pass(tmp_path):
    repository = _repo(tmp_path)

    assert flag(repository) == FlagReport(head=None, commits=0, flagged=())


# --- monotonic: reflow cannot unset it ---------------------------------------


def test_reflowing_the_file_does_not_unset_the_flag(tmp_path):
    """The second checkbox, and the reason git-blame span inference was
    retired: the flag is keyed by the statement's badge and words, not by
    its lines, so re-wrapping a flagged paragraph - by anyone - leaves it
    flagged, and no later pass recomputes it away."""
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}")
    flag(repository)
    assert is_human_touched(repository, BOB, _statement(INFERRED)) is True

    reflowed = "[inferred] Fear of losing control\nappears to intensify\nafter the call."
    _commit_entry(repository, f"{TESTIMONY}\n\n{reflowed}", as_curator=True)
    report = flag(repository)

    assert report.flagged == ()  # the Curator's reflow flags nothing new...
    assert is_human_touched(repository, BOB, _statement(reflowed)) is True  # ...and unsets nothing
    assert statement_key(_statement(reflowed)) == statement_key(_statement(INFERRED))


def test_a_flag_survives_a_rebuild_and_is_never_deleted(tmp_path):
    """`human_touched` is a preserved table: `memoria rebuild` regenerates
    derived state and leaves it alone, and no code path deletes a row."""
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}")
    flag(repository)

    index.rebuild(repository)
    flag(repository)

    assert flagged_statements(repository, BOB) == frozenset({INFERRED})
    assert "human_touched" in index.PRESERVED_TABLES
    source = (SRC_ROOT / "human_touched.py").read_text(encoding="utf-8")
    assert not re.search(r"DELETE FROM human_touched|UPDATE human_touched", source)


# --- a renamed entry is compared against its old path ------------------------


def test_renaming_an_entry_file_does_not_flag_its_untouched_statements(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, f"{TESTIMONY}\n\n{INFERRED}", as_curator=True)
    flag(repository)
    _git(repository.root, "mv", BOB_PATH, "subjects/people/robert.md")
    _git(repository.root, "commit", "-q", "-m", "rename bob")

    report = flag(repository)

    assert report.commits == 1
    assert report.flagged == ()


# --- nothing infers ownership from git blame ---------------------------------


def test_nothing_in_the_codebase_infers_ownership_from_git_blame():
    """The last checkbox, held as a property of the source tree: ownership
    is carried by the badge and backstopped by this flag, and no module
    runs `git blame` to reconstruct it."""
    offenders = [
        path.relative_to(SRC_ROOT).as_posix()
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if re.search(r"\bblame\b", path.read_text(encoding="utf-8"))
    ]
    assert offenders == ["human_touched.py"]  # its docstring says so, and nothing else


def _head(repository: Repository) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository.root, capture_output=True, text=True
    ).stdout.strip()
