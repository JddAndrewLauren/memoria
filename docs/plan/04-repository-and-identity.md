<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 2, 3, 4, 42 of the original memoria-plan.md -->

# 2. Repository Structure

A representative repository:

```text
memoria/
│
├── book.md                           the book's brief
│
├── chapters/
│   └── 08/
│       ├── chapter.md                the chapter's brief
│       └── sections/
│           └── 03/
│               ├── draft.md          the prose
│               └── section.md        the section's brief
│
├── subjects/
│   ├── people/
│   │   ├── _subject.md               match definition + matching hazards
│   │   └── bob.md                    author text, match terms, settlements
│   ├── timeline/
│   │   ├── _subject.md
│   │   └── chronology.md
│   ├── events/
│   │   ├── _subject.md
│   │   └── acquisition.md
│   ├── themes/
│   │   ├── _subject.md
│   │   └── control.md
│   └── arcs/
│       ├── _subject.md
│       └── bob-relationship.md
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

## 2.1 Briefs

Every level of the manuscript carries exactly one editable prose field: **its brief**.
`book.md`, `chapter.md` and `section.md` are the same artifact at three scales, and
they are the manuscript layer's entire durable footprint besides the prose itself.

A brief says what this part of the book is, what it covers and what it is for. It
holds, as prose rather than as fields:

- the **declared scope** — "June 1839 to October 1841, and my interactions with Bob
  about the conflict in the capital" (§32);
- **craft direction** — "Bob should read as unreliable early on", which part 06 §8.6
  excludes from entries because it is not a claim about the world;
- whatever else the author needs the next session to know before it starts.

**There are no separate fields.** Purpose, checkpoint, current approach, next step
and rejected approaches are not stored: §39's list is withdrawn, and what survives of
it is regenerable from the session records and git.

A brief has three write paths, all of them landing in the same field:

| Path | Authorization |
|---|---|
| The author writes or edits it | direct; supreme |
| An AI writes it from a conversation the author answered | §19.3 authorization, one level below prose |
| An AI drafts it by summarizing prose that already exists | produces an **unconfirmed** brief |

The third is how a pre-Memoria manuscript enters the system. An unconfirmed brief is
structurally partial — summarizing recovers coverage but never intent — and it is
**circular**, having been derived from the prose it would otherwise constrain, so
assembly uses it but brief drift is not evaluated against it. Editing or confirming it
makes it the author's. This is what the desktop design's `LEGACY DRAFT` badge is
marking: a state of the brief, not of the prose, which is why §3 needs no new class
for it.

Nothing but a deliberate act on the brief may write a brief. In particular, a finding
may not be resolved by editing the brief from a review card — rewriting a passage is
bounded and reviewable in a diff, while rewriting a brief silently changes what every
future audit checks and what every future assembly loads.

**The outline is not an artifact.** The ordered tree of chapters and sections, with
their briefs, *is* the outline; a planned section is one whose brief is written and
whose draft is empty. Reordering renumbers directories, and the stable IDs of §4 keep
references intact.

---

---

# 3. State Classes and Ownership

Every durable artifact belongs to an explicit class.

| Class | Examples | Authority |
|---|---|---|
| **Evidence** | `sources/**` | Immutable documentary record |
| **Interaction record** | `sessions/**` | Immutable record of conversations |
| **Manuscript** | `chapters/**/draft.md`, and the briefs `book.md` / `chapter.md` / `section.md` | Canonical book prose and intent; human- or AI-authored, but AI writes require author authorization |
| **Subjects** | `subjects/**` entries — body (testimony + badged statements), match terms, settlements | Ownership by badge: testimony and `[author]` statements are the author's and supreme; `[source]`/`[inferred]`/`[open]` are Curator-maintained. See part 06 §8.2 |
| **Claims** | `claims/**` | Propositions accreted from settlements, or asserted outright |
| **Working state** | decisions, questions, research | Primarily machine-maintained |
| **Change record** | Git history + `changes/**` | Record of direct human, AI, and Curator edits |
| **Derived** | digests, indexes, **gathered sets**, **candidates**, **appearances**, memoized audit judgements, findings | Machine-only, rebuildable |

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
CLM-0041                  important claim
RES-20261018-003          research memo
DEC-0088                  author decision
```

Subjects, entries, claims, chapters, and sections also carry stable IDs in frontmatter so file renames do not destroy identity.

A **subject** and an **entry** are addressable directly:

```text
SUB-people                subject
SUB-people/bob            entry
SUB-themes/control        entry
```

A **gathered set** is not addressable. It is derived, it asserts nothing, and it is
regenerated by `memoria rebuild` (§42). A **pin**, an **exclusion** and a
**settlement** are attributable author acts and survive the rebuild.

## 4.1 Manuscript passages have no durable identity

**Nothing canonical points at a paragraph of manuscript prose.** There is no anchoring
mechanism, because there is nothing left that needs one.

The problem was never about evidence: `SRC-000184 ¶17` is stable by construction,
because sources are immutable (Invariant 3). Only mutable prose drifts. Each of the
things that used to require a durable pointer into `draft.md` now lives somewhere
better:

| Was anchored to a passage | Now |
|---|---|
| Findings, impact records | recomputed from their disagreement set; nothing accumulates |
| Entry-to-passage edges | **appearances** (part 06 §8.11), held in the index and rebuildable |
| Settlements | stored on the entry; the passage where the conflict surfaced is provenance of the act, recorded as the session it happened in |
| Write-time provenance | `git blame` to a commit, the commit to a session, the session to its context manifest (§33) — composed by `trace()` (§26) |
| Dismissal memory | craft direction in the section's brief, resolved as prose at audit time |

This closes the deferral recorded in `poc-plan.md` §4. That deferral ruled out "store
no pointers, recompute everything" **on principle**, because §38's dismissal memory
was thought to need stable passage identity. It does not: a dismissal that is worth
remembering is craft direction, and craft direction belongs in the brief.

The index is free to key its own tables positionally or by content hash against the
git revision it was built at, because §42 guarantees that deleting it destroys nothing.
A cache key is not an identity.

**The cost, accepted knowingly.** A finding you decline that cannot be expressed as
craft direction has nowhere to go and will be raised again the next time you audit
that passage. Recurrence is treated as a signal that the brief or the entry is missing
something, rather than as noise to be suppressed.

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
- generated digests;
- **subject candidates**;
- **gathered sets**;
- **appearances**;
- **memoized audit judgements, and the staleness map derived from their keys**;
- **findings**.

The curated overlay is **not** derived and is never regenerated: author text, match
terms, pins, exclusions and settlements survive the rebuild because they are
attributable author acts, not machine output.

Deleting `.memoria/index.db` must never destroy intellectual work.

---
