# Memoria Build Plan — Index

The build plan is split into 18 parts, each a unit that can be considered,
revised or grilled on its own. Every one of the original 53 sections appears
in exactly one part; **section bodies are verbatim**. Part 19 is the exception: it
records the desktop UI as designed, and has no counterpart in the original plan.

Nine parts — 04, 06, 08, 09, 10, 11, 12, 14, 18 — end in an appended
`## Editorial note — the desktop design`, recording where that design confirms,
extends or collides with the section above it. The notes sit below the section text
and never alter it.

- **These parts are canonical.** `_original-memoria-plan.md` is an archived copy
  of the single-file plan as of 2026-08-31, kept for reference only. Do not edit it.
- **Decisions from the 2026-08-31 grilling session** live in
  [`../poc-plan.md`](../poc-plan.md). Where a part has been narrowed or has an
  open question, the status column says so and the reasoning is there, not here.

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
| 04 | [Repository, State Classes, Identity, Rebuildability](04-repository-and-identity.md) | 2, 3, 4, 42 | open |
| 05 | [Source Ingestion, Temporal Discipline, Aliases](05-evidence-and-ingestion.md) | 5, 6, 7 | **active** |
| 06 | [Interpretation Layer and Attribution](06-interpretation-and-attribution.md) | 8, 9 | stable |

**04** carries the unresolved anchoring question: §4 gives sources durable
anchors but never says what makes a manuscript paragraph address stable.
**05 is where the current risk concentrates.** The Thoreau recon
(`../../sources/raw/gutenberg/RECON.md`) shows normalization is the hard part —
1906 editorial voice sits inside 1837 evidence, and year resolution depends on
chapter headings plus a weekday checksum. If this is wrong, everything
downstream is quietly wrong with no failing test.
**06** defines `[source]` / `[author]` / `[inferred]` / `[open]` and the five
interpretation object types.

### The record — conversations, edits, curation

| # | Part | Original §§ | Status |
|---|---|---|---|
| 07 | [Session Records, Direct Human Edits, Git as Audit](07-sessions-and-human-edits.md) | 10, 11, 41 | reduced |
| 08 | [The Curator, Post-Session Curation, Ownership](08-curator-and-ownership.md) | 12, 13, 14, 15 | **open** |

**07** — §10 assumes Memoria owns the conversation loop. It does not: transcripts
with stable `#T017` anchors are derived from Claude Code's per-session JSONL as a
post-session pass.
**08** holds the deferred ownership decision. §14's git-blame span inference is
expected to fail on prose reflow. Safe default while open: **the Curator does not
rewrite prose a human has touched.**

### The manuscript — impact, authorship, authorization

| # | Part | Original §§ | Status |
|---|---|---|---|
| 09 | [Dependency, Propagation, Manuscript Impact](09-dependency-and-impact.md) | 16, 17, 18, 22 | open |
| 10 | [Manuscript Rules, Authorship, Authorization](10-manuscript-authorship.md) | 19, 20, 21, 36, 37, 38 | stable |

**09** is blocked behind the anchoring decision in 04 — impact records store
pointers into prose, and §38's dismissal memory needs stable passage identity.
**10** is the plan's strongest material: autonomy in observation, reasoning and
recommendation; authorization at the point of canonical authorship.

### Working — retrieval, context, research

| # | Part | Original §§ | Status |
|---|---|---|---|
| 11 | [Retrieval, Context Builder, Digests](11-retrieval-and-context.md) | 25–30, 32, 33 | reduced |
| 12 | [Session Modes, Research Workflows, Resumability](12-research-and-resumability.md) | 31, 34, 35, 39 | stable |

**11** — FTS5 only to start; semantic embeddings deferred pending a measured
number from the cross-reference benchmark. §33's search-scope honesty is the part
that matters most and is unaffected.
**12** — §39's resumption test ("leave a section for weeks, return, continue
without a recap") is the plan's own stated bar for whether the rest is premature.

### Runtime and interface

| # | Part | Original §§ | Status |
|---|---|---|---|
| 13 | [Model Runtime](13-model-runtime.md) | 24 | **reduced** |
| 14 | [Interfaces](14-interfaces.md) | 40 | **reduced** |
| 19 | [Desktop UI — as designed](19-desktop-ui.md) | — (design canvas) | open |

**13** is the most heavily narrowed part. The `ModelBackend` abstraction and the
§24.3–24.4 capacity scheduler are out: Memoria is an MCP server, Claude Code is
the client, and the subscription bet is avoided rather than validated.
**14** — local only. §40.5 auth and remote access are gone entirely; §40.6's write
coordinator reduces to a stale-revision check. Four of the five surfaces need no
model driver and are in scope; "Ask Memoria" is deferred.
**19** is the designed desktop UI, recorded as it stands — six screens, the
slide-over citation panel, cross-layer search, and the vocabulary the interface
puts on screen. It reads as an acceptance description of §40.3 with navigation
added. It is **open** because the design leads with "Ask Memoria", which the PoC
defers, and because every locator it shows assumes the part 04 anchoring
decision. Those conflicts are listed in §19.11 and left unresolved.

### Checking and sequencing

| # | Part | Original §§ | Status |
|---|---|---|---|
| 15 | [Provenance Validation, Evaluation Suite, Health](15-validation-and-health.md) | 23, 43, 47 | **active** |
| 16 | [Build Order](16-build-order.md) | 44 | **superseded** |
| 17 | [Optional Future Infrastructure, Agents, Privacy](17-future-options-and-privacy.md) | 45, 46, 48 | stable |

**15** is active because the benchmark is now the instrument that decides whether
embeddings get built. §45's "observe failure, then adopt" only works if the
measurement exists.
**16 must be rewritten before it is followed.** M0 and M1 as written assume the
web service, ModelBackend and capacity machinery that parts 13 and 14 removed.
Re-slicing was deliberately not done in this session.
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
- **Working on ingest now:** 05 → 04 → 06, with `RECON.md` alongside
- **Resolving the open decisions:** 04 (anchoring) and 08 (ownership), then 09
- **Re-planning the build:** 13 → 14 → 19 → 15 → 16

## Files

```
docs/
├── poc-plan.md                     decisions from the grilling session
├── design/
│   └── memoria-desktop.dc.html     the design canvas source, as incorporated
└── plan/
    ├── plan-index.md               this file
    ├── 01-…18-…                    the plan, split
    ├── 19-desktop-ui.md            the desktop UI as designed
    └── _original-memoria-plan.md   archived single-file original
```
