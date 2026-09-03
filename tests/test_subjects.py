"""The subject system's durable half: subjects, entries, and match terms.

Part of the build plan's part 06 §8. A subject prompt carries four required
declarations (what counts as a match, the matching hazards, the audit
questions, and whether it auto-promotes); an entry carries a body (testimony
and badged statements) and match terms (the system's only alias store).
"""

import pytest

from memoria.subjects import (
    MEMORIA_NOTE,
    BUILTIN_SUBJECTS,
    Entry,
    OverlayAct,
    Subject,
    SubjectError,
    classify_match_term,
    entry_to_markdown,
    SUBJECTS_RELATIVE_PATH,
    Statement,
    find_entry_path,
    is_audit_visible,
    is_seeded,
    load_all_subjects,
    load_entry,
    load_subject,
    parse_entry,
    parse_statements,
    parse_subject,
    serve_entry,
    set_match_terms,
    subject_path,
    subject_to_markdown,
    write_builtin_subjects,
)
from memoria.repository import Repository
from memoria.write import Actor, Rejected, WriteError, Written


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


def test_entry_overlay_round_trips():
    """#21: a pin/exclusion recorded on the entry (``OverlayAct``) survives
    the ``entry_to_markdown``/``parse_entry`` cycle - the same inverse
    property AC 3/4's durability guarantee depends on."""
    original = _entry(
        overlay=[
            OverlayAct(
                anchor="src-000001-p1",
                action="pin",
                actor_name="Author",
                actor_email="author@example.com",
                at="2026-09-01T00:00:00+00:00",
            )
        ]
    )
    text = entry_to_markdown(original)
    assert "overlay:" in text
    assert parse_entry(text) == original


def test_entry_with_no_overlay_writes_no_overlay_key():
    """The common case - never pinned or excluded - writes no bare
    ``overlay: []`` into every entry's frontmatter."""
    text = entry_to_markdown(_entry())
    assert "overlay" not in text


def test_entry_extra_frontmatter_round_trips():
    """A rewrite (``pin``/``exclude``, #21 - the first code path that
    rewrites an *existing* entry file) must not drop a frontmatter key this
    module does not itself model, the same contract
    ``memoria.manifest.ManifestEntry.extra`` keeps."""
    original = _entry(extra={"custom_key": "keep-me"})
    text = entry_to_markdown(original)
    assert "custom_key: keep-me" in text
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


# --- is_seeded (#157) -------------------------------------------------------


def test_load_all_subjects_over_a_missing_directory_is_empty_not_an_error(tmp_path):
    """An unseeded repository is an empty subject list, not a failure - the
    same posture `records.read_all` keeps for an un-normalized one."""
    assert load_all_subjects(Repository(root=tmp_path)) == []


def test_a_repository_with_no_subjects_directory_is_not_seeded(tmp_path):
    """The unbuilt half of the pair the empty list cannot express."""
    repository = Repository(root=tmp_path)

    assert is_seeded(repository) is False
    assert load_all_subjects(repository) == []


def test_a_subjects_directory_that_holds_no_prompts_is_still_seeded(tmp_path):
    """Pinned so a later reader cannot quietly tighten the predicate.

    The directory is the signal, not its contents: the stricter test is
    definitionally `bool(load_all_subjects(...))` and would carry nothing
    the caller's own list did not already carry - see `is_seeded`.
    """
    (tmp_path / SUBJECTS_RELATIVE_PATH).mkdir()
    repository = Repository(root=tmp_path)

    assert is_seeded(repository) is True
    assert load_all_subjects(repository) == []


def test_a_seeded_repository_is_seeded(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)

    assert is_seeded(repository) is True
    assert len(load_all_subjects(repository)) == len(BUILTIN_SUBJECTS)


# --- the audit-visible body (part 06 §8.2) -----------------------------------


@pytest.mark.parametrize("badge", [None, "author", "source", "inferred"])
def test_testimony_and_every_badge_but_open_is_audit_visible(badge):
    assert is_audit_visible(Statement(badge=badge, text="Bob kept the ledger.")) is True


def test_an_open_line_is_not_audit_visible():
    """`[open]` sits outside the body assembly loads and the audit compares
    prose against - so the entry view draws it outside the body too, off
    this same predicate."""
    assert is_audit_visible(Statement(badge="open", text="Did Bob know?")) is False


MEMORIA_NOTE_TEXT = (
    "> **Memoria note — 2026-10-18**\n"
    ">\n"
    "> Later research cuts against the interpretation above.\n"
    "> See RES-20261018-003 and SRC-002914 ¶8.\n"
    "> The author text has been left unchanged."
)


def test_a_memoria_note_is_parsed_as_a_note_and_not_as_testimony():
    """Part 08 §14.2's note is a blockquote paragraph in the shared body. An
    unbadged paragraph is testimony by definition (§9.5), so without its own
    kind the Curator's note would read as the author's own words."""
    body = f"[inferred] Fear of losing control appears to intensify.\n\n{MEMORIA_NOTE_TEXT}"
    statements = parse_statements(body)

    assert [s.badge for s in statements] == ["inferred", MEMORIA_NOTE]
    assert statements[1].text == MEMORIA_NOTE_TEXT


def test_a_memoria_note_is_not_audit_visible():
    """"It never loads into write-side assembly and the audit never
    evaluates against it" (part 08 §14.2) - the same predicate that keeps
    `[open]` out, so neither consumer needs a rule of its own."""
    assert is_audit_visible(Statement(badge=MEMORIA_NOTE, text=MEMORIA_NOTE_TEXT)) is False


# --- serving an entry for editing (ADR-0003, #26) ----------------------------


def _git(cwd, *args):
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


AUTHOR = Actor(name="Author", email="author@memoria.test")


def _entry_repo(tmp_path, entry=None) -> Repository:
    """A real git repository holding one entry, committed.

    Real, because `set_match_terms` goes through the write path and the
    write path commits - a fake would test everything except the half
    ADR-0003 decision 2 is about.
    """
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local-author@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    path = tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry_to_markdown(entry or _entry()), encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return repository


def test_serve_entry_returns_the_entry_and_a_token(tmp_path):
    repository = _entry_repo(tmp_path)

    entry, token = serve_entry(repository, "SUB-people", "bob")

    assert entry == _entry()
    assert token


def test_serve_entry_mints_a_new_token_when_the_file_changes(tmp_path):
    """The token is a content hash of the file as it was read (ADR-0003
    decision 1) - an edit in Obsidian has to change it, or the check it
    exists for never fires."""
    repository = _entry_repo(tmp_path)
    _, before = serve_entry(repository, "SUB-people", "bob")

    (tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md").write_text(
        entry_to_markdown(_entry(match_terms=["Bob", "Bobby"])), encoding="utf-8"
    )
    _, after = serve_entry(repository, "SUB-people", "bob")

    assert before != after


def test_serve_entry_resolves_an_entry_whose_file_was_renamed(tmp_path):
    """`find_entry_path`'s frontmatter fallback, inherited rather than
    repeated - and it must reach the *renamed* file, because a caller that
    rebuilt the path from the slug would write a second file beside it."""
    repository = _entry_repo(tmp_path)
    people = tmp_path / SUBJECTS_RELATIVE_PATH / "people"
    (people / "bob.md").rename(people / "robert-the-elder.md")

    entry, token = serve_entry(repository, "SUB-people", "bob")

    assert entry.id == "SUB-people/bob"
    assert token


@pytest.mark.parametrize(
    "subject_id, entry_slug", [("SUB-people", "nobody"), ("SUB-nothing", "bob")]
)
def test_serve_entry_raises_for_an_unknown_subject_or_entry(tmp_path, subject_id, entry_slug):
    repository = _entry_repo(tmp_path)

    with pytest.raises(SubjectError, match="no such "):
        serve_entry(repository, subject_id, entry_slug)


# --- the match-term write (#26) ----------------------------------------------


def test_setting_match_terms_with_a_current_token_writes_them(tmp_path):
    repository = _entry_repo(tmp_path)
    _, token = serve_entry(repository, "SUB-people", "bob")

    result = set_match_terms(repository, "SUB-people", "bob", ["Bob", "Bobby"], token, AUTHOR)

    assert isinstance(result, Written)
    assert load_entry(repository, "SUB-people", "bob").match_terms == ["Bob", "Bobby"]


def test_a_match_term_write_leaves_the_body_overlay_and_extra_untouched(tmp_path):
    """Match terms are frontmatter; everything else on the entry round-trips
    through `entry_to_markdown`. This is what makes the write safe to do to
    a file the author also edits in Obsidian."""
    original = _entry(
        overlay=[
            OverlayAct(
                anchor="src-000184-p17",
                action="pin",
                actor_name="A Person",
                actor_email="person@example.com",
                at="2026-09-02T00:00:00Z",
            )
        ],
        extra={"obsidian-tags": ["family"]},
    )
    repository = _entry_repo(tmp_path, original)
    _, token = serve_entry(repository, "SUB-people", "bob")

    set_match_terms(repository, "SUB-people", "bob", ["Bob"], token, AUTHOR)

    written = load_entry(repository, "SUB-people", "bob")
    assert written.body == original.body
    assert written.overlay == original.overlay
    assert written.extra == original.extra


def test_an_accepted_match_term_write_commits_as_the_actor(tmp_path):
    """ADR-0003 decision 2: without the commit, every file the author
    touches in the app carries uncommitted modifications and #32's
    dirty-tree rule closes it to the Curator."""
    import subprocess

    repository = _entry_repo(tmp_path)
    _, token = serve_entry(repository, "SUB-people", "bob")

    set_match_terms(repository, "SUB-people", "bob", ["Bob"], token, AUTHOR)

    log = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>%n%B"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert log.startswith("Author <author@memoria.test>")
    assert "subjects/people/bob.md" in log
    assert not subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()


def test_a_stale_token_is_rejected_and_the_file_is_left_byte_identical(tmp_path):
    """#26's fifth acceptance criterion. The author opened the entry in the
    app and then edited it in Obsidian; the app's write must not destroy
    that, and must not half-apply either (ADR-0003 decisions 1 and 3)."""
    repository = _entry_repo(tmp_path)
    _, stale = serve_entry(repository, "SUB-people", "bob")

    path = tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md"
    obsidian = entry_to_markdown(_entry(body="Bob was born in 1962 in Akron."))
    path.write_text(obsidian, encoding="utf-8")

    result = set_match_terms(repository, "SUB-people", "bob", ["Bob"], stale, AUTHOR)

    assert isinstance(result, Rejected)
    assert result.outcome == "stale"
    assert path.read_text(encoding="utf-8") == obsidian


def test_a_rejected_write_leaves_no_commit_behind(tmp_path):
    import subprocess

    repository = _entry_repo(tmp_path)
    _, stale = serve_entry(repository, "SUB-people", "bob")
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    (tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md").write_text(
        entry_to_markdown(_entry(body="Elsewhere.")), encoding="utf-8"
    )

    set_match_terms(repository, "SUB-people", "bob", ["Bob"], stale, AUTHOR)

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert before == after


def test_a_malformed_match_term_is_refused_before_the_file_is_touched(tmp_path):
    """A bad term makes the whole entry unparseable, taking its testimony
    and its overlay with it - so it is checked before the write, not caught
    by a later read."""
    repository = _entry_repo(tmp_path)
    path = tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md"
    before = path.read_text(encoding="utf-8")
    _, token = serve_entry(repository, "SUB-people", "bob")

    with pytest.raises(SubjectError):
        set_match_terms(repository, "SUB-people", "bob", ["SUB-people/"], token, AUTHOR)

    assert path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "actor", [Actor(name="", email="a@b.test"), Actor(name="A", email="   ")]
)
def test_an_unattributed_actor_is_refused_before_the_file_is_touched(tmp_path, actor):
    """`index._record_overlay`'s guard, for its reason: the write replaces
    the file before it commits, so relying on the commit to refuse an empty
    identity would leave a partially-applied durable write behind."""
    repository = _entry_repo(tmp_path)
    path = tmp_path / SUBJECTS_RELATIVE_PATH / "people" / "bob.md"
    before = path.read_text(encoding="utf-8")
    _, token = serve_entry(repository, "SUB-people", "bob")

    with pytest.raises(WriteError, match="attributed"):
        set_match_terms(repository, "SUB-people", "bob", ["Bob"], token, actor)

    assert path.read_text(encoding="utf-8") == before


def test_match_terms_can_be_emptied(tmp_path):
    """An entry with no match terms still matches on its implicit name
    (`extraction.implicit_name_term`), so this is a legitimate edit rather
    than a degenerate one to guard against."""
    repository = _entry_repo(tmp_path)
    _, token = serve_entry(repository, "SUB-people", "bob")

    result = set_match_terms(repository, "SUB-people", "bob", [], token, AUTHOR)

    assert isinstance(result, Written)
    assert load_entry(repository, "SUB-people", "bob").match_terms == []


def test_an_entry_reference_or_relation_is_a_valid_match_term(tmp_path):
    """A Theme's match terms name entries and relations rather than words
    (ADR-0005) - the write path must not reject the shape that makes a
    Theme gather."""
    repository = _entry_repo(tmp_path)
    _, token = serve_entry(repository, "SUB-people", "bob")
    terms = ["SUB-people/bob", "SUB-people/bob -> pressures -> SUB-people/alice"]

    result = set_match_terms(repository, "SUB-people", "bob", terms, token, AUTHOR)

    assert isinstance(result, Written)
    assert load_entry(repository, "SUB-people", "bob").match_terms == terms
