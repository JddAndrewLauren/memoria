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

`[dev]` pulls in the `[mcp]` extra, so the MCP server below is importable and
its tests run. `pip install memoria` on its own installs the core and the CLI
only — the MCP SDK brings a web-server stack with it, and the core's own
runtime dependency is PyYAML alone.

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

## The MCP server

Memoria is an MCP server, and Claude Code in this repo is the client
(`docs/poc-plan.md` §3). It exposes one tool so far:

```
read(ref)
```

`read` serves any stable reference verbatim — a record ID (`SRC-000184`), one
paragraph of one (`SRC-000184 P17`, `#src-000184-p17`, or a search result's
anchor as-is), or a repository-relative path. A record ID with no paragraph
returns the record file exactly as it is on disk. Evidence is never summarized
in place of the text: `docs/tool-surface.md` records the forced signature, the
constraint behind it (**retrieval is a superset of grep**), and what the
surface deliberately does not do yet.

`.mcp.json` at the repo root registers it, so Claude Code offers it in this
repo and in every worktree without per-machine configuration. Approve it once
when prompted; `/mcp` shows its state in a session and `claude mcp list`
outside one.

To run it by hand:

```
.venv/bin/python -m memoria.mcp --repo-root .
```

It speaks JSON-RPC over stdio, so it is not interactive — a client drives it.

**There are no records to read on a fresh checkout**, because nothing produces
them (see *No evidence corpus* above). `read` says so rather than failing
obscurely.

## CLI

```
.venv/bin/memoria --help
.venv/bin/memoria validate
.venv/bin/memoria rebuild
.venv/bin/memoria checkpoint
```

`memoria validate` verifies that every raw file in the evidence corpus matches
the hash recorded in its manifest, and exits non-zero, naming the offending file,
if a raw file has been modified or is missing. It also checks every normalized
record under `sources/normalized/` for a `SRC-` ID reference that does not
resolve to an actual record.

`memoria rebuild` deletes and regenerates all derived state — the normalized
records under `sources/normalized/`, the SQLite FTS5 full-text search index at
`.memoria/index.db`, and the `changes/` projection of `CHG-` commits (all
gitignored) — from evidence and git history, losing nothing (§42: derived
state carries no authority and can always be thrown away).

**`rebuild` has no normalizer to call.** With the corpus retired it regenerates
the index from whatever records are already on disk and reports that no producer
is wired in. Restoring it is part of choosing a corpus, not a gap to patch.

`memoria checkpoint` commits tracked, durable files with uncommitted
modifications — outside edits made in Obsidian or another editor, never
untracked files or Derived state — as one commit under one `CHG-` id
(ADR-0008). It also runs automatically before a machine actor (the Curator,
an AI write) writes to durable files, since that is the moment the dirty-tree
rule stops shielding a file the author left uncommitted. On a clean tree it
makes no commit and says so.

Use `memoria.index.search(db_path, query)` to query the index; pass
`exclude_editorial=True` to search evidence records only, excluding editorial
voice.
