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


def test_saving_unchanged_bytes_is_written_and_makes_no_commit(tmp_path):
    """An editor's save button saving what it read is ordinary, not an
    error: the token matches, the file is replaced with itself, and there is
    nothing for git to record."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout

    result = write.write(repository, "subjects/people/bob.md", served.token, "Bob\n", AUTHOR)

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert result == Written(path="subjects/people/bob.md")
    assert after == before
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert status == ""


def test_a_failed_git_call_reports_what_git_printed_on_either_stream(tmp_path, monkeypatch):
    """git reports some failures on stdout (`nothing to commit` is one), so
    an error that quoted stderr alone would carry an empty reason."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args, returncode=1, stdout="on stdout\n", stderr="on stderr\n"
        )

    monkeypatch.setattr(write.subprocess, "run", _fake_run)

    with pytest.raises(write.WriteError, match="on stdout") as excinfo:
        write._git(repository, ["commit"], env={})
    assert "on stderr" in str(excinfo.value)


# --- one module owns every durable write ------------------------------------

# The two pre-existing writers ADR-0003 and ADR-0004 scope outside this
# module: `records` is the ingest side, writing normalized records under
# `sources/normalized/`, and `index` is the index maintainer, writing
# `.memoria/index.db`. Both are Derived state (§42), not a durable class.
#
# `manuscript` is a third: #35 has it write a brief's bytes directly
# (`_write_brief_file`'s `os.replace`, `_renumber_directories`'s
# `Path.rename`) rather than through this module. Whether that should
# instead route through `memoria.write` is an open operator decision
# (issue #66, comment 5501089810), not settled by this guard - it only
# records who writes today.
ALLOWED_WRITERS = {"write.py", "records.py", "index.py", "manuscript.py"}
FILE_WRITING_CALLS = {
    "write_text", "write_bytes",
    "rename", "copy2", "copyfile", "copyfileobj", "move",
}
# `replace` and `copy` are also generic method names - `str.replace`,
# `dataclasses.replace`, `dict.copy`/`list.copy` - so matching the bare
# attribute name alone would flag those too (PR #87 round-2 review, note
# 2). Require the receiver to be `os`/`shutil`, the only modules this
# codebase calls them on, so only the real `os.replace`/`shutil.copy`
# trips the guard.
QUALIFIED_ONLY_CALLS = {"replace", "copy"}
FS_MODULES = {"os", "shutil"}
WRITE_MODES = set("wax+")


def _writes_a_file(node: ast.Call) -> str | None:
    """The name of the file-writing call `node` makes, or None."""
    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
    if name in QUALIFIED_ONLY_CALLS and isinstance(node.func, ast.Attribute):
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id in FS_MODULES:
            return name
        return None
    if name in FILE_WRITING_CALLS or name in QUALIFIED_ONLY_CALLS:
        return name
    if name == "open":
        mode = next(
            (kw.value for kw in node.keywords if kw.arg == "mode"),
            node.args[1] if len(node.args) > 1 else None,
        )
        if not isinstance(mode, ast.Constant) or WRITE_MODES & set(str(mode.value)):
            return "open"
    return None


def test_no_other_module_writes_a_file():
    """The durable-class paths are enumerated in `write.DURABLE_PATHS`; this
    is the other half - nothing outside the allowlist above writes a file at
    all, so nothing can write under them by another route. Caught: the
    pathlib and shutil writers, `os.replace`/`rename`, and `open()` in any
    mode that is not a read-only literal."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name in ALLOWED_WRITERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _writes_a_file(node)
            assert name is None, (
                f"{path.relative_to(SRC_ROOT)} calls {name}(): a durable write "
                "goes through memoria.write"
            )


def test_the_no_other_writer_guard_would_catch_a_real_violator(tmp_path):
    """The guard above is only worth having if it still fires on a module
    that writes a file directly - and, since `replace`/`copy` are now
    qualified-only, only on the real `os`/`shutil` call, not on the
    `str.replace`, `dataclasses.replace` or `dict.copy` that share its bare
    attribute name (PR #87 round-2 review, note 2)."""
    offender = tmp_path / "offender.py"
    offender.write_text(
        "import os\n"
        "def write_it(tmp, path):\n"
        "    os.replace(tmp, path)\n",
        encoding="utf-8",
    )
    tree = ast.parse(offender.read_text(encoding="utf-8"), filename=str(offender))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert any(_writes_a_file(node) == "replace" for node in calls)

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "import dataclasses\n"
        "def normalize(text, brief):\n"
        "    return text.replace('a', 'b'), dataclasses.replace(brief), {}.copy()\n",
        encoding="utf-8",
    )
    tree = ast.parse(innocent.read_text(encoding="utf-8"), filename=str(innocent))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert all(_writes_a_file(node) is None for node in calls)


def test_durable_paths_name_the_state_classes_and_nothing_derived_or_immutable():
    """Manuscript, Subjects, Claims and Working state (part 04 §3) - Change
    record has no path of its own, since it is realised as the commit every
    write already makes, not a directory this module writes into."""
    assert {"book.md", "chapters/", "subjects/", "claims/"} <= set(write.DURABLE_PATHS)
    assert {"decisions.md", "questions.md", "research/"} <= set(write.DURABLE_PATHS)
    for excluded in ("sources/", "sessions/", ".memoria/", "changes/"):
        assert excluded not in write.DURABLE_PATHS


@pytest.mark.parametrize(
    "relative_path", ["sources/2024/letter.md", ".memoria/index.db", "changes/CHG-1.md"]
)
def test_the_write_path_refuses_a_path_outside_the_durable_classes(tmp_path, relative_path):
    """Evidence is immutable and Derived state is regenerated; neither is
    this module's to write, and the constant is what says so."""
    repository = _repo(tmp_path, {relative_path: "not ours\n"})

    with pytest.raises(write.WriteError, match="not a durable"):
        write.serve(repository, relative_path)
    with pytest.raises(write.WriteError, match="not a durable"):
        write.write(repository, relative_path, "any", "x\n", AUTHOR)
    assert (tmp_path / relative_path).read_text() == "not ours\n"
