# The writing style is a durable file the Settings surface edits, proposed by a session and confirmed by the author

The author asked for a settings menu behind a gear icon, whose first setting is a
**writing style**: direction that reaches every piece of manuscript prose an agent
writes. They also asked for an analysis that reads samples of their own writing -
sources already in the archive, or documents supplied for the purpose - proposes a
series of observations about how they write, and lets them confirm or change each one
before it is used.

The design canvas has carried `⚙ Settings` in the sidebar footer since part 19 was
written, unspecified; §19.11 listed it as "recorded, not resolved". The plan already
names the thing itself, under two names: `book.md` carries "voice notes" (part 18
§52.1), and a writing session loads "voice guidance" as part of Tier 1 (part 18
§52.4). Part 06 §8.6 settles its kind - **craft direction is not testimony**, never
checked against evidence, never an entry - and puts it in a brief.

Three settled statements pull against a settings store: part 04 §2.1's "**there are no
separate fields**", part 14 §40's amendment "**the separation is a file boundary, not a
setting**", and §1.11's "structure should earn its existence". And one architectural
rule shapes the analysis: no adapter and no core module may call a model
(`../poc-plan.md` §3, `../tool-surface.md`), so nothing in the app can *run* it.

**We decided that** the writing style is one durable file, `style/writing-style.md`,
under a new `style/` state class: author-supreme, editable in Obsidian, served with a
staleness token and written whole through the one write path, committed as the author
(ADR-0003). The Settings dialog is a window onto that file, not a preferences store of
its own - which is what makes it *a file boundary rather than a setting*. The style is
book-wide craft direction that belongs to no section, so it is not a field on a brief
and adds none; it sits beside `book.md` as a second Tier 1 file, and `assemble` loads
it as the "voice guidance" the plan already lists. Every server of it - assembly, the
`writing_style` tool, the audit's task rendering - serves one rendering,
`memoria.style.writing_style_prompt`, so there is no second text to drift.

The analysis is a conversation, not a service: `style_brief` serves the analysis
prompt (a package constant, like `EXTRACTION_PROMPT`) with every chosen sample
verbatim, and `style_record` takes the observations back as tool arguments, each
required to quote an example that occurs verbatim in the served samples. What it
records is **proposals**, held in `.memoria/index.db` as a preserved table
(`style_observations`), asserting nothing - the candidate/promote shape of ADR-0005
applied to craft direction. The author confirms, changes or discards each one in
Settings; only a confirmation writes the durable file, as their own act.

Documents uploaded for their style are durable (the author put them there) but are
not evidence: they live under `style/samples/`, carry no `SRC-` id and no anchor, are
never normalized, gathered, searched or cited.

## Considered Options

**A section of `book.md`.** The nearest thing to the plan's own answer. Rejected
because a brief is one editable prose field whose parser refuses any other structure
(`manuscript.parse_brief`), and the confirm-one-at-a-time flow needs a list it can
append to without re-parsing the author's prose. Keeping the two files side by side
costs one path and keeps both parsers honest.

**A client-side preference (`localStorage`).** Rejected: ADR-0002 forbids a surface
assuming the browser and the repository share a machine, and a style held in one
browser would never reach a writing session at all. The style is repository state or
it is nothing.

**Running the analysis from the app.** Rejected by `../poc-plan.md` §3 before it was
considered: there is no model-driving service, and the session agent is the only
generative model in the system. The dialog says how to run it instead.

**Confirming in the conversation.** The skill could ask the author about each
observation in chat and record the confirmed text itself. Rejected with the author:
the app is where they read their own style, and a proposal confirmed in Settings is
a click-authorized act with a token behind it, the same shape as `Settle` and
`Apply`. The session proposes; the author promotes.

**Proposals as durable records.** Rejected: a proposal the author has not read
asserts nothing and must not be loaded anywhere. The index is where such things
already live (candidates, unplaced forms); a preserved table keeps them across a
rebuild, and `--reset-cache` discards only what the author had not yet acted on.

## Consequences

- `memoria.write.DURABLE_PATHS` gains `style/`; `memoria.style` writes only through
  `memoria.write`, and the no-direct-write test holds.
- `WorkingContext.writing_style` and the `assemble` ledger line's `writing_style`
  field record that the style was supplied, by path - a fact, never the text, in
  keeping with ADR-0001's countable units.
- The MCP server's instructions tell a writing session to call `writing_style()`
  before drafting or rewriting prose. There is no manuscript-writing tool yet
  (`authorship.write_draft` is driven from Python by the M5 gate); when one is
  built, it serves the same rendering.
- `audit_pending` prints the style above a non-empty batch, because a finding's
  patch is manuscript prose and follows it like any other AI write.
- The Settings dialog is the first modal beside search; the two share one
  `Dialog` component. The dialog's rail lists one setting; a second is a row there.
- `style_record` checks examples against the served samples. A model that
  paraphrases its evidence is told so per element and the rest of the batch is kept.
- **Revisit if** a writing-agent tool surface is built that composes its own prompt:
  the rendering should move behind that tool rather than be copied into it.
