<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 44 of the original memoria-plan.md -->

# 44. Build Order

Memoria should be built as a sequence of usable milestones rather than as several independent infrastructure projects.

---

## M0 — Repository, Evidence, and Provenance Foundation

Build:

- repository structure;
- Git conventions;
- source ingestion;
- immutable raw storage;
- normalized Markdown;
- stable source IDs;
- internal source anchors;
- temporal metadata;
- alias map;
- stable IDs for semantic objects;
- SQLite FTS5;
- semantic embeddings;
- basic dependency/backlink indexes;
- provenance reference model;
- human-change capture;
- core service layer shared by CLI, web UI, and Curator;
- `ModelBackend` abstraction;
- Claude Code subscription backend;
- controlled Memoria tool/MCP surface;
- `memoria rebuild`;
- `memoria validate`.

### Gate

Take a normalized source citation, click it, reach the exact evidence, then open the original file.

Make a direct edit to a theme and later retrieve its exact diff.

Delete the database and rebuild it without losing any durable information.

Authenticate Claude Code through the author's own supported Anthropic subscription and successfully run a Memoria tool-backed request through the `ModelBackend` abstraction.

---

## M1 — The Resumable Writing Loop

Build:

- session harness;
- three session modes;
- Context Builder;
- token budgeting;
- context manifests;
- immutable session transcripts;
- stable turn anchors;
- detailed event log;
- core retrieval tools;
- `trace()` and `backlinks()`;
- minimum viable post-session Curator;
- checkpoints;
- decisions;
- question extraction;
- provenance from Curator outputs to conversation turns;
- direct AI writing to canonical `draft.md`;
- explicit authorization capture;
- manuscript-write scoping;
- provenance for AI-written passages;
- draft-from-source-packet workflow;
- safe Git commits for AI manuscript work;
- responsive web UI;
- phone-friendly navigation;
- Home / Ask Memoria;
- Section view;
- Source viewer;
- Theme / Arc view;
- Research conversation;
- basic Review / manuscript-impact view;
- streamed model responses and activity;
- single write coordinator;
- graceful preservation and deferral when subscription capacity is unavailable.

### Gates

#### Resumption gate

Work deeply on a real section.

Leave it alone.

Return days or weeks later.

Memoria should restore enough state to continue without a manual recap.

Click an `[author]` interpretation created during the earlier session and arrive at the exact sentence in which it was expressed.

#### Web / phone gate

Open Memoria from both a desktop browser and a phone.

Ask a book-wide question whose answer requires retrieval outside the initial working context.

The user should not need to select files or manage context manually.

The answer should expose clickable provenance, and the same durable session should be resumable from either device.

#### AI writing gate

Research and outline a real section.

Tell Memoria:

> Draft this section from the source packet.

The resulting prose should be written directly into the canonical manuscript and committed.

Later, Memoria must be able to answer:

> Why does this paragraph say this?

and expose:

- the writing session;
- the authorization;
- source packet;
- source evidence;
- resulting Git change.

---

## M2 — Full Curator, Coherence, and Manuscript Impact

Build:

- ownership enforcement;
- Git-blame awareness;
- human-edit supremacy;
- human deletion boundaries;
- materiality classification;
- dependency propagation;
- conflict list;
- interpretation refresh;
- arc/theme propagation;
- digest generation;
- provenance validation on Curator commits;
- manuscript dependency analysis;
- manuscript-impact records;
- automatic candidate patches;
- confidence classification;
- dismissed-suggestion memory;
- batch authorization;
- post-write coherence checks.

### Gate

Change a major event date or correct an important arc.

Memoria should:

1. preserve the author's correction;
2. identify every materially affected manuscript passage;
3. distinguish high-confidence conflicts from softer interpretive implications;
4. prepare appropriate proposed revisions;
5. change no canonical prose before authorization;
6. accept a scoped batch instruction;
7. directly rewrite the authorized passages;
8. preserve provenance for every rewrite;
9. leave unauthorized passages untouched;
10. allow the entire Curator/AI pass to be reverted cleanly.

---

## M3 — Research Depth

Build:

- investigation skill;
- contradiction-search discipline;
- compare-accounts workflow;
- source-packet workflow;
- persistent research state;
- research memos;
- question-queue workflow;
- memo-to-interpretation curation;
- rigorous search-scope reporting.

### Gate

Give Memoria a genuinely contested interpretation.

It should independently:

- plan research;
- find supporting evidence;
- seek contradictory evidence;
- distinguish contemporaneous from retrospective material;
- inspect full sources rather than relying on chunks;
- explain uncertainty;
- create a durable memo;
- construct a clickable evidence chain.

---

## M4 — Whole-Book Reasoning and Hardening

Build:

- book/part/theme/arc digests;
- broader whole-book reasoning workflows;
- distributed-pattern evaluation;
- stale-state detection;
- health checks;
- Curator activity digest;
- provenance audits;
- broken-link repair;
- manuscript drift reports;
- advanced web UI polish;
- richer provenance exploration;
- richer research workspace;
- advanced manuscript review tooling.

### Gate

Ask Memoria:

> Why do we currently believe control is one of the major themes or arcs of the book?

The answer should synthesize the case but expose direct links all the way down to:

- primary source records;
- exact author conversations;
- direct author edits;
- contrary evidence;
- research memos;
- manuscript passages influenced by the interpretation.

Nothing important should terminate at:

> because the AI previously concluded that.

---
