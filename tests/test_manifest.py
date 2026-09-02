"""The evidence manifest as an ID ledger (ADR-0006)."""

from memoria.manifest import (
    ManifestEntry,
    check_ledger,
    load_converter_pins,
    load_manifest,
    save_manifest,
    sync,
)


def _write_raw_file(evidence_root, rel_path, content):
    full = evidence_root / "raw" / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return full


def test_sync_assigns_the_next_id_to_a_new_raw_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "hello")

    entries, added = sync(evidence_root)

    assert [e.id for e in entries] == ["SRC-000001"]
    assert added == ["SRC-000001"]
    assert entries[0].path == "raw/a.txt"


def test_a_second_sync_over_unchanged_input_adds_nothing(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "hello")
    entries, _ = sync(evidence_root)
    save_manifest(evidence_root / "raw" / "manifest.yaml", entries)

    entries2, added2 = sync(evidence_root)

    assert added2 == []
    assert entries2 == entries


def test_a_new_unit_that_sorts_before_existing_ones_renumbers_nothing(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "m.txt", "middle")
    entries, _ = sync(evidence_root)
    save_manifest(evidence_root / "raw" / "manifest.yaml", entries)
    original_id = entries[0].id

    # "a.txt" sorts before "m.txt".
    _write_raw_file(evidence_root, "a.txt", "first alphabetically")
    entries2, added2 = sync(evidence_root)

    by_path = {e.path: e for e in entries2}
    assert by_path["raw/m.txt"].id == original_id
    assert added2 == [by_path["raw/a.txt"].id]
    assert by_path["raw/a.txt"].id != original_id


def test_deleting_a_raw_unit_leaves_its_number_reserved(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "hello")
    entries, _ = sync(evidence_root)
    save_manifest(evidence_root / "raw" / "manifest.yaml", entries)
    deleted_id = entries[0].id

    path_a.unlink()
    _write_raw_file(evidence_root, "b.txt", "new content")
    entries2, added2 = sync(evidence_root)

    by_path = {e.path: e for e in entries2}
    assert by_path["raw/a.txt"].id == deleted_id
    assert by_path["raw/a.txt"].deleted is True
    # The new unit gets the next number, not the reserved one.
    assert added2 == [by_path["raw/b.txt"].id]
    assert by_path["raw/b.txt"].id != deleted_id


def test_a_changed_raw_hash_is_picked_up_on_the_existing_id(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "hello")
    entries, _ = sync(evidence_root)
    save_manifest(evidence_root / "raw" / "manifest.yaml", entries)
    original_id = entries[0].id
    original_sha = entries[0].sha256

    path_a.write_text("changed content")
    entries2, added2 = sync(evidence_root)

    assert added2 == []
    assert entries2[0].id == original_id
    assert entries2[0].sha256 != original_sha


def test_check_ledger_accepts_a_dense_monotonic_ledger():
    entries = [
        ManifestEntry(id="SRC-000001", path="raw/a.txt", sha256="x"),
        ManifestEntry(id="SRC-000002", path="raw/b.txt", sha256="y", deleted=True),
        ManifestEntry(id="SRC-000003", path="raw/c.txt", sha256="z"),
    ]
    assert check_ledger(entries) == []


def test_check_ledger_rejects_a_duplicate_id():
    entries = [
        ManifestEntry(id="SRC-000001", path="raw/a.txt", sha256="x"),
        ManifestEntry(id="SRC-000001", path="raw/b.txt", sha256="y"),
    ]
    errors = check_ledger(entries)
    assert any("duplicate" in e and "SRC-000001" in e for e in errors)


def test_check_ledger_rejects_an_out_of_order_id():
    entries = [
        ManifestEntry(id="SRC-000002", path="raw/a.txt", sha256="x"),
        ManifestEntry(id="SRC-000001", path="raw/b.txt", sha256="y"),
    ]
    errors = check_ledger(entries)
    assert any("dense and monotonic" in e for e in errors)


def test_sync_over_a_non_dense_ledger_never_reuses_a_live_id(tmp_path):
    """Regression: a ledger with a gap (SRC-000001, SRC-000003 - e.g.
    hand-edited, or reconstructed from a partial sync) used to compute the
    next ID from ``len(entries) + 1``, colliding with an ID already in use
    rather than skipping past it."""
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "first")
    _write_raw_file(evidence_root, "c.txt", "third")
    manifest_path = evidence_root / "raw" / "manifest.yaml"
    save_manifest(
        manifest_path,
        [
            ManifestEntry(id="SRC-000001", path="raw/a.txt", sha256="stale"),
            ManifestEntry(id="SRC-000003", path="raw/c.txt", sha256="stale"),
        ],
    )

    _write_raw_file(evidence_root, "new.txt", "brand new unit")
    entries, added = sync(evidence_root)

    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids)), f"duplicate IDs in ledger: {ids}"
    assert added == ["SRC-000004"]


def test_load_manifest_is_empty_when_no_file_exists(tmp_path):
    assert load_manifest(tmp_path / "raw" / "manifest.yaml") == []


def test_save_and_load_manifest_round_trips(tmp_path):
    entries = [
        ManifestEntry(id="SRC-000001", path="raw/a.txt", sha256="x"),
        ManifestEntry(id="SRC-000002", path="raw/b.txt", sha256="y", deleted=True),
    ]
    manifest_path = tmp_path / "raw" / "manifest.yaml"
    save_manifest(manifest_path, entries)

    assert load_manifest(manifest_path) == entries


def test_load_converter_pins_is_empty_when_no_file_exists(tmp_path):
    assert load_converter_pins(tmp_path / "raw" / "manifest.yaml") == {}


def test_save_and_load_converter_pins_round_trip(tmp_path):
    manifest_path = tmp_path / "raw" / "manifest.yaml"
    entries = [ManifestEntry(id="SRC-000001", path="raw/a.docx", sha256="x")]

    save_manifest(manifest_path, entries, converters={".docx": "markitdown 0.1.7"})

    assert load_converter_pins(manifest_path) == {".docx": "markitdown 0.1.7"}
    assert load_manifest(manifest_path) == entries


def test_save_manifest_omits_converters_when_none_given(tmp_path):
    """A caller that never passes ``converters`` (every one but
    ``memoria.normalize``) writes exactly the file this always wrote."""
    manifest_path = tmp_path / "raw" / "manifest.yaml"
    entries = [ManifestEntry(id="SRC-000001", path="raw/a.txt", sha256="x")]

    save_manifest(manifest_path, entries)

    assert "converters" not in manifest_path.read_text(encoding="utf-8")
