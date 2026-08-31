<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 16, 17, 18, 22 of the original memoria-plan.md -->

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

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

The design's Review shows four verdict labels. Two sit outside §18's ten categories:

- **`SUPPORTED`** — *"The draft's account matches contemporaneous records"*, dimmed,
  with no action offered. All ten §18 categories are defects; a confirmation is not
  one of them, and the design surfaces it anyway.
- **`HINDSIGHT LEAKAGE`** — *"Presents knowledge from Alice's 2019 account as available
  to the narrator in 2011."* §47 tests for exactly this; §18 does not name it.

`CONTRADICTED` and `OVERSTATED` map onto *factual contradiction* and *unsupported
assertion*.

Severity is also worded as a diagnosis rather than a confidence level: *"4 high —
factual conflicts, 5 medium — stale framing, 3 low."* §18 records confidence per
suggestion; the design groups by kind of problem as well.

Impact records reach the interface by id (`IMP-20261103-004` on the finding card),
so the §16–§18 pointers are load-bearing for the UI too — the same anchoring
dependency noted in part 04.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
