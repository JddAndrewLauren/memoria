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


@pytest.mark.m0
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
    # 587 journal + 130 letter + 27 book records (issue #6 review round 1:
    # rebuild() used to call normalize_journals alone, silently deleting
    # every letter record on a rebuild).
    assert len(normalized) == 744

    db_path = repo_root / ".memoria" / "index.db"
    assert db_path.is_file()

    results = search(db_path, "woodchuck")
    assert len(results) > 0


@pytest.mark.m0
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


@pytest.mark.m0
@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_rebuild_resolves_years_and_never_leaves_a_journal_record_unresolved(
    tmp_path,
):
    # Regression test (PR #50 review round 1): rebuild() re-derives
    # normalized records from evidence via normalize_journals alone, which
    # produces date_confidence: unresolved - it must also call
    # resolve_years(), or every rebuild silently discards year resolution
    # (docs/normalized-record-schema.md's date_confidence contract, and
    # rebuild()'s own "losing nothing" (§42) docstring).
    #
    # Scoped to journal records deliberately (issue #6 review round 1):
    # resolve_years() only ever touches journal records (it filters by
    # original_file against JOURNAL_VOLUMES). Letters get their
    # date_confidence resolved separately, directly inside
    # normalize_letters (issue #57) - 126 of 130 real letters resolve to
    # `inferred` (an explicit, unambiguous year in the dateline), and the
    # remaining 4 stay `unresolved` (see docs/normalized-record-schema.md's
    # Letters section and tests/test_letters.py's real-corpus split test).
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    records = rebuild(evidence_root, repo_root)
    journal_records = [r for r in records if r.source_type == "journal"]
    letter_records = [r for r in records if r.source_type == "letter"]

    assert all(r.date_confidence != "unresolved" for r in journal_records)
    assert {r.date_confidence for r in journal_records} <= {
        "exact",
        "inferred",
        "chapter-only",
    }
    assert letter_records, "rebuild() must not drop the letter records"
    assert {r.date_confidence for r in letter_records} <= {"inferred", "unresolved"}
    assert any(r.date_confidence == "inferred" for r in letter_records)


@pytest.mark.m0
@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_rebuild_strips_editorial_apparatus_and_exclude_editorial_excludes_it(
    tmp_path,
):
    # Regression test for PR #51 review round 1, BLOCKING 1: a plain
    # `rebuild()` used to index unstripped paragraphs (never calling
    # extract_editorial_apparatus) and never index EditorialRecords at
    # all, so exclude_editorial excluded nothing. A query that only
    # matches editorial apparatus text must find real matches by default
    # and none once excluded, and every remaining match must be tagged
    # source_type "editorial".
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    rebuild(evidence_root, repo_root)
    db_path = repo_root / ".memoria" / "index.db"

    with_editorial = search(db_path, "sic")
    without_editorial = search(db_path, "sic", exclude_editorial=True)

    assert len(with_editorial) > 0
    assert len(without_editorial) == 0
    assert {r.source_type for r in with_editorial} == {"editorial"}

    editorial_written = list((repo_root / "sources" / "editorial").glob("ED-*.md"))
    # See tests/test_cli.py::test_normalize_writes_editorial_records_under_sources_editorial
    # for the count breakdown (issue #56 extended this to the letters volume).
    assert len(editorial_written) == 1287


@pytest.mark.m0
@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
def test_search_excludes_letters_editorial_content(tmp_path):
    # Issue #56's own acceptance criterion: search(..., exclude_editorial=
    # True) must exclude the letters volume's editorial content too, not
    # just the journals' - proven against real corpus content, not a
    # synthetic record. "Concord Battle-Ground" is Sanborn's illustration
    # caption for a real letter (SRC-000592) - a standalone bracketed
    # aside stripped from the letter's own evidence text and extracted as
    # its own editorial record.
    evidence_root = os.environ[EVIDENCE_ROOT_ENV_VAR]
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    rebuild(evidence_root, repo_root)
    db_path = repo_root / ".memoria" / "index.db"

    with_editorial = search(db_path, '"Battle-Ground"')
    without_editorial = search(db_path, '"Battle-Ground"', exclude_editorial=True)

    assert any(
        r.source_type == "editorial" and r.anchor == "src-000592-p7"
        for r in with_editorial
    )
    assert not any(
        r.source_type == "editorial" and r.anchor == "src-000592-p7"
        for r in without_editorial
    )
