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
