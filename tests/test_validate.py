import hashlib


from memoria.subjects import Entry, Subject, entry_to_markdown, subject_to_markdown
from memoria.validate import validate


def _make_subject(**overrides):
    fields = dict(
        id="SUB-people",
        match="An entry under People represents a person.",
        hazards="Do not merge people sharing a surname without corroboration.",
        audit_questions="Does the passage contradict a settled fact about this person?",
        auto_promote=False,
    )
    fields.update(overrides)
    return Subject(**fields)


def _write_manifest(evidence_root, entries):
    lines = ["base: raw", "files:"]
    for entry in entries:
        lines.append(f"  - path: {entry}")
        content = (evidence_root / entry).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        lines.append(f"    sha256: {digest}")
    manifest_dir = evidence_root / "raw"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text("\n".join(lines) + "\n")


def _make_corpus(tmp_path, files):
    evidence_root = tmp_path / "evidence"
    for rel_path, content in files.items():
        full = evidence_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return evidence_root


def test_validate_passes_when_hashes_match(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])

    errors = validate(evidence_root)

    assert errors == []


def test_validate_fails_and_names_file_when_raw_file_modified(tmp_path):
    rel_path = "raw/vol-01/text.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello evidence"})
    _write_manifest(evidence_root, [rel_path])

    (evidence_root / rel_path).write_text("tampered content")

    errors = validate(evidence_root)

    assert len(errors) == 1
    assert rel_path in errors[0]


def test_validate_does_not_modify_the_evidence_tree(tmp_path):
    rel_path = "raw/vol-01/text.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello evidence"})
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
    rel_path = "raw/vol-01/text.txt"
    evidence_root = _make_corpus(tmp_path, {rel_path: "hello evidence"})
    _write_manifest(evidence_root, [rel_path])

    (evidence_root / rel_path).unlink()

    errors = validate(evidence_root)

    assert len(errors) == 1
    assert rel_path in errors[0]


def _write_normalized_record(repo_root, record_id, extra_body=""):
    normalized_dir = repo_root / "sources" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / f"{record_id}.md").write_text(
        f"---\nid: {record_id}\nsource_type: journal\n---\n\n{extra_body}\n"
    )


def test_validate_passes_when_no_normalized_records_directory_exists(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_passes_when_every_referenced_src_id_resolves(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    repo_root = tmp_path / "repo"
    _write_normalized_record(repo_root, "SRC-000001")
    _write_normalized_record(repo_root, "SRC-000002", extra_body="See SRC-000001.")

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_and_names_a_dangling_src_id_reference(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    repo_root = tmp_path / "repo"
    _write_normalized_record(repo_root, "SRC-000001", extra_body="See SRC-999999.")

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "SRC-999999" in errors[0]
    assert "SRC-000001.md" in errors[0]


# --- subject prompts: `memoria validate` fails one missing any of the four -


def _bare_evidence_and_repo(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    return evidence_root, tmp_path / "repo"


def _write_subject_prompt(repo_root, subject_id, text):
    slug = subject_id.removeprefix("SUB-")
    subject_dir = repo_root / "subjects" / slug
    subject_dir.mkdir(parents=True, exist_ok=True)
    (subject_dir / "_subject.md").write_text(text, encoding="utf-8")


def test_validate_passes_a_complete_subject_prompt(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_a_subject_prompt_missing_the_match_declaration(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    text = subject_to_markdown(_make_subject()).replace("## Match", "## Matching")
    _write_subject_prompt(repo_root, "SUB-people", text)

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "match" in errors[0].lower()
    assert "_subject.md" in errors[0]


def test_validate_fails_a_subject_prompt_missing_the_hazards_declaration(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    text = subject_to_markdown(_make_subject()).replace("## Hazards", "## Risks")
    _write_subject_prompt(repo_root, "SUB-people", text)

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "hazards" in errors[0].lower()


def test_validate_fails_a_subject_prompt_missing_the_audit_questions_declaration(
    tmp_path,
):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    text = subject_to_markdown(_make_subject()).replace(
        "## Audit questions", "## Audit"
    )
    _write_subject_prompt(repo_root, "SUB-people", text)

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "audit questions" in errors[0].lower()


def test_validate_fails_a_subject_prompt_missing_auto_promote(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    text = subject_to_markdown(_make_subject()).replace("auto-promote: false\n", "")
    _write_subject_prompt(repo_root, "SUB-people", text)

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "auto-promote" in errors[0]


def test_validate_passes_when_no_subjects_directory_exists(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    repo_root.mkdir()

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_and_names_a_malformed_match_term_on_an_entry(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )
    entry_path = repo_root / "subjects" / "people" / "bob.md"
    entry_path.write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["SUB-People/Bob"], body="Bob.")
        ),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "bob.md" in errors[0]
    assert "entry" in errors[0].lower()


def test_validate_accepts_every_match_term_shape_on_an_entry(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )
    entry_path = repo_root / "subjects" / "people" / "bob.md"
    entry_path.write_text(
        entry_to_markdown(
            Entry(
                id="SUB-people/bob",
                match_terms=[
                    "Bob",
                    "SUB-people/bob",
                    "SUB-people/bob -> pressures -> SUB-people/author",
                ],
                body="Bob.",
            )
        ),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []
