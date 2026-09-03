# The web adapter may launch a model-free derived-state pass, locally, one at a time

Until 2026-09-03 the web adapter (ADR-0002) never ran a pass. Its writes were the
author's own acts through the write path (ADR-0003) and one local convenience, "Reveal in
editor"; every pass — `memoria normalize`, `memoria rebuild`, the extraction — was
launched from the CLI or from a Claude Code session. The ingestion status surface
(`/ingestion`, part 19 §19.1) makes ingestion verifiable, and the author asked that it
also make ingestion *simple*: the two passes that need no model should be one click from
the page that shows their result. **We decide that the web adapter may launch a
model-free derived-state pass: normalization and the index rebuild, on a local
connection only, synchronously, under one lock, with no embedder.**

## The shape

- **Two routes, `POST /api/ingestion/normalize` and `POST /api/ingestion/rebuild`.** Each
  runs the same core function the CLI runs (`memoria.normalize.normalize`,
  `memoria.index.rebuild`) and returns that pass's own report as counts. The adapter
  computes nothing: `memoria.ingestion.run_normalize` and `run_rebuild` own the run, and
  the route maps their outcomes to status codes.
- **Local-only, the same check as reveal.** The server refuses a non-loopback peer with a
  403 whatever the client claims; the buttons are absent, not disabled, when
  `/api/locality` says the browser is elsewhere (ADR-0002's one locality condition,
  reused rather than duplicated).
- **Synchronous.** The request blocks until the pass finishes and the response is the
  report. On the gate corpus this is seconds; on a real archive it is minutes, and that
  is accepted for now — a job with progress is the revisit below, not a reason to ship
  nothing.
- **One process-wide lock, both passes.** A second click while either runs is a 409,
  named as such to the author. A rebuild reads the records a normalize writes, so they
  must not overlap either.
- **No embedder.** `run_rebuild` passes `embed_fn=None`: embeddings enter by choice
  (ADR-0007) and the CLI's `memoria rebuild` stays the only path that loads the model.
  The page says so beside the button. The `changes/` projection (ADR-0008) likewise
  stays with the CLI.
- **The extraction is not launchable here.** It needs a model, and nothing that needs a
  model runs unasked (ADR-0005): the page reports how much of each record the extraction
  has read, and the author starts one from a session.

## Why this is not a durable write

Normalized records and the index are Derived state (part 04 §42, ADR-0003's
`DURABLE_PATHS` excludes `sources/normalized/`): rebuildable, asserting nothing, outside
the write path. A pass needs no staleness token and commits nothing, and the adapter's
isolation tests still hold — it opens no file and no database, and the one write-route
list they pin grows by exactly these two paths.

## Considered Options

**Stay read-only; the page tells the author which command to run.** The grain of every
other surface, and what the plan's empty states already do. Rejected by the author on
2026-09-03: the point of the surface is that ingestion be simple as well as verifiable,
and a page that shows a failed unit and then sends the author to a terminal is half of
that.

**One button that runs both passes.** Rejected: one long request carrying two reports,
and a normalize that finds nothing changed still pays for a full rebuild.

**A background job the page polls.** The right shape for a 4,000-record archive, and
the revisit below. Rejected for now as job state, progress hooks in `normalize` and a
second route for the price of a synchronous request that is honest about being one.

**Letting the rebuild embed.** Rejected: it would load a model in the web process on
every click, against ADR-0007's "by choice", and make the fast button the slow one.

## Consequences

- The web adapter's write-route list, pinned in `tests/test_web_app.py`, names the two
  run routes with this ADR beside them; a third pass launched from the web must add itself
  there and say why.
- `memoria.ingestion` is on the adapter's import allowlist; it is the one module a run
  reaches, and it holds the lock.
- **Revisit if** a real archive makes the synchronous request untenable (a background
  job with progress, still under one lock), or if a surface wants to launch the
  extraction — which would be a different decision, not an extension of this one.
