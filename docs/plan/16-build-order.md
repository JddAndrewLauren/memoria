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
Claude Code as the client, proved against the Thoreau corpus in the sibling
evidence repo, on the two tracks poc-plan §1 keeps separate. Four rules shaped
the slicing:

- **The harness carries the discipline.** §45's "observe failure, then adopt"
  only works if the measurement exists, so the benchmark harness (§43.14)
  reports its three numbers from the first milestone that can produce any of
  them, printing the rest as *not yet measurable* rather than omitting them.
- **Normalization before everything.** It is the one place a mistake silently
  invalidates every downstream number (poc-plan §6 risk 3), so it lands first,
  recon-informed, with mechanical checks against `RECON.md`'s counts.
- **The index maintainer before the record extractor.** The maintainer writes
  only rebuildable derived state and no restraint rule binds it (§12); the
  extractor needs session records, the curation restraint rules and the entry
  write matrix. Half the Curator is therefore buildable two milestones earlier
  than the other half.
- **A milestone forces the decisions it needs, and no others.** The open
  questions in `../open-problems.md` stay open until a gate needs them closed;
  the table at the end names what each milestone forces.

---

## M0 — Normalized Evidence You Can Trust

Build:

- the normalizer for the five works, driven by the evidence repo's `RECON.md`:
  Gutenberg boilerplate and front matter excluded; CRLF and per-volume quote
  conventions handled; entries split on the line-initial italic date headings;
- year resolution from chapter headings with the **weekday checksum** as the
  primary path: `date_confidence: exact` only where checked, `inferred` for the
  remainder, `chapter-only` for J02's undated fragments (§5.2, §6);
- **editorial-voice segregation**: Torrey's and Sanborn's introductions, the
  ~1,750 footnote markers and ~1,050 bracketed editorial spans stored as
  retrospective editorial records *about* the evidence, never inside it (§6);
- letters parsing: header, dateline, recipient, salutation, body;
- the normalized record schema, stable `SRC-` IDs and paragraph anchors
  (§5.2–5.3);
- SQLite FTS5 over the normalized records;
- ground truth extraction: all cross-references parsed from the journals —
  668, of which the 379 landing on held targets are tabled with their
  journal-side anchors; the letter recipients tabled — 41 rows, `RECON.md`'s 43
  heading strings with the three carrying a footnote marker collapsed as
  apparatus (`docs/m0-check-suite.md`);
- the **answer key**: the cross-references cite pages of editions the corpus
  does not hold, and `RECON.md` §4 read that as needing adjudication rather
  than lookup. **That premise was wrong** — the cited editions are digitized
  page by page, so the target side is a page lookup plus an alignment between
  two printings of one book. The key resolves **348 of 379** links by
  requiring two independent editions to agree, and uses no part of the
  retrieval system it will be used to score
  (`docs/answer-key-protocol.md`, issue #9). Neither the hand-resolved pilot
  nor the re-scoping escape hatch was needed;
- `memoria rebuild` over the derived state that exists so far, and
  `memoria validate` (IDs, links, raw-file hashes) — both grow at every later
  milestone;
- a mechanical check-suite reconciling the normalizer against `RECON.md`:
  date headings, 130 letters, recipients, footnote and bracketed-span counts,
  and sampled evidence records containing no editorial voice. `RECON.md` is
  reconnaissance, not ground truth: the suite re-derives each count and asserts
  the verified figure with RECON's stated alongside it, so four of the five
  reconcile as documented deviations rather than as equalities — 558 date
  headings, not RECON's 448; 41 recipient rows, not 43. Every deviation found is
  an addition. The table, and the map from each M0 mismatch to the regression
  test that catches it again, are in `docs/m0-check-suite.md`.

### Gate

Open a normalized journal entry. Its text carries no 1906 voice; its apparatus
is linked alongside it; its date says how it was resolved.

Pick an entry inside a multi-year chapter (`1845–1847`) and see the weekday
resolve its year exactly.

Delete the index and rebuild it without losing anything.

The check-suite passes, and every mismatch it caught on the way is now a
regression test (§43).

---

## M1 — The Tool Surface and the First Number

Build:

- the MCP server, exposing the minimum of §25 this gate needs: `search_text`
  over FTS5 and `read(ref)` over the §4 stable IDs — verbatim source text,
  never a summary in its place, with a raw undecorated full-source read
  available (poc-plan §7's superset-of-grep constraint);
- the `events.jsonl` read ledger: every served read recorded (§10.4, §33);
- the benchmark harness, reporting all three slots: **retrieval recall@10**
  over the answer key measured; gathered-set recall and the promotion miss
  rate printed as *not yet measurable*. The harness spec also defines the
  **link-to-entry mapping** that makes gathered-set recall well-defined —
  which entries the cross-referenced passages are held to belong to — rather
  than leaving M2 to improvise it;
- **pre-registration**: before M2 begins, the harness records what its three
  numbers will decide and how — the embeddings go/no-go procedure (§45) is
  written down while the numbers do not yet exist, so the decision cannot be
  rationalized after the fact.

The evidence-read routing hook already exists; this milestone is what makes the
routed path the path of least resistance — the tools return more than a raw
read does.

### Gate

From Claude Code, ask a question about a journal passage. Every evidence read
arrives through the tools and lands in `events.jsonl`.

Run the harness and read the first real number. FTS5 is expected to score
poorly on paraphrase links (poc-plan §3); the point of this gate is that the
number exists before anything heavier is argued for.

---

## M2 — Subjects, Candidates, and the Index Maintainer

Build:

- the five built-in subjects with their prompts — match definition, matching
  hazards, audit questions (part 06 §8.1). People's hazards carry `RECON.md`'s
  four Thoreaus sharing a surname and Emerson under four location forms;
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
- harness numbers two and three: **gathered-set recall** over the links, under
  M1's link-to-entry mapping, and **promotion miss rate** against the 43
  recipients. Ground truth exists only where `RECON.md` supplies it — the
  recipients table is People-scoped — and the numbers claim no more than the
  mapping and that table cover.

### Gate

Promote Emerson. The entry materializes with its gathered set already built;
add his four location forms as match terms and watch the set complete.

Exclude a wrong Thoreau from an entry's gathered set, run `memoria rebuild`,
and see the exclusion survive.

The harness prints three real numbers. **With all three in hand, the embeddings
decision (open-problems §2.2) is taken by the procedure pre-registered at M1 —
the only mechanism decision this build order schedules.**

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
authorship-track piece** (open-problems §4.1 and §6; the likely subject is
Thoreau's revision practice, poc-plan §1). Deciding it here rather than at M5
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

Import a Walden chapter as legacy manuscript. It gets an unconfirmed brief and
a not-current tint; no model pass runs unasked.

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
coordinator stays a stale-revision check. Embeddings enter only if the M2
numbers say so.

Also deliberately unsequenced: acquiring *Excursions*, *Cape Cod* and *The
Service* (would lift harness coverage from 58%; nothing forces it), the in-app
prose editor (open-problems §1.2), editability of built-in subjects (§1.3),
late-subject backfill (§1.5), and everything about the real archive —
including whether its sources live inside the repo (§1.4). Those wait for
observed need, under §45.

---

## What each milestone forces

| Milestone | Decision forced |
|---|---|
| M0 | the normalized record schema, the editorial-apparatus representation, and the answer-key adjudication protocol (open-problems §6, `RECON.md` §4) |
| M1 | exact signatures of `search_text` and `read(ref)`; the link-to-entry mapping behind gathered-set recall; the pre-registered embeddings decision procedure. The rest of §25's tool list stays open |
| M2 | at its gate: embeddings, go or no-go, by the procedure M1 registered (§45, open-problems §2.2) |
| M3 | nothing open — it builds what earlier decisions already settled |
| M4 | at its start: the authorship piece's subject and length (open-problems §4.1, §6) |
| M5 | nothing new — it spends decisions forced earlier |

---
