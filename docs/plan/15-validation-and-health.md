<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 23, 43, 47 of the original memoria-plan.md -->
<!-- §43.14 added 2026-08-31: the benchmark harness's three numbers. -->

# 23. Provenance Validation

Provenance should be mechanically testable.

A command such as:

```bash
memoria validate
```

checks for:

- unresolved source IDs;
- broken links;
- missing transcript turns;
- missing change records;
- `[source]` assertions without sources;
- `[author]` assertions without author records;
- `[inferred]` assertions without a basis;
- AI manuscript writes without an identifiable authorization — **including writes to a
  brief**, which is manuscript-class and has an AI write path of its own (§2.1);
- derived summaries that introduce unsupported claims — the one check here that
  needs a model; it belongs to a requested audit rather than to `memoria validate`'s
  mechanical pass (recorded 2026-08-31);
- provenance chains that terminate in another derived artifact instead of original material.

Curator commits should fail validation when they introduce malformed provenance.

This converts attribution from a best practice into an architectural invariant.

---

---

# 43. Evaluation Suite

A small adversarial test suite begins early and grows from real failures.

The evaluation suite exists primarily to validate Memoria's central promise: that a model can work accurately across a corpus much larger than its immediate context without losing provenance, silently narrowing scope, or substituting remembered summaries for evidence.

## 43.1 Large-corpus reasoning test

Can Memoria answer questions whose evidence is distributed across material that cannot fit into a single model context?

The test should verify that it:

- assembles useful initial context;
- searches beyond that context when required;
- expands important hits to full source records;
- distinguishes searched from unsearched material;
- preserves citations to terminal evidence;
- and avoids claiming corpus-wide certainty when retrieval was incomplete.

## 43.2 Resumption test

Can Memoria resume a section after a long absence — from its **brief**, its draft and
an audit on request, with no stored checkpoint to read? See part 12 §39. Nothing in the
Thoreau corpus exercises this; only the authorship track can.

## 43.3 Date-leakage test

Does later hindsight contaminate questions about earlier beliefs?

## 43.4 Confirmation-bias test

When asked to prove something, does research actively seek contrary evidence?

## 43.5 Alias test

Can retrieval find evidence across multiple names for the same person without making unsafe merges?

## 43.6 Sparse-evidence test

Can the system correctly answer that evidence is insufficient?

## 43.7 Attribution test

Select random `[author]`, `[source]`, and `[inferred]` statements.

Can each be traced to legitimate terminal provenance?

## 43.8 Broken-link test

Do all cited source, session, and change references resolve?

## 43.9 Human-edit test

Can Memoria identify when an important interpretation changed and display the exact diff?

## 43.10 Curator-restraint test

Does exploratory author conversation remain exploratory instead of becoming accepted interpretation?

## 43.11 Distributed-pattern test

Can agentic retrieval identify patterns requiring evidence distributed broadly across the archive?

## 43.12 Manuscript-authorization test

Can Memoria propose a manuscript rewrite autonomously while refusing to apply it until explicit authorization exists?

## 43.13 Scope test

If the author authorizes one paragraph, does Memoria leave unrelated manuscript prose untouched?

## 43.14 Benchmark harness — three numbers

The machine-scored track's harness is built early (`poc-plan.md` §3) and reports
three numbers:

- **retrieval recall@10** over the 348 cross-references the answer key resolves
  (`docs/answer-key-protocol.md`) — the number that decides whether embeddings
  get built (§45), and one to read as a stress case rather than a threshold
  (`open-problems.md` §2.3);
- **gathered-set recall** — a set metric: whether an entry's gathered set is
  complete enough to write from, the silent recall risk of part 06 §8.3 and part
  11 §33.1;
- **promotion miss rate** — the promoted set scored against `RECON.md`'s 43 known
  letter recipients, since the ≥5-recurrence filter admits at most 36 candidates
  (part 06 §8.4).

Every consequential real-world failure becomes a regression test.

---

---

# 47. Health and Drift Detection

Memoria should periodically be able to report:

- sections not worked on recently;
- **paragraphs, sections and chapters that are not current**, and why — never audited,
  edited since, or touching an entry that has changed;
- sections whose brief is still **unconfirmed**;
- old unresolved questions;
- themes with substantial new evidence but no recent review;
- arcs whose cached judgements have gone stale against recent manuscript changes;
- human/Curator conflicts;
- unsupported interpretation statements;
- broken provenance;
- unprocessed source additions;
- research projects left incomplete;
- manuscript passages affected by changed chronology, themes, arcs, claims, or source
  status — which is the staleness map, not a scan.

This is a health report, not an approval queue.

**Everything in it is computed without a model** — hash comparisons, git facts and
mechanical validation — which is why it may run autonomously even though the audit
(Invariant 8, as amended) may not. It reports what has gone stale; it does not form an
opinion about the prose.

---
