# A new section is written from the app, by hand or from a grilling

The author asked for a floating button that opens a dialog for writing a new piece of the
manuscript: an option to **write now**, an option to be **grilled** first - the `/grilling`
skill's relentless one-question-at-a-time interview, repurposed for writing - an optional
choice of where in the manuscript it goes, the current chapter assumed when the dialog is
opened from a section, and the source included in the context when it is opened from a
source page. They asked that the grilling follow the settings ADR-0010 built.

Three settled things shape the answer. **The vocabulary**: CONTEXT.md reserves *entry* for
an instance under a subject; the thing being created is a **section**, with its **brief**
(`section.md`) and its prose (`draft.md`), and the dialog is named for it. **The write
path**: no author-facing create existed - `manuscript.create_section` writes a brief file
with no commit, for the legacy import and the gates - and ADR-0003 settles that creation
goes through `write.create`, "a second door, not a bypass", committed and attributed. **The
model**: ADR-0010 keeps every pass that needs a model in two shapes, a *direct run* from a
button when Settings > Model is ready and a *session run* driven by a skill over MCP tools,
the default. And one precedent decides how AI-drafted prose reaches the manuscript from the
app: `PUT /api/sections/{id}/paragraphs/{n}` commits a proposed rewrite as the author,
because "the click is the authorization (part 10 §19.3) and the applied prose is now the
author's".

**We decided that** a new section is created through the write path as the author's act,
from one dialog that offers two ways to arrive at its prose.

- **The floating `+ New section` button** sits at the bottom-right corner of every page and
  opens the dialog. It reads its context off the route: on a section page (or Review, or
  supplied context) the section's chapter is the default; on a source page the source is a
  chip in the dialog and joins the interviewer's context, and the brief starts by naming it.
  Anywhere else it assumes nothing beyond the first chapter.
- **Where it goes is a chapter, and the section is appended.** Position is the directory
  number (part 04 §2.1), `manuscript.plan_section` mints the next one, and the picker
  chooses a chapter and nothing finer. Inserting mid-chapter would be a create followed by
  `reorder_sections`, the non-atomic mechanism ADR-0003 declines to cover; it is deferred,
  and the dialog says the place can be changed later.
- **"Write now" is prose, and a brief where the author wrote one.** `POST
  /api/chapters/{id}/sections` plans the section, writes the brief and then `draft.md`, two
  commits through `write.create`, committed as `repository_actor` - never a name in the
  payload (ADR-0002). A brief the author did not write is the prose's opening, shortened,
  marked `unconfirmed` - exactly CONTEXT.md's *unconfirmed brief*, "drafted by summarizing
  existing prose, not yet confirmed" - and the author's first edit or confirmation makes it
  theirs.
- **"Grill me" is the fifth pass, in ADR-0010's two shapes, and it ends in a draft the
  author writes.** `memoria.grill` serves one briefing - the interview prompt, the book's
  and chapter's briefs, the sections already in the chapter, the writing style, the source
  - rendered once for both shapes. As a **direct run**, `POST /api/grill` is one interviewer
  turn per call: the dialog holds the transcript and sends the whole of it every time, the
  server keeps none of it, and every call is a `model_call` ledger line beside a
  `grill_brief` line naming what was served. When the understanding is shared, or the author
  says to write, the reply is the brief and the prose, and they land in the same editable
  box "Write now" uses. **The author's Write is the act**, and it commits as theirs by the
  `rewrite_paragraph` precedent: a draft the author read, could edit, and chose to write is
  the same class of thing as a rewrite they applied from Review. As a **session run**, the
  dialog prints the exact command - `/grill-writing CHP-0003 SRC-000184` - and the
  `grill-writing` skill drives `grill_brief` and the interview in the Claude Code session,
  then `section_create`, which writes the section through `memoria.authorship` under two
  authorizations from the author's confirming turn: the brief alone (`BriefTarget`) and the
  prose (`SectionTarget`), because a brief is authorized one level below prose and never
  beside it (§19.3). There is no `grill_run` tool: the interview's other party is the author,
  so the direct run exists only where the author is at a surface, and a session is already
  the interviewer.

## Considered Options

**Calling the thing an "entry".** The author's word, and the wrong one here: CONTEXT.md's
*entry* is Bob under People. Rejected; the dialog is "New section" and the ADR says why.

**Insert after a chosen section.** The natural reading of "where in the manuscript it goes".
Rejected for this slice: it needs `reorder_sections` after the create, two mechanisms in one
act with a half-done state between them (`.reorder-*` scratch directories), and ADR-0003
says reordering "needs a different mechanism if it is ever built". Appending, with the
picker choosing the chapter, is the whole of what the write path covers today.

**A brief only, prose in Obsidian.** The plan's own answer (`poc-plan.md` §3 puts editing
in Obsidian). Rejected with the author: "Write now" means prose. The dialog's textarea is
the app's first, and `open-problems.md` §1.2 - whether an in-app prose editor is built -
stays open: this creates a file that did not exist and edits nothing, so nothing can
collide with an Obsidian edit and the staleness question does not arise.

**Prose only, always.** Rejected: a section without a brief has no line in the outline (the
tree is labelled by the brief's opening) and nothing for assembly to resolve. The derived
unconfirmed brief costs the author nothing and says honestly what it is.

**The grilling as a stored interview.** The transcript could live in the index between
turns, like proposed observations. Rejected: an interview asserts nothing and belongs
nowhere durable; holding it in the client makes every request self-contained, the server
stateless, and a closed dialog a finished conversation. What the interview *produced* is
what the author writes, and that goes through the one write path like everything else.

**The grilled draft committed as the machine with an authorization.** The session run does
exactly this, because it has a turn to cite. The dialog has no transcript turn - the app
mints one ledger session per process and derives no transcript - and inventing a citation
would make `trace()` lie. The author's click is an authorization the plan already
recognises (§19.3's "Authorization may also occur through interface actions"), and the
edited draft is theirs. Rejected for the direct run, kept for the session run.

**A model in the browser.** Rejected before it was considered: ADR-0002 and
`tests/test_ui_dependency_boundary.py`. Every button posts to the backend, which holds the
seam.

## Consequences

- `manuscript.plan_section` / `add_section` / `add_draft` / `brief_from_prose` are the
  creation put behind the write path the module's docstring anticipated; `create_section`
  stays for the legacy import and the gates. Both isolation guards in `test_manuscript.py`
  hold: only `manuscript.py` names a brief's filename, and the guarded functions gain no
  new caller.
- The web adapter gains its first create route and its first route that opens no file and
  writes nothing durable but is still a POST (`/grill`); `test_web_app.py`'s pinned list of
  writing routes names both and says why.
- `memoria.authorship.write_section_from_conversation` is the first AI write that brings a
  file into being rather than replacing one; its two commits each carry
  `authorized-by`/`authorized-scope`, and `memoria validate`'s rule for manuscript commits
  is unchanged.
- The MCP surface gains `grill_brief` and `section_create` (`docs/tool-surface.md`), and
  the repository gains the `grill-writing` skill. `section_create` takes the confirming
  turn by number from the session, hand-checked the way `/curation` checks its turns - the
  transcript is derived after the session, so the number is the model's to get right.
- The ledger gains a `grill_brief` line with a `served` key, so the supplied-context account
  reads a source that entered an interview the same way it reads a `read` of it.
- **An author with direct runs on spends a metered call per interview turn**, and their
  answers - and the source's text - leave the machine each turn; the dialog says so
  beside the Start button. Off, nothing leaves: the dialog prints the command.
- Provenance of a grilled section written from the dialog is the author's commit and the
  `grill_brief`/`model_call` lines under the app's session; `trace()` names the commit and
  the author, not a turn. Provenance of one written from a session is the full chain part
  10 §20 draws. The difference is deliberate and this ADR is its record.
- **Revisit if** the author wants a section placed mid-chapter from the dialog (the
  reordering mechanism ADR-0003 deferred), or wants the dialog's interview to resume after
  the dialog closes (a stored interview, the option rejected above).
