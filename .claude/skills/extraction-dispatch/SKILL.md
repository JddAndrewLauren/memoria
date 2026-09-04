---
name: extraction-dispatch
description: Run Memoria's extraction over a corpus too large for one session to read itself - the orchestrating session serves paragraphs, parallel sub-agents read them, and the readings are cached through the same core function the extraction_record tool wraps. Use when the author says "dispatch the extraction", "extract the corpus with sub-agents", "run the extraction in waves", or invokes /extraction-dispatch. Not for a corpus one session can read - that is /extraction - and not when direct runs are ready - that is extraction_run.
---

# Dispatching the extraction

`/extraction` is the pass itself: the session is the model, reading twenty
paragraphs at a time. On a corpus of tens of thousands of paragraphs that is
hundreds of batches, more than one session holds. This skill is the same pass
with the reading delegated: **the orchestrating session serves, sub-agents
read, a script records.** Everything `/extraction` says about what the pass
is still holds - it asserts nothing, it proposes, the author promotes - and
the close of the pass is `/extraction`'s close, unchanged.

Three facts about the core make the shape safe (`src/memoria/extraction.py`):

- `pending_paragraphs` is a plain query with no lease. A paragraph leaves the
  pending set only when its reading is cached, so a wave served and never
  recorded is simply served again. Nothing is lost by a crash or a stop.
- `record_batch` is what the `extraction_record` tool calls, and all it
  calls. Recording from a file through `record.py` writes the same rows.
- `extraction_finish` refuses while any paragraph is unread. The pass has a
  hard gate before anything promotes.

The scripts beside this file (`serve.py`, `record.py`, `compare.py`) are run
with the project's Python from the repository root:
`uv run --with-editable . python .claude/skills/extraction-dispatch/serve.py ...`.
They import the core exactly as the MCP server does. `serve.py` ledgers the
brief and every served batch the way the MCP tools do, so the
supplied-context account (ADR-0001) still names the session that read
everything: run it with `MEMORIA_SESSION_ID=<this session's id>` (the newest
directory under `sessions/<year>/<month>/`, the one this session's MCP
calls are landing in) so the lines join that record instead of a fresh one.

## 0. Before anything: ask

Call `extraction_status()` and `model_status()` and show the author both.
Then ask whether to run, and wait. The pass reads the whole archive with a
model; part 08 §12.1's rule is that nothing needing a model runs unasked.

If `model_status()` says **ready**, stop here: `extraction_run` on the server
is the cheaper thing to supervise, and `/extraction` drives it. This skill is
for the session-driven path only.

## 1. Parameters, decided once, written to `run.md`

| parameter | default | rule |
|---|---|---|
| model | the pilot's winner | never silently downgrade; the author names it |
| batch size | 300 paragraphs | 100 to 500. Above 300, "judge each paragraph alone" drifts as a worker's context fills |
| parallel workers | 8 | bounded by what the session can supervise, not by the server |
| oversize threshold | 20,000 chars | above it a paragraph gets one worker to itself |
| retries | 1 per chunk, same model | a second failure is reported by anchor, never repaired by the orchestrator |

The run directory is `$SCRATCH/extraction-dispatch/<date>/`. `serve.py`
lays it out: `brief.md` and `brief.sha` once, `waves/<n>/chunk-<k>.json`
per wave, `oversize/<anchor>.json` for the giants. Add `readings/`,
`record/` and `run.md` yourself. Every file a worker writes is named for
its wave and chunk (`readings/<n>-<k>.json`): sub-agents share one
scratchpad, and a fixed name means the last writer wins.

## 2. The pilot

Mandatory on a fresh corpus and after any subject-prompt edit, because a
prompt edit re-reads everything and the model choice is what the whole pass
inherits.

1. `serve.py RUN --workers 1 --batch 100`, giving `waves/1/chunk-1.json`.
2. Spawn one worker per candidate model on that one chunk, each writing
   `readings/pilot-<model>.json` (the worker spec below, with the file name
   changed). Scratch only; nothing is recorded.
3. `compare.py --chunk waves/1/chunk-1.json --readings readings/pilot-*.json --out RUN/pilot`.
4. Spawn one read-only comparator (`model: opus`) over `brief.md`, the chunk,
   the readings and `pilot/compare.md`: for the top-disagreement paragraphs
   it lists, say which reading is closest to the brief and where each errs
   (over-extraction, misses, wrong subject, non-verbatim forms, hazard
   violations). It writes `pilot/verdict.md`, reads it back, and returns a
   ranked list with one line each.
5. Report both to the author. **The author names the model.** On their
   word, and only then, `record.py readings/pilot-<model>.json --chunk
   waves/1/chunk-1.json` caches those 100 so the pass does not re-read them.

## 3. The wave loop

1. `serve.py RUN --workers 8 --batch 300`. It prints the wave number, each
   chunk's span, and the oversize set. Chunks within a wave are disjoint
   slices of one query; the next wave's query excludes what was recorded.
   If it prints `nothing pending`, go to step 5.
2. Spawn every worker of the wave **in one message**, `subagent_type:
   general-purpose`, the chosen model, this spec with the paths filled in:

   > You are one reader in Memoria's extraction pass. Working dir: RUN.
   > Read `brief.md` FIRST and follow it exactly; it is the whole of your
   > instructions for judging a paragraph. Then read
   > `waves/<n>/chunk-<k>.json`; its `paragraphs` array is `[{anchor, text}]`.
   > Judge every paragraph ALONE: nothing carries over between paragraphs.
   > For each paragraph produce one object:
   > `{"anchor": "<as served>", "placements": [...], "relations": [...], "unplaced": [{"surface_form": "...", "subject_id": "SUB-..."}]}`
   > Place only against the entries the brief lists, with the exact words in
   > the paragraph as the surface form; when the brief lists none, placements
   > and relations stay empty. `subject_id` is one of the subject ids the
   > brief lists, or "" if none fits. An empty unplaced list is the common
   > and correct answer. Write all objects, in served order, as one JSON
   > array to `readings/<n>-<k>.json` and nothing else. Do NOT call any
   > Memoria MCP tool. Do NOT read any other file.
   > Return only, on separate lines: paragraphs written; paragraphs with at
   > least one unplaced form; total unplaced forms; anchors you could not
   > judge (or "none"). No prose.

3. As each worker returns: `record.py readings/<n>-<k>.json --chunk
   waves/<n>/chunk-<k>.json | tee record/<n>-<k>.log`. Its outcome is the
   tool's: `accepted X of N` and one line per rejected element naming the
   reason. Re-send only the rejected anchors to the **same** worker, once,
   by message; then record the corrected file. A second rejection of the
   same anchor goes in the report and is left unread.
4. A worker that returns fewer objects than served, a structural problem
   from `record.py`, or BLOCKED: message it once with the missing anchors.
   If that fails, leave the file alone; the unread paragraphs are pending
   and the next wave serves them to a fresh worker, which is the retry.
5. Append to `run.md`: wave, chunk spans, each worker's four lines
   verbatim, `record.py`'s first line, wall clock. Then serve the next wave.

**The orchestrator never judges a paragraph, never edits a readings file,
and never passes a reading through its own context.** Recording is the
script's job; the session's context is for supervision.

## 4. Oversize paragraphs

`serve.py` writes each paragraph above the threshold to
`oversize/<anchor>.json` in the chunk shape. Each gets one worker, the
largest-context model available, that file as its only chunk, and
`record.py` the same way. A paragraph too large for any worker is reported
to the author by anchor and size and left unread; the pass cannot finish
until they decide (split the source, or read it themselves).

## 5. Close the pass, as `/extraction` does

When `serve.py` says nothing is pending: `extraction_derive()`, report its
numbers; `extraction_finish()`; then `/extraction`'s summary loop, in this
session, because the clusters must be current and summaries are few. Then
`/extraction`'s promotion section applies unchanged: nothing under a
subject declaring `auto-promote: no` becomes an entry unless the author
names it, one at a time.

## 6. Stopping and resuming

Stop cleanly at a wave boundary. Everything is in the database: a new
session runs `serve.py` and the unread paragraphs are what it serves. A
readings file left over from an interrupted wave can be recorded first with
`record.py`; it refuses if the brief has changed since the chunk was served.

## 7. The report

`/extraction`'s report, plus: the pilot's ranking and the model chosen;
waves run and workers spawned; retries; paragraphs left unread, by anchor;
oversize paragraphs and their disposition; and, if the harness reports
them, tokens per wave. Close with the same words:

> The extraction asserted nothing. Every number above is a proposal; match
> terms decide what is placed, and nothing under a subject declaring
> `auto-promote: no` became an entry.

## Sizing (measured 2026-09-04, Opus workers)

Count **distinct paragraph texts**, not paragraphs: the cache is keyed on
the text, so one reading of "Bob" marks every identical paragraph read, and
`serve.py` serves one anchor per distinct text. This corpus has 52,904
paragraphs but 29,311 distinct texts.

| batch | workers per wave | wave wall clock | worker tokens | runs for 29,311 distinct |
|---|---|---|---|---|
| 100 | 1 | 1.5 to 4.5 min | 50k to 75k | ~293 |
| 300 | 8 | 5.6 min, spawn to last record | 83k to 123k | ~98, about 12 waves |

Measured on a rehearsal wave: 8 workers of 300, all returned, 2,400 of
2,400 accepted with no warnings, and those 2,400 readings marked 9,165
paragraphs read. A 300-paragraph worker agreed with three 100-paragraph
workers on the same text at 0.68 to 0.83 mean Jaccard, the last third the
highest, so no drift was seen at 300. Opus agreed with itself on a repeated
100 at 0.76, above its agreement with any other model (0.55 to 0.66).

These figures are for a corpus whose paragraphs average a few hundred
characters; measure a wave before trusting them elsewhere.
