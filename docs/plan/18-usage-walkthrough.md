<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 52, 53 of the original memoria-plan.md -->

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

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

The desktop design renders this walkthrough rather than inventing a scenario: the
acquisition, Bob's foreknowledge, `CLM-0041`, Chapter 2 ¶7, `SRC-0184 ¶17`, and §21's
"12 manuscript impacts found after chronology revision". Several lines are on screen
near-verbatim — *"Opening works. Middle section overstates certainty"*, *"¶7 may
overstate Bob's foreknowledge after the chronology revision"*, *"Acquisition
knowledge timeline"*.

The index calls this part an acceptance description containing no independent
requirements. It is now also the source material for an interface, which raises the
cost of its example being illustrative rather than specified.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
