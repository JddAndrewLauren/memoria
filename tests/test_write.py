"""The single write path: gated by a content hash, closed by a commit.

ADR-0003 settles the mechanism; docs/adr/0003-durable-writes-go-through-one-
path.md numbers the five decisions this module implements, and the tests
below are grouped against them.
"""

import ast
import dataclasses
import subprocess
from pathlib import Path

import pytest

from memoria import write
from memoria.repository import Repository
from memoria.write import Actor, Rejected, Written

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "memoria"

AUTHOR = Actor(name="Author", email="author@memoria.test")
CURATOR = Actor(name="Curator", email="curator@memoria.test")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, files: dict[str, str]) -> Repository:
    """A real git repository - not a fake - with `files` committed.

    A real repository because the point under test is what `git` itself
    ends up recording: the commit's scope and its author.
    """
    _git(tmp_path, "init", "-q")
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
         "commit", "-q", "-m", "initial")
    return Repository(root=tmp_path)


# --- serving mints the token (decision 1) -----------------------------------


def test_serving_a_file_returns_its_content_and_a_token_derived_from_the_bytes(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})

    served = write.serve(repository, "subjects/people/bob.md")

    assert served.text == "Bob\n"
    assert served.token == write._token(b"Bob\n")


def test_two_files_with_different_bytes_serve_different_tokens(tmp_path):
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )

    bob = write.serve(repository, "subjects/people/bob.md")
    alice = write.serve(repository, "subjects/people/alice.md")

    assert bob.token != alice.token


# --- a matching token applies exactly (decision 1, decision 3) -------------


def test_a_write_with_a_matching_token_applies_exactly(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    result = write.write(
        repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR
    )

    assert result == Written(path="subjects/people/bob.md")
    assert (tmp_path / "subjects/people/bob.md").read_text() == "Bob Smith\n"


def test_a_write_leaves_other_files_untouched(tmp_path):
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    served = write.serve(repository, "subjects/people/bob.md")

    write.write(repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR)

    assert (tmp_path / "subjects/people/alice.md").read_text() == "Alice\n"


# --- a stale token is rejected, both ways it can go stale (decisions 1, 5) --


def test_an_uncommitted_outside_edit_is_rejected(tmp_path):
    """The case §40.6's literal wording misses: `HEAD` never moves, but the
    bytes on disk did."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")

    result = write.write(
        repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR
    )

    assert result == Rejected(outcome="stale", path="subjects/people/bob.md")
    assert (tmp_path / "subjects/people/bob.md").read_text() == "Bob (edited in Obsidian)\n"


def test_a_committed_outside_edit_is_rejected_the_same_way(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=Obsidian", "-c", "user.email=obsidian@memoria.test",
         "commit", "-q", "-m", "outside edit")

    result = write.write(
        repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR
    )

    assert result == Rejected(outcome="stale", path="subjects/people/bob.md")
    assert (tmp_path / "subjects/people/bob.md").read_text() == "Bob (edited in Obsidian)\n"


def test_a_rejection_carries_only_the_outcome_and_the_path(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})

    result = write.write(
        repository, "subjects/people/bob.md", "not-a-real-token", "Bob Smith\n", AUTHOR
    )

    assert result == Rejected(outcome="stale", path="subjects/people/bob.md")
    assert {f.name for f in dataclasses.fields(Rejected)} == {"outcome", "path"}


# --- one write, one file, replaced whole (decision 3) -----------------------


def test_an_interrupted_write_leaves_the_original_intact(tmp_path, monkeypatch):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    def _boom(*args, **kwargs):
        raise OSError("simulated crash mid-rename")

    monkeypatch.setattr(write.os, "replace", _boom)

    with pytest.raises(OSError):
        write.write(
            repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR
        )

    assert (tmp_path / "subjects/people/bob.md").read_text() == "Bob\n"
    assert list((tmp_path / "subjects/people").glob("*.tmp-*")) == []


# --- an accepted write commits, path-scoped and attributed (decision 2) ----


def test_an_accepted_write_produces_a_commit_scoped_to_that_path(tmp_path):
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    served = write.serve(repository, "subjects/people/bob.md")
    (tmp_path / "subjects/people/alice.md").write_text("Alice (dirty, unrelated)\n")

    write.write(repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR)

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    # bob.md is clean - it was committed. alice.md is still dirty - it was
    # neither committed nor cleaned.
    assert "bob.md" not in status
    assert " M subjects/people/alice.md" in status

    log = subprocess.run(
        ["git", "log", "-1", "--name-only", "--format="], cwd=tmp_path,
        capture_output=True, text=True,
    ).stdout
    assert log.strip() == "subjects/people/bob.md"


def test_the_commit_is_attributed_to_the_actor(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    write.write(repository, "subjects/people/bob.md", served.token, "Bob Smith\n", CURATOR)

    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"], cwd=tmp_path,
        capture_output=True, text=True,
    ).stdout.strip()
    assert author == "Curator <curator@memoria.test>"


# --- one module owns every durable write ------------------------------------

# The two pre-existing writers ADR-0003 and ADR-0004 scope outside this
# module: `records` is the ingest side, writing normalized records under
# `sources/normalized/`, and `index` is the index maintainer, writing
# `.memoria/index.db`. Both are Derived state (§42), not a durable class.
ALLOWED_WRITERS = {"write.py", "records.py", "index.py"}
FILE_WRITING_CALLS = {"write_text", "write_bytes"}


def test_no_other_module_writes_a_file():
    """The durable-class paths are enumerated in `write.DURABLE_PATHS`; this
    is the other half - nothing outside the allowlist above writes a file at
    all, so nothing can write under them by another route."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name in ALLOWED_WRITERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in FILE_WRITING_CALLS, (
                f"{path.relative_to(SRC_ROOT)} calls {name}(): a durable write "
                "goes through memoria.write"
            )


def test_durable_paths_cover_the_state_classes_the_write_path_scopes_to():
    """Manuscript, Subjects, Claims and Working state (part 04 §3) - Change
    record has no path of its own, since it is realised as the commit every
    write already makes, not a directory this module writes into."""
    assert write.DURABLE_PATHS == (
        "book.md",
        "chapters/",
        "subjects/",
        "claims/",
        "decisions.md",
        "questions.md",
        "research/",
    )
