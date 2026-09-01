# Memoria

A system for writing a book from a large personal archive. See `CONTEXT.md` for
domain vocabulary and `docs/plan/` for the build plan.

## Installing

From a clean checkout, in a virtualenv:

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Running the tests

```
MEMORIA_EVIDENCE_ROOT=/absolute/path/to/thoreau-evidence .venv/bin/pytest tests/ -q
```

This is the one command every issue in this batch uses to run the suite.

## The M0 check-suite

```
MEMORIA_EVIDENCE_ROOT=/absolute/path/to/thoreau-evidence .venv/bin/python scripts/m0-check.py
```

One command for the whole M0 gate: `memoria validate`, `memoria rebuild` over the full
corpus, and the test suite, reporting pass/fail per check. Unlike bare `pytest`, it
refuses to run without the evidence corpus and treats a skipped real-corpus check as a
failed one — without the corpus every reconciliation against `RECON.md` skips and the
suite would otherwise report green having checked nothing.

`docs/m0-check-suite.md` holds the reconciliation table (what each `RECON.md` count was
re-derived to, and why it differs) and the map from every mismatch found during M0 to
the regression test that catches it again.

### Evidence corpus location

The raw evidence corpus (`thoreau-evidence`) is a sibling repository, read-only.
Code and tests resolve it via the `MEMORIA_EVIDENCE_ROOT` environment variable,
which defaults to `../thoreau-evidence` (the right default when running from
this repo's own root, next to the sibling checkout). Set it explicitly to an
absolute path when running from a location where the relative default does not
resolve, such as a `.claude/worktrees/issue-<n>` sub-worktree.

## CLI

```
.venv/bin/memoria --help
.venv/bin/memoria validate
.venv/bin/memoria normalize
.venv/bin/memoria rebuild
```

`memoria validate` verifies that every raw file in the evidence corpus matches
the hash recorded in `raw/gutenberg/manifest.yaml`, and exits non-zero, naming
the offending file, if a raw file has been modified or is missing. It also
checks every normalized record under `sources/normalized/` for a `SRC-` ID
reference that does not resolve to an actual record, and checks that every
answer-key row still quotes the paragraphs it names — the key is committed
while the records it points into are derived, so the two can otherwise drift
apart silently.

`memoria normalize` reads the journal volumes (J01, J02) and the letters
volume from the evidence corpus and writes one normalized Markdown record
per dated entry or letter to `sources/normalized/` (gitignored — regenerate
on demand; see `docs/normalized-record-schema.md` for the schema and the
`SRC-` ID / paragraph-anchor conventions), plus `sources/normalized/recipients.yaml`
(the letters' recipients) and `sources/normalized/cross-references.yaml`
(cross-references extracted from editorial apparatus). Editorial apparatus
(footnotes, front/back matter, and other non-evidence text) is segregated
into its own Markdown records under `sources/editorial/` (also gitignored).
The two audit targets (*Walden*, *A Week*) are normalized too, one record
per chapter, under `source_type: book`.

It also writes `benchmark/answer-key.yaml`, which — unlike everything else
above — **is committed**. The key resolves each cross-reference's
target-side citation to a span of held book paragraphs, by aligning the
1906 Manuscript and 1894 Riverside scans the footnotes cite against the
held text and keeping only the links where the two editions agree. It uses
no part of Memoria's retrieval, deliberately: see
`docs/answer-key-protocol.md`.

`memoria rebuild` deletes and regenerates all derived state — the normalized
records under `sources/normalized/`, the editorial records under
`sources/editorial/`, and the SQLite FTS5 full-text search index at
`.memoria/index.db` (all gitignored) — from evidence, losing nothing (§42:
derived state carries no authority and can always be thrown away).
`sources/normalized/`, `sources/editorial/` and `benchmark/answer-key.yaml`
come out byte-identical to what `memoria normalize` produces. Use `memoria.index.search(db_path, query)`
to query the index; pass `exclude_editorial=True` to search evidence records
only, excluding editorial voice.
