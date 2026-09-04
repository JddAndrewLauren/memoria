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
| `search_global(query, filters, summarize)` | **Forced** — issue #74, below |
| `search_semantic(query, filters)` | **Forced** — issue #81, below |
| `audit_pending(...)`, `audit_record(results)` | **Forced** — issue #40, below |
| `trace(ref)` | **Forced** — issue #42, below |
| `expand`, `timeline`, `grep_repo`, `backlinks`, `list` | Open; §25 does not commit to shipping them |

## Maintainer-class tools (ADR-0005, issue #17)

A second class on the same server, and a different kind of thing from the
table above. The read tools are what a *writing* session reaches for. These
are the extraction pass: they are driven by the `extraction` skill, they
write, and they exist because there is nowhere else to put them.

| Tool | State |
|---|---|
| `extraction_brief()` | **Forced** — issue #17 |
| `extraction_next_paragraphs(limit)` | **Forced** — issue #17 |
| `extraction_record(results)` | **Forced** — issue #17 |
| `extraction_derive(recurrence_threshold)` | **Forced** — issue #17 |
| `extraction_next_summary()` | **Forced** — issue #17 |
| `extraction_record_summary(cluster_id, membership, summary)` | **Forced** — issue #17 |
| `extraction_status()` | **Forced** — issue #17 |
| `extraction_finish(recurrence_threshold)` | **Forced** — issue #17 |
| `extraction_candidates(subject_id, rejected, limit)` | **Forced** — issue #17 |
| `extraction_unplaced_forms(limit)` | **Forced** — issue #17 |
| `extraction_cluster(cluster_id)` | **Forced** — issue #17 |
| `extraction_promote_candidate(candidate_id, entry_slug)` | **Forced** — issue #17 |
| `extraction_promote_cluster(cluster_id, subject_id, entry_slug)` | **Forced** — issue #17 |
| `writing_style()`, `style_status()`, `style_brief()`, `style_record(observations)` | **Forced** — ADR-0009, below |
| `model_status()`, `extraction_run(limit)`, `audit_run(...)`, `style_run()` | **Forced** — ADR-0010, below |

The last five are the author's side of the pass rather than the pass itself.
#17 keeps rejected candidates and unplaced forms *enumerable* and offers
promotion as a one-key act; the three list tools are the enumeration, and the
two promote tools are the key. They exist on the server for the same reason
the rest do — the author's session has no other route to the rows — and they
act only on an id the author named.

### Why they are on this server

Because, by default, there is no other model in the system. `poc-plan.md` §3
forbids a model-driving service, and part 08 §12.1 forbids anything needing a
model from running unasked, so the extraction is an author-launched act inside
a Claude Code session — and the session's only route to the archive is this
server. ADR-0010's direct run (below) does not change that: it is the same
author-launched act with Memoria holding the model's end of the conversation,
and only when the author switched it on.

### The rule that shapes every signature

**No adapter can call a model**, and this one does not — with one deliberate,
named widening (ADR-0010): the `*_run` tools ask `memoria.model`'s seam for a
model at the point of use and hand it to a driver, when the author switched
direct runs on, and refuse otherwise. Every other tool is one of three things:
it *serves* (paragraphs, prompts, a summary task), it *records* what the model
produced, or it is local computation over rows (`extraction_derive`,
`extraction_finish`). There is no `generate_` anything: a direct run records
through the same `record_*` functions and validation the serve/record tools
use. This is the same finding that decided `search_global(summarize=true)`
serves a memoized summary rather than composing one (#74) — and a direct run
does not compose one on that call either.

### What the model sends back

`extraction_record` takes a list of `RecordedParagraph`, each carrying an
`anchor`, its `placements` (entry reference + the surface form in *this*
paragraph that placed it), its `unplaced` surface forms, and its `relations`.

Two rules are held by the **type** rather than by the prompt:

- a `RecordedRelation` has no second anchor field, so a relation spanning two
  paragraphs cannot be expressed at all;
- both its ends are entry references, checked against that same paragraph's
  placements, so a relation to an unplaced form is refused.

The core validates and re-encodes before caching. That is deliberate: what is
written survives every rebuild, so a malformed reading cached is a bad reading
no `memoria rebuild` will ever clear, and an adapter is the wrong place to be
the last line of defence for something that permanent.

### Batch in, per-element out

`extraction_record` takes a whole batch and reports **per element**: a
malformed reading names its reason and its siblings are still kept.

This is the one tool on this server with two failure channels — per-element in
the rendered result, whole-call as a `ToolError` — and it is worth stating
because it is unlike everything else here. The reason is that the failure atom
and the call atom are different sizes. One call per paragraph would spend a
tool-call envelope on every paragraph in the archive, which is a large amount
of pure framing; a batch that dies on one bad element throws away nineteen good
ones. Splitting them buys both.

### The prompt is a package constant

`memoria.extraction.EXTRACTION_PROMPT` and `CLUSTER_SUMMARY_PROMPT` are module
constants, and `extraction_brief` serves the first one verbatim. Its hash is in
every memo key, so **editing it re-reads every archive** — which is why it lives
where a change to it is a reviewed commit, rather than under `subjects/` where
an author's editor could invalidate the whole cache without anyone deciding to.

The skill holds no copy of it. Two copies would mean the hash covers the one
nobody read.

### What is ledgered

`memoria.ledger` records what the surface **served to a session**, so:

- `extraction_brief` — it serves every subject prompt verbatim, which is the
  same category of thing as `read("SUB-people")`;
- `extraction_next_paragraphs` — across a pass this is the largest delivery of
  evidence into a model's context anywhere in the system;
- `extraction_next_summary` — naming the member anchors it served, which is
  empty for a parent cluster, because a parent is served its children's
  summaries and no evidence at all.

Not ledgered: `extraction_record`, `extraction_record_summary`,
`extraction_derive`, `extraction_finish`, `extraction_status`, the three list
tools and the two promote tools. They supply nothing to the model; they take
from it, compute, or list derived rows. An account of *acts* rather
than reads would be a second, broader ledger — the same call this document
already makes about failed reads.

One property falls out rather than being arranged: **a memo hit is never
ledgered**, because the batch only ever carries paragraphs with no cached
reading. A re-run over an extracted corpus appends nothing.

**Cluster ids are deliberately not `read(ref)`-resolvable.** `served` names
things `read(ref)` accepts, and a cluster id is not one — cluster identity does
not survive re-clustering (ADR-0005 decision 6), so it rides in its own field.

### These tools write

`read` and `search_text` write nothing but the ledger, and a test asserts it.
The extraction tools write derived rows to `.memoria/index.db`, and
`extraction_finish` writes durable entry files under `subjects/` through
`memoria.write`. The read tools' no-write test is scoped to the read tools for
that reason; the narrowing is a decision, not drift.

---

## Record-extractor tools — forced, issue #34

The Curator's other half (part 08 §12-§13): where the extraction proposes and
asserts nothing, these write **durable records** - decisions, open questions,
badged entry statements, Memoria notes - each one a path-scoped commit as the
Curator. They are driven by the `curation` skill after a research session,
never reached for by a session mid-conversation, and they call no model: the
judgement (is this turn a decision or a musing?) arrives as tool arguments,
and the core checks mechanically the one thing it can - whose turn is cited
(`memoria.sessions.turn_role`).

| Tool | State |
|---|---|
| `curation_status()` | **Forced** — issue #34 |
| `record_decision(session_id, turn, text)` | **Forced** — issue #34 |
| `record_question(session_id, turn, text)` | **Forced** — issue #34 |
| `record_statement(entry_id, badge, text, provenance)` | **Forced** — issue #34 |
| `revise_statement(entry_id, statement_badge, statement_text, badge, text, provenance)` | **Forced** — issue #34 |
| `curation_flag()` | **Forced** — issue #34 |

### What each refuses

`record_decision` refuses an assistant-spoken turn and names `record_question`
as where the item belongs (part 08 §13.1's "does not qualify"). Every write
refuses a tree with uncommitted human modifications (the dirty-tree rule,
§14.2) and names the files. `record_statement` and `revise_statement` apply
the write matrix (part 06 §8.2) exactly as the core does for any caller: no
unbadged text, provenance on every assertion badge, an author-spoken turn
behind `[author]`, and provenance that terminates in original material only.
Each refusal reaches the model as the core's own message.

### The token is served in the same call

`record_statement` and `revise_statement` serve the entry and write against
that serve's token (ADR-0003) within one call, because a tool call has no
earlier read to carry a token from. What the token still buys is the
refusal of an edit committed between serve and write; the dirty-tree rule
runs before either.

### Naming a statement

`revise_statement` names the existing statement by badge and words, matched
with whitespace collapsed (`memoria.human_touched.statement_key`'s rule) and
without its own `— <reference>` lines, so a reflowed paragraph still resolves
and a miss lists what the entry does hold.

### These tools write, and are not ledgered

Every successful call is a commit attributed to the Curator, path-scoped to
the file it appended to or revised - that commit is the record of the call,
and `trace(ref)` reads it. Nothing is appended to `events.jsonl`: the ledger
records what a session was *served*, and these calls serve nothing.

---

## Audit tools — forced, issue #40

```
audit_pending(chapter_number, section_number=None, paragraph_index=None, limit=20) -> str
audit_record(results: list[RecordedAuditItem]) -> str
```

A third class on the same server, the same shape as the extraction tools
above and for the same reason (no model-driving service, `poc-plan.md` §3):
`memoria.audit` cannot call a model, so running the audit is a conversation —
`audit_pending` hands out paragraph/entry pairs that are missing or stale
judgements, and `audit_record` takes the answers back. Unlike the extraction
tools, this pair is not driven by a standing skill in this slice; it is
reached only by something naming a target explicitly.

### A target, not the whole manuscript

`audit_pending` always names a target — a chapter, a chapter plus a section,
or a section plus one highlighted passage (CONTEXT.md's "Audit": "a button on
a section or a chapter, or on a highlighted passage"). No call of this tool
audits the whole book at once; a chapter-level request is the broadest target
it accepts. The bound is the tool's, not the function's: `chapter_number` is
positional and required here, while the underlying
`memoria.audit.pending_for_target` scopes to the whole manuscript when called
with no keywords. Only judgements the staleness map (#37) already knows are
missing or stale are served — a target with nothing not-current says so
rather than re-serving what is already current.

### What the model sends back

`audit_record` takes a list of `RecordedAuditItem`, each an ``anchor`` (the
one `audit_pending` served it under) plus either an engagement answer
(``engages``, ``note``) or an audit-verdict answer (``clear``, or a
``finding``: its disagreement set, a statement, a confidence, and an
optional patch). A finding whose disagreement set matches no row in part 09
§18's resolution table is rejected rather than cached — there is no shape
that resolves by writing a brief.

### Batch in, per-element out

The same reasoning as `extraction_record`: one call per paragraph would spend
a tool-call envelope on every paragraph in the target, and a batch that died
on one bad element would throw away the rest. `audit_record` accepts or
rejects each element on its own and reports both counts.

### What is ledgered

Nothing. `memoria.ledger` records what was served *by reference* (#13), and a
manuscript paragraph carries no durable reference to record — the module
docstring's "no paragraph carries a durable identity" applies here exactly as
it does to the staleness map. No session id is minted for an audit call
either, so no `sessions/` directory appears from calling these tools alone.
`audit_run` (ADR-0010, below) is the exception: it is metered, so it ledgers.

### The author-testimony policy is served, not enforced

Part 06 §8.6: author testimony outranks documentary evidence, and the audit
must report a conflict with it as a disagreement, never as an error. This is
a rule for the model answering the questions `audit_pending` serves, not
something this adapter (or `memoria.audit`) can check mechanically — so every
audit-verdict task carries `memoria.audit.AUTHOR_TESTIMONY_POLICY` verbatim,
the same way `extraction_brief` serves its prompt verbatim rather than
paraphrasing it.

---

## Writing-style tools — forced, ADR-0009

```
writing_style() -> str
style_status() -> str
style_brief() -> str
style_record(observations: list[RecordedObservation]) -> str
```

A fourth class on the same server, in two halves. `writing_style` is what a
*writing* session reaches for: the author's writing style
(`style/writing-style.md`, CONTEXT.md's "Writing style") rendered as direction
for a writer, verbatim, or a plain statement that none is set. The server's
instructions tell a session to call it before drafting or rewriting any
manuscript prose. The rendering is `memoria.style.writing_style_prompt`, the
same string `assemble` loads as Tier 1 voice guidance and `audit_pending`
prints above a batch — one rendering, three servers, nothing to drift.

The `style_*` three are the analysis, and they have the extraction's shape
for the extraction's reason (no model-driving service, `poc-plan.md` §3):
`style_brief` *serves* the analysis prompt with every chosen source's
paragraphs and every uploaded sample, `style_record` *records* what the model
produced, and `style_status` is local computation. There is no `generate_`
anything. The `writing-style` skill drives them.

### What the model sends back

`style_record` takes a list of `RecordedObservation`, each an `aspect`, an
`observation` phrased as a directive, and an `example`. The core refuses an
element whose example does not occur verbatim (whitespace-normalized) in the
samples the brief served: an observation that cannot point at the author's own
words is not one the author should be asked to confirm. Batch in, per-element
out, as `extraction_record`.

### What it records, and what it does not

Nothing durable. Accepted observations are rows in the index
(`style_observations`, a preserved table that survives `memoria rebuild`),
proposed under a key naming the prompt and the samples; a second batch under
the same key replaces the still-proposed rows. The author confirms, changes or
discards each one under Settings > Writing style in the app, and only a
confirmation writes `style/writing-style.md` — through the one write path, as
the author's own act. No tool on this server writes the style.

### The prompt is a package constant

`memoria.style.STYLE_ANALYSIS_PROMPT`, served verbatim by `style_brief`; the
skill holds no copy, for the reason given under the extraction above.

### What is ledgered

- `writing_style` — the file reached a context verbatim, the same category as
  `read("style/writing-style.md")`; a call that found no style ledgers nothing.
- `style_brief` — every `SRC-` id and sample path served: the author's own
  words entering a model's context.
- `style_status` and `style_record` — nothing; neither serves evidence.

---

## Direct-run tools — forced, ADR-0010

```
model_status() -> str
extraction_run(limit: int = 20) -> str
audit_run(chapter_number, section_number=None, paragraph_index=None, limit=20) -> str
style_run() -> str
```

A fifth class, and the one that reaches a generative model. A **direct run**
(CONTEXT.md) is a pass Memoria executes itself against a metered model API —
the same `brief`, `pending_*` and `record_*` core functions the serve/record
tools call, in the skill's order, with `memoria.model`'s `ModelFn` between the
serve and the record (`memoria.drivers`). The prompts are served verbatim and
unchanged, so the memo keys are the same keys a session run writes; every
reading passes the same validation. The server holds no model: each tool is
`require_model` → one driver call → render, and `require_model` is the point of
use, refusing with a `ToolError` that names Settings > Model.

**Off by default.** The switch, the model id and the stored key live in
`.memoria/model.json`, beside the index, machine-local and gitignored, written
0600 by the app's Settings > Model and never through `memoria.write`;
`ANTHROPIC_API_KEY` in the server's environment overrides the stored key. A key
alone does not switch direct runs on. `model_status` says whether a run would
succeed and, if not, why; it never shows the key.

### Where the skills stand

The `extraction` and `writing-style` skills call `model_status()` **after** the
author's go, never before it, and hand the pass to `extraction_run` /
`style_run` only when it says ready; otherwise they drive the serve/record
tools as before. They never tell the author to switch direct runs on. The audit
has no skill; `audit_run` is reached like `audit_pending`, by something naming a
target the author asked to audit.

### Bounded per call, resumable

`extraction_run` makes at most `limit` model calls: one per paragraph while any
awaits extraction, then — once none do — it closes the pass (`finish_pass`, run
again on every summary-phase call rather than any state being carried) and
writes up to `limit` summaries, leaves first. It reports `phase: paragraphs`,
`summaries` or `done`, and the caller calls again. `audit_run` answers up to
`limit` of a target's not-current judgements per call. A refused, truncated or
off-schema reply is one rejected item, named by anchor with its reason, and
the run goes on; a provider failure is a `ToolError` with what was recorded
kept. Nothing is lost between calls and nothing repeats, for the extraction's
own reason: what is left is a query over what is absent.

### What each refuses

- All four: nothing while direct runs are off, no key is set, or the `llm`
  extra is not installed — a `ToolError` naming Settings > Model and the reason.
- `extraction_run` — a `limit` below one.
- `audit_run` — a passage without its section, as `audit_pending` does; a
  `limit` below one.
- `style_run` — nothing to analyse, as `style_brief` does.

### What is ledgered

Every metered call, as a `model_call` line: the pass it served, the provider,
the model that answered, input and output tokens, the cache counts, the stop
reason, and the anchor or cluster it was about. That is part 13 §24.5's "the
author should be able to tell whether a task is using subscription capacity or
metered API usage", made mechanical. The line carries **no `served` key**:
`supplied_context` reads every event with one as a served read, and this line
records spend, not supply. What reached the model's context is ledgered by the
same `extraction_brief`, `extraction_next_paragraphs`,
`extraction_next_summary`, `style_brief` and `read` lines the serve tools
write — the drivers write those too, including a `read` for each gathered
anchor a direct audit inlines where a session would `read(ref)` it.

### Reachable without the MCP server

`memoria.drivers.run_extraction`, `run_audit` and `run_style` take a
`Repository`, a `ModelFn` and a session id. The app's `POST /api/extraction/run`,
`POST /api/sections/{id}/audit` and `POST /api/style/analyse` call the same three,
under one ledger session per server process, and answer 409 while direct runs
are off.

---

## The constraint that binds all of it

From `poc-plan.md` §7, and it **may not be weakened**:

> retrieval must be a **superset of grep**: verbatim source text (never
> summarized-only), decorated with the curated overlay, a raw full-source read
> available, and every read ledgered in `events.jsonl`.

The reason is not purity. Evidence lives outside the session's working repo,
and this repo's own `sources/normalized/` records and `.memoria/` index are
what a session actually reads — direct reads of either are routed back to the
tools by a hook (`.claude/hooks/route-evidence-reads.sh`, `poc-plan.md` §3),
registered for Read, Grep, Glob and Bash. That hook is a **router, not a
wall** — a rewritten Bash command can still reach the files, since the hook
matches Bash by exact-string containment rather than parsing shell. It only
works while the tool returns *more* than a raw read does. The moment reading
through the tool is worse than `cat`, the router becomes an obstacle and
people go around it, and the ledger that makes the context manifest a record
rather than a request stops being complete.

So: the verbatim text is served unmodified and contiguously, and the
full-source read may never be removed or degraded.

## `read(ref)` — forced 2026-09-01, issue #11

```
read(ref: str, raw: bool = False) -> str
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
| `CHP-0001` | that chapter's brief, verbatim | part 04 §2.1 / #35 |
| `SEC-0001` | that section's brief, verbatim | part 04 §2.1 / #35 |
| `CHG-20261014-003` | the §11 projection of that human-authored commit | part 04 §4 / ADR-0008 |
| `SES-20260912-1432` | that session's whole transcript, verbatim, plus its context manifest | part 04 §4 / #28, #29 |
| `SES-20260912-1432#T017` | that transcript turn's text alone | part 04 §4 / #28 |
| `DEC-0088` | that decision's `decisions.md` block, verbatim | part 04 §4 / #30 |
| `RES-20261018-003` | that research memo, verbatim | part 04 §4 / #30 |

The bare anchor is accepted deliberately. `SearchResult` carries
`(src_id, anchor, source_type)`, so a search hit feeds straight back into
`read` — without it, #12 would have to reassemble a citation string inside an
adapter, which is the duplication §40.1 exists to forbid.

`SRC-` IDs are six digits, zero-padded. `SRC-184` is refused with a message
saying so, rather than guessed at. `CHP-` and `SEC-` IDs are four digits,
zero-padded, one flat namespace each — a chapter and a section never share an
ID space, but two sections in different chapters do, so a bare `SEC-0002` in
a citation is unambiguous without naming its chapter. They resolve by stable
ID rather than by directory, because reordering renumbers directories (#35);
the ID in a chapter's or section's own frontmatter is what survives the
move. `CHG-` IDs are a per-day sequence, `CHG-YYYYMMDD-NNN`, minted by
counting the day's `change-id:` trailers already in git history (ADR-0008) —
there is no allocation file. `read` finds the commit by its trailer, never
positionally, so a later rebase cannot renumber a reference to it; an id with
no matching commit is refused, naming the reference.

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

**A non-raw paragraph read carries the curated overlay** (#20, part 06 §8.3),
a second `---`-delimited block after the text: `entry links` (every entry
whose `gather` result — the same word-, entry- and relation-shaped recall,
and the same pin/exclude overlay, `gather` applies for a placement's own
entry — currently includes this anchor, read backwards from the anchor
rather than forward from one entry: the gathered-set-inverse, not a
placements-only narrowing of it), `exclusions` (every entry that has
excluded this anchor, whether or not it was otherwise gathered), and
`citing settlements` (always `none` in this build — settlements are an M4
concept with no durable storage yet, part 16). Both `entry links` and
`exclusions` are scoped to entries `load_all_entries` finds on disk, so a
deleted or renamed entry a stale index still names never surfaces. Every
field is printed even when empty — `none` rather than an absent line — so a
paragraph with no overlay comes back the same shape as one with one.
`Read.text` stays byte-identical between a decorated and an undecorated read
of the same paragraph: the overlay is a sibling field
(`memoria.records.Read.overlay`), never folded into `text`.

A degraded index — a schema older than this build, or a concurrent writer
holding it locked — drops the overlay (`Read.overlay` is `None`, the same as
a `raw=True` read) rather than failing the read: the verbatim text is never
conditioned on the overlay being computable, so the constraint this section
opens with does not weaken.

`render_overlay`'s own output never contains a bare `---` line — every field
it prints is an entry id or the literal `none` — so the *last* `---` in a
decorated paragraph's rendering is always the true text/overlay boundary,
even when the paragraph's own text happens to contain one; a caller splits
from the end for that boundary, and from the start for the header/text one
(the header is equally `---`-free by construction).

`original_locator` is printed and never parsed. It is a pointer a person
follows, not an offset — issue #25 depends on that staying true.

**A `SUB-` read is bare too** — a subject's prompt or an entry's file,
exactly as it is on disk, with no header and no delimiter, for the same
reason a full-source `SRC-` read is (issue #16). An entry read resolves by
its frontmatter `id` rather than by filename, so a renamed entry file still
answers to the `SUB-x/y` it was created with.

**A bare `SES-` read carries the whole `transcript.md`, verbatim** (#28),
**plus its context manifest** (#29) — a second `---`-delimited block
appended after the text, the same convention the curated overlay (#20)
established for a `SRC-` paragraph. Built live from `events.jsonl`, not from
a prior derivation of `context-manifest.json` having run: which records were
loaded, which entries were resolved, which searches ran and which of their
hits were also read, and a token count per item (ADR-0001) — never rendered
by this tool as an author-facing figure, because the model reading its own
session is not one of the surfaces part 14 §40 bans them from. **A
`SES-...#T017` read returns just that turn's text** — the same "a paragraph
read gives back the paragraph, not the record" split a `SRC-` paragraph
reference makes, and carries no manifest: a turn cites what was said, not
what was supplied.

**`raw=True` serves the least-processed version of what it is given** — one
parameter, two shapes, dispatched on whether the `SRC-` reference names a
paragraph:

- **A bare `SRC-` ID** serves the pre-normalization original, not the
  record — the file at the referenced record's `original_file`, through
  `read_raw_source`, confined to `MEMORIA_EVIDENCE_ROOT` the same way every
  evidence read is (#25's "Open original", already served by #64's
  `/api/sources/{id}/raw`). The original is what grep could have found
  before a normalizer ever ran, so serving it is part of the
  superset-of-grep constraint, not an exception to it (#113). Like the
  full-source read, this shape is bare — no header, no delimiter — and is
  ledgered like any other read, with its citation marked `SRC-000184 raw` so
  the served line names it as the original rather than the record.
- **A paragraph reference** serves that paragraph **undecorated** — the same
  header-plus-text a plain read gives, with no curated overlay block
  appended (#20). This is what keeps the raw undecorated read of a paragraph
  explicitly reachable once decoration exists, rather than reachable only by
  the accident of nothing decorating reads yet. Its citation is marked
  ` raw` too, the same shape as the whole-record case, so the ledger line
  distinguishes it from a decorated read of the same paragraph.

Refused for anything else — a `SUB-`, a `CHP-`/`SEC-`/`CHG-`, or a path, all
of which carry neither an `original_file` nor a curated overlay — naming the
reference it was given.

An original that does not decode as UTF-8 is refused too, rather than
handed back as bytes: the payload here is text, and a `.docx`'s raw bytes
returned as if they were text would be worse than `cat`, not equal to it.
The refusal names the file and its suffix and says what it could not do —
it does not claim the file is binary, since a `.txt` in another encoding
lands in the same branch.
Without `MEMORIA_EVIDENCE_ROOT` configured, a raw read of a whole record
fails with the same `NoEvidenceRoot` message every other evidence read
gives.

### What it refuses, and how

Every reference kind part 04 §4 defines now resolves. A kind that is not
part of the scheme at all is named in the error, never a silent empty
result; the "not resolvable in this build yet" message for a kind the plan
names but nothing implements is kept for the next kind the plan adds. `SUB-x`
and `SUB-x/y` were on that list until issue #16, `CHG-` until ADR-0008,
`SES-` (with or without a `#T` turn) until #28, `RES-`/`DEC-` until #30, and
`CLM-` until #33.

Errors reach the model as `ToolError`, which is the SDK's anticipated-failure
type: the call comes back `is_error` with the message intact. Any other
exception is reported as `Error executing tool read` with the reason stripped,
which would be exactly the silent failure #11 forbids — so the adapter maps
the core's error types onto it: `ReadError` always, and — for a `raw=True`
read with no evidence corpus configured — `NoEvidenceRoot` too (#113), the
same named refusal every other evidence read gives rather than a second
failure shape the model has to learn.

### What is deliberately still missing

- **`citing settlements` is always empty.** The overlay (#20) prints the
  field, but settlements are an M4 concept (part 16) with no durable storage
  yet to query. The shape will not need to change again when M4 adds one.

## `search_text(query, filters)` — forced 2026-09-01, issue #12

```
search_text(query: str, filters: SearchFilters | None = None) -> str
```

The retrieval half of the minimum M1 tool surface: full-text search over the
FTS5 index (`memoria.index`), the other half of what §7's superset-of-grep
constraint needs alongside `read`.

**FTS5 and nothing else.** ADR-0007 admitted embeddings by choice, but
`search_semantic` (#81, below) is a separate tool over a separate
`sqlite-vec` table; ADR-0005's extraction is a candidate engine, not a
search index (`docs/open-problems.md` §2.2: "`search_text` stays FTS5").
This tool's result set is FTS5 hits, and cluster summaries are never served
here as evidence.

### The filters are implemented in the core, not the tool

`memoria.index.search(repository, query, filters)` takes the frozen
`Repository` value, like every other core read (ADR-0004) — the point at
which the function's `db_path` parameter was aligned to match, since #74 and
#81 inherit the shape. `build_index` was aligned the same way by #95, so
nothing in the module composes an index path from outside it. `SearchFilters` carries the six filters that have
something to filter on at M1:

- `event_date` — exact match against the record's verbatim frontmatter
  string
- `recorded_date` — exact match, same reason
- `source_type` — exact match (e.g. `"journal"`, `"editorial"`)
- `contemporaneous` — `true` excludes retrospective/editorial commentary
  added over the same ground; this is how §6's temporal discipline is
  enforced at retrieval time
- `from_` — case-insensitive substring match against the record's verbatim
  `from` header string (#111)
- `to` — case-insensitive substring match against the record's verbatim
  `to` header string, same reason

All six are optional and compose (ANDed together). An **empty string is not a
filter** — `from_=""` and `to=""` are treated exactly like `None`, because
`INSTR(x, "")` is true of every non-null value, so an empty header filter
would otherwise return every record that merely *has* that header (218 of 375
on the real index) and present it as the answer to a narrower question. `record class` is not a
filter: §26 lists it only as a *potential* one, and nothing defines it in
`docs/normalized-record-schema.md` or on `NormalizedRecord`. Dates have no
sortable value in the schema (`date_confidence` runs `exact` … `unresolved`
with no ordering), so a range filter has nothing ordered to compare against —
exact/prefix match was the choice available, and exact match is what shipped.
Subject and entry filters (`person`, `theme`, `arc`, …) wait for M2, since
entries do not exist yet; they are never filters, because the entry filter
will cover every subject the author adds.

`from_`/`to` are metadata retrieval, not entity resolution (#111, the M1 gate
walk on #15: a session had to fall back to Bash and grep frontmatter because
`search_text` indexed paragraph bodies only and the header fields were
invisible to it). `docs/corpora/enron.md` finding 3 is why they stop at a
string filter: half the correspondents in a real export are bare display
names in mixed order, sometimes both ways in the same header, so resolving
"Dave Perrino" to a person is entry match-term work, and these filters never
attempt it — they match the verbatim string.

They are reachable through the core (`memoria.index.search`) and the MCP tool
(`search_text`) only. #64's web route still enumerates the original four query
params — `event_date`, `recorded_date`, `source_type`, `contemporaneous` — and
passes no `from_`/`to`; carrying them across that boundary belongs to #64, not
#111.

The filter values live in a plain (non-FTS) table keyed by paragraph anchor —
`paragraphs(anchor, src_id, source_type, event_date, recorded_date,
contemporaneous, email_from, email_to)` — written by `build_index` beside the
FTS5 `records` virtual table, not as extra `UNINDEXED` FTS5 columns; one row
per paragraph, with the record's `from`/`to` values repeated across every one
of its rows, so the predicate needs no join into the FTS5 table and no record
file read. `memoria.index.
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

## `search_semantic(query, filters)` — forced 2026-09-02, issue #81

```
search_semantic(query: str, filters: SearchFilters | None = None) -> str
```

The nearest-neighbour half of retrieval (ADR-0007), beside `search_text`'s
lexical one: a paragraph whose wording differs from the query but whose
meaning is close to it is unreachable by FTS5's `MATCH`, and this is what
reaches it. `docs/adr/0007-embeddings-enter-by-choice.md` settles the
mechanism and is the contract this section serializes.

### One store, populated at rebuild

A `sqlite-vec` `vec0` virtual table, `paragraph_vectors(anchor, embedding)`,
beside the FTS5 `records` table in the same `.memoria/index.db` file — no
second store, no vector database, no additional process. `memoria.index.
build_index` creates it whenever the `sqlite-vec` extension loads (empty
tables cost nothing) and populates it only when given an embedder
(`embed_fn`); `memoria rebuild` — the actual "at rebuild" moment the ADR
names — is the one caller that supplies the real one
(`memoria.embeddings.default_embed_fn`), so deleting `.memoria/index.db`
removes the vector table exactly as it removes the FTS5 one, with no
separate CLI verb or lifecycle (§42). On an interpreter whose `sqlite3`
cannot load extensions at all (#153), the table is simply not created —
every other derived table still is, so only `search_semantic` degrades, with
a scope line naming the missing extension instead of raising.

`build_index`'s own default is `embed_fn=None` — skip — not the real
embedder, and this is a deliberate reading of part 08 §12.1's "nothing that
needs a model runs unasked", not an oversight: `build_index` is called
directly by most of this repository's own test suite, over fixture records,
and none of those calls should pay for or need a model. `search_semantic`'s
`embed_fn` is required outright, with no default at all, for the same
reason — every call site (the MCP tool, a core test, `tests/
test_labelled_queries.py`) names its embedder explicitly rather than one
hidden inside `memoria.index` a test would have to know to monkeypatch.

### The embedder: a seam with exactly one implementation

`bge-small-en-v1.5` through `fastembed`, run on CPU through `onnxruntime` —
no `torch`, no GPU, matching ADR-0007's "production has no GPU". Nothing
here is user-configurable; `memoria.embeddings.default_embed_fn` is the one
production implementation, pinned by name (`EMBEDDING_MODEL_NAME`) and, in
`pyproject.toml`, by exact version — `sqlite-vec` is pinned the same way,
being pre-1.0. What the module offers a caller instead of a choice of model
is the substitution point itself: every function that needs an embedder
takes one as a plain callable (`EmbedFn`) rather than reaching for this
module directly, so `tests/test_index.py` and `tests/test_mcp_server.py`
hand it a deterministic fake — fixed basis vectors, never `fastembed` — and
the full test suite runs with no network and no GPU. Only
`default_embed_fn` itself reaches the network, the first time anything
calls it: `fastembed`'s `TextEmbedding` downloads the model's ONNX weights
from the Hugging Face Hub on first use, which is why nothing in this
package's own test suite calls it.

### The filters are #12's, not a new representation

Reuses `SearchFilters` and `memoria.index.filter_predicate` exactly as
`search_text` does (above), applied as a subquery — `anchor IN (SELECT
anchor FROM paragraphs WHERE {predicate})` — rather than a join, because
`sqlite-vec`'s KNN operator only accepts a plain `LIMIT`/`k` constraint on a
query against the vector table directly; joining it to `paragraphs` defeats
the library's query-planner detection and it refuses to run at all.
Reachable without the MCP server, exercised directly by `tests/
test_index.py`, the same shape `search_text`'s core function has.

### What it returns

The same `SearchResult` triple `search_text` and `search_global` return —
no second result type, and no score field added to the shared one either,
since `search_text`'s FTS5 path does not have one. Ranked nearest first;
`SEMANTIC_SEARCH_LIMIT` (20) bounds how many come back, because `sqlite-vec`'s
KNN operator requires a bound and, unlike FTS5's `MATCH`, always returns its
`k` nearest rows regardless of how distant the furthest of them actually is
— there is no "no match" state below the limit, only fewer embedded
paragraphs than it.

Cluster summaries are never embedded, and cannot be: `build_index`'s
embedding loop walks each `NormalizedRecord`'s real paragraphs only, the
same collection point that feeds the FTS5 `records` table, and never queries
the `memo` cache at all — a test plants a decoy cluster-summary memo row and
asserts it never reaches the embedder.

### The scope line names what was embedded and what was searched

Every reply ends with a line in the §33 style — *"embedded 1,842 paragraphs
with bge-small-en-v1.5; filters: source_type=journal; 20 semantic hits"* —
because §33.1 is explicit that an index reports nothing about its own recall
on its own: this is the one place a session can say what the semantic index
actually covered, the same discipline `search_global`'s scope line already
keeps for the cluster tool. The filters clause is printed as `none` rather
than omitted when nothing was set — the same "printed, not omitted"
discipline `render_overlay` (#20) keeps for an empty overlay — because #81's
own acceptance criteria ask the line to *name* the filters applied, not
merely let a reader infer them from the hit count. Named the same way with
an empty or unbuilt index (`0` and `0`) rather than falling silent.

### Reachable without the MCP server

`memoria.index.search_semantic` is a plain core function over
`memoria.index.connect`'s `sqlite-vec` extension loading and `memoria.index.
filter_predicate`, exercised directly by `tests/test_index.py` — the same
shape `search_text` and `search_global`'s core functions have.

### The labelled query set

`tests/fixtures/labelled_queries.yaml` carries a documented shape and ships
empty, checked by `tests/test_labelled_queries.py` — part 15 §43.14's
successor harness, the instrument this ADR chose in place of a pre-registered
benchmark number. Populating it with real entries is out of scope for #81
and starts the day a real evidence archive exists to draw queries from
(`docs/open-problems.md` §2.2); until then the check passes vacuously, by
construction rather than by a skip.

## `search_global(query, filters, summarize)` — forced 2026-09-01, issue #74

```
search_global(query: str | None, filters: SearchFilters | None = None, summarize: bool = False) -> str
```

The one global tool over the extraction's clusters (part 11 §25, ADR-0005 "Build
shape" 4). Where `search_text` returns a flat, ranked list of hits, this returns
paragraph references **grouped by cluster**, each group labelled by the entries
and relations that define it, under a §33-style scope line — *"clustered 1,842
paragraphs across 2009–2014; 3 clusters matched at level 2"*. It is a superset of
`grep` in the same sense `search_text` is: every reference is an anchor `read(ref)`
accepts verbatim, and no group carries paragraph text of its own — the search over
derived state rejected for `search_text` (above, "full paragraph hydration was
rejected") is not repeated here either.

### `query` is optional

Given, `search_global` full-text searches the archive exactly like `search_text`
and groups the hits by cluster. `None` returns every paragraph of every matched
cluster instead — the map step of ADR-0005's "Build shape" 4: with no model in the
server, the session agent does the reduce itself through part 11 §28's loop, and
this is the one call that hands it the map.

### One level per call

`SearchFilters` gained a seventh field, `level`, for this tool alone —
`search_text` never consults it (`memoria.index.SearchFilters`, above). A
paragraph nests inside a cluster at every level of the hierarchy at once
(ADR-0005 build shape 1), so grouping across every level in one call would show
the same paragraph again under each of its ancestors. `filters.level` picks the
grain; left unset, `memoria.extraction.search_global` resolves the finest level
the corpus currently has. Either way the level actually used is named in the
returned scope line — never left for a caller to infer, the same discipline §33.1
states for assembly.

### A promoted cluster routes to its entry, not to its stale label

ADR-0005 decision 6 (part 06 §8.4): a cluster promoted into a Theme or Arc is
never pointed at by the entry it became — cluster identity does not survive
re-clustering, and match terms do, so the link cannot be stored either way.
`memoria.extraction.search_global` reads it forward instead, and the check is
**exact, not bounded**: a cluster routes to an entry only when the entry's own
entry- and relation-shaped match terms exactly equal what `promote_cluster`
would seed from this cluster *today* — computed by the same ordering
`promote_cluster` itself uses (relations split around members, deduplicated,
capped at `MAX_SEEDED_MATCH_TERMS`, a candidate-shaped member contributing its
label as a plain word), with the plain-word terms then dropped before the
comparison, since a Theme's own routing table is built the same way. One-way
containment — an entry's terms merely a subset of the cluster's — is not
enough: it also matches a hand-authored Theme whose terms happen to overlap an
unrelated cluster's larger membership, and it matches every coarser ancestor of
the cluster an entry was actually promoted from (a coarser level's members are
always a superset of a finer one's). A bounded slack on top of containment
cannot fix this without reopening it: any cardinality allowance forgiven for
"the cap could have crowded a member out" becomes indistinguishable from "the
cluster is just bigger than the entry" once a cluster carries enough
candidate-shaped members — and recurring unplaced forms are the most numerous
node shape in a real extraction, so that crowding is the common case, not a
corner one. Exact equality forgives candidate crowding and the cap by
construction, since both are already reflected in what `promote_cluster` would
seed today, while still failing a hand-authored overlap or a coarser ancestor
regardless of how many candidates either carries — because neither one's
would-seed set actually equals the route it merely resembles.

A route can still be lost two ways: editing a Theme's match terms past what its
origin cluster would seed today (the declared cost of ADR-0005 rejecting a
durable pointer, not a bug in this tool), or the cluster re-clustering into a
shape whose own would-seed set no longer equals the entry's.

### `summarize=true` serves; it never generates

The same rule that shapes every tool on this server (above, "The rule that shapes
every signature"): `search_global(summarize=true)` can only *serve* a cluster's
memoized `[inferred]` text — leaves from their member paragraphs, parents from
their children's summaries, written by the extraction's own summary loop
(`extraction_next_summary` / `extraction_record_summary`), never composed on this
call. A cluster with no summary yet says so rather than making one. `summarize=false`,
the default, never returns cluster text at all, marked or not: a summary is a
compression under part 02 §1.5, never evidence, and it is served only when
explicitly asked for — never handed to a caller who did not request it, and never
substituted for a `read(ref)` result, which touches no cluster row.

### What is ledgered

Every call is ledgered (`memoria.ledger.append_search_global`), naming the mode
that ran (`summarize`) and whether a summary was actually served
(`summary_served`) — `summarize=true` over freshly-clustered paragraphs with no
summary yet still ran in that mode and served none, and the ledger says so rather
than collapsing the two. Matched cluster ids ride in their own `clusters` field,
the same call `extraction_next_summary`'s ledger line makes: a cluster id is not
`read(ref)`-resolvable (below, "Cluster ids are deliberately not…"), so it does not
belong beside the anchors in `served`.

### Reachable without the MCP server

`memoria.extraction.search_global` is a plain core function over
`memoria.index.connect` and `memoria.index.filter_predicate`, exercised directly
by `tests/test_extraction.py` — the same shape `search_text`'s core function has,
and for the same reason (§16's "the `SUBJECTS` tree needs the same grouping to
show a cluster before the author promotes it").

## `trace(ref)` — forced 2026-09-03, issue #42

Provenance as a tool (part 11 §26), composed rather than stored (part 04 §4.1,
part 10 §20). Implemented by `memoria.trace`; the tool is one call and a
rendering.

### What it accepts

One paragraph of a section's prose, positionally: `SEC-0001 ¶7` or
`SEC-0001 P7`, the same `¶`/`P` pair a source paragraph takes. The form is
for a live question and is **never a durable pointer** — §4.1 rules those out
for manuscript prose, and `read(SEC-0001 ¶7)` serves the paragraph as it is
right now for the same reason. Anything else — a bare section, a brief, a
source paragraph, a path — is refused naming what trace does take.

### What it returns

The paragraph verbatim between `---` delimiters, then one block per commit
that last touched its lines, most recent first, each composed on the call
from records that already exist:

```text
ref: SEC-0001 ¶7
path: chapters/02/sections/01/draft.md
---
<the paragraph>
---
commit: 31cb8d2 2026-11-03 10:41 by Memoria (3 line(s))
  authorized by: SES-20261103-1041#T008 (scope: SEC-0001 ¶7)
  turn:
Rewrite it using the corrected timeline.
  assembled from: SUB-people/bob, SUB-timeline/chronology, SRC-000184
```

A human-authored commit stops at its `CHG-` id: what changed is in the commit,
and Memoria does not invent why (part 07 §40). An AI commit's `authorized-by:`
trailer names the session turn; the turn's text is quoted **verbatim** once the
session is derived (`derive-session`, which resolves Claude Code's own JSONL
from `CLAUDE_CODE_SESSION_ID` when run with no path, #198), and reported as
not yet derived before;
`assembled from` is the session's context manifest (#29) — entries resolved,
then records loaded, each taking in what the session read *and* what assembly
(#38) resolved for it, since a draft authorized from the working context was
written from the entries and sources the `assemble` line names whether or not
the session went on to read them — built live from `events.jsonl`. Lines with no commit yet
are counted as uncommitted, not traced. A commit with neither trailer is named
as such: `memoria validate` fails it.

### The accepted cost

Blame coarsens under reflow. A human rewrap after an AI rewrite is the last
thing that touched those lines, so the trace reports the rewrap's `CHG-` and
the AI commit drops out of the chain — a loss of precision, never of
correctness, pinned by a test. §20 names the falsifying observation: blame
attributing a paragraph so badly that the account misleads.

### What is ledgered

A `trace` line carrying the paragraph's citation and every authorizing turn
whose text it quoted — each a reference `read(ref)` accepts. Commit facts and
manifest references are identifiers, not text served, and are not listed. The
context manifest does not project `trace` lines; like the extraction and audit
tools, they are in the ledger and not in the manifest's four categories.

## `events.jsonl` — the read ledger, forced 2026-09-01, issue #13

Every `read(ref)` and `search_text(query, filters)` call this server
**serves** appends one JSON line to `events.jsonl`, in `memoria.ledger` —
core, not the adapter, so that any future caller ledgers through the same
function rather than opening its own file. (#64's web app, which landed
alongside this, deliberately appends nothing — author reads are out of scope,
below.) Each line carries the
reference or query, the filters, the records served (by `SRC-` ID or
paragraph anchor — the same identifier `read(ref)` accepts verbatim), a
timestamp, and the session it belongs to. A `read` line also carries
`tokens` (#29) — measured from the text actually served, at the moment it
is served, rather than re-derived later from whatever the evidence looks
like by then — the development instrument behind `poc-plan.md` §6 risk 1's
budget-capping experiment (ADR-0001); a `search_text`/`search_global` line
carries none, since a search serves references, not evidence text. The
file is opened in append mode and written one line at a time; nothing here
ever reads it back to rewrite it.

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
