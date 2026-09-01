<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 25, 26, 27, 28, 29, 30, 32, 33 of the original memoria-plan.md -->
<!-- §25 revised 2026-08-31: per-type read tools unified into read(ref). -->
<!-- §25 read(ref) signature forced 2026-09-01 (issue #11): see ../tool-surface.md. -->
<!-- §33.1 revised 2026-08-31: index recall is gathered-set recall, a set metric. -->

# 25. Retrieval Architecture

Memoria begins with a deliberately simple retrieval substrate.

The session model receives tools rather than a complicated RAG middleware stack.

Core tools:

```text
search_text(query, filters)
search_semantic(query, filters)   <- in by choice, 2026-09-01 (ADR-0007)

read(ref)

expand(chunk_id)
timeline(range, person?)
grep_repo(pattern, paths)

trace(ref)
backlinks(ref)

search_global(query, filters, summarize=false)

list(path)
```

**`search_global` was added 2026-09-01** (ADR-0005). It returns paragraph references
grouped by **cluster**, each group labelled by the entries and relations that define
it, under a §33-style scope line — *"clustered 1,842 paragraphs across 2009–2014;
3 clusters matched"*. With `summarize=true` it also returns each cluster's synthesized
text, marked `[inferred]` and never served as evidence. Both modes are ledgered, with
the mode named. **Settled later that day** (ADR-0005, "Build shape"): the query is
optional and the filters include `level`, so a call with no query returns every
cluster at one level of the nesting — the map step of a whole-corpus question, which
the session agent then reduces through §28's loop. Summaries are *served* from what
the extraction pass memoized, never generated on the call: no adapter can run a model. It is a superset of grep in the poc-plan §7 sense: every reference
resolves through `read(ref)`, and the summary is a compression under §1.5, not an
answer.

**`read(ref)` is the single read tool.** It accepts any §4 stable reference —
`SRC-`, `SES-` (with an optional `#T` turn), `CHG-`, `CLM-`, `RES-`, `DEC-`,
`SUB-x` and `SUB-x/y` — as well as a repository path. The ID scheme already names
the type, so dispatch is read off the reference. The former per-type list
(`read_source`, `read_session`, `read_change`, `read_claim`, …) was an enumeration
of kinds in the §1.10a sense, and it had already drifted — `read_impact` was
deleted when impact records went away, and `read_entry` existed only in §24.2's
mirror. It is withdrawn.

What `read` returns is constrained by `poc-plan.md` §7, and the constraint may not
be weakened: **retrieval is a superset of grep**. An evidence read returns verbatim
source text — never a summary in its place — decorated with the curated overlay
(entry links, exclusions, settlements citing the paragraph); a raw undecorated
full-source read remains available; and every read is ledgered in `events.jsonl`.

Potential filters include:

```text
event date
recorded date
source type
contemporaneous/retrospective
chapter
record class
subject            e.g. SUB-people
entry              e.g. SUB-people/bob, SUB-themes/control
level              a cluster level, for search_global
```

`person`, `theme` and `arc` are no longer separate filters. They are entries, and an
entry filter covers them and every subject the author adds.

---

---

# 26. `trace()` — Provenance as a Tool

`trace(ref)` recursively resolves an assertion or interpretation back toward its origins.

For example:

```text
trace(THEME-control#loss-of-autonomy)
```

might return:

```text
THEME-control
  ├── CLM-0041
  │     ├── SRC-0184 ¶17
  │     ├── SRC-0392 ¶8
  │     └── RES-20261018-003
  │           └── SRC-1102 ¶4
  └── SES-20260912-1432 T017
```

A model should be able to inspect the existing case behind an interpretation before accepting, challenging, or extending it.

---

---

# 27. `backlinks()` — What Depends on This?

The reverse question is equally important.

```text
backlinks(SRC-0184)
```

might show:

```text
CLM-0041
SUB-themes/control
SUB-arcs/bob-relationship
RES-20261018-003
chapter 8 source packet
chapters/02 ¶14–17        (appearance, from the index)
```

This makes source corrections, reinterpretation, contradiction analysis, and impact analysis much easier.

It also provides much of the useful graph behavior without requiring a dedicated graph database.

Since 2026-09-01 the extraction's **relations** (part 06 §8.4) feed it too: `backlinks`
on an entry can list the entries it is related to, paragraph by paragraph. Relations are
derived index rows and nothing else — never durable, never in a working context.

---

---

# 28. Agentic Retrieval

Research proceeds iteratively.

The model may:

1. formulate an initial search;
2. inspect results;
3. identify aliases;
4. widen or narrow dates;
5. search semantic variants;
6. inspect parent source records;
7. inspect neighboring records;
8. compare contemporaneous and retrospective accounts;
9. search for contradictions;
10. revisit the subjects;
11. form or revise a conclusion.

The agent is not expected to get the right evidence from a single vector search.

The loop itself is the retrieval architecture.

---

---

# 29. Whole-Corpus Reasoning and Unknown-Pattern Discovery

Memoria's core claim depends on being able to reason reliably across a corpus too large to load at once.

Most questions can be handled through durable interpretation state plus iterative retrieval. The hardest case is not ordinary factual lookup, but distributed reasoning: patterns whose evidence is scattered broadly across the archive or that the author has not yet thought to ask about.

The primary risk of avoiding GraphRAG or a global machine-generated graph is therefore that agentic retrieval may miss some genuinely distributed patterns.

This is treated as a measured, continuously tested risk rather than ignored.

A small permanent evaluation set should contain questions designed specifically to require distributed corpus reasoning.

For example:

- identify recurring associations across years;
- detect people who repeatedly co-occur with a concept;
- find changes in language around an event;
- identify themes connecting otherwise unrelated periods;
- discover contradictions distributed across many sources.

If frontier-model agentic search repeatedly fails real examples, those failures become the benchmark for evaluating:

- GraphRAG;
- graph databases;
- corpus-wide clustering;
- topic models;
- additional summary structures;
- other retrieval systems.

Heavier machinery earns its place against observed failures.

> **Revised 2026-09-01** (ADR-0005). The gate above was not walked; it was set aside.
> The extraction, its clusters and `search_global` — including the summary half —
> ship with M2, chosen with the cost stated: the failure-first discipline is gone for
> GraphRAG, and the evaluation set above becomes a **regression suite** that gates
> nothing (part 15 §43.11). What the extraction actually answers is not this
> section's risk but part 06's gap — nothing proposed a Theme or gathered for one.
> The rest of the list (graph databases, clustering, topic models, summary structures)
> still enters only against an observed failure.
>
> **Build shape, later the same day** (ADR-0005 "Build shape"; ADR-0007): the
> whole-corpus reasoning this section worries about is done by the session agent, not
> a service — `search_global` with no query hands it every cluster summary at one level
> and §28's loop is the reduce. Embeddings enter by choice for the reason this section's
> discipline cannot cover: a retrieval miss is never observed.

---

---

# 30. Digests

Memoria maintains one derived compression layer under:

```text
digests/
```

Possible digests include:

- chapter digest;
- part digest;
- theme evidence map;
- arc digest;
- major-era digest;
- current-book digest.

A digest may compress.

It may not silently create new interpretation.

Every significant digest statement must link back to:

- interpretation records;
- claims;
- research;
- or ultimately source/author provenance.

Digests are machine-owned.

Manual edits are not durable.

They can be completely regenerated.

---

---

# 32. Context Builder

A session should never begin by dumping the repository into a model, nor should the author have to decide what fits.

The Context Builder is the layer that turns a book-sized corpus into a focused working context. It assembles the durable state most relevant to the task under a token budget, while leaving the broader archive available through retrieval tools.

**A budget that is reached is reported, never silent** (added 2026-09-01). When the
budget binds, assembly names what loaded only in part and how far it got — *"Bob's
audit-visible body loaded in part, 40 of 96 statements"*. Truncating in silence would be
§33.1's failure one level up: material the agent cannot know is missing. The report is
in countable units, not tokens; the token figures live on the manifest (§33).

The operating principle is:

> **Load what is predictably relevant. Retrieve what becomes relevant. Preserve what must survive the session.**

This allows the model to work with a focused context without losing access to the larger project.

For a section session:

```text
Tier 1 — always
    book.md                   the book's brief
    chapter.md                the chapter's brief
    section.md                the section's brief, including its declared scope
    draft.md                  the prose

Tier 2 — the declared scope, resolved
    the named entries' audit-visible bodies
    relevant claims
    active decisions
    local questions

Tier 3 — structural neighborhood
    previous section ending
    the next section's brief
    chapter digest

Tier 4 — on demand
    the named entries' gathered sets
    unpromoted candidates
    search results
    full sources
    research memos
    additional digests
```

**Tier 2 is declared, not inferred.** A section states its own scope in the author's
terms, as part of its brief (§2.1) rather than as a field of its own:

```text
Covers June 1839 to October 1841, and my interactions with Bob about
the conflict in the capital.
```

Assembly resolves that declaration through the subjects (part 06 §8.5). What loads is
an entry's audit-visible body — testimony, settlements and badged statements, badges
visible — short and dense. What does **not** load is its `[open]` lines and Memoria
notes (part 06 §8.2), its gathered set, which stays queryable at Tier 4, and the
unpromoted candidates, which never load at all.

The consequence matters for Invariant 1: **the working context is bounded by the size
of the declared scope, not by the number of subjects or entries.** Ten subjects and
four hundred promoted entries cost the same as two and twelve, because a session
still names a handful. The only thing that would break this is automatic inclusion —
transitive expansion from a named entry to its neighbours, or loading a whole
subject. Neither is done; §28's loop retrieves instead. The extraction's relations
(ADR-0005) change nothing here: they are read by gathering, `backlinks()` and
`search_global`, and a related entry is never loaded because its neighbour was.

The declared scope is **durable on the section**, as prose and only as prose. It is
never parsed into a structured field, and the resolution is never written back onto the
section: what a scope resolved to is recorded in that session's context manifest (§33),
against the subjects **as they stood that day**. Assembly is therefore reproducible
per session rather than globally deterministic, which is the honest form — what
satisfies a scope should move as the subjects learn.

The brief is also the section's contract. Prose that drifts from it produces a finding
whose disagreement set is `{passage, brief}`, resolvable by rewriting the prose or by
opening a conversation about the brief — never by editing the brief from the finding
card (part 09 §18).

**Drift is a set difference, not a check.** Assembly already resolves the brief to a
set of entries, and `appearances` (part 06 §8.11) already knows which entries a
section's prose touches. Prose appearing under `SUB-events/acquisition` in a section
whose brief never names it is drift, detected by subtracting two sets that exist for
other reasons — no model call, no bespoke question. Every audit question in the system
belongs to a subject (part 06 §8.1), and this is the one manuscript-layer check, which
turns out not to need to be one.

Drift is **not** evaluated against an *unconfirmed* brief: a brief summarized from the
prose agrees with the prose by construction, and the comparison would be circular.

A brief that is deliberately loose — "the middle of the book, roughly" — resolves to
few entries and will report drift constantly. The remedy is a tighter brief, which is
the intended pressure, though it is irritating early in a section's life.

A declared scope that names something with no entry does not fail. Assembly falls
back to the unpromoted candidate and reports that it did.

---

---

# 33. Context Manifests

Every session records exactly what initial context was supplied.

This is a key accuracy mechanism, not merely an audit feature.

The manifest's completeness claim is conditioned on the runtime layout: evidence
lives outside the session's working repo, direct reads are routed to the tool
surface, and the server-side ledger (`events.jsonl`, §10.4) records every evidence
read as it is served. Within that layout the manifest bounds model knowledge of the
archive. For a session run outside it — a development session in the memoria repo
itself — the manifest records tool-mediated retrieval only, and claims nothing about
direct reads.

The model is explicitly told that material outside its context has not necessarily been examined. It must use retrieval when a conclusion depends on evidence outside the loaded working set.

Research responses must describe their search scope so that a fluent answer cannot masquerade as a corpus-wide conclusion.

For example:

> Searched July–September 2011 communications, Bob-linked journal entries, and the acquisition event record. I did not perform a corpus-wide search of unrelated correspondence.

Memoria should never allow:

> “The archive shows...”

when the model has actually examined twelve documents.

## 33.1 An index reports nothing about its own recall

Subject-based assembly (part 06 §8.5) introduces a harder version of this problem
than search does.

When a writing agent works from an entry's gathered set **instead of** searching the
corpus, the completeness of that set determines what the chapter is written from. A
source that never joined the set is invisible, and the agent cannot know it is
missing. A search at least reports its query and can honestly say *"I did not search
unrelated correspondence."* An index says nothing.

Two obligations follow:

- **Assembly must report what it resolved** — which entries the declared scope named,
  which fell back to unpromoted candidates, and that the gathered sets are indexes
  rather than exhaustive searches.
- **Recall must be measured, not assumed.** The PoC's 348 resolved
  cross-references are the instrument; **gathered-set recall** over those links —
  a set metric, not recall@10 — is the measure of whether the index is complete
  enough to write from. See `poc-plan.md` §3 and part 15 §43.14.

**What discharges the first obligation** (added 2026-09-01): the **supplied context**
surface. It reports, for one session, the **working context** assembly produced and every
read served since — which entries the scope named, which fell back to unpromoted
candidates, what the budget truncated, and that gathered sets are indexes rather than
exhaustive searches. It is opened deliberately rather than watched, states countable
domain units rather than tokens, and claims only what Memoria **supplied**: the client
may compact served reads away, and an account that claimed to describe the model's
current knowledge would be this section's own error in a new place. Part 14 §40 is
amended accordingly; part 16 builds it at M5 and gates on it.

This is the central risk of the subject system and it is silent by nature. Part 06
§8.3 states it; §15's evaluation suite is where it is caught.

---

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

§33 is the part of this section the design leans on hardest, and it appears twice:
as the scope note under an answer — *"Searched July 2011 – June 2014 journals and
Bob-linked email… I did not search unrelated correspondence from that period"* — and
as *"31 more"* above the filter line. §27's filter list is that footer verbatim:
**"refine with filters — dates, people, contemporaneous only."**

What is new: the design turns `search_text` into **a surface the author drives**. One
query, results grouped by layer with per-layer counts and colours — MANUSCRIPT
3 passages (maroon), INTERPRETATION 4 records (blue), SOURCES 34 records (green).
§§25–33 describe retrieval as tools the model calls on the author's behalf; a search
screen is not described anywhere in the plan.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
