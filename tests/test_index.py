import os

import pytest

from memoria.normalize import NormalizedRecord
from memoria.index import build_index, rebuild, search

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


def _record(record_id, paragraphs, source_type="journal"):
    return NormalizedRecord(
        id=record_id,
        source_type=source_type,
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="unresolved",
        contemporaneous=True,
        original_file="raw/gutenberg/57393-journal-01/pg57393.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=paragraphs,
    )


def test_search_finds_a_record_by_its_paragraph_text(tmp_path):
    db_path = tmp_path / "index.db"
    records = [_record("SRC-000001", ["The fox ran through the woods."])]

    build_index(db_path, records)
    results = search(db_path, "fox")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000001"


def test_search_returns_the_specific_paragraph_anchor_that_matched(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record(
            "SRC-000002",
            ["First paragraph, no match here.", "Second paragraph mentions a badger."],
        )
    ]

    build_index(db_path, records)
    results = search(db_path, "badger")

    assert len(results) == 1
    assert results[0].src_id == "SRC-000002"
    assert results[0].anchor == "src-000002-p2"


def test_search_can_exclude_editorial_records(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record("SRC-000003", ["Thoreau saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]

    build_index(db_path, records)
    results = search(db_path, "heron", exclude_editorial=True)

    assert [r.src_id for r in results] == ["SRC-000003"]


def test_search_includes_editorial_records_by_default(tmp_path):
    db_path = tmp_path / "index.db"
    records = [
        _record("SRC-000003", ["Thoreau saw a heron by the pond."], source_type="journal"),
        _record(
            "SRC-000004",
            ["The editor notes that a heron was a common sight."],
            source_type="editorial",
        ),
    ]

    build_index(db_path, records)
    results = search(db_path, "heron")

    assert {r.src_id for r in results} == {"SRC-000003", "SRC-000004"}


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_rebuild_writes_normalized_records_and_builds_a_searchable_index(tmp_path):
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    rebuild(evidence_root, repo_root)

    normalized = list((repo_root / "sources" / "normalized").glob("SRC-*.md"))
    assert len(normalized) == 558

    db_path = repo_root / ".memoria" / "index.db"
    assert db_path.is_file()

    results = search(db_path, "woodchuck")
    assert len(results) > 0


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_rebuild_after_deleting_the_index_reproduces_identical_search_results(
    tmp_path,
):
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    rebuild(evidence_root, repo_root)
    db_path = repo_root / ".memoria" / "index.db"
    before = search(db_path, "woodchuck")

    db_path.unlink()
    rebuild(evidence_root, repo_root)
    after = search(db_path, "woodchuck")

    assert before == after


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_rebuild_resolves_years_and_never_leaves_a_record_unresolved(tmp_path):
    # Regression test (PR #50 review round 1): rebuild() re-derives
    # normalized records from evidence via normalize_journals alone, which
    # produces date_confidence: unresolved - it must also call
    # resolve_years(), or every rebuild silently discards year resolution
    # (docs/normalized-record-schema.md's date_confidence contract, and
    # rebuild()'s own "losing nothing" (§42) docstring).
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    records = rebuild(evidence_root, repo_root)

    assert all(r.date_confidence != "unresolved" for r in records)
    assert {r.date_confidence for r in records} <= {"exact", "inferred", "chapter-only"}
