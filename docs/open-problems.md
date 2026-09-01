# Open Problems

Everything the plan knows it has not settled, in one place. Updated 2026-08-31, after
the manuscript-layer session.

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
the app, which is a second write path into `chapters/**/draft.md`. The reduced §40.6
check — "reject writes staged against a stale git revision" — is all that holds the two
apart, and it is file-level, which is now sufficient because §4.1 leaves no stored
pointers for an Obsidian edit to invalidate.

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

### 2.2 Semantic embeddings

FTS5 first. The resolvable cross-references produce the number that decides whether
heavier machinery is justified. **This only works if the benchmark harness is built
early** — FTS5-first without measurement is just under-building.

The answer key now exists (issue #9): **348 of 379** links resolved, by aligning the
editions the footnotes cite rather than by adjudication. See §2.3 before reading the
number it produces as a threshold.

Where: `poc-plan.md` §3, part 11, part 15.

### 2.3 What recall@10 over the cross-references is evidence for

Raised 2026-09-01 while building the answer key, and it constrains how §2.2 may be
decided rather than deferring anything.

Recall@10 over these links measures **retrieval when wording diverges** — a real
capability the eventual archive needs, since prose about an event rarely repeats the
words of the evidence behind it. But the *distribution* is Thoreau deliberately
rewriting journal into literature: almost certainly harder, and differently shaped,
than "the same event, described differently". The capability transfers; the difficulty
does not.

So the number is a **stress case, good for detecting gross failure, and a poor
instrument for setting thresholds**. `poc-plan.md` §6 risk 4 anticipates half of this —
that the task may be hard enough to swamp the signal — but frames it as difficulty
rather than as measuring a task the real archive does not have.

**What follows:** M1's pre-registered embeddings procedure (issue #14) must say what a
poor score licenses, written down before the number exists. Harness numbers two and
three are unaffected — gathered-set recall measures index completeness, promotion miss
rate measures entity resolution against `RECON.md`'s 43 recipients, and both are the
People/Timeline/Events material a factual archive is actually made of.

Where: `docs/answer-key-protocol.md`, issue #14, part 15 §43.14.

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

Thoreau supplies evidence and audit targets. It supplies **nothing with a brief, a
declared scope, or a passage written from something**, and nothing to resume. §43.2's
resumption test is now the manuscript layer's central claim — it must be passed by a
brief, a draft and an audit on request, with no stored recap — and it cannot be
exercised against the corpus at all.

The authorship track's short piece is the only place any of this can be tested, which
means its subject and length are no longer a free choice. Deciding them is on the list
below.

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

---

## 6. Not yet specified

Build detail rather than open decisions, from `poc-plan.md` §7:

- the normalized record schema, and how editorial apparatus is represented;
- which §25 tools ship, and their exact signatures;
- the Curator's scope and trigger policy;
- **the subject and length of the authorship-track piece** — now constrained by §4.1
  above, and forced at part 16's M4;
- whether and when to acquire *Excursions*, *Cape Cod* and *The Service*.
