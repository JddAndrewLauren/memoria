# Model calls enter by choice, and the session stays the default

The author asked that the backend and the MCP server be allowed to call a model
directly - with the switch for it, and the API key it calls with, kept in the Settings
dialog ADR-0009 built - and that, for now, it not be the default.

Until this decision the system held one rule about generative models in three places:
`../poc-plan.md` §3 ("no model-driving service"), `../tool-surface.md` ("**No adapter
can call a model**... There is no `generate_` anything"), and ADR-0005 decision 3, which
considered exactly this - "bringing forward the §24.5 API fallback" - and rejected it
as "the first unasked model and the first metered spend". Every pass that needs a model
is a *conversation*: the extraction (ADR-0005), the audit (#40) and the writing-style
analysis (ADR-0009) each serve text out through a tool and take structured results back
as tool arguments, with the loop written in skill prose and the Claude Code session
doing the reading. The rule is enforced by an AST sweep over the core, a
socket-monkeypatch test around the whole derive-and-summarize loop, and a denylist over
the client's dependencies.

_Contradicts ADR-0005 decision 3 and `poc-plan.md` §3 - reopened because the author
asked for it, and because the two reasons ADR-0005 gave do not survive the shape
below._ "Unasked" is a trigger question, and the trigger does not change: a direct run
still happens only from a button or a tool call the author asked for, and part 08
§12.1's "nothing that needs a model runs unasked" holds as written. "Metered spend" is
a cost question, and part 13 §24.5 already said how an API backend must answer it:
"explicit and configurable... the author should be able to tell whether a task is using
subscription capacity or metered API usage." What §24.5 did not say was that the
subscription-backed session must stay the way the system works when nobody has chosen
otherwise. That is the decision.

**We decided that** the backend and the MCP server may call a generative model
directly, **off by default**, switched on by the author under Settings > Model, with the
key stored on the machine and never in the repository; that each of the four passes
keeps its serve/record shape and gains one *driver* over it, so the mechanism changes
(who executes the loop) and nothing about what is stored does; and that every metered
call is a ledger line. A pass Memoria executes this way is a **direct run**; the
skill-driven pass is a **session run**, and it stays the default.

## The shape

- **One seam, `memoria.model`.** The one core module allowed to import a model SDK, and
  it imports it lazily, inside the provider function. Everything that needs a model
  takes one as a plain callable (`ModelFn`: one request in, one reply out), the
  substitution point `memoria.embeddings` already offers with `EmbedFn`. Part 13 §24's
  `ModelBackend` / `AnthropicAPIBackend` vocabulary arrives as a function, not a class
  hierarchy: a second provider is one more function. The AST sweep in
  `tests/test_extraction.py` exempts exactly this module and holds it to that shape.
- **The settings are machine-local.** `.memoria/model.json`, beside `index.db` under
  the gitignored index directory, holds the switch, the model id and the stored key;
  written with mode 0600 directly, not through `memoria.write` - ADR-0003 governs
  durable files a commit closes, and a credential must never be one. `ANTHROPIC_API_KEY`
  in the server's environment overrides the stored key and never touches disk. No
  surface ever returns the key; `Readiness` says whether one is set and where from.
- **`require_model` is the point of use**, in the shape of `require_evidence_root`: a
  run that cannot happen refuses with a message naming Settings > Model. Off, no key,
  or no SDK all refuse there and nowhere earlier - an install without the `llm` extra
  starts and serves everything that is not a direct run.
- **Four drivers, one module (`memoria.drivers`).** Each calls the same `brief`,
  `pending_*` and `record_*` core functions its tools call, in the skill's order, with
  the model between the serve and the record. The prompts are served verbatim - they
  are hashed into every memo key - and every reading passes the core's own validation
  in `record_batch`, `record_audit_batch` and `record_observations`. The JSON schemas
  the replies must satisfy mirror the tool-argument dataclasses and are in no memo key.
- **Every call is bounded; every run is resumable.** One driver call makes at most
  `limit` model calls and returns a report, so a button or a tool loops and shows
  progress, and "what is left" stays a query over what is absent. A refused, truncated
  or off-schema reply is one rejected item in the report and the run goes on; a
  provider failure stops the run with what was recorded kept. No server-side fallback
  model: a refusal on archive text is a visible rejection, not something re-run
  elsewhere unannounced.
- **The tools and the routes.** `model_status`, `extraction_run`, `audit_run` and
  `style_run` on the MCP server; `GET`/`PUT /api/model`, `GET /api/extraction`,
  `POST /api/extraction/run`, `POST /api/sections/{id}/audit` and
  `POST /api/style/analyse` on the app. Each is `require_model`, one driver call,
  render - the adapters still hold no model. The extraction and writing-style skills
  ask `model_status()` *after* the author's go and hand the pass to `*_run` only when it
  is ready; they never tell the author to switch direct runs on.
- **Spend is ledgered per call**, as a `model_call` line naming the pass, the model
  that answered and its token counts - part 13 §24.5's requirement, made mechanical.
  The line carries no `served` key, so the supplied-context account never reads it as
  a served read; what entered the model's context is ledgered by the same brief, batch,
  summary-task and read lines a session's tools write, which the drivers write too.
- **The UI gates on readiness.** Settings gains a Model row; Review, the Section view
  and Writing style gain a Run button only when `GET /api/model` says ready, and keep
  their "run one from a session" wording otherwise. The client still holds no model
  dependency (`tests/test_ui_dependency_boundary.py` stands): every button posts to the
  backend, which holds the seam.

## Considered Options

**MCP sampling** (the server asking its client to run the model). Rejected: it spends
the same subscription capacity the session already spends, gains nothing over the
skill-driven loop, and gives the app no route at all - the app has no MCP client.

**A background service or a queue** for the long extraction. Rejected: `poc-plan.md` §3's
objection was always to a service driving a model behind the author's back, and
`tests/test_audit.py` forbids scheduler and background-task machinery outright. Bounded,
resumable steps the surface loops over give the same progress with no process to babysit.

**A key in the OS keyring.** Rejected for this slice: a dependency that behaves
differently headless, on WSL and on the production machine, for a file the index
directory's existing gitignore already keeps out of every commit. The environment
variable remains for anyone who wants the key nowhere on disk.

**Storing the key in the repository's settings files through the write path.** Rejected
without discussion: a credential in a durable, committed file is the one thing this
design must never produce.

**Making direct runs the default once a key is present.** Rejected: a key alone is
capability, not consent. The switch is separate from the key, off by default, and the
readiness line says which of the two is missing.

## Consequences

- Metered spend now exists in the system, opt-in, and every unit of it is a line in
  `sessions/**/events.jsonl` the author can count.
- **When switched on, archive text leaves the machine**: every paragraph of a direct
  extraction, the manuscript prose and gathered evidence of a direct audit, and the
  author's own samples in a direct analysis go to the provider. Part 17 §48 said
  "privacy, billing, and source-upload policies are configuration decisions rather
  than architectural assumptions"; this is that configuration, and the Settings panel
  says so beside the switch. ADR-0007's "nothing leaves the machine" still holds for
  embeddings, which stay local.
- `tests/test_extraction.py`'s sweep exempts one named module; `tests/test_audit.py`'s
  list of files that may record a judgement gains `drivers.py`. Both are deliberate
  edits with this ADR as their reason.
- The `llm` extra (`anthropic`, major pinned) is the core's second non-trivial runtime
  dependency after ADR-0007's; `dev` pulls it so the seam's tests run against a fake
  SDK and never open a socket.
- The direct audit run ledgers a `model_call` line and the gathered reads it inlines,
  where the session-driven audit tools ledger nothing (`../tool-surface.md`); the app
  mints one ledger session per server process for this, as the stdio server does.
- Curation stays a session run: the record extractor reads a transcript and proposes
  records for the author to confirm in conversation, and nothing about a direct run
  fits that shape. Ask Memoria (`../open-problems.md` §2.1) stays deferred; a driver now
  exists that it could one day use, which is not a decision to build it.
- Invariant 13 (the model runtime is replaceable) holds: the seam is a callable, no
  durable state names a provider, and the session run is unchanged.
- `../open-problems.md` §5 carries the cost: an author leaving direct runs on without
  noticing the spend, or a pass the session would have done better.
- **Revisit if** the first direct extraction of a real archive shows the bounded-step
  loop is the wrong grain (too many round trips, or a step the app cannot wait for);
  the Batch API named as ADR-0005's flip is the next shape, behind the same seam.
