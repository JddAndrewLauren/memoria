"""Settlements and the claims they accrete into (#33, part 06 §8.7-§8.9).

A real git repository, like ``test_record_extractor.py``'s: a settlement is
an attributable author act, and what is under test is what lands on the
entry, in git, and what the audit then stops raising.
"""

import json
import subprocess
from pathlib import Path

import pytest

from memoria.audit import (
    DisagreementMember,
    Finding,
    finding_verdict,
    findings_in_scope,
    manuscript_paragraphs,
    record_audit_verdict,
)
from memoria.index import rebuild
from memoria.manuscript import create_chapter, create_section
from memoria.records import ReadError
from memoria.records import read as records_read
from memoria.repository import Repository
from memoria.sessions import derive_session
from memoria.settlements import (
    Claim,
    Settlement,
    SettlementError,
    claim_from_settlement,
    is_settled,
    next_claim_id,
    parse_settlement,
    read_claim,
    record_claim,
    render_settlement,
    settle,
    settlements_on,
)
from memoria.subjects import (
    Entry,
    entry_to_markdown,
    is_audit_visible,
    parse_statements,
    serve_entry,
    write_builtin_subjects,
)
from memoria.write import Actor

AUTHOR = Actor(name="Local Author", email="local-author@memoria.test")
MACHINE = Actor(name="Memoria", email="curator@memoria.local", human=False)
BOB = "SUB-people/bob"
SESSION_ID = "SES-20260912-1432"
TESTIMONY = "Bob was born in 1962 in Cleveland."


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path) -> Repository:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", AUTHOR.name)
    _git(tmp_path, "config", "user.email", AUTHOR.email)
    _git(
        tmp_path, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", "initial", "--allow-empty",
    )
    return Repository(root=tmp_path)


def _commit_entry(repository: Repository, entry_id: str, body: str) -> str:
    subject_slug, entry_slug = entry_id[len("SUB-"):].split("/")
    relative_path = f"subjects/{subject_slug}/{entry_slug}.md"
    path = repository.root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        entry_to_markdown(Entry(id=entry_id, match_terms=["Bob"], body=body)), encoding="utf-8"
    )
    _git(repository.root, "add", relative_path)
    _git(
        repository.root, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", f"add {entry_id}",
    )
    return relative_path


def _token(repository: Repository, entry_id: str = BOB) -> str:
    return serve_entry(repository, *entry_id.split("/"))[1]


def _entry(repository: Repository, entry_id: str = BOB) -> Entry:
    return serve_entry(repository, *entry_id.split("/"))[0]


def _session(repository: Repository, session_id: str = SESSION_ID) -> str:
    """Derive a real session record, so the settlement's provenance is a
    session ``read(ref)`` resolves."""
    entries = [
        {
            "uuid": "u1",
            "parentUuid": None,
            "type": "user",
            "timestamp": "2026-09-12T14:32:00+00:00",
            "message": {"role": "user", "content": "Bob's birth year is 1962; settle it."},
        }
    ]
    jsonl_path = repository.root / "session.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    derive_session(repository, session_id, jsonl_path)
    return session_id


# The disagreement set part 06 §8.10's own example carries: the passage,
# Bob's entry, and the source that puts him in his mid-thirties.
def _three_way(slot: str = "02/01#7") -> tuple[DisagreementMember, ...]:
    return (
        DisagreementMember("passage", slot),
        DisagreementMember("entry", BOB),
        DisagreementMember("source", "src-000184-p12"),
    )


def _settle(repository: Repository, side: str = "entry", **overrides):
    kwargs = dict(
        side=side,
        proposition="birth year 1962",
        reason="the author's own recollection outranks the letter's guess",
        session_id=SESSION_ID,
        token=_token(repository),
        actor=AUTHOR,
        today="2026-09-02",
    )
    kwargs.update(overrides)
    return settle(repository, _three_way(), **kwargs)


# --- AC 1: settled by an explicit author act - side, reason, date ------------


def test_settle_records_the_side_chosen_the_reason_and_the_date_on_the_entry(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _commit_entry(repository, BOB, TESTIMONY)

    record = _settle(repository, side="entry")

    text = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert TESTIMONY in text
    assert (
        "[settled] birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-09-02\n"
        "Reason: the author's own recollection outranks the letter's guess\n"
        "— SES-20260912-1432"
    ) in text
    assert record.settlement == Settlement(
        proposition="birth year 1962",
        chosen=("SUB-people/bob",),
        against=("SRC-000184 ¶12",),
        reason="the author's own recollection outranks the letter's guess",
        date="2026-09-02",
        session_id=SESSION_ID,
    )
    assert record.entry_id == BOB


@pytest.mark.parametrize(
    ("side", "chosen", "against"),
    [
        ("entry", ("SUB-people/bob",), ("SRC-000184 ¶12",)),
        ("source", ("SRC-000184 ¶12",), ("SUB-people/bob",)),
        ("passage", ("the passage",), ("SUB-people/bob", "SRC-000184 ¶12")),
    ],
)
def test_the_three_way_set_settles_in_any_of_three_directions(tmp_path, side, chosen, against):
    """Part 09 §18's row: passage + entry + source settles in three
    directions, and the settlement names what was chosen against what."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    record = _settle(repository, side=side)

    assert record.settlement.chosen == chosen
    assert record.settlement.against == against
    [settlement] = settlements_on(_entry(repository))
    assert settlement == record.settlement


def test_a_settlement_is_committed_as_the_authors_own_act(tmp_path):
    """Click-authorized: the commit is the author's, carrying a change id
    (ADR-0008), never the Curator's."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    _settle(repository)

    assert _git(tmp_path, "status", "--porcelain").stdout == ""
    log = _git(tmp_path, "log", "-1", "--format=%an <%ae>%n%B").stdout
    assert log.startswith(f"{AUTHOR.name} <{AUTHOR.email}>")
    assert "change-id: CHG-" in log


def test_a_machine_actor_cannot_settle(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _commit_entry(repository, BOB, TESTIMONY)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")

    with pytest.raises(SettlementError, match="author act"):
        _settle(repository, actor=MACHINE)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before


def test_an_unattributed_actor_cannot_settle(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    with pytest.raises(SettlementError, match="attributed"):
        _settle(repository, actor=Actor(name="", email=""))


@pytest.mark.parametrize("field", ["proposition", "reason"])
def test_the_proposition_and_the_reason_are_required(tmp_path, field):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    with pytest.raises(SettlementError, match=field):
        _settle(repository, **{field: "  "})


def test_settle_is_rejected_when_the_entry_moved_underneath(tmp_path):
    """ADR-0003: the token is the caller's, from the read the author acted
    on; a committed edit in between is refused as stale."""
    repository = _repo(tmp_path)
    relative_path = _commit_entry(repository, BOB, TESTIMONY)
    token = _token(repository)
    _commit_entry(repository, BOB, TESTIMONY + " Heavyset.")

    with pytest.raises(SettlementError, match="stale"):
        _settle(repository, token=token)

    assert "[settled]" not in (tmp_path / relative_path).read_text(encoding="utf-8")


def test_a_set_with_no_entry_has_nowhere_to_settle(tmp_path):
    """Part 06 §8.7: a settlement is stored on the entry. Passage + source
    has no entry - its resolutions are a rewrite or an exclusion (#21)."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    members = (
        DisagreementMember("passage", "02/01#7"),
        DisagreementMember("source", "src-000184-p12"),
    )

    with pytest.raises(SettlementError, match="no entry"):
        settle(
            repository, members, side="source", proposition="p", reason="r",
            session_id=SESSION_ID, token=_token(repository), actor=AUTHOR,
        )


def test_settling_toward_the_entry_needs_something_besides_the_passage_to_choose_over(tmp_path):
    """Passage + entry admits "update the entry" (toward the passage) as its
    settlement; the other way round is a plain rewrite (part 09 §18), and a
    settlement recording it would silence every later passage that
    disagrees with the entry - a manuscript pointer by another route."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    members = (
        DisagreementMember("passage", "02/01#7"),
        DisagreementMember("entry", BOB),
    )

    with pytest.raises(SettlementError, match="rewrite the passage"):
        settle(
            repository, members, side="entry", proposition="p", reason="r",
            session_id=SESSION_ID, token=_token(repository), actor=AUTHOR,
        )

    record = settle(
        repository, members, side="passage", proposition="Bob was born in 1965",
        reason="the draft follows the birth certificate", session_id=SESSION_ID,
        token=_token(repository), actor=AUTHOR, today="2026-09-02",
    )
    assert record.settlement.chosen == ("the passage",)
    assert record.settlement.against == (BOB,)


def test_a_side_the_set_does_not_carry_is_refused(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    with pytest.raises(SettlementError, match="decision"):
        _settle(repository, side="decision")


def test_a_brief_is_never_a_settlement_target(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    members = (
        DisagreementMember("passage", "02/01#7"),
        DisagreementMember("entry", BOB),
        DisagreementMember("brief", "SEC-0001"),
    )

    with pytest.raises(SettlementError, match="brief"):
        settle(
            repository, members, side="entry", proposition="p", reason="r",
            session_id=SESSION_ID, token=_token(repository), actor=AUTHOR,
        )


# --- AC 2: inside the audit-visible body ------------------------------------


def test_a_settlement_is_inside_the_audit_visible_body(tmp_path):
    from memoria.audit import audit_visible_body

    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY + "\n\n[open] Maybe he was born in 1963.")

    _settle(repository)

    entry = _entry(repository)
    statements = parse_statements(entry.body)
    settled = [s for s in statements if s.badge == "settled"]
    assert len(settled) == 1
    assert is_audit_visible(settled[0])
    visible = audit_visible_body(entry)
    assert "[settled] birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12" in visible
    assert "Maybe he was born in 1963" not in visible


# --- AC 3: provenance is the session; nothing points at a paragraph ---------


def test_the_settlement_records_its_session_and_never_the_paragraph(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _commit_entry(repository, BOB, TESTIMONY)
    slot = "02/01#7"

    record = settle(
        repository, _three_way(slot), side="passage", proposition="birth year 1965",
        reason="the draft follows the certificate", session_id=SESSION_ID,
        token=_token(repository), actor=AUTHOR, today="2026-09-02",
    )

    text = (tmp_path / relative_path).read_text(encoding="utf-8")
    assert record.settlement.session_id == SESSION_ID
    assert SESSION_ID in text
    assert slot not in text
    assert "chapters" not in text


def test_the_session_is_recorded_whole_never_as_a_turn(tmp_path):
    """The click is not a turn: the provenance of the act is the session it
    happened in (part 06 §8.7), and a turn citation would point at a
    transcript that is not derived until the session ends."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    with pytest.raises(SettlementError, match="session"):
        _settle(repository, session_id=f"{SESSION_ID}#T001")
    with pytest.raises(SettlementError, match="session"):
        _settle(repository, session_id="SRC-000184")


def test_a_settlement_resolves_to_a_session_read_can_serve(tmp_path):
    """AC 6, the settlements half: traceable to their session."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    _session(repository)

    record = _settle(repository)

    served = records_read(repository, record.settlement.session_id)
    assert "settle it" in served.text
    entry_read = records_read(repository, BOB)
    assert f"— {SESSION_ID}" in entry_read.text


# --- the grammar round-trips ------------------------------------------------


def test_render_and_parse_are_inverses():
    settlement = Settlement(
        proposition="birth year 1962 — not 1965",
        chosen=("the passage",),
        against=("SUB-people/bob", "SRC-000184 ¶12", "DEC-0001"),
        reason="Reason: the certificate — chosen over memory",
        date="2026-09-02",
        session_id=SESSION_ID,
    )
    [statement] = parse_statements(render_settlement(settlement))
    assert statement.badge == "settled"
    assert parse_settlement(statement) == settlement


@pytest.mark.parametrize(
    "text",
    [
        "birth year 1962\nReason: r\n— SES-20260912-1432",
        "birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-09-02\n— SES-20260912-1432",
        "birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-09-02\nReason: r",
        "birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-09-02\nReason: r\n— SRC-000184",
        "birth year 1962 — SUB-people/bob, chosen over SRC-000184 ¶12, 2026-9-2\nReason: r\n— SES-20260912-1432",
    ],
)
def test_a_malformed_settlement_is_a_named_refusal(text):
    from memoria.subjects import Statement

    with pytest.raises(SettlementError):
        parse_settlement(Statement(badge="settled", text=text))


# --- AC 4: a settled conflict is not re-raised --------------------------------


def _manuscript(repository: Repository, draft: str):
    write_builtin_subjects(repository)
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    _git(repository.root, "add", "-A")
    _git(
        repository.root, "-c", "user.name=Setup", "-c", "user.email=setup@memoria.test",
        "commit", "-q", "-m", "manuscript",
    )


def _raise(repository: Repository, members, statement="Bob is fifty-nine here.") -> Finding:
    """What an audit pass would record for this paragraph against Bob."""
    paragraph = manuscript_paragraphs(repository)[0]
    finding = Finding(
        disagreement_set=members,
        statement=statement,
        confidence="high",
        subject_id="SUB-people",
    )
    record_audit_verdict(repository, paragraph, BOB, finding_verdict(finding))
    return finding


def test_a_downstream_pass_stays_silent_on_a_settled_conflict(tmp_path):
    """The acceptance test. An audit raises the three-way finding; the
    author settles it; the entry changed, so the paragraph goes not-current
    and the next audit reads it again - and if that pass raises the same
    disagreement, it is not served. A different disagreement still is."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    _manuscript(repository, "Bob was fifty-nine that summer.")
    paragraph = manuscript_paragraphs(repository)[0]
    members = _three_way(paragraph.slot)

    raised = _raise(repository, members)
    assert findings_in_scope(repository) == (raised,)

    _settle(repository, side="entry")
    # The entry moved, so nothing is current until the audit runs again.
    assert findings_in_scope(repository) == ()

    # The downstream pass re-raises the very same disagreement: silent.
    re_raised = _raise(repository, members)
    assert findings_in_scope(repository) == ()
    assert is_settled(_entry(repository), re_raised.disagreement_set)

    # A disagreement with a different source is not the settled one.
    other = _raise(
        repository,
        (
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("entry", BOB),
            DisagreementMember("source", "src-000200-p3"),
        ),
    )
    assert findings_in_scope(repository) == (other,)


def test_silence_is_by_the_disagreements_identity_not_the_passage(tmp_path):
    """The set is the identity (part 06 §8.10), and the passage has none:
    the same entry-versus-source disagreement surfacing from another
    paragraph is the same settled disagreement."""
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)
    _settle(repository, side="source")

    entry = _entry(repository)
    assert is_settled(entry, _three_way("02/01#7"))
    assert is_settled(entry, _three_way("05/03#1"))
    # And the set that carries only the passage and the entry is never
    # mechanically silenced - the entry now says what it says, and the
    # audit reads that.
    assert not is_settled(
        entry, (DisagreementMember("passage", "02/01#7"), DisagreementMember("entry", BOB))
    )


# --- AC 5: CLM- records, from settlements and directly ------------------------


def test_a_settlement_accretes_into_a_claim(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    record = _settle(repository, side="entry")

    assert record.claim_id == "CLM-0001"
    text = read_claim(repository, "CLM-0001")
    assert text == (
        "# CLM-0001\n\n"
        "## Claim\n\nbirth year 1962\n\n"
        "## Status\n\nauthor\n\n"
        "## Confidence\n\nhigh\n\n"
        "## Supporting evidence\n\n- SUB-people/bob\n\n"
        "## Contradicting evidence\n\n- SRC-000184 ¶12\n\n"
        "## Reasoning\n\nthe author's own recollection outranks the letter's guess\n\n"
        "## Provenance\n\n- settlement on SUB-people/bob, 2026-09-02\n- SES-20260912-1432\n"
    )
    assert record.claim == claim_from_settlement(record.entry_id, record.settlement)


def test_a_claim_born_of_settling_toward_the_passage_cites_no_paragraph(tmp_path):
    repository = _repo(tmp_path)
    _commit_entry(repository, BOB, TESTIMONY)

    record = _settle(repository, side="passage", proposition="birth year 1965")

    assert record.claim.supporting == ()
    assert record.claim.contradicting == ("SUB-people/bob", "SRC-000184 ¶12")
    assert "02/01#7" not in read_claim(repository, record.claim_id)


def test_a_claim_is_creatable_directly_with_every_field(tmp_path):
    """Part 06 §8.9: claims are a superset of settlements - the author may
    assert one outright, with no conflict behind it."""
    repository = _repo(tmp_path)
    claim = Claim(
        proposition="Bob probably knew about the acquisition before July 17.",
        status="inferred",
        confidence="moderate",
        supporting=("SRC-000184 ¶17",),
        contradicting=("SRC-001102 ¶8",),
        reasoning="The July 15 call only makes sense if he already knew.",
        session_id=SESSION_ID,
    )

    record = record_claim(repository, claim, AUTHOR, today="2026-09-02")

    assert record.claim_id == "CLM-0001"
    assert record.path == "claims/CLM-0001.md"
    text = (tmp_path / record.path).read_text(encoding="utf-8")
    assert "## Status\n\ninferred\n" in text
    assert "## Confidence\n\nmoderate\n" in text
    assert "- SRC-000184 ¶17" in text
    assert "- SRC-001102 ¶8" in text
    assert "## Reasoning\n\nThe July 15 call only makes sense if he already knew.\n" in text
    assert "## Provenance\n\n- asserted directly, 2026-09-02\n- SES-20260912-1432\n" in text
    assert _git(tmp_path, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("status", "settled", "status"),
        ("confidence", "certain", "confidence"),
        ("proposition", " ", "proposition"),
        ("supporting", ("chapters/02/draft.md",), "manuscript"),
        ("supporting", ("CLM-0001",), "derived"),
        ("contradicting", ("SEC-0001",), "manuscript"),
    ],
)
def test_a_claim_refuses_a_bad_status_confidence_proposition_or_evidence(
    tmp_path, field, value, match
):
    repository = _repo(tmp_path)
    claim = Claim(proposition="p", status="inferred", confidence="low")
    claim = Claim(**{**claim.__dict__, field: value})

    with pytest.raises(SettlementError, match=match):
        record_claim(repository, claim, AUTHOR)

    assert not (tmp_path / "claims").exists()


def test_claim_ids_are_one_more_than_the_highest_on_disk(tmp_path):
    repository = _repo(tmp_path)
    assert next_claim_id(repository) == "CLM-0001"
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "CLM-0007.md").write_text("# CLM-0007\n", encoding="utf-8")
    (tmp_path / "claims" / "notes.md").write_text("not a claim\n", encoding="utf-8")

    assert next_claim_id(repository) == "CLM-0008"

    record = record_claim(repository, Claim(proposition="p", status="author", confidence="high"), AUTHOR)
    assert record.claim_id == "CLM-0008"


# --- AC 6: read(ref) resolves CLM- --------------------------------------------


def test_read_ref_resolves_a_claim_to_its_file_verbatim(tmp_path):
    repository = _repo(tmp_path)
    record = record_claim(
        repository, Claim(proposition="p", status="source", confidence="low"), AUTHOR
    )

    served = records_read(repository, "CLM-0001")

    assert served.citation == "CLM-0001"
    assert served.text == (tmp_path / record.path).read_text(encoding="utf-8")
    assert records_read(repository, "clm-0001").text == served.text


def test_reading_a_claim_that_does_not_exist_names_it(tmp_path):
    repository = _repo(tmp_path)

    with pytest.raises(ReadError, match="CLM-0041"):
        records_read(repository, "CLM-0041")
    with pytest.raises(ReadError, match="malformed claim reference"):
        records_read(repository, "CLM-41")


def test_a_claim_is_not_provenance_for_an_entry_statement(tmp_path):
    """A claim is a derived artifact (part 15 §23); now that ``CLM-``
    parses, ``check_provenance`` must still refuse it."""
    from memoria.record_extractor import RecordExtractorError, check_provenance

    with pytest.raises(RecordExtractorError, match="original material"):
        check_provenance("CLM-0041")


# --- AC 7: settlements survive rebuild as attributable author acts -----------


def test_a_settlement_survives_rebuild_as_the_authors_own_commit(tmp_path):
    repository = _repo(tmp_path)
    relative_path = _commit_entry(repository, BOB, TESTIMONY)

    record = _settle(repository)
    before = (tmp_path / relative_path).read_text(encoding="utf-8")

    rebuild(repository)

    assert (tmp_path / relative_path).read_text(encoding="utf-8") == before
    assert settlements_on(_entry(repository)) == [record.settlement]
    assert read_claim(repository, record.claim_id).startswith("# CLM-0001")
    # Attributable: the commit that carries the settlement is the author's,
    # under a change id that read(CHG-...) resolves to this very file.
    log = _git(
        tmp_path, "log", "--format=%an%x1f%B", "--", relative_path
    ).stdout
    author, body = log.split("\x1f", 1)
    assert author == AUTHOR.name
    change_id = next(
        line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("change-id: ")
    )
    projection = records_read(repository, change_id).text
    assert relative_path in projection
    assert "[settled] birth year 1962" in projection


# --- the module never reaches a model, and writes only through the write path --


def test_settlements_writes_only_through_the_write_path():
    import ast

    source = (Path(__file__).resolve().parent.parent / "src" / "memoria" / "settlements.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "write_text" not in calls
    assert "write_bytes" not in calls
