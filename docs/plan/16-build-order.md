<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 44 of the original memoria-plan.md -->
<!-- REWRITTEN 2026-08-31: re-sliced for the PoC runtime (MCP server + Claude Code -->
<!-- client, sibling evidence repo), the subject system, the manuscript layer and -->
<!-- ownership by badge. The original M0–M4 is in _original-memoria-plan.md §44. -->

# 44. Build Order

Memoria is built as a sequence of usable milestones rather than as several
independent infrastructure projects. Each milestone ends at a **gate**: a
concrete, author-visible act that either works or does not.

This order sequences the PoC (`../poc-plan.md`): Memoria as an MCP server with
Claude Code as the client.

> **Amended 2026-09-01.** The Thoreau corpus was retired as PoC data and no
> replacement was chosen (`../open-problems.md` §2.4). **M0 is withdrawn**, and
> **M1 and M2 can be built but not gated** — their gate acts need evidence, and
> there is none. The machine-scored track of poc-plan §1 is gone; the authorship
> track is untouched. M3, M4 and M5 are unaffected.

Four rules shaped the slicing; the first no longer holds:

- ~~**The harness carries the discipline.**~~ **Withdrawn with the corpus.** §45's
  "observe failure, then adopt" only works if the measurement exists — and it no
  longer does, so §45 now governs unaided. This is a real loss of discipline,
  recorded rather than papered over (`../open-problems.md` §2.2).
- **Normalization before everything.** It is the one place a mistake silently
  invalidates everything downstream (poc-plan §6 risk 3), so it lands first,
  recon-informed, with mechanical checks against whatever counts the corpus's own
  recon supplies.
- **The index maintainer before the record extractor.** The maintainer writes
  only rebuildable derived state and no restraint rule binds it (§12); the
  extractor needs session records, the curation restraint rules and the entry
  write matrix. Half the Curator is therefore buildable two milestones earlier
  than the other half.
- **A milestone forces the decisions it needs, and no others.** The open
  questions in `../open-problems.md` stay open until a gate needs them closed;
  the table at the end names what each milestone forces.

---

## M0 — Normalized Evidence You Can Trust — WITHDRAWN 2026-09-01

> **This milestone was built, gated, and then withdrawn.** It normalized the
> Thoreau corpus: the five works, year resolution with the weekday checksum,
> editorial-voice segregation, letters parsing, cross-reference extraction, the
> answer key, and a check-suite reconciling all of it against `RECON.md`'s
> counts. Every part of it was written for that corpus, so when the corpus was
> retired (`../open-problems.md` §2.4) the code went with it.
>
> **What survives:** the normalized-record contract — stable `SRC-` IDs,
> paragraph anchors, the frontmatter fields and the whitespace policy — recorded
> in `../normalized-record-schema.md`. That is what a successor normalizer must
> produce, and `memoria.index` and `memoria validate` already read it.
>
> **What a successor must re-force:** the editorial-apparatus representation, and
> whatever adjudication a new corpus's ground truth needs — if it has any. The
> lesson worth carrying is the one that retired this milestone: **do not build
> ingestion machinery against a corpus before establishing that what it measures
> is the task the real archive has.**
>
> Normalization stays first whenever a corpus does arrive. It is the one place a
> mistake silently invalidates everything downstream, with no failing test to
> reveal it (poc-plan §6 risk 3), and that risk was not discharged by the
> retirement.


## M1 — The Tool Surface

*Renamed 2026-09-01: there is no first number.* **Gate needs an evidence corpus.**

Build:

- the MCP server, exposing the minimum of §25 this gate needs: `search_text`
  over FTS5 and `read(ref)` over the §4 stable IDs — verbatim source text,
  never a summary in its place, with a raw undecorated full-source read
  available (poc-plan §7's superset-of-grep constraint);
- the `events.jsonl` read ledger: every served read recorded (§10.4, §33);
- ~~the benchmark harness~~ and ~~pre-registration~~ — **both withdrawn
  2026-09-01** with the corpus that supplied their ground truth (issues #14, #22,
  #23). The link-to-entry mapping went with them.

The evidence-read routing hook already exists; this milestone is what makes the
routed path the path of least resistance — the tools return more than a raw
read does.

### Gate — needs an evidence corpus

From Claude Code, ask a question about an evidence record. Every evidence read
arrives through the tools and lands in `events.jsonl`.

**This cannot be walked today.** The slices above are buildable against the
record schema and synthetic fixtures; the gate waits for a corpus. It is left
open rather than replaced — a substitute gate against evidence that does not
exist would assert nothing.

---

## M2 — Subjects, Candidates, and the Index Maintainer

Build:

- the five built-in subjects with their prompts — match definition, matching
  hazards, audit questions (part 06 §8.1). Hazards are stated as **classes** —
  surname collision, multi-form naming — not as instances of a particular corpus;
- continuous candidate matching and the recurrence filter (part 06 §8.4);
  promotion as an author act; manual entry creation;
- **match terms** on entries — populated by ingest, owned by the author, the
  system's only alias store (§7, part 06 §8.2);
- gathered sets, and the curated overlay: **pins and exclusions**, attributable
  and rebuild-surviving — the durable-dismissal machinery poc-plan §3 requires
  from the first Curator pass;
- appearances over the audit targets, lexical engine only (part 06 §8.11); the
  model engine for Themes and Arcs waits for the audit at M5;
- read decoration: `read(ref)` on evidence now returns the curated overlay —
  entry links, exclusions, settlements citing the paragraph (poc-plan §7);
- `rebuild` covers candidates, gathered sets and appearances; `validate` covers
  overlay attribution;
- ~~harness numbers two and three~~ — **withdrawn 2026-09-01** (issue #22). What
  survives is the structural mitigation: candidates the recurrence filter rejects
  stay **enumerable**, so a miss rate is computable the day ground truth exists.

### Gate — withdrawn 2026-09-01

Two of its three acts named people from the corpus, and the third was the harness
printing three numbers (issue #23). **M2 is left ungated.** No substitute is
written: inventing gate acts against a corpus that does not exist is ceremony, not
verification.

The embeddings decision this gate carried is withdrawn with it. It reverts to
§45's default — observe a real failure before adopting heavier machinery — which
is weaker than the pre-registered procedure it replaces (`../open-problems.md`
§2.2).

---

## M3 — Two Reading Surfaces

Build:

- the app shell and three-tree navigation (part 19's `MANUSCRIPT` tree stays
  empty until M5);
- the **Source viewer** with the slide-over citation panel and **Open
  original** into the evidence repo;
- the **Theme / Arc (entry) view**: audit-visible body with badges visible,
  match terms, gathered set with its overlay, appearances.

Both are reads over the repository and SQLite; no model driver (poc-plan §3).
The other two model-free surfaces — Section and Review — wait at M5 for the
data they show. M3 and M4 are independent of each other; order or overlap them
freely.

### Gate

Take a citation in an entry, click it, land on the exact evidence paragraph in
the slide-over without losing your place, then open the original file.

This is the original M0 gate, kept.

---

## M4 — Sessions and the Record Extractor

This milestone opens by deciding the **subject and length of the
authorship-track piece** (open-problems §4.1 and §6). The subject is fully open
as of 2026-09-01 — it was expected to be Thoreau's revision practice, and the
corpus that supplied that evidence is gone. Deciding it here rather than at M5
buys two things: the piece's research sessions become M4's real sessions,
exercising the extractor on genuine work instead of staged conversation, and
the clock the resumption gate needs starts as early as it can.

Build:

- transcript derivation from Claude Code's per-session JSONL:
  `sessions/**/transcript.md` with stable `#T` anchors, metadata, and the
  served-reads ledger folded in (§10, poc-plan §3);
- context manifests (§33), with the completeness claim conditioned on the
  routed layout, and **token counts per supplied item** — the development
  instrument behind `poc-plan.md` §6 risk 1's budget-capping experiment. It
  lives on the manifest and is never rendered by any surface (part 14 §40);
- the **record extractor** (§12–§13): decisions, questions, research memos;
  `[author]` only on a citing transcript turn, `[open]` otherwise; entry
  statement writes per part 06 §8.2's write matrix;
- the **human-touched flag**, the dirty-tree rule, and Memoria notes (§14);
- **settlements**, click-authorized, and the claims they accrete into
  (part 06 §8.7, §8.9);
- `validate` grows: an `[author]` statement without a citing turn fails; a
  badged write without provenance fails.

Research workflows (§34) are skills over the M1 tool surface, not
infrastructure; what this milestone builds is the durable records they leave.

### Gate

Hold a real research session on the piece's subject. Muse about an
interpretation; it lands `[open]`. Decide something; the decision cites your
exact turn, and clicking it lands on the sentence in which you decided.

Hand-edit a badged statement. The next pass flags it human-touched; when
evidence later conflicts with it, the conflict arrives as a Memoria note and
your text is unchanged.

---

## M5 — The Manuscript Layer and the Authorship Piece

The piece was decided at M4 and its research already exists as durable
records; M5 adds the machinery to write it. The manuscript layer has no test
corpus (open-problems §4.1) — the piece is the only place §43.2 can ever be
exercised — and the resumption gate needs real elapsed time after real
writing, so M5 starting late puts the defining test out of reach.

Build:

- **briefs** at three scales, with all three write paths, including the
  *unconfirmed* state (§2.1);
- legacy import: an audit target imported as manuscript prose gets an
  unconfirmed brief and a cold cache — a tinted chapter and a count, not ten
  thousand model calls (part 06 §8.12);
- **assembly**: the declared scope resolved through the subjects into the §32
  tiers, reporting what it resolved (§33.1). The report is the
  **supplied-context** surface, opened from the Section view: an unnumbered
  opener, live while open and absent while closed, stating countable domain
  units — briefs, entries, fallbacks, sources served — and naming anything the
  budget truncated. No token figure reaches it;
- one **scope resolver**: assembly, the audit's bounding and drift detection
  all resolve brief-to-entries through the same module (§32, part 06 §8.5) —
  three call sites independently inferring that fact is a divergence bug
  scheduled in advance;
- AI manuscript writing under explicit authorization, write scoping, and
  write-time provenance composed from `git blame`, the commit, the session and
  its manifest via `trace()` (part 04 §4.1, §19–§21);
- the **audit**, on demand only: memoized judgements under both key
  compositions, the staleness map, findings as disagreement sets, and the
  model-engine appearances for Themes and Arcs (part 06 §8.10–§8.12);
- brief drift as a set difference, never against an unconfirmed brief (§32);
- the **Section view** and the **Review surface** — the results view of an
  audit the author asked for, not an inbox (part 19 §19.11);
- the §47 health report — model-free, so it may run unasked;
- `validate` grows: an AI manuscript write without an identifiable
  authorization fails, **including writes to a brief** (§23).

### Gate

Import an existing chapter of prose as legacy manuscript. It gets an unconfirmed
brief and a not-current tint; no model pass runs unasked.

Write the piece's section brief, naming something with no entry. Open the
supplied context: assembly reports what the scope resolved to, and the fallback
to an unpromoted candidate is named there rather than passing in silence.
Authorize a draft from the assembled context, then ask why a paragraph says
what it says and walk the provenance to the session, the authorization and the
evidence.

Audit the section from its button. Settle one finding; the tint clears only
through re-audit.

---

## The Gate That Waits — Resumption

Work the piece deeply. Leave it for weeks. Return, and continue productive work
from the brief, the draft and an audit on request — with no stored recap
(§43.2, part 12 §39).

This gate cannot be scheduled to pass; it passes only after real absence, which
is why it stands outside the milestones. Everything above exists so that it can
be attempted honestly, and §1.12 is its governing risk: if the milestones all
gate green and this fails, Memoria advanced while no book did.

---

## What no milestone builds

The poc-plan §5 reductions stand: no `ModelBackend`, no capacity queue, no
auth or remote access, no web/phone surface, no Ask Memoria, and the write
coordinator stays a stale-revision check. Embeddings enter only against an
observed failure (§45) — there are no M2 numbers to say so.

Also deliberately unsequenced: **choosing an evidence corpus at all**
(open-problems §2.4) and rebuilding a benchmark harness against one — a successor
needs an archive carrying labelled provenance, and building one against an archive
that has none is what this retirement removed. Likewise the in-app
prose editor (open-problems §1.2), editability of built-in subjects (§1.3),
late-subject backfill (§1.5), and everything about the real archive —
including whether its sources live inside the repo (§1.4). Those wait for
observed need, under §45.

---

## What each milestone forces

| Milestone | Decision forced |
|---|---|
| M0 | **withdrawn** — the record schema it forced survives (`../normalized-record-schema.md`); the editorial-apparatus representation is re-forced when a corpus is chosen |
| M1 | exact signatures of `search_text` and `read(ref)`. The rest of §25's tool list stays open |
| M2 | nothing open — the embeddings decision it carried is withdrawn (open-problems §2.2) |
| M3 | nothing open — it builds what earlier decisions already settled |
| M4 | at its start: the authorship piece's subject and length (open-problems §4.1, §6) |
| M5 | nothing new — it spends decisions forced earlier |

---
