"""Assembly (#38): a section's declared scope resolved through the one
scope resolver (#36) into a working context, reporting what it resolved and
recording that resolution on the session's own context manifest (#29) - never
back onto the section.
"""

import json

from memoria import index, ledger
from memoria.assembly import ResolvedEntry, ScopeFallback, WorkingContext, assemble
from memoria.context_manifest import build_context_manifest
from memoria.manuscript import Brief
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown
from memoria.write import DURABLE_PATHS


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


def _write_entry(tmp_path, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _brief(text: str, *, unconfirmed: bool = False) -> Brief:
    return Brief(id="SEC-0001", text=text, unconfirmed=unconfirmed)


def _seed_candidate(
    repository: Repository,
    *,
    candidate_id: str,
    subject_id: str,
    label: str,
    recurrence: int = 1,
    above_threshold: bool = False,
) -> None:
    con = index.connect(repository)
    try:
        con.execute(
            "INSERT INTO candidates "
            "(candidate_id, subject_id, label, gloss, recurrence, above_threshold) "
            "VALUES (?, ?, ?, '', ?, ?)",
            (candidate_id, subject_id, label, recurrence, int(above_threshold)),
        )
        con.commit()
    finally:
        con.close()


# --- resolving the declared scope through the one scope resolver (#36) ------


def test_assemble_resolves_the_declared_scope_through_the_scope_resolver(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)

    context = assemble(
        repository, "SES-test", _brief("Covers my interactions with Bob.")
    )

    assert isinstance(context, WorkingContext)
    (resolved,) = context.resolved_entries
    assert resolved.entry_id == "SUB-people/bob"
    assert resolved.matched_by == ("bob",)
    assert context.empty is False


def test_assemble_over_a_scope_naming_nothing_resolves_to_no_entries(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    context = assemble(repository, "SES-test", _brief("Roughly the middle of the book."))

    assert context.resolved_entries == ()
    assert context.empty is True


# --- loaded content is the audit-visible body only (CONTEXT.md) -------------


def test_loaded_content_excludes_open_lines_and_is_the_audit_visible_body(tmp_path):
    _write_entry(
        tmp_path,
        Entry(
            id="SUB-people/bob",
            body="Bob is tall.\n\n[source] Bob was born in 1980.\n\n[open] Maybe he isn't.",
        ),
    )
    repository = _repo(tmp_path)

    context = assemble(repository, "SES-test", _brief("About Bob."))

    (resolved,) = context.resolved_entries
    assert "Bob is tall." in resolved.audit_visible_body
    assert "[source] Bob was born in 1980." in resolved.audit_visible_body
    assert "Maybe he isn't" not in resolved.audit_visible_body


# --- the report: entries, sources, and what it could not resolve (§33.1) ----


def test_the_report_names_which_sources_back_a_resolved_entry(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)
    con = index.connect(repository)
    try:
        con.execute(
            "INSERT INTO paragraphs (anchor, src_id, source_type) "
            "VALUES ('src-000001-p1', 'SRC-000001', 'journal')"
        )
        con.execute(
            "INSERT INTO placements (anchor, entry_id, surface_form, licensed_by) "
            "VALUES ('src-000001-p1', 'SUB-people/bob', 'Bob', 'bob')"
        )
        con.commit()
    finally:
        con.close()

    context = assemble(repository, "SES-test", _brief("About Bob."))

    (resolved,) = context.resolved_entries
    assert [source.anchor for source in resolved.gathered_set] == ["src-000001-p1"]


def test_a_declared_scope_naming_no_entry_falls_back_to_an_unpromoted_candidate(tmp_path):
    """Part 06 §8.4 / part 11 §32: "assembly never dead-ends ... falls back
    to the candidate, and says that it did." Nothing about the candidate's
    content loads - only its identity."""
    repository = _repo(tmp_path)
    _seed_candidate(
        repository, candidate_id="CAN-0001", subject_id="SUB-people", label="Carol"
    )

    context = assemble(repository, "SES-test", _brief("Covers my dealings with Carol."))

    assert context.resolved_entries == ()
    (fallback,) = context.fallbacks
    assert fallback == ScopeFallback(
        subject_id="SUB-people", candidate_id="CAN-0001", label="Carol"
    )


def test_a_candidate_whose_label_the_brief_does_not_name_is_not_a_fallback(tmp_path):
    repository = _repo(tmp_path)
    _seed_candidate(
        repository, candidate_id="CAN-0001", subject_id="SUB-people", label="Carol"
    )

    context = assemble(repository, "SES-test", _brief("About Bob only."))

    assert context.fallbacks == ()


def test_a_promoted_entry_with_its_stale_candidate_row_is_not_also_a_fallback(tmp_path):
    """``extraction.promote_candidate`` leaves the promoted candidate's row in
    place until the next extraction rebuild. The phrase resolves to its entry;
    reporting it as a fallback too would claim a gap that does not exist."""
    _write_entry(tmp_path, Entry(id="SUB-people/carol", body="Carol is a neighbour."))
    repository = _repo(tmp_path)
    _seed_candidate(
        repository, candidate_id="CAN-0001", subject_id="SUB-people", label="Carol"
    )

    context = assemble(repository, "SES-test", _brief("Covers my dealings with Carol."))

    assert [resolved.entry_id for resolved in context.resolved_entries] == [
        "SUB-people/carol"
    ]
    assert context.fallbacks == ()


def test_a_candidate_the_resolved_set_does_not_account_for_is_still_a_fallback(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)
    _seed_candidate(
        repository, candidate_id="CAN-0001", subject_id="SUB-people", label="Carol"
    )

    context = assemble(repository, "SES-test", _brief("Bob's dealings with Carol."))

    assert [resolved.entry_id for resolved in context.resolved_entries] == [
        "SUB-people/bob"
    ]
    (fallback,) = context.fallbacks
    assert fallback.candidate_id == "CAN-0001"


# --- countable domain units only - no token figure (ADR-0001) ---------------


def test_the_ledgered_resolution_carries_no_token_figure(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)

    assemble(repository, "SES-test", _brief("About Bob."))

    path = ledger.event_path(repository, "SES-test")
    (line,) = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(line)
    assert "token" not in json.dumps(event).lower()


def test_the_ledgered_resolution_names_the_section_it_resolved(tmp_path):
    """The one place the link from a section to the sessions that assembled
    it exists (#61): nothing is written back onto the section."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)

    assemble(repository, "SES-test", _brief("About Bob."))

    path = ledger.event_path(repository, "SES-test")
    (line,) = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["section_id"] == "SEC-0001"


# --- recorded on the session's context manifest, never on the section -------


def test_the_resolution_is_recorded_on_the_sessions_context_manifest(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)

    assemble(repository, "SES-test", _brief("About Bob."))

    manifest = build_context_manifest(repository, "SES-test")
    (resolution,) = manifest["scope_resolutions"]
    assert resolution["entries"] == [
        {"entry_id": "SUB-people/bob", "matched_by": ["bob"], "sources": []}
    ]
    assert resolution["fallbacks"] == []
    assert resolution["unconfirmed"] is False
    assert resolution["empty"] is False


def test_an_untouched_session_has_no_scope_resolutions(tmp_path):
    manifest = build_context_manifest(_repo(tmp_path), "SES-test")
    assert manifest["scope_resolutions"] == []


# --- an unconfirmed brief still resolves, and says so (part 11 §32) ---------


def test_assembly_over_an_unconfirmed_brief_works_and_says_so(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    context = assemble(
        repository, "SES-test", _brief("About Bob.", unconfirmed=True)
    )

    assert context.unconfirmed is True
    assert context.resolved_entries != ()


# --- assembly writes no durable state ----------------------------------------


def test_assembly_writes_no_durable_state(tmp_path):
    """None of `memoria.write`'s durable state classes move - the only trace
    of a call is the session's own ledger line (Interaction record, not a
    durable state class per `memoria.write`'s own docstring)."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob", body="Bob is tall."))
    repository = _repo(tmp_path)

    def _snapshot() -> dict[str, str]:
        snapshot = {}
        for prefix in DURABLE_PATHS:
            path = tmp_path / prefix
            if path.is_file():
                snapshot[prefix] = path.read_text(encoding="utf-8")
            elif path.is_dir():
                for file in sorted(path.rglob("*")):
                    if file.is_file():
                        snapshot[str(file.relative_to(tmp_path))] = file.read_text(
                            encoding="utf-8"
                        )
        return snapshot

    before = _snapshot()
    assemble(repository, "SES-test", _brief("About Bob."))
    after = _snapshot()

    assert before == after


# --- reproducible per session, at the same repository revision (#38) --------


def test_the_same_session_reassembles_identically_at_the_same_revision(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", match_terms=["Robert"]))
    repository = _repo(tmp_path)
    brief = _brief("Bob's role, called Robert by his mother.")

    first = assemble(repository, "SES-same", brief)
    second = assemble(repository, "SES-same", brief)

    assert first == second
    assert isinstance(first.resolved_entries[0], ResolvedEntry)
