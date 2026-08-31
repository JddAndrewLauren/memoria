<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 31, 34, 35, 39 of the original memoria-plan.md -->

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

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

§39's resumption test is the design's most literal borrowing: **Resume →**, the
`CHECKPOINT` card with its *"Next — rewrite the final three paragraphs using only
contemporaneous evidence"*, and the line *"Last worked October 18, 2026 · six weeks
ago."* §34's research memos land as `✓ Saved as research memo RES-20261018-003 ·
linked to CLM-0041`.

§31's three modes are visible as conversation scope labels — "book-wide",
"Chapter 6", "research", "Theme · Control", "§ 8.3".

Two additions:

- **A browsable conversation history.** The plan records sessions (§10, part 07) but
  never offers them back as a list to return to. The design gives them a 264px rail
  with `+ New`.
- **Entry points from an object into a conversation about it** — `💬 Discuss this` on a
  theme, *"see the exact turn"*, *"when did this change?"* `trace()` and `backlinks()`
  exist as tools; these affordances do not.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
