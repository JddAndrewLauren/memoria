"""``memoria normalize``: the skip-unchanged normalization run (part 05 §5.4)."""

from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH
from memoria.normalize import CONVERTERS, normalize
from memoria.records import NORMALIZED_RELATIVE_PATH, read_all
from memoria.repository import Repository


def _write_raw_file(evidence_root, rel_path, content):
    full = evidence_root / "raw" / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return full


def test_normalize_converts_a_new_plain_text_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "First paragraph.\n\nSecond paragraph.")
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    assert report.added_units == ["SRC-000001"]
    assert report.converted == ["SRC-000001"]
    assert report.skipped == []

    (record,) = read_all(repository)
    assert record.id == "SRC-000001"
    assert record.paragraphs == ["First paragraph.", "Second paragraph."]
    assert record.original_file == "raw/a.txt"
    assert record.converter == CONVERTERS[".txt"][1]
    assert len(record.raw_sha256) == 64


def test_a_run_over_unchanged_input_produces_no_diff(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "Hello.\n\nWorld.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    record_path = repository.root / NORMALIZED_RELATIVE_PATH / "SRC-000001.md"
    before = record_path.read_bytes()

    report = normalize(repository, evidence_root)

    after = record_path.read_bytes()
    assert before == after
    assert report.converted == []
    assert report.skipped == ["SRC-000001"]


def test_a_new_unit_that_sorts_before_existing_ones_renumbers_nothing(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "m.txt", "Middle file.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    _write_raw_file(evidence_root, "a.txt", "Alphabetically first.")
    report = normalize(repository, evidence_root)

    records = {r.original_file: r.id for r in read_all(repository)}
    assert records["raw/m.txt"] == "SRC-000001"
    assert records["raw/a.txt"] == "SRC-000002"
    assert report.added_units == ["SRC-000002"]
    assert report.converted == ["SRC-000002"]


def test_deleting_a_raw_unit_leaves_its_number_reserved_and_skips_it(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "Gone soon.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    path_a.unlink()
    _write_raw_file(evidence_root, "b.txt", "New arrival.")
    report = normalize(repository, evidence_root)

    records = {r.original_file: r.id for r in read_all(repository)}
    assert records["raw/b.txt"] == "SRC-000002"
    # The deleted unit's record is untouched; its ID was never reassigned.
    assert "SRC-000001.md" in [
        p.name for p in (repository.root / NORMALIZED_RELATIVE_PATH).glob("*.md")
    ]
    assert report.added_units == ["SRC-000002"]


def test_a_changed_raw_hash_reconverts_only_that_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "Original.")
    _write_raw_file(evidence_root, "b.txt", "Unchanged.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    path_a.write_text("Changed content.")
    report = normalize(repository, evidence_root)

    assert report.converted == ["SRC-000001"]
    assert report.skipped == ["SRC-000002"]
    records = {r.id: r for r in read_all(repository)}
    assert records["SRC-000001"].paragraphs == ["Changed content."]


def test_a_changed_converter_version_reconverts_the_unit(tmp_path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "Content.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    from memoria import normalize as normalize_module

    monkeypatch.setitem(
        normalize_module.CONVERTERS,
        ".txt",
        (normalize_module.convert_plain_text, "plain-text 2"),
    )
    report = normalize(repository, evidence_root)

    assert report.converted == ["SRC-000001"]
    (record,) = read_all(repository)
    assert record.converter == "plain-text 2"


def test_all_forces_every_unit_to_reconvert(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "One.")
    _write_raw_file(evidence_root, "b.txt", "Two.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    report = normalize(repository, evidence_root, force_all=True)

    assert sorted(report.converted) == ["SRC-000001", "SRC-000002"]
    assert report.skipped == []


def test_reconverting_with_force_all_is_still_byte_identical(tmp_path):
    """The real idempotence check: forcing a reconversion of unchanged input
    must reproduce exactly the same bytes, not merely be skipped. A
    skip-path-only byte-identity test would pass even if the converter or
    the serializer were nondeterministic, since it would never re-run
    either of them on unchanged input."""
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "One.\n\nTwo.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    record_path = repository.root / NORMALIZED_RELATIVE_PATH / "SRC-000001.md"
    before = record_path.read_bytes()

    report = normalize(repository, evidence_root, force_all=True)

    assert report.converted == ["SRC-000001"]
    assert record_path.read_bytes() == before


def test_a_unit_with_no_registered_converter_is_reported_but_not_converted(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.docx", "not really a docx")
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    assert report.added_units == ["SRC-000001"]
    assert report.unconvertible == ["SRC-000001"]
    assert report.converted == []
    assert read_all(repository) == []
