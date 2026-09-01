# The tool surface

What Memoria exposes to a session model, and what is settled about it.
Implemented by `src/memoria/mcp/`, over the core read side that
`docs/adr/0004-the-read-side-is-functions-over-a-repository-value.md` places.

Part 11 §25 lists eleven candidate tools. This document records the ones whose
signatures are **forced** — closed, with a reason — and leaves the rest
explicitly open, so that "still open" is a statement someone made rather than
a gap nobody noticed.

| Tool | State |
|---|---|
| `read(ref)` | **Forced** — issue #11, below |
| `search_text(query, filters)` | **Forced** — issue #12, below |
| `search_global(query, filters, summarize)` | Open — issue #74, scheduled for M2 (ADR-0005). Settled 2026-09-01: `query` optional, a `level` filter, summaries served from the extraction pass and never generated on the call |
| `search_semantic(query, filters)` | Open — issue #81, scheduled for M2 (ADR-0007): a `sqlite-vec` table in the index file, a local CPU model at rebuild |
| `expand`, `timeline`, `grep_repo`, `trace`, `backlinks`, `list` | Open; §25 does not commit to shipping them |

## The constraint that binds all of it

From `poc-plan.md` §7, and it **may not be weakened**:

> retrieval must be a **superset of grep**: verbatim source text (never
> summarized-only), decorated with the curated overlay, a raw full-source read
> available, and every read ledgered in `events.jsonl`.

The reason is not purity. Evidence lives outside the session's working repo
and direct reads are routed back to the tools by a hook
(`.claude/hooks/route-evidence-reads.sh`, `poc-plan.md` §3). That hook is a
**router, not a wall** — Bash can still reach the files. It only works while
the tool returns *more* than a raw read does. The moment reading through the
tool is worse than `cat`, the router becomes an obstacle and people go around
it, and the ledger that makes the context manifest a record rather than a
request stops being complete.

So: the verbatim text is served unmodified and contiguously, and the
full-source read may never be removed or degraded.

## `read(ref)` — forced 2026-09-01, issue #11

```
read(ref: str) -> str
```

One tool, not a family. Dispatch is read off the reference, because the ID
scheme of part 04 §4 already names the type. The former per-type list
(`read_source`, `read_session`, `read_change`, …) was withdrawn by §25 as an
enumeration of kinds, and had already drifted.

### What it accepts

| Form | Serves | Where the form comes from |
|---|---|---|
| `SRC-000184` | the whole record, verbatim | part 04 §4 |
| `SRC-000184 ¶17` / `SRC-000184 P17` | that paragraph | part 04 §4's prose citation |
| `SRC-000184#src-000184-p17` | that paragraph | part 04 §4's markdown link |
| `#src-000184-p17` | that paragraph | the fragment alone |
| `src-000184-p17` | that paragraph | `index.SearchResult.anchor`, verbatim |
| `docs/poc-plan.md` | the file, verbatim | a repository-relative path |
| `SUB-people` | the subject's prompt, verbatim | part 04 §4, part 06 §8.1 |
| `SUB-people/bob` | the entry, verbatim | part 04 §4, part 06 §8.2 |

The bare anchor is accepted deliberately. `SearchResult` carries
`(src_id, anchor, source_type)`, so a search hit feeds straight back into
`read` — without it, #12 would have to reassemble a citation string inside an
adapter, which is the duplication §40.1 exists to forbid.

`SRC-` IDs are six digits, zero-padded. `SRC-184` is refused with a message
saying so, rather than guessed at.

Paths are repository-relative, and reads are confined to the repository by
**two** checks, because one is not enough. The reference is refused if it says
it leaves the tree — absolute, a drive letter, a `..` component, or any
backslash (one component on POSIX, three on Windows, and a rule that holds
only on the developer's platform is not a rule). The resolved path is then
refused if it turns out to leave the tree, which is the case a symlink makes:
the reference is an ordinary relative path and only the target escapes.

A reference is treated as an ID only when its kind is upper case, as part 04
§4 writes them. Without that, `open-problems.md` — a file in this repository —
was answered with "unknown reference kind OPEN-".

`SUB-` subject and entry slugs are lowercase, directory-name shaped
(`subjects/people/bob.md`, part 04 §2). `SUB-People` or `SUB-people/Bob` is
refused as a malformed subject reference rather than folded to lowercase, the
same call made for a malformed `SRC-` ID.

### What it returns

A record ID with no paragraph returns **the record file exactly as it is on
disk** — frontmatter, anchors and all, byte for byte what `cat` gives. That is
the raw undecorated full-source read the constraint requires.

**A full-source read is returned bare** — the file and nothing else, with no
header and no delimiter. It is the undecorated read, and it should be
indistinguishable from `cat` at the surface, not only in the value the core
returns. Path reads are bare for the same reason.

That was learned rather than designed. The first live read carried a `ref:`
line and a `---` above the record's own frontmatter opener; the reader saw two
consecutive `---` lines, took them for an empty pair, and reported the payload
as corrupted. The envelope was correct and the report was wrong — which is
precisely the problem. The routing hook is a router, not a wall, and a tool
whose output reads as damaged loses the traffic it depends on. The line was
redundant anyway: the record's frontmatter states its own `id`.

**A paragraph reference** returns that paragraph's bytes, with the record's
metadata in a header above a `---` delimiter — a paragraph genuinely does not
carry the fields a reader needs to judge it.

Two properties of that header are contracts, not styling:

- **The verbatim text appears contiguously and unmodified** — never wrapped,
  re-indented, escaped, or interleaved with anything.
- **There is exactly one delimiter convention.** The curated overlay (#20)
  appends after the text using it; it does not interleave. The full-source
  read has no delimiter because it has no decoration — that is what makes it
  the raw one.

`original_locator` is printed and never parsed. It is a pointer a person
follows, not an offset — issue #25 depends on that staying true.

**A `SUB-` read is bare too** — a subject's prompt or an entry's file,
exactly as it is on disk, with no header and no delimiter, for the same
reason a full-source `SRC-` read is (issue #16). An entry read resolves by
its frontmatter `id` rather than by filename, so a renamed entry file still
answers to the `SUB-x/y` it was created with.

### What it refuses, and how

Reference kinds part 04 §4 defines but this build does not resolve —
`SES-` (with or without a `#T` turn), `CHG-`, `CLM-`, `RES-`, `DEC-` — return
an error **naming the kind**, never a silent empty result. A kind that is not
part of the scheme at all is named too, and distinguished from one that is
merely unbuilt. `SUB-x` and `SUB-x/y` were on this list until issue #16.

Errors reach the model as `ToolError`, which is the SDK's anticipated-failure
type: the call comes back `is_error` with the message intact. Any other
exception is reported as `Error executing tool read` with the reason stripped,
which would be exactly the silent failure #11 forbids — so the adapter maps
the core's one error type onto it.

### What is deliberately still missing

- **No overlay.** Decoration with entry links, exclusions and citing
  settlements is issue #20, at M2.
- **No `raw` parameter.** Every read is undecorated today, so the
  full-source read is raw by accident rather than by contract. **#20 owes the
  parameter**: when it adds decoration it must also add the flag that turns it
  off, because "a raw full-source read remains available" is a constraint on
  the surface after M2, not just before it. This is the one part of the
  signature this slice did not force, and it is recorded here so that #20
  finds it rather than discovering it.
- **No raw *original*.** Reading the pre-normalization source at
  `original_file` is #64/#25's "Open original", not this.

## `search_text(query, filters)` — forced 2026-09-01, issue #12

```
search_text(query: str, filters: SearchFilters | None = None) -> str
```

The retrieval half of the minimum M1 tool surface: full-text search over the
FTS5 index (`memoria.index`), the other half of what §7's superset-of-grep
constraint needs alongside `read`.

**FTS5 and nothing else.** ADR-0007 admitted embeddings by choice, but
`search_semantic` (#81) is a separate tool over a separate `sqlite-vec`
table, scheduled for M2; ADR-0005's extraction is a candidate engine, not a
search index (`docs/open-problems.md` §2.2: "`search_text` stays FTS5").
This tool's result set is FTS5 hits, and cluster summaries are never served
here as evidence.

### The filters are implemented in the core, not the tool

`memoria.index.search(repository, query, filters)` takes the frozen
`Repository` value, like every other core read (ADR-0004) — the point at
which the function's `db_path` parameter was aligned to match, since #74 and
#81 inherit the shape. `build_index` was aligned the same way by #95, so
nothing in the module composes an index path from outside it. `SearchFilters` carries the four filters that have
something to filter on at M1:

- `event_date` — exact match against the record's verbatim frontmatter
  string
- `recorded_date` — exact match, same reason
- `source_type` — exact match (e.g. `"journal"`, `"editorial"`)
- `contemporaneous` — `true` excludes retrospective/editorial commentary
  added over the same ground; this is how §6's temporal discipline is
  enforced at retrieval time

All four are optional and compose (ANDed together). `record class` is not a
filter: §26 lists it only as a *potential* one, and nothing defines it in
`docs/normalized-record-schema.md` or on `NormalizedRecord`. Dates have no
sortable value in the schema (`date_confidence` runs `exact` … `unresolved`
with no ordering), so a range filter has nothing ordered to compare against —
exact/prefix match was the choice available, and exact match is what shipped.
Subject and entry filters (`person`, `theme`, `arc`, …) wait for M2, since
entries do not exist yet; they are never filters, because the entry filter
will cover every subject the author adds.

The filter values live in a plain (non-FTS) table keyed by paragraph anchor —
`paragraphs(anchor, src_id, source_type, event_date, recorded_date,
contemporaneous)` — written by `build_index` beside the FTS5 `records`
virtual table, not as extra `UNINDEXED` FTS5 columns. `memoria.index.
filter_predicate` is the one predicate builder that turns a `SearchFilters`
into `(sql, params)` against that table; `search()` joins FTS5 hits to it,
and #81 (a `sqlite-vec` table) and #74 (the extraction's placements,
relations, clusters and membership) are expected to join their own
paragraph-keyed rows to it the same way, rather than each keeping a second
copy of the metadata (§40.1).

Reachable without the MCP server — `memoria.index.search` is a plain core
function, exercised directly by `tests/test_index.py`.

### What it returns

Each `SearchResult` carries `(src_id, anchor, source_type)` and **no paragraph
text**. `search_text` renders one line per hit, ranked, giving both the `SRC-`
ID and the paragraph anchor — the anchor is `SearchResult.anchor` verbatim,
which `read(ref)` accepts with no reconstruction by the caller (the bare-anchor
form in the `read(ref)` table above exists specifically for this).

**A hit carries a match locator, not evidence** — settled 2026-09-01, issue
#95. `search(repository, query, filters, snippet=True)` adds a `snippet` to
each result: a truncated fragment of the *index's* copy of the paragraph, with
matched terms wrapped in `index.SNIPPET_MATCH_START` / `SNIPPET_MATCH_END`
(C0 control characters, so a mark can never be confused with the evidence's own
punctuation — brackets are real editorial syntax in this schema — and nothing
is ever interpolated as markup). It is the same category of thing as the line
`grep` prints. It is computed by FTS5 inside the query that already runs, so it
costs a column rather than a second pass or a file read.

It is **off by default**, and `search_text` leaves it off: the model gets
identifiers and reads evidence with `read(ref)`. The web adapter turns it on,
because the search dialog draws a fragment per hit (part 19 §19.8) and the
slide-over reads the full source when the reader clicks one (§19.9).

Three things follow from a snippet being a locator rather than evidence, and
each is held by a test:

- **Nothing ledgers it.** `append_search` records anchors, so `served` keeps
  meaning *supplied* and §33's manifest stays a record rather than a request.
- **`read(ref)` does not accept it.** A snippet falls through to the path
  fallback in `references.parse` and fails as a read; the anchor beside it is
  what resolves.
- **§42 is undisturbed.** The index is derived state carrying no authority, so
  a snippet out of it is a pointer that may go stale, never a quotation that
  may go wrong. Evidence always comes from the record file, through `read`.

**Full paragraph hydration was rejected**, not deferred. It is cheap — the text
is already in the FTS5 `records` table — but `search()` has no `LIMIT`, so
hydrating would let one call dump every matching paragraph into a session's
context, against part 11's tier list, which keeps "search results" and "full
sources" as separate Tier 4 on-demand items. It would also serve evidence out
of derived state and make the ledger's `served` line a lie by omission. If
something later needs *authoritative* paragraph text for a result list — a
plausible turn for `search_global` (#74) — the shape is a separately-ledgered
hydration call over the record files, not a widened `search`.

No match, and no built index yet — every fresh clone, since `.memoria/` is
gitignored — both render `"No results."` rather than an empty string or a
driver exception. The empty index is part of this function's interface: it
answers "the corpus is not built" rather than raising
`sqlite3.OperationalError: no such table: records`, and it does not create
`.memoria/index.db` as a side effect of searching.

### Performance

Search over the full corpus returns in well under a second — a test asserts
it against a synthetic multi-thousand-paragraph index.

## `events.jsonl` — the read ledger, forced 2026-09-01, issue #13

Every `read(ref)` and `search_text(query, filters)` call this server
**serves** appends one JSON line to `events.jsonl`, in `memoria.ledger` —
core, not the adapter, so that any future caller ledgers through the same
function rather than opening its own file. (#64's web app, which landed
alongside this, deliberately appends nothing — author reads are out of scope,
below.) Each line carries the
reference or query, the filters, the records served (by `SRC-` ID or
paragraph anchor — the same identifier `read(ref)` accepts verbatim), a
timestamp, and the session it belongs to. The file is opened in append mode
and written one line at a time; nothing here ever reads it back to rewrite
it.

**The path nests by year and month, matching part 04 §2's tree exactly:**
`sessions/<YYYY>/<MM>/<session_id>/events.jsonl` — the directory #29's
`context-manifest.json` and M4's `transcript.md` must later land in beside
this file. Nesting is derived from the session id itself, since the
documented `SES-YYYYMMDD-HHMM` form (part 04 §4) already carries the date.
A caller-supplied `MEMORIA_SESSION_ID` that does not carry that form has no
year/month to nest by; the ledger then falls back to
`sessions/<session_id>/events.jsonl` directly, flat. That fallback is a
documented deviation from part 04 §2, not a broken promise — an operator
who wants the full nested layout sets a session id in the documented form.

**Only what was served is ledgered.** A `ToolError` — an unresolvable kind,
a missing record, an un-normalized corpus, a bad query — supplies nothing,
so nothing is appended on that path. `CONTEXT.md`'s *Supplied context* is
explicit that the account is of what Memoria *supplied*, and that is the
definition #29's manifest is built on; an account of what was *asked for*
would be a different, broader ledger than this one is.

**The undecorated path is not an unlogged path.** A bare full-source read is
ledgered exactly like a paragraph read or a path read — there is no read
this server serves that skips the ledger.

**Author reads are out of scope.** The ledger records what the tool surface
served *to a session* (§10.4). The UI (#25) reads through the same core —
there is no second read path — but it is served to nobody, and passes
through nothing that appends here: there is no session for an author's own
click to belong to. Ledgering author browsing would make the supplied-context
account report the author's own reading as context supplied to a model,
which is exactly the confident-but-wrong number ADR-0001 exists to prevent.

**Session identity.** The MCP protocol carries no session id, and Claude
Code's own session id lives in its transcript JSONL path rather than
anywhere a tool call can read it (`docs/poc-plan.md` §3). Absent
`MEMORIA_SESSION_ID` in the server's environment, one id is generated for
the whole life of the server process and held for every call it serves — a
stdio server is spawned per client, so the process boundary stands in for
the session boundary until a spawner sets the variable explicitly. The
generated id is part 04 §4's `SES-YYYYMMDD-HHMM` form plus a random 24-bit
suffix: the documented form alone is minute granularity, and two servers
spawned in the same minute with no suffix would generate the identical id
and silently merge their events into one shared file.

## Registering the server

`.mcp.json` at the repository root, committed:

```json
{
  "mcpServers": {
    "memoria": {
      "type": "stdio",
      "command": ".venv/bin/python",
      "args": ["-m", "memoria.mcp"]
    }
  }
}
```

One committed file, correct in the primary checkout and in every worktree,
each of which has its own `.venv`, and with nothing machine-specific in it.

Three facts it depends on, **measured on Claude Code 2.1.252 rather than
assumed**, by registering a probe server that recorded what it was handed:

- **A project stdio server is launched with the project directory as its
  working directory.** That is what makes the relative `command` resolve, and
  what lets the server find the repository root by walking up for
  `pyproject.toml`. Pass `--repo-root` if you ever need to be explicit.
- **`${CLAUDE_PROJECT_DIR}` is *not* expanded in `.mcp.json`.** It is a hooks
  variable. A config that uses it is reported by `claude mcp list` as
  `Missing environment variables: CLAUDE_PROJECT_DIR`, and the literal string
  is passed through unexpanded. (`CLAUDE_PROJECT_DIR` *is* present in the
  spawned process's own environment — it is the config-time substitution that
  does not happen. Nothing here relies on either.)
- **`env` in `.claude/settings.json` / `settings.local.json` does not reach
  the server process.** It applies to Claude Code's own tool execution.

`python -m memoria.mcp` rather than the `memoria-mcp` console script: a module
works the moment the package is importable, while a newly added console script
does not exist until the environment is reinstalled.

A project-scoped server needs approving once — `claude mcp list` shows
`⏸ Pending approval` until then, and `/mcp` reports its state inside a
session.

### A finding worth not rediscovering

The settings-`env` fact above is why `orca.yaml`'s mechanism for handing a
worktree its `MEMORIA_EVIDENCE_ROOT` — writing `.claude/settings.local.json`
at setup — will not reach this server.

It does not matter yet: `read(ref)` resolves everything from the repository
root and never touches evidence, which is why the committed registration
carries no `env` block at all. It will matter the first time a tool reads
evidence. The options then are forwarding it (`"env": {"VAR": "${VAR}"}`,
which works only if the variable is exported in the shell that launched
`claude`), a machine-local `claude mcp add --scope local`, or an
`--evidence-root` argument written by the setup hook. None is built.

The `.venv/bin/python` path is POSIX; `orca.yaml` already requires WSL on
Windows for the same class of reason.
