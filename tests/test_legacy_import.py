"""Legacy import (#39, part 04 §2.1 / part 06 §8.12): a pre-Memoria chapter
enters the system as an unconfirmed brief and a cold cache.

Covers the acceptance criteria: stable IDs in the chapters tree, an
unconfirmed brief on both chapter and section, zero model calls, every
imported paragraph reading as never-audited, a scalar count rather than a
queue, drift skipped against the unconfirmed brief, and confirming/editing
clearing it. The last two lean on `memoria.drift`/`memoria.manuscript`
directly, already built (#35, #41) - this module adds nothing of its own to
either.
"""

import ast
from pathlib import Path

from memoria.audit import StalenessMap, compute_staleness_map
from memoria.drift import compute_drift
from memoria.legacy_import import ImportResult, import_chapter
from memoria.manuscript import (
    confirm_brief,
    list_chapters,
    list_sections,
    write_brief,
)
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


def _write_entry(repository: Repository, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = repository.root / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


PROSE = "Bob went to town.\n\nBob came home."
SUMMARY = "Bob's trip into town and back."


# --- AC 1: stable IDs in the chapters tree ------------------------------------


def test_import_creates_one_chapter_and_one_section_with_stable_ids(tmp_path):
    repository = _repo(tmp_path)

    result = import_chapter(repository, PROSE, SUMMARY)

    assert result.chapter.brief.id.startswith("CHP-")
    assert result.section.brief.id.startswith("SEC-")
    chapters = list_chapters(repository)
    assert [c.brief.id for c in chapters] == [result.chapter.brief.id]
    sections = list_sections(repository, result.chapter.number)
    assert [s.brief.id for s in sections] == [result.section.brief.id]
    draft_path = repository.root / "chapters" / "01" / "sections" / "01" / "draft.md"
    assert draft_path.read_text(encoding="utf-8") == PROSE


# --- AC 2: an unconfirmed brief, drafted by summarizing the prose ------------


def test_import_drafts_an_unconfirmed_brief_on_both_chapter_and_section(tmp_path):
    repository = _repo(tmp_path)

    result = import_chapter(repository, PROSE, SUMMARY)

    assert result.chapter.brief.unconfirmed is True
    assert result.chapter.brief.text == SUMMARY
    assert result.section.brief.unconfirmed is True
    assert result.section.brief.text == SUMMARY


# --- AC 3: no per-paragraph model evaluation, no model reachable at all ------


def test_no_core_module_imports_a_model_client():
    """Mirrors `test_audit.py`'s AST sweep - the module never has a reason
    to reach a model, since the summary is supplied, not generated here."""
    forbidden = {"anthropic", "openai", "httpx", "requests", "urllib", "socket"}
    tree = ast.parse((SRC_ROOT / "legacy_import.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] not in forbidden


def test_importing_a_chapter_opens_no_socket_and_leaves_no_process(tmp_path, monkeypatch):
    import socket
    import subprocess

    def _blocked(*args, **kwargs):
        raise AssertionError("import touched the network")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)
    monkeypatch.setattr(subprocess, "Popen", _blocked)

    repository = _repo(tmp_path)
    result = import_chapter(repository, PROSE, SUMMARY)

    assert isinstance(result, ImportResult)


# --- AC 4: every imported paragraph reads as not current, never_audited -----


def test_every_imported_paragraph_reads_as_never_audited(tmp_path):
    repository = _repo(tmp_path)
    write_builtin_subjects(repository)
    _write_entry(repository, Entry(id="SUB-people/bob", match_terms=["Bob"], body=""))

    import_chapter(repository, PROSE, SUMMARY)

    staleness = compute_staleness_map(repository)
    assert isinstance(staleness, StalenessMap)
    # Two paragraphs, each checked against Bob under both judgement kinds.
    assert staleness.paragraphs_not_current == 2
    assert {item.cause for item in staleness.not_current} == {"never_audited"}
    assert {item.kind for item in staleness.not_current} == {"engagement", "audit_verdict"}


# --- AC 5: a count, not a queue of work ---------------------------------------


def test_import_reports_a_scalar_paragraph_count(tmp_path):
    repository = _repo(tmp_path)

    result = import_chapter(repository, PROSE, SUMMARY)

    assert result.paragraph_count == 2
    assert isinstance(result.paragraph_count, int)


def test_an_empty_chapter_imports_as_a_zero_count(tmp_path):
    repository = _repo(tmp_path)

    result = import_chapter(repository, "", SUMMARY)

    assert result.paragraph_count == 0


# --- AC 6: drift is not evaluated against the unconfirmed brief --------------


def test_drift_is_skipped_against_the_freshly_imported_brief(tmp_path):
    repository = _repo(tmp_path)

    result = import_chapter(repository, PROSE, SUMMARY)

    report = compute_drift(repository, result.section.brief)
    assert report.skipped is True
    assert report.reason and "unconfirmed" in report.reason


# --- AC 7: confirming or editing clears unconfirmed and enables drift -------


def test_confirming_the_imported_brief_clears_unconfirmed_and_enables_drift(tmp_path):
    repository = _repo(tmp_path)
    result = import_chapter(repository, PROSE, SUMMARY)

    confirmed = confirm_brief(result.section.path)

    assert confirmed.unconfirmed is False
    report = compute_drift(repository, confirmed)
    assert report.skipped is False


def test_editing_the_imported_brief_clears_unconfirmed_and_enables_drift(tmp_path):
    repository = _repo(tmp_path)
    result = import_chapter(repository, PROSE, SUMMARY)

    edited = write_brief(result.section.path, "The author's own words now.")

    assert edited.unconfirmed is False
    report = compute_drift(repository, edited)
    assert report.skipped is False
