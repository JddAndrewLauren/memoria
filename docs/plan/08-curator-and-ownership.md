<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 12, 13, 14, 15 of the original memoria-plan.md -->

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
| Human edits an entry | Propagate to derived non-manuscript material; invalidate that entry's cached judgements — **no manuscript pass runs** |
| **New or edited manuscript prose exists** | Mark it **not current**. The audit itself runs only when the author asks |
| Research memo completes | Append supported findings to entry bodies as badged `[source]`/`[inferred]` statements; testimony is never machine-written (part 06 §8.2) |
| New evidence ingested | Index, match against every subject, refresh candidates and gathered sets |
| **A subject is added or its prompt changes** | **Re-match that subject across the corpus; refresh its candidates** |

Passes are debounced and materiality-gated.

A spelling correction should not trigger a cascade through the book.

Three rules govern the audit, and they exist to make its coverage inspectable:

- **It runs only on demand** — a button on a section, a chapter, or a highlighted
  passage. Invariant 8 is amended accordingly. What runs unasked is only what needs no
  model: the staleness map, §47's health report, and §23's validation.
- **It evaluates only changed inputs.** A judgement whose paragraph, entry and subject
  prompt are unchanged is read from cache, never re-argued. This replaces the older
  "only new text" rule, which was a proxy for cost. See part 06 §8.12.
- **It evaluates only on subjects that exist**, asking the questions those subjects
  declare, bounded by the entries the section's brief resolves to. A risk with no
  subject is not checked, and the pass says so. See part 06 §8.1 and §8.5.

---

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

## 13.4 Entry changes

The Curator is deliberately conservative.

If the author muses about an interpretation, it belongs under `[open]`.

If the author clearly adopts a position, the Curator may record it in the entry body
as `[author]`, citing the precise transcript turn. §13.1's bar decides the badge —
`[author]` against `[open]` — not whether supreme text gets written: the Curator never
writes unbadged testimony, and it never revises an existing `[author]` statement
without a new citing turn (part 06 §8.2).

If the Curator independently identifies a pattern from evidence, it may enter as `[inferred]`, with supporting provenance.

The Curator may never convert exploratory discussion into an author belief merely because doing so makes the knowledge base neater.

The same restraint applies with more force to manuscript prose. **The Curator never
harvests a passage into an entry.** It may link freely, and it may surface a
disagreement as a finding; changing what an entry says requires the author's
settlement. Part 06 §8.8 gives the reasoning: narrative prose is not assertion, and
AI-drafted prose carries an authorization to write, not to believe.

---

---

# 14. Human-Edit Supremacy

<!-- Rewritten 2026-08-31: ownership by badge. The original git-blame span mechanism -->
<!-- is in _original-memoria-plan.md §14. Open problem 1.1 is closed on this ground. -->

**Ownership is carried by the badge, not inferred from history.** Part 06 §8.2's write
matrix says who may write and who may revise each statement in an entry body; nothing
reconstructs authorship from git blame at span granularity, so there is no attribution
for a prose reflow to destroy. Git remains the audit trail (§41); it is no longer the
ownership oracle.

## 14.1 What the Curator may rewrite

Its own statements — `[source]`, `[inferred]` and `[open]` — freely, provided
provenance remains valid. An `[author]` statement is revised only on a new citing
transcript turn. Unbadged testimony, never.

## 14.2 Human-touched statements, and the Memoria note

The author's primary moves against a badged statement are conventions, not edits in
place: disagree by writing testimony above it or by settling the conflict; claim it by
stripping the badge.

The backstop for in-place edits is a **human-touched flag** in the index. At each
Curator pass, statements changed by non-Curator commits since the last pass are
flagged. The flag is set once, is monotonic, and is never recomputed — reflow cannot
unset it, so the ratchet points toward the author. The Curator does not rewrite a
flagged statement; if new evidence conflicts with one, it appends a **Memoria note**:

```markdown
> **Memoria note — 2026-10-18**
>
> Later research cuts against the interpretation above.
> See [RES-20261018-003](...) and [SRC-02914](...).
> The author text has been left unchanged.
```

A Memoria note is author-facing only: it never loads into write-side assembly and the
audit does not evaluate against it (part 06 §8.2).

The conflict is also added to the curation-conflict queue.

These conflicts are not administrative noise.

They are often where the most interesting intellectual work lies.

One further guard: **the Curator never writes into a file with uncommitted human
modifications.** A dirty tree means the author is mid-thought; the pass waits.

---

---

# 15. Human Deletions Are Boundaries

If the author deletes a Curator-created interpretation, the Curator should not recreate it from the same evidence during the next pass.

The deletion itself is an author action.

The system remembers it.

Stripping a badge is the inverse act: the author claims the statement rather than
removing it (part 06 §8.6).

This is the same mechanism as the subject system's curated overlay. An **exclusion**
from a gathered set, a **dismissed finding** and a **settlement** are all boundaries
of this kind, and a finding's disagreement set is what makes the boundary
identifiable without minting an ID. See part 06 §§8.3, 8.7, 8.10.

Materially new evidence may justify resurfacing the possibility, but it should appear explicitly as something previously rejected or removed.

This prevents autonomous curation from repeatedly arguing with the author.

---

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

§14.2's Memoria note is on screen almost verbatim — down to `RES-20261018-003` — as
an amber card closing the Theme page: *"Later research cuts against part of the
reading above… **Your text has been left unchanged** — worth a conversation?"* The
deferred-ownership safe default is what the design draws, not the §14 git-blame
mechanism. (Since resolved: ownership is by badge, the blame mechanism is retired,
and the note card the design draws **is** §14.2's specified mechanism.)

Nothing in §§12–15 surfaces Curator run state. The design does: a green dot and
**"Curator idle · last pass 09:41"** in the sidebar footer, plus, after an author
edit, *"the Curator may ask whether this changes the Bob arc."*

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
