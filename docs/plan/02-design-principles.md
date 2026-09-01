<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 1 of the original memoria-plan.md -->

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

There is one curated layer of **subjects** and their entries:

- People;
- Timeline;
- Events;
- Themes;
- Arcs;
- and whatever else the author adds.

Claims are not a subject. They are the propositional layer that accretes from the
author's settlements, cutting across every subject. Part 06 is authoritative.

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

## 1.10a Enumerations are withdrawn on contact with use

A recurring failure in this plan has been specifying a **fixed list of kinds** before
anything was built. Four have now been withdrawn:

| Enumeration | Replaced by |
|---|---|
| §18's ten impact categories | a finding is a disagreement set; its shape is read from the set |
| §19.3's four review verdicts | the same; the design's labels are illustrative only |
| §17's seven impact questions | each subject declares the questions it asks (part 06 §8.1) |
| §25's per-type read tools | one `read(ref)`; the type is read off the §4 ID scheme |

The pattern is the same each time. A category list is a schema imposed before the
material demanded one, it is always slightly wrong, and it hardens into data structures
that outlive the reasoning behind it. The replacements share a shape too: the thing
that used to be enumerated centrally is **derived from a set**, or **stated locally by
whoever owns it**.

Treat any new fixed list of kinds in this plan as suspect until something real needs
it. This is §1.11 applied to vocabulary rather than to files.

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
