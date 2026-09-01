<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 49, 50, 51 of the original memoria-plan.md -->
<!-- Invariant 15 revised 2026-08-31: its milestone reference updated for the -->
<!-- rewritten part 16 ("M1" meant the original writing-loop milestone, now M5). -->

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

**Amended 2026-08-31.** Memoria no longer analyzes manuscript prose autonomously. An
audit runs only when the author asks for one — on a section, a chapter, or a
highlighted passage. Within a requested audit, identifying findings, recommending
changes and preparing candidate patches need no further authorization.

What remains autonomous is everything that requires no model: knowing which paragraphs
are **not current** (a hash comparison over cached judgements, part 06 §8.12), §47's
health report, and §23's validation. Memoria therefore always knows what has gone
stale and never forms an opinion about prose unasked.

AI may draft, revise, and directly modify the canonical manuscript — prose or a brief —
within an explicitly author-authorized scope. A brief is authorized only by a
deliberate act on that brief, never from a finding card and never in a batch.

It may not independently apply manuscript changes merely because it believes they would improve the book.

## Invariant 9 — Authorization is scoped and attributable

Every AI manuscript write must have an identifiable authorization covering the change.
This covers writes to a brief as well as to `draft.md`.

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

Once the writing loop exists (part 16's M5), meaningful system development must
accompany real book progress.

---

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
