# The supplied context is inspectable, but never manageable

Invariant 1 says the author does not manage context windows, and part 14 §40 banned
context manifests from the interface — yet part 11 §33.1 obliges assembly to report what
it resolved, and nothing discharged that obligation. We resolved the contradiction by
separating **managing** from **inspecting**: Memoria exposes a **supplied context**
surface reporting, for one session, the working context assembly produced and every read
served since — opened deliberately rather than watched, stating countable domain units
rather than tokens, and naming anything a budget truncated. Invariant 1 stands unamended,
because nothing on that surface asks the author for a decision, a threshold or an action.

## Considered Options

**What is being measured.** The author's request was for the *context window*. Rejected:
Memoria is an MCP server (part 13 §24, reduced) and cannot see Claude Code's window —
a percentage assembled from Memoria's half of the picture would be a confident number
that is wrong, which is the failure §33 exists to prevent. We measure what Memoria itself
assembled and served.

**Snapshot or running account.** An assembly-only snapshot is exactly true forever and
is immune to the drift below. We chose the **whole session** — assembly plus every read
served since — because the retrieval half is most of what a long session sees, and a
report that stopped at assembly would under-describe "by what". The price is recorded in
`../open-problems.md` §5.

**Gauge or omission report.** A fullness gauge (`184k / 1M`) was rejected outright: a
number the author can watch is a number the author will optimise against, which is the
workflow §1.1 exists to abolish. The quantity that matters is not fullness but
**omission** — a budget reached and something loaded only in part. A gauge reports a
number you must interpret; an omission report states a fact you must act on, and is
silent when there is nothing to say.

**Where tokens live.** Token counts are needed — `../poc-plan.md` §6 risk 1's
budget-capping experiment cannot be run without them. Rejected: a developer toggle in the
UI, which is one left-on switch away from being the product. They live on the context
manifest (§33) and are read from the file. The separation is a file boundary, so there is
no code path from the instrument to a screen.

**Watched or opened.** Steering behaviour is caused by peripheral visibility, not by the
data. The surface is therefore opened deliberately, live only while open, and its opener
carries no count — a count on the opener would be the always-on panel with an extra click
in front of it.

## Consequences

- **Part 14 §40 is amended**, not Invariant 1. The §40 sentence was already false: it
  bans "retrieval mechanics" while §40.7, three subsections below, specifies the streamed
  activity log. The amendment records both exceptions and keeps the ban on token budgets
  absolute.
- **The account can be stale in one direction.** `events.jsonl` records reads Memoria
  served; it cannot record what the client compacted away. The surface therefore claims
  only what Memoria **supplied** and never what the model holds. The wording is
  load-bearing, not decorative — this is why the term is "supplied context".
- **Its PoC home is the Section view**, built with assembly at M5. The semantically right
  home is beside the §19.2 scope note, which discharges §33 for the search half; that
  opener is deferred with Ask Memoria, which the PoC never builds.
- **M5's gate grows a clause.** "Assembly reports what the scope resolved to" now
  requires opening the surface and finding a fallback to an unpromoted candidate named
  there.
