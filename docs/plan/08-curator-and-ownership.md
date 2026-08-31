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
| Human edits an entry | Propagation + manuscript-impact pass |
| **New manuscript prose exists** (hand-written or AI-written) | **Audit pass** — evaluate it against the entries, bounded by the subjects that exist |
| Research memo completes | Fold supported findings into entries |
| New evidence ingested | Index, match against every subject, refresh candidates and gathered sets |
| **A subject is added or its prompt changes** | **Re-match that subject across the corpus; refresh its candidates** |

Passes are debounced and materiality-gated.

A spelling correction should not trigger a cascade through the book.

Two scoping rules govern the audit, and both exist to make its coverage inspectable:

- **It evaluates only new text.** Prose that has already been audited and settled is
  not re-argued. §15 supplies the memory.
- **It evaluates only on subjects that exist.** A risk with no subject is not
  checked, and the pass says so. See part 06 §8.5.

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

If the author muses about an interpretation, it belongs under an open thread.

If the author clearly adopts a position, it may enter an entry as `[author]`, citing the precise transcript turn.

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

---

# 15. Human Deletions Are Boundaries

If the author deletes a Curator-created interpretation, the Curator should not recreate it from the same evidence during the next pass.

The deletion itself is an author action.

The system remembers it.

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
mechanism.

Nothing in §§12–15 surfaces Curator run state. The design does: a green dot and
**"Curator idle · last pass 09:41"** in the sidebar footer, plus, after an author
edit, *"the Curator may ask whether this changes the Bob arc."*

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
