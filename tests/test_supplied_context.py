"""The supplied context (#61, ADR-0001): for each session that assembled a
section, the working context assembly produced and every read served
since - two halves kept apart, in countable domain units, claiming only
what Memoria supplied.
"""

import json
from dataclasses import asdict

import pytest

from memoria import index, ledger
from memoria.assembly import assemble
from memoria.manuscript import ManuscriptError, create_chapter, create_section
from memoria.records import Read
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.supplied_context import (
    AssembledEntry,
    Fallback,
    ServedSince,
    supplied_context,
)


def _repo(tmp_path, *, brief_text="About Bob."):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    directory = tmp_path / "subjects" / "people"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bob.md").write_text(
        entry_to_markdown(Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")),
        encoding="utf-8",
    )
    chapter = create_chapter(repository, "The first chapter.")
    section = create_section(repository, chapter.number, brief_text)
    return repository, section


def _seed_candidate(repository, *, candidate_id, subject_id, label):
    con = index.connect(repository)
    try:
        con.execute(
            "INSERT INTO candidates "
            "(candidate_id, subject_id, label, gloss, recurrence, above_threshold) "
            "VALUES (?, ?, ?, '', 1, 0)",
            (candidate_id, subject_id, label),
        )
        con.commit()
    finally:
        con.close()


def _serve_read(repository, session_id, ref, citation, text="Bob called on July 17."):
    """A read the tool surface served to ``session_id`` - ledgered the way
    the MCP server ledgers one, token figure and all (#29)."""
    ledger.append_read(repository, session_id, Read(ref=ref, citation=citation, text=text))


def _forbidden_figures(value) -> list[str]:
    text = json.dumps(asdict(value)).lower()
    return [word for word in ("token", "byte", "percent", "%", "capacity") if word in text]


# --- a section no session has assembled -------------------------------------


def test_a_section_no_session_has_assembled_has_no_account(tmp_path):
    repository, section = _repo(tmp_path)

    account = supplied_context(repository, section.brief.id)

    assert account.section_id == section.brief.id
    assert account.sessions == ()


def test_an_unknown_section_is_the_same_error_a_read_gives(tmp_path):
    repository, _ = _repo(tmp_path)

    with pytest.raises(ManuscriptError):
        supplied_context(repository, "SEC-9999")


# --- the working context: briefs, entries, and fallbacks named explicitly --


def test_the_account_reports_the_brief_loaded_and_the_entries_resolved(tmp_path):
    repository, section = _repo(tmp_path)
    assemble(repository, "SES-20260902-1000-aaaaaaaaaaaa", section.brief)

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert session.session_id == "SES-20260902-1000-aaaaaaaaaaaa"
    assert session.briefs == (section.brief.id,)
    assert session.entries == (
        AssembledEntry(entry_id="SUB-people/bob", matched_by=("bob", "Bob"), sources=()),
    )
    assert session.fallbacks == ()
    assert session.unconfirmed is False
    assert session.empty is False
    assert session.assembled_at
    assert session.served_since == ()


def test_a_scope_naming_something_with_no_entry_names_the_fallback(tmp_path):
    """Part 06 §8.4: the fallback is named explicitly - subject, candidate
    and the label the scope matched - not passed over in silence."""
    repository, section = _repo(tmp_path, brief_text="Bob's dealings with Carol.")
    _seed_candidate(repository, candidate_id="CAN-0001", subject_id="SUB-people", label="Carol")
    assemble(repository, "SES-20260902-1000-aaaaaaaaaaaa", section.brief)

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert [entry.entry_id for entry in session.entries] == ["SUB-people/bob"]
    assert session.fallbacks == (
        Fallback(subject_id="SUB-people", candidate_id="CAN-0001", label="Carol"),
    )


# --- reads served since assembly, kept apart from what assembly loaded -----


def test_a_session_that_reads_beyond_its_assembly_shows_both_halves_apart(tmp_path):
    """The acceptance test: a session assembles, then reads a paragraph the
    working context never loaded. The paragraph is in ``served_since`` and
    nowhere in the assembly half; the entry is in the assembly half and
    nowhere in ``served_since``."""
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    _serve_read(repository, session_id, "src-000184-p1", "SRC-000184 ¶1")

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert [entry.entry_id for entry in session.entries] == ["SUB-people/bob"]
    assert session.served_since == (
        ServedSince(tool="read", ref="src-000184-p1", served=("SRC-000184 ¶1",)),
    )
    assembled = {entry.entry_id for entry in session.entries} | {
        source for entry in session.entries for source in entry.sources
    }
    served = {ref for item in session.served_since for ref in item.served} | {
        item.ref for item in session.served_since
    }
    assert assembled.isdisjoint(served)


def test_a_read_served_before_assembly_is_not_a_read_served_since(tmp_path):
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    _serve_read(repository, session_id, "src-000184-p1", "SRC-000184 ¶1")
    assemble(repository, session_id, section.brief)
    _serve_read(repository, session_id, "src-000184-p2", "SRC-000184 ¶2")

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert [item.ref for item in session.served_since] == ["src-000184-p2"]


def test_a_search_served_since_is_reported_by_the_anchors_it_served(tmp_path):
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    ledger.append_search(
        repository,
        session_id,
        "July",
        None,
        [index.SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert session.served_since == (
        ServedSince(tool="search_text", ref=None, served=("src-000184-p1",)),
    )


def test_a_session_that_reassembles_keeps_the_reads_served_between(tmp_path):
    """The latest assembly is the working context; ``served_since`` runs
    from the first, so nothing served to the session on this section drops
    out of the account."""
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    _serve_read(repository, session_id, "src-000184-p1", "SRC-000184 ¶1")
    assemble(repository, session_id, section.brief)

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert [item.ref for item in session.served_since] == ["src-000184-p1"]
    assert [entry.entry_id for entry in session.entries] == ["SUB-people/bob"]


# --- one account per session that assembled this section, latest first ----


def test_a_session_that_assembled_another_section_only_is_absent(tmp_path):
    repository, section = _repo(tmp_path)
    other = create_section(repository, 1, "Roughly the middle of the book.")
    assemble(repository, "SES-20260902-1000-aaaaaaaaaaaa", other.brief)

    assert supplied_context(repository, section.brief.id).sessions == ()
    (session,) = supplied_context(repository, other.brief.id).sessions
    assert session.empty is True


def test_sessions_are_ordered_latest_assembly_first(tmp_path):
    repository, section = _repo(tmp_path)
    assemble(repository, "SES-20260901-1000-aaaaaaaaaaaa", section.brief)
    assemble(repository, "SES-20260902-1000-bbbbbbbbbbbb", section.brief)

    sessions = supplied_context(repository, section.brief.id).sessions

    assert [session.session_id for session in sessions] == [
        "SES-20260902-1000-bbbbbbbbbbbb",
        "SES-20260901-1000-aaaaaaaaaaaa",
    ]


# --- countable domain units only: the file boundary (ADR-0001) --------------


def test_no_token_byte_percentage_or_capacity_figure_reaches_the_account(tmp_path):
    """A ``read`` ledger line carries a token figure for the context
    manifest (#29). The account is built from the same file and never
    copies it - no field of the value holds one, whatever the ledger
    holds."""
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    _serve_read(repository, session_id, "src-000184-p1", "SRC-000184 ¶1", text="x" * 4000)

    line = ledger.event_path(repository, session_id).read_text(encoding="utf-8")
    assert '"tokens": 1000' in line, "the ledger does carry the figure the account must not"

    account = supplied_context(repository, section.brief.id)

    assert _forbidden_figures(account) == []


def test_the_account_tolerates_a_ledger_line_that_does_not_parse(tmp_path):
    repository, section = _repo(tmp_path)
    session_id = "SES-20260902-1000-aaaaaaaaaaaa"
    assemble(repository, session_id, section.brief)
    with ledger.event_path(repository, session_id).open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    _serve_read(repository, session_id, "src-000184-p1", "SRC-000184 ¶1")

    (session,) = supplied_context(repository, section.brief.id).sessions

    assert [item.ref for item in session.served_since] == ["src-000184-p1"]
