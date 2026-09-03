"""Memoized judgements and the staleness map (#37), and the audit itself, on
demand only (#40, part 06 §8.10-§8.12).

Covers #37's acceptance criteria: both key compositions, hash-comparison-only
staleness with no model reachable, the whole-manuscript map, the five
distinguishable causes, a subject-prompt edit staling every paragraph judged
under it, an ingest that moves a gathered set staling only the affected audit
verdicts (never the engagement judgements sharing the same paragraph), and
`memoria rebuild` deriving the map.

And #40's: an audit target is reached only by something naming it explicitly
(never a scheduled or ingest-triggered path); the questions asked are the
subjects' own, through the one scope resolver; a finding is a disagreement
set with no category, and its resolutions are read from the set's shape;
impact analysis is the same code path as the audit, not a second one; the
model-engine appearances for Themes and Arcs are memoized, not computed
fresh; a conflict with author testimony is served as policy for the model to
report as a disagreement, never as an error; and no finding-resolution path
can write a brief.
"""

import ast
import sqlite3
from pathlib import Path

import pytest

from memoria.audit import (
    AuditRecordOutcome,
    AuditTask,
    AUTHOR_TESTIMONY_POLICY,
    DisagreementMember,
    Finding,
    ManuscriptParagraph,
    ModelAppearance,
    RecordedAuditItem,
    RecordedDisagreementMember,
    RecordedFinding,
    StalenessMap,
    UnresolvableDisagreementShape,
    audit_tasks_for_target,
    audit_verdict_key,
    clear_verdict,
    compute_staleness_map,
    engagement_key,
    entry_hash,
    finding_from_verdict,
    finding_verdict,
    findings_in_scope,
    gathered_set_hash,
    manuscript_paragraphs,
    model_engine_appearances,
    paragraph_at,
    pending_for_target,
    record_audit_batch,
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


# --- AC: on demand only, never scheduled or ingest-triggered (#40) -----------


def test_the_writing_functions_are_reachable_only_from_audit_py_and_the_mcp_server():
    """AC: nothing triggers an audit automatically. `record_engagement`,
    `record_audit_verdict` and `record_audit_batch` are the only functions
    that ever cache a judgement, and a call to one of them appears nowhere
    in the shipped source but here (where they are defined) and in the MCP
    server's audit tools (`audit_pending`/`audit_record`) - never in ingest
    (`memoria.index`), the extraction pass, the CLI, or the record
    extractor. `memoria.index.rebuild` calling the *read-only*
    `compute_staleness_map` is a different function and is unaffected."""
    writing_functions = {"record_engagement", "record_audit_verdict", "record_audit_batch"}
    allowed_files = {"audit.py", "server.py"}
    for path in SRC_ROOT.rglob("*.py"):
        if path.name in allowed_files:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            assert name not in writing_functions, (
                f"{path}: calls {name}(), which must only ever run from an "
                "explicit audit request"
            )


def test_no_scheduler_or_background_task_infrastructure_exists():
    """AC: nothing schedules an audit - there is no cron, timer, or
    background-task machinery anywhere in the shipped source for a future
    caller to hook one into."""
    forbidden = (
        "apscheduler",
        "croniter",
        "BackgroundTasks",
        "threading.Timer",
        "asyncio.create_task",
        "celery",
    )
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in text, f"{path.name} references {term!r}"


def test_audit_py_imports_no_brief_writing_function():
    """AC: no finding-resolution path can write a brief. This module never
    imports `write_brief`, `confirm_brief`, or any of the brief creators -
    structural, not a rule a caller has to remember (part 06 §8.10: "a
    brief is never edited from a finding card")."""
    tree = ast.parse((SRC_ROOT / "audit.py").read_text(encoding="utf-8"))
    forbidden = {
        "write_brief",
        "confirm_brief",
        "create_book",
        "create_chapter",
        "create_section",
        "_write_brief_file",
        "reorder_chapters",
        "reorder_sections",
    }
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "memoria.manuscript":
            imported.update(alias.name for alias in node.names)
    assert not (imported & forbidden), imported & forbidden


# --- an on-demand target, and the paragraph lookup it needs -------------------


def test_pending_for_target_scopes_to_chapter_section_or_passage(tmp_path):
    """AC: an audit runs from an explicit act on a section, a chapter or a
    highlighted passage. `pending_for_target` reads the whole-manuscript
    staleness map and narrows it; the count shrinks with each added
    constraint and never grows."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    _write_entry(repository, entry)

    chapter1 = create_chapter(repository, "Chapter one.")
    section1 = create_section(repository, chapter1.number, "About Bob.")
    (section1.dir / "draft.md").write_text(
        "Bob went to town.\n\nBob came home.", encoding="utf-8"
    )
    section2 = create_section(repository, chapter1.number, "Also about Bob.")
    (section2.dir / "draft.md").write_text("Bob left again.", encoding="utf-8")

    chapter2 = create_chapter(repository, "Chapter two.")
    section3 = create_section(repository, chapter2.number, "Still about Bob.")
    (section3.dir / "draft.md").write_text("Bob wrote a letter.", encoding="utf-8")

    everything = pending_for_target(repository)
    chapter_only = pending_for_target(repository, chapter_number=chapter1.number)
    section_only = pending_for_target(
        repository, chapter_number=chapter1.number, section_number=section1.number
    )
    passage_only = pending_for_target(
        repository,
        chapter_number=chapter1.number,
        section_number=section1.number,
        paragraph_index=2,
    )

    assert len(everything) > len(chapter_only) > len(section_only) > len(passage_only)
    assert all(i.chapter_number == chapter1.number for i in chapter_only)
    assert all(i.section_number == section1.number for i in section_only)
    assert all(i.paragraph_index == 2 for i in passage_only)


def test_pending_for_target_rejects_a_passage_without_a_section(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(ValueError):
        pending_for_target(repository, paragraph_index=1)


def test_pending_for_target_rejects_a_section_without_a_chapter(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(ValueError):
        pending_for_target(repository, section_number=1)


def test_paragraph_at_finds_by_position_and_none_when_gone(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    found = paragraph_at(repository, 1, 1, 1)

    assert found is not None
    assert found.text == "Bob went to town."
    assert paragraph_at(repository, 1, 1, 2) is None
    assert paragraph_at(repository, 9, 9, 9) is None


# --- AC: the audit asks the subjects' own questions, through the scope
# resolver ---------------------------------------------------------------


def test_audit_tasks_for_target_carries_the_subjects_own_questions(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )

    tasks = audit_tasks_for_target(repository, chapter_number=1, section_number=1)

    assert {t.kind for t in tasks} == {"engagement", "audit_verdict"}
    people_subject = load_subject(repository, "SUB-people")
    verdict_task = next(t for t in tasks if t.kind == "audit_verdict")
    assert verdict_task.subject_prompt == people_subject.audit_questions
    assert verdict_task.entry_audit_visible_body == "Bob is tall."
    assert verdict_task.paragraph_text == "Bob went to town."
    assert verdict_task.entry_id == "SUB-people/bob"
    engagement_task = next(t for t in tasks if t.kind == "engagement")
    assert people_subject.match in engagement_task.subject_prompt
    assert people_subject.hazards in engagement_task.subject_prompt


def test_audit_tasks_carry_the_gathered_set_for_an_audit_verdict_task_only(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    record = _record("SRC-000001", ["Bob mentioned here."])
    write_normalized_records([record], repository.root / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])

    tasks = audit_tasks_for_target(repository, chapter_number=1, section_number=1)

    verdict_task = next(t for t in tasks if t.kind == "audit_verdict")
    assert verdict_task.gathered_anchors
    engagement_task = next(t for t in tasks if t.kind == "engagement")
    assert engagement_task.gathered_anchors == ()


def test_audit_tasks_for_target_is_bounded_by_the_scope_resolver(tmp_path):
    """AC: bounded by the entries the section's brief resolves to, through
    the one scope resolver - an entry the brief never names is never
    served, current or not."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    carol = Entry(id="SUB-people/carol", match_terms=["Carol"], body="Carol is short.")
    _write_entry(repository, bob)
    _write_entry(repository, carol)
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text("Bob went to town.", encoding="utf-8")

    tasks = audit_tasks_for_target(repository, chapter_number=chapter.number, section_number=section.number)

    assert all(t.entry_id == "SUB-people/bob" for t in tasks)


# --- findings: disagreement sets, no category (#40, part 06 §8.10) -----------


def test_finding_resolutions_are_read_from_the_disagreement_sets_shape():
    passage_source = Finding(
        disagreement_set=(
            DisagreementMember("passage", "01/01#1"),
            DisagreementMember("source", "src-000001-p1"),
        ),
        statement="disagreement",
        confidence="high",
        subject_id="SUB-people",
    )
    assert passage_source.available_resolutions == (
        "rewrite the passage",
        "exclude the source",
    )

    passage_entry_source = Finding(
        disagreement_set=(
            DisagreementMember("passage", "01/01#1"),
            DisagreementMember("entry", "SUB-people/bob"),
            DisagreementMember("source", "src-000001-p1"),
        ),
        statement="disagreement",
        confidence="moderate",
        subject_id="SUB-people",
    )
    assert len(passage_entry_source.available_resolutions) == 3


def test_a_disagreement_set_naming_a_brief_never_offers_a_rewrite_of_it():
    """AC: no finding-resolution path can write a brief - the one row that
    can name a brief offers a conversation, never an edit."""
    passage_brief = Finding(
        disagreement_set=(
            DisagreementMember("passage", "01/01#1"),
            DisagreementMember("brief", "SEC-0001"),
        ),
        statement="disagreement",
        confidence="low",
        subject_id="SUB-themes",
    )
    resolutions = passage_brief.available_resolutions
    assert "open a conversation about the brief" in resolutions
    assert not any(
        "update the brief" in r or "rewrite the brief" in r or "edit the brief" in r
        for r in resolutions
    )


def test_a_disagreement_set_with_no_declared_shape_is_refused_loudly():
    finding = Finding(
        disagreement_set=(DisagreementMember("entry", "SUB-people/bob"),),
        statement="malformed",
        confidence="low",
        subject_id="SUB-people",
    )
    with pytest.raises(UnresolvableDisagreementShape):
        finding.available_resolutions
    with pytest.raises(UnresolvableDisagreementShape):
        finding_verdict(finding)


def test_clear_and_finding_verdicts_round_trip_through_the_memo_value():
    assert finding_from_verdict(clear_verdict()) is None

    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", "01/01#1"),
            DisagreementMember("entry", "SUB-people/bob"),
        ),
        statement="Bob's age is disputed.",
        confidence="high",
        subject_id="SUB-people",
        patch="maybe fifty-nine",
    )

    round_tripped = finding_from_verdict(finding_verdict(finding))

    assert round_tripped == finding


# --- findings are derived, and impact analysis is the same code path (#40) --


def test_findings_in_scope_reads_back_a_recorded_finding(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("entry", "SUB-people/bob"),
        ),
        statement="Contradicts the entry.",
        confidence="high",
        subject_id="SUB-people",
    )
    record_audit_verdict(repository, paragraph, "SUB-people/bob", finding_verdict(finding))

    assert findings_in_scope(repository, chapter_number=1, section_number=1) == (finding,)
    # And clear once actually settled/cleared, never accumulating alongside.
    assert findings_in_scope(repository, chapter_number=1, section_number=2) == ()


def test_findings_in_scope_reports_nothing_once_the_judgement_is_stale(tmp_path):
    """AC: findings recompute and nothing accumulates - editing the entry
    the finding rests on makes it stop being served, with nothing left over
    to clean up."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("entry", "SUB-people/bob"),
        ),
        statement="Contradicts the entry.",
        confidence="high",
        subject_id="SUB-people",
    )
    record_audit_verdict(repository, paragraph, "SUB-people/bob", finding_verdict(finding))
    assert findings_in_scope(repository) == (finding,)

    _write_entry(
        repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is short.")
    )

    assert findings_in_scope(repository) == ()


def test_impact_analysis_and_the_audit_read_the_same_pending_function(tmp_path):
    """AC: impact from a changed entry is the same code path as an audit.
    Editing the prose and editing the entry both surface through
    `pending_for_target` - the single function this module offers for "what
    needs (re-)evaluation" - never a second, "impact analysis" function."""
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", clear_verdict())
    assert pending_for_target(repository, chapter_number=1, section_number=1) == ()

    # Triggered from the prose end - a hand edit to the passage.
    (repository.root / "chapters" / "01" / "sections" / "01" / "draft.md").write_text(
        "Bob went to the capital instead.", encoding="utf-8"
    )
    from_prose = pending_for_target(repository, chapter_number=1, section_number=1)
    assert {i.cause for i in from_prose} == {"paragraph_edited"}

    # Re-audit clears it, then trigger from the other end - editing the entry.
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True})
    record_audit_verdict(repository, paragraph, "SUB-people/bob", clear_verdict())
    assert pending_for_target(repository, chapter_number=1, section_number=1) == ()

    _write_entry(
        repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is short.")
    )
    from_entry = pending_for_target(repository, chapter_number=1, section_number=1)
    assert {i.cause for i in from_entry} == {"entry_changed"}


def test_no_function_in_this_module_is_named_for_impact_analysis_separately():
    """AC (structural half): there is no second, "impact analysis" entry
    point beside the audit's own - a caller re-runs the same
    `pending_for_target`/`audit_tasks_for_target` either way."""
    import memoria.audit as audit_module

    public_names = {name for name in dir(audit_module) if not name.startswith("_")}
    assert not any("impact" in name.lower() for name in public_names)


# --- the model engine for Themes and Arcs (#40, part 06 §8.11) --------------


def test_model_engine_appearances_reads_back_current_engagement_judgements(tmp_path):
    """AC: model-engine appearances are produced for Themes and Arcs and
    memoized - there is no separate write here, only a read over what the
    audit already cached."""
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    control = Entry(id="SUB-themes/control", match_terms=["Control"], body="About control.")
    _write_entry(repository, control)
    _section(repository, brief_text="About Control.", draft="Bob wrestled with control.")
    paragraph = manuscript_paragraphs(repository)[0]

    assert model_engine_appearances(repository) == ()

    record_engagement(
        repository,
        paragraph,
        "SUB-themes/control",
        {"engages": True, "note": "frames episode as ambition"},
    )

    appearances = model_engine_appearances(repository)
    assert appearances == (
        ModelAppearance(
            entry_id="SUB-themes/control", slot="01/01#1", note="frames episode as ambition"
        ),
    )
    assert model_engine_appearances(repository, entry_id="SUB-themes/control") == appearances
    assert model_engine_appearances(repository, entry_id="SUB-people/bob") == ()


def test_model_engine_appearances_excludes_engages_false_and_lexical_subjects(tmp_path):
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    bob = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    control = Entry(id="SUB-themes/control", match_terms=["Control"], body="About control.")
    _write_entry(repository, bob)
    _write_entry(repository, control)
    _section(
        repository, brief_text="About Bob and Control.", draft="Bob wrestled with control."
    )
    paragraph = manuscript_paragraphs(repository)[0]

    record_engagement(repository, paragraph, "SUB-people/bob", {"engages": True, "note": "matched Bob"})
    record_engagement(
        repository, paragraph, "SUB-themes/control", {"engages": False, "note": "not really"}
    )

    assert model_engine_appearances(repository) == ()


def test_model_engine_appearances_goes_stale_the_same_way_engagement_does(tmp_path):
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    control = Entry(id="SUB-themes/control", match_terms=["Control"], body="About control.")
    _write_entry(repository, control)
    _section(repository, brief_text="About Control.", draft="Bob wrestled with control.")
    paragraph = manuscript_paragraphs(repository)[0]
    record_engagement(
        repository, paragraph, "SUB-themes/control", {"engages": True, "note": "note"}
    )
    assert len(model_engine_appearances(repository)) == 1

    _write_entry(
        repository,
        Entry(id="SUB-themes/control", match_terms=["Control"], body="Control means something else now."),
    )

    assert model_engine_appearances(repository) == ()


# --- AC: author testimony is a disagreement, never an error -----------------


def test_the_author_testimony_policy_is_defined_once_and_names_the_rule():
    assert "outranks" in AUTHOR_TESTIMONY_POLICY
    assert "author" in AUTHOR_TESTIMONY_POLICY.lower()


def test_a_testimony_versus_evidence_conflict_records_as_a_finding_not_an_exception(tmp_path):
    """A conflict with author testimony is reported as a disagreement,
    never as an error: recording one goes through the same `Finding`/
    `record_audit_verdict` path as any other, and there is no separate
    "the author is wrong" exception type for it to raise instead."""
    entry = Entry(
        id="SUB-people/bob",
        match_terms=["Bob"],
        body="Bob was born in 1962.\n\n[source] Notes describe Bob as in his thirties.",
    )
    repository = _basic_repo(
        tmp_path,
        entry=entry,
        brief_text="About Bob.",
        draft="Bob, thirty-something, walked in.",
    )
    paragraph = manuscript_paragraphs(repository)[0]

    finding = Finding(
        disagreement_set=(
            DisagreementMember("passage", paragraph.slot),
            DisagreementMember("entry", "SUB-people/bob"),
            DisagreementMember("source", "src-000001-p1"),
        ),
        statement=(
            "The passage's age matches the notes, but the entry's testimony "
            "(1962) outranks them - a disagreement, not an error."
        ),
        confidence="moderate",
        subject_id="SUB-people",
    )

    record_audit_verdict(repository, paragraph, "SUB-people/bob", finding_verdict(finding))

    assert findings_in_scope(repository) == (finding,)


# --- record_audit_batch: the recording half of an audit run (#40) -----------


def test_record_audit_batch_records_engagement_and_a_clear_verdict(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    anchor = f"{paragraph.slot}|SUB-people/bob"

    outcome = record_audit_batch(
        repository,
        [
            RecordedAuditItem(anchor=anchor, kind="engagement", engages=True, note="mentions Bob"),
            RecordedAuditItem(anchor=anchor, kind="audit_verdict", clear=True),
        ],
    )

    assert outcome.accepted == (anchor, anchor)
    assert outcome.rejected == ()
    assert compute_staleness_map(repository).not_current == ()


def test_record_audit_batch_records_a_finding(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    anchor = f"{paragraph.slot}|SUB-people/bob"

    outcome = record_audit_batch(
        repository,
        [
            RecordedAuditItem(
                anchor=anchor,
                kind="audit_verdict",
                finding=RecordedFinding(
                    disagreement_set=[
                        RecordedDisagreementMember(kind="passage", ref=paragraph.slot),
                        RecordedDisagreementMember(kind="entry", ref="SUB-people/bob"),
                    ],
                    statement="Contradicts the entry.",
                    confidence="high",
                ),
            )
        ],
    )

    assert outcome.accepted == (anchor,)
    findings = findings_in_scope(repository, chapter_number=1, section_number=1)
    assert len(findings) == 1
    assert findings[0].statement == "Contradicts the entry."
    assert findings[0].subject_id == "SUB-people"


def test_record_audit_batch_rejects_element_by_element(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    good_anchor = f"{paragraph.slot}|SUB-people/bob"

    outcome = record_audit_batch(
        repository,
        [
            RecordedAuditItem(anchor="not-an-anchor", kind="engagement", engages=True),
            RecordedAuditItem(
                anchor=f"{paragraph.slot}|SUB-people/carol", kind="engagement", engages=True
            ),
            RecordedAuditItem(anchor=good_anchor, kind="engagement"),  # missing 'engages'
            RecordedAuditItem(
                anchor=good_anchor, kind="engagement", engages=True, note="mentions Bob"
            ),
        ],
    )

    assert outcome.accepted == (good_anchor,)
    assert len(outcome.rejected) == 3


def test_record_audit_batch_rejects_a_finding_with_no_declared_resolution(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _basic_repo(
        tmp_path, entry=entry, brief_text="About Bob.", draft="Bob went to town."
    )
    paragraph = manuscript_paragraphs(repository)[0]
    anchor = f"{paragraph.slot}|SUB-people/bob"

    outcome = record_audit_batch(
        repository,
        [
            RecordedAuditItem(
                anchor=anchor,
                kind="audit_verdict",
                finding=RecordedFinding(
                    disagreement_set=[
                        RecordedDisagreementMember(kind="entry", ref="SUB-people/bob"),
                    ],
                    statement="No passage in this set.",
                    confidence="low",
                ),
            )
        ],
    )

    assert outcome.accepted == ()
    assert len(outcome.rejected) == 1
    assert findings_in_scope(repository) == ()
