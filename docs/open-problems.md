# Open Problems

Everything the plan knows it has not settled, in one place. Updated 2026-09-01, after
the Thoreau corpus was retired (§2.4).

Each entry says what the question is, where it lives, and — where one exists — the
**safe default** that keeps deferring it cheap. §45's discipline governs all of them:
observe a real failure before choosing a mechanism.

---

## 1. Open decisions

### 1.1 Curator ownership and human-edit supremacy — CLOSED 2026-08-31

**Resolved: ownership by badge.** The entry body is shared territory and §9's badges
are the structural ownership marker — testimony is never machine-written, `[author]`
requires a citing turn, `[source]`/`[inferred]`/`[open]` are the Curator's to revise.
§14's git-blame span inference is retired; the backstop for in-place human edits is a
monotonic **human-touched flag** set once at Curator-pass time, plus the rule that the
Curator never writes into a file with uncommitted human modifications. Both predicted
failures are structurally dead: there is no blame to destroy, and the surviving
ratchet points toward the author.

Full mechanism: part 06 §8.2 and part 08 §14. §20's display-blame coarseness is a
separate, already-accepted cost (§5 table, row 2).

### 1.2 Whether the in-app prose editor is built

`poc-plan.md` §3 puts editing in Obsidian. §19.7 draws a paragraph-at-a-time editor in
the app, which is a second write path into `chapters/**/draft.md`. The single write path
and its staleness check are all that hold the two apart, and the check is file-level.

**Why file-level is sufficient** — corrected 2026-09-01; the earlier reason given here was
that §4.1 leaves no stored pointers for an Obsidian edit to invalidate, which is an
argument about identity and does not bear on whether two writes collide. The real
constraint is that finer granularity has only two implementations and both are closed.
Positional ("replace paragraph 12") is invalidated by any insert or delete above the
target, so a concurrent edit elsewhere silently lands the write on the wrong prose — and
§4.1 removed durable passage identity by design, so position is all that is left.
Content-addressed ("replace the paragraph hashing to X") is patch application onto a file
that has moved, i.e. reconciliation, which `poc-plan.md` §5's reduction of §40.6 cut by
name. See `adr/0003-durable-writes-go-through-one-path.md`.

So this stays open on its own merits. If the editor is built, the cost of file-level
granularity is a rejected write, not lost work: the client holds the author's text and
re-reads for a fresh token.

Undecided, and cheap to leave undecided.

Where: `poc-plan.md` §3 and §8, part 19 §19.11.

### 1.3 Whether built-in subjects can be edited or removed

People, Timeline, Events, Themes and Arcs ship as built-ins. Whether the author may
rewrite their prompts — including the audit questions they now declare (part 06 §8.1) —
or delete them outright is unspecified.

Where: `poc-plan.md` §9.

### 1.4 Whether the real book repo holds its sources inside

The PoC corpus lives in a sibling evidence repo so that evidence reads route through
the tool surface (`poc-plan.md` §3). §2's canonical book repository keeps `sources/`
inside — which §1.2's repository-is-the-system, §4.1's ordinary relative links and
§42's one-tree rebuild all assume. When the real archive arrives, decide: sources
inside (then per-repo routing rules do the work of the layout) or a sibling evidence
repo (then §2 and §4.1's link examples change, and Obsidian will not resolve
sibling-relative links from a book-repo vault).

**Safe default:** inside, per §2. Revisit at archive time; the PoC layout proves the
routing either way.

### 1.5 Whether a late-added subject backfills over existing prose

Adding a subject after a hundred thousand words exist: does it evaluate what is already
written, or only what comes next? Under part 06 §8.12 this is now a cost question with a
clear shape — a new subject prompt means a cold cache for every paragraph against every
entry under it — and the on-demand rule means nothing happens until the author asks. So
the question reduces to what the interface offers, not what runs.

Where: `poc-plan.md` §9.

---

## 2. Deferred pending evidence

### 2.1 "Ask Memoria"

The one surface of §40.3 that needs a model driver, and the front door of the desktop
design. Deferred; the other four surfaces are reads over the repository and SQLite.

Deferred with it: the **second opener onto the supplied-context surface**, beside the
§19.2 scope note. That is the semantically right home for it — the scope note discharges
§33 for search, the panel discharges §33.1 for assembly — but book-wide conversations do
not exist in the PoC, so at M5 the surface opens from the Section view only (ADR-0001).

Where: `poc-plan.md` §3 and §5, part 19 §19.11.

### 2.2 Semantic embeddings — REOPENED 2026-09-01, with no instrument

FTS5 first, and it was to stay first only until a number said otherwise. That number
is gone: the benchmark harness was withdrawn with the corpus that supplied its ground
truth (§2.4), and with it the pre-registered go/no-go procedure that was the only
mechanism decision the build order scheduled.

**This is a real loss and should not be dressed up.** The plan's own rule was that
FTS5-first without measurement is just under-building. What remains is §45 unaided:
adopt heavier machinery only against a failure observed in use. That is a weaker
discipline than a pre-registered threshold, because "observed in use" is exactly the
kind of judgement that rationalizes after the fact.

**Safe default:** FTS5. Anything heavier needs a written-down failure first.

The extraction (ADR-0005, 2026-09-01) does not touch this: it is a candidate engine,
not a search index, and `search_text` stays FTS5. It is, though, the first thing to
enter without a failure, and §5 records that.

Where: `poc-plan.md` §3, part 11, part 15 §43.14.

### 2.3 What recall@10 over the cross-references is evidence for — SUPERSEDED

Raised 2026-09-01 while building the answer key; superseded the same day by §2.4,
which retired the corpus this was about. Kept because the reasoning is why the corpus
went.

Recall@10 over the editors' cross-references measured **retrieval when wording
diverges** — a real capability the eventual archive needs, since prose about an event
rarely repeats the words of the evidence behind it. But the *distribution* was Thoreau
deliberately rewriting journal into literature: almost certainly harder, and
differently shaped, than "the same event, described differently". The capability
transfers; the difficulty does not. So the number was **a stress case, good for
detecting gross failure, and a poor instrument for setting thresholds** — and a stress
case did not justify the machinery built to produce it.

### 2.4 The evidence corpus — OPEN, deliberately

**Decided 2026-09-01: the Thoreau corpus is retired as PoC data, and no replacement is
chosen.**

It had been chosen for a property almost no public corpus has — an archive, a
manuscript derived from it, and 628 editorial cross-references labelling which journal
passage became which published passage. What §2.3 established is that the ground truth
this bought was measuring a task the real archive does not have. Memoria is being built
for an author concerned with facts and event timelines; Thoreau is literary rewriting.

Not deferred pending a search for a better corpus. The alternative on offer was to keep
building measurement scaffolding for an instrument of uncertain validity, and that is
the trade being refused.

**What went with it:** the benchmark harness and all three of its numbers (issues #14,
#22, #23); M0's normalizer, editorial segregation, year resolution, cross-reference
extraction and answer key, and the code that implemented them; the M1 and M2 gates,
which now carry a *needs an evidence corpus* precondition.

**What did not:** everything in §1-23 — provenance, temporal discipline, attribution,
the subject system, manuscript authorization. `CONTEXT.md` and ADRs 0001-0004 are
corpus-agnostic, and ADR-0004 anticipated this directly by modelling evidence location
as a configured field inside the repository value.

**What this reopens:** §2.2 above, with nothing to decide it. And §4.1's gap widens —
the manuscript layer never had a test corpus, and now neither does the evidence side.

**Safe default:** build against the record schema, not against a corpus. The
normalized-record contract (`SRC-` IDs, paragraph anchors, the frontmatter fields) is
what a future normalizer must produce, and it survives.

Where: issue #1, `poc-plan.md` §1 and §3, part 16.

---

## 3. Documents that must be rewritten before they are followed

### 3.1 Part 16 — Build Order — CLOSED 2026-08-31

**Rewritten.** Part 16 now sequences the PoC as six gated milestones (M0
normalizer through M5 manuscript layer, plus the resumption gate), replacing the
M0/M1 that assumed the web service, `ModelBackend` and capacity machinery. Its
closing table records which open decision each milestone forces and when; nothing
in §1 above is decided by it. The old build order is archived in
`_original-memoria-plan.md` §44.

---

## 4. The gap with no plan entry

### 4.1 The manuscript layer has no test corpus

An archive supplies evidence and audit targets. No archive supplies **anything with a
brief, a declared scope, or a passage written from something**, and nothing to resume.
§43.2's resumption test is now the manuscript layer's central claim — it must be passed
by a brief, a draft and an audit on request, with no stored recap — and no corpus can
exercise it.

The authorship track's short piece is the only place any of this can be tested, which
means its subject and length are no longer a free choice. Deciding them is on the list
below. As of §2.4 the subject is fully open: it was expected to be Thoreau's revision
practice, on the grounds that the corpus supplied the evidence directly, and that
reasoning is void.

Where: part 12 §39, part 15 §43.2, `poc-plan.md` §6 risk 6.

---

## 5. Accepted costs, to watch in use

Not open questions — decisions already made, with known prices. Listed so that a real
failure is recognised as evidence rather than as a surprise.

| Cost | From | What would falsify the decision |
|---|---|---|
| A declined finding that is not craft direction recurs at every audit | §4.1 — no durable passage pointers | Recurring declines that genuinely cannot be written into a brief |
| Provenance display rides on `git blame`; reflow coarsens it | §20 | Blame attributing a paragraph so badly that provenance misleads |
| Appearances recall is unreported, worst for Themes | part 06 §8.11 | A theme demonstrably missing passages the author knows are there |
| Nothing repairs a stale brief but drift detection | part 04 §2.1 | Briefs drifting badly with drift never firing |
| A deliberately loose brief reports drift constantly | part 11 §32 | The pressure to tighten reading as noise rather than as useful |
| A legacy import audits from a cold cache | part 06 §8.12 | First audit of a real chapter being unaffordably slow |
| Assembly is reproducible per session, not globally deterministic | part 11 §32 | Needing to reproduce an old assembly exactly and being unable to |
| Ingest stales audit verdicts across every touched entry | part 06 §8.12 — fourth hash | Not-current counts so noisy after routine ingest that the author stops trusting the tint |
| The supplied-context account lists reads the client may have compacted away | ADR-0001 — the account covers the whole session, not just assembly | An author acting on a supplied item the model demonstrably no longer holds |
| The extraction and `search_global`'s summary mode ship without an observed failure | ADR-0005 — chosen against §1.11 and §45 | Clusters the author never promotes, or summaries the agent quotes in place of evidence |
| Placement recall is unreported, like gathered-set recall | ADR-0005 — unplaced surface forms stay enumerable | A person the author knows is in the archive with placements missing where the name is plain |
| A fresh archive shows no candidates until the author runs the extraction | ADR-0005 — one engine, author-launched | The first extraction of a real archive being unaffordably long in one session |
| Quoted replies are dropped from email records, not kept unindexed | part 05 §5.4 — one body per record, the quote is in the raw file and usually the parent record | A quoted message whose original was never exported (a sent-folder-only export) that the author needs to find by search |
| docx and pdf are one record per file until a real file breaks it | part 05 §5.2 — start simple; the split rule is the amendment path | A journal-style file whose every paragraph carries one date, polluting Timeline candidates |
| The ingest is planned against an unconfirmed format list | part 05 §5.2 — docx, pdf, email exports assumed | The real archive's bulk turning out to be something else (chat exports, scans) and the normalizer covering none of it |

---

## 6. Not yet specified

Build detail rather than open decisions, from `poc-plan.md` §7:

- ~~the normalized record schema~~ — settled 2026-09-01 for docx, pdf and email
  (part 05 §5.1-5.4, `normalized-record-schema.md`, ADR-0006); how editorial apparatus
  is represented is still open, and so is whether the extraction (ADR-0005) is handed a
  record's frontmatter — sender, recipient, date — alongside each paragraph, which
  email paragraphs need to be placeable;
- how images, charts and spreadsheets are handled — written down, not built: a deep
  read of a spreadsheet is unlikely to be worth it, surfacing that one was attached to
  a message may be (part 05 §5.4);
- which §25 tools ship, and their exact signatures — `read(ref)` forced
  2026-09-01 (issue #11, [`tool-surface.md`](tool-surface.md)); the rest open;
- the Curator's scope and trigger policy;
- **the subject and length of the authorship-track piece** — now constrained by §4.1
  above, and forced at part 16's M4;
- **which evidence corpus, if any, Memoria is proved against** — §2.4.
