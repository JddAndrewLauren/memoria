import hashlib
import os
import subprocess
import sys

import pytest

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


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
    rel_path = "raw/gutenberg/57393-journal-01/pg57393.txt"
    evidence_root = tmp_path / "thoreau-evidence"
    file_path = evidence_root / rel_path
    file_path.parent.mkdir(parents=True)
    file_path.write_text("hello thoreau")
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()

    manifest_dir = evidence_root / "raw" / "gutenberg"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text(
        f"base: raw/gutenberg\nfiles:\n  - path: {rel_path}\n    sha256: {digest}\n"
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
    assert "pg57393.txt" in result.stdout


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


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_normalize_writes_records_under_sources_normalized(tmp_path):
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=os.environ[EVIDENCE_ROOT_ENV_VAR])

    result = run_cli("normalize", env=env, cwd=tmp_path)

    assert result.returncode == 0
    written = list((tmp_path / "sources" / "normalized").glob("SRC-*.md"))
    assert len(written) == 558


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_normalize_writes_editorial_records_under_sources_editorial(tmp_path):
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=os.environ[EVIDENCE_ROOT_ENV_VAR])

    result = run_cli("normalize", env=env, cwd=tmp_path)

    assert result.returncode == 0
    written = list((tmp_path / "sources" / "editorial").glob("ED-*.md"))
    # 880 footnotes (508 J01 + 372 J02) + 232 spans (asides + interpolations,
    # 83 + 149) + 2 introductions (Torrey, Sanborn) - see test_editorial.py.
    assert len(written) == 1114


def test_rebuild_writes_normalized_records_and_the_index(tmp_path):
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=os.environ[EVIDENCE_ROOT_ENV_VAR])

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0
    written = list((tmp_path / "sources" / "normalized").glob("SRC-*.md"))
    assert len(written) == 558
    assert (tmp_path / ".memoria" / "index.db").is_file()


def test_rebuild_writes_editorial_records_and_strips_them_from_normalized(tmp_path):
    # BLOCKING 1, PR #51 review round 1: a plain `memoria rebuild` used to
    # overwrite sources/normalized/ with unstripped paragraphs and never
    # index the editorial records at all, silently undoing `memoria
    # normalize` and leaving `exclude_editorial` an effective no-op.
    env = dict(os.environ, MEMORIA_EVIDENCE_ROOT=os.environ[EVIDENCE_ROOT_ENV_VAR])

    result = run_cli("rebuild", env=env, cwd=tmp_path)

    assert result.returncode == 0
    editorial_written = list((tmp_path / "sources" / "editorial").glob("ED-*.md"))
    assert len(editorial_written) == 1114
    for path in (tmp_path / "sources" / "normalized").glob("SRC-*.md"):
        content = path.read_text(encoding="utf-8")
        body = content.split("---\n", 2)[2]
        assert "[" not in body and "]" not in body, path.name
