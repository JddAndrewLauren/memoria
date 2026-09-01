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
- apply authorized findings.

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

# 39. Resumability

**There is no section state record, and no checkpoint.** §39 previously specified a
`state.md` holding seventeen tracked fields — purpose, status, last worked, checkpoint,
current approach, important decisions, rejected approaches, themes, arcs, people,
events, claims, source packets, open questions, attention flags, unresolved manuscript
impacts, next step. **That list is withdrawn in full.**

Eleven of those items were views of state that lives elsewhere and are now composed at
read time: themes, arcs, people, events and claims resolve from the brief through the
subjects; decisions and questions filter from `decisions.md` and `questions.md`;
attention flags are findings from the last audit; unresolved impacts do not exist at
all, since nothing accumulates; status and last-worked are git facts. Purpose and craft
direction moved into the **brief** (§2.1). The checkpoint, the current approach, the
next step and the rejected approaches were **removed**.

What replaces them, for resumption, is:

- the **brief** — what this section is and is for;
- the **draft** — where you actually got to;
- the **audit**, on request — what is wrong with it right now.

The checkpoint was a summary of three things that are all still in front of you.
Removing it also removes the last routine machine-write path into author-supreme text:
nothing rewrites a brief at the end of a session.

The defining test is unchanged:

> Leave a section untouched for several weeks, reopen it, and continue productive work
> without reconstructing what happened last time.

If Memoria cannot pass that test, the rest of the architecture is premature. The test
is now **harder and more honest**, because it must be passed by a brief, a draft and a
live audit rather than by a stored recap. §43.2 keeps the test and changes its subject.

One consequence, recorded rather than solved: an archive supplies evidence and audit
targets but nothing to *resume* — no brief, no declared scope, no passage written from
something. **The manuscript layer has no test corpus**, and this is the claim that
most needs one. The authorship track's short piece is the only place it can be
exercised, and it should be shaped deliberately to do so.
