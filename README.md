# Memoria

A system for writing a book from a large personal archive. See `CONTEXT.md` for
domain vocabulary and `docs/plan/` for the build plan.

## No evidence corpus

**The Thoreau proof-of-concept corpus was retired on 2026-09-01, and no
replacement has been chosen.** See `docs/open-problems.md` §2.4 for the decision,
and issue #1 for what it cost.

Practically, this means:

- `memoria normalize` produces normalized records from any raw unit whose suffix
  has a registered converter — plain text, docx and pdf today, with email owed
  by #78. What was removed with that corpus is the rest of its ingestion
  layer: editorial segregation, year resolution, cross-reference extraction
  and the benchmark answer key.
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

`[dev]` pulls in the `[mcp]`, `[web]`, `[convert]` and `[graph]` extras, so
the MCP server, the FastAPI app below, the docx/pdf converters and the
extraction's clustering are all importable and their tests run. `pip install
memoria` on its own installs the core and the CLI only — the core's own
runtime dependency is PyYAML alone, and an extraction on a core-only install
produces candidates and placements but no clusters, and says so.

`[graph]` is networkx. `graspologic-native` (Leiden, and the preferred backend)
is deliberately not in any extra: if `[dev]` pulled it, the suite would only
ever exercise Leiden and never the networkx fallback most installs actually
run. Install it by hand for Leiden.

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

## The FastAPI app

The third adapter over the core (#64, `docs/adr/0002-ui-is-a-react-client.md`),
serving JSON under `/api` for the React client at `ui/` (#24). Same rule the
MCP server keeps: domain logic stays in `memoria.*`, and this app calls it and
shapes the result — it opens no SQLite database and reads no evidence file
directly.

```
.venv/bin/python -m uvicorn memoria.web.app:create_app --factory --reload
```

Four reads exist today: list sources (`GET /api/sources`, filterable by
`source_type`, `date_confidence` and `contemporaneous`, paginated), read one
source (`GET /api/sources/{id}`), the raw un-normalized file behind one
(`GET /api/sources/{id}/raw`), and search (`GET /api/search`, wrapping
`memoria.index.search`). See `docs/tool-surface.md` for what each filter
means and `src/memoria/web/schemas.py` for the response shapes.

No auth, HTTPS or remote-access code exists — localhost, one machine
(`docs/poc-plan.md` §5).

### Regenerating the TypeScript client types

```
scripts/generate-web-types.sh
```

Writes `ui/src/api/schema.d.ts` from the app's OpenAPI schema. Run it after
changing a route or a response model in `src/memoria/web/`, and commit the
result — `tests/test_web_types.py` fails the suite when the committed file
goes stale against the schema, which is the mitigation the ADR names for a
two-language stack in a repo with no CI: a backend field rename becomes a
compile error in `ui/`, not a runtime surprise nobody sees.

## CLI

```
.venv/bin/memoria --help
.venv/bin/memoria validate
.venv/bin/memoria normalize
.venv/bin/memoria rebuild
.venv/bin/memoria rebuild --recurrence-threshold 3
.venv/bin/memoria rebuild --reset-cache
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

**`rebuild` does not normalize.** It regenerates the index from whatever records
are already on disk; producing those records is `memoria normalize`'s job, and
the two stay separate so a reindex never rewrites evidence-derived records. On
an empty corpus `rebuild` indexes nothing and says so — choosing a corpus is
what fills it, not a gap to patch.

It also recomputes the extraction's derived rows: placements, candidates and
their recurrence ranking, relations, clusters and proposed match terms (#17).
That step calls **no model** — accepting a proposed match term and rebuilding
moves what is placed without re-reading a single paragraph. `--recurrence-threshold`
sets the filter a candidate must clear (default 5); rejected candidates are kept
and stay listable either way.

**One table survives a rebuild: the extraction's memo cache.** It holds what a
model read, paragraph by paragraph, and a rebuild has no model to regenerate it
with — so `rebuild` drops and rewrites everything else in `.memoria/index.db`
and leaves that alone. `--reset-cache` discards it too, and is the only way to;
the next extraction then re-reads the whole archive.

**`rebuild` never promotes.** Auto-promotion creates durable, committed entry
files, and it belongs to the author-launched extraction pass, never to a
command whose whole contract is that everything it touches is disposable.

## The extraction

The extraction is the subject system's one candidate engine (part 06 §8.4,
`docs/adr/0005-extraction-is-the-candidate-engine.md`). A model reads every
paragraph of the archive for what it mentions, and from that Memoria proposes
candidates under every subject, clusters offered under Themes and Arcs, and
match terms on the entries that already exist.

It is **author-launched and runs nowhere else**: there is no scheduler and no
model-driving service (`docs/poc-plan.md` §3), and nothing that needs a model
runs unasked (part 08 §12.1). Run it from a Claude Code session in the
repository with the `extraction` skill:

```
/extraction
```

The skill drives the `extraction_*` tools on the MCP server, which hand
paragraphs out and take structured readings back — the server itself calls no
model and cannot. A pass that runs out of capacity stops cleanly and resumes
where it stopped; nothing is lost and nothing repeats, because what is left to
do is a query over what has no cached reading rather than a cursor to keep.
`docs/tool-surface.md` records the tools and why they are shaped as they are.

What the pass produces waits for the author. Candidates above the recurrence
filter, the ones it set aside, the mentions nothing licensed and every
cluster are all listable from the same session (`extraction_candidates`,
`extraction_unplaced_forms`, `extraction_cluster`), and a candidate or cluster
becomes an entry only when the author names it to
`extraction_promote_candidate` or `extraction_promote_cluster` — or when its
subject declares `auto-promote: yes`, which Themes and Arcs never do.

`memoria checkpoint` commits tracked, durable files with uncommitted
modifications — outside edits made in Obsidian or another editor, never
untracked files or Derived state — as one commit under one `CHG-` id
(ADR-0008). It also runs automatically before a machine actor (the Curator,
an AI write) writes to durable files, since that is the moment the dirty-tree
rule stops shielding a file the author left uncommitted. On a clean tree it
makes no commit and says so.

Use `memoria.index.search(repository, query, filters)` to query the index —
it takes the frozen `Repository` value, like every other core read (ADR-0004).
Pass `SearchFilters(contemporaneous=True)` to search evidence records only,
excluding retrospective editorial commentary; `SearchFilters.source_type` is
an exact match with no negation, so narrowing to one type (not "everything
except editorial") is what a `source_type` filter alone can express. See
`docs/tool-surface.md`'s `search_text` section for the full filter set.
