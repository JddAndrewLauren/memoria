"""Context manifests (#29): what a session's own events.jsonl says it was
supplied.

Fixtures drive the ledger through its public functions (`memoria.ledger`),
the same discipline `test_ledger.py` holds itself to, so a manifest test
also exercises the exact shape the tool surface writes - "the manifest
matches the ledger" is then a fact about two modules agreeing, not two
fixtures agreeing with each other.
"""

import json
from pathlib import Path

import pytest

from memoria import ledger
from memoria.context_manifest import (
    BASIS,
    ManifestResult,
    build_context_manifest,
    derive_context_manifest,
    manifest_path,
)
from memoria.index import ReadOverlay, SearchFilters, SearchResult
from memoria.records import Read
from memoria.repository import Repository
from memoria.sessions import SessionError


def _read(**overrides):
    fields = dict(ref="SRC-000184", citation="SRC-000184", text="A blue heron flew over.")
    fields.update(overrides)
    return Read(**fields)


def _repo(tmp_path) -> Repository:
    return Repository(root=tmp_path)


# --- building the manifest from events.jsonl --------------------------------


def test_an_untouched_session_has_an_empty_manifest(tmp_path):
    manifest = build_context_manifest(_repo(tmp_path), "SES-test")

    assert manifest["records_loaded"] == []
    assert manifest["entries_resolved"] == []
    assert manifest["other_reads"] == []
    assert manifest["searches"] == []
    assert manifest["session_id"] == "SES-test"


def test_a_whole_record_read_is_listed_under_records_loaded(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read())

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["records_loaded"] == [
        {"ref": "SRC-000184", "tokens": ledger.estimate_tokens("A blue heron flew over.")}
    ]
    assert manifest["entries_resolved"] == []


def test_an_entry_read_is_listed_under_entries_resolved_not_records_loaded(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(
        repository,
        "SES-test",
        _read(ref="SUB-people/bob", citation="SUB-people/bob", text="Bob is a contractor."),
    )

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["records_loaded"] == []
    assert [item["ref"] for item in manifest["entries_resolved"]] == ["SUB-people/bob"]


def test_a_read_of_no_known_kind_lands_under_other_reads_rather_than_vanishing(tmp_path):
    """A path or a CHG- read is still something this session was given -
    dropping it silently would misstate the manifest's own completeness
    claim, so it lands in a named catch-all bucket instead."""
    repository = _repo(tmp_path)
    ledger.append_read(
        repository, "SES-test", _read(ref="docs/poc-plan.md", citation="docs/poc-plan.md", text="§6")
    )

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["records_loaded"] == []
    assert manifest["entries_resolved"] == []
    assert [item["ref"] for item in manifest["other_reads"]] == ["docs/poc-plan.md"]


def test_a_paragraph_read_still_groups_under_its_own_record(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(
        repository,
        "SES-test",
        _read(ref="SRC-000184 P1", citation="SRC-000184 ¶1", text="A blue heron flew over."),
    )

    manifest = build_context_manifest(repository, "SES-test")

    assert [item["ref"] for item in manifest["records_loaded"]] == ["SRC-000184 ¶1"]


def test_a_search_is_listed_with_its_query_and_filters(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        SearchFilters(source_type="journal"),
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )

    manifest = build_context_manifest(repository, "SES-test")

    (search,) = manifest["searches"]
    assert search["tool"] == "search_text"
    assert search["query"] == "heron"
    assert search["filters"]["source_type"] == "journal"
    assert search["results"] == [{"anchor": "src-000184-p1", "read": False}]


def test_search_global_carries_its_own_mode_fields(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_search_global(
        repository,
        "SES-test",
        None,
        None,
        True,
        True,
        ["CLU-0001"],
        ["src-000184-p1"],
    )

    manifest = build_context_manifest(repository, "SES-test")

    (search,) = manifest["searches"]
    assert search["tool"] == "search_global"
    assert search["summarize"] is True
    assert search["summary_served"] is True
    assert search["clusters"] == ["CLU-0001"]


# --- searched but not read, distinguished from read -------------------------


def test_a_search_hit_that_is_never_read_is_marked_unread(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        None,
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["searches"][0]["results"] == [{"anchor": "src-000184-p1", "read": False}]


def test_a_search_hit_later_read_by_its_own_anchor_is_marked_read(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        None,
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )
    ledger.append_read(
        repository,
        "SES-test",
        _read(ref="src-000184-p1", citation="SRC-000184 ¶1"),
    )

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["searches"][0]["results"] == [{"anchor": "src-000184-p1", "read": True}]


def test_a_search_hit_covered_by_a_whole_record_read_is_marked_read(tmp_path):
    """Reading the whole record necessarily served every paragraph in it,
    the searched one included."""
    repository = _repo(tmp_path)
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        None,
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )
    ledger.append_read(repository, "SES-test", _read(ref="SRC-000184"))

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["searches"][0]["results"] == [{"anchor": "src-000184-p1", "read": True}]


def test_material_never_reached_at_all_is_simply_absent(tmp_path):
    """No search, no read - so it names nothing, which is how "never
    reached" is told apart from "searched but not read": the latter is a
    result row with `read: false`, the former is no row at all."""
    repository = _repo(tmp_path)
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        None,
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )

    manifest = build_context_manifest(repository, "SES-test")

    anchors = {result["anchor"] for search in manifest["searches"] for result in search["results"]}
    assert "src-000185-p1" not in anchors


# --- token counts -------------------------------------------------------


def test_a_served_reads_token_count_rides_the_ledger_line_it_is_measured_from(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read(text="one two three four"))

    path = ledger.event_path(repository, "SES-test")
    (line,) = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(line)

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["records_loaded"][0]["tokens"] == event["tokens"]
    assert event["tokens"] > 0


def test_an_empty_reads_token_count_is_zero(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read(text=""))

    manifest = build_context_manifest(repository, "SES-test")

    assert manifest["records_loaded"][0]["tokens"] == 0


def test_a_decorated_reads_token_count_is_unaffected_by_its_overlay(tmp_path):
    """The overlay is decoration, not evidence (#20); the budget the token
    count feeds (poc-plan.md §6 risk 1) is about corpus content, so only
    `Read.text` is measured."""
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read(text="one two three four"))
    ledger.append_read(
        repository,
        "SES-test",
        _read(
            ref="SRC-000185",
            citation="SRC-000185",
            text="one two three four",
            overlay=ReadOverlay(entry_links=["SUB-people/bob"], exclusions=[], citing_settlements=[]),
        ),
    )

    manifest = build_context_manifest(repository, "SES-test")

    tokens = [item["tokens"] for item in manifest["records_loaded"]]
    assert tokens[0] == tokens[1]


# --- the manifest matches the ledger exactly, for a driven session ------


def test_the_manifest_matches_the_ledger_exactly_for_a_driven_session(tmp_path):
    """Drive a session through every ledgered tool call once, then check the
    manifest names exactly what the ledger says was served - nothing
    invented, nothing dropped."""
    repository = _repo(tmp_path)
    session_id = "SES-driven"

    ledger.append_read(repository, session_id, _read(ref="SRC-000184", citation="SRC-000184"))
    ledger.append_search(
        repository,
        session_id,
        "heron",
        SearchFilters(source_type="journal"),
        [
            SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal"),
            SearchResult(src_id="SRC-000185", anchor="src-000185-p3", source_type="journal"),
        ],
    )
    ledger.append_read(
        repository,
        session_id,
        _read(ref="src-000184-p1", citation="SRC-000184 ¶1", text="A blue heron flew over."),
    )
    ledger.append_read(
        repository,
        session_id,
        _read(ref="SUB-people/bob", citation="SUB-people/bob", text="Bob is a contractor."),
    )

    path = ledger.event_path(repository, session_id)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    read_events = [e for e in events if e["tool"] == "read"]
    search_events = [e for e in events if e["tool"] == "search_text"]

    manifest = build_context_manifest(repository, session_id)

    # Every read event's citation and measured token count appears exactly
    # once, under records_loaded or entries_resolved.
    all_read_items = manifest["records_loaded"] + manifest["entries_resolved"]
    assert sorted((item["ref"], item["tokens"]) for item in all_read_items) == sorted(
        (e["served"][0], e["tokens"]) for e in read_events
    )
    assert {item["ref"] for item in manifest["records_loaded"]} == {"SRC-000184", "SRC-000184 ¶1"}
    assert {item["ref"] for item in manifest["entries_resolved"]} == {"SUB-people/bob"}

    # The one search event's query, filters and hits reappear verbatim.
    (search,) = manifest["searches"]
    (search_event,) = search_events
    assert search["query"] == search_event["query"]
    assert search["filters"] == search_event["filters"]
    assert [r["anchor"] for r in search["results"]] == search_event["served"]

    # src-000184-p1 was read afterwards; src-000185-p3 never was.
    by_anchor = {r["anchor"]: r["read"] for r in search["results"]}
    assert by_anchor == {"src-000184-p1": True, "src-000185-p3": False}


# --- the basis statement ------------------------------------------------


def test_the_manifest_states_its_own_completeness_basis(tmp_path):
    manifest = build_context_manifest(_repo(tmp_path), "SES-test")

    assert manifest["basis"] == BASIS
    assert "events.jsonl" in BASIS
    assert "outside" in BASIS


# --- a malformed ledger --------------------------------------------------


def test_a_malformed_events_line_names_the_file_and_line(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read())
    path = ledger.event_path(repository, "SES-test")
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")

    with pytest.raises(SessionError, match=r"events\.jsonl.*line 2"):
        build_context_manifest(repository, "SES-test")


# --- deriving and persisting context-manifest.json -----------------------


def test_derive_context_manifest_writes_the_file_beside_events_jsonl(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read())

    result = derive_context_manifest(repository, "SES-test")

    assert isinstance(result, ManifestResult)
    assert result.changed is True
    assert result.manifest_path == manifest_path(repository, "SES-test")
    assert result.manifest_path.parent == ledger.event_path(repository, "SES-test").parent
    written = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert written["records_loaded"][0]["ref"] == "SRC-000184"


def test_re_deriving_an_unchanged_manifest_is_a_no_op(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read())
    derive_context_manifest(repository, "SES-test")

    result = derive_context_manifest(repository, "SES-test")

    assert result.changed is False


def test_re_deriving_a_manifest_that_changed_is_refused(tmp_path):
    repository = _repo(tmp_path)
    ledger.append_read(repository, "SES-test", _read())
    derive_context_manifest(repository, "SES-test")
    ledger.append_read(repository, "SES-test", _read(ref="SRC-000185", citation="SRC-000185"))

    with pytest.raises(SessionError, match="immutable"):
        derive_context_manifest(repository, "SES-test")


# --- no surface renders a token figure (part 14 §40, ADR-0001) -----------

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_PACKAGE = REPO_ROOT / "src" / "memoria" / "web"
GENERATED_UI_TYPES = REPO_ROOT / "ui" / "src" / "api" / "schema.d.ts"


def test_no_author_facing_surface_exposes_a_token_figure():
    """Part 14 §40 (as amended by ADR-0001) bans token figures from every
    author-facing view, without exception. The FastAPI app (`memoria.web`)
    is the backend those views are served from, and its generated
    TypeScript client (`ui/src/api/schema.d.ts`) is what a view could
    render straight through - so this scans both for the word rather than
    trusting that a future route remembers the rule. `memoria.mcp` (the
    model-facing tool surface, #29) and `memoria.context_manifest` itself
    are deliberately not scanned: they are not "the interface" §40 means.
    """
    surface_files = sorted(WEB_PACKAGE.rglob("*.py"))
    assert surface_files, "no memoria.web sources found - has the package moved?"
    if GENERATED_UI_TYPES.is_file():
        surface_files.append(GENERATED_UI_TYPES)

    for path in surface_files:
        text = path.read_text(encoding="utf-8").lower()
        assert "token" not in text, f"{path} names a token figure - part 14 §40 bans it"
