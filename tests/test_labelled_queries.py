"""The labelled query set (#81; ADR-0007; part 15 §43.14; docs/open-problems.md
§2.2): the successor retrieval-recall instrument, grown by the author once a
real archive exists to draw labelled queries from.

`tests/fixtures/labelled_queries.yaml` carries its documented shape and ships
empty - populating it is out of scope for #81 (docs/adr/
0007-embeddings-enter-by-choice.md's "Out of scope"), and starts the day a
real archive arrives. This file is the check part 15 §43.14 asks a successor
harness to provide: it validates the fixture's shape unconditionally, and for
each labelled query (there are none yet) asserts `search_semantic` recalls at
least one of its expected anchors among its nearest hits - so it passes
vacuously today and becomes a real gate the day the fixture is not empty,
with no further code change needed here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from memoria.embeddings import default_embed_fn
from memoria.index import SearchFilters, search_semantic
from memoria.repository import from_env

LABELLED_QUERIES_PATH = Path(__file__).parent / "fixtures" / "labelled_queries.yaml"


def _load_labelled_queries() -> list[dict]:
    with LABELLED_QUERIES_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


def test_the_labelled_query_file_is_a_list():
    assert isinstance(_load_labelled_queries(), list)


def test_every_labelled_query_has_the_documented_shape():
    for entry in _load_labelled_queries():
        assert set(entry) >= {"id", "query", "expected_anchors"}
        assert set(entry) <= {"id", "query", "filters", "expected_anchors"}
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["query"], str) and entry["query"]
        assert isinstance(entry["expected_anchors"], list) and entry["expected_anchors"]


def test_labelled_queries_are_recalled_by_search_semantic():
    """The check itself. Runs over `repository.from_env()` - the same
    repository every other retrieval call resolves against - so it exercises
    the real archive's index the day one is configured and does nothing
    (vacuously passes) until then: with no entries, `from_env()` is never
    even called, so this never depends on an evidence root being set."""
    queries = _load_labelled_queries()
    if not queries:
        return
    repository = from_env()
    for entry in queries:
        filters = SearchFilters(**entry.get("filters", {}))
        result = search_semantic(
            repository, entry["query"], filters, embed_fn=default_embed_fn
        )
        hit_anchors = {r.anchor for r in result.results}
        expected = set(entry["expected_anchors"])
        assert hit_anchors & expected, (
            f"{entry['id']!r}: none of {sorted(expected)} were recalled "
            f"among {sorted(hit_anchors)}"
        )
