"""The subject system's durable half: subjects, entries, and match terms.

Part of the build plan's part 06 §8. A subject prompt carries four required
declarations (what counts as a match, the matching hazards, the audit
questions, and whether it auto-promotes); an entry carries a body (testimony
and badged statements) and match terms (the system's only alias store).
"""

import pytest

from memoria.subjects import (
    BUILTIN_SUBJECTS,
    Entry,
    Subject,
    SubjectError,
    classify_match_term,
    entry_to_markdown,
    find_entry_path,
    load_entry,
    load_subject,
    parse_entry,
    parse_statements,
    parse_subject,
    subject_path,
    subject_to_markdown,
    write_builtin_subjects,
)
from memoria.repository import Repository


def _subject(**overrides):
    fields = dict(
        id="SUB-people",
        match="An entry under People represents a person.",
        hazards="Do not merge people sharing a surname without corroboration.",
        audit_questions="Does the passage contradict a settled fact about this person?",
        auto_promote=False,
    )
    fields.update(overrides)
    return Subject(**fields)


# --- the subject prompt format ----------------------------------------------


def test_subject_to_markdown_and_parse_subject_are_inverses():
    original = _subject()
    text = subject_to_markdown(original)

    assert parse_subject(text) == original
    assert subject_to_markdown(parse_subject(text)) == text


def test_parse_subject_requires_the_match_section():
    text = subject_to_markdown(_subject()).replace("## Match", "## Matching")
    with pytest.raises(SubjectError, match="match"):
        parse_subject(text)


def test_parse_subject_requires_the_hazards_section():
    text = subject_to_markdown(_subject()).replace("## Hazards", "## Risks")
    with pytest.raises(SubjectError, match="hazards"):
        parse_subject(text)


def test_parse_subject_requires_the_audit_questions_section():
    text = subject_to_markdown(_subject()).replace(
        "## Audit questions", "## Audit"
    )
    with pytest.raises(SubjectError, match="audit questions"):
        parse_subject(text)


def test_parse_subject_requires_the_auto_promote_declaration():
    text = subject_to_markdown(_subject()).replace("auto-promote: false\n", "")
    with pytest.raises(SubjectError, match="auto-promote"):
        parse_subject(text)


def test_parse_subject_accepts_auto_promote_true():
    original = _subject(auto_promote=True)
    text = subject_to_markdown(original)
    assert parse_subject(text) == original


# --- the five built-in subjects ---------------------------------------------


def test_five_builtin_subjects_are_declared():
    assert {s.id for s in BUILTIN_SUBJECTS} == {
        "SUB-people",
        "SUB-timeline",
        "SUB-events",
        "SUB-themes",
        "SUB-arcs",
    }


def test_every_builtin_subject_carries_all_four_declarations():
    for subject in BUILTIN_SUBJECTS:
        assert subject.match.strip()
        assert subject.hazards.strip()
        assert subject.audit_questions.strip()
        assert isinstance(subject.auto_promote, bool)


def test_every_builtin_subject_ships_with_auto_promote_off():
    assert all(not subject.auto_promote for subject in BUILTIN_SUBJECTS)


def test_people_hazards_name_surname_collision_and_multi_form_naming():
    people = next(s for s in BUILTIN_SUBJECTS if s.id == "SUB-people")

    # Stated as classes - no corpus instance, no specific name.
    assert "surname" in people.hazards.lower()
    assert "corroboration" in people.hazards.lower()
    assert "initial" in people.hazards.lower() or "alias" in people.hazards.lower()


def test_every_builtin_subject_round_trips_through_the_serializer():
    for subject in BUILTIN_SUBJECTS:
        text = subject_to_markdown(subject)
        assert parse_subject(text) == subject


def test_write_builtin_subjects_creates_one_file_per_subject(tmp_path):
    repository = Repository(root=tmp_path)

    written = write_builtin_subjects(repository)

    assert len(written) == 5
    for subject in BUILTIN_SUBJECTS:
        path = subject_path(repository, subject.id)
        assert path.is_file()
        assert parse_subject(path.read_text(encoding="utf-8")) == subject


def test_write_builtin_subjects_does_not_clobber_an_author_edit(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    path = subject_path(repository, "SUB-people")
    edited = path.read_text(encoding="utf-8").replace(
        "Do not merge people sharing a surname without corroboration.",
        "Do not merge people sharing a surname. My own note: watch for Bob.",
    )
    path.write_text(edited, encoding="utf-8")

    write_builtin_subjects(repository)

    assert path.read_text(encoding="utf-8") == edited


# --- entries -----------------------------------------------------------------


def _entry(**overrides):
    fields = dict(
        id="SUB-people/bob",
        match_terms=["Bob", "Robert", "R."],
        body="Bob was born in 1962 in Cleveland.\n\n"
        "[source] Bob called on July 17.\n— SRC-000184 ¶17",
    )
    fields.update(overrides)
    return Entry(**fields)


def test_entry_to_markdown_and_parse_entry_are_inverses():
    original = _entry()
    text = entry_to_markdown(original)

    assert parse_entry(text) == original
    assert entry_to_markdown(parse_entry(text)) == text


def test_entry_with_no_match_terms_round_trips():
    original = _entry(match_terms=[])
    text = entry_to_markdown(original)
    assert parse_entry(text) == original


def test_parse_entry_requires_an_id():
    text = entry_to_markdown(_entry()).replace("id: SUB-people/bob\n", "")
    with pytest.raises(SubjectError, match="id"):
        parse_entry(text)


@pytest.mark.parametrize(
    "bad_id",
    [
        "SUB-people",  # bare subject id - no /<entry-slug> at all (#119)
        "people/bob",  # missing the SUB- prefix
        "SUB-people/",  # empty entry-slug segment
        "SUB-/bob",  # empty subject segment
    ],
)
def test_parse_entry_rejects_a_malformed_id_shape(bad_id):
    text = entry_to_markdown(_entry()).replace("id: SUB-people/bob\n", f"id: {bad_id}\n")
    with pytest.raises(SubjectError, match="SUB-<subject>/<entry-slug>"):
        parse_entry(text)


def test_parse_entry_accepts_a_well_formed_id():
    original = _entry(id="SUB-people/bob")
    text = entry_to_markdown(original)
    assert parse_entry(text) == original


# --- testimony and badged statements are distinguishable --------------------


def test_testimony_carries_no_badge():
    statements = parse_statements("Bob was born in 1962 in Cleveland.")
    assert len(statements) == 1
    assert statements[0].badge is None
    assert statements[0].text == "Bob was born in 1962 in Cleveland."


@pytest.mark.parametrize("badge", ["author", "source", "inferred", "open"])
def test_a_badged_statement_carries_its_badge(badge):
    body = f"[{badge}] Something was said.\n— SRC-000184 ¶17"
    statements = parse_statements(body)
    assert len(statements) == 1
    assert statements[0].badge == badge
    assert statements[0].text.startswith("Something was said.")


def test_testimony_and_badged_statements_in_one_body_are_distinguishable():
    body = (
        "Bob was born in 1962 in Cleveland.\n\n"
        "[source] Bob called on July 17.\n— SRC-000184 ¶17\n\n"
        "[inferred] Fear of losing control appears to intensify.\n\n"
        "[open] Maybe this reflects embarrassment."
    )
    statements = parse_statements(body)

    assert [s.badge for s in statements] == [None, "source", "inferred", "open"]
    assert statements[0].text.startswith("Bob was born")


# --- match terms: word, entry reference, or relation ------------------------


def test_classify_match_term_recognizes_a_plain_word():
    assert classify_match_term("Bob") == "word"
    assert classify_match_term("my brother-in-law") == "word"


def test_classify_match_term_recognizes_an_entry_reference():
    assert classify_match_term("SUB-people/bob") == "entry"


def test_classify_match_term_recognizes_a_relation():
    assert (
        classify_match_term("SUB-people/bob -> pressures -> SUB-people/author")
        == "relation"
    )


def test_classify_match_term_rejects_a_malformed_entry_reference():
    with pytest.raises(SubjectError, match="entry"):
        classify_match_term("SUB-People/Bob")


def test_classify_match_term_rejects_a_relation_missing_a_verb():
    with pytest.raises(SubjectError, match="relation"):
        classify_match_term("SUB-people/bob ->  -> SUB-people/author")


def test_classify_match_term_rejects_a_relation_not_between_two_entries():
    with pytest.raises(SubjectError, match="entry reference"):
        classify_match_term("Bob -> pressures -> SUB-people/author")


def test_classify_match_term_rejects_an_unspaced_relation_as_a_relation():
    # Missing the required spaces around "->" - diagnosed as a malformed
    # relation, not a malformed entry reference, even though the left side
    # alone would otherwise look like one (issue #91).
    with pytest.raises(SubjectError, match="relation"):
        classify_match_term("SUB-people/bob->pressures->SUB-people/author")


def test_parse_entry_rejects_a_malformed_match_term():
    text = entry_to_markdown(_entry(match_terms=["SUB-People/Bob"]))
    with pytest.raises(SubjectError, match="entry"):
        parse_entry(text)


def test_parse_entry_accepts_all_three_match_term_shapes():
    entry = _entry(
        match_terms=[
            "Bob",
            "SUB-people/bob",
            "SUB-people/bob -> pressures -> SUB-people/author",
        ]
    )
    text = entry_to_markdown(entry)
    assert parse_entry(text) == entry


# --- SUB-x/y IDs survive a file rename ---------------------------------------


def test_load_entry_finds_a_renamed_file_by_its_frontmatter_id(tmp_path):
    repository = Repository(root=tmp_path)
    subjects_dir = tmp_path / "subjects" / "people"
    subjects_dir.mkdir(parents=True)
    (subjects_dir / "some-other-filename.md").write_text(
        entry_to_markdown(_entry()), encoding="utf-8"
    )

    entry = load_entry(repository, "SUB-people", "bob")

    assert entry.id == "SUB-people/bob"


def test_find_entry_path_returns_none_when_no_entry_matches(tmp_path):
    repository = Repository(root=tmp_path)
    (tmp_path / "subjects" / "people").mkdir(parents=True)

    assert find_entry_path(repository, "SUB-people", "bob") is None


def test_load_entry_raises_for_a_missing_subject(tmp_path):
    repository = Repository(root=tmp_path)
    with pytest.raises(SubjectError, match="no such subject"):
        load_entry(repository, "SUB-people", "bob")


def test_load_subject_raises_for_a_missing_subject(tmp_path):
    repository = Repository(root=tmp_path)
    with pytest.raises(SubjectError, match="no such subject"):
        load_subject(repository, "SUB-people")


def test_find_entry_path_skips_an_unrelated_malformed_sibling(tmp_path):
    """A stray bad entry elsewhere in the subject must not blow up the scan
    for a different, validly renamed entry (reproduces PR #84 review round 1).
    """
    repository = Repository(root=tmp_path)
    subjects_dir = tmp_path / "subjects" / "people"
    subjects_dir.mkdir(parents=True)
    # Unrelated, malformed - a typo'd match term.
    (subjects_dir / "bob.md").write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["SUB-People/Bob"], body="Bob.")
        ),
        encoding="utf-8",
    )
    # The one actually being looked up, validly renamed.
    (subjects_dir / "renamed-carol.md").write_text(
        entry_to_markdown(Entry(id="SUB-people/carol", body="Carol.")),
        encoding="utf-8",
    )

    path = find_entry_path(repository, "SUB-people", "carol")

    assert path == subjects_dir / "renamed-carol.md"


def test_load_entry_skips_an_unrelated_malformed_sibling(tmp_path):
    repository = Repository(root=tmp_path)
    subjects_dir = tmp_path / "subjects" / "people"
    subjects_dir.mkdir(parents=True)
    (subjects_dir / "bob.md").write_text(
        entry_to_markdown(
            Entry(id="SUB-people/bob", match_terms=["SUB-People/Bob"], body="Bob.")
        ),
        encoding="utf-8",
    )
    (subjects_dir / "renamed-carol.md").write_text(
        entry_to_markdown(Entry(id="SUB-people/carol", body="Carol.")),
        encoding="utf-8",
    )

    entry = load_entry(repository, "SUB-people", "carol")

    assert entry.id == "SUB-people/carol"
