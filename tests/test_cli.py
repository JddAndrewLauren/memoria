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
        f"base: raw\nfiles:\n  - path: {rel_path}\n    sha256: {digest}\n"
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
