"""Brief drift as a set difference (#41): `memoria.drift.compute_drift`.

Builds directly on `memoria.scope.resolve_scope` (#36) for the declared side
and `memoria.index.compute_appearances`/`appeared_entry_ids` (#19) for the
covered side - these tests exercise the set difference and its two refusal-
and-recompute properties, not the resolver or the appearances engine
themselves (those are `test_scope.py` and `test_index.py`'s job).
"""

from memoria.drift import DriftReport, compute_drift
from memoria.index import build_index, compute_appearances
from memoria.manuscript import Brief, create_section
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown


def _record(record_id, paragraphs, source_type="book"):
    return NormalizedRecord(
        id=record_id,
        source_type=source_type,
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="unresolved",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=paragraphs,
    )


def _write_entry(tmp_path, entry):
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry))


def _repo_with_prose(tmp_path, paragraphs) -> Repository:
    """A repository with one ``book`` record indexed and its appearances
    already computed - the persisted state `compute_drift` reads from."""
    repository = Repository(root=tmp_path)
    book = _record("SRC-000001", paragraphs)
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])
    compute_appearances(repository)
    return repository


def _brief(text: str, *, unconfirmed: bool = False) -> Brief:
    return Brief(id="SEC-0001", text=text, unconfirmed=unconfirmed)


# --- the set difference itself (#41's first acceptance criterion) ----------


def test_no_drift_when_the_declared_scope_matches_what_the_prose_covers(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    report = compute_drift(repository, _brief("Covers Bob."))

    assert report.skipped is False
    assert report.covered_but_undeclared == ()
    assert report.declared_but_uncovered == ()


def test_compute_drift_returns_a_drift_report(tmp_path):
    repository = _repo_with_prose(tmp_path, ["Nothing relevant."])
    assert isinstance(compute_drift(repository, _brief("Anything.")), DriftReport)


# --- both directions (#41's third acceptance criterion) --------------------


def test_covered_but_undeclared_is_prose_touching_an_entry_the_brief_never_names(tmp_path):
    """Part 11 §32's own example: prose appearing under an entry a section's
    brief never names is drift."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    report = compute_drift(repository, _brief("Roughly the middle of the book."))

    assert report.covered_but_undeclared == ("SUB-people/bob",)
    assert report.declared_but_uncovered == ()


def test_declared_but_uncovered_is_a_brief_naming_an_entry_the_prose_never_touches(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Nothing about him here."])

    report = compute_drift(repository, _brief("Covers Bob."))

    assert report.declared_but_uncovered == ("SUB-people/bob",)
    assert report.covered_but_undeclared == ()


def test_both_directions_are_reported_together_rather_than_a_single_boolean(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    _write_entry(tmp_path, Entry(id="SUB-events/acquisition"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    report = compute_drift(repository, _brief("Covers the acquisition."))

    assert report.covered_but_undeclared == ("SUB-people/bob",)
    assert report.declared_but_uncovered == ("SUB-events/acquisition",)


def test_themes_and_arcs_are_reported_unmatchable_not_uncovered(tmp_path):
    """`compute_appearances` never indexes entries under
    `CO_OCCURRENCE_SUBJECTS` (#19 names them as skipped), so a brief naming a
    theme can never be "covered" - reporting it as uncovered would be a
    permanent false finding for a brief that describes the prose exactly."""
    _write_entry(tmp_path, Entry(id="SUB-themes/solitude", match_terms=["solitude"]))
    _write_entry(tmp_path, Entry(id="SUB-arcs/retreat", match_terms=["retreat"]))
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob's retreat into solitude."])

    report = compute_drift(repository, _brief("Covers Bob's retreat into solitude."))

    assert report.unmatchable == ("SUB-arcs/retreat", "SUB-themes/solitude")
    assert report.declared_but_uncovered == ()
    assert report.covered_but_undeclared == ()


def test_unmatchable_is_empty_when_the_brief_names_no_theme_or_arc(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-themes/solitude", match_terms=["solitude"]))
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    report = compute_drift(repository, _brief("Covers Bob."))

    assert report.unmatchable == ()
    assert report.declared_but_uncovered == ()


# --- never against an unconfirmed brief (#41's second acceptance criterion) -


def test_drift_is_skipped_against_an_unconfirmed_brief_with_a_stated_reason(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    report = compute_drift(
        repository, _brief("Roughly the middle of the book.", unconfirmed=True)
    )

    assert report.skipped is True
    assert report.reason and "unconfirmed" in report.reason
    assert report.covered_but_undeclared == ()
    assert report.declared_but_uncovered == ()
    assert report.unmatchable == ()


def test_an_unconfirmed_brief_would_otherwise_report_zero_drift_by_construction(tmp_path):
    """The circularity #41 and part 11 §32 name: a brief drafted by
    summarizing the very prose it would constrain agrees with that prose -
    were drift not skipped, this exact case would report no drift at all,
    precisely when the brief is least trustworthy."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])
    summarized_from_the_prose = _brief("Bob argued with Carol.", unconfirmed=True)

    report = compute_drift(repository, summarized_from_the_prose)

    assert report.skipped is True


# --- recomputed, not cached (#41's fifth acceptance criterion) -------------


def test_drift_recomputes_when_the_brief_text_changes(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])

    loose = compute_drift(repository, _brief("Roughly the middle of the book."))
    tightened = compute_drift(repository, _brief("Covers Bob."))

    assert loose.covered_but_undeclared == ("SUB-people/bob",)
    assert tightened.covered_but_undeclared == ()


def test_drift_recomputes_when_the_prose_changes(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Nothing about him here."])
    brief = _brief("Covers Bob.")

    before = compute_drift(repository, brief)
    assert before.declared_but_uncovered == ("SUB-people/bob",)

    book = _record("SRC-000001", ["Bob argued with Carol."])
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])
    compute_appearances(repository)

    after = compute_drift(repository, brief)
    assert after.declared_but_uncovered == ()


def test_drift_recomputes_when_the_resolved_entries_change(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])
    brief = _brief("Robert's role in the conflict.")

    before = compute_drift(repository, brief)
    assert before.covered_but_undeclared == ("SUB-people/bob",)

    _write_entry(tmp_path, Entry(id="SUB-people/bob", match_terms=["Robert"]))
    after = compute_drift(repository, brief)

    assert after.covered_but_undeclared == ()


def test_drift_reads_the_persisted_appearances_table_without_recomputing_it(tmp_path):
    """AC 4: model-free where the underlying appearances are, memoized where
    they are not - `compute_drift` never itself re-derives what the prose
    touches. Rewriting the prose without a fresh `compute_appearances` pass
    leaves drift reporting against the stale, persisted table, the same way
    `list_appearances` would."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Nothing about him here."])
    brief = _brief("Covers Bob.")
    assert compute_drift(repository, brief).declared_but_uncovered == ("SUB-people/bob",)

    book = _record("SRC-000001", ["Bob argued with Carol."])
    write_normalized_records([book], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [book])
    # No `compute_appearances` call here.

    assert compute_drift(repository, brief).declared_but_uncovered == ("SUB-people/bob",)


# --- never writes to the brief (#41's sixth acceptance criterion) ----------


def test_drift_never_writes_to_the_brief(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo_with_prose(tmp_path, ["Bob argued with Carol."])
    section = create_section(repository, 1, "Roughly the middle of the book.")
    before = section.path.read_bytes()

    compute_drift(repository, section.brief)

    assert section.path.read_bytes() == before
