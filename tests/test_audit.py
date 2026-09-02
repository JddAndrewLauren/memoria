"""Memoized judgements and the staleness map (#37, part 06 §8.12).

Covers the acceptance criteria: both key compositions, hash-comparison-only
staleness with no model reachable, the whole-manuscript map, the five
distinguishable causes, a subject-prompt edit staling every paragraph judged
under it, an ingest that moves a gathered set staling only the affected audit
verdicts (never the engagement judgements sharing the same paragraph), and
`memoria rebuild` deriving the map.
"""

import ast
import sqlite3
from pathlib import Path

import pytest

from memoria.audit import (
    ManuscriptParagraph,
    StalenessMap,
    audit_verdict_key,
    compute_staleness_map,
    engagement_key,
    entry_hash,
    gathered_set_hash,
    manuscript_paragraphs,
    record_audit_verdict,
    record_engagement,
    subject_hash,
)
from memoria.index import build_index, rebuild
from memoria.manuscript import create_chapter, create_section
from memoria.records import NormalizedRecord, write_normalized_records
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import Repository
from memoria.subjects import (
    BUILTIN_SUBJECTS,
    Entry,
    entry_to_markdown,
    load_subject,
    subject_path,
    subject_to_markdown,
    write_builtin_subjects,
)

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _section(repository: Repository, *, brief_text: str, draft: str):
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, brief_text)
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    return chapter, section


def _record(record_id, paragraphs):
    return NormalizedRecord(
        id=record_id,
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="unresolved",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=paragraphs,
    )


def _basic_repo(tmp_path, *, entry: Entry, brief_text: str, draft: str):
    """A repository carrying the built-in subjects, one entry, and one
    section whose brief resolves to that entry and whose draft.md holds
    ``draft`` - the minimum every test below builds on."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, entry)
    _section(repository, brief_text=brief_text, draft=draft)
    return repository


# --- AC: no model is reachable ------------------------------------------------


def test_no_core_module_imports_a_model_client():
    """AC: not-current is a hash comparison, no model call. Mirrors
    `test_extraction.py`'s AST sweep, which already covers this file too -
    kept here as well so the claim is checked from `audit.py`'s own tests."""
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib", "socket"}
    tree = ast.parse((SRC_ROOT / "audit.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] not in forbidden


def test_computing_the_staleness_map_opens_no_socket_and_leaves_no_process(
    tmp_path, monkeypatch
):
    """The real half of the claim: driving the whole map computation to
    completion with sockets and subprocesses made to raise."""
    import socket
    import subprocess

    def _blocked(*args, **kwargs):
        raise AssertionError("staleness map computation touched the network")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)
    monkeypatch.setattr(subprocess, "Popen", _blocked)

    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    staleness = compute_staleness_map(repository)

    assert isinstance(staleness, StalenessMap)


# --- AC: both key compositions ------------------------------------------------


def test_engagement_key_depends_on_all_three_inputs():
    base = engagement_key("p", "e", "s")
    assert engagement_key("p2", "e", "s") != base
    assert engagement_key("p", "e2", "s") != base
    assert engagement_key("p", "e", "s2") != base
    assert engagement_key("p", "e", "s") == base


def test_audit_verdict_key_carries_a_fourth_gathered_set_hash():
    base = audit_verdict_key("p", "e", "s", "g")
    assert audit_verdict_key("p", "e", "s", "g2") != base
    # And otherwise agrees with nothing an engagement key produces - the two
    # kinds never collide even given identical component hashes.
    assert audit_verdict_key("p", "e", "s", "g") != engagement_key("p", "e", "s")


def test_entry_hash_ignores_open_lines():
    """Part 06 §8.12: "`[open]` lines ... sit outside it [the audit-visible
    body]" - appending one must not move the entry's contribution to the
    key, so it invalidates nothing."""
    before = Entry(id="SUB-people/bob", body="Bob is tall.")
    after = Entry(
        id="SUB-people/bob", body="Bob is tall.\n\n[open] Maybe he isn't."
    )
    assert entry_hash(before) == entry_hash(after)


def test_entry_hash_moves_when_visible_testimony_changes():
    before = Entry(id="SUB-people/bob", body="Bob is tall.")
    after = Entry(id="SUB-people/bob", body="Bob is short.")
    assert entry_hash(before) != entry_hash(after)


def test_subject_hash_moves_when_the_prompt_changes():
    subject = BUILTIN_SUBJECTS[0]
    edited = subject.__class__(
        id=subject.id,
        match=subject.match,
        hazards=subject.hazards + " Also: do not trust nicknames.",
        audit_questions=subject.audit_questions,
        auto_promote=subject.auto_promote,
    )
    assert subject_hash(subject) != subject_hash(edited)


# --- manuscript paragraphs, read fresh, no durable id -------------------------


def test_manuscript_paragraphs_splits_on_blank_lines(tmp_path):
    repository = _repo(tmp_path)
    _section(
        repository,
        brief_text="About nothing in particular.",
        draft="First paragraph.\n\nSecond paragraph,\nstill one paragraph.\n",
    )

    paragraphs = manuscript_paragraphs(repository)

    assert [p.text for p in paragraphs] == [
        "First paragraph.",
        "Second paragraph,\nstill one paragraph.",
    ]
    assert paragraphs[0].slot == "01/01#1"
    assert paragraphs[1].slot == "01/01#2"


def test_a_section_with_no_draft_contributes_no_paragraphs(tmp_path):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "A chapter.")
    create_section(repository, chapter.number, "A planned section.")

    assert manuscript_paragraphs(repository) == []
    assert compute_staleness_map(repository).not_current == ()


# --- the staleness map, current vs. not current -------------------------------


def _only_entry_id(entry: Entry) -> str:
    return entry.id


def test_a_paragraph_never_judged_is_never_audited(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    staleness = compute_staleness_map(repository)

    kinds = {(item.kind, item.cause) for item in staleness.not_current}
    assert kinds == {("engagement", "never_audited"), ("audit_verdict", "never_audited")}
    assert staleness.paragraphs_not_current == 1
    assert all(item.entry_id == "SUB-people/bob" for item in staleness.not_current)


def test_recording_both_judgements_makes_the_paragraph_current(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]

    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    assert compute_staleness_map(repository).not_current == ()


def test_a_paragraph_outside_the_sections_declared_scope_is_never_checked(tmp_path):
    """The audit is bounded by `resolve_scope` (#36): an entry the brief
    never names contributes no judgement at all, current or not."""
    entry = Entry(id="SUB-people/carol", match_terms=["Carol"], body="")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    staleness = compute_staleness_map(repository)

    assert staleness.not_current == ()


def test_editing_the_paragraph_stales_both_judgements(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    (repository.root / "chapters" / "01" / "sections" / "01" / "draft.md").write_text(
        "Bob went to the capital instead.", encoding="utf-8"
    )

    staleness = compute_staleness_map(repository)
    causes = {item.cause for item in staleness.not_current}
    assert causes == {"paragraph_edited"}
    assert len(staleness.not_current) == 2  # both kinds, same paragraph


def test_editing_the_entry_stales_both_judgements_for_it(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    _write_entry(
        repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is short.")
    )

    staleness = compute_staleness_map(repository)
    causes = {item.cause for item in staleness.not_current}
    assert causes == {"entry_changed"}
    assert len(staleness.not_current) == 2


def test_changing_a_subject_prompt_stales_every_paragraph_judged_under_it(tmp_path):
    """AC: a test changes a subject prompt and asserts every paragraph
    judged under it becomes not current - and that an entry under an
    untouched subject is left alone."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    carol = Entry(id="SUB-people/carol", match_terms=["Carol"], body="Carol is short.")
    control_theme = Entry(id="SUB-themes/control", match_terms=["Control"], body="About control.")
    _write_entry(repository, bob)
    _write_entry(repository, carol)
    _write_entry(repository, control_theme)
    _section(
        repository,
        brief_text="About Bob, Carol, and Control.",
        draft="Bob and Carol discuss control.",
    )
    paragraph = manuscript_paragraphs(repository)[0]
    for entry_id in ("SUB-people/bob", "SUB-people/carol", "SUB-themes/control"):
        record_engagement(repository, paragraph, entry_id, {"engages": True})
        record_audit_verdict(repository, paragraph, entry_id, {"clear": True})
    assert compute_staleness_map(repository).not_current == ()

    people_subject = load_subject(repository, "SUB-people")
    edited = people_subject.__class__(
        id=people_subject.id,
        match=people_subject.match,
        hazards=people_subject.hazards + " Do not trust nicknames either.",
        audit_questions=people_subject.audit_questions,
        auto_promote=people_subject.auto_promote,
    )
    subject_path(repository, "SUB-people").write_text(
        subject_to_markdown(edited), encoding="utf-8"
    )

    staleness = compute_staleness_map(repository)
    affected_entries = {item.entry_id for item in staleness.not_current}
    assert affected_entries == {"SUB-people/bob", "SUB-people/carol"}
    assert {item.cause for item in staleness.not_current} == {"subject_changed"}
    # Control belongs to SUB-themes, untouched, and stays current.
    assert not any(item.entry_id == "SUB-themes/control" for item in staleness.not_current)


def test_ingest_that_moves_a_gathered_set_stales_only_the_audit_verdict(tmp_path):
    """AC: ingest that moves a gathered set stales the affected audit
    verdicts, attributable to that cause - and never the engagement
    judgement over the same paragraph and entry, which does not depend on
    evidence (part 06 §8.12: "never its engagement judgements")."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    record = _record("SRC-000001", ["Bob mentioned here."])
    write_normalized_records([record], repository.root / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    assert gathered_set_hash(repository, "SUB-people/bob") != ""

    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})
    assert compute_staleness_map(repository).not_current == ()

    # Ingest a second source that also names Bob - the gathered set moves.
    second = _record("SRC-000002", ["Bob again, elsewhere."])
    write_normalized_records(
        [record, second], repository.root / NORMALIZED_RELATIVE_PATH
    )
    build_index(repository, [record, second], reset_cache=False)

    staleness = compute_staleness_map(repository)
    assert [(item.kind, item.cause) for item in staleness.not_current] == [
        ("audit_verdict", "gathered_set_changed")
    ]


def test_count_by_cause_and_paragraphs_not_current(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path,
        entry=entry,
        brief_text="About Bob.",
        draft="Bob went to town.\n\nBob came home.",
    )

    staleness = compute_staleness_map(repository)

    assert staleness.paragraphs_not_current == 2
    assert staleness.count_by_cause() == {"never_audited": 4}  # 2 paragraphs x 2 kinds


# --- AC: the map is derived and rebuilt by `memoria rebuild` -----------------


def test_rebuild_derives_the_staleness_map(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    report = rebuild(repository)

    assert isinstance(report.staleness, StalenessMap)
    assert report.staleness.paragraphs_not_current == 1

    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    report = rebuild(repository)
    assert report.staleness.not_current == ()


# --- an index built before #37 ------------------------------------------------


def test_a_memo_table_built_before_37_is_migrated_not_refused(tmp_path):
    """`memo` is preserved across rebuilds and created with `IF NOT EXISTS`,
    so an index from before #37 keeps the old two-kind CHECK constraint
    forever unless something rewrites the table. Recording a judgement
    against it must succeed, and the extraction's paid-for rows must
    survive the rewrite untouched."""
    from memoria.index import INDEX_RELATIVE_PATH

    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    build_index(repository, [])
    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    con.execute("DROP INDEX IF EXISTS memo_kind_anchor")
    con.execute("DROP TABLE memo")
    con.execute(
        "CREATE TABLE memo("
        "key TEXT PRIMARY KEY, "
        "kind TEXT NOT NULL CHECK (kind IN ('paragraph', 'cluster_summary')), "
        "anchor TEXT NOT NULL DEFAULT '', "
        "value TEXT NOT NULL, "
        "written_at TEXT NOT NULL"
        ")"
    )
    con.execute("CREATE INDEX memo_kind_anchor ON memo(kind, anchor)")
    con.execute(
        "INSERT INTO memo (key, kind, anchor, value, written_at) "
        "VALUES ('old-key', 'paragraph', 'src-000001-p1', '{}', '2026-01-01T00:00:00')"
    )
    con.commit()
    con.close()
    paragraph = manuscript_paragraphs(repository)[0]

    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", {"clear": True})

    con = sqlite3.connect(repository.root / INDEX_RELATIVE_PATH)
    try:
        assert con.execute(
            "SELECT value FROM memo WHERE key = 'old-key'"
        ).fetchone() == ("{}",)
        kinds = {row[0] for row in con.execute("SELECT kind FROM memo")}
        assert kinds == {"paragraph", "engagement", "audit_verdict"}
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'memo_kind_anchor'"
        ).fetchone() is not None
    finally:
        con.close()
    assert compute_staleness_map(repository).not_current == ()
