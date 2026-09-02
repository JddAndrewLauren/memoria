"""The one scope resolver (#36): a brief's declared scope, resolved through
the subjects into a set of entries, deterministically and with no model
call. `test_no_module_but_scope_resolves_a_briefs_text_against_the_entries` and its
neighbour are the guard against assembly (#38), the audit's bounding (#40)
or drift detection (#41) growing their own copy instead of calling
`resolve_scope`. The memoized judgements and staleness map (#37) and drift
detection (#41) have since landed, and both import `resolve_scope`;
assembly (#38) and the audit's own run (#40) are still to come. The same
shape as `test_manuscript.py`'s "no module but manuscript knows a brief's
filename".
"""

import ast
from pathlib import Path

from memoria.manuscript import Brief
from memoria.repository import Repository
from memoria.scope import ScopeResolution, resolve_scope
from memoria.subjects import Entry, entry_to_markdown

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "memoria"


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


def _write_entry(tmp_path, entry: Entry) -> None:
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry), encoding="utf-8")


def _brief(text: str, *, unconfirmed: bool = False) -> Brief:
    return Brief(id="SEC-0001", text=text, unconfirmed=unconfirmed)


# --- resolving a brief's declared scope through the subjects (#36) ----------


def test_resolve_scope_finds_an_entry_by_its_implicit_name(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    resolution = resolve_scope(
        repository, _brief("Covers my interactions with Bob about the acquisition.")
    )

    assert resolution.entry_ids == ("SUB-people/bob",)
    assert resolution.matched_by == {"SUB-people/bob": ("bob",)}
    assert not resolution.empty


def test_resolve_scope_finds_an_entry_by_a_declared_match_term(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", match_terms=["Robert"]))
    repository = _repo(tmp_path)

    resolution = resolve_scope(repository, _brief("Covers Robert's early years."))

    assert resolution.entry_ids == ("SUB-people/bob",)
    assert resolution.matched_by == {"SUB-people/bob": ("Robert",)}


def test_resolve_scope_names_every_term_the_text_actually_contains(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob", match_terms=["Robert", "R."]))
    repository = _repo(tmp_path)

    resolution = resolve_scope(
        repository, _brief("Bob, called Robert by his mother, signs letters R.")
    )

    assert resolution.matched_by["SUB-people/bob"] == ("bob", "Robert", "R.")


def test_resolve_scope_does_not_match_a_term_inside_a_longer_word(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    resolution = resolve_scope(repository, _brief("Covers Bobby's early years."))

    assert resolution.entry_ids == ()
    assert resolution.empty


def test_resolve_scope_ignores_entry_and_relation_shaped_match_terms(tmp_path):
    """A Theme's entry-/relation-shaped match terms name co-occurrence for
    gathering, never a phrase a brief's prose would contain (#36's
    docstring) - so a brief that happens to contain that literal text does
    not resolve the Theme through it; only its implicit name can."""
    _write_entry(
        tmp_path,
        Entry(
            id="SUB-themes/the-conflict",
            match_terms=["SUB-people/bob", "SUB-people/bob -> pressures -> SUB-people/author"],
        ),
    )
    repository = _repo(tmp_path)

    resolution = resolve_scope(
        repository, _brief("Mentions SUB-people/bob directly, oddly.")
    )

    assert resolution.entry_ids == ()


def test_an_unmatched_word_shaped_entry_or_relation_reference_is_still_ignorable(tmp_path):
    """The same brief resolves the Theme when it is named by its own
    implicit name instead."""
    _write_entry(
        tmp_path,
        Entry(id="SUB-themes/the-conflict", match_terms=["SUB-people/bob"]),
    )
    repository = _repo(tmp_path)

    resolution = resolve_scope(
        repository, _brief("Covers the conflict, and how it resolves.")
    )

    assert resolution.entry_ids == ("SUB-themes/the-conflict",)


def test_resolve_scope_resolves_several_entries_in_sorted_order(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    _write_entry(tmp_path, Entry(id="SUB-events/acquisition"))
    repository = _repo(tmp_path)

    resolution = resolve_scope(
        repository, _brief("Bob's role in the acquisition.")
    )

    assert resolution.entry_ids == ("SUB-events/acquisition", "SUB-people/bob")


def test_resolve_scope_over_a_brief_naming_nothing_is_reported_explicitly(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    resolution = resolve_scope(repository, _brief("Roughly the middle of the book."))

    assert resolution.entry_ids == ()
    assert resolution.matched_by == {}
    assert resolution.empty is True


def test_resolve_scope_flags_an_unconfirmed_brief(tmp_path):
    _write_entry(tmp_path, Entry(id="SUB-people/bob"))
    repository = _repo(tmp_path)

    confirmed = resolve_scope(repository, _brief("About Bob.", unconfirmed=False))
    unconfirmed = resolve_scope(repository, _brief("About Bob.", unconfirmed=True))

    assert confirmed.unconfirmed is False
    assert unconfirmed.unconfirmed is True
    # The brief's unconfirmed state does not itself change what resolves -
    # only assembly and the audit (#38, #40) treat the two differently.
    assert confirmed.entry_ids == unconfirmed.entry_ids


def test_resolve_scope_is_deterministic_at_a_repository_revision(tmp_path):
    """Same subjects, same entries, same brief text, same answer - #36's
    second acceptance criterion."""
    _write_entry(tmp_path, Entry(id="SUB-people/bob", match_terms=["Robert"]))
    _write_entry(tmp_path, Entry(id="SUB-events/acquisition"))
    repository = _repo(tmp_path)
    brief = _brief("Bob's role in the acquisition, called Robert by his mother.")

    first = resolve_scope(repository, brief)
    second = resolve_scope(repository, brief)

    assert first == second


def test_resolve_scope_returns_a_scope_resolution(tmp_path):
    repository = _repo(tmp_path)
    assert isinstance(resolve_scope(repository, _brief("Anything.")), ScopeResolution)


# --- the resolver is the one seam (#36) --------------------------------------

# A guard keyed on the function name alone only catches a reimplementation
# literally called `resolve_scope`; a future assembly.py naming its copy
# `_entries_in_scope` or `_resolve_brief_entries` would pass it silently
# while still being the divergence bug #36 exists to prevent. So this is
# keyed on the combination that *is* the resolution instead - a module
# naming `Brief`, reading its `.text`, and calling the same entry-scanning
# functions `resolve_scope` uses to build what it scans for
# (`load_all_entries`, `implicit_name_term`, `classify_match_term`) - the
# same content-based shape as `test_manuscript.py`'s `_BRIEF_WRITERS` guard.
_ENTRY_SCAN_FUNCTIONS = {"load_all_entries", "implicit_name_term", "classify_match_term"}

# Modules allowed to call the entry-scanning functions for their own,
# pre-existing purposes unrelated to resolving a Brief's scope: index.py's
# appearance computation and extraction.py's own candidate matching (and
# extraction.py's own, unrelated `Brief` dataclass). Neither reads a
# `manuscript.Brief`'s `.text`.
_SCOPE_RESOLUTION_ALLOWLIST = ("index.py", "extraction.py")


def _names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
    return names


def _package_sources() -> list[Path]:
    sources = sorted(SRC_ROOT.rglob("*.py"))
    assert sources, "no memoria package sources found - has the package moved?"
    return [
        path
        for path in sources
        if path.name != "scope.py" and path.name not in _SCOPE_RESOLUTION_ALLOWLIST
    ]


def test_no_module_but_scope_resolves_a_briefs_text_against_the_entries():
    """No module outside `scope.py` both names `Brief`, reads a `.text` off
    one, and calls the functions `resolve_scope` calls to build the terms it
    scans for. That combination is the resolution itself, under whatever
    name a reimplementation gave its function - the divergence bug #36
    exists to rule out. The memoized judgements and staleness map (#37) and
    drift detection (#41) have since landed, and both take their bounding by
    importing `resolve_scope` rather than rebuilding it - which is what this
    guard asks for. Assembly (#38) and the audit's own run (#40) are still
    to come, so for those this still only fails a future module that
    rebuilds the resolution instead of importing this one."""
    for path in _package_sources():
        names = _names_in(path)
        if "Brief" not in names or "text" not in names:
            continue
        found = names & _ENTRY_SCAN_FUNCTIONS
        assert not found, (
            f"{path.name} names Brief, reads .text, and calls {sorted(found)} - "
            "that combination is the scope resolution itself; call "
            "scope.resolve_scope instead of rebuilding it"
        )


def test_the_content_based_guard_would_catch_a_differently_named_resolver(tmp_path):
    """The guard above is only worth having if it catches the exact case a
    name-based guard would miss: a reimplementation under a name that is not
    `resolve_scope`."""
    offender = tmp_path / "assembly.py"
    offender.write_text(
        "from memoria.extraction import implicit_name_term\n"
        "from memoria.manuscript import Brief\n"
        "from memoria.subjects import classify_match_term, load_all_entries\n"
        "\n"
        "def _entries_in_scope(repository, brief: Brief):\n"
        "    found = []\n"
        "    for entry_id, entry in load_all_entries(repository).items():\n"
        "        implicit_name_term(entry_id)\n"
        "        for term in entry.match_terms:\n"
        "            classify_match_term(term)\n"
        "            if term in brief.text:\n"
        "                found.append(entry_id)\n"
        "    return found\n",
        encoding="utf-8",
    )
    names = _names_in(offender)
    assert "Brief" in names and "text" in names
    assert names & _ENTRY_SCAN_FUNCTIONS
