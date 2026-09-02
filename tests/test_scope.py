"""The one scope resolver (#36): a brief's declared scope, resolved through
the subjects into a set of entries, deterministically and with no model
call. `test_the_isolation_test_would_catch_a_second_resolver` and its
neighbour are the guard against assembly (#38), the audit's bounding (#40)
or drift detection (#41) - none of which exist yet - growing their own copy
instead of calling `resolve_scope` when one of them lands, the same shape as
`test_manuscript.py`'s "no module but manuscript knows a brief's filename".
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

_RESOLVER_FUNCTIONS = {"resolve_scope"}


def _function_names_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _package_sources() -> list[Path]:
    sources = sorted(SRC_ROOT.rglob("*.py"))
    assert sources, "no memoria package sources found - has the package moved?"
    return [path for path in sources if path.name != "scope.py"]


def test_no_module_but_scope_defines_the_resolver():
    """`resolve_scope` is defined in exactly one place. Assembly, the
    audit's bounding and drift detection (#38, #40, #41) do not exist yet -
    this issue is built before all three precisely so none of them grows its
    own copy - so today this only fails for a future module that
    reimplements the resolution instead of importing this one."""
    for path in _package_sources():
        found = _function_names_in(path) & _RESOLVER_FUNCTIONS
        assert not found, (
            f"{path.name} defines {sorted(found)} - the scope resolver lives "
            "in scope.py alone; a second definition is the divergence bug "
            "#36 exists to rule out"
        )


def test_the_isolation_test_would_catch_a_second_resolver(tmp_path):
    """The test above is only worth having if it fails for the thing it
    guards against."""
    offender = tmp_path / "assembly.py"
    offender.write_text(
        "def resolve_scope(repository, brief):\n"
        "    return None\n",
        encoding="utf-8",
    )
    assert _function_names_in(offender) & _RESOLVER_FUNCTIONS
