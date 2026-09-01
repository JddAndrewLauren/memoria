<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 16, 17, 18, 22 of the original memoria-plan.md -->
<!-- Rewritten 2026-08-31: the manuscript half of §16-§17 collapses into part 06 §8.12. -->

# 16. Dependency and Propagation

Dependencies among **non-manuscript** material are explicit and indexed: ordinary
Markdown links, stable IDs, claim relationships, source packets and provenance
relationships, indexed by SQLite into a rebuildable graph. Changing
`subjects/themes/control.md` may reach `subjects/arcs/bob-relationship.md`,
`claims/CLM-0041.md` and `digests/chapter-08.md`, and derived material may be
propagated automatically according to ownership rules.

**The manuscript is not reached this way, and needs no graph.** A theme's dependency
on a passage is expressed by the cache key of the judgement that relates them — part
06 §8.12 — so changing the Control entry does not require the graph to find affected
prose. It invalidates every cached Control judgement, and the invalidated set *is* the
affected material.

The plan previously listed `chapters/02/draft.md#p7` among a change's calculated
dependents. It no longer does: nothing durable points at a passage (§4.1).

---

---

# 17. Manuscript Impact Analysis

**Impact analysis is not a separate mechanism.** It is the audit (part 06 §8.5),
triggered from the other end: the audit fires when the prose changes, impact analysis
fires when an entry or a subject prompt changes, and both recompute the same judgement
from the same key.

**The questions live on the subjects.** §17 previously carried a fixed list of seven
questions asked of every affected passage. That list is **withdrawn**. Each subject
declares the questions it asks of manuscript prose in its own prompt (part 06 §8.1),
and a subject the author adds is not finished until it does. The seventh question —
*"does it reveal information earlier than the narrative plan permits?"* — is **removed
entirely** rather than rehomed; the audit's questions now map onto subjects with no
orphan.

**Nothing runs unasked.** Invalidation is automatic and free; evaluation happens when
the author presses a button on a section, a chapter or a highlighted passage. A change
to an entry therefore produces a count, not a queue:

```text
142 paragraphs not current · 12 stale since you revised Control · Audit section
```

When an audit does run, a plausible impact produces a **finding**:

```text
Disagreement set:
    chapters/02 ¶7
    SUB-arcs/bob-relationship
    SRC-0184 ¶17

Statement:
    Paragraph treats Bob's July 15 behavior as evidence
    of foreknowledge. The revised timeline now places
    his probable knowledge on July 18.

Confidence:
    high

Raised by:
    SUB-timeline
```

A finding **carries no category**. Everything a surface needs derives from the
disagreement set: which actions are available, which subject raised it, and — since
the set is the finding's identity — whether it has already been settled. Ordering is
by confidence, per §21's tiers. Part 06 §8.10 is authoritative.

Findings are **derived**. They are recomputed rather than accumulated, so a stale
finding cannot outlive the disagreement that produced it, and no `IMP-` records are
written. What persists is the author's **settlement**, not the finding.

Memoria may prepare a proposed rewrite. It may not apply that rewrite to `draft.md`
without authorization.

---

---

# 18. Findings and Their Resolutions

**The category list this section originally carried is withdrawn.** Enumerating kinds
of problem was superseded 2026-08-31: a finding is a disagreement set plus prose, and
its shape is read from the set rather than classified. The old list is preserved in
`_original-memoria-plan.md` §18.

A finding is:

- its disagreement set — the members that disagree;
- prose stating how they disagree;
- confidence;
- which subject raised it;
- an optional candidate patch.

The disagreement set determines what can be done about it:

| Set | Available resolutions |
|---|---|
| passage + source | rewrite the passage; exclude the source |
| passage + entry + source | settle in any of three directions |
| passage + entry | rewrite the passage; update the entry |
| passage + decision | rewrite the passage; revise the decision |
| passage + brief | rewrite the passage; **open a conversation about the brief** |

Every one of these is a **settlement** (part 06 §8.7) except a plain rewrite, and
every settlement records what was chosen, against what, and when.

The last row is deliberately not symmetrical with the others. Rewriting a passage is
bounded and reviewable in a diff; rewriting a brief changes what every future audit
checks and what every future assembly loads. A brief is never edited from a finding
card, and never from a batch action — see §2.1.

There is no stored disposition. A finding is not a record awaiting a decision; it
exists while its disagreement exists, and declining to act simply means it will be
raised again the next time you audit that passage. A decline worth remembering is
craft direction, and belongs in the brief.

---

---

# 22. Editorial Suggestions Beyond Contradictions

Memoria's manuscript reasoning is not limited to factual errors, and the mechanism is
now explicit: a subject's audit questions are whatever that subject can usefully ask.
For Themes, the useful question is about framing rather than fact.

Suppose `subjects/themes/control.md` changes from:

> Control is primarily about professional authority.

to:

> Control is primarily about fear of dependence; professional authority is one
> manifestation of it.

Every cached Control judgement in the book is invalidated. When the author next audits
a chapter, passages containing no factual error at all may still report:

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

Memoria may prepare a candidate revision. The author determines whether the canonical
manuscript changes.

This is what lets Memoria function as a persistent developmental editor as well as a
research and fact-checking system — and it is the case that forced audit questions onto
subjects in the first place, since no matching rule produces it.
