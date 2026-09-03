"""Normalization invented nothing - the M3 gate's step 7, as a test (#26).

The gate walk ends by putting two things side by side: the paragraph the
slide-over served for a citation, and the raw, unnormalized file it came
from. A person compares a sentence and satisfies themselves that the
converter did not write anything nobody said. That comparison was the point
of the whole gate and, until this file, was checked nowhere - not in pytest,
where the converter tests assert against expected paragraphs rather than
against the original bytes, and not in vitest, which never sees a raw file.

So it is checked here, over the same two HTTP routes the panel and "Open
original" actually call, against every fixture the email converter handles.

**What "verbatim" is, and where it stops.** The claim held here is
containment: every paragraph a record carries appears, character for
character, inside the text `GET /sources/{id}/raw` serves. It is deliberately
one-directional - the raw file has far more in it than the record does
(headers, the ZL footer, an excised quoted reply), and dropping material is
what a converter is for. Inventing material is what it must never do.

The claim is also bounded by transfer encoding, and the bound is worth
stating because a future fixture will find it. `read_raw_source` serves the
file decoded as UTF-8 but otherwise untouched, so a body written in
quoted-printable reaches the reader as `=\\n`-wrapped source text while the
record carries the decoded lines. Today's fixtures include a
quoted-printable message (`plain.eml`) whose *body* happens to need no soft
wraps, so containment holds for it too. If this test ever fails on a new
fixture, the question to ask first is which of the two it is: a converter
that invented text - a real defect - or a body whose encoding means the
reader is comparing against source rather than against text, in which case
the gate's step 7 needs to say so rather than this assertion being relaxed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memoria.index import build_index
from memoria.normalize import normalize
from memoria.records import load, read_all
from memoria.repository import Repository
from memoria.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "enron"


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """Every `.eml` fixture normalized, indexed and served, exactly the way
    `scripts/gate-m3.sh` prepares the walk's own repository."""
    root = tmp_path_factory.mktemp("fidelity")
    evidence_root = root / "evidence"
    raw_root = evidence_root / "raw"
    raw_root.mkdir(parents=True)
    for path in sorted(FIXTURES.glob("*.eml")):
        shutil.copy(path, raw_root / path.name)

    repository_root = root / "repo"
    repository_root.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=repository_root, check=True, capture_output=True
    )
    repository = Repository(root=repository_root, evidence_root=evidence_root)

    report = normalize(repository, evidence_root)
    assert report.converted, "the fixtures no longer produce any record"
    assert not report.failed, report.failed

    build_index(repository, read_all(repository))
    with TestClient(create_app(repository=repository)) as client:
        yield repository, report.converted, client


def _record_ids(served):
    return served[1]


def test_the_fixtures_still_exercise_the_converter(served):
    """A guard on this file's own worth: if the fixtures stop converting,
    every assertion below passes over an empty list."""
    _, record_ids, _ = served
    assert len(record_ids) >= 5


def test_every_served_paragraph_is_verbatim_in_the_original(served):
    """The gate's comparison, over the whole corpus rather than one sentence.

    Read through `/api/read` and `/api/sources/{id}/raw` rather than off
    disk, because those two routes are what the slide-over and "Open
    original ↗" call - a record that was faithful but a route that reshaped
    what it served would pass a check made on the records alone.
    """
    repository, record_ids, client = served

    compared = 0
    for record_id in record_ids:
        raw = client.get(f"/api/sources/{record_id}/raw")
        assert raw.status_code == 200, raw.text
        original = raw.json()["text"]

        for number in range(1, len(load(repository, record_id).paragraphs) + 1):
            anchor = f"{record_id.lower()}-p{number}"
            citation = client.get("/api/read", params={"ref": anchor})
            assert citation.status_code == 200, citation.text
            text = citation.json()["text"]

            assert text in original, (
                f"{anchor} was served text that is not in "
                f"{load(repository, record_id).original_file} verbatim - "
                "either the converter invented it, or this body's transfer "
                "encoding means the raw file holds source rather than text "
                "(see this module's docstring):\n"
                f"served: {text!r}"
            )
            compared += 1

    assert compared >= 5, "too few paragraphs compared for this to mean much"


def test_the_original_is_more_than_what_was_served(served):
    """The other half of "invented nothing": the converter *drops* material,
    and the reader has to be able to see it did. A record whose paragraphs
    reproduced the whole file would pass the test above trivially and would
    also mean the apparatus - headers, footers, the excised quoted reply -
    had leaked into the evidence text.
    """
    repository, record_ids, client = served

    for record_id in record_ids:
        original = client.get(f"/api/sources/{record_id}/raw").json()["text"]
        # The ZL production's stray header line, in every fixture and in no
        # record (`test_enron_fixtures.py` owns why it is there at all).
        assert "Microsoft Mail Internet Headers Version 2.0" in original

        served_text = " ".join(load(repository, record_id).paragraphs)
        assert "Microsoft Mail Internet Headers" not in served_text
        assert len(served_text) < len(original)


def test_the_locator_the_reader_follows_is_served_with_the_original(served):
    """`original_locator` is a human-readable pointer, not a byte offset
    (docs/normalized-record-schema.md), and it is what makes the comparison
    findable in a file with more than one message in it. The raw route
    carries it, so the gate's step 7 has something to read above the bytes.
    """
    repository, record_ids, client = served

    for record_id in record_ids:
        payload = client.get(f"/api/sources/{record_id}/raw").json()
        assert payload["original_locator"]
        assert payload["original_locator"] == load(repository, record_id).original_locator
