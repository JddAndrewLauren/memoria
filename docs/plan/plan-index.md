# Memoria Build Plan — Index

The build plan is split into 18 parts, each a unit that can be considered,
revised or grilled on its own. Every one of the original 53 sections appears
in exactly one part. **Section bodies were verbatim as of 2026-08-31**; sections
revised since then are marked in the part's own header comment. Part 19 is the
exception: it records the desktop UI as designed, and has no counterpart in the
original plan.

**Revised since:** §8 (rewritten as the subject system), §16-§18 and §39 (rewritten
for the manuscript layer), §14 (rewritten as ownership by badge), §18's category list
and §17's question list (both withdrawn),
§1.5, §1.10a (new), §2, §2.1 (new), §3, §4, §4.1 (new), §7, §8.1, §8.2, §8.3, §8.4, §8.5, §8.6, §8.11,
§8.12 (new), §9.5, §12, §12.1, §13, §13.4, §15, §19, §20, §21, §23, §24.2, §25, §32, §33, §36-§38, §42,
§43.2, §43.14 (new), §44 (rewritten as the PoC build order), §47, §52.2, and Invariants 8, 9 and 15.

Five parts — 06, 08, 11, 14, 18 — end in an appended
`## Editorial note — the desktop design`, recording where that design confirms,
extends or collides with the section above it. The notes sit below the section text
and never alter it. The notes on 04, 09, 10 and 12 were **resolved into the section
text** on 2026-08-31 rather than left appended.

- **These parts are canonical.** `_original-memoria-plan.md` is an archived copy
  of the single-file plan as of 2026-08-31, kept for reference only. Do not edit it.
- **Decisions from the 2026-08-31 grilling sessions** live in
  [`../poc-plan.md`](../poc-plan.md). Where a part has been narrowed or has an
  open question, the status column says so and the reasoning is there, not here.
- **Everything still unsettled** is collected in
  [`../open-problems.md`](../open-problems.md) — open decisions, deferrals with their
  safe defaults, documents needing rewrite, and the accepted costs worth watching.

---

## Status legend

| | Meaning |
|---|---|
| **stable** | Reviewed, no changes pending |
| **active** | Load-bearing for current work; needs attention now |
| **open** | Contains a decision deliberately deferred, with a safe default recorded |
| **reduced** | Narrowed for the PoC; parts deliberately out of scope |
| **superseded** | Needs rewriting before it can be followed |

---

## The parts

### Foundations — what Memoria is and what it promises

| # | Part | Original §§ | Status |
|---|---|---|---|
| 01 | [Purpose and Product Thesis](01-purpose-and-thesis.md) | Preamble, 0, 0.1 | stable |
| 02 | [Core Design Principles](02-design-principles.md) | 1.1–1.12 | stable |
| 03 | [Invariants, Non-Goals, Authorship Principle](03-invariants-and-non-goals.md) | 49, 50, 51 | stable |

**01** states the promise: work at book scale without managing context windows.
Worth re-reading against the fact that the PoC corpus fits in a 1M window, so the
promise is not falsifiable there.
**02** is the governing document — §1.11 (structure must earn its existence) and
§1.12 (the system exists to produce a book) are the two most frequently invoked.
**03** is the testable contract. Read it before changing anything else.

### The substrate — files, evidence, meaning

| # | Part | Original §§ | Status |
|---|---|---|---|
| 04 | [Repository, State Classes, Identity, Rebuildability](04-repository-and-identity.md) | 2, 3, 4, 42 | **active** |
| 05 | [Source Ingestion, Temporal Discipline, Aliases](05-evidence-and-ingestion.md) | 5, 6, 7 | **active** |
| 06 | [The Subject System and Attribution](06-subjects-and-attribution.md) | 8, 9 | **active** |

**04 carries the manuscript layer.** New **§2.1** defines the **brief** — the one
editable prose field each of `book.md`, `chapter.md` and `section.md` holds, covering
declared scope and craft direction, with three write paths and an *unconfirmed* state
for briefs summarized from existing prose. New **§4.1** closes the anchoring question:
**nothing durable points at a manuscript passage.** `state.md`, `outline.md` and
`impacts/` are gone from §2's tree; §3 puts briefs in the Manuscript class and adds
appearances and memoized judgements to Derived.
**05 is where the current risk concentrates.** The Thoreau recon (`RECON.md` in the
sibling evidence repo `../thoreau-evidence/raw/gutenberg/`) shows normalization is the hard part —
1906 editorial voice sits inside 1837 evidence, and year resolution depends on
chapter headings plus a weekday checksum. If this is wrong, everything
downstream is quietly wrong with no failing test.
**06 was rewritten 2026-08-31** and is now the load-bearing part. §8 defines
**subjects** (People, Timeline, Events, Themes, Arcs, plus whatever the author adds),
**entries**, the derived **gathered set** with its pin/exclude overlay, promotion from
candidates, the two consumers (assembly and audit), **author testimony**,
**settlements**, and why claims are the accretion layer rather than a subject. §9
keeps the four attribution statuses and adds §9.5: author testimony needs no badge.

### The record — conversations, edits, curation

| # | Part | Original §§ | Status |
|---|---|---|---|
| 07 | [Session Records, Direct Human Edits, Git as Audit](07-sessions-and-human-edits.md) | 10, 11, 41 | reduced |
| 08 | [The Curator, Post-Session Curation, Ownership](08-curator-and-ownership.md) | 12, 13, 14, 15 | stable |

**07** — §10 assumes Memoria owns the conversation loop. It does not: transcripts
with stable `#T017` anchors are derived from Claude Code's per-session JSONL as a
post-session pass.
**08** — ownership is **closed** (2026-08-31): §14 was rewritten as **ownership by
badge**. The entry body is shared territory, the §9 badge is the ownership marker,
testimony is never machine-written, and a monotonic human-touched flag plus the
dirty-tree rule backstop in-place author edits. Git-blame inference is retired.
§12.1's trigger table carries the audit pass; §13.4 forbids harvesting manuscript
prose into an entry without a settlement. §12 names the Curator's two halves: the
**index maintainer** (derived state only; no restraint rules) and the **record
extractor** (durable records; the only half §13 and the write matrix constrain).

### The manuscript — impact, authorship, authorization

| # | Part | Original §§ | Status |
|---|---|---|---|
| 09 | [Dependency, Propagation, Manuscript Impact](09-dependency-and-impact.md) | 16, 17, 18, 22 | stable |
| 10 | [Manuscript Rules, Authorship, Authorization](10-manuscript-authorship.md) | 19, 20, 21, 36, 37, 38 | stable |

**09 was rewritten 2026-08-31 and is now short.** Impact analysis is not a separate
mechanism — it is the audit fired from the other end, and both are the same memoized
judgement (part 06 §8.12). §17's seven-question list is withdrawn onto the subjects and
its premature-revelation question is removed outright; §18's ten categories were
already withdrawn. What remains is the finding, its disagreement set, and the
resolutions the set admits.
**10** is the plan's strongest material, now with one restriction added: authorization
covers **briefs** as well as prose, and a brief is never written from a finding card or
a batch. §20's provenance is composed from git and the session records rather than
stored.

### Working — retrieval, context, research

| # | Part | Original §§ | Status |
|---|---|---|---|
| 11 | [Retrieval, Context Builder, Digests](11-retrieval-and-context.md) | 25–30, 32, 33 | reduced |
| 12 | [Session Modes, Research Workflows, Resumability](12-research-and-resumability.md) | 31, 34, 35, 39 | stable |

**11** — FTS5 only to start; semantic embeddings deferred pending a measured
number from the cross-reference benchmark. §32's Tier 2 is now the **declared scope**,
which is what bounds the working context. New **§33.1** states the sharper version of
the search-scope problem: an index reports nothing about its own recall, and that is
the central risk of the subject system.
**12** — §39 was rewritten 2026-08-31. The seventeen-field state record and the
checkpoint are **withdrawn**; resumption is carried by the brief, the draft and an audit
on request. The test itself stands and is now harder, and **nothing in the Thoreau
corpus exercises it.**

### Runtime and interface

| # | Part | Original §§ | Status |
|---|---|---|---|
| 13 | [Model Runtime](13-model-runtime.md) | 24 | **reduced** |
| 14 | [Interfaces](14-interfaces.md) | 40 | **reduced** |
| 19 | [Desktop UI — as designed](19-desktop-ui.md) | — (design canvas) | open |

**13** is the most heavily narrowed part. The `ModelBackend` abstraction and the
§24.3–24.4 capacity scheduler are out: Memoria is an MCP server, Claude Code is
the client, and the subscription bet is avoided rather than validated. The
reduction is now marked inline at the head of the part.
**14** — local only. §40.5 auth and remote access are gone entirely; §40.6's write
coordinator reduces to a stale-revision check. Four of the five surfaces need no
model driver and are in scope; "Ask Memoria" is deferred. The reduction is now
marked inline at the head of the part.
**19 is illustrative throughout** — every label, verdict, badge and count in it is
example content and may not drive data structures (banner recorded 2026-08-31).
It is the designed desktop UI, recorded as it stands — six screens, the
slide-over citation panel, cross-layer search, and the vocabulary the interface
puts on screen. It reads as an acceptance description of §40.3 with navigation
added. It is **open** because the design leads with "Ask Memoria", which the PoC
defers. The anchoring blocker is **gone** (part 04 §4.1), and §19.11 now records
`LEGACY DRAFT`, drag-to-reorder, the Curator status line, the `CHECKPOINT` card and the
Review inbox as resolved or superseded.

### Checking and sequencing

| # | Part | Original §§ | Status |
|---|---|---|---|
| 15 | [Provenance Validation, Evaluation Suite, Health](15-validation-and-health.md) | 23, 43, 47 | **active** |
| 16 | [Build Order](16-build-order.md) | 44 | **active** |
| 17 | [Optional Future Infrastructure, Agents, Privacy](17-future-options-and-privacy.md) | 45, 46, 48 | stable |

**15** is active because the benchmark is now the instrument that decides whether
embeddings get built. §45's "observe failure, then adopt" only works if the
measurement exists. The harness reports three numbers (§43.14): retrieval
recall@10, gathered-set recall, and the promotion miss rate.
**16 was rewritten 2026-08-31** and sequences the PoC: six milestones from the
recon-informed normalizer to the authorship piece, each gated on a concrete
author-visible act, ending in the resumption gate that only real absence can
pass. The harness's three numbers land across M0–M2; the authorship piece is
decided at M4; the embeddings decision is taken at M2's gate by a procedure
pre-registered at M1. The original M0–M4 is archived in
`_original-memoria-plan.md` §44.
**17** — §45's adoption process is the governing rule for every "should we add X"
question.

### Illustrative

| # | Part | Original §§ | Status |
|---|---|---|---|
| 18 | [Usage Flow and Target Experience](18-usage-walkthrough.md) | 52, 53 | stable |

Narrative walkthroughs. Useful as an acceptance description; contains no
independent requirements.

---

## Reading orders

- **Orienting from scratch:** 01 → 02 → 03 → 18
- **The subject system:** 06 → 11 (§32, §33.1) → 09 → 08, then 04's anchoring note
- **Working on ingest now:** 05 → 04 → 06, with `RECON.md` alongside
- **Resolving the open decisions:** none remain at the architecture level — 04's anchoring and 08's ownership are both closed; what's left is in `../open-problems.md` §1
- **The manuscript layer:** 04 (§2.1, §4.1) → 06 (§8.11, §8.12) → 09 → 12 (§39)
- **Following the build:** 16, with `../poc-plan.md` and `../open-problems.md`
  alongside; 13 → 14 → 19 → 15 give the reductions and the harness it sequences

## Files

```
../thoreau-evidence/                sibling evidence repo: the PoC corpus
                                    (raw/, manifest.yaml, RECON.md)
CONTEXT.md                          settled domain vocabulary
docs/
├── poc-plan.md                     decisions from the grilling sessions
├── open-problems.md                everything still unsettled
├── design/
│   └── memoria-desktop.dc.html     the design canvas source, as incorporated
└── plan/
    ├── plan-index.md               this file
    ├── 01-…18-…                    the plan, split
    ├── 06-subjects-and-attribution.md   the subject system (rewritten)
    ├── 19-desktop-ui.md            the desktop UI as designed (illustrative)
    └── _original-memoria-plan.md   archived single-file original
```
