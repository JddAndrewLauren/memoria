# The extraction is the subject system's candidate engine

The plan excluded GraphRAG from its first line — part 02 §1.11 "do not build GraphRAG
because global retrieval might theoretically fail", part 17 §45's observe-a-failure
gate, part 03's non-goal. On 2026-09-01 the Thoreau corpus and its harness were retired
and `open-problems.md` §2.2 conceded the gate had no instrument left. The question was
re-grilled the same day, before M1 and M2 hardened a shape that could not carry it. What
the grilling found was not a retrieval gap but a **candidate gap**: part 06 §8.4 only
ever described capitalized-name candidates with a recurrence filter, §8.11 admitted
Themes and Arcs have no match terms that work, and nothing in the plan proposed a Theme,
gathered for one, or answered §29's "patterns the author has not yet thought to ask
about". We decided that a GraphRAG-style **extraction** — a model reading every paragraph
for the entities, relations and clusters it contains — becomes the **one** candidate
engine for every subject, replacing the lexical pass, and that **extracted entities are
entries**: a subject is an entity type plus the audit questions it asks, and an entry is
what an entity becomes when promoted. The subject system is unchanged in shape; it gains
an engine underneath and a per-subject `auto-promote` switch.

## The decisions

1. **Entities are entries.** No second node set. The `SUBJECTS` tree the author sees is
   a surfacing of extracted entities, promoted or not. Everything an entry carries that
   an entity cannot — testimony, settlements, pins and exclusions, match terms, and at
   subject level the audit questions — stays exactly where part 06 puts it. A subject
   reduced to a *view* over entities was considered and rejected: those five things are
   the manuscript loop, and Themes in particular hold the author's reading (§8.1), which
   no machine description can hold.

2. **One engine.** The extraction replaces #17's regex candidate pass rather than
   sitting beside it. Two engines writing the same candidate rows would have to agree on
   identity and recurrence, and the lexical one would be strictly less useful to the
   alias store than the model. What stays lexical and model-free is **gathering**: a
   promoted entry's set is derived deterministically from its match terms. The cost is
   that a fresh archive shows no candidates until the author runs the extraction once.

3. **Runtime.** The extraction is an author-launched Curator act, run inside a Claude
   Code session as a skill over the tool surface, in the same class as the audit. It is
   memoized per paragraph on `hash(paragraph) + hash(extraction prompt) +
   hash(subject prompts)`. **Match terms are not in the key**, so accepting a term never
   re-reads the corpus. Part 08 §12.1's rule — nothing that needs a model runs unasked —
   and poc-plan §3's rule — no model-driving service — both hold. Bringing forward the
   §24.5 API fallback for a scheduled batch, and a local model run freely by the
   maintainer, were both rejected: the first is the first unasked model and the first
   metered spend, the second lowers extraction quality where part 05 §7 punishes it.

4. **Identity: the model proposes, match terms decide.** The extractor is handed the
   subject prompts (with their hazards) and the promoted entries' names, and records per
   paragraph which entries it believes are mentioned (**placements**), which surface
   forms it could not place, and the **relations** between them. The durable mapping is
   recomputed at rebuild from match terms, deterministically. A placement that match
   terms do not license becomes a **proposed match term** on the entry, which the author
   accepts or rejects; until then the mention is unplaced. This is #17's existing seam —
   "ingest populates match terms, the author owns what stays" — fed by a model instead
   of a regex. Part 05 §7 is unchanged: one alias store, ambiguity surfaced rather than
   resolved. "The model's placement is the placement" was rejected as the exact
   misidentification path §7 forbids, with a full-corpus re-read as its only correction.
   "Surface forms only, the model never places" was rejected as weaker than the lexical
   ingest it would replace.

5. **Promotion is declared per subject.** The subject prompt carries a fourth line,
   **auto-promote**. Off means candidates above the recurrence filter wait, ranked, for a
   one-key promotion; on means they become entries with an empty overlay and the author
   demotes what is wrong. Themes and Arcs default off, because a wrong entry there is in
   Tier 2 and the audit until noticed; a subject like Locations may turn it on. §8.4's
   "nothing promotes itself" becomes "nothing promotes itself unless its subject says
   so", stated locally by the subject in §1.10a's sense.

6. **Themes and Arcs gather by co-occurrence.** On promotion from a cluster, the entry's
   match terms are seeded with the entries and relations that defined the cluster —
   `Bob`, `the acquisition`, `Bob -> pressures -> author` — and thereafter it gathers the
   paragraphs where those co-occur, joined over placements. Deterministic at rebuild,
   no model, and the author tunes a Theme the way they tune a person: by editing its
   match terms. A promoted entry never points at the cluster it came from, because
   cluster identity does not survive re-clustering. **Relations are derived index rows
   only** — read by gathering, `backlinks()` and the global tool, never durable, and
   never loaded into working context: Invariant 1's ban on transitive expansion stands.

7. **One global tool, both halves now.** `search_global(query, filters, summarize=false)`
   returns paragraph references grouped by cluster with a §33-style scope line; with
   `summarize=true` it also returns the cluster's synthesized text, marked `[inferred]`
   and never served as evidence. Every call is ledgered with the mode that ran. The
   refs half is candidate-flow infrastructure — how the author inspects a cluster before
   promoting it. The summary half is the part §1.11 and §45 gated behind an observed
   failure, and **the author chose to ship it now**, with the concern stated at the time:
   this reverses §1.11 and §45 for GraphRAG outright rather than amending them, and
   §43.11's distributed-pattern set becomes a regression suite that gates nothing.
   Recorded as a chosen cost, not papered over.

8. **Vocabulary.** *Extraction*, *placement*, *cluster*, *relation*, *auto-promote*;
   *entity* joins Entry's avoid list. GraphRAG's own words — entity, relationship,
   community — were rejected because they would put two words beside every one of ours.

## Consequences

- Part 06 §8.4 and issue #17 are rewritten: candidates, placements, relations, clusters
  and proposed match terms all come from one pass; the recurrence filter runs over its
  output; rejected candidates stay enumerable. #16 gains the auto-promote declaration;
  #18 gains co-occurrence gathering and match-term seeding on promotion; #19 is
  unchanged in scope but says why appearances for Themes still wait for M5 while
  gathering does not.
  `search_global` is #74; the §43.11 set, now a regression suite, is #75.
- §1.11 loses its GraphRAG sentence and §45 loses GraphRAG from its list. The
  failure-first process stays for everything else on that list — embeddings included,
  which this decision does not touch (`open-problems.md` §2.2).
- The one number the plan owes and cannot yet produce is unchanged: gathered-set recall
  needs a corpus. The extraction adds a second unmeasured recall — placement recall — and
  the same structural mitigation applies: unplaced surface forms stay enumerable.
- §42's rebuild list already named "entity enrichment", "dependency graph" and
  "provenance graph" as derived state. This ADR is what fills those entries.
