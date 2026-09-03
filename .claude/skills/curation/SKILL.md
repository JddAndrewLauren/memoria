---
name: curation
description: Run Memoria's post-session curation - the record extractor's pass in which the session's transcript is read for what the author actually decided, wondered and found, and each is written as a durable record citing its exact turn. Use when the author says "curate the session", "record what we decided", "run the extractor", or invokes /curation. Not for the archive-wide extraction - that is /extraction.
---

# Post-session curation

The record extractor is the Curator's constrained half (part 08 §12-§13,
`src/memoria/record_extractor.py`). After a research session it reads the
transcript and writes **only what actually occurred**: decisions the author
made, questions and musings left open, and badged statements into entries.
Every record cites the transcript turn it came from, and `memoria validate`
fails a citation that names a turn that is not there.

**One rule does the work** (part 06 §9.2, part 08 §13.1): a decision needs a
citing turn that is *identifiably the author's*. The tools check whose turn it
is; whether the author's words decide something or only wonder is **your
judgement, made against the turn's text, hand-checked by turn number**. When in
doubt it is not a decision. Everything that is not a decision is `[open]`.

## Before anything: derive, commit, ask

1. `curation_status()`. It lists every session on disk and whether its
   transcript has been derived. A session with `no transcript yet` cannot be
   cited.
2. To derive one, the author (or you, in a shell) runs:

   ```
   memoria derive-session <SES-id>
   ```

   The `SES-` id is the directory name under `sessions/` that the session's
   own `events.jsonl` landed in. With no path argument, the command resolves
   Claude Code's own JSONL for the *current* session itself, from
   `CLAUDE_CODE_SESSION_ID` in the environment - no path to find or guess at.
   Then **commit** the derived `sessions/` directory: the dirty-tree rule
   (part 08 §14.2) refuses every write while tracked files carry uncommitted
   changes, and `curation_status` names them.
3. Read the transcript: `read(SES-...)` for the whole thing, `read(SES-...#T017)`
   for one turn. Every heading is `## Tnnn — Author` or `## Tnnn — Assistant`.
4. **Show the author the list of what you propose to record - each item with
   its turn number and its kind - and wait.** Nothing here writes unasked.

## Recording

- `record_decision(session_id, turn, text)` - only for an author turn in which
  the author actually decides. `text` is the decision in the author's own
  terms, one paragraph. Cite the turn in which it was *said*, not the turn in
  which you summarised it back. The tool refuses an assistant turn and tells
  you to use `record_question`; take that at its word.
- `record_question(session_id, turn, text)` - a musing ("maybe…", "what if…"),
  an interim interpretation, an actual question. Lands `[open]` in
  `questions.md`, citing the turn. This is the landing place for everything
  that did not clear the bar above - including things the author said with
  conviction that are nonetheless not a decision about the book.
- `record_statement(entry_id, badge, text, provenance)` - what the session
  established about an entry, per the write matrix (part 06 §8.2):
  `[source]` for what the evidence says (cite the `SRC-` paragraph),
  `[inferred]` for what follows from it (cite the evidence it follows from),
  `[author]` for an interpretation the author spoke (cite their turn), `[open]`
  for a question the entry should hold. Never testimony: the tool has no
  unbadged mode.
- `revise_statement(entry_id, statement_badge, statement_text, badge, text,
  provenance)` - when new evidence conflicts with a statement already there.
  Name the existing statement by its badge and words. The tool refreshes the
  human-touched flag first and then either rewrites the statement in place or,
  where the Curator may not - author testimony, an `[author]` statement with
  no new author turn, or any statement the author has hand-edited - appends a
  **Memoria note** after it and leaves the author's text byte-identical. The
  reply says which. Do not try to route around a note by rewording; the note
  *is* the correct outcome.
- `curation_flag()` - the flagging step on its own, to see what the author's
  hand edits since the last pass touched. `revise_statement` runs it itself.

Each write is one path-scoped commit as the Curator. A refusal (dirty tree,
stale entry, missing turn, assistant turn offered as a decision) is a message,
not a failure: read it, fix the cause, and re-issue that one call. A pass that
stops part way leaves valid records behind and can be re-run - nothing is
written twice, because you will re-read `curation_status` and the files
before continuing.

## The report

Close with, in this order: decisions recorded (id, turn, text); questions
recorded (turn, text); statements appended or revised, and every Memoria note
written, naming the entry; anything you judged a candidate and did **not**
record, with the turn and why. Then, in as many words:

> Every record above cites the turn it came from. Nothing the assistant said
> is badged `[author]`, and nothing was written into an entry as testimony.
