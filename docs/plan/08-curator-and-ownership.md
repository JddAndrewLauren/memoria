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
| Human edits interpretation files | Propagation + manuscript-impact pass |
| Human edits manuscript | Interpretation/continuity impact scan |
| Research memo completes | Fold supported findings into interpretation |
| New evidence ingested | Index, alias scan, question/theme/arc impact scan |

Passes are debounced and materiality-gated.

A spelling correction should not trigger a cascade through the book.

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

## 13.4 Interpretation changes

The Curator is deliberately conservative.

If the author muses about an interpretation, it belongs under an open thread.

If the author clearly adopts a position, it may enter current interpretation as `[author]`, citing the precise transcript turn.

If the Curator independently identifies a pattern from evidence, it may enter as `[inferred]`, with supporting provenance.

The Curator may never convert exploratory discussion into an author belief merely because doing so makes the knowledge base neater.

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

Materially new evidence may justify resurfacing the possibility, but it should appear explicitly as something previously rejected or removed.

This prevents autonomous curation from repeatedly arguing with the author.

---
