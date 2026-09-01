# The UI is a React client over a JSON API, not server-rendered templates

M3 builds Memoria's first reading surfaces, and part 19's design already exists as a
Claude Design canvas. Its `.dc.html` source is a Jinja-family template dialect —
`{{ prop }}`, `<sc-if>`, `<sc-for>`, 360 inline `style` strings and no CSS classes — and
DesignSync's round trip exchanges HTML files on disk. That evidence points squarely at
server-rendered Python templates. **We chose React anyway**: a Vite + TypeScript client
over a JSON API served by FastAPI, delivered in a browser at `localhost`, with the canvas
demoted from source to reference. The choice buys frontend idioms that are stable and
densely represented — this repo is built by agents, and htmx 4.0 landed on 2026-08-28
renaming every event and inverting attribute inheritance — plus the natural home for a
streamed conversational surface if Ask Memoria's deferral ever lifts. It pays for that by
making every canvas iteration a transcode, and by adding a second language, a build step
and a second test runner to a repo that had one command.

Two constraints bound the decision. The app is **delivered in a browser**, because the
plan's post-PoC direction is a web/API service (§40.1-40.2) and a localhost web app is
that artifact with auth and HTTPS removed, exactly as `../poc-plan.md` §5 removed them.
And **hosting it later — cross-platform, phone included — is a design constraint on M3**,
not a deferred option: no surface may depend on the browser and the repository sharing a
machine.

## Considered Options

**Server-rendered Jinja/JinjaX + htmx.** The strongest rejected option, and the one the
artifacts predict. `{{ ch.expanded }}` is valid Jinja character for character; `sc-for`
is `{% for %}`; the 360 inline styles survive verbatim where JSX would rewrite every one
into an object literal. A rendered JinjaX partial *is* a DesignSync preview file, so the
canvas round trip stays a one-language loop in both directions. It also makes #25's
flagship interaction structural rather than managed: under htmx the main column is never
re-rendered, so the slide-over cannot cost the reader their place. Rejected on the
judgement that stable idioms and the Ask Memoria option are worth more than the round
trip — an explicitly close call, recorded here because a future reader will otherwise
assume the canvas was never consulted.

**The canvas as a source, via a `.dc.html` -> `.tsx` transcode script.** Rejected: it
means maintaining a compiler for an evolving dialect we do not control, whose output is
360 generated style objects nobody will hand-edit. The result is neither a clean codebase
nor a clean canvas, and every canvas change threatens hand-tuning downstream. The canvas
is where new screens are explored; the app is where they are built.

**Publishing our components back to the canvas (DesignSync reverse-flow).** Not rejected
— deferred. Rendering real components to static preview HTML with `@dsCard` markers is
the genuine round trip under React, but it is only worth building once a component
library exists that is worth publishing, which it does not at M3.

**The UI as an MCP client.** Rejected on shape. `read(ref)` serves a model verbatim
source text, never a summary in its place; the Source viewer needs structured fields —
`date_confidence` and how it resolved, record class, the temporal badge row, paragraph
anchors as data, backlinks. Proxying would put a model-facing protocol in the rendering
path permanently and leave the UI parsing prose back into fields.

**Direct SQLite and file reads from the view layer.** Rejected as the duplication §40.1
exists to forbid; it would drift inside a single milestone.

**A committed build bundle.** Rejected. It would buy a one-command run on a machine
without node, at the cost of putting a generated artifact under version control in a repo
whose discipline is that derived state carries no authority and can always be thrown away
(§42). `memoria rebuild` exists to prove that rule; this would be its first exception,
for convenience alone.

**Open original as an editor launch.** Rejected as the *primary* meaning. Its job, per the
M3 gate, is to show that normalization invented nothing, and serving the raw bytes in a
browser pane discharges that from anywhere — including a phone. An editor launch is a
local convenience and the one thing in the design that breaks when hosted.

## Consequences

- **One core, thin adapters.** Domain logic stays in `memoria.*`; the CLI, the FastAPI app
  and the MCP server are all thin over it, and the HTTP layer holds no domain logic. This
  is the first concrete discharge of §40.1, which until now had exactly one adapter.
- **TypeScript types are generated from FastAPI's OpenAPI schema.** Two languages that can
  drift silently is this decision's structural cost; generation converts drift into a
  compile error. It is the mitigation that makes the choice safe, not an optimisation.
- **Author reads are not ledgered.** `events.jsonl` records what Memoria served to a
  session (§10.4). The UI reads through the same core — there is no second read path — but
  reading is not serving. Ledgering author browsing would make M5's supplied-context
  surface report the author's own clicks as context supplied to a model, which is the
  confident-but-wrong number ADR-0001 says §33 exists to prevent.
- **No surface may acquire a client-locality condition.** Everything works hosted and on a
  phone. "Reveal in editor" may be added later only as a pure addition — the hosted build
  never loses a capability the local one has.
- **Styling is Tailwind v4 with tokens in `@theme`, plus a hand-written `prose.css`.** The
  manuscript and source reading surfaces are typographic work — Newsreader at 17.5px/1.75
  on a 640px measure, mono paragraph anchors in the margin — and are not expressed as
  utility classes. Token extraction is an explicit first step, not a cleanup: the canvas
  carries 44 distinct colours and 22 font sizes, of which 20 colours appear three times or
  fewer.
- **Layout**: `ui/` at the repo root for source, FastAPI at `src/memoria/web/`, build
  output gitignored into the package. The repo's "one command" property is gone, so #24
  carries two acceptance criteria that were previously README prose: one documented
  command that installs, builds and runs everything, and one that runs both test suites.
- **`../open-problems.md` §1.2 stays open** — whether the in-app prose editor is built.
  Nothing here forces it, and React makes it cheaper if it is wanted.
- **Revisit if Ask Memoria's deferral lifts** (this decision anticipated it), or if the
  canvas becomes the primary design loop rather than an exploration surface (it did not
  anticipate that, and the round-trip tax would then be paid on every iteration).
