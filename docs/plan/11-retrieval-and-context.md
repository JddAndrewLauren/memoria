<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 25, 26, 27, 28, 29, 30, 32, 33 of the original memoria-plan.md -->

# 25. Retrieval Architecture

Memoria begins with a deliberately simple retrieval substrate.

The session model receives tools rather than a complicated RAG middleware stack.

Core tools:

```text
search_text(query, filters)
search_semantic(query, filters)

read_source(id)
read_session(id)
read_change(id)
read_claim(id)
read_impact(id)
read(path)

expand(chunk_id)
timeline(range, person?)
grep_repo(pattern, paths)

trace(ref)
backlinks(ref)

list(path)
```

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
THEME-control
ARC-bob-relationship
RES-20261018-003
IMP-20261103-004
chapter 8 source packet
```

This makes source corrections, reinterpretation, contradiction analysis, and manuscript-impact analysis much easier.

It also provides much of the useful graph behavior without requiring a dedicated graph database.

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

The operating principle is:

> **Load what is predictably relevant. Retrieve what becomes relevant. Preserve what must survive the session.**

This allows the model to work with a focused context without losing access to the larger project.

For a section session:

```text
Tier 1 — always
    book.md
    chapter.md
    section state.md          including its declared scope
    section draft.md

Tier 2 — the declared scope, resolved
    the named entries' author text
    the named entries' settlements
    relevant claims
    active decisions
    local questions

Tier 3 — structural neighborhood
    previous section ending
    next section outline
    chapter digest

Tier 4 — on demand
    the named entries' gathered sets
    unpromoted candidates
    search results
    full sources
    research memos
    additional digests
```

**Tier 2 is declared, not inferred.** A section states its own scope, in the author's
terms:

```text
Covers June 1839 to October 1841, and my interactions with Bob about
the conflict in the capital.
```

Assembly resolves that declaration through the subjects (part 06 §8.5). What loads is
an entry's author text and settlements — short and dense. What does **not** load is
its gathered set, which stays queryable at Tier 4, and the unpromoted candidates,
which never load at all.

The consequence matters for Invariant 1: **the working context is bounded by the size
of the declared scope, not by the number of subjects or entries.** Ten subjects and
four hundred promoted entries cost the same as two and twelve, because a session
still names a handful. The only thing that would break this is automatic inclusion —
transitive expansion from a named entry to its neighbours, or loading a whole
subject. Neither is done; §28's loop retrieves instead.

The declared scope is **durable on the section**, which makes assembly reproducible
and gives §39's resumption test something to resume from. It is also the section's
contract: prose that drifts from it produces a finding whose disagreement set is
`{passage, declared scope}`, resolvable by rewriting the prose or updating the
declaration. Neither is an error.

A declared scope that names something with no entry does not fail. Assembly falls
back to the unpromoted candidate and reports that it did.

---

---

# 33. Context Manifests

Every session records exactly what initial context was supplied.

This is a key accuracy mechanism, not merely an audit feature.

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
- **Recall must be measured, not assumed.** The PoC's 364 resolvable
  cross-references are the instrument; recall@10 over those links is the measure of
  whether the index is complete enough to write from. See `poc-plan.md` §3.

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
