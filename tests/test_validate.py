import hashlib

import pytest


from memoria.manifest import format_id, load_manifest, save_manifest
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
    """A manifest ledger listing each of ``entries`` (paths relative to
    ``evidence_root``) with sequential IDs, in the order given."""
    lines = ["units:"]
    for number, entry in enumerate(entries, start=1):
        lines.append(f"  - id: {format_id(number)}")
        lines.append(f"    path: {entry}")
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


def test_validate_fails_when_the_manifest_itself_does_not_exist(tmp_path):
    """Regression: an absent manifest.yaml used to read as an empty ledger
    (right for sync's bootstrap of a brand-new evidence root) and validate
    would report zero errors - an unconfigured corpus looked identical to a
    corpus that matches its manifest exactly."""
    evidence_root = _make_corpus(tmp_path, {"raw/vol-01/text.txt": "hello evidence"})

    errors = validate(evidence_root)

    assert len(errors) == 1
    assert "manifest" in errors[0].lower()


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


def test_validate_rejects_a_duplicate_id_in_the_manifest_ledger(tmp_path):
    evidence_root = _make_corpus(
        tmp_path,
        {"raw/a.txt": "one", "raw/b.txt": "two"},
    )
    manifest_dir = evidence_root / "raw"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    digest_a = hashlib.sha256((evidence_root / "raw/a.txt").read_bytes()).hexdigest()
    digest_b = hashlib.sha256((evidence_root / "raw/b.txt").read_bytes()).hexdigest()
    (manifest_dir / "manifest.yaml").write_text(
        "units:\n"
        f"  - id: SRC-000001\n    path: raw/a.txt\n    sha256: {digest_a}\n"
        f"  - id: SRC-000001\n    path: raw/b.txt\n    sha256: {digest_b}\n"
    )

    errors = validate(evidence_root)

    assert any("duplicate" in e and "SRC-000001" in e for e in errors)


def test_validate_rejects_an_out_of_order_id_in_the_manifest_ledger(tmp_path):
    evidence_root = _make_corpus(
        tmp_path,
        {"raw/a.txt": "one", "raw/b.txt": "two"},
    )
    manifest_dir = evidence_root / "raw"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    digest_a = hashlib.sha256((evidence_root / "raw/a.txt").read_bytes()).hexdigest()
    digest_b = hashlib.sha256((evidence_root / "raw/b.txt").read_bytes()).hexdigest()
    (manifest_dir / "manifest.yaml").write_text(
        "units:\n"
        f"  - id: SRC-000002\n    path: raw/a.txt\n    sha256: {digest_a}\n"
        f"  - id: SRC-000001\n    path: raw/b.txt\n    sha256: {digest_b}\n"
    )

    errors = validate(evidence_root)

    assert any("dense and monotonic" in e for e in errors)


def test_validate_accepts_a_deleted_units_reserved_gap(tmp_path):
    evidence_root = _make_corpus(tmp_path, {"raw/b.txt": "still here"})
    manifest_dir = evidence_root / "raw"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    digest_b = hashlib.sha256((evidence_root / "raw/b.txt").read_bytes()).hexdigest()
    (manifest_dir / "manifest.yaml").write_text(
        "units:\n"
        "  - id: SRC-000001\n    path: raw/a.txt\n    sha256: deadbeef\n    deleted: true\n"
        f"  - id: SRC-000002\n    path: raw/b.txt\n    sha256: {digest_b}\n"
    )

    errors = validate(evidence_root)

    assert errors == []


def test_validate_fails_when_a_records_raw_sha256_is_stale(tmp_path):
    evidence_root = _make_corpus(tmp_path, {"raw/a.txt": "current content"})
    _write_manifest(evidence_root, ["raw/a.txt"])
    repo_root = tmp_path / "repo"
    normalized_dir = repo_root / "sources" / "normalized"
    normalized_dir.mkdir(parents=True)
    (normalized_dir / "SRC-000001.md").write_text(
        "---\nid: SRC-000001\nsource_type: journal\nraw_sha256: stale-hash\n---\n\n"
    )

    errors = validate(evidence_root, repo_root)

    assert any("raw_sha256 mismatch" in e and "SRC-000001.md" in e for e in errors)


# --- converter pinning (#79, part 05 §5.4) ---------------------------------


def _record_converter_pin(evidence_root, suffix, version):
    manifest_path = evidence_root / "raw" / "manifest.yaml"
    entries = load_manifest(manifest_path)
    save_manifest(manifest_path, entries, converters={suffix: version})


def test_validate_fails_when_the_manifest_pin_differs_from_pyprojects(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    _record_converter_pin(evidence_root, ".docx", "markitdown 0.1.5")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text(
        'convert = [\n    "markitdown[docx]==0.1.7",\n    "pdfplumber==0.11.10",\n]\n'
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "markitdown 0.1.5" in errors[0]
    assert "markitdown 0.1.7" in errors[0]


def test_validate_passes_when_the_manifest_pin_matches_pyprojects(tmp_path):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    _record_converter_pin(evidence_root, ".docx", "markitdown 0.1.7")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text(
        'convert = [\n    "markitdown[docx]==0.1.7",\n    "pdfplumber==0.11.10",\n]\n'
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_ignores_a_suffix_the_manifest_has_never_recorded_a_pin_for(
    tmp_path,
):
    evidence_root = _make_corpus(
        tmp_path, {"raw/vol-01/text.txt": "hello evidence"}
    )
    _write_manifest(evidence_root, ["raw/vol-01/text.txt"])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text(
        'convert = [\n    "markitdown[docx]==0.1.7",\n    "pdfplumber==0.11.10",\n]\n'
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


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


# --- #91's three gaps: a missing prompt, a misfiled entry, an unspaced
# relation ------------------------------------------------------------------


def test_validate_fails_a_subject_directory_missing_its_prompt(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    entry_path = repo_root / "subjects" / "people" / "bob.md"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(
        entry_to_markdown(Entry(id="SUB-people/bob", body="Bob.")),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "_subject.md" in errors[0]
    assert "missing" in errors[0].lower()


def test_validate_fails_an_entry_whose_id_disagrees_with_its_directory(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )
    entry_path = repo_root / "subjects" / "people" / "carol.md"
    entry_path.write_text(
        entry_to_markdown(Entry(id="SUB-places/carol", body="Carol.")),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "carol.md" in errors[0]
    assert "SUB-places/carol" in errors[0]
    assert "SUB-people" in errors[0]


def test_validate_passes_an_entry_whose_id_matches_its_directory(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )
    entry_path = repo_root / "subjects" / "people" / "carol.md"
    entry_path.write_text(
        entry_to_markdown(Entry(id="SUB-people/carol", body="Carol.")),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_and_names_an_unspaced_relation_match_term(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_subject_prompt(
        repo_root, "SUB-people", subject_to_markdown(_make_subject())
    )
    entry_path = repo_root / "subjects" / "people" / "bob.md"
    entry_path.write_text(
        entry_to_markdown(
            Entry(
                id="SUB-people/bob",
                match_terms=["SUB-people/bob->pressures->SUB-people/author"],
                body="Bob.",
            )
        ),
        encoding="utf-8",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "bob.md" in errors[0]
    assert "relation" in errors[0].lower()


# --- SES-...#T017 citations: the missing-transcript-turn check (#28) --------


def _write_transcript(repo_root, session_id, turns):
    session_path = (
        repo_root / "sessions" / session_id[4:8] / session_id[8:10] / session_id
    )
    session_path.mkdir(parents=True, exist_ok=True)
    blocks = [
        f'<a id="t{number:03d}"></a>\n\n## T{number:03d} — {role}\n\n{text}'
        for number, role, text in turns
    ]
    (session_path / "transcript.md").write_text(
        "\n\n".join(blocks) + "\n", encoding="utf-8"
    )


def test_validate_passes_when_a_session_turn_citation_resolves(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_transcript(
        repo_root, "SES-20260912-1432", [(1, "Author", "Decide the subject.")]
    )
    (repo_root / "decisions.md").write_text(
        "Decided the subject. See SES-20260912-1432#T001.", encoding="utf-8"
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_and_names_a_missing_transcript_turn(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_transcript(
        repo_root, "SES-20260912-1432", [(1, "Author", "Decide the subject.")]
    )
    (repo_root / "decisions.md").write_text(
        "Decided the subject. See SES-20260912-1432#T017.", encoding="utf-8"
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "SES-20260912-1432#T017" in errors[0]
    assert "decisions.md" in errors[0]


def test_validate_fails_and_names_a_citation_to_a_session_with_no_transcript(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "questions.md").write_text(
        "Raised in SES-20260913-0900#T001.", encoding="utf-8"
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "SES-20260913-0900#T001" in errors[0]
    assert "questions.md" in errors[0]


# --- entry statements: badge, provenance, and where it terminates (#31) ------


def _write_entry(repo_root, entry_id, body):
    subject_id, entry_slug = entry_id.split("/")
    _write_subject_prompt(
        repo_root, subject_id, subject_to_markdown(_make_subject(id=subject_id))
    )
    entry_path = repo_root / "subjects" / subject_id.removeprefix("SUB-") / f"{entry_slug}.md"
    entry_path.write_text(entry_to_markdown(Entry(id=entry_id, body=body)), encoding="utf-8")
    return entry_path


def test_validate_passes_badged_statements_carrying_original_provenance(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_transcript(
        repo_root, "SES-20260912-1432", [(1, "Author", "Bob knew by chapter 5.")]
    )
    _write_entry(
        repo_root, "SUB-people/bob",
        "Bob was born in 1962.\n\n"
        "[source] Bob called on July 17.\n— SRC-000184 ¶17\n\n"
        "[author] Bob knew by chapter 5.\n— SES-20260912-1432#T001\n\n"
        "[inferred] Bob feared losing control.\n— SRC-000184 ¶17\n— SES-20260912-1432#T001\n\n"
        "[open] Maybe he called twice.\n\n"
        "— a dash line in testimony is testimony, not provenance",
    )

    errors = validate(evidence_root, repo_root)

    assert errors == []


def test_validate_fails_an_author_statement_lacking_a_citing_turn(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(
        repo_root, "SUB-people/bob", "[author] Bob knew by chapter 5.\n— SRC-000184 ¶17"
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "citing transcript turn" in errors[0]
    assert "subjects/people/bob.md" in errors[0].replace("\\", "/")


def test_validate_fails_an_author_statement_citing_the_assistants_turn(tmp_path):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_transcript(
        repo_root, "SES-20260912-1432", [(1, "Assistant", "Maybe Bob knew by chapter 5.")]
    )
    _write_entry(
        repo_root, "SUB-people/bob",
        "[author] Bob knew by chapter 5.\n— SES-20260912-1432#T001",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "Assistant" in errors[0]


def test_validate_fails_an_author_statement_whose_turn_is_missing_once_not_twice(tmp_path):
    """A missing turn is already `_validate_session_turns`'s finding; the
    statement check does not report the same hole a second time."""
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(
        repo_root, "SUB-people/bob",
        "[author] Bob knew by chapter 5.\n— SES-20260912-1432#T001",
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "missing transcript turn" in errors[0]


@pytest.mark.parametrize("badge", ["source", "inferred", "author"])
def test_validate_fails_a_badged_statement_lacking_provenance(tmp_path, badge):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(repo_root, "SUB-people/bob", f"[{badge}] Bob called on July 17.")

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "no provenance" in errors[0]
    assert f"[{badge}]" in errors[0]


def test_validate_passes_an_open_line_without_provenance(tmp_path):
    """Part 06 §9.4's own example carries none: `[open]` is exploratory,
    not an assertion, and part 15 §23 lists the three assertion badges."""
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(repo_root, "SUB-people/bob", "[open] Maybe he called twice.")

    assert validate(evidence_root, repo_root) == []


@pytest.mark.parametrize(
    "reference", ["DEC-0001", "RES-20261018-003", "CLM-0041", "SUB-people/alice"]
)
def test_validate_fails_provenance_terminating_in_a_derived_artifact(tmp_path, reference):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(
        repo_root, "SUB-people/bob", f"[inferred] Bob feared losing control.\n— {reference}"
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "original material" in errors[0]
    assert reference in errors[0]


@pytest.mark.parametrize("reference", ["CHP-0001", "chapters/08/draft.md"])
def test_validate_fails_provenance_harvested_from_the_manuscript(tmp_path, reference):
    evidence_root, repo_root = _bare_evidence_and_repo(tmp_path)
    _write_entry(
        repo_root, "SUB-people/bob", f"[source] Bob knew by chapter 5.\n— {reference}"
    )

    errors = validate(evidence_root, repo_root)

    assert len(errors) == 1
    assert "settlement" in errors[0]
