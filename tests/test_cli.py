import hashlib
import json
import os
import re
import subprocess
import sys

from memoria import ledger
from memoria.records import Read
from memoria.repository import Repository


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


def test_rebuild_writes_the_semantic_index_table_beside_fts5(tmp_path):
    """#81 AC 1: one database file, both tables - `memoria rebuild` wires
    the real embedder (`memoria.embeddings.default_embed_fn`) so this is the
    actual "at rebuild" moment ADR-0007 names, not merely `build_index`
    called with none. This repository has no evidence corpus, so the table
    is created but stays empty - the assertion is on its shape, not its
    rows, so this needs no network and no model load."""
    import sqlite3

    import sqlite_vec

    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    con = sqlite3.connect(tmp_path / ".memoria" / "index.db")
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    try:
        tables = {
            name
            for name, in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"records", "paragraph_vectors"} <= tables
    finally:
        con.close()


def test_rebuild_reports_how_long_it_took(tmp_path):
    """#21's sixth acceptance criterion: what `rebuild` regenerated is
    already reported line by line; this is the "how long it took" half."""
    (tmp_path / "pyproject.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    match = re.search(r"rebuild: completed in (\d+\.\d\d)s", result.stdout)
    assert match, result.stdout
    assert float(match.group(1)) >= 0


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


def test_derive_session_end_to_end_through_the_cli(tmp_path):
    """#155: the command has no test of its own - `memoria.sessions` is unit
    tested directly, but never driven through the CLI subcommand a real
    caller actually runs. A small repository, a two-turn JSONL, one
    subprocess call."""
    (tmp_path / "pyproject.toml").write_text("")
    jsonl_path = tmp_path / "claude-code-session.jsonl"
    entries = [
        {
            "uuid": "u1",
            "parentUuid": None,
            "type": "user",
            "timestamp": "2026-09-12T14:30:00+00:00",
            "sessionId": "claude-code-session-uuid",
            "message": {"role": "user", "content": "Hello?"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u1",
            "type": "assistant",
            "timestamp": "2026-09-12T14:30:05+00:00",
            "sessionId": "claude-code-session-uuid",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there."}]},
        },
    ]
    jsonl_path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli(
        "derive-session", "SES-20260912-1432", str(jsonl_path), env=env, cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "derived 2 turn(s)" in result.stdout
    transcript = (
        tmp_path / "sessions" / "2026" / "09" / "SES-20260912-1432" / "transcript.md"
    )
    assert transcript.is_file()
    assert "Hello?" in transcript.read_text(encoding="utf-8")
    assert (tmp_path / "sessions" / "2026" / "09" / "SES-20260912-1432" / "metadata.yaml").is_file()


def test_derive_context_manifest_end_to_end_through_the_cli(tmp_path):
    """#155: the sibling gap to the one above - `memoria.context_manifest`
    is unit tested directly, but the `derive-context-manifest` subcommand
    itself never runs. A small repository whose session already served one
    read, then the actual subprocess call."""
    (tmp_path / "pyproject.toml").write_text("")
    repository = Repository(root=tmp_path)
    ledger.append_read(
        repository,
        "SES-20260912-1432",
        Read(ref="SRC-000184", citation="SRC-000184", text="A blue heron flew over."),
    )
    env = {k: v for k, v in os.environ.items() if k != "MEMORIA_EVIDENCE_ROOT"}

    result = run_cli(
        "derive-context-manifest", "SES-20260912-1432", env=env, cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout
    manifest_path = (
        tmp_path
        / "sessions"
        / "2026"
        / "09"
        / "SES-20260912-1432"
        / "context-manifest.json"
    )
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["records_loaded"] == [
        {"ref": "SRC-000184", "tokens": ledger.estimate_tokens("A blue heron flew over.")}
    ]
