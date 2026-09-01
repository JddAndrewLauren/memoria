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
reference that does not resolve to an actual record.

`memoria normalize` reads the journal volumes (J01, J02) from the evidence
corpus and writes one normalized Markdown record per dated entry to
`sources/normalized/` (gitignored — regenerate on demand; see
`docs/normalized-record-schema.md` for the schema and the `SRC-` ID /
paragraph-anchor conventions).

`memoria rebuild` deletes and regenerates all derived state — the normalized
records under `sources/normalized/` and the SQLite FTS5 full-text search
index at `.memoria/index.db` (both gitignored) — from evidence, losing
nothing (§42: derived state carries no authority and can always be thrown
away). Use `memoria.index.search(db_path, query)` to query the index; pass
`exclude_editorial=True` to search evidence records only, excluding editorial
voice.
