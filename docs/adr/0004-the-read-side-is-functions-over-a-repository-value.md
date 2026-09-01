# The read side is functions over a repository value, not a repository object

M3 gives the core its second and third adapters — the MCP server (#11) and the FastAPI
app (#64) — after a year with exactly one. §40.1 asks for one core service layer, and
`0002-ui-is-a-react-client.md` discharged that as "domain logic stays in `memoria.*`"
without saying which modules. Four issues then each independently assert that something
"belongs in the core": reference resolution (#11), search filters and hydration (#12),
the response shapes (#64), and no second read path (#25). They assert it about a core
that has a complete write half and no read half at all — `_record_to_markdown` serializes
a record to disk and nothing anywhere deserializes one, so the only parser in the repo is
a private helper inside `validate.py` that returns `dict[anchor, text]` and discards every
frontmatter field. We settle the placement: the read side is **module-level functions
taking a frozen `Repository` value** that carries the roots — `records`, `references` and
a deepened `index`, not one `Repository` object with methods — and the **composed read**
is a core function rather than each adapter's job.

Two findings decided it, and neither is about taste.

**A long-lived object may not hold a connection.** Probed on this repo's interpreter:

```
python: 3.14.4 | sqlite3.threadsafety = 3
shared connection used from another thread ->
  ProgrammingError: SQLite objects created in a thread can only be used in that
  same thread.
```

FastAPI runs `def` routes in a threadpool with varying threads, so an object holding an
open connection breaks under exactly the deployment #64 builds. `index.search` already
connects and closes per call, which is correct and stays that way.

**The other candidate for held state is assigned elsewhere.** Part 08 gives the index
maintainer "derived state only — ingest matching, candidates, gathered sets, appearances,
**invalidation**, the staleness map." A cache that ingest must invalidate is therefore
derived state under §42, rebuildable and thrown away, not process memory. Strip both and
what a `Repository` object would hold is two `Path`s, which is a value.

## Considered Options

**One `memoria.repository.Repository` object.** The strongest rejected option, and the one
both adapter frameworks ask for: FastAPI's current guidance is a `lifespan` context manager
creating application-scoped resources reached through `Depends()`, and the MCP Python SDK's
is an `@asynccontextmanager` yielding a typed `AppContext` that tools reach at
`ctx.request_context.lifespan_context`. Passing a value down to module functions works
slightly against the grain of both, and that cost is real. Rejected on the two findings
above — with statefulness removed there is no behaviour for the object to justify — and on
the deletion test: an object that forwards to `records`, `references` and `index` does not
concentrate complexity, it relocates it. The trajectory is also predictable. Roots, then
records, then search, then writes, then subjects (#16), then assembly at M5: by the end
"no domain logic in the HTTP layer" is satisfied trivially because everything sits behind
one name, and nothing is separately testable. Recorded here at length because a future
reader looking at two framework idioms pointing the other way will otherwise assume they
were not consulted.

**Roots as arguments to every function, with no value at all.** The cheapest option today
and the closest to what the code already does — every core function takes
`(evidence_root, repo_root)` positionally. Rejected because the invariant that matters
gets no owner: every read, search and write in one process must see the same roots, and
under this option three adapters each construct them independently, which is how a
half-configured server ends up reading records from one checkout and evidence from
another. It also degrades worst as the composed read grows an input per milestone —
apparatus and backlinks now, gathered-set membership and overlays at M2, appearances at
M5 — with three adapters updating call sites in lockstep each time. That is the read-side
recurrence of the defect `cli.py` and `index.rebuild()` already demonstrate on the write
side, where twelve calls in a load-bearing order are written out twice because no module
owns the ordering.

**Reference resolution inside the record store.** Rejected on what `read(ref)` has to do.
The tool dispatches on the reference kind, and most kinds will never be records —
`SES-` with an optional `#T` turn, `CHG-`, `CLM-`, `RES-`, `DEC-`, `SUB-x`, `SUB-x/y`,
plus repository paths — and #11 requires a kind that does not exist yet to return a clear
error naming it rather than a silent empty result. A record store should not know what
`SUB-x` is. Parsing a reference and resolving one to a record are different jobs:
`references` owns the first, `records` the second.

**The FTS index as the read store.** Deferred, not rejected. `.memoria/index.db` already
holds `(src_id, anchor, source_type, text)` for every paragraph of all 587 journal entries
and 130 letters, so hydration could be a second `SELECT` with no Markdown parsed at all,
and the filters #12 and #64 both want would be a `WHERE` clause. The two facts that look
fatal are not: the audit targets are excluded from the **FTS table** for a real reason
(a benchmark probe would return itself as its own top hit), and frontmatter is nine
columns away — a second, non-FTS `records` table dissolves both. It is deferred because
the PoC corpus is not representative of the production archive in either direction, which
makes this a performance decision with no evidence behind it. Behind the interface this
ADR settles it becomes reversible by editing one module, which is the point of settling
the interface first. Records stay Markdown-backed, and the `.md` files stay written —
M0's gate opens one, `validate` reads them, and they are the only form a human can inspect
without a query tool.

**A storage interface with swappable adapters.** Rejected. One adapter is a hypothetical
seam; two are a real one. Markdown is the only implementation, and an abstract interface
for a second that does not exist is the speculative abstraction this repo's own discipline
forbids.

## Consequences

- **Four things, named.** `memoria.records` owns the on-disk record format in both
  directions and the composed read. `memoria.references` parses and formats `SRC-` IDs,
  paragraph anchors and repository paths. `memoria.index` keeps search and grows the
  filters. The `Repository` value carries location. Adapters call functions and shape
  results; they compose nothing.

- **The value is one repository root, not two co-equal ones.** Part 05 §5.1 puts raw
  evidence at `sources/raw/` inside the repository, and its own example frontmatter reads
  `original_file: ../raw/journals/2011.docx`. The sibling `thoreau-evidence` repo is PoC
  scaffolding with a specific reason (`../poc-plan.md` §3: the corpus belongs to someone
  else and its own git history is Invariant 3's tamper-evidence). Model the evidence
  location as a configured field inside the value, so the target layout arrives as a value
  change rather than a signature change across three adapters.

- **The value is frozen and therefore hashable**, so `functools.lru_cache` keyed on it is
  available for read-only derived tables — the 348 answer-key rows and the cross-reference
  table that backlinks need — without a stateful holder and without a process-global that
  tests cannot reset.

- **No module holds an open connection.** `index.search` keeps connect-per-call. This is
  a rule, not an implementation detail: it is what makes the core safe under a threadpool.

- **Hydration is a core function.** #12 and #64 currently disagree — #12 puts hydration and
  the filters in `memoria.index`, #64's acceptance criteria hydrate in the API. #12 is
  right and #64 is amended. Two adapters hydrating independently is the duplication §40.1
  exists to forbid, arriving inside one milestone.

- **The empty corpus becomes a value.** `search` against a fresh checkout today raises
  `sqlite3.OperationalError: no such table: records` and creates an empty
  `.memoria/index.db` on the way out. Two acceptance criteria are unsatisfiable until that
  moves into the core: #64's "the web package imports no SQLite driver" (catching the
  error requires importing it) and #24's "an un-normalized checkout renders an honest
  empty state rather than an error".

- **`NORMALIZED_RELATIVE_PATH` leaves `validate.py`.** The constant a reader needs is
  currently owned by the module least related to reading, and `index.py` and `cli.py` both
  import it from there.

- **Writes take the same value and live in their own module** (#66). The staleness token
  then crosses between two core modules as an explicit value rather than as hidden state
  on a shared object — which is what #66 needs anyway, since the token has to survive the
  round trip out to a browser and back. `0003-durable-writes-go-through-one-path.md`
  settles that path's *mechanism* — the content hash, the path-scoped commit, the accepted
  TOCTOU window — and was decided concurrently with this one. The two compose: it says how
  a write is gated, this says where the module sits and what it is handed. Its rule that
  the token is minted from the file as read is the reason #66 waits on the record store.

- **Nothing here is glossary material.** `CONTEXT.md` is unchanged: repository, record
  store and reference resolution are service-layer naming, not domain concepts.

- **Out of scope, and noted so it is not discovered inside a read ticket:** `SRC-` IDs are
  assigned by input position (`start_id=len(journal_records) + 1`, targets last "so adding
  them moves no existing ID"). That is stable only under append-only ingest of whole
  volumes, and §4's claim that `SRC-000184 ¶17` is stable by construction stops holding
  the first time incremental ingest inserts anywhere but the end. It belongs to the
  derivation half, not this seam.

- **Revisit if the one-host model gives way.** §40.5 and part 17 both put the repository,
  the index, git, the service and the credentials on a single Memoria host, with phones as
  clients holding no credentials. If evidence ever genuinely lives on devices that can be
  offline, evidence access needs a live, stateful handle — a sync client, an availability
  cache, an auth session — a frozen value cannot hold one, and the rejected object becomes
  correct.
