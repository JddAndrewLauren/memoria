# Memoria

A system for writing a book from a large personal archive. See `CONTEXT.md` for
domain vocabulary and `docs/plan/` for the build plan.

## No evidence corpus

**The Thoreau proof-of-concept corpus was retired on 2026-09-01, and no
replacement has been chosen.** See `docs/open-problems.md` §2.4 for the decision,
and issue #1 for what it cost.

Practically, this means:

- Nothing produces normalized records today. The ingestion layer written for that
  corpus — the normalizer, editorial segregation, year resolution,
  cross-reference extraction and the benchmark answer key — was removed with it.
- `docs/normalized-record-schema.md` survives as the **contract** a future
  normalizer must satisfy. It is what `memoria.index` and `memoria validate`
  already read, and it is what to build against.
- The test suite runs with no corpus present and no environment set. If a test
  ever needs one, that is a bug in the test.

## Installing

From a clean checkout, in a virtualenv:

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Running the tests

```
.venv/bin/pytest tests/ -q
```

This is the one command every issue uses to run the suite. It needs no evidence
corpus and no environment variables.

### Evidence corpus location

When an evidence corpus exists, it lives in a **sibling repository, read-only**,
and code resolves it via the `MEMORIA_EVIDENCE_ROOT` environment variable. There
is no default: the commands that read evidence fail with a clear message when it
is unset, rather than silently probing a path that is not there.

The variable is required only **at the point of use** — by the commands that
actually read evidence. Anything reading only this repo's own
`sources/normalized/` records never needs it set.

## CLI

```
.venv/bin/memoria --help
.venv/bin/memoria validate
.venv/bin/memoria rebuild
```

`memoria validate` verifies that every raw file in the evidence corpus matches
the hash recorded in its manifest, and exits non-zero, naming the offending file,
if a raw file has been modified or is missing. It also checks every normalized
record under `sources/normalized/` for a `SRC-` ID reference that does not
resolve to an actual record.

`memoria rebuild` deletes and regenerates all derived state — the normalized
records under `sources/normalized/` and the SQLite FTS5 full-text search index at
`.memoria/index.db` (both gitignored) — from evidence, losing nothing (§42:
derived state carries no authority and can always be thrown away).

**`rebuild` has no normalizer to call.** With the corpus retired it regenerates
the index from whatever records are already on disk and reports that no producer
is wired in. Restoring it is part of choosing a corpus, not a gap to patch.

Use `memoria.index.search(db_path, query)` to query the index; pass
`exclude_editorial=True` to search evidence records only, excluding editorial
voice.
