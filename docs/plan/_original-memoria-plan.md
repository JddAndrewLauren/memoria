# Memoria — Build Plan

> **Project name:** Memoria  
> **Purpose:** An attributable AI research-and-writing environment for working accurately across a book-sized source archive far beyond any single model context window.

---

## 0. Purpose

Memoria is an AI research-and-writing system for working accurately across a source archive far larger than any model context window.

Its primary promise is simple:

> **The author should be able to work at the scale of the book without having to manage the limits of the model.**

The user should not have to think about token budgets, manually decide which source files fit into a prompt, repeatedly summarize earlier research, or wonder whether the AI has become confused because the archive is too large.

Memoria absorbs that complexity.

It maintains a durable model of the book, assembles focused working context, searches the wider archive when needed, expands back to original sources, and preserves the provenance of every important conclusion. This makes it possible to use frontier models across a book-sized corpus without treating a large context window as a substitute for evidence discipline.

Memoria should behave less like a chatbot with document access and more like a research and writing collaborator that:

- can work across a source archive much larger than any single model context;
- automatically assembles the right context for the task at hand;
- retrieves deeper evidence on demand rather than forcing the whole corpus into one prompt;
- distinguishes primary evidence from retrospective evidence and later interpretation;
- shows exactly which sources were searched and which evidence supports a conclusion;
- reasons across themes, arcs, people, events, claims, chapters, and time without collapsing those distinctions;
- can independently research contested questions and actively seek disconfirming evidence;
- knows the current state of the book and where a section fits into the whole;
- can directly draft and revise canonical manuscript prose when explicitly authorized;
- can notice when changes elsewhere in the project imply changes to the manuscript;
- can propose those manuscript changes without applying them unprompted;
- preserves the author's evolving intent over time;
- can resume work after long gaps without reconstruction;
- and can explain why it believes anything it believes.

The final requirement is foundational.

Memoria must never become an opaque second memory whose conclusions can no longer be traced to their origins.

Every durable assertion must be attributable.

A durable statement should ultimately resolve to one or more of:

1. an immutable source record;
2. an exact author turn in a preserved AI conversation;
3. an exact direct human edit preserved in Git;
4. or, for model inference, an explicit argument grounded in such material.

The goal is therefore not simply persistent memory.

It is **persistent, inspectable, attributable memory in service of a manuscript**.

## 0.1 Product Thesis

Memoria's selling point is not that it remembers where the author left off, although it does.

Its central value is that it makes **large-context AI work trustworthy and usable**.

A frontier model should be able to help with a project whose relevant evidence is far larger than its context window without requiring the author to become a retrieval engineer. Memoria provides the persistent state, retrieval loop, source expansion, provenance, temporal discipline, and scope reporting that make this possible.

The promise is:

> **Bring the whole archive. Ask the real question. Memoria handles the context.**

Resumability follows naturally because the understanding required to answer future questions is stored durably instead of being trapped inside one model session.

---

# 1. Core Design Principles

## 1.1 The user works at book scale, not context-window scale

Memoria exists to hide model-context management from the author.

The archive may contain millions of tokens. A single task may depend on material scattered across years of journals, email, interviews, notes, research, prior AI sessions, and manuscript drafts.

The solution is not to hope that one ever-larger prompt contains everything important.

Memoria instead combines:

- durable structured project state;
- explicit interpretation records;
- targeted context assembly;
- iterative text and semantic retrieval;
- source expansion back to full documentary context;
- book-level digests used only as compression;
- provenance tracing;
- explicit search-scope reporting;
- and adversarial research practices such as contradiction searches.

The author should therefore be able to ask questions naturally:

> What changed in my understanding of Bob between 2011 and 2014?

> Does Chapter 6 overstate the evidence for this interpretation?

> What themes connect the acquisition period to the events in Part III?

without first deciding which documents fit inside the model's context window.

Context-window limits are an implementation concern for Memoria, not a workflow concern for the author.

---

## 1.2 The repository is the system


The durable state of Memoria lives in an ordinary directory of human-readable files under Git.

There is no proprietary database that contains the only authoritative representation of the book.

The manuscript, interpretations, research, conversations, sources, decisions, questions, and working state should remain intelligible if every Memoria-specific program disappears.

SQLite and other indexes may make the repository faster to search and reason over, but they are caches.

**Files are truth. Indexes are rebuildable.**

---

## 1.3 Provenance is constitutional

Every durable assertion about the book must identify where it came from.

A statement may be:

- **`[source]`** — directly supported by documentary evidence;
- **`[author]`** — a position actually expressed or deliberately written by the author;
- **`[inferred]`** — an interpretation produced by a model from identified evidence and/or author material;
- **`[open]`** — a possibility worth retaining but not currently adopted as the working interpretation.

Each statement must link to its basis.

A model may compress or summarize provenance, but it may never sever the chain.

The desired property is simple:

> **Keep clicking and eventually reach what was actually written, said, or changed.**

---

## 1.4 Provenance is transitive and terminal

Derived material may cite other derived material for convenience, but provenance must eventually terminate in original records.

For example:

```text
Book-level observation
        ↓
Theme
        ↓
Claim
        ↓
Research memo
        ↓
SRC-0184
SRC-0912
SES-20260912-1432#T017
CHG-20261014-0917
```

The research memo is useful context.

It is not the final authority.

The terminal records are the original source evidence and attributable author actions.

---

## 1.5 One authoritative representation of meaning

Memoria should not maintain several competing semantic models of the book.

There is one curated **interpretation layer** containing:

- themes;
- arcs;
- people;
- events;
- important claims;
- chronology;
- structural interpretation.

Other generated summaries are compressions of this layer and its evidence.

They are not independent semantic authorities.

This prevents the project from gradually accumulating contradictory understandings across graph summaries, agents, vector stores, cached summaries, and model memories.

---

## 1.6 Evidence and interpretation remain distinct

A journal entry from 2011 is evidence.

A conclusion in 2026 about what that entry means is interpretation.

A later recollection of the 2011 event is also evidence, but it is retrospective evidence rather than contemporaneous evidence.

Memoria must preserve these distinctions explicitly.

No interpretation process may silently rewrite the underlying evidence.

---

## 1.7 Human interpretation edits are supreme

The Curator may organize, infer, connect, summarize, challenge, and annotate.

It may not silently overwrite interpretation text deliberately authored or edited by the human.

If new evidence conflicts with a human-authored interpretation, Memoria should surface the conflict rather than replace the author's text.

Human edits are therefore not merely file changes.

They are attributable author acts.

---

## 1.8 Conversations are part of the intellectual record

AI conversations often contain meaningful author thinking that exists nowhere else.

They cannot be treated as disposable chat history.

Every Memoria session is preserved as an immutable transcript with stable turn identifiers.

If a later theme says:

> `[author] Control was primarily about fear of losing autonomy.`

the author should be able to click the citation and see the exact conversation in which that position was expressed.

Memoria should remember the author's original words, not merely the Curator's paraphrase of them.

---

## 1.9 Direct edits are part of the intellectual record

A direct edit in Obsidian or another editor may express an important change in thinking without an accompanying AI conversation.

Git therefore functions not merely as version control but as an author-history substrate.

Meaningful human editing bursts are preserved as identifiable changes.

A later model should be able to answer:

> When did I change my mind about this?

and point directly to the relevant diff.

---

## 1.10 AI manuscript authorship is first-class

The canonical manuscript is not reserved to human-authored prose.

A passage may be:

- written entirely by the author;
- drafted by AI at the author's request;
- written by the author and polished by AI;
- generated by AI from a source packet;
- rewritten by AI after a factual correction;
- written by AI and then substantially edited by the author.

All are legitimate canonical manuscript states.

The important boundary is not:

> human writes; AI advises.

It is:

> **Memoria may autonomously observe, reason about, and recommend manuscript changes. Modification of canonical manuscript prose requires explicit author authorization.**

Once authorized, the AI should be allowed to perform the work directly rather than forcing the author to manually copy suggestions into the manuscript.

---

## 1.11 Structure should earn its existence

Memoria begins with a deliberately small ontology.

Add formal structure when repeated use demonstrates that free text and links are insufficient.

Do not build a graph database because relationship graphs are theoretically useful.

Do not build GraphRAG because global retrieval might theoretically fail.

A real failure becomes a benchmark.

New infrastructure must beat the existing system against that benchmark before it becomes permanent.

---

## 1.12 The system exists to produce a book

Memoria can easily become an absorbing software project.

That is a failure condition.

Once the core loop works, improvements to Memoria should occur alongside actual progress on the manuscript.

If the system becomes more sophisticated while the book does not advance, development stops.

---

# 2. Repository Structure

A representative repository:

```text
memoria/
│
├── book.md
├── outline.md
├── chronology.md
│
├── chapters/
│   └── 08/
│       ├── chapter.md
│       └── sections/
│           └── 03/
│               ├── draft.md
│               └── state.md
│
├── themes/
│   └── control.md
│
├── arcs/
│   └── bob-relationship.md
│
├── people/
│   ├── _aliases.yaml
│   └── bob.md
│
├── events/
│   └── acquisition.md
│
├── claims/
│   └── CLM-0041.md
│
├── decisions.md
├── questions.md
│
├── research/
│   ├── memos/
│   └── packets/
│
├── impacts/
│   └── IMP-20261103-004.md
│
├── sources/
│   ├── raw/
│   └── normalized/
│
├── sessions/
│   └── 2026/
│       └── 09/
│           └── SES-20260912-1432/
│               ├── transcript.md
│               ├── metadata.yaml
│               ├── context-manifest.json
│               └── events.jsonl
│
├── changes/
│   └── CHG-20261014-0917.md
│
├── digests/
│
└── .memoria/
    ├── index.db
    ├── config.yaml
    ├── manifests/
    └── cache/
```

The repository should remain understandable without Memoria-specific software.

---

# 3. State Classes and Ownership

Every durable artifact belongs to an explicit class.

| Class | Examples | Authority |
|---|---|---|
| **Evidence** | `sources/**` | Immutable documentary record |
| **Interaction record** | `sessions/**` | Immutable record of conversations |
| **Manuscript** | `chapters/**/draft.md` | Canonical book prose; human- or AI-authored, but AI writes require author authorization |
| **Interpretation** | themes, arcs, people, events, claims, chronology | Shared, with human supremacy |
| **Working state** | `state.md`, decisions, questions, research, impacts | Primarily machine-maintained |
| **Change record** | Git history + `changes/**` | Record of direct human, AI, and Curator edits |
| **Derived** | digests, indexes, dependency data | Machine-only, rebuildable |

These distinctions matter because different classes have different epistemic meanings.

A session transcript proves that someone said something.

A source proves that a document contains something.

A Git change proves that material changed.

None of these alone proves that an interpretation is correct.

---

# 4. Stable Identity and Links

Everything that may need to be cited receives a durable identity.

Examples:

```text
SRC-000184                normalized source record
SES-20260912-1432         AI session
SES-20260912-1432#T017    exact transcript turn
CHG-20261014-0917         direct change
IMP-20261103-004          manuscript-impact record
CLM-0041                  important claim
RES-20261018-003          research memo
DEC-0088                  author decision
```

Themes, arcs, people, events, chapters, and sections also carry stable IDs in frontmatter so file renames do not destroy identity.

Ordinary Markdown links remain the primary human-facing linking mechanism.

For example:

```markdown
[SRC-000184 ¶17](../../sources/normalized/SRC-000184.md#src-000184-p17)
```

or:

```markdown
[our September 12 conversation, turn 17]
(../../sessions/2026/09/SES-20260912-1432/transcript.md#t017)
```

Memoria should not require a proprietary URI scheme merely to understand its own citations.

---

# 5. Source Ingestion

## 5.1 Raw evidence

Original files are preserved untouched under:

```text
sources/raw/
```

They are never rewritten by the Curator.

Where practical, hashes of raw files should be stored to detect accidental modification.

---

## 5.2 Normalized source records

Documents are converted into searchable Markdown records.

Example:

```yaml
---
id: SRC-000184
source_type: journal
recorded_date: 2011-07-17
event_date: 2011-07-17
date_confidence: exact
contemporaneous: true
original_file: ../raw/journals/2011.docx
original_locator: "Entry dated July 17, 2011"
---
```

A natural documentary boundary should normally define a record:

- journal entry;
- email;
- individual note;
- message or logical message thread;
- meeting transcript;
- document section.

Search-time chunking occurs only in the index.

The normalized record remains the unit of evidence.

---

## 5.3 Stable internal anchors

Normalized records receive stable paragraph or logical-section anchors.

For example:

```markdown
<a id="src-000184-p17"></a>

I called Bob that evening...
```

This allows Memoria to cite the precise relevant location rather than merely pointing at a large document.

Where the original file format supports deep linking, Memoria should expose an **Open original** action as well.

A source view should ideally provide:

```text
Normalized evidence
Original file
Original locator/page/message
Recorded date
Event date
Source type
Provenance metadata
```

---

# 6. Temporal Discipline

Personal archives contain several kinds of time that must not collapse into one another.

Memoria distinguishes:

- **event date** — when something happened;
- **recorded date** — when the source was created;
- **contemporaneous evidence** — created near the event;
- **retrospective evidence** — later recollection or interpretation.

Therefore:

> What happened in July 2011?

and:

> What did I believe in July 2011?

are different research questions.

A 2018 recollection may help answer the first.

It must not silently answer the second.

This distinction is enforced in research skills and represented in search filters.

---

# 7. Alias and Entity Resolution

Names in a personal archive are messy.

A person may appear as:

```text
Bob
Robert
R.
Bob Smith
my brother-in-law
```

A canonical alias map lives in:

```text
people/_aliases.yaml
```

Alias resolution is one of the few curation activities where ambiguity should normally be surfaced to the author.

A mistaken theme summary is reversible.

A mistaken entity merge can silently contaminate thousands of retrieval results.

Memoria should therefore prefer unresolved ambiguity to confident misidentification.

---

# 8. The Interpretation Layer

The interpretation layer is Memoria's maintained understanding of the book.

It consists initially of five major object types.

## 8.1 Themes

Examples:

```text
control
ambition
obligation
memory
inheritance
```

A theme file should answer:

- what the theme currently means;
- how it develops;
- where it appears;
- competing readings;
- important supporting claims;
- contradictions;
- unresolved threads;
- affected chapters or arcs.

---

## 8.2 Arcs

Arcs are first-class because they are directly useful to writing.

An arc represents change across time or narrative structure.

Examples:

```text
Bob relationship
loss of institutional trust
changing understanding of success
family obligation
```

An arc may span people, events, themes, and chapters.

A representative structure:

```markdown
# Bob Relationship

## Current reading

## Beginning state

## Turning points

## End state

## Evidence

## Competing interpretations

## Chapter use

## Open threads
```

Themes describe recurring meaning.

Arcs describe transformation.

They should not be collapsed merely because both involve interpretation.

---

## 8.3 People

Person files may contain:

- identity and aliases;
- role in events;
- relationship to the narrator;
- changing understanding over time;
- associated arcs;
- relevant claims;
- source trails;
- open ambiguities.

---

## 8.4 Events

Event files may collect:

- chronology;
- participants;
- source accounts;
- disagreements between accounts;
- later interpretations;
- relevant themes and arcs;
- unresolved factual questions.

---

## 8.5 Claims

Not every observation needs its own claim file.

Claims become first-class when they are:

- important;
- contested;
- repeatedly referenced;
- structurally consequential;
- or supported by a substantial case.

Example:

```markdown
# CLM-0041

## Claim

Bob probably knew about the acquisition before July 17.

## Status

inferred

## Confidence

moderate

## Supporting evidence

- [SRC-00184 ¶17](...)
- [SRC-00391 ¶4](...)

## Contradicting evidence

- [SRC-01102 ¶8](...)

## Author material

- [SES-20260912-1432 T017](...)

## Reasoning

...

## Open questions

...
```

A claim is therefore not merely a sentence.

It is an inspectable argument.

---

# 9. Attribution Model

Every durable interpretation statement must carry its epistemic status and provenance.

## 9.1 Source statements

```markdown
[source] Bob called on July 17.
— [SRC-00184 ¶17](...)
```

This means the cited source directly states or supports the assertion.

---

## 9.2 Author statements

```markdown
[author] I now think the conflict was primarily about autonomy.
— [SES-20260912-1432 T017](...)
```

or:

```markdown
[author] The conflict should be framed primarily around autonomy.
— [CHG-20261014-0917](...)
```

The Curator must not turn the AI's suggestion into an `[author]` position merely because the author discussed it.

There must be identifiable author evidence.

---

## 9.3 Inferred statements

```markdown
[inferred] Fear of losing control appears to intensify after the acquisition.

Basis:
- [SRC-00184 ¶17](...)
- [SRC-00392 ¶8](...)
- [SES-20260912-1432 T017](...)
```

An inference should identify both its conclusion and its basis.

For important inferences, the reasoning should be preserved as a claim or research memo rather than regenerated from scratch each time.

---

## 9.4 Open interpretations

Exploratory thinking should remain exploratory.

```markdown
[open] One possibility is that the later hostility reflects embarrassment rather than betrayal.
```

An `[open]` idea is not part of the current accepted interpretation.

This gives interesting speculation a durable home without allowing it to silently harden into doctrine.

---

# 10. Session Records

Every Memoria AI session is a permanent part of the project record.

A session directory contains:

```text
transcript.md
metadata.yaml
context-manifest.json
events.jsonl
```

## 10.1 transcript.md

Contains the human-readable conversation.

Every turn receives a stable anchor:

```markdown
## T016 — Assistant

...

## T017 — Author

I think what I've been calling ambition is actually more about fear of losing control.

## T018 — Assistant

...
```

The transcript is immutable once the session closes.

Corrections or annotations are layered separately rather than silently changing history.

---

## 10.2 metadata.yaml

Records information such as:

```yaml
session_id:
started:
ended:
model:
provider:
mode:
chapter:
section:
system_prompt_version:
```

This does not attempt to reproduce the model.

It records enough context to understand what kind of interaction occurred.

---

## 10.3 context-manifest.json

Records what Memoria supplied to the model.

For example:

```text
book.md
chapter 8 brief
section 8.3 state
theme/control
arc/bob-relationship
five source records
two research memos
```

It also records:

- token budgeting;
- truncation;
- explicitly excluded material;
- retrieval performed during the session.

This provides a boundary around model knowledge.

A later audit can distinguish:

> The model concluded X after inspecting these 14 sources.

from:

> The model spoke as though it knew the archive but had only seen three documents.

---

## 10.4 events.jsonl

This is the detailed machine audit record.

It may contain:

- tool calls;
- searches;
- retrieved result IDs;
- files opened;
- writes performed;
- Curator handoff events.

The Markdown transcript remains the human interface.

The event log exists when deeper reconstruction is required.

---

# 11. Direct Human Edits

The author should be able to work normally in Obsidian or another editor.

Memoria should not require every thought to pass through the AI.

A lightweight repository watcher or synchronization layer observes human changes.

After a meaningful editing burst, or before an agent modifies affected files, Memoria creates a human checkpoint commit.

That change receives an identifier such as:

```text
CHG-20261014-0917
```

A machine-generated projection under `changes/` provides a human-readable view:

```markdown
# CHG-20261014-0917

Date: 2026-10-14 09:17
Commit: 9b07fa1
Files:
- themes/control.md

## Diff

-Control appears primarily as a professional concern.
+Control is fundamentally personal and only later becomes professional.
```

Git remains canonical.

`changes/` is a deterministic, rebuildable view that makes Git history easy to link from Markdown and the UI.

A direct edit proves **what changed**.

Memoria must not invent **why** it changed unless that reason exists in a conversation, note, or explicit commit annotation.

---

# 12. The Curator

The Curator is an autonomous background agent responsible for maintaining interpretation and working state.

It never edits documentary evidence.

It may inspect manuscript prose autonomously.

It may propose manuscript changes autonomously.

It may only modify canonical manuscript prose when the author has explicitly authorized that write.

---

## 12.1 Curator triggers

The Curator runs after events such as:

| Event | Response |
|---|---|
| AI session ends | Post-session curation |
| Human edits interpretation files | Propagation + manuscript-impact pass |
| Human edits manuscript | Interpretation/continuity impact scan |
| Research memo completes | Fold supported findings into interpretation |
| New evidence ingested | Index, alias scan, question/theme/arc impact scan |

Passes are debounced and materiality-gated.

A spelling correction should not trigger a cascade through the book.

---

# 13. Post-Session Curation

After a session, the Curator reads the transcript.

It extracts only what actually occurred.

## 13.1 Decisions

A decision exists only when the author actually decides something.

> “Let's keep Bob's knowledge ambiguous until chapter 9.”

qualifies.

> “Maybe we could keep it ambiguous.”

does not.

Every recorded decision links to the exact author turn.

---

## 13.2 Checkpoint

The relevant section or chapter state is updated with:

- what was attempted;
- what changed;
- approaches rejected;
- present state;
- immediate next step.

Checkpoints are the foundation of resumability.

---

## 13.3 Questions

The Curator records:

- newly raised questions;
- resolved questions;
- partially resolved questions;
- questions deferred or deemed unknowable.

---

## 13.4 Interpretation changes

The Curator is deliberately conservative.

If the author muses about an interpretation, it belongs under an open thread.

If the author clearly adopts a position, it may enter current interpretation as `[author]`, citing the precise transcript turn.

If the Curator independently identifies a pattern from evidence, it may enter as `[inferred]`, with supporting provenance.

The Curator may never convert exploratory discussion into an author belief merely because doing so makes the knowledge base neater.

---

# 14. Human-Edit Supremacy

Git authorship serves as the ownership ledger.

Before changing existing interpretation text, the Curator determines who last meaningfully authored it.

## 14.1 Curator-authored span

The Curator may:

- rewrite;
- update;
- reorganize;
- remove;

provided provenance remains valid.

## 14.2 Human-authored span

The Curator may not silently rewrite it.

If new evidence conflicts with it, the Curator adds an adjacent note:

```markdown
> **Memoria note — 2026-10-18**
>
> Later research cuts against the interpretation above.
> See [RES-20261018-003](...) and [SRC-02914](...).
> The author text has been left unchanged.
```

The conflict is also added to the curation-conflict queue.

These conflicts are not administrative noise.

They are often where the most interesting intellectual work lies.

---

# 15. Human Deletions Are Boundaries

If the author deletes a Curator-created interpretation, the Curator should not recreate it from the same evidence during the next pass.

The deletion itself is an author action.

The system remembers it.

Materially new evidence may justify resurfacing the possibility, but it should appear explicitly as something previously rejected or removed.

This prevents autonomous curation from repeatedly arguing with the author.

---

# 16. Dependency and Propagation

Interpretation files link explicitly to affected material.

Dependencies may arise from:

- ordinary Markdown links;
- stable IDs;
- `affects:` frontmatter;
- chapter and section references;
- claim relationships;
- source packets;
- provenance relationships;
- explicit manuscript dependencies accumulated during writing and research.

SQLite indexes these relationships into a rebuildable dependency graph.

If the author materially changes:

```text
themes/control.md
```

Memoria may calculate affected material such as:

```text
arcs/bob-relationship.md
claims/CLM-0041.md
chapters/02/draft.md#p7
chapters/08/sections/03/state.md
digests/chapter-08.md
```

Interpretation and derived material may be propagated automatically according to ownership rules.

The manuscript is handled through a dedicated **manuscript-impact workflow**.

---

# 17. Manuscript Impact Analysis

When a dependency reaches canonical manuscript prose, Memoria asks whether the underlying change materially affects the passage.

Questions include:

- Does the passage now contain a factual contradiction?
- Does it rely on an interpretation that has been rejected or revised?
- Does it reveal information earlier than the current narrative plan permits?
- Does it mischaracterize a person or arc under the current interpretation?
- Does it cite or imply evidence whose status has changed?
- Does it remain technically true but frame the material in a way inconsistent with the current book?
- Does a chronology correction alter causation, sequence, or what the narrator could have known?

If no meaningful impact exists, nothing happens.

If an impact is plausible, Memoria creates a manuscript-impact record.

Example:

```text
IMP-20261103-004

Trigger:
    CHG-20261103-1024
    Author revised ARC-bob-relationship

Affected passage:
    chapters/02/draft.md#p7

Assessment:
    High-confidence contradiction

Reason:
    Paragraph treats Bob's July 15 behavior as evidence
    of foreknowledge. The revised timeline now places
    his probable knowledge on July 18.

Basis:
    ARC-bob-relationship
    EVT-acquisition
    CLM-0041
    SRC-0184
    SRC-0391
```

Memoria may prepare a proposed rewrite automatically.

It may not apply that rewrite to `draft.md` without authorization.

---

# 18. Manuscript Impact Suggestions

Manuscript suggestions are first-class working state.

Typical categories include:

```text
factual contradiction
chronology conflict
unsupported assertion
weakened claim
theme misalignment
arc misalignment
premature reveal
continuity issue
source/citation change
editorial opportunity
```

Each suggestion records:

- what triggered it;
- affected manuscript location;
- confidence;
- explanation;
- relevant evidence and interpretation records;
- proposed action;
- optional candidate patch;
- current disposition.

Suggested actions may include:

```text
rewrite
review
remove
qualify
move
fact-check
leave unchanged
```

A suggestion can remain unresolved indefinitely without changing the manuscript.

This lets Memoria be proactive without becoming intrusive.

---

# 19. Manuscript Authorization

Memoria recognizes three levels of manuscript authority.

## 19.1 Autonomous reading and analysis

Memoria may read and reason over the manuscript whenever appropriate.

No authorization is required to detect:

- contradictions;
- stale interpretations;
- structural problems;
- continuity problems;
- potential improvements;
- downstream consequences of changes elsewhere.

---

## 19.2 Autonomous suggestions

Memoria may autonomously:

- create manuscript-impact records;
- explain why a passage may need attention;
- prepare candidate rewrites;
- generate diffs;
- rank suggested changes by confidence or importance.

Preparing prose is not the same as modifying canonical prose.

---

## 19.3 Authorized manuscript modification

Memoria may directly modify `draft.md` when the author explicitly authorizes the work.

Authorization may occur through natural language:

```text
Rewrite that paragraph.

Apply this suggestion.

Fix those four factual conflicts.

Take a pass at chapter 2 using the revised Bob arc.

Draft section 8.3 from the source packet.

Apply all high-confidence chronology fixes, but only
show me suggestions for interpretive changes.
```

Authorization may also occur through interface actions such as:

```text
Apply
Rewrite
Accept selected
Apply high-confidence fixes
```

Authorization is scoped.

A request to rewrite one paragraph does not authorize unrelated changes elsewhere in the chapter.

A request to revise a chapter may authorize broad work within that chapter.

A request to apply a defined batch of manuscript-impact suggestions authorizes that batch.

Memoria records the authorization boundary before writing.

---

# 20. Provenance of AI-Written Manuscript

AI-authored prose is first-class manuscript prose.

Memoria does not label it as lesser, temporary, or noncanonical merely because a model wrote it.

What matters is being able to reconstruct how it came to exist.

A canonical manuscript change made by AI should preserve, where applicable:

```text
manuscript location
previous text
new text
authorizing session + turn
triggering change or research
manuscript-impact record
source packet
relevant claims
relevant evidence
model/provider metadata
Git commit
```

For example:

```text
chapters/02/draft.md#p7

Written:
    2026-11-03

By:
    AI during SES-20261103-1041

Authorized by:
    SES-20261103-1041#T008
    "Rewrite it using the corrected timeline."

Triggered by:
    CHG-20261103-1024

Suggestion:
    IMP-20261103-004

Evidence:
    SRC-0184
    SRC-0391

Commit:
    31cb8d2
```

The useful question is not merely:

> Human or AI?

It is:

> **How did this passage get here?**

Memoria should answer that precisely.

---

# 21. Batch Authorization

Author supervision should not become approval-dialog theater.

Memoria may group related manuscript-impact suggestions.

For example:

```text
12 manuscript impacts found after chronology revision

4 high confidence
    Direct factual contradictions

5 medium confidence
    Existing prose relies on superseded interpretations

3 low confidence
    Possible framing implications
```

The author may issue a scoped instruction such as:

> Rewrite the four high-confidence conflicts. Prepare diffs for the five medium-confidence changes. Leave the low-confidence ones alone.

Memoria may then modify all four canonical passages directly.

Each resulting modification remains individually traceable to:

- its trigger;
- evidence;
- suggestion;
- authorization;
- Git change.

---

# 22. Editorial Suggestions Beyond Contradictions

Memoria's manuscript reasoning is not limited to factual errors.

Interpretive changes may have narrative consequences even when existing prose remains factually correct.

For example, suppose:

```text
themes/control.md
```

changes from:

> Control is primarily about professional authority.

to:

> Control is primarily about fear of dependence; professional authority is one manifestation of it.

A chapter may contain no factual error but still frame several events primarily as ambition.

Memoria may identify those passages and report:

```text
Chapter 2 ¶14–17

The events remain accurate, but the interpretation here
is now materially out of step with the current Control theme.

Current framing:
    professional ambition

Current theme:
    fear of dependence expressed through professional control

Suggested action:
    preserve events; reconsider interpretive emphasis
```

It may also prepare a candidate revision.

The author determines whether the canonical manuscript changes.

This lets Memoria function as a persistent developmental editor as well as a research and fact-checking system.

---

# 23. Provenance Validation

Provenance should be mechanically testable.

A command such as:

```bash
memoria validate
```

checks for:

- unresolved source IDs;
- broken links;
- missing transcript turns;
- missing change records;
- `[source]` assertions without sources;
- `[author]` assertions without author records;
- `[inferred]` assertions without a basis;
- AI manuscript writes without an identifiable authorization;
- manuscript-impact records whose triggers no longer resolve;
- derived summaries that introduce unsupported claims;
- provenance chains that terminate in another derived artifact instead of original material.

Curator commits should fail validation when they introduce malformed provenance.

This converts attribution from a best practice into an architectural invariant.

---

# 24. Model Runtime

Memoria should separate its durable architecture from the model runtime used to operate on it.

The preferred initial runtime is **Claude Code authenticated through the author's own supported Anthropic Claude subscription**, rather than requiring pay-as-you-go API usage for normal personal operation.

Conceptually:

```text
Phone / browser
      ↓
Memoria web service
      ↓
ModelBackend
      ↓
Claude subscription backend
      ↓
Claude Code
      ↓
Author's Claude Pro / Max subscription
```

The subscription-backed runtime is an implementation choice, not canonical architecture. Memoria's repository, provenance model, retrieval rules, manuscript authorization, and intellectual state must remain independent of it.

The runtime boundary should look like:

```text
                 Memoria
                    │
              ModelBackend
                    │
        ┌───────────┴───────────┐
        │                       │
ClaudeSubscriptionBackend   AnthropicAPIBackend
        │                       │
   Claude Code               optional later
```

Only the subscription-backed backend is required initially. The abstraction exists so Memoria can later add API access, another provider, local models, specialized models, or a hybrid policy without changing durable project state.

---

## 24.1 Division of responsibility

Claude Code already supplies much of the generic agent runtime Memoria would otherwise need to build.

### Claude Code provides

- authenticated model access through a supported Anthropic subscription;
- multi-step agentic execution;
- tool invocation;
- streaming responses;
- resumable model sessions where useful;
- file-aware execution;
- and MCP/tool integration.

### Memoria provides

- canonical repository state;
- source normalization;
- provenance;
- context assembly;
- retrieval;
- temporal discipline;
- interpretation state;
- research procedures;
- manuscript authorization;
- manuscript-impact analysis;
- Git history;
- resumability;
- and the user interface.

Claude Code is the initial **agent runtime**.

Memoria is the **intellectual system**.

---

## 24.2 Controlled tool access

Memoria should not simply grant Claude Code unrestricted authority over the repository.

The preferred arrangement is to expose controlled Memoria tools, for example:

```text
memoria.search()
memoria.search_semantic()
memoria.read_source()
memoria.timeline()
memoria.trace()
memoria.backlinks()
memoria.read_theme()
memoria.read_arc()
memoria.read_claim()
memoria.build_source_packet()
memoria.propose_manuscript_change()
memoria.apply_authorized_change()
```

Research sessions can operate with canonical writes disabled except for explicit durable research outputs.

Interpretation changes pass through Curator ownership and provenance rules.

Canonical manuscript writes pass through the explicit authorization model defined in this plan.

This allows Memoria to benefit from a powerful agent runtime without weakening its invariants.

---

## 24.3 Subscription usage is variable capacity

A subscription-backed runtime must be treated as a capacity-constrained resource rather than infinitely available compute.

Memoria must not hard-code assumptions about message counts, token allowances, model availability, or reset windows. Capacity can vary with subscription tier, provider policy, model choice, conversation length, tool use, and research depth.

If model capacity is temporarily unavailable:

```text
Claude available
      ↓
normal operation

usage capacity unavailable
      ↓
preserve current state
      ↓
keep repository / search / UI available
      ↓
defer non-urgent model work
      ↓
resume safely when capacity returns
```

A usage limit must never cause loss of research state, manuscript work, pending Curator actions, authorization records, or provenance.

---

## 24.4 Interactive work has priority

Subscription capacity should be allocated according to user value.

Default priority:

```text
1. Interactive author conversation and writing
2. Explicitly requested research
3. Necessary post-session curation
4. Manuscript-impact analysis
5. Digest regeneration
6. Health scans and speculative background analysis
```

When capacity is constrained, lower-priority work waits. Memoria should not consume substantial subscription capacity on housekeeping while preventing the author from working interactively.

---

## 24.5 Optional API fallback

An Anthropic API backend may be added later. Possible policies include:

```text
subscription only
subscription preferred, API fallback
API only
provider-selectable per task
```

The initial build does not require API fallback.

If fallback is added, it should be explicit and configurable because API usage has separate billing behavior. The author should be able to tell whether a task is using subscription capacity or metered API usage.

---

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
person
source type
contemporaneous/retrospective
chapter
theme
arc
record class
```

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
10. revisit the interpretation layer;
11. form or revise a conclusion.

The agent is not expected to get the right evidence from a single vector search.

The loop itself is the retrieval architecture.

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

# 31. Session Modes

Memoria exposes three primary modes.

## 31.1 Work here

Focused work on a chapter or section.

Typical activities:

- draft;
- revise;
- inspect sources;
- resolve local questions;
- check continuity;
- discuss choices;
- apply authorized manuscript-impact suggestions.

---

## 31.2 Research sources

Interrogate the archive.

Typical activities:

- investigate claims;
- build timelines;
- compare accounts;
- locate quotations;
- test interpretations;
- build source packets.

---

## 31.3 Think across book

Reason at book scale.

Typical activities:

- examine themes;
- examine arcs;
- find structural repetition;
- assess chapter ordering;
- identify thematic gaps;
- compare current manuscript against current interpretation;
- inspect manuscript drift caused by changes elsewhere.

This mode begins with compressed interpretation and drills into evidence on demand.

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
    section state.md
    section draft.md

Tier 2 — declared relevance
    themes
    arcs
    people
    events
    relevant claims
    active decisions
    local questions
    unresolved manuscript impacts

Tier 3 — structural neighborhood
    previous section ending
    next section outline
    chapter digest

Tier 4 — on demand
    search results
    full sources
    research memos
    additional digests
```

Each `state.md` contains or accumulates references to the entities relevant to that segment.

The Curator maintains these links, and the author may edit them.

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

---

# 34. Research Workflows

Research workflows are implemented primarily as rigorous skills over common retrieval tools rather than separate infrastructure.

## 34.1 Investigate a claim

Procedure:

1. define the claim;
2. identify relevant people and aliases;
3. define time boundaries;
4. run exact and semantic searches;
5. inspect full parent records;
6. search for disconfirming evidence;
7. separate contemporaneous and retrospective evidence;
8. assess uncertainty;
9. preserve searches performed and sources inspected;
10. write a durable research memo.

Valid conclusions include:

```text
supported
probably supported
mixed
probably false
contradicted
insufficient evidence
unknowable from current archive
```

“Insufficient evidence” is a successful research result.

---

## 34.2 Compare accounts

Explicitly compare:

- contemporaneous vs retrospective sources;
- two participants' accounts;
- early vs later beliefs;
- documentary record vs manuscript framing.

---

## 34.3 Build source packet

Create a pre-writing package for a chapter or section containing:

- relevant chronology;
- source excerpts;
- candidate quotations;
- contradictions;
- people;
- themes;
- arcs;
- claims;
- unanswered questions;
- possible sequencing.

Every included item links directly to its source.

---

## 34.4 Work the question queue

Questions have states such as:

```text
open
researching
partial
resolved
unknowable
deferred
```

Research state persists so an investigation can stop and resume.

---

# 35. Durable Research Memos

A completed research memo should capture more than the final conclusion.

It records:

```text
question
research plan
scope
searches performed
sources inspected
supporting evidence
contradicting evidence
interpretation
confidence
unresolved questions
provenance
```

A later model should not have to recreate important research merely because the original conversation fell outside its context window.

At the same time, every important conclusion in the memo remains linked to underlying material.

---

# 36. Manuscript Rules

The manuscript has exactly one canonical home:

```text
chapters/**/draft.md
```

There is no human manuscript and AI manuscript.

There is only the current canonical text.

Passages may have been:

- written directly by the author;
- drafted by AI at the author's request;
- generated from a research packet;
- heavily rewritten by AI;
- lightly polished by AI;
- written by AI and then substantially edited by the author;
- rewritten because a source, chronology, theme, arc, or claim changed.

These histories remain recoverable through Git and Memoria provenance.

External DOCX, PDF, or other formats are export artifacts rather than synchronized authorities.

---

# 37. AI Manuscript Authorship

AI manuscript authorship is explicitly in scope.

During an authorized operation, the model may:

- draft new prose;
- rewrite existing prose;
- restructure passages;
- move material;
- reconcile multiple drafts;
- incorporate source material;
- revise framing;
- improve continuity;
- adjust voice;
- shorten or expand;
- apply factual corrections;
- implement approved manuscript-impact suggestions.

The AI should have enough authority within the authorized scope to perform the actual work.

Memoria should not force the author to manually copy AI-generated text back into the manuscript.

The key restriction is:

> **The model may not independently decide that canonical prose should change and then apply that change without authorization.**

Analysis may be autonomous.

Recommendations may be autonomous.

Candidate patches may be autonomous.

Canonical manuscript modification is authorized.

---

# 38. Manuscript Change Workflow

The standard workflow is:

```text
Evidence / interpretation / author change
                  ↓
         Dependency analysis
                  ↓
         Manuscript impact scan
                  ↓
       Suggested change or patch
                  ↓
           Author decision
          ↙              ↘
       Reject          Authorize
                          ↓
                    AI modifies
                    canonical text
                          ↓
                    Git commit
                          ↓
                 Provenance record
                          ↓
                Curator coherence pass
```

Rejecting a suggestion is itself useful working state.

Memoria should avoid repeatedly proposing the same rejected change unless materially new evidence or interpretation emerges.

---

# 39. Section State and Resumability

Each section has a `state.md`.

A useful state record contains:

```text
purpose
status
last worked
checkpoint
current approach
important decisions
rejected approaches
themes
arcs
people
events
claims
source packets
open questions
attention flags
unresolved manuscript impacts
next step
```

The defining test is simple:

> Leave a section untouched for several weeks, reopen it, and continue productive work without reconstructing what happened last time.

If Memoria cannot pass that test, the rest of the architecture is premature.

---

# 40. Interfaces

The responsive web interface should be part of the first usable Memoria build rather than a late-stage convenience layer.

This follows directly from the product promise:

> **Bring the whole archive. Ask the real question. Memoria handles the context.**

The user should interact in terms of questions, chapters, themes, arcs, evidence, and manuscript changes—not commands, token budgets, context manifests, or retrieval mechanics.

The early UI should expose Memoria's intelligence without attempting to replace every mature writing tool.

---

## 40.1 One core service layer

Every interface should use the same Memoria service layer.

```text
Desktop browser ─┐
Phone browser   ─┼──► Memoria web/API service ──► Repository
CLI             ─┘             │                  SQLite
                               │                  Git
                               └──► ModelBackend / Curator
```

Business logic should not be duplicated between the CLI, web UI, and Curator.

The web application owns no unique intellectual state. It is an interface to the same canonical repository and service layer.

---

## 40.2 Responsive web first

Memoria should initially target a responsive web application rather than separate native mobile applications.

A phone is particularly well suited to:

- asking book-wide questions;
- continuing a conversation;
- reviewing research;
- opening cited sources;
- inspecting themes and arcs;
- reviewing manuscript impacts;
- previewing candidate rewrites;
- authorizing or rejecting changes;
- capturing a thought;
- and telling Memoria to draft or revise something.

Desktop may present multiple panes simultaneously.

Phone should present one focused surface at a time.

The same backend and canonical repository serve both.

---

## 40.3 Initial web surfaces

The first useful web version should remain deliberately small.

### Home / Ask Memoria

General book-wide conversation. This is the simplest expression of the product promise: ask the question and let Memoria handle context assembly and retrieval.

### Section

Show:

```text
Purpose
Current draft
Checkpoint
Decisions
Open questions
Attention
Relevant themes/arcs
Source packet
Unresolved impacts
Resume
```

### Source viewer

Show the normalized source, exact cited location, temporal metadata, backlinks, and an **Open original** action.

### Theme / Arc

Show the current interpretation, supporting and contradicting claims, provenance, affected manuscript passages, and open threads.

### Research conversation

Allow searches and source reads to appear as the model works without requiring the author to manage those operations manually.

### Review

Show manuscript impacts and candidate changes with actions such as:

```text
View evidence
Explain
Preview diff
Rewrite
Apply
Dismiss
```

These surfaces are enough for an early desktop-and-phone product.

---

## 40.4 What not to build early

The first web UI should not attempt to replace a mature desktop writing application.

Avoid making the initial build depend on:

- a sophisticated rich-text editor;
- offline-first synchronization;
- native iOS or Android applications;
- push notifications;
- collaborative editing;
- a full visual graph explorer;
- or elaborate dashboards.

Viewing manuscript prose and directing AI-assisted changes should work well on mobile. Serious manual long-form editing may continue in Obsidian or another editor.

---

## 40.5 Authentication and remote access

Phone access requires secure authentication and HTTPS.

For a personal deployment, the preferred early model is private-network or tailnet access rather than direct public-internet exposure.

The Memoria host contains:

```text
repository
SQLite index
Git
web/API service
Claude Code authentication
model runtime
```

The phone contains no Anthropic credentials. It is only a client.

This keeps model authentication and the private archive centralized on the Memoria host.

---

## 40.6 Single write coordinator

Once multiple interfaces exist, all automated writes should pass through one write coordinator.

This prevents conflicts between:

- Obsidian;
- the web UI;
- phone actions;
- AI sessions;
- and the Curator.

Writes should be checked against the current Git revision. Stale operations should be rejected or reconciled rather than silently overwriting newer work.

---

## 40.7 Streaming and visible activity

The web service should support streamed model output and structured activity updates.

The UI may show concise status such as:

```text
Searching 2011 email…
Reading SRC-0184…
Checking Bob aliases…
Comparing retrospective accounts…
```

This helps make large-corpus reasoning legible without making the user manage the context window or retrieval loop.

---

## 40.8 CLI remains administrative

The CLI remains useful for operations such as:

```text
memoria ingest
memoria rebuild
memoria validate
memoria sync
memoria trace
```

It does not need to be the primary daily interface.

The primary product experience should be the responsive web interface.

---

# 41. Git as Audit and Authorship Infrastructure

Git serves:

1. history;
2. rollback;
3. attribution;
4. ownership;
5. manuscript-authorization audit.

Curator commits are machine-authored.

Direct human changes are human-authored.

AI manuscript changes are committed with references to their authorizing interaction.

Example:

```text
manuscript: revise ch2 ¶7 for corrected Bob timeline

authorized-by:
  SES-20261103-1041#T008

triggered-by:
  CHG-20261103-1024
  IMP-20261103-004

evidence:
  SRC-0184
  SRC-0391
```

A later author or model can reconstruct both:

- why Memoria wanted the passage changed;
- and why it had authority to change it.

A bad Curator or AI writing pass should be reversible with ordinary Git operations.

---

# 42. Rebuildability

The command:

```bash
memoria rebuild
```

must be capable of recreating all derived state from canonical material.

This includes:

- full-text index;
- embeddings;
- entity enrichment;
- dependency graph;
- backlink index;
- provenance graph;
- source chunks;
- change projections;
- generated digests.

Deleting `.memoria/index.db` must never destroy intellectual work.

---

# 43. Evaluation Suite

A small adversarial test suite begins early and grows from real failures.

The evaluation suite exists primarily to validate Memoria's central promise: that a model can work accurately across a corpus much larger than its immediate context without losing provenance, silently narrowing scope, or substituting remembered summaries for evidence.

## 43.1 Large-corpus reasoning test

Can Memoria answer questions whose evidence is distributed across material that cannot fit into a single model context?

The test should verify that it:

- assembles useful initial context;
- searches beyond that context when required;
- expands important hits to full source records;
- distinguishes searched from unsearched material;
- preserves citations to terminal evidence;
- and avoids claiming corpus-wide certainty when retrieval was incomplete.

## 43.2 Resumption test

Can Memoria resume a section after a long absence?

## 43.3 Date-leakage test

Does later hindsight contaminate questions about earlier beliefs?

## 43.4 Confirmation-bias test

When asked to prove something, does research actively seek contrary evidence?

## 43.5 Alias test

Can retrieval find evidence across multiple names for the same person without making unsafe merges?

## 43.6 Sparse-evidence test

Can the system correctly answer that evidence is insufficient?

## 43.7 Attribution test

Select random `[author]`, `[source]`, and `[inferred]` statements.

Can each be traced to legitimate terminal provenance?

## 43.8 Broken-link test

Do all cited source, session, change, and impact references resolve?

## 43.9 Human-edit test

Can Memoria identify when an important interpretation changed and display the exact diff?

## 43.10 Curator-restraint test

Does exploratory author conversation remain exploratory instead of becoming accepted interpretation?

## 43.11 Distributed-pattern test

Can agentic retrieval identify patterns requiring evidence distributed broadly across the archive?

## 43.12 Manuscript-authorization test

Can Memoria propose a manuscript rewrite autonomously while refusing to apply it until explicit authorization exists?

## 43.13 Scope test

If the author authorizes one paragraph, does Memoria leave unrelated manuscript prose untouched?

Every consequential real-world failure becomes a regression test.

---

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

# 45. Optional Future Retrieval Infrastructure

Memoria initially does **not** require:

- Qdrant;
- GraphRAG;
- Neo4j;
- Open WebUI;
- a graph database;
- a hierarchical summary pyramid;
- persistent specialist agents.

Any may eventually become worthwhile.

The process for adding one is:

```text
Observe real failure
        ↓
Turn failure into benchmark
        ↓
Prototype heavier approach
        ↓
Compare against existing Memoria
        ↓
Adopt only if materially better
```

The existing file model should survive regardless.

Retrieval implementations are replaceable.

The repository is durable.

---

# 46. Optional Future Specialist Agents

Memoria begins with capabilities expressed as skills over shared state.

Possible future roles include:

- Research Editor;
- Continuity Editor;
- Theme Analyst;
- Fact Checker;
- Structural Editor.

A role earns persistent agent state only if experiments show that loading the relevant skill plus explicit Memoria state does not provide sufficient continuity.

Separate agents must not develop private canonical memories disconnected from the repository.

Anything durable they learn belongs in Memoria.

---

# 47. Health and Drift Detection

Memoria should periodically be able to report:

- sections not worked on recently;
- stale checkpoints;
- old unresolved questions;
- themes with substantial new evidence but no recent review;
- arcs whose current interpretation conflicts with recent manuscript changes;
- human/Curator conflicts;
- unsupported interpretation statements;
- broken provenance;
- unprocessed source additions;
- research projects left incomplete;
- manuscript passages affected by changed chronology, themes, arcs, claims, or source status;
- manuscript-impact suggestions awaiting a decision;
- dismissed impacts that may deserve reopening because materially new evidence appeared.

This is a health report, not an approval queue.

Normal Curator work remains autonomous.

---

# 48. Privacy and Provider Independence

Memoria should not depend conceptually on a particular model vendor.

A model needs:

- repository read access;
- controlled write access;
- retrieval tools;
- skills;
- context;
- provenance rules;
- manuscript authorization rules.

The underlying model may change over the lifetime of the book.

The durable intellectual state remains in ordinary files.

The preferred initial deployment uses a local Claude Code installation authenticated to the author's own supported Anthropic subscription. Authentication credentials remain on the Memoria host rather than being distributed to browsers or phones.

If external model APIs are later used, privacy, billing, and source-upload policies are configuration decisions rather than architectural assumptions.

---

# 49. Explicit Non-Goals

Memoria initially does not attempt:

- multi-user collaboration;
- routing many users through a shared consumer LLM subscription;
- native iOS or Android applications in the initial build;
- unprompted modification of canonical manuscript prose;
- Word or Scrivener round-trip synchronization;
- graph infrastructure without demonstrated need;
- a large up-front ontology;
- permanent agent personas with private memories;
- automated interpretation that cannot be traced;
- exact recreation of old model reasoning;
- treating an AI transcript as factual evidence merely because the AI said something.

AI manuscript authorship itself is **not** a non-goal.

It is a core capability.

---

# 50. The Core Invariants

## Invariant 1 — The author does not manage context windows

Memoria must allow the author to work at the scale of the book. The system is responsible for focused context assembly, retrieval beyond the working context, durable project memory, and explicit reporting of what was and was not searched.

## Invariant 2 — Files are truth

All important intellectual state survives without the database.

## Invariant 3 — Evidence is immutable

Interpretation never rewrites documentary history.

## Invariant 4 — Every durable assertion is attributable

No important belief exists without inspectable provenance.

## Invariant 5 — Provenance terminates in original records

A chain of summaries may not become circular authority.

## Invariant 6 — Author statements require author evidence

The model cannot appoint itself interpreter of what the author believes.

## Invariant 7 — Human interpretation edits are supreme

Automation may challenge them but does not silently overwrite them.

## Invariant 8 — Canonical prose changes are authorized

AI authorship is first-class.

Memoria may autonomously read manuscript prose, analyze it, identify impacts, recommend changes, and prepare candidate patches.

AI may draft, revise, and directly modify the canonical manuscript within an explicitly author-authorized scope.

It may not independently apply manuscript changes merely because it believes they would improve the book.

## Invariant 9 — Authorization is scoped and attributable

Every AI manuscript write must have an identifiable authorization covering the change.

## Invariant 10 — Search scope is explicit

The model may not imply that it searched material it did not search.

## Invariant 11 — Uncertainty is valid state

Memoria must be comfortable concluding that something is unknown.

## Invariant 12 — Complexity must earn its place

Infrastructure is added to solve demonstrated problems.

## Invariant 13 — The model runtime is replaceable

Claude Code and an Anthropic subscription are the preferred initial runtime, not canonical architecture. No durable intellectual state may depend on a private model session or provider-specific representation.

## Invariant 14 — Subscription limits may pause work, never corrupt it

If model capacity is temporarily unavailable, Memoria preserves state, defers lower-priority work, and resumes safely later.

## Invariant 15 — Memoria serves the manuscript

After M1, meaningful system development must accompany real book progress.

---

# 51. The Authorship Principle

Memoria's relationship to manuscript authorship can be summarized as:

> **Autonomy in observation.**  
> **Autonomy in reasoning.**  
> **Autonomy in recommendation.**  
> **Authorization at the point of canonical authorship.**

Once authorized, the AI should be allowed to actually perform the work.

The system is intended to be an active writing collaborator, not merely a suggestion engine.

---

# 52. High-Level Usage Flow

The architecture should disappear behind a simple working loop.

Most importantly, the author should never have to begin a task by deciding what the model can fit into context. The user chooses the intellectual task; Memoria determines the working set, retrieves additional evidence as needed, and preserves the result.

At a high level, using Memoria should feel like:

```text
Ingest
  ↓
Explore
  ↓
Build interpretation
  ↓
Research
  ↓
Draft
  ↓
Human correction
  ↓
Interpretation changes
  ↓
Impact detection
  ↓
AI-assisted propagation
  ↓
Refine
  ↓
Repeat
```

---

## 52.1 Initial ingest

The author points Memoria at the archive:

- journals;
- emails;
- notes;
- transcripts;
- documents;
- PDFs;
- message exports;
- other contemporaneous records.

Memoria preserves the originals, normalizes them, assigns stable IDs and anchors, extracts temporal metadata, builds indexes, and proposes aliases where needed.

At this stage, Memoria is deliberately not trying to decide what the book means.

The initial goal is a trustworthy, attributable evidence substrate.

The author also creates minimal project framing:

- `book.md`;
- an initial `outline.md`;
- broad date range;
- purpose;
- audience;
- voice notes;
- known structural ideas.

The outline may be skeletal.

No complete ontology is required before useful work begins.

---

## 52.2 Initial exploration and interpretation

The author begins talking to Memoria in **Think across book** or **Research sources** mode.

Example:

> I think one of the threads here is the tension between independence and needing other people. Look through 2008–2014 and tell me whether the archive actually supports that.

Memoria first assembles the durable book-level context relevant to the question, then the model searches iteratively across the wider archive.

It reads full sources when needed, expands beyond search chunks, compares contemporaneous and retrospective material, seeks counterexamples, and gives a sourced answer. The author does not need to know which records were initially loaded or how many retrieval passes are required; Memoria manages that internally and reports the resulting search scope.

If the author adopts the idea, the conversation turn becomes durable provenance.

Memoria may create or update:

```text
themes/control.md
arcs/...
claims/...
```

with a mixture of `[author]`, `[source]`, `[inferred]`, and `[open]` material.

Every substantive point is clickable.

---

## 52.3 Research a chapter or section

Suppose Chapter 2 covers the acquisition.

Memoria builds a source packet containing:

- chronology;
- key events;
- people;
- candidate quotations;
- contradictions;
- relevant themes;
- relevant arcs;
- important claims;
- unresolved questions.

The author can interrogate the packet before writing.

For example:

> What is the strongest contemporaneous evidence that Bob knew beforehand?

or:

> What would I be overstating if I wrote that he definitely knew on July 14?

The important research becomes durable state rather than disappearing with the chat.

---

## 52.4 First AI-generated draft

Once the source packet and section purpose are satisfactory, the author gives explicit writing authorization.

Example:

> Draft §2.3 from this material. About 1,500 words. Keep the reader inside what I knew at the time; don't use Alice's later account yet.

Memoria loads:

- section purpose;
- surrounding prose;
- relevant themes and arcs;
- decisions;
- source packet;
- voice guidance;
- explicit constraints.

The AI writes directly to the canonical `draft.md`.

The result is committed with provenance linking the draft to:

- the authorizing turn;
- the writing session;
- relevant source packet;
- important evidence and claims.

The prose itself need not be cluttered with visible internal citation syntax during normal reading.

Provenance can be available through links, metadata, or the provenance inspector.

---

## 52.5 Human correction and refinement

The author reads the draft in Obsidian and edits normally.

Perhaps the AI's psychology is wrong.

The author rewrites a passage to emphasize fear of dependence rather than ambition.

Git captures the change.

Memoria recognizes that the author deliberately changed manuscript prose.

It does **not** automatically assume every prose edit represents a book-level interpretation change.

If the change appears semantically important, the Curator may flag:

> This edit appears inconsistent with the current Bob arc. Is this a local wording change, or should the arc itself be reconsidered?

The system should distinguish manuscript refinement from canonical interpretation.

---

## 52.6 Correcting the interpretation layer

The author then decides the broader interpretation really was wrong and directly edits:

```text
arcs/bob-relationship.md
```

or:

```text
themes/control.md
```

Now the intent is explicit.

Memoria preserves the human diff and performs dependency analysis.

It may discover:

```text
Chapter 2 ¶7 — direct contradiction
Chapter 5 ¶12 — likely framing conflict
Chapter 9 ¶4 — possible implication
```

The manuscript remains untouched.

---

## 52.7 AI-assisted propagation

Memoria creates manuscript-impact suggestions and may prepare candidate patches.

The author might say:

> Rewrite the two direct conflicts. Show me diffs for the framing changes. Leave the weak implication alone.

That gives Memoria scoped manuscript authorization.

It directly rewrites the authorized canonical passages, commits them, and records:

```text
author correction
    ↓
manuscript impact
    ↓
supporting evidence
    ↓
author authorization
    ↓
AI rewrite
    ↓
Git commit
```

Unauthorized passages remain unchanged.

---

## 52.8 Ongoing refinement

From there, the book and Memoria evolve together.

Research may weaken a claim.

A new source may alter the chronology.

The author may revise a theme.

Drafting may expose weaknesses in an arc.

Memoria continually reconciles these layers without assuming reconciliation means silently rewriting the book.

The author can ask:

> What parts of the manuscript are out of step with our current understanding?

or:

> What has changed in our interpretation of Bob since I drafted Chapter 2?

or:

> Take a new pass at Chapter 2 now that we've resolved these questions.

The last instruction deliberately authorizes a broader writing scope.

Memoria can then make substantial manuscript revisions rather than forcing paragraph-by-paragraph approval.

---

# 53. Target Experience

After Memoria is mature, the author should be able to open a section not touched in six months.

The screen might show:

```text
SECTION 8.3 — The Acquisition

Purpose
Show the first point at which the narrator realizes that
Bob may have known substantially more than he admitted.

Last worked
October 18, 2026

Checkpoint
Opening works. Middle section currently overstates certainty.
Need to distinguish what was knowable in 2011 from what became
clear retrospectively.

Important decisions
• Do not reveal Alice's later account until §8.5.
• Keep Bob's knowledge ambiguous here.

Relevant arcs
• Bob relationship
• Loss of institutional trust

Relevant themes
• Control
• Loyalty

Research
• Acquisition knowledge timeline
• Bob/Alice account comparison

Open question
Did Bob receive the July 14 document?

Unresolved manuscript impacts
• ¶7 may overstate Bob's foreknowledge after chronology revision.

Next step
Rewrite the final three paragraphs using only contemporaneous
evidence.
```

The author can open this view on a desktop browser or phone and press **Resume**.

Memoria assembles the appropriate state and gives the AI access to the wider archive through retrieval tools. The author does not choose which files fit into context.

During the conversation it says:

> There are three contemporaneous pieces of evidence supporting that reading, but one July 18 email cuts against it.

Each item is clickable.

The author can open the source.

Later the author asks:

> Why are we treating control as an important theme?

Memoria responds with the current case.

The author follows the case into a claim.

From the claim into a journal entry.

From another portion of the theme into a conversation from eight months earlier.

From another into a direct edit where the interpretation changed.

At another point Memoria says:

> Your revision to the Control theme appears to make Chapter 2 ¶14–17 narratively stale. Nothing there is factually false, but the passage still frames the episode around ambition. I have a proposed rewrite if you want to see it.

The author says:

> Rewrite it.

Memoria modifies the canonical manuscript, preserving the authorization and provenance.

At no point does the chain disappear into anonymous model memory.

That is the intended end state of Memoria:

> **A system that lets the author use AI across a book-sized body of evidence as naturally as if the whole project fit in the model's mind—without sacrificing provenance, search-scope honesty, evidentiary discipline, or control of canonical authorship.**

Resumability is an important consequence of that architecture: because the book's understanding is durable rather than trapped inside model context, the author can leave and return without rebuilding it.
