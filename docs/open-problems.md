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

### 1.4 Whether a late-added subject backfills over existing prose

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

Where: `poc-plan.md` §3 and §5, part 19 §19.11.

### 2.2 Semantic embeddings

FTS5 first. The 364 resolvable cross-references produce the number that decides whether
heavier machinery is justified. **This only works if the benchmark harness is built
early** — FTS5-first without measurement is just under-building.

Where: `poc-plan.md` §3, part 11, part 15.

---

## 3. Documents that must be rewritten before they are followed

### 3.1 Part 16 — Build Order

**Superseded.** M0 and M1 assume the web service, `ModelBackend` and capacity machinery
that parts 13 and 14 removed, and it predates the subject system and the manuscript
layer. Re-slicing was deliberately not done in the three grilling sessions so far.

Sequencing is now more decidable than it was: anchoring is closed, the manuscript's
durable footprint is fixed, and the audit has one mechanism rather than two.

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

---

## 6. Not yet specified

Build detail rather than open decisions, from `poc-plan.md` §7:

- the normalized record schema, and how editorial apparatus is represented;
- which §25 tools ship, and their exact signatures;
- the Curator's scope and trigger policy;
- **the subject and length of the authorship-track piece** — now constrained by §4.1
  above;
- whether and when to acquire *Excursions*, *Cape Cod* and *The Service*.
