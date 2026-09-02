# Memoria — Preliminary PoC Plan

Status: preliminary. Produced 2026-08-31 from a grilling session over
`memoria-plan.md`. Records decisions reached, decisions deliberately deferred,
and where this narrows the build plan. **No build sequencing is implied.**

> ## RETIRED 2026-09-01 — the corpus this plan was built around is gone
>
> **The Thoreau corpus is no longer Memoria's PoC data, and no replacement was
> chosen.** See `open-problems.md` §2.4 for the decision and its reasoning, and
> issue #1 for what it cost.
>
> This document is kept as the **decision record it is** — the sections below are
> what was decided on 2026-08-31 and why, not a description of the current plan.
> §1's corpus framing, all of §2, the benchmark half of §3, and risks 2 and 4 of
> §6 are retired along with the corpus; each is marked in place. Everything else
> — the runtime decision, the UI split, the rejection ledger, the two closed
> architectural deferrals, and the three addenda — stands unchanged, because none
> of it depended on which corpus was used.

---

## 1. What the PoC is

Memoria will be proved out against a **public archive** before it touches the
real one. The final archive for the book exists but its state is not yet
established; nothing here depends on it.

~~The test corpus is **Thoreau**~~ — **RETIRED 2026-09-01.** It was chosen for a
property almost no public corpus has: it contained an archive, a manuscript
derived from that archive, and 628 editorial cross-references labelling which
journal passage became which published passage — ground truth for
journal-to-manuscript provenance, the hardest thing in the plan to evaluate.

It was retired anyway, because that ground truth measured a task the real archive
does not have: Memoria is for an author concerned with facts and event timelines,
and Thoreau is literary rewriting. `open-problems.md` §2.4 carries the decision;
§2.3 carries the reasoning that forced it.

**No corpus is chosen.** Everything below that names one is history.

### The two tracks

One corpus, two uses, deliberately kept separate.

| | Machine-scored track | Authorship track |
|---|---|---|
| **Instrument** | ~~348 resolved cross-references~~ — **withdrawn 2026-09-01** | A real short piece of prose |
| **Author needed?** | No — runs unattended | Yes — must be genuine |
| **Tests** | Retrieval, provenance, temporal discipline (§43.1, §43.7, §43.11) | Ownership, curator restraint, authorization (§1.7, §13.4, §14, §15, §19-21) |
| **Output** | Three numbers: retrieval recall@10 / precision@10, gathered-set recall, promotion miss rate (§3) | Observed failures |

**Why separate.** A benchmark that can be scored automatically loses most of its
value if it is entangled with prose being judged subjectively. And the ownership
invariants cannot be tested at all without a real author making real decisions —
a public archive contains no author voice, so "did the Curator harden my
speculation into my belief" is unexercisable against it. Reconstructing Walden
from the journals was considered and rejected for exactly this reason: it gives
an objective quality signal but turns authorship into imitation, reopening the
gap.

~~The authorship track's likely subject is **Thoreau's revision practice**~~ —
void as of 2026-09-01; the corpus that supplied the evidence for it is gone, and
the subject is fully open again (issue #27).

---

## 2. Corpus — acquired, and RETIRED 2026-09-01

> **This whole section is history.** The corpus was retired as PoC data on
> 2026-09-01 (`open-problems.md` §2.4) and the ingestion code written for it was
> removed. The findings below are kept because several of them are *general* —
> normalization being the hard part, dates being harder than boundaries, quote
> conventions differing within one edition — and a future corpus will meet them
> again.

10 files under `raw/gutenberg/` in the **sibling evidence repo**
`../thoreau-evidence/` (moved out of this repo 2026-08-31 — see §3), hashed in its
`manifest.yaml`, analysed in its `RECON.md`. **661,946 words.** Nothing failed
verification, including the post-move hash check.

| ID | Role | Work | Words |
|---|---|---|---|
| 57393 | evidence | Journal I, 1837-1846 | 139,336 |
| 59031 | evidence | Journal II, 1850-Sep 1851 | 142,119 |
| 43523 | evidence | Familiar Letters | 143,211 |
| 205 | audit_target | Walden + Civil Disobedience | 118,874 |
| 4232 | audit_target | A Week on the Concord and Merrimack | 118,406 |

**Spec correction:** the originally specified Walden ID 26289 is an *audiobook* —
its file tree holds only `m4b/`, `mp3/`, `ogg/`, `spx/`. Substituted ID 205.

### Findings that shape the design

- **Text quality is excellent.** Genuine Distributed Proofreaders output. Valid
  UTF-8, no BOM, CRLF throughout. Zero ligature corruption, zero l/1 confusion.
  Every apparent "stray page number" was legitimate text.
- **Normalization is the hard part, not retrieval.** ~1,750 inline footnote
  markers and ~1,050 bracketed editorial spans put 1906 editorial voice
  *inside* 1837 evidence, plus two long editor introductions (Torrey ~L428-1290
  in J01; Sanborn in Letters). Under §6 these are retrospective commentary about
  the evidence. Misclassifying them silently invalidates every date-leakage test.
- **Entry boundaries are easy; dates are not.** All 448 date headings are
  line-initial italics in a small closed set (`_Oct 22._`, `_Jan. 24. Sunday._`),
  zero mid-line. But only 3 of 448 carry a year — the year lives on the chapter
  heading, and three J01 chapters span multiple years (`1845-1846`, `1845-1847`,
  `1837-1847`). **~100 headings carry a weekday, which resolves the year
  exactly**; the remainder should be marked inferred rather than exact. J02
  Chapter I is undated fragments and should stay that way.
- **The cross-references need text matching, not page lookup.** They cite 1906
  Manuscript Edition and Riverside pages. Walden and Week as held have **zero
  page markers** and are different editions. The journals and letters HTML *do*
  carry page anchors (486 / 503 / 458). So evidence is page-addressable and
  targets are not. Matching is further complicated by Thoreau rewriting heavily
  between journal and book — matches are paraphrases. This is harder than a join
  but is the actual §17/§20 task, with labels.
- **Quote characters differ between volumes of one edition.** J01 and Letters use
  straight ASCII; J02 uses curly Unicode. Exact-match search will silently
  succeed on one volume and fail on another.
- **Free alias material** in Letters: 130 letters, 43 recipients, Emerson under
  four location forms, four Thoreaus sharing a surname — the unsafe-merge hazard
  §7 warns about, already present.
- Retained variant spellings (`Shakspeare`/`Shakespeare`, `Bramins`/`Brahmins`)
  are declared by the transcriber. **Alias test material, not errors.**

---

## 3. Decisions reached

### Corpus scale — accepted as-is *(moot: corpus retired 2026-09-01)*
662k words is roughly 860-930k tokens, which **fits inside a 1M context window**.
The central claim (§0.1) therefore cannot be falsified against this corpus, and a
"paste everything in" baseline would beat Memoria on most queries. Expanding was
considered — Gutenberg holds only journal volumes 01 and 02, but *Excursions*,
*Cape Cod* and *The Service* (~162k words) would have resolved all 628
cross-references and crossed 1M tokens. **Accepted the corpus as-is anyway.**

Consequence to carry: the machine-scored track runs at **364 of 628 links (58%
coverage)**; references to *Excursions*, *Cape Cod* and *The Service* are
unresolvable.

**Superseded 2026-09-01 (issue #9).** Both numbers were RECON's. Re-deriving the
cross-references mechanically finds 668, not 628, of which 379 land on held works;
the answer key resolves **348** of those. Coverage against the full 668 is 52%
rather than the 58% projected here. The projection was left standing because the
answer-key protocol measured itself against it; both are gone as of 2026-09-01.

### Runtime — local, no model-driving service
Everything runs on one machine. Memoria is an **MCP server** exposing the §24.2
controlled tool surface; **Claude Code in the repo is the client**; Obsidian is
the editor.

This *avoids* the §24 subscription bet rather than validating it. The risky part
was never "use Claude Code" — it was driving Claude Code headless behind a web
service on personal subscription auth, then building a capacity scheduler to
manage the resulting fragility. Using Claude Code as an interactive client is its
ordinary supported use.

§10 survives without Memoria owning the conversation loop: Claude Code writes
per-session JSONL under `~/.claude/projects/<slug>/<session-id>.jsonl` with
`sessionId`, `parentUuid` chains and a uuid per message, so
`sessions/**/transcript.md` with stable `#T017` anchors can be **derived** as a
post-session pass — which is the §13 curation step regardless.

**Evidence lives in a sibling repo, and direct reads are routed, not forbidden**
(2026-08-31; widened 2026-09-01, #112). The corpus moved to `../thoreau-evidence/`,
whose own git history is Invariant 3's tamper-evidence. In this repo a PreToolUse
hook (`.claude/hooks/route-evidence-reads.sh`) denies Read/Grep/Glob against the
evidence path with a message pointing at the Memoria tools. The framing matters: the
hook is a **router, not a wall** — the tools return the same verbatim text plus the
curated overlay (entry links, exclusions, settlements citing the paragraph), and
every served read lands in `events.jsonl`, which is what makes §33's manifest a
record rather than a request.

The M1 gate (#15) found the router pointed at the wrong thing: no session opens the
raw evidence directly, but `sources/normalized/` and `.memoria/` — this repo's own
records and index — are read every time, and one session's Bash sweep over
`sources/normalized/*.md` went around the hook entirely while the ledger showed
nothing for it. The hook now also denies Read/Grep/Glob under this repo's own
`sources/normalized/` and `.memoria/`, whether or not an evidence corpus is
configured, and is registered for Bash too: a command whose text names
`sources/normalized`, `.memoria/`, or the evidence root is denied by exact-string
containment, no attempt at shell parsing. A determined rewrite of the command text
can still get past that; accepted — the goal remains that the logged path is the
path of least resistance, not that evasion is impossible.

Verified present: Claude Code 2.1.252, Python 3.14.4, Node 26.3, SQLite 3.46.1
with FTS5, no MCP servers configured.

### UI — wanted, and split by whether a surface needs a model
The UI is in scope. Four of the five §40.3 surfaces need **no model driver at
all** — they are reads over the repo and SQLite:

| Surface | Model driver? |
|---|---|
| Section view | No |
| Source viewer | No |
| Theme / Arc view | No |
| Review queue (evidence, diff, apply, dismiss) | No |
| Home / Ask Memoria | **Yes** — the only one |

Build the four model-free surfaces; conversation stays in Claude Code. Add "Ask
Memoria" later, choosing a driver with real usage behind the decision.

Running locally removes: **§40.5 auth and remote access entirely** (no HTTPS,
tailnet, or credentials), **§40.6 write coordinator** down to "reject writes
staged against a stale git revision", upload/download paths, and streaming
complexity. It does **not** remove the question of who drives the model — local
vs remote changes exposure, not runtime.

### Retrieval — FTS5 only, benchmark decides
SQLite FTS5 plus the §28 agentic loop. No embeddings initially.

Normalized record counts will be small — roughly 448 dated journal entries, 130
letters, plus book chapters — so FTS5 is instant over 600-1,500 records.

The tension was acknowledged: the headline benchmark was **paraphrase matching**,
where lexical search is structurally weak, so FTS5 was expected to score poorly.
That was the point. §45 requires heavier machinery to beat the existing system
against an observed failure, and the corpus produced that number on day one
rather than after months of vague dissatisfaction. Adding local embeddings later
is cheap — bge-base on CUDA and a recall/precision harness over 80k messages are
already proven in a separate project.

> **Decided 2026-09-01** (`adr/0007-embeddings-enter-by-choice.md`): embeddings enter
> by choice, because the failure §45 waits for is a retrieval miss and a retrieval miss
> is never observed. The shape is a `sqlite-vec` table in the index file and a local CPU
> model — production has no GPU, so the CUDA path above is prior art only. Built at M2
> against fixtures.

**This only works if the benchmark harness is built early.** FTS5-first without
measurement is just under-building.

> **RETIRED 2026-09-01.** The harness was withdrawn with the corpus that supplied
> its ground truth (issues #14, #22, #23). The sentence above still stands as a
> criticism — of the current state. There is no measurement, so §45 governs
> unaided: heavier machinery enters only against a failure observed in use, which
> is a weaker discipline than the pre-registered threshold this replaced.
> `open-problems.md` §2.2 carries it.

**The harness reports three numbers, not one** (2026-08-31; ~~withdrawn~~ 2026-09-01 — kept because a successor harness owes the same three things):

1. **Retrieval recall@10** over the 348 cross-references the answer key resolved
   — the number that was to decide whether embeddings
   get built (§45 discipline). What a poor score licenses has to be written down
   before the number exists; see `open-problems.md` §2.3.
2. **Gathered-set recall** — a set metric, not @k: of the cross-referenced
   journal passages belonging to an entry, the fraction actually present in that
   entry's gathered set. A writing agent reads the gathered set *instead of*
   searching, so set completeness — not rank quality — is what decides whether
   the index is safe to write from (part 06 §8.3, part 11 §33.1).
3. **Promotion miss rate** — the promoted set scored against `RECON.md`'s ground
   truth of 43 distinct letter recipients. The ≥5-recurrence filter admits at
   most 9 / 18 / 36 candidates per volume, so the filter that makes promotion
   tractable is a guaranteed miss generator; this number says how bad the misses
   are, rather than assuming the dozens it keeps are the right dozens (part 06
   §8.4).

### Rejection ledger
Not treated as an architecture decision. The only requirement: **dismissals get
recorded durably from the first Curator pass**, not retrofitted after fifty
things have been dismissed. §15 and §38 both depend on it.

---

## 4. Decisions deliberately deferred

Both were deferred under §45 discipline — observe real failure before choosing a
mechanism — and both have since been closed. The entries record the questions as
deferred and how each was resolved.

### Manuscript passage anchoring — CLOSED 2026-08-31

**Was:** §17, §20, §16 and §38 all stored pointers like `chapters/02/draft.md#p7`, and
nothing made `#p7` stable. Four mechanisms were weighed — Obsidian block IDs, HTML
comment anchors, content-hash with fuzzy re-anchoring, positional anchors. A fifth,
"store no pointers and recompute everything", was ruled out **on principle**, because
§38's dismissal memory was thought to need stable passage identity.

**Resolved:** the fifth option, on the ground that its ruling-out was wrong. Dismissal
memory does not need passage identity — a decline worth remembering is craft direction,
and craft direction lives in the section's brief. With that removed, nothing durable
needs to point at a paragraph: findings recompute, entry-to-passage edges became
`appearances` in the index, settlements live on the entry, and write-time provenance is
composed from `git blame` plus the session's context manifest.

Full reasoning: part 04 §4.1. This also unblocks the desktop UI, which part 04
previously said could not be built past mock data until this was settled.

### Human-edit supremacy / Curator ownership — CLOSED 2026-08-31

**Was:** §1.7 stated as an invariant but §14 implemented it as a heuristic — git
blame at span granularity. Two expected failures: prose reflow destroys attribution,
so one Curator touch claims your sentence; and ownership ratchets the wrong way,
since once the Curator owns a span your light edit does not reclaim it, inverting
§1.7 exactly. Options weighed: file-level ownership via git history, explicit span
markers, always-append-only Curator, or git blame as specified — none chosen; the
safe default while deferred was "the Curator does not rewrite prose a human has
touched."

**Resolved: ownership by badge.** The entry body is shared territory and the §9 badge
is the structural ownership marker: testimony is never machine-written, `[author]`
requires a citing transcript turn, the working badges are the Curator's to revise.
Blame inference is retired, so there is nothing for reflow to destroy; a monotonic
**human-touched flag**, set once at Curator-pass time from commit diffs, backstops
in-place author edits of badged statements, and the Curator never writes into a file
with uncommitted human modifications. Full mechanism: part 06 §8.2, part 08 §14.

---

## 5. What this removes from the plan, for the PoC

| Plan section | Status |
|---|---|
| §24 `ModelBackend` abstraction | Out — Claude Code is the client directly |
| §24.3-24.4 capacity queue and priority scheduler | Out — no evidence it is needed; interrupted sessions corrupt nothing because files are truth |
| §40.5 auth, HTTPS, tailnet | Out — localhost only |
| §40.6 write coordinator | Reduced to a stale-revision check |
| §40.3 "Home / Ask Memoria" | Deferred — the only surface needing a model driver |
| Semantic embeddings | ~~Deferred — pending the benchmark number~~ In by choice, 2026-09-01 (ADR-0007); built at M2 against fixtures |
| Web/phone access | Out — costs interface coverage, not invariant coverage |

Nothing in §1-23 (provenance, temporal discipline, attribution, the interpretation
layer, manuscript authorization) is removed. The reductions are all runtime and
interface.

---

## 6. Known risks

1. **The corpus fits in context.** Accepted knowingly. The large-corpus claim
   (§0.1) is not falsifiable here and must be proved against the real archive.
   Capping the Context Builder budget well below corpus size would test the same
   retrieval discipline honestly, and remains available.
2. ~~**Benchmark coverage is 58%.**~~ **Void 2026-09-01** — there is no benchmark.
   Replaced by: **there is no evidence corpus at all**, so M1 and M2 can be built
   but not gated, and nothing measures retrieval quality.
3. **Normalization correctness is load-bearing and unverifiable downstream.** If
   editorial voice leaks into evidence, every temporal-discipline result is quietly
   wrong, with no failing test to reveal it. **Not discharged by the retirement** —
   it transfers intact to whatever corpus arrives next.
4. ~~**Paraphrase matching may be hard enough to swamp the signal.**~~ **Resolved
   by retirement 2026-09-01.** This risk was the argument that retired the corpus:
   the links measured a distribution the real archive does not have. See
   `open-problems.md` §2.3 and §2.4.
5. **Ownership — resolved 2026-08-31** (ownership by badge, §4). Both architectural
   deferrals are now closed; what remains open is listed in `open-problems.md` §1.
6. **The manuscript layer has no test corpus.** An archive supplies evidence and
   audit targets, but nothing with a brief, a declared scope, or a passage written
   from something. §43.2's resumption test is now the manuscript layer's central claim and
   can only be exercised on the authorship track's own piece.
7. **§1.12 remains the governing risk.** The failure condition is Memoria
   advancing while no book does. The authorship track exists partly to keep that
   honest during development.

---

## 7. Not yet decided

- Build sequencing and milestone structure — **deliberately not addressed** here;
  addressed 2026-08-31 in the rewritten [`plan/16-build-order.md`](plan/16-build-order.md).
- ~~Normalized record schema and the editorial-apparatus representation.~~ Settled
  2026-08-31, and the corpus-agnostic half survives the retirement:
  [`normalized-record-schema.md`](normalized-record-schema.md) is now the contract
  a future normalizer must produce.
- Which §25 tools ship, and their exact signatures — constrained 2026-08-31:
  retrieval must be a **superset of grep**: verbatim source text (never
  summarized-only), decorated with the curated overlay, a raw full-source read
  available, and every read ledgered in `events.jsonl`. Narrowed further the same
  day: the per-type read tools unify into one `read(ref)` over the §4 stable IDs
  (part 11 §25, mirrored in §24.2). **`read(ref)` was forced 2026-09-01** (issue
  #11) and is recorded in [`tool-surface.md`](tool-surface.md), which also states
  what it deliberately does not do yet — no overlay (#20), and no
  `raw` parameter, which #20 owes when it adds decoration. `search_text` (#12)
  and the `events.jsonl` read ledger (#13) have since shipped too, both
  recorded in the same doc.
- Scope and trigger policy for the Curator.
- Subject and length of the authorship-track piece — fully open again as of
  2026-09-01, since the corpus that suggested one is gone (issue #27).
- **Which evidence corpus, if any, Memoria is proved against** — `open-problems.md`
  §2.4. This replaces the old question of whether to acquire *Excursions*,
  *Cape Cod* and *The Service*, which is moot.

---

## 8. Addendum — desktop design, 2026-08-31

A desktop UI was designed after this session and incorporated as
[`plan/19-desktop-ui.md`](plan/19-desktop-ui.md); the canvas source is at
[`design/memoria-desktop.dc.html`](design/memoria-desktop.dc.html).

**Nothing above is revised by it.** Two points of contact worth recording:

- The design makes **Home / Ask Memoria** the front door — the one surface §3 defers
  as needing a model driver. The deferral stands; the design simply assumes it
  resolved.
- The design **edits manuscript prose in the app**, paragraph at a time. §3 above puts
  editing in Obsidian, and §5 reduces §40.6 to a stale-revision check. If the in-app
  editor is built, that check is what has to hold the two write paths apart.

Both, and the rest of the reconciliation, are listed in §19.11.


---

## 9. Addendum — the subject system, 2026-08-31

A second grilling session replaced §8's five fixed interpretation object types with
**subjects**: named dimensions along which the archive connects to the book, each
serving as both an index a writing agent reads and a check the Curator runs. Built-in
subjects are People, Timeline, Events, Themes and Arcs; the author adds more. Claims
are not a subject — they are the propositional layer that accretes from the author's
settlements.

Full model: [`plan/06-subjects-and-attribution.md`](plan/06-subjects-and-attribution.md).
Vocabulary: [`../CONTEXT.md`](../CONTEXT.md).

**What it changes for this PoC.**

- **The headline benchmark gains a second reading.** The 348 resolved
  cross-references already measure retrieval recall. Under the subject system they
  also measure **index recall** — whether an entry's gathered set is complete enough
  to write a chapter from. That is the central and otherwise-silent risk of the
  design (part 06 §8.3, part 11 §33.1). §3's "this only works if the benchmark
  harness is built early" becomes more load-bearing, not less. Scored as
  **gathered-set recall**, the second of §3's three harness numbers.
- **The alias material stops being a side test.** `RECON.md`'s Emerson-under-four-forms
  and four-Thoreaus-sharing-a-surname are now the worked example of a subject's
  **matching hazards** (part 06 §8.1), which is a required field on every subject
  prompt.
- **Entry population is measurable here.** Recurrence collapses the candidate space
  hard on this corpus — 516 / 638 / 1,066 distinct capitalized-name candidates per
  volume, but only 9 / 18 / 36 appearing five or more times, against `RECON.md`'s
  ground truth of 43 distinct letter recipients. The promotable set is dozens — and
  a filter admitting at most 36 candidates cannot reach all 43, which is why the
  **promotion miss rate** is §3's third harness number.
- **The authorship track gains a specific thing to observe.** Author testimony
  outranks documentary evidence (part 06 §8.6), which means the audit can report
  author misremembering but never flag it as an error. Whether that feels right in
  practice is only answerable with a real author writing real prose.
- **Nothing in §5's reductions is affected.** The subject system is repository and
  Curator design; it adds no runtime and no interface requirement beyond what §3
  already scoped.

**Revised 2026-09-01.** The candidate numbers above came from a capitalized-name
pass that no longer exists: candidates now come from the **extraction**, a model pass,
and subjects carry an **auto-promote** declaration
(`adr/0005-extraction-is-the-candidate-engine.md`). The gathered-set recall reading
stands.

**Still not decided.** Whether hard-coded subjects can be edited or removed, and
whether adding a subject late backfills over existing prose. §17's premature-revelation
check was **removed entirely** on 2026-08-31 rather than rehomed. Manuscript durable
state and its storage were settled in a third session; see §10.


---

## 10. Addendum — the manuscript layer, 2026-08-31

A third grilling session settled what durable state the manuscript carries. Full model:
[`plan/04-repository-and-identity.md`](plan/04-repository-and-identity.md) §2.1 and
§4.1, [`plan/06-subjects-and-attribution.md`](plan/06-subjects-and-attribution.md)
§8.11-§8.12, [`plan/09-dependency-and-impact.md`](plan/09-dependency-and-impact.md),
[`plan/12-research-and-resumability.md`](plan/12-research-and-resumability.md) §39.
Vocabulary: [`../CONTEXT.md`](../CONTEXT.md).

**The manuscript's whole durable footprint** is the prose plus one editable prose field
per level — the **brief** — in `book.md`, `chapter.md` and `section.md`. `state.md`,
`outline.md`, the checkpoint, §39's seventeen fields, impact records and passage anchors
are all gone.

**What this changes for this PoC.**

- **Anchoring is closed** (§4 above), which removes one of the two deferred
  architectural questions and unblocks the interface.
- **Nothing analyzes prose unasked.** Audits run from a button on a section, a chapter
  or a highlighted passage. Invariant 8 is amended. This makes importing a legacy
  manuscript cheap — a cold cache produces a tinted chapter and a count, not ten
  thousand model calls — which matters because the authorship track starts from real
  prose.
- **Staleness is free and always known.** Judgements are memoized on
  `hash(paragraph) + hash(entry) + hash(subject prompt)`, so what is **not current** is
  a hash comparison. §47's health report survives autonomy on exactly this ground: it
  needs no model.
- **§17's fixed question list moved onto the subjects.** Each subject prompt now
  declares the audit questions it asks, which makes the subject prompt the third place
  the PoC's alias and hazard material has to be right — and makes a new subject
  incomplete until its questions are written.
- **The benchmark gains no new reading, but the corpus gap widens.** Nothing in Thoreau
  exercises briefs, resumption, or write-time provenance. This is now risk 6 in §6.
- **Nothing in §5's reductions is affected**, and §3's "Obsidian is the editor" is
  untouched: whether the in-app paragraph editor is built remains open, and the reduced
  §40.6 stale-revision check is still what holds two write paths apart.
