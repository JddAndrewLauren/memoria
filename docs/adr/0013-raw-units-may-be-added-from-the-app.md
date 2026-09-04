# Raw units may be added from the app

Until 2026-09-04 a raw unit entered the archive one way: a file appeared under
`{evidence_root}/raw/` because the author copied it there by hand, and the next
`memoria normalize` numbered it (ADR-0006) and converted it. The SOURCES tree's empty
state said as much - "run `memoria normalize` against an evidence root". The author asked
for the step before that to be one act in the app: pick files, pick a folder, or drop
either onto the window. **We decide that the web adapter may place a raw unit's bytes
under `raw/`, at the relative path the author's pick or drop gave it, never overwriting
and never numbering.**

## The shape

- **One route, `POST /api/ingestion/units`, one file per request.** The body is
  `{path, content}` - the path relative to `raw/`, forward-slash, keeping the folder a
  drop came from; the content base64 in a JSON body, as `POST /api/style/samples` already
  does and for the same reason (no form encoding on the client, no extra dependency on
  the server). The core function `memoria.ingestion.add_raw_unit` owns the write; the
  route maps its outcomes to status codes and computes nothing (ADR-0004).
- **Never overwritten.** A path already taken is a 409 and nothing is written - the same
  rule `write.create` keeps for durable files. Re-dropping a folder is a row of 409s, which
  is the right answer.
- **Never numbered here.** The manifest is not touched. The ledger mints on first sight
  (ADR-0006), so the next normalize pass numbers the unit, in the order it always would.
- **Not a durable write.** `raw/` is Original state outside `write.DURABLE_PATHS`, the
  evidence root may sit outside the book repository, and nothing is committed - the
  posture `normalize` already takes when it materializes an email attachment into `raw/`.
  So no staleness token and no actor: the upload is not an ADR-0003 write.
- **Not local-only.** The bytes travel, so this works hosted and on a phone (ADR-0002).
  Only the follow-on normalize is local (ADR-0011); the app runs it automatically when
  `/api/locality` says it may, and otherwise tells the author a normalize is still needed.
- **Refused at the boundary.** A path that is absolute, climbs out of `raw/`, names a
  dotfile or folder (the ledger numbers *every* file under `raw/`, so a `.DS_Store` would
  hold an id forever), or is the ledger itself is a 400. A file over 64 MB is a 422 -
  higher than a style sample's 8 MB because scanned PDFs are large, still a cap so a
  stray upload is refused rather than held.

## Options considered

- **Multipart upload.** Rejected for the reason `SampleUpload` gave: the JSON body needs
  nothing new on either side, and one file per request keeps error reporting per row.
- **A server-side folder pick** ("here is a path, go read it"). Rejected: it needs a native
  dialog the browser does not have and a locality condition ADR-0002 forbids.
- **Normalize inside the upload route.** Rejected: it would couple a hosted-safe write to a
  local-only pass. The client sequences the two.

## Consequences

- The write-route list in `tests/test_web_app.py` grows by exactly this path, with this
  ADR as its reason.
- The SOURCES tree and the Ingestion page each carry an "Add sources" action, and the
  window accepts a drop anywhere.
- Revisit if the per-file cap bites or a whole-archive drop is too slow one request at a
  time: chunking or a batch route would be the next shape, not a change of rule.
