"""Briefs at three scales: the on-disk form, the author write path, the
unconfirmed state, reordering, and the isolation that keeps a brief writable
only by a deliberate act on it (#35).

``read(ref)`` resolving chapters and sections by their stable IDs is
exercised end to end in ``test_read_ref.py``, alongside the SRC- forms it
already covers.
"""

import ast
from pathlib import Path

import pytest

from memoria import manuscript
from memoria.manuscript import (
    Brief,
    ManuscriptError,
    brief_to_markdown,
    confirm_brief,
    create_book,
    create_chapter,
    create_section,
    list_chapters,
    list_sections,
    parse_brief,
    reorder_chapters,
    reorder_sections,
    resolve_chapter,
    resolve_section,
    write_brief,
)
from memoria.repository import Repository

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


# --- the on-disk form, both directions --------------------------------------


def test_a_brief_round_trips_through_markdown():
    original = Brief(id="CHP-0001", text="June 1839 to October 1841.", unconfirmed=False)
    text = brief_to_markdown(original)

    assert parse_brief(text) == original
    assert brief_to_markdown(parse_brief(text)) == text


def test_the_serialized_brief_carries_only_id_and_unconfirmed():
    """No scope field, no checkpoint field, no next-step field (#35)."""
    text = brief_to_markdown(Brief(id="CHP-0001", text="Some prose.", unconfirmed=True))

    assert "id: CHP-0001" in text
    assert "unconfirmed: true" in text
    for withdrawn in ("scope:", "checkpoint:", "next_step:", "purpose:", "status:"):
        assert withdrawn not in text


def test_a_frontmatter_field_the_schema_does_not_define_is_named_not_swallowed():
    text = brief_to_markdown(Brief(id="CHP-0001", text="x", unconfirmed=False)).replace(
        "unconfirmed: false", "unconfirmed: false\nscope: June to October"
    )
    with pytest.raises(ManuscriptError, match="scope"):
        parse_brief(text)


def test_unconfirmed_must_be_a_real_boolean():
    text = brief_to_markdown(Brief(id="CHP-0001", text="x", unconfirmed=False)).replace(
        "unconfirmed: false", "unconfirmed: 'false'"
    )
    with pytest.raises(ManuscriptError, match="must be a YAML boolean"):
        parse_brief(text)


def test_prose_with_no_trailing_newline_still_round_trips():
    original = Brief(id="CHP-0001", text="No trailing newline in the source text", unconfirmed=False)
    assert parse_brief(brief_to_markdown(original)) == original


# --- creation and the outline is the directory tree -------------------------


def test_create_book_writes_a_singleton_with_a_fixed_id(tmp_path):
    repository = _repo(tmp_path)
    brief = create_book(repository, "A memoir of the acquisition years.")

    assert brief.id == "BOOK"
    assert brief.unconfirmed is False
    assert (tmp_path / "book.md").is_file()


def test_create_chapter_mints_sequential_stable_ids(tmp_path):
    repository = _repo(tmp_path)
    first = create_chapter(repository, "Chapter one.")
    second = create_chapter(repository, "Chapter two.")

    assert first.brief.id == "CHP-0001"
    assert second.brief.id == "CHP-0002"
    assert first.number == 1
    assert second.number == 2
    assert (tmp_path / "chapters" / "01" / "chapter.md").is_file()
    assert (tmp_path / "chapters" / "02" / "chapter.md").is_file()


def test_create_section_mints_stable_ids_unique_across_the_whole_book(tmp_path):
    """Section IDs are one flat namespace, not one counter per chapter -
    what makes a bare `SEC-0002` in a citation unambiguous."""
    repository = _repo(tmp_path)
    chapter_a = create_chapter(repository, "A")
    chapter_b = create_chapter(repository, "B")
    section_a = create_section(repository, chapter_a.number, "A1")
    section_b = create_section(repository, chapter_b.number, "B1")

    assert section_a.brief.id == "SEC-0001"
    assert section_b.brief.id == "SEC-0002"


def test_list_chapters_and_sections_reflect_directory_order(tmp_path):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "Chapter.")
    create_section(repository, chapter.number, "First.")
    create_section(repository, chapter.number, "Second.")

    (chapter_entry,) = list_chapters(repository)
    sections = list_sections(repository, chapter.number)

    assert chapter_entry.brief.id == chapter.brief.id
    assert [s.brief.text for s in sections] == ["First.", "Second."]


def test_no_outline_file_or_state_file_exists_anywhere(tmp_path):
    """The outline is the directory tree of briefs, not a file (#35)."""
    repository = _repo(tmp_path)
    create_book(repository, "Book.")
    chapter = create_chapter(repository, "Chapter.")
    create_section(repository, chapter.number, "Section.")

    for stray in tmp_path.rglob("outline.md"):
        pytest.fail(f"unexpected outline.md: {stray}")
    for stray in tmp_path.rglob("state.md"):
        pytest.fail(f"unexpected state.md: {stray}")


# --- the author write path: direct, supreme, clears unconfirmed ------------


def test_write_brief_replaces_the_prose_unconditionally(tmp_path):
    repository = _repo(tmp_path)
    brief = create_book(repository, "Draft text.")

    updated = write_brief(manuscript.book_path(repository), "The author's own words.")

    assert updated.text == "The author's own words."
    assert updated.id == brief.id


def test_editing_an_unconfirmed_brief_clears_the_flag(tmp_path):
    """Part 04 §2.1: editing an unconfirmed brief makes it the author's."""
    repository = _repo(tmp_path)
    create_book(repository, "Summarized from existing prose.", unconfirmed=True)
    path = manuscript.book_path(repository)
    assert parse_brief(path.read_text(encoding="utf-8")).unconfirmed is True

    write_brief(path, "The author's rewrite.")

    assert parse_brief(path.read_text(encoding="utf-8")).unconfirmed is False


def test_confirming_an_unconfirmed_brief_clears_the_flag_without_changing_text(tmp_path):
    repository = _repo(tmp_path)
    create_book(repository, "Summarized text, left as is.", unconfirmed=True)
    path = manuscript.book_path(repository)

    confirmed = confirm_brief(path)

    assert confirmed.unconfirmed is False
    assert confirmed.text == "Summarized text, left as is."


def test_confirming_an_already_confirmed_brief_is_a_harmless_no_op(tmp_path):
    repository = _repo(tmp_path)
    create_book(repository, "Author-written from the start.")
    path = manuscript.book_path(repository)

    confirmed = confirm_brief(path)

    assert confirmed.unconfirmed is False
    assert confirmed.text == "Author-written from the start."


def test_write_brief_on_a_missing_brief_is_a_named_error(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(ManuscriptError, match="no brief at"):
        write_brief(manuscript.book_path(repository), "text")


# --- reordering: directories renumber, IDs and references survive ----------


def test_reordering_sections_renumbers_directories(tmp_path):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "Chapter.")
    first = create_section(repository, chapter.number, "First.")
    second = create_section(repository, chapter.number, "Second.")
    third = create_section(repository, chapter.number, "Third.")

    reorder_sections(repository, chapter.number, [third.brief.id, first.brief.id, second.brief.id])

    ordered = list_sections(repository, chapter.number)
    assert [s.brief.id for s in ordered] == [third.brief.id, first.brief.id, second.brief.id]
    assert [s.number for s in ordered] == [1, 2, 3]


def test_reordering_sections_breaks_no_reference(tmp_path):
    """The stable ID resolves to the same brief before and after the move -
    the whole point of separating identity from directory position."""
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "Chapter.")
    first = create_section(repository, chapter.number, "First.")
    second = create_section(repository, chapter.number, "Second.")

    reorder_sections(repository, chapter.number, [second.brief.id, first.brief.id])

    assert resolve_section(repository, first.brief.id).brief.text == "First."
    assert resolve_section(repository, second.brief.id).brief.text == "Second."
    assert resolve_section(repository, second.brief.id).number == 1
    assert resolve_section(repository, first.brief.id).number == 2


def test_reordering_chapters_renumbers_directories_and_breaks_no_reference(tmp_path):
    repository = _repo(tmp_path)
    first = create_chapter(repository, "First.")
    second = create_chapter(repository, "Second.")

    reorder_chapters(repository, [second.brief.id, first.brief.id])

    assert resolve_chapter(repository, first.brief.id).number == 2
    assert resolve_chapter(repository, second.brief.id).number == 1


def test_reorder_rejects_a_list_that_does_not_name_exactly_the_existing_sections(tmp_path):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "Chapter.")
    create_section(repository, chapter.number, "Only one.")

    with pytest.raises(ManuscriptError, match="existing sections"):
        reorder_sections(repository, chapter.number, ["SEC-0001", "SEC-9999"])


# --- resolution by stable ID -------------------------------------------------


def test_resolve_chapter_and_section_find_the_entry_by_id(tmp_path):
    repository = _repo(tmp_path)
    chapter = create_chapter(repository, "Chapter text.")
    section = create_section(repository, chapter.number, "Section text.")

    assert resolve_chapter(repository, chapter.brief.id).brief.text == "Chapter text."
    assert resolve_section(repository, section.brief.id).brief.text == "Section text."


def test_resolving_an_unknown_id_is_a_named_error(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(ManuscriptError, match="CHP-0001"):
        resolve_chapter(repository, "CHP-0001")
    with pytest.raises(ManuscriptError, match="SEC-0001"):
        resolve_section(repository, "SEC-0001")


# --- a brief is writable only by a deliberate act on it (#35) ---------------


def test_only_manuscript_reaches_the_one_place_a_brief_is_written():
    """`_write_brief_file` is where a brief's bytes reach disk, and nothing
    outside this module names it - so nothing outside a deliberate call to
    `write_brief`/`confirm_brief`/`create_*` can write one. There is no
    finding-resolution module in this codebase yet (#40-#42 are unbuilt); this
    is what makes the constraint checkable rather than merely intended, now
    and once one exists.
    """
    sources = sorted(SRC_ROOT.rglob("*.py"))
    assert sources, "no memoria package sources found - has the package moved?"

    for path in sources:
        if path == SRC_ROOT / "manuscript.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            assert name != "_write_brief_file", (
                f"{path.name} reaches manuscript._write_brief_file directly - "
                "a brief may only be written through write_brief/confirm_brief/"
                "create_book/create_chapter/create_section"
            )
