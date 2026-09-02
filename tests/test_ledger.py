"""The read ledger (#13): what the tool surface served, and to whom.

``events.jsonl`` is core (ADR-0004's "adapters shape, they do not act"
extended to writing): the MCP server calls this module after a served read
or search, and this module owns the file. Behaviour is exercised through the
module's public functions and the file they write, never through a private
helper.
"""

from __future__ import annotations

import json
import re

from memoria import ledger
from memoria.index import ReadOverlay, SearchFilters, SearchResult
from memoria.records import Read
from memoria.repository import Repository


def _read(**overrides):
    fields = dict(
        ref="SRC-000184",
        citation="SRC-000184",
        text="A blue heron flew over.",
    )
    fields.update(overrides)
    return Read(**fields)


def test_event_path_nests_by_year_and_month_for_a_documented_session_id(tmp_path):
    """Part 04 §2's tree nests a session under ``sessions/<YYYY>/<MM>/``."""
    repository = Repository(root=tmp_path)

    path = ledger.event_path(repository, "SES-20260912-1432-abcdef")

    assert path == tmp_path / "sessions" / "2026" / "09" / "SES-20260912-1432-abcdef" / "events.jsonl"


def test_event_path_falls_back_flat_for_a_non_conforming_session_id(tmp_path):
    """A caller-supplied id that does not follow part 04 §4's ``SES-``
    form has no year/month to nest by - documented in docs/tool-surface.md
    as the deviation, rather than guessed at."""
    repository = Repository(root=tmp_path)

    path = ledger.event_path(repository, "my-custom-session")

    assert path == tmp_path / "sessions" / "my-custom-session" / "events.jsonl"


def test_a_served_read_appends_one_line_naming_the_reference_and_session(tmp_path):
    repository = Repository(root=tmp_path)

    ledger.append_read(repository, "SES-test", _read())

    path = tmp_path / "sessions" / "SES-test" / "events.jsonl"
    (line,) = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(line)
    assert event["session_id"] == "SES-test"
    assert event["tool"] == "read"
    assert event["ref"] == "SRC-000184"
    assert event["served"] == ["SRC-000184"]
    assert "timestamp" in event


def test_a_decorated_read_is_ledgered_like_any_other_read(tmp_path):
    """The curated overlay (#20) rides on `Read.overlay`; `append_read`
    ledgers the reference and citation exactly as it does for an
    undecorated read - decoration earns no separate code path here."""
    repository = Repository(root=tmp_path)
    decorated = _read(
        ref="SRC-000184 P1",
        citation="SRC-000184 ¶1",
        text="A blue heron flew over.",
        overlay=ReadOverlay(
            entry_links=["SUB-people/bob"], exclusions=[], citing_settlements=[]
        ),
    )

    ledger.append_read(repository, "SES-test", decorated)

    path = tmp_path / "sessions" / "SES-test" / "events.jsonl"
    (line,) = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(line)
    assert event["ref"] == "SRC-000184 P1"
    assert event["served"] == ["SRC-000184 ¶1"]


def test_a_served_search_appends_a_line_naming_the_query_filters_and_hits(tmp_path):
    repository = Repository(root=tmp_path)
    filters = SearchFilters(source_type="journal")
    results = [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")]

    ledger.append_search(repository, "SES-test", "heron", filters, results)

    path = tmp_path / "sessions" / "SES-test" / "events.jsonl"
    (line,) = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(line)
    assert event["session_id"] == "SES-test"
    assert event["tool"] == "search_text"
    assert event["query"] == "heron"
    assert event["filters"] == {
        "event_date": None,
        "recorded_date": None,
        "source_type": "journal",
        "contemporaneous": None,
        "from_": None,
        "to": None,
    }
    assert event["served"] == ["src-000184-p1"]


def test_the_ledger_is_append_only_existing_lines_are_never_rewritten(tmp_path):
    repository = Repository(root=tmp_path)
    path = tmp_path / "sessions" / "SES-test" / "events.jsonl"

    ledger.append_read(repository, "SES-test", _read(ref="SRC-000184"))
    first_line = path.read_text(encoding="utf-8")

    ledger.append_read(repository, "SES-test", _read(ref="SRC-000185", citation="SRC-000185"))

    assert path.read_text(encoding="utf-8").startswith(first_line)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_several_calls_reconstruct_exactly_what_was_served(tmp_path):
    repository = Repository(root=tmp_path)

    ledger.append_read(repository, "SES-test", _read(ref="SRC-000184"))
    ledger.append_search(
        repository,
        "SES-test",
        "heron",
        None,
        [SearchResult(src_id="SRC-000184", anchor="src-000184-p1", source_type="journal")],
    )
    ledger.append_read(
        repository, "SES-test", _read(ref="SRC-000184 P1", citation="SRC-000184 ¶1")
    )

    path = tmp_path / "sessions" / "SES-test" / "events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["tool"] for e in events] == ["read", "search_text", "read"]
    assert events[0]["served"] == ["SRC-000184"]
    assert events[1]["served"] == ["src-000184-p1"]
    assert events[2]["served"] == ["SRC-000184 ¶1"]


def test_session_id_from_env_uses_the_configured_value(monkeypatch):
    monkeypatch.setenv(ledger.SESSION_ID_ENV_VAR, "SES-fixed")

    assert ledger.session_id_from_env() == "SES-fixed"


def test_session_id_from_env_generates_one_when_unset(monkeypatch):
    """Part 04 §4's citable form is minute granularity: ``SES-20260912-1432``.
    A random suffix follows it, so the id stays parseable as that form by a
    caller that only wants the prefix, while remaining collision-resistant.
    """
    monkeypatch.delenv(ledger.SESSION_ID_ENV_VAR, raising=False)

    session_id = ledger.session_id_from_env()

    assert re.fullmatch(r"SES-\d{8}-\d{4}-[0-9a-f]{12}", session_id)


def test_generated_session_ids_do_not_collide_within_the_same_minute(monkeypatch):
    """Two servers spawned in the same minute must not share one id and
    silently merge their events into one file (second-granularity used to
    make exactly that possible)."""
    monkeypatch.delenv(ledger.SESSION_ID_ENV_VAR, raising=False)

    ids = {ledger.session_id_from_env() for _ in range(200)}

    assert len(ids) == 200
