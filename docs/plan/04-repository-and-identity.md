<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 2, 3, 4, 42 of the original memoria-plan.md -->

# 2. Repository Structure

A representative repository:

```text
memoria/
│
├── book.md
├── outline.md
├── chronology.md
│
├── chapters/
│   └── 08/
│       ├── chapter.md
│       └── sections/
│           └── 03/
│               ├── draft.md
│               └── state.md
│
├── themes/
│   └── control.md
│
├── arcs/
│   └── bob-relationship.md
│
├── people/
│   ├── _aliases.yaml
│   └── bob.md
│
├── events/
│   └── acquisition.md
│
├── claims/
│   └── CLM-0041.md
│
├── decisions.md
├── questions.md
│
├── research/
│   ├── memos/
│   └── packets/
│
├── impacts/
│   └── IMP-20261103-004.md
│
├── sources/
│   ├── raw/
│   └── normalized/
│
├── sessions/
│   └── 2026/
│       └── 09/
│           └── SES-20260912-1432/
│               ├── transcript.md
│               ├── metadata.yaml
│               ├── context-manifest.json
│               └── events.jsonl
│
├── changes/
│   └── CHG-20261014-0917.md
│
├── digests/
│
└── .memoria/
    ├── index.db
    ├── config.yaml
    ├── manifests/
    └── cache/
```

The repository should remain understandable without Memoria-specific software.

---

---

# 3. State Classes and Ownership

Every durable artifact belongs to an explicit class.

| Class | Examples | Authority |
|---|---|---|
| **Evidence** | `sources/**` | Immutable documentary record |
| **Interaction record** | `sessions/**` | Immutable record of conversations |
| **Manuscript** | `chapters/**/draft.md` | Canonical book prose; human- or AI-authored, but AI writes require author authorization |
| **Interpretation** | themes, arcs, people, events, claims, chronology | Shared, with human supremacy |
| **Working state** | `state.md`, decisions, questions, research, impacts | Primarily machine-maintained |
| **Change record** | Git history + `changes/**` | Record of direct human, AI, and Curator edits |
| **Derived** | digests, indexes, dependency data | Machine-only, rebuildable |

These distinctions matter because different classes have different epistemic meanings.

A session transcript proves that someone said something.

A source proves that a document contains something.

A Git change proves that material changed.

None of these alone proves that an interpretation is correct.

---

---

# 4. Stable Identity and Links

Everything that may need to be cited receives a durable identity.

Examples:

```text
SRC-000184                normalized source record
SES-20260912-1432         AI session
SES-20260912-1432#T017    exact transcript turn
CHG-20261014-0917         direct change
IMP-20261103-004          manuscript-impact record
CLM-0041                  important claim
RES-20261018-003          research memo
DEC-0088                  author decision
```

Themes, arcs, people, events, chapters, and sections also carry stable IDs in frontmatter so file renames do not destroy identity.

Ordinary Markdown links remain the primary human-facing linking mechanism.

For example:

```markdown
[SRC-000184 ¶17](../../sources/normalized/SRC-000184.md#src-000184-p17)
```

or:

```markdown
[our September 12 conversation, turn 17]
(../../sessions/2026/09/SES-20260912-1432/transcript.md#t017)
```

Memoria should not require a proprietary URI scheme merely to understand its own citations.

---

---

# 42. Rebuildability

The command:

```bash
memoria rebuild
```

must be capable of recreating all derived state from canonical material.

This includes:

- full-text index;
- embeddings;
- entity enrichment;
- dependency graph;
- backlink index;
- provenance graph;
- source chunks;
- change projections;
- generated digests.

Deleting `.memoria/index.db` must never destroy intellectual work.

---

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

Every locator the design puts on screen — `Ch 2 ¶7`, `SRC-0184 ¶17`,
`Chapter 2 ¶14–17` — assumes the §4 anchoring question is settled. Past mock data,
the interface cannot be built before that decision, which makes it a UI blocker as
well as a Curator one.

Three smaller collisions:

- The design writes `SRC-0184` where §4's example is `SRC-000184`. Every other id on
  screen — `IMP-20261103-004`, `RES-20261018-003`, `DEC-0088`,
  `SES-20260912-1432 · T017` — is §4's own, unchanged.
- Pre-Memoria manuscript prose is badged `LEGACY DRAFT`. §3's state classes have no
  such state.
- The sidebar edits manuscript structure: add chapter, add section, drag to reorder.
  §2 gives `outline.md` a place in the repository; no operation changes it.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
