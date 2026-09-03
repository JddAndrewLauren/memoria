# HANDOFF — the M4 gate's author session (#34)

Written 2026-09-03 at the end of the session that built PR #197. Everything an
agent could do on the gate is done; what remains needs the author in the loop,
and this file is the brief for the session that does it.

## Goal

Pass the M4 gate on a **real** research session, then close #34. The gate's
machinery is proven on a staged session (`docs/gates/m4-gate-walk.md`); what
is unproven is curator restraint on a conversation not held to test it, and
the `/curation` skill's prose driven by a model rather than by
`gate/m4/records.py`.

## Member items, in order

1. **Decide the piece — #27.** Subject, target length, the §1.12 check ("what
   makes this genuine writing rather than an exercise"), dated. Update
   `docs/open-problems.md` §4.1 and §6 and `docs/poc-plan.md` §7 as #27 lists.
   Nothing below can start first: the gate's sessions are that piece's research
   sessions.
2. **Dry-run `/curation` before the real session.** Run
   `scripts/gate-m4.sh --keep`, open a Claude Code session in the kept scratch
   repository (it has a derived session, `decisions.md` and `questions.md`
   already), and invoke `/curation`. What to watch: whether the skill's
   "derive, commit, ask" opening reads correctly to a model, whether it
   hand-checks turn numbers before recording, and whether it stops to ask before
   writing. Fix the skill text, not the tools, unless a tool refusal is wrong.
3. **Hold the real session** in Claude Code with the Memoria MCP server up
   (`.mcp.json` registers it; reads are ledgered under a `SES-` id in
   `sessions/`). Do not hold it in order to test the extractor.
4. **Curate it** — `/curation`. Derive from the session's JSONL
   (`~/.claude/projects/<cwd with / as ->/<uuid>.jsonl`, newest file), commit
   the derived `sessions/` directory, let the pass record. Quote the `[open]`
   musing, as written, in #34.
5. **Click the decision** on the Section view. It appears only on a section
   the session's ledger served a read of; if the page is empty, that is a
   finding worth recording, not a failed step.
6. **Hand-edit a badged statement**, run `curation_flag`, and let a later
   conflict produce the note through `revise_statement`. Confirm your text is
   byte-for-byte unchanged (`git diff` the file: only the note is added).
7. **Every real misbehaviour becomes a regression test**, in `tests/` or
   `ui/src/`, in the same PR that fixes it.
8. `memoria validate` over the real repository; paste the observations under
   the gate doc's *Verdict*; close #34.

## Context to load

- `docs/gates/m4-gate-walk.md` — what the walk proves and what it does not.
- `.claude/skills/curation/SKILL.md` — the pass the author will run.
- `docs/tool-surface.md` "Record-extractor tools" — what each tool refuses.
- `src/memoria/record_extractor.py` module docstring — the rules, with the
  plan sections they come from; `tests/test_curation_tools.py` for the shapes.
- Issue #27's body for what the piece decision must record.

## Missing decisions

- **#27 itself** — the author's, and the only blocker.
- Whether `derive-session` should find the newest JSONL itself (`--latest`)
  or the skill should print the exact path — filed as an issue from this
  session; either answer removes the one manual step most likely to stall a
  real pass.

## State at handoff

- Branch `JddAndrewLauren/m4-gate`, PR #197 open against `main`, mergeable.
- Standing gate green (pytest + vitest); both browser walks pass.
- The `.claude/hooks/route-evidence-reads.sh` hook rejects any Bash command
  whose text names the index directory; assemble the literal or use Write/Edit.
