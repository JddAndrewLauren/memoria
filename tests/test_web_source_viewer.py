"""``GET /api/read`` - the slide-over citation panel's read (#25, §19.9).

The one generic reference read the panel uses in both directions: a
``SRC-`` paragraph anchor serves the cited text, its record and its
curated-overlay backlinks (#20); a ``SUB-x/y`` entry reference is what a
backlink resolves to, traversing back into the same panel. This route
wraps ``memoria.records.read`` exactly - the same core the MCP tool
surface's ``read(ref)`` calls - so these tests exercise the adapter, not
the composition logic ``tests/test_read_ref.py`` already covers.
"""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from memoria import extraction as ex
from memoria.index import build_index
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown
from memoria.web.app import create_app


def _record(**overrides):
    fields = dict(
        id="SRC-000184",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22., 1845",
        date_confidence="inferred",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I, entry dated Oct. 22.",
        paragraphs=["A blue heron flew over.", "Second paragraph here."],
    )
    fields.update(overrides)
    return NormalizedRecord(**fields)


def _write_entry(tmp_path, entry):
    subject_slug = entry.id.split("/", 1)[0][len("SUB-") :]
    slug = entry.id.split("/", 1)[1]
    directory = tmp_path / "subjects" / subject_slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{slug}.md").write_text(entry_to_markdown(entry))


def _repo(tmp_path, *records, entries=()):
    """A git-backed repository with ``records`` normalized, indexed, and
    ``entries`` written to disk - the shape a decorated read's overlay
    needs beneath it (mirrors ``test_read_ref.py``'s ``_overlay_repo``)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    for entry in entries:
        _write_entry(tmp_path, entry)
    records = list(records) or [_record()]
    write_normalized_records(records, tmp_path / NORMALIZED_RELATIVE_PATH)
    repository = Repository(root=tmp_path)
    build_index(repository, records)
    return repository


def _client(repository):
    return TestClient(create_app(repository=repository)).__enter__()


def _place(repository, anchor, entry_id, match_term):
    ex.record_extraction(
        repository,
        anchor,
        ex.ParagraphExtraction(placements=(ex.ProposedPlacement(entry_id, match_term),)),
    )
    ex.derive(repository)


# --- a citation into evidence -----------------------------------------------


def test_read_serves_the_cited_paragraph_its_record_and_its_backlinks(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _repo(tmp_path, entries=[entry])
    _place(repository, "src-000184-p1", "SUB-people/bob", "heron")
    client = _client(repository)

    body = client.get("/api/read", params={"ref": "src-000184-p1"}).json()

    assert body["ref"] == "src-000184-p1"
    assert body["text"] == "A blue heron flew over."
    assert body["paragraph"] == 1
    assert body["record"]["id"] == "SRC-000184"
    assert body["overlay"] == {
        "entry_links": ["SUB-people/bob"],
        "exclusions": [],
        "citing_settlements": [],
    }


def test_read_gives_a_fully_shaped_empty_overlay_when_nothing_links_the_paragraph(
    tmp_path,
):
    repository = _repo(tmp_path)
    client = _client(repository)

    body = client.get("/api/read", params={"ref": "SRC-000184 P1"}).json()

    assert body["overlay"] == {
        "entry_links": [],
        "exclusions": [],
        "citing_settlements": [],
    }


def test_read_of_a_whole_record_carries_no_paragraph_or_overlay(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    body = client.get("/api/read", params={"ref": "SRC-000184"}).json()

    assert body["record"]["id"] == "SRC-000184"
    assert body["paragraph"] is None
    assert body["overlay"] is None


def test_read_of_an_unresolvable_reference_is_a_404(tmp_path):
    repository = _repo(tmp_path)
    client = _client(repository)

    response = client.get("/api/read", params={"ref": "SRC-000999 P1"})

    assert response.status_code == 404


# --- a backlink into an entry, traversing the other direction --------------


def test_read_resolves_a_backlinks_entry_reference_for_the_reverse_traversal(tmp_path):
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="Bob's own words.")
    repository = _repo(tmp_path, entries=[entry])
    client = _client(repository)

    body = client.get("/api/read", params={"ref": "SUB-people/bob"}).json()

    assert body["ref"] == "SUB-people/bob"
    assert "Bob's own words." in body["text"]
    assert body["record"] is None
    assert body["paragraph"] is None
    assert body["overlay"] is None


# --- author reads are not ledgered ------------------------------------------


def test_viewer_reads_write_nothing_to_events_jsonl(tmp_path):
    """#25's acceptance criteria: there is no second read path, and an
    author's own read in the interface is never served to a session -
    ``sessions/`` should not even exist afterwards."""
    entry = Entry(id="SUB-people/bob", match_terms=["heron"], body="")
    repository = _repo(tmp_path, entries=[entry])
    _place(repository, "src-000184-p1", "SUB-people/bob", "heron")
    client = _client(repository)

    assert client.get("/api/sources/SRC-000184").status_code == 200
    assert client.get("/api/sources/SRC-000184/raw").status_code == 404  # no evidence root
    assert client.get("/api/read", params={"ref": "src-000184-p1"}).status_code == 200
    assert client.get("/api/read", params={"ref": "SUB-people/bob"}).status_code == 200

    assert not (repository.root / "sessions").exists()
