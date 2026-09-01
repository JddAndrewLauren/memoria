"""The CHG- ledger (ADR-0008): minting, resolving and rendering commits.

Every scenario needs a real git repository - not a fake - because the point
under test is what `git log` itself finds by the `change-id:` trailer.
"""

import re
import shutil
import subprocess

import pytest

from memoria import changes
from memoria.records import ReadError, read
from memoria.repository import Repository
from memoria.write import checkpoint


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    return Repository(root=tmp_path)


def _commit(tmp_path, message: str, files: dict[str, str]) -> None:
    """One commit, with `files` written and staged first - `message` carries
    whatever trailer (or none) the scenario needs."""
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(
        tmp_path, "-c", "user.name=Author", "-c", "user.email=author@memoria.test",
        "commit", "-q", "-m", message,
    )


# --- render: the pure §11 projection -----------------------------------------


def test_render_produces_the_11_projection():
    commit = changes.ChangeCommit(
        change_id="CHG-20261014-003",
        sha="9b07fa1",
        date="2026-10-14 09:17",
        files=("subjects/themes/control.md",),
        diff="-Control appears primarily as a professional concern.\n"
             "+Control is fundamentally personal and only later becomes "
             "professional.",
    )

    rendered = changes.render(commit)

    assert rendered == (
        "# CHG-20261014-003\n"
        "\n"
        "Date: 2026-10-14 09:17\n"
        "Commit: 9b07fa1\n"
        "Files:\n"
        "- subjects/themes/control.md\n"
        "\n"
        "## Diff\n"
        "\n"
        "-Control appears primarily as a professional concern.\n"
        "+Control is fundamentally personal and only later becomes "
        "professional.\n"
    )
    assert rendered.isascii()


# --- resolve: found by the trailer, not by position --------------------------


def test_resolve_finds_a_commit_by_its_trailer(tmp_path):
    repository = _repo(tmp_path)
    _commit(
        tmp_path, "initial",
        {"subjects/themes/control.md": "Control appears primarily as a "
                                        "professional concern.\n"},
    )
    _commit(
        tmp_path, "checkpoint\n\nchange-id: CHG-20261014-003",
        {"subjects/themes/control.md": "Control is fundamentally personal "
                                        "and only later becomes "
                                        "professional.\n"},
    )

    commit = changes.resolve(repository, "CHG-20261014-003")

    assert commit.change_id == "CHG-20261014-003"
    assert commit.files == ("subjects/themes/control.md",)
    assert "-Control appears primarily" in commit.diff
    assert "+Control is fundamentally personal" in commit.diff
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", commit.date)
    assert re.match(r"^[0-9a-f]{7,}$", commit.sha)


def test_resolve_on_an_unmatched_id_names_the_reference(tmp_path):
    repository = _repo(tmp_path)
    _commit(tmp_path, "initial", {"a.md": "a\n"})

    with pytest.raises(changes.ChangesError, match="CHG-20261014-003"):
        changes.resolve(repository, "CHG-20261014-003")


def test_a_commit_with_no_trailer_is_not_in_the_ledger(tmp_path):
    """A Curator or AI manuscript commit (§41) carries no change-id -
    `resolve` and `rebuild` must not mistake ordinary history for one."""
    repository = _repo(tmp_path)
    _commit(tmp_path, "manuscript: revise ch2", {"a.md": "a\n"})

    assert changes.rebuild(repository) == []
    with pytest.raises(changes.ChangesError):
        changes.resolve(repository, "CHG-20261014-001")


# --- rebuild: the other caller, and its lifecycle -----------------------------


def test_rebuild_writes_one_file_per_change_id(tmp_path):
    repository = _repo(tmp_path)
    _commit(tmp_path, "initial", {"a.md": "a\n"})
    _commit(tmp_path, "checkpoint\n\nchange-id: CHG-20261014-001", {"a.md": "a2\n"})
    _commit(tmp_path, "checkpoint\n\nchange-id: CHG-20261014-002", {"a.md": "a3\n"})

    change_ids = changes.rebuild(repository)

    assert change_ids == ["CHG-20261014-001", "CHG-20261014-002"]
    written = sorted(p.name for p in (tmp_path / "changes").glob("*.md"))
    assert written == ["CHG-20261014-001.md", "CHG-20261014-002.md"]
    for change_id in change_ids:
        expected = changes.render(changes.resolve(repository, change_id))
        assert (tmp_path / "changes" / f"{change_id}.md").read_text() == expected


def test_rebuild_on_a_fresh_git_repo_with_no_commits_writes_nothing(tmp_path):
    repository = _repo(tmp_path)

    assert changes.rebuild(repository) == []
    assert not (tmp_path / "changes").exists()


def test_rebuild_on_a_non_git_directory_succeeds_with_nothing(tmp_path):
    """No evidence root, no corpus, and not even a git repository yet - the
    degenerate case ADR-0008's 'no default' consequence has to survive."""
    repository = Repository(root=tmp_path)

    assert changes.rebuild(repository) == []


def test_deleting_changes_and_rebuilding_restores_it_byte_identically(tmp_path):
    repository = _repo(tmp_path)
    _commit(tmp_path, "initial", {"a.md": "a\n"})
    _commit(tmp_path, "checkpoint\n\nchange-id: CHG-20261014-001", {"a.md": "a2\n"})
    changes.rebuild(repository)
    before = (tmp_path / "changes" / "CHG-20261014-001.md").read_bytes()
    shutil.rmtree(tmp_path / "changes")

    changes.rebuild(repository)

    after = (tmp_path / "changes" / "CHG-20261014-001.md").read_bytes()
    assert after == before


# --- read(CHG-...) is the other caller of render -----------------------------


def test_read_resolves_a_change_by_its_trailer(tmp_path):
    repository = _repo(tmp_path)
    _commit(tmp_path, "initial", {"subjects/themes/control.md": "old\n"})
    _commit(
        tmp_path, "checkpoint\n\nchange-id: CHG-20261014-003",
        {"subjects/themes/control.md": "new\n"},
    )

    result = read(repository, "CHG-20261014-003")

    assert result.citation == "CHG-20261014-003"
    assert "subjects/themes/control.md" in result.text
    assert "## Diff" in result.text


def test_read_on_an_unresolvable_change_id_names_it(tmp_path):
    repository = _repo(tmp_path)
    _commit(tmp_path, "initial", {"a.md": "a\n"})

    with pytest.raises(ReadError, match="CHG-20261014-003"):
        read(repository, "CHG-20261014-003")


# --- write.checkpoint mints an id that read(CHG-...) resolves ---------------


def test_a_checkpoints_change_id_resolves_through_read(tmp_path):
    repository = _repo(tmp_path)
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    _commit(tmp_path, "initial", {"subjects/people/bob.md": "Bob\n"})
    (tmp_path / "subjects/people/bob.md").write_text("Bob (edited in Obsidian)\n")

    result = checkpoint(repository)

    read_result = read(repository, result.change_id)
    assert "+Bob (edited in Obsidian)" in read_result.text


# --- an unreadable repository is not an empty ledger -------------------------


def test_a_repository_with_no_commits_has_an_empty_ledger(tmp_path):
    """The case the empty result exists for: a real repository, nothing
    committed to it yet."""
    repository = _repo(tmp_path)

    assert changes._ledger(repository) == []


def test_a_corrupt_repository_is_not_read_as_an_empty_ledger(tmp_path):
    """A repository git cannot read is a failure, not a history with no
    changes in it - the two were indistinguishable while any non-zero exit
    returned []."""
    repository = _repo(tmp_path)
    _commit(tmp_path, "checkpoint\n\nchange-id: CHG-20261014-001", {"a.md": "a\n"})
    (tmp_path / ".git" / "HEAD").write_text("0" * 40 + "\n", encoding="utf-8")

    with pytest.raises(changes.ChangesError, match="bad object"):
        changes._ledger(repository)
