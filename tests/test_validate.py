import hashlib
import os

import pytest
import yaml

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


# --- The answer key (issue #9) ------------------------------------------
#
# The key is committed while the normalized records it points into are
# derived and gitignored, so the two can drift apart with nothing to say
# so. These cover the check that notices.


def _write_record_with_paragraphs(repo_root, record_id, paragraphs):
    normalized_dir = repo_root / "sources" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(
        f'<a id="{record_id.lower()}-p{n}"></a>\n\n{text}'
        for n, text in enumerate(paragraphs, start=1)
    )
    (normalized_dir / f"{record_id}.md").write_text(
        f"---\nid: {record_id}\nsource_type: book\n---\n\n{body}\n"
    )


def _write_answer_key(repo_root, target_text, status="resolved"):
    benchmark_dir = repo_root / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "answer-key.yaml").write_text(
        yaml.safe_dump(
            {
                "links": [
                    {
                        "link_id": "src-000001-p1/Walden",
                        "status": status,
                        "source_record_id": "SRC-000001",
                        "source_anchor": "src-000001-p1",
                        "target_anchors": ["src-000002-p1", "src-000002-p2"],
                        "target_text": target_text,
                    }
                ]
            },
            sort_keys=False,
        )
    )


def _corpus_with_key(tmp_path, target_text, status="resolved"):
    evidence_root = _make_corpus(
        tmp_path, {"raw/gutenberg/57393-journal-01/pg57393.txt": "hello thoreau"}
    )
    _write_manifest(evidence_root, ["raw/gutenberg/57393-journal-01/pg57393.txt"])
    repo_root = tmp_path / "repo"
    _write_record_with_paragraphs(repo_root, "SRC-000001", ["the journal side"])
    _write_record_with_paragraphs(repo_root, "SRC-000002", ["first half", "second half"])
    _write_answer_key(repo_root, target_text, status)
    return evidence_root, repo_root


def test_validate_passes_when_the_key_still_quotes_its_anchors(tmp_path):
    evidence_root, repo_root = _corpus_with_key(tmp_path, "first half\n\nsecond half")

    assert validate(evidence_root, repo_root) == []


def test_validate_catches_a_key_whose_target_text_has_gone_stale(tmp_path):
    # What a renumbering normalizer change would do to a committed key.
    evidence_root, repo_root = _corpus_with_key(tmp_path, "first half\n\nWRONG")

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "src-000001-p1/Walden" in errors[0]
    assert "no longer matches" in errors[0]


def test_validate_catches_a_key_pointing_at_an_anchor_that_is_gone(tmp_path):
    evidence_root, repo_root = _corpus_with_key(tmp_path, "first half\n\nsecond half")
    _write_record_with_paragraphs(repo_root, "SRC-000002", ["first half"])

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "src-000002-p2" in errors[0]


def test_validate_does_not_ask_a_rejected_row_for_a_target(tmp_path):
    # A row the two editions disagreed about carries no target at all, and
    # must not be read as a broken resolved row.
    evidence_root, repo_root = _corpus_with_key(
        tmp_path, "", status="editions-disagree"
    )

    assert validate(evidence_root, repo_root) == []
