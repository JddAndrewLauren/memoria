import hashlib
import os

import pytest

from memoria.validate import validate

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


def _write_manifest(evidence_root, entries):
    lines = ["base: raw/gutenberg", "files:"]
    for entry in entries:
        lines.append(f"  - path: {entry}")
        content = (evidence_root / entry).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        lines.append(f"    sha256: {digest}")
    manifest_dir = evidence_root / "raw" / "gutenberg"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text("\n".join(lines) + "\n")


def _make_corpus(tmp_path, files):
    evidence_root = tmp_path / "thoreau-evidence"
    for rel_path, content in files.items():
        full = evidence_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return evidence_root


def test_validate_passes_when_hashes_match(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/gutenberg/57393-journal-01/pg57393.txt": "hello thoreau"}
    )
    _write_manifest(evidence_root, ["raw/gutenberg/57393-journal-01/pg57393.txt"])

    errors = validate(evidence_root)

    assert errors == []


def test_validate_fails_and_names_file_when_raw_file_modified(tmp_path):
    rel_path = "raw/gutenberg/57393-journal-01/pg57393.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello thoreau"})
    _write_manifest(evidence_root, [rel_path])

    (evidence_root / rel_path).write_text("tampered content")

    errors = validate(evidence_root)

    assert len(errors) == 1
    assert rel_path in errors[0]


def test_validate_does_not_modify_the_evidence_tree(tmp_path):
    rel_path = "raw/gutenberg/57393-journal-01/pg57393.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello thoreau"})
    _write_manifest(evidence_root, [rel_path])

    before = {
        p: p.stat().st_mtime_ns
        for p in evidence_root.rglob("*")
        if p.is_file()
    }

    validate(evidence_root)

    after = {
        p: p.stat().st_mtime_ns
        for p in evidence_root.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_validate_fails_when_manifest_file_is_missing(tmp_path):
    rel_path = "raw/gutenberg/57393-journal-01/pg57393.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello thoreau"})
    _write_manifest(evidence_root, [rel_path])

    (evidence_root / rel_path).unlink()

    errors = validate(evidence_root)

    assert len(errors) == 1
    assert rel_path in errors[0]


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_validate_passes_against_the_real_evidence_corpus():
    real_evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]

    errors = validate(real_evidence_root)

    assert errors == []


def _write_normalized_record(repo_root, record_id, extra_body=""):
    normalized_dir = repo_root / "sources" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / f"{record_id}.md").write_text(
        f"---\nid: {record_id}\nsource_type: journal\n---\n\n{extra_body}\n"
    )


def test_validate_passes_when_no_normalized_records_directory_exists(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/gutenberg/57393-journal-01/pg57393.txt": "hello thoreau"}
    )
    _write_manifest(evidence_root, ["raw/gutenberg/57393-journal-01/pg57393.txt"])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_passes_when_every_referenced_src_id_resolves(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/gutenberg/57393-journal-01/pg57393.txt": "hello thoreau"}
    )
    _write_manifest(evidence_root, ["raw/gutenberg/57393-journal-01/pg57393.txt"])
    repo_root = tmp_path / "repo"
    _write_normalized_record(repo_root, "SRC-000001")
    _write_normalized_record(repo_root, "SRC-000002", extra_body="See SRC-000001.")

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_and_names_a_dangling_src_id_reference(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/gutenberg/57393-journal-01/pg57393.txt": "hello thoreau"}
    )
    _write_manifest(evidence_root, ["raw/gutenberg/57393-journal-01/pg57393.txt"])
    repo_root = tmp_path / "repo"
    _write_normalized_record(repo_root, "SRC-000001", extra_body="See SRC-999999.")

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "SRC-999999" in errors[0]
    assert "SRC-000001.md" in errors[0]
