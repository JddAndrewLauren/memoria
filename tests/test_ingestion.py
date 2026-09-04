"""The ingestion status: what the ledger, the records and the index say
about each raw unit, derived and never recorded (part 05 §5.4's "the record
is the state"), plus the two model-free runs the web adapter may launch
(ADR-0011).
"""

from __future__ import annotations

import ast
import hashlib
import threading
from pathlib import Path

import pytest

from memoria import extraction as ex
from memoria.index import INDEX_RELATIVE_PATH, build_index
from memoria.ingestion import (
    CONVERTED_STATES,
    AddedRawUnit,
    RawUnitError,
    RawUnitExists,
    RunInProgress,
    _RUN_LOCK,
    add_raw_unit,
    ingestion_status,
    run_normalize,
    run_rebuild,
    unprocessed_units,
)
from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH, load_manifest, save_manifest
from memoria.normalize import CONVERTERS, EMAIL_CONVERTER_VERSION, normalize
from memoria.records import read_all
from memoria.repository import NoEvidenceRoot, Repository
from memoria.subjects import write_builtin_subjects
from test_normalize import _email_message, _write_mbox, _write_raw_file

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _corpus(tmp_path, *files: tuple[str, str]) -> tuple[Repository, Path]:
    evidence_root = tmp_path / "evidence"
    for rel_path, content in files:
        _write_raw_file(evidence_root, rel_path, content)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return Repository(root=repo_root, evidence_root=evidence_root), evidence_root


def _unit(status, unit_id):
    (unit,) = [u for u in status.units if u.id == unit_id]
    return unit


# --- not checked --------------------------------------------------------------


def test_status_is_not_checked_without_an_evidence_root(tmp_path):
    status = ingestion_status(Repository(root=tmp_path))

    assert status.units is None
    assert unprocessed_units(Repository(root=tmp_path)) is None
    # The keys are the same on every report, checked or not.
    assert set(status.counts) == set(CONVERTED_STATES) | {"indexed", "extracted_complete"}
    assert status.is_normalized is False
    assert status.is_indexed is False


def test_an_empty_ledger_is_a_value(tmp_path):
    repository, _ = _corpus(tmp_path)

    status = ingestion_status(repository)

    assert status.units == ()


# --- the conversion states ----------------------------------------------------


def test_a_unit_in_the_ledger_with_no_record_is_not_yet_converted(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"))
    sha = hashlib.sha256(b"hello").hexdigest()
    (evidence_root / "raw" / "manifest.yaml").write_text(
        f"units:\n- id: SRC-000001\n  path: raw/one.txt\n  sha256: {sha}\n", encoding="utf-8"
    )

    unit = _unit(ingestion_status(repository), "SRC-000001")

    assert unit.converted == "not_yet_converted"
    assert unit.record_paragraphs is None
    assert unit.extracted_paragraphs is None
    assert unprocessed_units(repository) == ("SRC-000001",)


def test_a_converted_unit_is_current(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    normalize(repository, evidence_root)

    status = ingestion_status(repository)
    unit = _unit(status, "SRC-000001")

    assert unit.converted == "current"
    assert unit.record_paragraphs == 2
    assert unit.failure_reason is None
    assert status.counts["current"] == 1
    assert status.is_normalized is True
    assert unprocessed_units(repository) == ()


def test_a_changed_raw_hash_reads_as_out_of_date(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"))
    normalize(repository, evidence_root)
    _write_raw_file(evidence_root, "one.txt", "hello, changed")
    # The ledger's hash moves on the next sync; until then the record and
    # the ledger agree, so re-sync the ledger without converting.
    entries = load_manifest(evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH)
    from dataclasses import replace

    changed = hashlib.sha256(b"hello, changed").hexdigest()
    save_manifest(
        evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH,
        [replace(entries[0], sha256=changed)],
    )

    unit = _unit(ingestion_status(repository), "SRC-000001")

    assert unit.converted == "out_of_date"
    # Processed once; what changed since is a reconversion, not an addition.
    assert unprocessed_units(repository) == ()


def test_a_bumped_converter_pin_reads_as_out_of_date(tmp_path, monkeypatch):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"))
    normalize(repository, evidence_root)
    converter, _ = CONVERTERS[".txt"]
    monkeypatch.setitem(CONVERTERS, ".txt", (converter, lambda: "plain-text 2"))

    unit = _unit(ingestion_status(repository), "SRC-000001")

    assert unit.converted == "out_of_date"


def test_a_failed_unit_carries_its_reason(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("a.pdf", "not a pdf at all"))
    report = normalize(repository, evidence_root)

    status = ingestion_status(repository)
    unit = _unit(status, "SRC-000001")

    assert unit.converted == "failed"
    assert unit.failure_reason == report.failed["SRC-000001"]
    assert status.counts["failed"] == 1
    assert unprocessed_units(repository) == ("SRC-000001",)


def test_an_unregistered_suffix_is_unconvertible(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("photo.heic", "not really"))
    normalize(repository, evidence_root)

    unit = _unit(ingestion_status(repository), "SRC-000001")

    assert unit.converted == "unconvertible"
    assert unprocessed_units(repository) == ("SRC-000001",)


def test_a_deleted_unit_keeps_its_reserved_number(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"), ("two.txt", "world"))
    normalize(repository, evidence_root)
    (evidence_root / "raw" / "one.txt").unlink()
    normalize(repository, evidence_root)

    status = ingestion_status(repository)

    assert [u.id for u in status.units] == ["SRC-000001", "SRC-000002"]
    assert _unit(status, "SRC-000001").converted == "deleted"
    assert _unit(status, "SRC-000001").deleted is True
    # A reserved number is not an addition awaiting processing (ADR-0006).
    assert unprocessed_units(repository) == ()


def test_an_email_export_is_a_container_and_its_messages_are_units(tmp_path):
    repository, evidence_root = _corpus(tmp_path)
    _write_mbox(
        evidence_root,
        "box.mbox",
        [
            _email_message(
                from_="a@x.test",
                to="b@x.test",
                date="Mon, 01 Jan 2024 10:00:00 +0000",
                message_id="<one@x.test>",
                body="First message.",
            ),
            _email_message(
                from_="b@x.test",
                to="a@x.test",
                date="Mon, 01 Jan 2024 11:00:00 +0000",
                message_id="<two@x.test>",
                body="Second message.",
            ),
        ],
    )
    normalize(repository, evidence_root)

    status = ingestion_status(repository)

    by_state = {u.id: u.converted for u in status.units}
    assert by_state["SRC-000001"] == "container"
    assert {by_state["SRC-000002"], by_state["SRC-000003"]} == {"current"}
    assert _unit(status, "SRC-000002").email_message_index is not None
    assert (read_all(repository)[0]).converter == EMAIL_CONVERTER_VERSION
    assert status.counts["container"] == 1
    assert unprocessed_units(repository) == ()


def test_a_record_with_no_paragraphs_is_a_stub(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("empty.txt", ""))
    normalize(repository, evidence_root)

    unit = _unit(ingestion_status(repository), "SRC-000001")

    assert unit.converted == "stub"
    assert unit.record_paragraphs == 0


# --- the index and the extraction --------------------------------------------


def test_indexed_is_none_until_rebuild_and_counts_rows_after(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    normalize(repository, evidence_root)

    before = ingestion_status(repository)
    assert before.is_indexed is False
    assert _unit(before, "SRC-000001").indexed_paragraphs is None
    assert before.counts["indexed"] == 0

    build_index(repository, read_all(repository))

    after = ingestion_status(repository)
    assert after.is_indexed is True
    assert _unit(after, "SRC-000001").indexed_paragraphs == 2
    assert after.counts["indexed"] == 1


def test_extracted_counts_memo_rows_under_the_current_digest(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    write_builtin_subjects(repository)
    normalize(repository, evidence_root)
    build_index(repository, read_all(repository))

    assert _unit(ingestion_status(repository), "SRC-000001").extracted_paragraphs == 0

    record = read_all(repository)[0]
    ex.record_extraction(repository, record.anchor_id(1), ex.ParagraphExtraction())

    status = ingestion_status(repository)
    assert _unit(status, "SRC-000001").extracted_paragraphs == 1
    assert status.counts["extracted_complete"] == 0

    ex.record_extraction(repository, record.anchor_id(2), ex.ParagraphExtraction())

    status = ingestion_status(repository)
    assert _unit(status, "SRC-000001").extracted_paragraphs == 2
    assert status.counts["extracted_complete"] == 1
    # The same answer `pending_paragraphs` gives, grouped by record.
    assert ex.pending_paragraphs(repository) == []


def test_status_never_creates_the_index_file(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"))
    normalize(repository, evidence_root)

    ingestion_status(repository)

    assert not (repository.root / INDEX_RELATIVE_PATH).exists()


# --- model-free, write-free -----------------------------------------------------


def test_no_model_client_is_importable_from_ingestion_py():
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib"}
    tree = ast.parse((SRC_ROOT / "ingestion.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] not in forbidden


def test_computing_the_status_writes_nothing(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello"))
    normalize(repository, evidence_root)
    build_index(repository, read_all(repository))
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}

    ingestion_status(repository)

    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


# --- the two runs (ADR-0011) ---------------------------------------------------


def test_run_normalize_converts_and_reports_counts(tmp_path):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"), ("a.pdf", "not a pdf"))

    outcome = run_normalize(repository)

    assert outcome.kind == "normalize"
    assert outcome.summary["added_units"] == 2
    assert outcome.summary["converted"] == 1
    assert outcome.summary["failed"] == 1
    assert outcome.elapsed_seconds >= 0
    # Numbered in path order: a.pdf first, one.txt second.
    assert _unit(ingestion_status(repository), "SRC-000002").converted == "current"


def test_run_normalize_needs_an_evidence_root(tmp_path):
    with pytest.raises(NoEvidenceRoot):
        run_normalize(Repository(root=tmp_path))


def test_run_rebuild_indexes_the_records_without_an_embedder(tmp_path, monkeypatch):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "hello\n\nworld"))
    write_builtin_subjects(repository)
    normalize(repository, evidence_root)

    seen = {}
    import memoria.ingestion as ingestion

    real = ingestion.rebuild_index

    def spy(repo, **kwargs):
        seen.update(kwargs)
        return real(repo, **kwargs)

    monkeypatch.setattr(ingestion, "rebuild_index", spy)

    outcome = run_rebuild(repository)

    assert seen["embed_fn"] is None
    assert outcome.kind == "rebuild"
    assert outcome.summary["records"] == 1
    assert outcome.summary["paragraphs"] == 2
    assert _unit(ingestion_status(repository), "SRC-000001").indexed_paragraphs == 2


def test_a_run_refuses_while_another_holds_the_lock(tmp_path):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"))
    assert _RUN_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(RunInProgress):
            run_normalize(repository)
        with pytest.raises(RunInProgress):
            run_rebuild(repository)
    finally:
        _RUN_LOCK.release()


def test_the_lock_is_released_after_a_run_even_when_it_raises(tmp_path, monkeypatch):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"))
    import memoria.ingestion as ingestion

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingestion, "run_normalize_pass", boom)
    with pytest.raises(RuntimeError):
        run_normalize(repository)

    assert _RUN_LOCK.acquire(blocking=False)
    _RUN_LOCK.release()


def test_the_lock_serialises_concurrent_runs(tmp_path):
    repository, _ = _corpus(tmp_path, ("one.txt", "hello"))
    import memoria.ingestion as ingestion

    started = threading.Event()
    release = threading.Event()
    real = ingestion.run_normalize_pass

    def slow(repo, root, **kwargs):
        started.set()
        release.wait(timeout=5)
        return real(repo, root, **kwargs)

    ingestion.run_normalize_pass = slow
    try:
        worker = threading.Thread(target=run_normalize, args=(repository,))
        worker.start()
        assert started.wait(timeout=5)
        with pytest.raises(RunInProgress):
            run_rebuild(repository)
    finally:
        release.set()
        worker.join(timeout=10)
        ingestion.run_normalize_pass = real


# --- adding a raw unit (ADR-0013) ------------------------------------------------


def test_add_raw_unit_writes_the_bytes_under_raw_keeping_the_folder_shape(tmp_path):
    repository, evidence_root = _corpus(tmp_path)

    added = add_raw_unit(repository, "letters/1952/march.txt", b"hello\n\nworld")

    assert added == AddedRawUnit(path="raw/letters/1952/march.txt", size=12)
    assert (evidence_root / "raw" / "letters" / "1952" / "march.txt").read_bytes() == b"hello\n\nworld"
    # No stray temp file is left beside it.
    assert [p.name for p in (evidence_root / "raw" / "letters" / "1952").iterdir()] == ["march.txt"]


def test_add_raw_unit_refuses_a_path_already_taken_and_leaves_it_untouched(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("one.txt", "original"))

    with pytest.raises(RawUnitExists) as excinfo:
        add_raw_unit(repository, "one.txt", b"replacement")

    assert excinfo.value.path == "raw/one.txt"
    assert (evidence_root / "raw" / "one.txt").read_text() == "original"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "   ",
        "/abs.txt",
        "../out.txt",
        "a/../b.txt",
        ".DS_Store",
        "dir/.hidden/x.txt",
        "manifest.yaml",
        "dir\\file.txt",
        "bad\0name.txt",
    ],
)
def test_add_raw_unit_refuses_a_path_the_ledger_must_never_see(tmp_path, path):
    repository, evidence_root = _corpus(tmp_path)

    with pytest.raises(RawUnitError):
        add_raw_unit(repository, path, b"x")

    assert not (evidence_root / "raw").exists() or not list((evidence_root / "raw").rglob("*"))


def test_add_raw_unit_needs_an_evidence_root(tmp_path):
    with pytest.raises(NoEvidenceRoot):
        add_raw_unit(Repository(root=tmp_path), "one.txt", b"x")


def test_add_raw_unit_does_not_touch_the_ledger_and_the_next_normalize_numbers_it(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("b.txt", "first"))
    normalize(repository, evidence_root)

    add_raw_unit(repository, "a.txt", b"second")
    ids_before = [e.id for e in load_manifest(evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH)]
    normalize(repository, evidence_root)

    entries = load_manifest(evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH)
    assert ids_before == ["SRC-000001"]
    # Sorted-path order would put a.txt first, but the ledger never
    # renumbers (ADR-0006): the newcomer takes the next id.
    assert [(e.id, e.path) for e in entries] == [
        ("SRC-000001", "raw/b.txt"),
        ("SRC-000002", "raw/a.txt"),
    ]


def test_status_names_the_raw_files_the_ledger_has_not_numbered(tmp_path):
    repository, evidence_root = _corpus(tmp_path, ("b.txt", "one"))
    normalize(repository, evidence_root)
    _write_raw_file(evidence_root, "box/a.txt", "two")
    _write_raw_file(evidence_root, "c.txt", "three")

    status = ingestion_status(repository)

    assert status.unnumbered == ("raw/box/a.txt", "raw/c.txt")
    assert [u.path for u in status.units] == ["raw/b.txt"]
    normalize(repository, evidence_root)
    assert ingestion_status(repository).unnumbered == ()
    assert ingestion_status(Repository(root=tmp_path)).unnumbered is None
