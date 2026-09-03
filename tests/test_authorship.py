"""AI manuscript writing under authorization (#42, part 10 §19-§21).

Every scenario runs against a real git repository, because what is under
test is what git ends up recording: that an unauthorized write leaves no
commit, that an authorized one carries its authorization, and that a
scoped write changes exactly the bytes it was authorized to.
"""

import subprocess
from pathlib import Path

import pytest

from memoria import authorship, manuscript
from memoria.audit import manuscript_paragraphs
from memoria.authorship import (
    Applied,
    Authorization,
    AuthorshipError,
    BriefTarget,
    ParagraphTarget,
    Refused,
    SectionTarget,
    apply_rewrite,
    apply_rewrites,
    paragraph_spans,
    propose_rewrite,
    read_paragraph,
    write_brief_from_conversation,
    write_draft,
)
from memoria.records import ReadError, read
from memoria.repository import Repository
from memoria.write import checkpoint

SESSION = "SES-20260912-1432"
DRAFT = "Bob went to town.\n\nBob came home late.\n\nCarol wrote a letter.\n"


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(tmp_path, draft: str = DRAFT) -> tuple[Repository, manuscript.SectionEntry]:
    """A real git repository holding a book, one chapter and one section
    with `draft` as its prose, all committed as the author's own
    checkpoint - so every test starts from a clean, human-authored
    history."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    repository = Repository(root=tmp_path)
    manuscript.create_book(repository, "The book.")
    chapter = manuscript.create_chapter(repository, "Chapter one.")
    section = manuscript.create_section(repository, chapter.number, "Section one.")
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    checkpoint(repository)
    return repository, section


def _draft_text(section) -> str:
    return (section.dir / "draft.md").read_text(encoding="utf-8")


def _commits(tmp_path) -> list[str]:
    return _git(tmp_path, "log", "--format=%s").splitlines()


def _last_message(tmp_path) -> str:
    return _git(tmp_path, "log", "-1", "--format=%B")


def _authorize(*targets) -> Authorization:
    return Authorization(SESSION, 8, frozenset(targets))


# --- an authorization is identifiable or it does not exist -------------------


def test_an_authorization_is_a_citable_session_turn():
    authorization = _authorize(ParagraphTarget("SEC-0001", 2))

    assert authorization.citation == "SES-20260912-1432#T008"


@pytest.mark.parametrize("session_id", ["", "session-1", "CHG-20260912-001", "SES-2026"])
def test_an_uncitable_session_id_cannot_be_an_authorization(session_id):
    with pytest.raises(AuthorshipError):
        Authorization(session_id, 1, frozenset({ParagraphTarget("SEC-0001", 1)}))


def test_a_turn_below_one_cannot_be_an_authorization():
    with pytest.raises(AuthorshipError, match="1-based"):
        Authorization(SESSION, 0, frozenset({ParagraphTarget("SEC-0001", 1)}))


def test_an_authorization_covers_at_least_one_target():
    with pytest.raises(AuthorshipError, match="at least one"):
        Authorization(SESSION, 1, frozenset())


# --- Memoria proposes; it does not apply (§19.2, §43.12) -------------------


def test_a_proposal_writes_nothing_and_commits_nothing(tmp_path):
    repository, section = _repo(tmp_path)
    before = _draft_text(section)

    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    assert proposal.current_text == "Bob came home late."
    assert proposal.proposed_text == "Bob came home at dusk."
    assert _draft_text(section) == before
    assert _commits(tmp_path) == ["checkpoint"]


def test_applying_a_proposal_without_an_authorization_is_refused(tmp_path):
    repository, section = _repo(tmp_path)
    before = _draft_text(section)
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    result = apply_rewrite(repository, proposal)

    assert isinstance(result, Refused)
    assert "no authorization" in result.reason
    assert _draft_text(section) == before
    assert _commits(tmp_path) == ["checkpoint"]


def test_an_authorization_for_another_paragraph_does_not_cover_this_one(tmp_path):
    repository, section = _repo(tmp_path)
    before = _draft_text(section)
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    result = apply_rewrite(
        repository, proposal, _authorize(ParagraphTarget(section.brief.id, 1))
    )

    assert isinstance(result, Refused)
    assert "not covered" in result.reason
    assert "¶2" in result.reason
    assert _draft_text(section) == before
    assert _commits(tmp_path) == ["checkpoint"]


def test_an_authorization_for_another_section_does_not_cover_this_one(tmp_path):
    repository, section = _repo(tmp_path)
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    result = apply_rewrite(repository, proposal, _authorize(SectionTarget("SEC-0099")))

    assert isinstance(result, Refused)


# --- an authorized write applies, and records its authorization durably -----


def test_an_authorized_rewrite_applies_and_commits_with_its_authorization(tmp_path):
    repository, section = _repo(tmp_path)
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    result = apply_rewrite(
        repository, proposal, _authorize(ParagraphTarget(section.brief.id, 2))
    )

    assert result == Applied(
        path="chapters/01/sections/01/draft.md",
        target=ParagraphTarget(section.brief.id, 2),
        authorized_by="SES-20260912-1432#T008",
    )
    assert _draft_text(section) == (
        "Bob went to town.\n\nBob came home at dusk.\n\nCarol wrote a letter.\n"
    )
    message = _last_message(tmp_path)
    assert "authorized-by: SES-20260912-1432#T008" in message
    assert f"authorized-scope: {section.brief.id} ¶2" in message
    assert "change-id:" not in message
    assert _git(tmp_path, "log", "-1", "--format=%an") .strip() == "Memoria"


def test_a_section_authorization_covers_any_paragraph_in_it(tmp_path):
    repository, section = _repo(tmp_path)
    proposal = propose_rewrite(repository, section.brief.id, 3, "Carol wrote to Bob.")

    result = apply_rewrite(repository, proposal, _authorize(SectionTarget(section.brief.id)))

    assert isinstance(result, Applied)
    assert _draft_text(section).endswith("Carol wrote to Bob.\n")


def test_an_ai_write_checkpoints_the_authors_outside_edits_first(tmp_path):
    repository, section = _repo(tmp_path)
    (repository.root / "book.md").write_text(
        "---\nid: BOOK\nunconfirmed: false\n---\n\nThe book, edited in Obsidian.\n",
        encoding="utf-8",
    )
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")

    apply_rewrite(repository, proposal, _authorize(ParagraphTarget(section.brief.id, 2)))

    subjects = _commits(tmp_path)
    assert subjects[0] == "write: chapters/01/sections/01/draft.md"
    assert subjects[1] == "checkpoint"
    assert "change-id:" in _git(tmp_path, "log", "-1", "--skip=1", "--format=%B")


# --- scoping is a byte-level property (§43.13), tested adversarially --------

# Three paragraphs that say the same thing, ragged whitespace between and
# around them, no trailing newline: the adversary's draft. A rewrite that
# matched by text would hit the wrong occurrence; one that split and
# re-joined would normalise the whitespace it never touched.
ADVERSARIAL = (
    "  Bob went to town.  \n"
    "\n"
    "   \n"
    "\n"
    "Bob went to town.\t\n"
    "\n"
    "\n"
    "Bob went to town."
)


def test_authorizing_one_paragraph_leaves_every_other_byte_identical(tmp_path):
    repository, section = _repo(tmp_path, draft=ADVERSARIAL)
    before = _draft_text(section)
    (start, end) = paragraph_spans(before)[1]
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob rode to town.")

    result = apply_rewrite(
        repository, proposal, _authorize(ParagraphTarget(section.brief.id, 2))
    )

    assert isinstance(result, Applied)
    after = _draft_text(section)
    # Everything before the authorized paragraph, byte for byte - the
    # leading spaces, the trailing spaces, the ragged blank lines.
    assert after[:start] == before[:start]
    # Everything after it, byte for byte - including the identical third
    # paragraph, which a text match would have hit first or as well.
    assert after[start + len("Bob rode to town."):] == before[end:]
    assert after[start:start + len("Bob rode to town.")] == "Bob rode to town."
    assert after.count("Bob went to town.") == 2


def test_the_first_of_identical_paragraphs_is_not_the_one_rewritten(tmp_path):
    repository, section = _repo(tmp_path, draft=ADVERSARIAL)
    proposal = propose_rewrite(repository, section.brief.id, 3, "Bob rode to town.")

    apply_rewrite(repository, proposal, _authorize(ParagraphTarget(section.brief.id, 3)))

    after = _draft_text(section)
    assert after.startswith("  Bob went to town.  \n")
    assert after.endswith("\n\n\nBob rode to town.")


def test_a_proposal_cannot_smuggle_a_second_paragraphs_change_in(tmp_path):
    """The adversary proposes ¶2's rewrite carrying ¶3's text too, hoping
    the splice replaces both. It cannot: the write replaces ¶2's bytes
    only, so ¶3 survives after the inserted text, and the draft now says
    what the proposal wrote plus what was there - never less."""
    repository, section = _repo(tmp_path)
    proposal = propose_rewrite(
        repository, section.brief.id, 2, "Bob came home.\n\nCarol never wrote."
    )

    apply_rewrite(repository, proposal, _authorize(ParagraphTarget(section.brief.id, 2)))

    after = _draft_text(section)
    assert after == (
        "Bob went to town.\n\nBob came home.\n\nCarol never wrote.\n\nCarol wrote a letter.\n"
    )


def test_a_rewrite_refuses_a_paragraph_that_moved_underneath_it(tmp_path):
    """An insert above the target shifts the numbering after the proposal
    was made. Landing ¶2 on what is now ¶2 would rewrite the wrong prose
    (ADR-0003's positional hazard); the pinned text catches it."""
    repository, section = _repo(tmp_path)
    proposal = propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk.")
    (section.dir / "draft.md").write_text(
        "A new opening paragraph.\n\n" + DRAFT, encoding="utf-8"
    )
    before = _draft_text(section)

    result = apply_rewrite(
        repository, proposal, _authorize(ParagraphTarget(section.brief.id, 2))
    )

    assert isinstance(result, Refused)
    assert "moved" in result.reason
    assert _draft_text(section) == before


def test_paragraph_numbering_agrees_with_the_audits(tmp_path):
    repository, section = _repo(tmp_path, draft=ADVERSARIAL + "\n\n  \n  Last one.\n\n")

    text = _draft_text(section)
    spans = paragraph_spans(text)

    assert [text[s:e] for s, e in spans] == [
        p.text for p in manuscript_paragraphs(repository)
    ]
    assert read_paragraph(repository, section.brief.id, 4) == "Last one."


def test_read_ref_serves_a_section_paragraph(tmp_path):
    repository, section = _repo(tmp_path)

    assert read(repository, f"{section.brief.id} ¶2").text == "Bob came home late."
    assert read(repository, f"{section.brief.id} P2").citation == f"{section.brief.id} ¶2"
    with pytest.raises(ReadError, match="no ¶9"):
        read(repository, f"{section.brief.id} ¶9")


# --- a whole draft, for a planned section ----------------------------------------


def test_drafting_a_planned_section_needs_a_section_authorization(tmp_path):
    repository, section = _repo(tmp_path)
    planned = manuscript.create_section(repository, 1, "Section two, planned.")
    _git(tmp_path, "add", "-A")
    checkpoint(repository)

    refused = write_draft(
        repository, planned.brief.id, "New prose.",
        _authorize(ParagraphTarget(planned.brief.id, 1)),
    )
    applied = write_draft(
        repository, planned.brief.id, "New prose.", _authorize(SectionTarget(planned.brief.id))
    )

    assert isinstance(refused, Refused)
    assert isinstance(applied, Applied)
    assert (planned.dir / "draft.md").read_text(encoding="utf-8") == "New prose."
    assert "authorized-by: SES-20260912-1432#T008" in _last_message(tmp_path)
    assert f"authorized-scope: {planned.brief.id} draft" in _last_message(tmp_path)


# --- batch authorization records each write individually (§21) -----------------


def test_a_batch_is_one_commit_per_write_each_with_its_own_authorization(tmp_path):
    repository, section = _repo(tmp_path)
    proposals = [
        propose_rewrite(repository, section.brief.id, 1, "Bob rode to town.\n\nIt rained."),
        propose_rewrite(repository, section.brief.id, 3, "Carol wrote to Bob."),
    ]
    authorization = _authorize(
        ParagraphTarget(section.brief.id, 1), ParagraphTarget(section.brief.id, 3)
    )

    results = apply_rewrites(repository, proposals, authorization)

    assert [type(r) for r in results] == [Applied, Applied]
    assert _draft_text(section) == (
        "Bob rode to town.\n\nIt rained.\n\nBob came home late.\n\nCarol wrote to Bob.\n"
    )
    log = _git(tmp_path, "log", "--format=%B%x1e")
    bodies = [b.strip() for b in log.split("\x1e") if b.strip()]
    assert len(bodies) == 3  # two writes, then the checkpoint
    assert f"authorized-scope: {section.brief.id} ¶1" in bodies[0]
    assert f"authorized-scope: {section.brief.id} ¶3" in bodies[1]
    assert all("authorized-by: SES-20260912-1432#T008" in b for b in bodies[:2])


def test_a_batch_applies_only_the_writes_it_covers(tmp_path):
    repository, section = _repo(tmp_path)
    proposals = [
        propose_rewrite(repository, section.brief.id, 1, "Bob rode to town."),
        propose_rewrite(repository, section.brief.id, 2, "Bob came home at dusk."),
    ]

    results = apply_rewrites(
        repository, proposals, _authorize(ParagraphTarget(section.brief.id, 1))
    )

    assert isinstance(results[0], Applied)
    assert isinstance(results[1], Refused)
    assert _draft_text(section) == (
        "Bob rode to town.\n\nBob came home late.\n\nCarol wrote a letter.\n"
    )


# --- the brief's AI write path: one level below prose, separately (§19.3) ---


def test_a_brief_is_written_from_a_conversation_under_its_own_authorization(tmp_path):
    repository, section = _repo(tmp_path)
    manuscript.write_brief(section.path, "A placeholder.")
    _git(tmp_path, "add", "-A")
    checkpoint(repository)

    result = write_brief_from_conversation(
        repository, section.brief.id, "What this section is for, as the author said.",
        Authorization(SESSION, 12, frozenset({BriefTarget(section.brief.id)})),
    )

    assert result == Applied(
        path="chapters/01/sections/01/section.md",
        target=BriefTarget(section.brief.id),
        authorized_by="SES-20260912-1432#T012",
    )
    brief = manuscript.resolve_section(repository, section.brief.id).brief
    assert brief.text == "What this section is for, as the author said."
    assert brief.unconfirmed is False
    message = _last_message(tmp_path)
    assert "authorized-by: SES-20260912-1432#T012" in message
    assert f"authorized-scope: {section.brief.id} brief" in message


def test_the_conversation_path_clears_an_unconfirmed_brief(tmp_path):
    repository, section = _repo(tmp_path)
    chapter = manuscript.create_chapter(repository, "Summarized.", unconfirmed=True)
    _git(tmp_path, "add", "-A")
    checkpoint(repository)

    write_brief_from_conversation(
        repository, chapter.brief.id, "What the author said it is for.",
        Authorization(SESSION, 3, frozenset({BriefTarget(chapter.brief.id)})),
    )

    assert manuscript.resolve_chapter(repository, chapter.brief.id).brief.unconfirmed is False


def test_the_book_brief_takes_the_same_path(tmp_path):
    repository, _ = _repo(tmp_path)

    result = write_brief_from_conversation(
        repository, "BOOK", "What the book is.",
        Authorization(SESSION, 3, frozenset({BriefTarget("BOOK")})),
    )

    assert isinstance(result, Applied)
    assert manuscript.parse_brief(
        (repository.root / "book.md").read_text(encoding="utf-8")
    ).text == "What the book is."


def test_a_brief_write_without_an_authorization_is_refused(tmp_path):
    repository, section = _repo(tmp_path)
    before = section.path.read_text(encoding="utf-8")

    result = write_brief_from_conversation(repository, section.brief.id, "Rewritten.")

    assert isinstance(result, Refused)
    assert section.path.read_text(encoding="utf-8") == before
    assert _commits(tmp_path) == ["checkpoint"]


def test_a_prose_authorization_does_not_reach_a_brief(tmp_path):
    """An authorization that covers the section's draft - broad work in
    that section - still does not cover its brief: a brief is authorized
    one level below, by an act on that brief alone."""
    repository, section = _repo(tmp_path)
    before = section.path.read_text(encoding="utf-8")

    result = write_brief_from_conversation(
        repository, section.brief.id, "Rewritten.", _authorize(SectionTarget(section.brief.id))
    )

    assert isinstance(result, Refused)
    assert "separately" in result.reason
    assert section.path.read_text(encoding="utf-8") == before


def test_an_authorization_covering_a_brief_and_anything_else_is_refused_for_the_brief(tmp_path):
    """Never in a batch (§19.3, §21): one authorization for a brief and a
    paragraph, or for two briefs, writes no brief."""
    repository, section = _repo(tmp_path)

    with_prose = write_brief_from_conversation(
        repository, section.brief.id, "Rewritten.",
        _authorize(BriefTarget(section.brief.id), ParagraphTarget(section.brief.id, 1)),
    )
    two_briefs = write_brief_from_conversation(
        repository, section.brief.id, "Rewritten.",
        _authorize(BriefTarget(section.brief.id), BriefTarget("BOOK")),
    )

    assert isinstance(with_prose, Refused)
    assert isinstance(two_briefs, Refused)
    assert _commits(tmp_path) == ["checkpoint"]


def test_a_batch_of_proposals_cannot_name_a_brief():
    """Structural: a `Proposal` is a paragraph, so `apply_rewrites` has no
    argument through which a brief could be written."""
    assert "brief" not in {f.name for f in authorship.Proposal.__dataclass_fields__.values()}
    assert set(authorship.Proposal.__dataclass_fields__) == {
        "section_id", "paragraph", "current_text", "proposed_text"
    }


def test_an_unknown_brief_id_is_a_named_error(tmp_path):
    repository, _ = _repo(tmp_path)

    with pytest.raises(AuthorshipError, match="SEC-0042"):
        write_brief_from_conversation(
            repository, "SEC-0042", "x",
            Authorization(SESSION, 1, frozenset({BriefTarget("SEC-0042")})),
        )
    with pytest.raises(AuthorshipError, match="not a brief id"):
        write_brief_from_conversation(
            repository, "DEC-0001", "x",
            Authorization(SESSION, 1, frozenset({BriefTarget("DEC-0001")})),
        )


# --- the module writes only through memoria.write ----------------------------


def test_authorship_writes_no_file_itself():
    """Every write here is `memoria.write.write`/`create`: that is what
    makes the commit, the trailer, the checkpoint and the staleness token
    apply to an AI write without a second discipline. (The suite-wide
    guard in test_write.py enforces this too; this names the reason.)"""
    source = (Path(authorship.__file__)).read_text(encoding="utf-8")
    assert "write_text" not in source
    assert "os.replace" not in source
