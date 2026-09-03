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
from memoria.write import (
    Actor,
    Checkpointed,
    NoChanges,
    Rejected,
    WriteError,
    Written,
    create,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "memoria"

AUTHOR = Actor(name="Author", email="author@memoria.test")
CURATOR = Actor(name="Curator", email="curator@memoria.test", human=False)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, files: dict[str, str]) -> Repository:
    """A real git repository - not a fake - with `files` committed.

    A real repository because the point under test is what `git` itself
    ends up recording: the commit's scope and its author.

    A local `user.name`/`user.email` is configured so a checkpoint's
    ambient-identity commit (no `Actor`, unlike `write`) succeeds
    regardless of the host machine's own git config.
    """
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
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


# --- checkpoints commit outside human edits (ADR-0008) ----------------------


def test_checkpoint_commits_tracked_modified_durable_files_only(tmp_path):
    repository = _repo(
        tmp_path, {"subjects/people/bob.md": "Bob\n", ".memoria/index.db": "stale\n"}
    )
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")
    (tmp_path / ".memoria/index.db").write_text("also dirty, but Derived\n")
    (tmp_path / "subjects/people/untracked.md").write_text("new, never added\n")

    result = write.checkpoint(repository)

    assert isinstance(result, Checkpointed)
    assert result.files == ("subjects/people/bob.md",)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "bob.md" not in status              # committed
    assert " M .memoria/index.db" in status    # Derived - left dirty
    assert "?? subjects/people/untracked.md" in status  # untracked - left alone


def test_checkpoint_on_a_clean_tree_is_a_no_op(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout

    result = write.checkpoint(repository)

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert result == NoChanges()
    assert after == before


def test_a_checkpoint_commit_carries_a_change_id_trailer(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")

    result = write.checkpoint(repository)

    message = subprocess.run(
        ["git", "log", "-1", "--format=%B"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert f"change-id: {result.change_id}" in message


def test_two_checkpoints_the_same_day_get_distinct_sequential_ids(tmp_path):
    """Covers two mintings within the same minute (part 04 §4's amended
    per-day form) - both calls happen back to back in this test."""
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited)\n")
    first = write.checkpoint(repository)
    (tmp_path / "subjects/people/alice.md").write_text("Alice (edited)\n")
    second = write.checkpoint(repository)

    assert first.change_id != second.change_id
    assert first.change_id.rsplit("-", 1)[0] == second.change_id.rsplit("-", 1)[0]


# --- every human-authored commit is identified, machine ones are not -------


def test_a_human_actors_write_carries_a_change_id_trailer(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    write.write(repository, "subjects/people/bob.md", served.token, "Bob Smith\n", AUTHOR)

    message = subprocess.run(
        ["git", "log", "-1", "--format=%B"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "change-id: CHG-" in message


def test_a_curator_actors_write_carries_no_change_id_trailer(tmp_path):
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    write.write(repository, "subjects/people/bob.md", served.token, "Bob Smith\n", CURATOR)

    message = subprocess.run(
        ["git", "log", "-1", "--format=%B"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "change-id:" not in message


def test_a_machine_write_checkpoints_other_dirty_files_first(tmp_path):
    """The moment #32's dirty-tree rule stops shielding a file - a machine
    actor's write must not leave an unrelated outside edit uncommitted."""
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    served = write.serve(repository, "subjects/people/bob.md")
    (tmp_path / "subjects/people/alice.md").write_text("Alice (edited in Obsidian)\n")

    result = write.write(
        repository, "subjects/people/bob.md", served.token, "Bob Smith\n", CURATOR
    )

    assert result == Written(path="subjects/people/bob.md")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert status == ""  # alice.md's outside edit was checkpointed, not left dirty
    subjects = subprocess.run(
        ["git", "log", "--format=%s"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert "checkpoint" in subjects



def test_a_rejected_machine_write_leaves_no_checkpoint_commit(tmp_path):
    """The checkpoint is of the human edits a machine write is about to
    write over (ADR-0008). A write that never happens has nothing to shield,
    so a stale token must leave history exactly as it found it."""
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    (tmp_path / "subjects/people/alice.md").write_text("Alice (edited in Obsidian)\n")
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout

    result = write.write(
        repository, "subjects/people/bob.md", "not-a-real-token", "Bob Smith\n", CURATOR
    )

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert result == Rejected(outcome="stale", path="subjects/people/bob.md")
    assert after == before


def test_a_refused_machine_write_leaves_no_checkpoint_commit(tmp_path):
    """The same, for the write that cannot be attempted at all: a path
    outside the durable classes is a `WriteError`, not a reason to commit."""
    repository = _repo(
        tmp_path,
        {"subjects/people/bob.md": "Bob\n", "subjects/people/alice.md": "Alice\n"},
    )
    (tmp_path / "subjects/people/alice.md").write_text("Alice (edited in Obsidian)\n")
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout

    with pytest.raises(write.WriteError):
        write.write(repository, "sources/raw/notes.md", "any-token", "x\n", CURATOR)

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout
    assert after == before


def test_a_machine_write_still_checkpoints_before_it_writes(tmp_path):
    """The checkpoint moved after validation, not after the write: the
    human's own edit to the file being written must be committed as theirs
    first, or the machine's commit would swallow it."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")
    served = write.serve(repository, "subjects/people/bob.md")

    result = write.write(
        repository, "subjects/people/bob.md", served.token, "Bob Smith\n", CURATOR
    )

    assert result == Written(path="subjects/people/bob.md")
    subjects = subprocess.run(
        ["git", "log", "--format=%s"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.splitlines()
    assert subjects[:2] == ["write: subjects/people/bob.md", "checkpoint"]


def test_a_traversing_path_that_leaves_a_durable_class_is_refused(tmp_path):
    """`chapters/../sources/x.md` stays inside the repository, so the escape
    check passes it - and its raw string starts with `chapters/`. Only the
    normalized path shows what it actually names."""
    repository = _repo(tmp_path, {"chapters/01.md": "one\n"})
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/x.md").write_text("evidence\n", encoding="utf-8")

    with pytest.raises(write.WriteError, match="not a durable state class path"):
        write.serve(repository, "chapters/../sources/x.md")

# --- one module owns every durable write ------------------------------------

# The pre-existing writers ADR-0003 and ADR-0004 scope outside this module:
# `records` is the ingest side, writing normalized records under
# `sources/normalized/`, and `index` is the index maintainer, writing
# `.memoria/index.db`. `changes` is ADR-0008's - the gitignored `changes/`
# projection. All three are Derived state (§42), not a durable class.
#
# `ledger`, `manifest`, `normalize` and `sessions` are four more of that same
# kind, all arriving from main after this guard was written: #13's ledger
# appends `sessions/<...>/events.jsonl` (Interaction record), #82's manifest
# writes under `sources/` (Evidence), `normalize` writes
# `sources/normalized/` (Derived), and #28's `sessions` writes
# `sessions/<...>/transcript.md` and `metadata.yaml` beside the ledger's own
# file - the same Interaction record class, immutable once derived rather
# than staleness-token-gated, so it has no token to route through
# `memoria.write` either. All four are absent from DURABLE_PATHS by the same
# deliberate choice, so none of them has a durable write to route.
#
# `subjects` is not of that kind, and is listed here under protest: #84 has
# `write_builtin_subjects` seed `subjects/<slug>/_subject.md` with a direct
# `Path.write_text`, and `subjects/` IS a durable class - it is in
# DURABLE_PATHS. So this is a durable write that does not go through
# `memoria.write`, which is the exact thing this guard exists to catch. It is
# allowlisted to keep the suite green, not because the question is settled;
# it is the same open operator decision as `manuscript` below, raised a
# second time by a module that landed on main after this guard was written.
#
# `manuscript` is the other one: #35 has it write a brief's bytes directly
# (`_write_brief_file`'s `os.replace`, `_renumber_directories`'s
# `Path.rename`) rather than through this module. Whether that should
# instead route through `memoria.write` is an open operator decision
# (issue #66, comment 5501089810), not settled by this guard - it only
# records who writes today.
ALLOWED_WRITERS = {
    "write.py",
    "records.py",
    "index.py",
    "manuscript.py",
    "changes.py",
    "ledger.py",
    "manifest.py",
    "normalize.py",
    "subjects.py",
    "sessions.py",
    "context_manifest.py",
}
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


# --- create (#17) ------------------------------------------------------------


def test_create_brings_a_new_durable_file_into_being_and_commits_it(tmp_path):
    """Promotion creates entries, and `write` cannot: its token is minted from
    a file that exists. `create` is the second door, in this module rather
    than around it, so a promotion is still confined, replaced atomically,
    committed and attributed."""
    repository = _repo(tmp_path, {"subjects/people/_subject.md": "seed\n"})
    actor = Actor(name="Memoria", email="curator@memoria.local", human=False)

    result = create(repository, "subjects/people/bob.md", "new entry\n", actor)

    assert isinstance(result, Written)
    assert (tmp_path / "subjects" / "people" / "bob.md").read_text() == "new entry\n"
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert author == "Memoria <curator@memoria.local>"


def test_create_rejects_a_path_that_already_exists(tmp_path):
    """Not an overwrite, and not an exception: the same shape a stale token
    has, because it is the same kind of thing - a normal outcome the caller
    handles. It is also what makes running a pass twice create nothing new
    rather than flatten an entry the author has since edited."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "mine\n"})
    actor = Actor(name="Memoria", email="curator@memoria.local", human=False)

    result = create(repository, "subjects/people/bob.md", "theirs\n", actor)

    assert isinstance(result, Rejected)
    assert result.outcome == "exists"
    assert (tmp_path / "subjects" / "people" / "bob.md").read_text() == "mine\n"


def test_create_refuses_a_path_outside_the_durable_classes(tmp_path):
    repository = _repo(tmp_path, {"book.md": "seed\n"})
    actor = Actor(name="Memoria", email="curator@memoria.local", human=False)

    with pytest.raises(WriteError, match="durable state class"):
        create(repository, "sources/normalized/SRC-000001.md", "x\n", actor)


def test_create_makes_the_parent_directory(tmp_path):
    """A subject the author added has a directory; a brand new one may not."""
    repository = _repo(tmp_path, {"book.md": "seed\n"})
    actor = Actor(name="Memoria", email="curator@memoria.local", human=False)

    result = create(repository, "subjects/locations/capital.md", "x\n", actor)

    assert isinstance(result, Written)
    assert (tmp_path / "subjects" / "locations" / "capital.md").is_file()


# --- the author's identity, for a surface's write (#26) ----------------------


def test_the_repository_actor_is_the_repositorys_own_git_identity(tmp_path):
    """ADR-0002 forbids assuming the browser and the repository share a
    machine, so a surface cannot take the author's name from the request.
    The repository's own git config is the identity already on the server
    side of that boundary - and the one `checkpoint` commits under."""
    repository = _repo(tmp_path, {"book.md": "seed\n"})

    actor = write.repository_actor(repository)

    assert actor.name == "Local Author"
    assert actor.email == "local-author@memoria.test"


def test_the_repository_actor_is_human(tmp_path):
    """§41: a direct human change is human-authored, so a write through it
    carries ADR-0008's `change-id:` trailer. A surface's write is one."""
    repository = _repo(tmp_path, {"book.md": "seed\n"})

    assert write.repository_actor(repository).human is True


@pytest.mark.parametrize("unset", ["user.name", "user.email"])
def test_an_unconfigured_git_identity_refuses_rather_than_guessing(
    tmp_path, monkeypatch, unset
):
    """Git's own fallback is a guessed `user@hostname`, and attributing an
    author act to a guess is worse than refusing it: afterwards the guess is
    indistinguishable from a real identity, and #32's human-touched flag is
    defined over exactly these commits. Both settings are named, because
    whoever hits this has to set both.

    The global and system files are pointed at nothing, because `git config
    --get` falls through to them: without that, this asserts nothing on a
    developer machine that has a global identity - and passes for the wrong
    reason on CI, which does not.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent-global"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent-system"))
    repository = _repo(tmp_path, {"book.md": "seed\n"})
    _git(tmp_path, "config", "--unset", unset)

    with pytest.raises(WriteError) as excinfo:
        write.repository_actor(repository)

    assert "user.name" in str(excinfo.value)
    assert "user.email" in str(excinfo.value)


def test_a_write_by_the_repository_actor_commits_as_that_identity(tmp_path):
    """The whole point of the value: it is what git ends up recording."""
    repository = _repo(tmp_path, {"subjects/people/bob.md": "Bob\n"})
    served = write.serve(repository, "subjects/people/bob.md")

    result = write.write(
        repository,
        "subjects/people/bob.md",
        served.token,
        "Robert\n",
        write.repository_actor(repository),
    )

    assert isinstance(result, Written)
    author = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert author == "Local Author <local-author@memoria.test>"
