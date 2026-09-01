"""The repository value: where state is, and who is allowed to not know.

ADR-0004 makes this a frozen value rather than an object with methods, and
makes the evidence root a *configured field* rather than a second co-equal
root. Both of those have consequences a test can hold: the value must be
hashable (so `lru_cache` over it stays available), and it must be
constructible without a corpus (so an adapter that never reads evidence
starts without one).
"""

from pathlib import Path

import pytest

from memoria.repository import (
    EVIDENCE_ROOT_ENV_VAR,
    NoEvidenceRoot,
    Repository,
    discover_root,
    from_env,
    require_evidence_root,
)


def test_the_value_is_frozen():
    repository = Repository(root=Path("/repo"))
    with pytest.raises(Exception):
        repository.root = Path("/elsewhere")


def test_the_value_is_hashable_so_lru_cache_over_it_stays_available():
    """ADR-0004 keeps this open deliberately; nothing uses it yet."""
    assert len({Repository(root="/a"), Repository(root="/a"), Repository(root="/b")}) == 2


def test_paths_are_coerced_so_a_caller_holding_strings_needs_no_pathlib():
    repository = Repository(root="/repo", evidence_root="/evidence")

    assert repository.root == Path("/repo")
    assert repository.evidence_root == Path("/evidence")


def test_an_absent_evidence_root_stays_absent():
    assert Repository(root="/repo").evidence_root is None


# --- discovery --------------------------------------------------------------


def test_discover_root_finds_the_directory_holding_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    nested = tmp_path / "src" / "memoria"
    nested.mkdir(parents=True)

    assert discover_root(nested) == tmp_path.resolve()


def test_discover_root_resolves_its_answer(tmp_path):
    """A spawned server's working directory is not a contract, so the root it
    reports must not depend on how it was reached."""
    (tmp_path / "pyproject.toml").write_text("")
    link = tmp_path.parent / f"{tmp_path.name}-link"
    link.symlink_to(tmp_path)

    assert discover_root(link) == tmp_path.resolve()


def test_discover_root_falls_back_to_the_start_rather_than_raising(tmp_path):
    """There may be no pyproject.toml above; that is not an error here."""
    assert discover_root(tmp_path) == tmp_path.resolve()


# --- the environment --------------------------------------------------------


def test_from_env_reads_the_evidence_root_when_it_is_set(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.setenv(EVIDENCE_ROOT_ENV_VAR, "/some/corpus")

    repository = from_env(tmp_path)

    assert repository.root == tmp_path.resolve()
    assert repository.evidence_root == Path("/some/corpus")


def test_from_env_constructs_without_a_corpus(tmp_path, monkeypatch):
    """The load-bearing one.

    `read(ref)` never touches evidence, and settings `env` does not reach an
    MCP server process - so a value that refused to exist without a corpus
    would stop the server starting over a path no tool reads.
    """
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.delenv(EVIDENCE_ROOT_ENV_VAR, raising=False)

    assert from_env(tmp_path).evidence_root is None


def test_an_empty_evidence_root_variable_counts_as_unset(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.setenv(EVIDENCE_ROOT_ENV_VAR, "")

    assert from_env(tmp_path).evidence_root is None


# --- the point of use -------------------------------------------------------


def test_require_evidence_root_returns_it_when_configured():
    repository = Repository(root="/repo", evidence_root="/evidence")

    assert require_evidence_root(repository) == Path("/evidence")


def test_require_evidence_root_names_the_variable_and_the_decision():
    """The error is the only place the absence of a corpus becomes a failure,
    so it has to say what to set and why there is no default."""
    with pytest.raises(NoEvidenceRoot) as caught:
        require_evidence_root(Repository(root="/repo"))

    message = str(caught.value)
    assert EVIDENCE_ROOT_ENV_VAR in message
    assert "no default" in message
    assert "open-problems" in message
