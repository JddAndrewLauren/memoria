# A new subject is declared from the app

The author asked for buttons to add sections and subjects "like there is for sources"
(ADR-0013's `+ Add sources…` row at the top of the SOURCES tree). A section already had
its dialog (ADR-0012) but only the floating corner button opened it; a subject had no
creation path at all - `memoria seed-subjects` writes the five built-ins and the author
adds one by hand in the editor, though CONTEXT.md has said since the start that "a new
subject is added with `+ New subject`".

Two settled things shape the answer. **The prompt format**: a subject is one file,
`subjects/<slug>/_subject.md`, carrying the four declarations part 06 §8.1 requires - the
match, the hazards, the audit questions, and whether it auto-promotes (ADR-0005) - and
`subject_to_markdown` / `parse_subject` own both directions of it. **The write path**:
`subjects/` is a durable state class, and ADR-0003 settles that creation goes through
`write.create`, committed and attributed; ADR-0012 settled that a click in a dialog is the
author's act and commits as `repository_actor`.

**We decided that** a subject is declared from a dialog and created through the write path
as the author's act, and that every tree offers its create at the top, the same way.

- **`+ New subject…`** at the top of the SUBJECTS tree opens the dialog: a name, the four
  declarations, Create. The id is derived from the name - `Key dates` is `SUB-key-dates` -
  by `subjects.subject_slug`, the same slug shape an entry reference accepts, so the author
  never types an id. Only the match must say something; the hazards and audit questions
  may be left for later, in the prompt file, and validate reads them back either way.
- **`POST /api/subjects`** calls `subjects.add_subject`: one file through `write.create`,
  one commit as `repository_actor` - never a name in the payload (ADR-0002). A subject
  already there is a 409 and nothing is written: a prompt the author may have edited is
  never flattened by a second create, `add_draft`'s rule.
- **`+ New section…`** at the top of the MANUSCRIPT tree opens the ADR-0012 dialog, the
  same one the floating button opens, reading the same context off the route. The floating
  button stays: it is the affordance for *while reading*, the tree row for *while
  browsing*, and both are one dialog.

## Considered Options

**Seeding from the app** (a button running `memoria seed-subjects`). Rejected: it adds
nothing the five built-ins do not already say, and the author's request is for *their*
subjects.

**A free-form prompt textarea.** Rejected: the four declarations are required, and a
prompt missing one fails `parse_subject` - which would make the create fail after the
author wrote it, or write a file validate then refuses. Four labelled fields make the
requirement the form.

**An id field.** Rejected: the id is the directory name and the entry-reference prefix,
so it has one legal shape; deriving it is the only way the author cannot get it wrong.

## Consequences

- `subjects.add_subject` and `subject_slug` join `set_match_terms` as the module's durable
  writes; the module docstring says so. `write_builtin_subjects` is unchanged and still
  not a durable write.
- The web adapter gains `POST /subjects`; `test_web_app.py`'s pinned list of writing
  routes names it and says why. `SubjectCreate` / `SubjectCreated` join the generated
  types.
- The SUBJECTS tree's empty state names the button before the CLI command; the
  MANUSCRIPT tree gains its row. Both rows call one context the app provides
  (`newItemsContext`), so a tree needs no knowledge of the dialogs.
- **Revisit if** the author wants to edit a subject's prompt from the app (a `write`
  with a token, not a create), or a subject's directory to be renamed after the fact.
