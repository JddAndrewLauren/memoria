"""The extraction: candidates, placements, relations, clusters, summaries (#17)."""

import ast
import json
import pathlib
import sqlite3
import subprocess

import pytest

from memoria import extraction as ex
from memoria.index import (
    DERIVED_TABLES,
    INDEX_RELATIVE_PATH,
    SearchFilters,
    build_index,
    rebuild,
)
from memoria.records import NormalizedRecord, write_normalized_records
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import Repository
from memoria.subjects import (
    Entry,
    entry_to_markdown,
    load_all_entries,
    load_all_subjects,
    write_builtin_subjects,
)

SRC_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "memoria"


# --- helpers -----------------------------------------------------------------


def _record(paragraphs, record_id="SRC-000001", event_date="Oct. 22."):
    return NormalizedRecord(
        id=record_id,
        source_type="journal",
        recorded_date=event_date,
        event_date=event_date,
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=paragraphs,
    )


def _repo(tmp_path, paragraphs, entries=(), auto_promote=(), event_date="Oct. 22."):
    """A repository with the built-in subjects, an index, and some entries."""
    repository = Repository(root=tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_builtin_subjects(repository)
    for subject_id in auto_promote:
        path = tmp_path / "subjects" / subject_id[len("SUB-") :] / "_subject.md"
        path.write_text(
            path.read_text().replace("auto-promote: false", "auto-promote: true")
        )
    for entry in entries:
        slug = entry.id.split("/", 1)[1]
        subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
        (tmp_path / "subjects" / subject_slug / f"{slug}.md").write_text(
            entry_to_markdown(entry)
        )
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(tmp_path),
            "-c", "user.email=author@example.com", "-c", "user.name=Author",
            "commit", "-qm", "seed",
        ],
        check=True,
    )
    record = _record(paragraphs, event_date=event_date)
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    return repository


def _memo(repository, anchor, **kwargs):
    ex.record_extraction(repository, anchor, ex.ParagraphExtraction(**kwargs))


def _rows(repository, table):
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    try:
        return con.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        con.close()


def _place(entry_id, surface_form):
    return ex.ProposedPlacement(entry_id, surface_form)


def _form(surface_form, subject_id="SUB-people"):
    return ex.ProposedForm(surface_form, subject_id)


# --- AC 1: nothing here invokes a model --------------------------------------


def test_no_core_module_imports_a_model_client():
    """AC 1: no code path invokes a model unasked.

    The core computes; the session model is reached only by a tool handing
    text out and taking a result back. An import of a model client anywhere in
    the core would be the first place that stopped being true, so this is an
    AST sweep in the shape of `test_no_other_module_writes_a_file`.

    Like that guard, it is against drift rather than against an adversary: a
    `__import__` built from a string would walk past it. The runtime half of
    the claim is the socket test below, which is the one that actually holds.
    """
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib", "socket"}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.parts[-2] in ("mcp", "web"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in forbidden, (
                    f"{path.name} imports {name}: the core calls no model"
                )


def test_the_whole_pass_leaves_no_process_and_opens_no_socket(tmp_path, monkeypatch):
    """AC 14, the real half: the summary step never invokes a model.

    A model call has to leave this process, so nothing may leave this process.
    Sockets and subprocesses are made to raise, and then the entire
    derive-and-summarize loop is driven to completion over them.
    """
    import socket

    repository = _repo(tmp_path, ["Bob and the acquisition.", "Bob again."])
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))

    def refuse(*args, **kwargs):
        raise AssertionError("the extraction left the process")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)

    ex.derive(repository, recurrence_threshold=1)
    pending = ex.pending_cluster_summaries(repository)
    assert pending
    for task in pending:
        ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")
    assert ex.pending_cluster_summaries(repository) == []


# --- AC 2: the memo key ------------------------------------------------------


def test_a_paragraph_already_read_is_not_offered_again(tmp_path):
    repository = _repo(tmp_path, ["One.", "Two."])
    assert len(ex.pending_paragraphs(repository)) == 2

    _memo(repository, "src-000001-p1")

    pending = ex.pending_paragraphs(repository)
    assert [p.anchor for p in pending] == ["src-000001-p2"]


def test_a_re_run_after_adding_one_record_reads_one_paragraph(tmp_path):
    """AC 2: a re-run after adding one record reads one paragraph.

    The point of memoizing per paragraph rather than per pass: ingest is
    incremental, so extraction has to be too, or every new letter costs a
    full-corpus re-read.
    """
    repository = _repo(tmp_path, ["One.", "Two."])
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}")
    assert ex.pending_paragraphs(repository) == []

    second = _record(["Three."], record_id="SRC-000002")
    write_normalized_records(
        [_record(["One.", "Two."]), second],
        tmp_path / NORMALIZED_RELATIVE_PATH,
    )
    build_index(repository, [_record(["One.", "Two."]), second])

    pending = ex.pending_paragraphs(repository)
    assert [p.anchor for p in pending] == ["src-000002-p1"]


def test_editing_a_subject_prompt_makes_every_paragraph_pending(tmp_path):
    """The other half of the key, and the price part 06 §8.1 already names."""
    repository = _repo(tmp_path, ["One.", "Two."])
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}")
    assert ex.pending_paragraphs(repository) == []

    prompt = tmp_path / "subjects" / "people" / "_subject.md"
    prompt.write_text(prompt.read_text().replace("a person.", "a person or a pet."))

    assert len(ex.pending_paragraphs(repository)) == 2


def test_reformatting_a_subject_prompt_does_not_re_read_the_corpus(tmp_path):
    """The key hashes the serialized prompt, not the file's bytes.

    Re-saving `_subject.md` with a trailing blank line is not a change to what
    the subject means, and paying a full-corpus model pass for one would make
    the author afraid of their own editor.
    """
    repository = _repo(tmp_path, ["One."])
    _memo(repository, "src-000001-p1")

    prompt = tmp_path / "subjects" / "people" / "_subject.md"
    prompt.write_text(prompt.read_text() + "\n\n")

    assert ex.pending_paragraphs(repository) == []


# --- AC 3: match terms decide, and the cache is untouched --------------------


def test_adding_a_match_term_places_the_paragraph_without_touching_the_cache(tmp_path):
    """AC 3, the whole of it.

    A placement the terms do not license is not a placement; adding the term
    makes it one, at rebuild, with no model and with the cache byte-identical
    on both sides.
    """
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _repo(tmp_path, ["Robert wrote again."], entries=[entry])
    _memo(
        repository,
        "src-000001-p1",
        placements=(_place("SUB-people/bob", "Robert"),),
    )

    ex.derive(repository)
    assert _rows(repository, "placements") == []
    before = _rows(repository, "memo")

    path = tmp_path / "subjects" / "people" / "bob.md"
    path.write_text(
        entry_to_markdown(Entry(id="SUB-people/bob", match_terms=["Robert"], body=""))
    )
    ex.derive(repository)

    placements = _rows(repository, "placements")
    assert placements == [("src-000001-p1", "SUB-people/bob", "Robert", "Robert")]
    assert _rows(repository, "memo") == before


def test_an_entry_is_licensed_by_its_own_name_without_declaring_it(tmp_path):
    """Match terms are how an entry is referenced *beyond the subject default*
    (part 06 §8.2), and the default is its own name.

    Without this an entry the author created by hand places nothing, and every
    mention of its own name comes back as a proposed match term for its own
    name.
    """
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _repo(tmp_path, ["Bob wrote again."], entries=[entry])
    _memo(repository, "src-000001-p1", placements=(_place("SUB-people/bob", "Bob"),))

    ex.derive(repository)

    assert [row[1] for row in _rows(repository, "placements")] == ["SUB-people/bob"]


def test_a_form_two_entries_both_license_is_placed_against_neither(tmp_path):
    """Part 05 §7: ambiguity is surfaced, never resolved.

    The People hazard says not to merge two people who share a name. Picking
    one here would be the misidentification the whole design is arranged
    against, so the row says so and waits for the author.
    """
    entries = [
        Entry(id="SUB-people/bob-a", match_terms=["Bob"], body=""),
        Entry(id="SUB-people/bob-b", match_terms=["Bob"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob wrote again."], entries=entries)
    _memo(repository, "src-000001-p1", unplaced=(_form("Bob"),))

    ex.derive(repository)

    assert _rows(repository, "placements") == []
    assert [row[3] for row in _rows(repository, "unplaced_forms")] == [
        ex.AMBIGUOUS_TERMS
    ]


# --- AC 4: an unlicensed placement is two rows -------------------------------


def test_an_unlicensed_placement_is_a_proposed_term_and_an_unplaced_form(tmp_path):
    """AC 4: "appears as a proposed match term on the entry **and** is
    otherwise unplaced" - two statements about two different things, so two
    rows."""
    entry = Entry(id="SUB-people/bob", match_terms=[], body="")
    repository = _repo(tmp_path, ["Robert wrote again."], entries=[entry])
    _memo(
        repository,
        "src-000001-p1",
        placements=(_place("SUB-people/bob", "Robert"),),
    )

    ex.derive(repository)

    assert _rows(repository, "proposed_match_terms") == [
        ("SUB-people/bob", "Robert", "word", 1)
    ]
    assert _rows(repository, "unplaced_forms") == [
        ("src-000001-p1", "Robert", "SUB-people", ex.UNLICENSED_PLACEMENT, "SUB-people/bob")
    ]
    assert _rows(repository, "placements") == []


def test_a_placement_against_an_entry_that_does_not_exist_is_unplaced(tmp_path):
    repository = _repo(tmp_path, ["Carol wrote again."])
    # `record_extraction` refuses a placement against an entry that does not
    # exist, so the only way to reach this state is the one that matters: the
    # entry was there during the pass and the author deleted it afterwards.
    # Written straight into the cache to stand in for that.
    con = sqlite3.connect(tmp_path / INDEX_RELATIVE_PATH)
    con.execute(
        "INSERT OR REPLACE INTO memo (key, kind, anchor, value, written_at) "
        "VALUES (?, 'paragraph', ?, ?, '')",
        (
            ex.paragraph_memo_key(
                "Carol wrote again.",
                ex.subject_prompts_digest(load_all_subjects(repository)),
            ),
            "src-000001-p1",
            json.dumps(
                {"placements": [{"entry_id": "SUB-people/carol", "surface_form": "Carol"}]}
            ),
        ),
    )
    con.commit()
    con.close()

    ex.derive(repository)

    assert [row[3] for row in _rows(repository, "unplaced_forms")] == [ex.NO_SUCH_ENTRY]


# --- AC 5: candidates and the recurrence filter ------------------------------


def test_the_recurrence_filter_defaults_to_five_and_reports_both_counts(tmp_path):
    repository = _repo(tmp_path, [f"Paragraph {n}." for n in range(6)])
    for number in range(1, 5):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))
    for number in range(1, 7):
        _memo(
            repository,
            f"src-000001-p{number}",
            unplaced=(_form("Carol"), _form("Dave")) if number < 5 else (_form("Dave"),),
        )

    counts = ex.derive(repository)

    assert counts.recurrence_threshold == 5
    assert counts.candidates_raw == 2
    assert counts.candidates_above_threshold == 1
    assert counts.per_subject["SUB-people"] == (2, 1)


def test_the_recurrence_threshold_is_configurable(tmp_path):
    repository = _repo(tmp_path, ["One.", "Two."])
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    assert ex.derive(repository).candidates_above_threshold == 0
    assert ex.derive(repository, recurrence_threshold=2).candidates_above_threshold == 1


# --- AC 9: rejected candidates and unplaced forms stay enumerable ------------


def test_a_candidate_the_filter_rejects_keeps_its_forms_and_paragraphs(tmp_path):
    """AC 9. The filter is a known miss generator (part 06 §8.4) and the only
    mitigation until ground truth exists is that the misses stay countable."""
    repository = _repo(tmp_path, ["One.", "Two."])
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    ex.derive(repository)

    candidates = _rows(repository, "candidates")
    assert len(candidates) == 1
    assert candidates[0][5] == 0, "rejected by the filter"
    assert candidates[0][4] == 2, "and its recurrence is still recorded"
    assert len(_rows(repository, "candidate_forms")) == 1
    assert len(_rows(repository, "candidate_paragraphs")) == 2


# --- AC 13: the gloss --------------------------------------------------------


def test_a_candidate_gloss_names_its_forms_and_its_relations(tmp_path):
    """AC 13: computed from rows that exist, with no model call."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _repo(tmp_path, ["Bob pressed me about the acquisition."] * 2, entries=[entry])
    for number in (1, 2):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(_place("SUB-people/bob", "Bob"),),
            unplaced=(_form("the acquisition", "SUB-events"),),
        )
    con = sqlite3.connect(tmp_path / INDEX_RELATIVE_PATH)
    con.close()

    ex.derive(repository, recurrence_threshold=1)

    glosses = {row[1]: row[3] for row in _rows(repository, "candidates")}
    assert "the acquisition" in glosses["SUB-events"]


# --- AC 6 and 8: promotion ---------------------------------------------------


def test_a_subject_declaring_auto_promote_promotes_above_the_filter(tmp_path):
    repository = _repo(
        tmp_path, [f"Paragraph {n}." for n in range(6)], auto_promote=["SUB-people"]
    )
    for number in range(1, 7):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    report = ex.finish_pass(repository)

    assert [p.entry_id for p in report.promotions] == ["SUB-people/carol"]
    assert (tmp_path / "subjects" / "people" / "carol.md").is_file()


def test_a_subject_declaring_no_creates_no_entry_without_an_author_act(tmp_path):
    """AC 6. Part 06 §8.4: nothing promotes itself unless its subject says so."""
    repository = _repo(tmp_path, [f"Paragraph {n}." for n in range(6)])
    for number in range(1, 7):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    report = ex.finish_pass(repository)

    assert report.promotions == ()
    assert not (tmp_path / "subjects" / "people" / "carol.md").exists()
    assert report.counts.per_subject["SUB-people"] == (1, 1), "still a candidate"


def test_themes_and_arcs_ship_with_auto_promote_off():
    """AC 6, third clause. A wrong Theme sits in Tier 2 and in the audit until
    somebody notices, which is why these two ship off whatever else does."""
    from memoria.subjects import BUILTIN_SUBJECTS

    off = {s.id for s in BUILTIN_SUBJECTS if not s.auto_promote}
    assert {"SUB-themes", "SUB-arcs"} <= off


def test_promoting_a_candidate_seeds_its_match_terms_from_its_surface_forms(tmp_path):
    """AC 8, first half."""
    repository = _repo(tmp_path, [f"Paragraph {n}." for n in range(3)])
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))
    ex.derive(repository, recurrence_threshold=1)
    candidate_id = _rows(repository, "candidates")[0][0]

    promotion = ex.promote_candidate(repository, candidate_id, ex.CURATOR)

    assert promotion.entry_id == "SUB-people/carol"
    assert promotion.match_terms == ("Carol",)
    assert load_all_entries(repository)["SUB-people/carol"].match_terms == ["Carol"]


def test_promoting_a_candidate_turns_its_forms_into_placements_next_rebuild(tmp_path):
    """The loop closes, and closes without a model.

    This is what makes promotion mean anything: the entry materializes with a
    gathered set already built, rather than with an empty one waiting for the
    next full pass over the archive.
    """
    repository = _repo(tmp_path, [f"Paragraph {n}." for n in range(3)])
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))
    ex.derive(repository, recurrence_threshold=1)
    assert _rows(repository, "placements") == []
    candidate_id = _rows(repository, "candidates")[0][0]

    ex.promote_candidate(repository, candidate_id, ex.CURATOR)
    counts = ex.derive(repository, recurrence_threshold=1)

    assert counts.placements == 3
    assert "SUB-people" not in counts.per_subject, "the candidate is an entry now"


def test_promotion_refuses_a_slug_the_read_side_would_reject(tmp_path):
    """The write side may not create an entry `parse_entry` cannot read back.

    `entry_slug` reaches promotion straight from the author's tool call, so
    it bypasses `entry_slug_for`; #119 made a malformed id a checked property
    on the way in, and an archive that accepted the write anyway would hold a
    file it could never serve.
    """
    repository = _repo(tmp_path, [f"Paragraph {n}." for n in range(3)])
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))
    ex.derive(repository, recurrence_threshold=1)
    candidate_id = _rows(repository, "candidates")[0][0]

    for slug in ("Bad Slug!", "carol ", "-carol", "carol/extra"):
        with pytest.raises(ex.ExtractionError, match="SUB-<subject>/<entry-slug>"):
            ex.promote_candidate(
                repository, candidate_id, ex.CURATOR, entry_slug=slug
            )

    assert list((tmp_path / "subjects" / "people").glob("*.md")) == [
        tmp_path / "subjects" / "people" / "_subject.md"
    ], "nothing was written"


def test_promoting_a_cluster_seeds_entry_references_and_relations(tmp_path):
    """AC 8, second half. A relation whose ends are both entries is
    expressible as a match term; the format decides that, not us."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob pressed about the acquisition."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-events/acquisition", "the acquisition"),
            ),
            relations=(
                ex.ProposedRelation(
                    "SUB-people/bob", "presses", "SUB-events/acquisition"
                ),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    cluster_id = _rows(repository, "clusters")[0][0]

    promotion = ex.promote_cluster(repository, cluster_id, ex.CURATOR)

    assert "SUB-people/bob" in promotion.match_terms
    assert "SUB-events/acquisition" in promotion.match_terms
    assert (
        "SUB-people/bob -> presses -> SUB-events/acquisition" in promotion.match_terms
    )


def test_promoting_a_cluster_seeds_a_candidate_member_as_a_plain_word(tmp_path):
    """The mixed case the issue's example does not cover.

    A cluster's members are entries *and* candidates - on a fresh archive they
    are all candidates - and `classify_match_term` refuses a relation whose
    ends are not entry references. A plain word is the only shape left, and it
    degrades well: the Theme gathers on the word until the author promotes that
    candidate and swaps it for a reference.
    """
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _repo(tmp_path, ["Bob pressed about the acquisition."] * 3, entries=[entry])
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(_place("SUB-people/bob", "Bob"),),
            unplaced=(_form("the acquisition", "SUB-events"),),
        )
    ex.derive(repository, recurrence_threshold=1)
    cluster_id = _rows(repository, "clusters")[0][0]

    promotion = ex.promote_cluster(repository, cluster_id, ex.CURATOR)

    assert "SUB-people/bob" in promotion.match_terms
    assert "the acquisition" in promotion.match_terms
    from memoria.subjects import classify_match_term

    assert sorted(classify_match_term(t) for t in promotion.match_terms) == [
        "entry",
        "word",
    ]


def test_a_cluster_of_many_members_still_seeds_its_relations(tmp_path):
    """AC 8, second half, at the cap. Members alone fill
    `MAX_SEEDED_MATCH_TERMS` on a big cluster; the relations that defined it
    must not be the part that falls off, and what fell off is counted."""
    names = [f"person{n:02d}" for n in range(ex.MAX_SEEDED_MATCH_TERMS + 2)]
    entries = [Entry(id=f"SUB-people/{n}", match_terms=[n], body="") for n in names]
    repository = _repo(tmp_path, ["Everyone was there."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=tuple(_place(f"SUB-people/{n}", n) for n in names),
            relations=(
                ex.ProposedRelation("SUB-people/person00", "hosts", "SUB-people/person01"),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    (cluster_id,) = {row[0] for row in _rows(repository, "clusters")}

    promotion = ex.promote_cluster(repository, cluster_id, ex.CURATOR)

    assert len(promotion.match_terms) == ex.MAX_SEEDED_MATCH_TERMS
    assert "SUB-people/person00 -> hosts -> SUB-people/person01" in promotion.match_terms
    assert promotion.dropped == len(names) + 1 - ex.MAX_SEEDED_MATCH_TERMS


def test_a_theme_is_never_placed_and_never_offered_to_the_model(tmp_path):
    """ADR-0005 decision 6: a Theme gathers by co-occurrence, over #18's join.
    A Theme named `grief` must not collect every paragraph with the word in
    it, so its name licenses nothing and the brief does not list it."""
    entries = [
        Entry(id="SUB-themes/grief", match_terms=[], body=""),
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
    ]
    repository = _repo(tmp_path, ["Grief.", "Grief again."], entries=entries)
    _memo(repository, "src-000001-p1", placements=(_place("SUB-themes/grief", "grief"),))
    _memo(repository, "src-000001-p2", unplaced=(_form("grief", ""),))

    assert [e for e, _ in ex.brief(repository).entry_names] == ["SUB-people/bob"]
    ex.derive(repository, recurrence_threshold=1)

    assert _rows(repository, "placements") == []
    assert not any(row[0] == "SUB-themes/grief" for row in _rows(repository, "proposed_match_terms"))
    assert len(_rows(repository, "unplaced_forms")) == 2


def test_candidates_unplaced_forms_and_cluster_members_are_enumerable(tmp_path):
    """AC 9 and AC 12: rows are enumerable through a reader, not only through
    SQL a test happens to write. `status` counts; these list."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="")
    repository = _repo(tmp_path, ["Bob and Carol."] * 3 + ["Zed."], entries=[entry])
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(_place("SUB-people/bob", "Bob"),),
            unplaced=(_form("Carol"),),
        )
    _memo(repository, "src-000001-p4", unplaced=(_form("Zed", ""),))
    ex.derive(repository, recurrence_threshold=5)

    (carol,) = ex.candidates(repository)
    assert (carol.label, carol.recurrence, carol.above_threshold) == ("Carol", 3, False)
    assert ex.candidates(repository, above_threshold=True) == []
    assert ex.candidates(repository, subject_id="SUB-events") == []
    assert [f.surface_form for f in ex.unplaced_forms(repository)] == ["Carol"] * 3 + ["Zed"]

    ex.derive(repository, recurrence_threshold=1)
    (cluster_id,) = {row[0] for row in _rows(repository, "clusters")}
    opened = ex.cluster_members(repository, cluster_id)

    assert opened.anchors == ("src-000001-p1", "src-000001-p2", "src-000001-p3")
    assert "SUB-people/bob" in opened.members
    assert opened.children == ()
    assert opened.summary is None
    with pytest.raises(ex.ExtractionError):
        ex.cluster_members(repository, "CL-nope")


def test_a_promoted_entry_carries_an_empty_body(tmp_path):
    """ADR-0005 build shape 2: nothing machine-written enters an entry body.
    Prose about an entry has a designed producer, and it is not this."""
    repository = _repo(tmp_path, ["Paragraph."] * 2)
    for number in (1, 2):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))
    ex.derive(repository, recurrence_threshold=1)

    ex.promote_candidate(repository, _rows(repository, "candidates")[0][0], ex.CURATOR)

    assert load_all_entries(repository)["SUB-people/carol"].body == ""


def test_running_the_pass_twice_promotes_nothing_new(tmp_path):
    repository = _repo(
        tmp_path, [f"Paragraph {n}." for n in range(6)], auto_promote=["SUB-people"]
    )
    for number in range(1, 7):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    assert len(ex.finish_pass(repository).promotions) == 1
    assert ex.finish_pass(repository).promotions == ()


def test_finish_pass_refuses_while_the_corpus_is_unread(tmp_path):
    """Nothing promotes off a partial reading of the archive: the recurrence
    filter over half a corpus is a different filter."""
    repository = _repo(tmp_path, ["One.", "Two."], auto_promote=["SUB-people"])
    _memo(repository, "src-000001-p1", unplaced=(_form("Carol"),))

    with pytest.raises(ex.ExtractionError, match="not fully extracted"):
        ex.finish_pass(repository)


def test_rebuild_never_promotes(tmp_path):
    """AC 6, mechanically. `memoria rebuild`'s contract is that everything it
    touches is disposable; it must not be making durable, committed entry
    files as a side effect. It never names `auto_promote`, and this is that
    claim under load."""
    repository = _repo(
        tmp_path, [f"Paragraph {n}." for n in range(6)], auto_promote=["SUB-people"]
    )
    for number in range(1, 7):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Carol"),))

    rebuild(repository)

    assert not (tmp_path / "subjects" / "people" / "carol.md").exists()
    assert _rows(repository, "candidates")[0][5] == 1, "above the filter, and waiting"


def test_rebuild_source_never_calls_auto_promote():
    """The structural half of the same claim, so it cannot regress quietly."""
    tree = ast.parse((SRC_ROOT / "index.py").read_text(encoding="utf-8"))
    # Names actually referenced in code, not the prose that explains why they
    # are not - the docstring says `auto_promote` on purpose.
    referenced = {
        getattr(node, "id", None) or getattr(node, "attr", None)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    assert "auto_promote" not in referenced
    assert "finish_pass" not in referenced


# --- AC 7 and 12: clusters ---------------------------------------------------


def _nested_repo(tmp_path):
    """An archive whose co-occurrence graph genuinely has two scales.

    Eight groups of three people who appear together constantly, paired up by
    a weaker link between two of their members. Louvain's own dendrogram finds
    the eight triples and then the four pairs, which is what gives clusters a
    level and a parent to carry.

    The shape matters: a "group" has to be several nodes that co-occur, not
    one node, or there is no structure at the finer grain to nest inside
    anything.
    """
    groups = 8
    paragraphs = []
    forms = []
    for group in range(groups):
        members = [f"person {group}{index}" for index in range(3)]
        for _ in range(3):
            paragraphs.append(f"Group {group} together.")
            forms.append(tuple(_form(name) for name in members))
    for group in range(0, groups, 2):
        for index in range(3):
            paragraphs.append(f"Groups {group} and {group + 1} meet.")
            forms.append(
                (
                    _form(f"person {group}{index}"),
                    _form(f"person {group + 1}{index}"),
                )
            )
    repository = _repo(tmp_path, paragraphs)
    for number, paragraph_forms in enumerate(forms, start=1):
        _memo(repository, f"src-000001-p{number}", unplaced=paragraph_forms)
    return repository


def test_clusters_nest_with_a_level_and_a_parent(tmp_path):
    """AC 12: clusters carry a level and a parent, and both a cluster's member
    paragraphs and its child clusters are enumerable."""
    repository = _nested_repo(tmp_path)

    ex.derive(repository, recurrence_threshold=1)

    clusters = _rows(repository, "clusters")
    levels = {row[1] for row in clusters}
    assert len(levels) > 1, "the hierarchy has more than one grain"

    children = [row for row in clusters if row[2]]
    assert children, "some cluster names a parent"
    child = children[0]
    parents = {row[0] for row in clusters}
    assert child[2] in parents

    con = sqlite3.connect(tmp_path / INDEX_RELATIVE_PATH)
    try:
        assert con.execute(
            "SELECT COUNT(*) FROM cluster_paragraphs WHERE cluster_id = ?", (child[0],)
        ).fetchone()[0] > 0
        assert con.execute(
            "SELECT COUNT(*) FROM clusters WHERE parent_id = ?", (child[2],)
        ).fetchone()[0] > 0
    finally:
        con.close()


def test_a_cluster_is_labelled_by_its_defining_entries_and_relations(tmp_path):
    """AC 7. The label is derived from rows, with no model - the same rule that
    glosses a candidate (ADR-0005 build shape 2)."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob pressed about the acquisition."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-events/acquisition", "the acquisition"),
            ),
            relations=(
                ex.ProposedRelation(
                    "SUB-people/bob", "presses", "SUB-events/acquisition"
                ),
            ),
        )

    ex.derive(repository, recurrence_threshold=1)

    label = _rows(repository, "clusters")[0][3]
    assert "SUB-people/bob" in label
    assert "SUB-events/acquisition" in label
    assert "presses -> SUB-events/acquisition" in label, "and in the right direction"


def test_a_fresh_archive_with_no_entries_still_proposes_clusters(tmp_path):
    """The cold start, which is every archive's first run.

    Clustering only promoted entries would give an empty graph here, and
    "clusters are proposed under Themes and Arcs" would be false on every
    archive nobody has curated yet - which is exactly the archive the feature
    is for.
    """
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    assert load_all_entries(repository) == {}
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            unplaced=(_form("Bob"), _form("the acquisition", "SUB-events")),
        )

    counts = ex.derive(repository, recurrence_threshold=1)

    assert counts.clusters >= 1


# --- AC 14 and 15: summaries -------------------------------------------------


def test_every_cluster_is_pending_a_summary_after_a_pass(tmp_path):
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)

    assert len(ex.pending_cluster_summaries(repository)) == len(
        _rows(repository, "clusters")
    )


def test_unchanged_membership_generates_no_new_summary(tmp_path):
    """AC 14: re-running with unchanged membership generates none.

    Memoized on the membership rather than on the cluster id, so a
    re-clustering that lands in the same place is a cache hit even though the
    partition was recomputed from scratch.
    """
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    for task in ex.pending_cluster_summaries(repository):
        ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")

    ex.derive(repository, recurrence_threshold=1)

    assert ex.pending_cluster_summaries(repository) == []


def test_the_summary_step_resumes_without_repeating_work(tmp_path):
    """AC 14, and the §24.3 interruption.

    A capacity limit has to be able to stop the pass anywhere and leave a
    complete extraction with a partial summary set. There is no cursor to
    lose: what is pending is a query over what is absent.
    """
    repository = _nested_repo(tmp_path)
    ex.derive(repository, recurrence_threshold=1)

    served = []
    for _ in range(3):
        task = ex.pending_cluster_summaries(repository)[0]
        served.append(task.cluster_id)
        ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")

    # The process stops here and a new one picks it up.
    while True:
        pending = ex.pending_cluster_summaries(repository)
        if not pending:
            break
        task = pending[0]
        served.append(task.cluster_id)
        ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")

    assert len(served) == len(set(served)), "no cluster was summarized twice"
    assert set(served) == {row[0] for row in _rows(repository, "clusters")}


def test_a_parent_is_not_offered_until_its_children_are_summarized(tmp_path):
    """AC 15, made structural.

    A parent's memo key is computed over its children's summary keys, so it
    cannot even be addressed until they exist. "Written from its children's
    summaries" is therefore a property of the key rather than a request the
    prompt makes.
    """
    repository = _nested_repo(tmp_path)
    ex.derive(repository, recurrence_threshold=1)
    clusters = {row[0]: row for row in _rows(repository, "clusters")}
    parents = {row[2] for row in clusters.values() if row[2]}
    assert parents

    first = ex.pending_cluster_summaries(repository)
    assert {task.cluster_id for task in first}.isdisjoint(parents)

    while ex.pending_cluster_summaries(repository):
        task = ex.pending_cluster_summaries(repository)[0]
        if task.cluster_id in parents:
            assert task.member_anchors == (), "a parent is served no paragraph text"
            assert task.child_summaries, "it is served its children's summaries"
            break
        ex.record_summary(repository, task.cluster_id, task.memo_key, "A leaf summary.")
    else:
        pytest.fail("no parent was ever offered")


def test_a_summary_recorded_against_a_stale_membership_is_refused(tmp_path):
    """Between serving a task and recording it, a rebuild may have
    re-clustered. Filing the text anyway would attach a description to
    paragraphs it is not about, and nobody would ever find out."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    task = ex.pending_cluster_summaries(repository)[0]

    with pytest.raises(ex.ExtractionError, match="re-clustered"):
        ex.record_summary(repository, task.cluster_id, "not-the-hash", "A summary.")


def test_a_cluster_with_no_summary_says_so_rather_than_making_one(tmp_path):
    """What #74's `summarize=true` serves. No adapter can call a model, so an
    absent summary is an answer."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    cluster_id = _rows(repository, "clusters")[0][0]

    assert ex.cluster_summary(repository, cluster_id) is None

    task = ex.pending_cluster_summaries(repository)[0]
    ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")
    assert ex.cluster_summary(repository, cluster_id) == "A summary."


# --- AC 10 and 11: the rebuild rule ------------------------------------------


def test_rebuild_preserves_the_memo_cache_and_drops_everything_else(tmp_path):
    """AC 11. The cache holds model output that a rebuild has no model to
    regenerate; everything else here is §42's disposable derived state."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    cache = _rows(repository, "memo")
    assert cache

    rebuild(repository, recurrence_threshold=1)

    assert _rows(repository, "memo") == cache


def test_reset_cache_is_the_one_way_to_lose_the_cache(tmp_path):
    repository = _repo(tmp_path, ["Bob."])
    _memo(repository, "src-000001-p1", unplaced=(_form("Bob"),))
    assert _rows(repository, "memo")

    rebuild(repository, reset_cache=True)

    assert _rows(repository, "memo") == []


def test_derived_state_regenerates_identically_from_the_cache(tmp_path):
    """AC 10. Scoped to one process on purpose: clustering is deterministic
    under a fixed seed *and* a fixed backend, and a machine with the Leiden
    wheel will not agree with one without it. That is why the backend is
    recorded rather than assumed."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 4)
    for number in (1, 2, 3, 4):
        _memo(
            repository,
            f"src-000001-p{number}",
            unplaced=(_form("Bob"), _form("the acquisition", "SUB-events")),
        )
    rebuild(repository, recurrence_threshold=1)
    before = {table: _rows(repository, table) for table in DERIVED_TABLES}

    rebuild(repository, recurrence_threshold=1)

    for table in DERIVED_TABLES:
        assert _rows(repository, table) == before[table], table


def test_build_index_alone_leaves_the_derived_tables_empty(tmp_path):
    """The tables really are dropped, rather than being written over in place
    - which is the difference between a rebuild and an update."""
    repository = _repo(tmp_path, ["Bob."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    assert _rows(repository, "candidates")

    build_index(repository, [_record(["Bob."] * 3)])

    assert _rows(repository, "candidates") == []
    assert _rows(repository, "memo"), "but not the cache"


def test_the_pass_runs_on_a_repository_with_no_index_built(tmp_path):
    """`memoria rebuild` may never have been run here.

    The extraction reads record files, not the index, so there is no reason it
    should need one - and the skill's very first call is a status. Without the
    tables being created on open, that call came back as a bare SQL error the
    session had no way to act on.
    """
    repository = Repository(root=tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_builtin_subjects(repository)
    write_normalized_records(
        [_record(["Bob and the acquisition."] * 3)],
        tmp_path / NORMALIZED_RELATIVE_PATH,
    )
    assert not (tmp_path / INDEX_RELATIVE_PATH).exists()

    assert ex.status(repository).pending == 3
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))

    counts = ex.derive(repository, recurrence_threshold=1)

    assert counts.candidates_above_threshold == 1
    assert ex.pending_cluster_summaries(repository)


# --- #74: search_global -------------------------------------------------------


def test_search_global_groups_matched_paragraphs_by_cluster_with_a_scope_line(tmp_path):
    """AC 1 and AC 5: references grouped by cluster, feeding `read(ref)`
    verbatim, under a §33-style scope line - exercised over the core alone,
    with no MCP server in the loop."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    repository = _repo(
        tmp_path,
        ["Bob pressed about the acquisition."] * 3,
        entries=entries,
        event_date="2011-06-01",
    )
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-events/acquisition", "the acquisition"),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    (cluster_id, level, *_rest) = _rows(repository, "clusters")[0]
    assert len(_rows(repository, "clusters")) == 1, "two nodes nest no further"

    result = ex.search_global(repository, "acquisition")

    assert len(result.groups) == 1
    group = result.groups[0]
    assert group.cluster_id == cluster_id
    assert {(r.src_id, r.anchor) for r in group.results} == {
        ("SRC-000001", f"src-000001-p{n}") for n in (1, 2, 3)
    }
    assert result.scope == (
        f"clustered 3 paragraphs across 2011; 1 cluster matched at level {level}"
    )


def test_search_global_a_promoted_cluster_routes_to_the_entry_not_its_stale_label(
    tmp_path,
):
    """AC 2, part 06 §8.4 and ADR-0005 decision 6."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob pressed about the acquisition."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-events/acquisition", "the acquisition"),
            ),
            relations=(
                ex.ProposedRelation(
                    "SUB-people/bob", "presses", "SUB-events/acquisition"
                ),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    cluster_id = _rows(repository, "clusters")[0][0]
    promotion = ex.promote_cluster(repository, cluster_id, ex.CURATOR)

    result = ex.search_global(repository, "acquisition")

    assert len(result.groups) == 1
    assert result.groups[0].entry_id == promotion.entry_id


def test_search_global_an_unpromoted_cluster_shows_its_own_label(tmp_path):
    """The common case, and every case before the first promotion."""
    entries = [Entry(id="SUB-people/bob", match_terms=["Bob"], body="")]
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(_place("SUB-people/bob", "Bob"),),
            unplaced=(_form("the acquisition", "SUB-events"),),
        )
    ex.derive(repository, recurrence_threshold=1)

    result = ex.search_global(repository, "acquisition")

    assert result.groups[0].entry_id is None
    assert result.groups[0].label


def test_search_global_routing_degrades_once_the_entrys_terms_are_edited_away(
    tmp_path,
):
    """Documented rather than hidden: ADR-0005 decision 6 says a promoted
    entry never points back at its cluster, so once the author tunes the
    Theme past what the cluster itself still defines, `search_global` can no
    longer read the link back off its terms - the declared cost of rejecting
    a durable pointer."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-events/acquisition", match_terms=["the acquisition"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob pressed about the acquisition."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-events/acquisition", "the acquisition"),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    cluster_id = _rows(repository, "clusters")[0][0]
    promotion = ex.promote_cluster(repository, cluster_id, ex.CURATOR)
    (tmp_path / promotion.path).write_text(
        entry_to_markdown(
            Entry(id=promotion.entry_id, match_terms=["a new idea"], body="")
        )
    )

    result = ex.search_global(repository, "acquisition")

    assert result.groups[0].entry_id is None


def test_search_global_a_hand_authored_theme_does_not_capture_an_unrelated_cluster(
    tmp_path,
):
    """Review round 1, finding 1. One-way containment - an entry's terms are
    a subset of the cluster's - is not enough: a hand-authored Theme naming
    just one of several co-occurring people is a subset of that whole
    cluster too, and was wrongly routing to it. Nothing here calls
    `promote_cluster` at all - `SUB-themes/hand-written` is author-created,
    part 06 §8.4's other route to an entry."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-people/carol", match_terms=["Carol"], body=""),
        Entry(id="SUB-themes/hand-written", match_terms=["SUB-people/bob"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob and Carol talked."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(
            repository,
            f"src-000001-p{number}",
            placements=(
                _place("SUB-people/bob", "Bob"),
                _place("SUB-people/carol", "Carol"),
            ),
        )
    ex.derive(repository, recurrence_threshold=1)
    assert len(_rows(repository, "clusters")) == 1, "two nodes nest no further"

    result = ex.search_global(repository, "Bob")

    assert result.groups[0].entry_id is None


def test_search_global_routes_the_earliest_entry_deterministically_on_a_tie(
    tmp_path,
):
    """Review round 1, finding 4. Two entries with the identical term set
    collide on the same routing-table key; `_theme_routes` must resolve that
    deterministically rather than however dict insertion happens to land."""
    entries = [
        Entry(id="SUB-people/bob", match_terms=["Bob"], body=""),
        Entry(id="SUB-themes/z-later", match_terms=["SUB-people/bob"], body=""),
        Entry(id="SUB-themes/a-earlier", match_terms=["SUB-people/bob"], body=""),
    ]
    repository = _repo(tmp_path, ["Bob alone."] * 3, entries=entries)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", placements=(_place("SUB-people/bob", "Bob"),))
    ex.derive(repository, recurrence_threshold=1)

    result = ex.search_global(repository, "Bob")

    assert result.groups[0].entry_id == "SUB-themes/a-earlier"


def _nested_entry_repo(tmp_path):
    """`_nested_repo` (above), but every node is a promoted entry reached
    through a real placement rather than a candidate. Needed here because a
    cluster of candidates seeds only plain words on promotion (`promote_cluster`),
    which never route at all - this fixture is what lets a promotion seed
    entry references instead, so the ancestor-leak in finding 2 is
    reproducible."""
    groups = 8
    names = [f"person{group}{index}" for group in range(groups) for index in range(3)]
    entries = [Entry(id=f"SUB-people/{n}", match_terms=[n], body="") for n in names]
    paragraphs = []
    placements = []
    for group in range(groups):
        members = [f"person{group}{index}" for index in range(3)]
        for _ in range(3):
            paragraphs.append(f"Group {group} together.")
            placements.append(
                tuple(_place(f"SUB-people/{m}", m) for m in members)
            )
    for group in range(0, groups, 2):
        for index in range(3):
            paragraphs.append(f"Groups {group} and {group + 1} meet.")
            placements.append(
                (
                    _place(f"SUB-people/person{group}{index}", f"person{group}{index}"),
                    _place(
                        f"SUB-people/person{group + 1}{index}",
                        f"person{group + 1}{index}",
                    ),
                )
            )
    repository = _repo(tmp_path, paragraphs, entries=entries)
    for number, paragraph_placements in enumerate(placements, start=1):
        _memo(repository, f"src-000001-p{number}", placements=paragraph_placements)
    return repository


def test_search_global_a_promoted_cluster_does_not_leak_to_its_coarser_ancestor(
    tmp_path,
):
    """Review round 1, finding 2. A coarser level's members are always a
    superset of a finer one's (`clustering.py`), so one-way containment let a
    fine cluster's promotion falsely capture its own broader ancestor too -
    reproduced here by promoting the finest cluster and checking its parent
    at the coarser level stays unrouted."""
    repository = _nested_entry_repo(tmp_path)
    ex.derive(repository, recurrence_threshold=1)
    rows = _rows(repository, "clusters")
    finest = max(row[1] for row in rows)
    fine_id, fine_level, fine_parent = next(
        (row[0], row[1], row[2]) for row in rows if row[1] == finest and row[2]
    )
    parent_level = next(row[1] for row in rows if row[0] == fine_parent)
    assert parent_level != fine_level

    promotion = ex.promote_cluster(repository, fine_id, ex.CURATOR)

    fine_result = ex.search_global(repository, None, SearchFilters(level=fine_level))
    fine_group = next(g for g in fine_result.groups if g.cluster_id == fine_id)
    assert fine_group.entry_id == promotion.entry_id, "the real origin still routes"

    coarse_result = ex.search_global(
        repository, None, SearchFilters(level=parent_level)
    )
    coarse_group = next(g for g in coarse_result.groups if g.cluster_id == fine_parent)
    assert coarse_group.entry_id is None, "the ancestor must not inherit the route"


def test_search_global_summarize_false_never_carries_a_summary(tmp_path):
    """AC 3: `summarize=false` returns none, even when one has been written."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)
    task = ex.pending_cluster_summaries(repository)[0]
    ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")

    result = ex.search_global(repository, "Bob", summarize=False)

    assert all(group.summary is None for group in result.groups)
    assert result.summary_served is False


def test_search_global_summarize_true_serves_memoized_text_or_says_none_yet(
    tmp_path,
):
    """AC 3 and AC 8: served, never generated - a cluster with no summary
    says so, and there is no model anywhere in this call to make one."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)

    unsummarized = ex.search_global(repository, "Bob", summarize=True)
    assert unsummarized.groups[0].summary is None
    assert unsummarized.summary_served is False

    task = ex.pending_cluster_summaries(repository)[0]
    ex.record_summary(repository, task.cluster_id, task.memo_key, "A summary.")

    summarized = ex.search_global(repository, "Bob", summarize=True)
    assert summarized.groups[0].summary == "A summary."
    assert summarized.summary_served is True


def test_search_global_with_no_query_returns_every_cluster_at_the_requested_level(
    tmp_path,
):
    """AC 6 and AC 7: `search_global(query=None, filters={level: n})` is the
    map step - every cluster at that level, with its summary, under a scope
    line naming the level."""
    repository = _nested_repo(tmp_path)
    ex.derive(repository, recurrence_threshold=1)
    rows = _rows(repository, "clusters")
    finest = max(row[1] for row in rows)
    expected = {row[0] for row in rows if row[1] == finest}

    result = ex.search_global(
        repository, None, SearchFilters(level=finest), summarize=True
    )

    assert {group.cluster_id for group in result.groups} == expected
    assert f"level {finest}" in result.scope
    assert all(group.level == finest for group in result.groups)


def test_search_global_defaults_to_the_finest_level_and_always_names_it(tmp_path):
    """§33.1's discipline applied here: a call that leaves `level` unset still
    resolves one, and it is never left for the caller to infer."""
    repository = _nested_repo(tmp_path)
    ex.derive(repository, recurrence_threshold=1)
    finest = max(row[1] for row in _rows(repository, "clusters"))

    result = ex.search_global(repository, None)

    assert result.level == finest
    assert f"level {finest}" in result.scope


def test_search_global_filters_narrow_the_matched_paragraphs(tmp_path):
    """The other six `SearchFilters` narrow query mode exactly as they narrow
    `search` (#12) - proven with one guaranteed to exclude everything, since
    the compose logic itself is `index.filter_predicate`'s own test coverage."""
    repository = _repo(tmp_path, ["Bob and the acquisition."] * 3)
    for number in (1, 2, 3):
        _memo(repository, f"src-000001-p{number}", unplaced=(_form("Bob"),))
    ex.derive(repository, recurrence_threshold=1)

    result = ex.search_global(repository, "Bob", SearchFilters(contemporaneous=False))

    assert result.groups == ()


def test_search_global_over_a_missing_index_returns_no_groups(tmp_path):
    """Matches `search` and `gather`: the corpus not being built is an
    answer, not a driver exception, and nothing here creates the file."""
    repository = Repository(root=tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    result = ex.search_global(repository, "anything")

    assert result.groups == ()
    assert "0 clusters matched" in result.scope
    assert not (tmp_path / INDEX_RELATIVE_PATH).exists()
