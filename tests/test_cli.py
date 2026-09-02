import hashlib
import os
import subprocess
import sys


def run_cli(*args, env=None, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "memoria.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def test_help_lists_validate():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "validate" in result.stdout


def test_help_lists_normalize():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "normalize" in result.stdout


def test_help_lists_rebuild():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "rebuild" in result.stdout


def test_help_lists_checkpoint():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "checkpoint" in result.stdout


def test_help_lists_seed_subjects():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "seed-subjects" in result.stdout


def _make_valid_corpus(tmp_path):
    rel_path = "raw/vol-01/text.txt"
    evidence_root = tmp_path / "evidence"
    file_path = evidence_root / rel_path
    file_path.parent.mkdir(parents=True)
    file_path.write_text("hello evidence")
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()

    manifest_dir = evidence_root / "raw"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        f"units:\n  - id: SRC-000001\n    path: {rel_path}\n    sha256: {digest}\n"
    )
    return evidence_root, file_path


def test_validate_exits_zero_when_corpus_matches_manifest(tmp_path, monkeypatch):
    evidence_root, _ = _make_valid_corpus(tmp_path)
    import os

    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    result = run_cli("validate", env=env)

    assert result.returncode == 0


def test_validate_exits_nonzero_when_file_tampered(tmp_path):
    import os

    evidence_root, file_path = _make_valid_corpus(tmp_path)
    file_path.write_text("tampered")
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    result = run_cli("validate", env=env)

    assert result.returncode != 0
    assert "text.txt" in result.stdout


def test_validate_exits_nonzero_when_normalized_record_has_dangling_src_id(
    tmp_path,
):
    evidence_root, _ = _make_valid_corpus(tmp_path)
    repo_root = tmp_path / "repo"
    normalized_dir = repo_root / "sources" / "normalized"
    normalized_dir.mkdir(parents=True)
    (normalized_dir / "SRC-000001.md").write_text(
        "---\nid: SRC-000001\n---\n\nSee SRC-999999.\n"
    )
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    result = run_cli("validate", env=env, cwd=repo_root)

    assert result.returncode != 0
    assert "SRC-999999" in result.stdout


def test_validate_refuses_clearly_when_no_corpus_is_configured(tmp_path):
    """The point-of-use rule: only the commands that read evidence demand it.

    There is no default any more - one used to point at a sibling checkout
    that was correct only when run from beside it - so the refusal has to name
    the variable and say why there is nothing to fall back to.
    """
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("validate", env=env)

    assert result.returncode == 1
    assert "MEMORIA_EVIDENCE_ROOT" in result.stderr
    assert "no default" in result.stderr


def test_validate_exits_nonzero_and_reports_when_index_schema_version_is_unknown(
    tmp_path,
):
    """`validate` reaches the index through `list_overlay` -> `connect` ->
    `_ensure_preserved` (#18), which refuses to read a cache carrying a
    schema version this build does not know (#117). That must land as a
    clean `validate: <message>` and exit 1, like `rebuild` already does for
    the same exception - not an uncaught traceback (#118)."""
    import sqlite3

    from memoria.index import INDEX_RELATIVE_PATH

    evidence_root, _ = _make_valid_corpus(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    rebuilt = run_cli("rebuild", env=env, cwd=repo_root)
    assert rebuilt.returncode == 0, rebuilt.stderr

    db_path = repo_root / INDEX_RELATIVE_PATH
    con = sqlite3.connect(db_path)
    con.execute("UPDATE memoria_schema SET value = '99' WHERE key = 'memo_version'")
    con.commit()
    con.close()

    result = run_cli("validate", env=env, cwd=repo_root)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "validate: " in result.stderr
    assert "schema version '99'" in result.stderr


def test_normalize_converts_a_plain_text_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    raw_file = evidence_root / "raw" / "a.txt"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_text("First paragraph.\n\nSecond paragraph.")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("")
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    result = run_cli("normalize", env=env, cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert "converted 1" in result.stdout
    assert (repo_root / "sources" / "normalized" / "SRC-000001.md").is_file()


def test_normalize_lists_failed_units_on_stderr_and_still_exits_zero(tmp_path):
    """One corrupt unit is reported, not fatal (#106): the run converts the
    rest, names the failed unit with its reason on stderr, and exits 0."""
    evidence_root = tmp_path / "evidence"
    raw = evidence_root / "raw"
    raw.mkdir(parents=True)
    (raw / "a.pdf").write_text("not a pdf")
    (raw / "b.txt").write_text("Fine.")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("")
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    result = run_cli("normalize", env=env, cwd=repo_root)

    assert result.returncode == 0, result.stderr
    assert "converted 1" in result.stdout
    assert "1 unit(s) failed to convert" in result.stderr
    assert "SRC-000001" in result.stderr
    assert (repo_root / "sources" / "normalized" / "SRC-000002.md").is_file()
    assert not (repo_root / "sources" / "normalized" / "SRC-000001.md").exists()


def test_normalize_refuses_clearly_when_no_corpus_is_configured(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("normalize", env=env, cwd=repo_root)

    assert result.returncode == 1
    assert "MEMORIA_EVIDENCE_ROOT" in result.stderr


def test_rebuild_needs_no_corpus_at_all(tmp_path):
    """It reads this repo's own records, so it must not demand an evidence
    root it never uses."""
    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "run `memoria normalize` to produce them" in result.stdout
    assert "wrote 0 change projection(s)" in result.stdout
    assert "0 appearance(s) over 0 lexically-matchable" in result.stdout


def test_seed_subjects_needs_no_corpus_at_all(tmp_path):
    """The subjects tree lives in the repository, not the corpus, so it must
    not demand an evidence root it never uses."""
    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("seed-subjects", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr


def test_seed_subjects_writes_the_five_built_ins_and_reports_them(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("seed-subjects", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    for slug in ("people", "timeline", "events", "themes", "arcs"):
        subject_path = tmp_path / "subjects" / slug / "_subject.md"
        assert subject_path.is_file()
        assert str(subject_path) in result.stdout


def test_seed_subjects_does_not_clobber_an_author_edit(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}
    run_cli("seed-subjects", env=env, cwd=tmp_path)
    subject_path = tmp_path / "subjects" / "people" / "_subject.md"
    edited = subject_path.read_text(encoding="utf-8") + "\nAuthor note.\n"
    subject_path.write_text(edited, encoding="utf-8")

    result = run_cli("seed-subjects", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "nothing to write" in result.stdout
    assert subject_path.read_text(encoding="utf-8") == edited


def test_validate_passes_on_a_repository_seeded_by_seed_subjects(tmp_path):
    evidence_root, _ = _make_valid_corpus(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("")
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=str(evidence_root))

    seed_result = run_cli("seed-subjects", env=env, cwd=repo_root)
    assert seed_result.returncode == 0, seed_result.stderr

    result = run_cli("validate", env=env, cwd=repo_root)

    assert result.returncode == 0, result.stdout + result.stderr


def _git_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)


def _git_commit(tmp_path, *args, env=None):
    subprocess.run(
        ["git", "-c", "user.name=X", "-c", "user.email=x@x.com", "commit", *args],
        cwd=tmp_path, check=True, capture_output=True, env=env,
    )


def test_rebuild_writes_the_changes_projection(tmp_path):
    _git_repo(tmp_path)
    _git_commit(tmp_path, "--allow-empty", "-q", "-m", "checkpoint\n\nchange-id: CHG-20261014-001")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "wrote 1 change projection(s)" in result.stdout
    assert (tmp_path / "changes" / "CHG-20261014-001.md").is_file()


def test_checkpoint_on_a_clean_tree_exits_zero_and_reports_it(tmp_path):
    """ADR-0008's on-demand trigger: a no-op is reported, not silent."""
    _git_repo(tmp_path)
    _git_commit(tmp_path, "--allow-empty", "-q", "-m", "init")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("checkpoint", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "nothing to checkpoint" in result.stdout


def test_checkpoint_commits_a_dirty_durable_file(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "subjects").mkdir()
    (tmp_path / "subjects" / "bob.md").write_text("Bob\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    _git_commit(tmp_path, "-q", "-m", "init")
    (tmp_path / "subjects" / "bob.md").write_text("Bob (edited)\n")
    env = dict(
        (k, v) for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"
    )
    env.update(
        GIT_AUTHOR_NAME="X", GIT_AUTHOR_EMAIL="x@x.com",
        GIT_COMMITTER_NAME="X", GIT_COMMITTER_EMAIL="x@x.com",
    )

    result = run_cli("checkpoint", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "committed 1 file(s) as CHG-" in result.stdout
