---
name: grill-writing
description: Interview the author about a new section of their manuscript until the two of you share what it says, then write it - the grilling repurposed for writing (ADR-0011). Use when the author says "grill me about this section", "interview me before I write", "let's write a new section", or invokes /grill-writing, optionally with a chapter id (CHP-nnnn) and a source id (SRC-nnnnnn) the app's New section dialog printed. Not for editing prose that exists - that is a rewrite under an authorization.
---

# Grilling toward a new section

A new section begins as a shared understanding of what it says, and the
grilling is how that understanding is reached: relentless, one question at
a time, a recommended answer with each, the decisions the author's. This
skill runs that interview in this session and, once the author confirms
what came out of it, writes the section - brief and prose - as two commits
citing the turn in which they confirmed. **Nothing is written before that
turn.** The app's dialog offers the same interview as a direct run when the
author switched one on under Settings > Model; there is no `grill_run` tool
here, because the interview's other party is the author and this session is
already the interviewer.

## Before anything: which chapter, which source

The dialog prints the exact invocation - `/grill-writing CHP-0003` or
`/grill-writing CHP-0003 SRC-000184` - so the arguments are the chapter the
section is appended to and, when the author opened the dialog from a
source, that source. Without a chapter id, `read(BOOK)` and the chapters it
names, or the MANUSCRIPT tree the author is looking at, say which chapters
exist; **ask the author which one** and wait. Do not guess a chapter.

## The briefing

Call `grill_brief(chapter_id, source_ref)` **once** and keep it. It carries
the interview prompt verbatim, the book's and the chapter's briefs, every
section already in the chapter and whether each has prose, the author's
writing style, and the source's text where there is one.

Do not paraphrase the prompt or substitute instructions of your own; it is
served verbatim so that there is exactly one version of it. Follow it.

## The interview

- **One question per turn.** Several at once is bewildering. Wait for the
  answer before the next.
- **A recommended answer with every question**, and a sentence on why. The
  author takes it or overrules it.
- **Look facts up; ask only decisions.** What the chapter's brief says, what
  the neighbouring sections cover, what the source says - these are in the
  briefing or one `read(ref)` / `search_text` away. Put to the author only
  what is theirs to decide: what the section is about, where it opens and
  closes, who is in it, what the reader should know or feel by its end,
  what it must not say yet.
- **Walk the branches in order**, each question resolving what the last one
  opened, until the understanding is shared - or until the author says to
  write. "Write it now" ends the interview where it stands.

## The draft, and the confirmation

When the understanding is shared, draft in the conversation - **not** in
the repository:

- **The brief**: one short paragraph in the author's own terms - what this
  section is, what it covers, and what it is for. Prose, not a list; it
  names no fields.
- **The prose**: the section itself, written to the writing style the
  briefing carries, complete and first-class - not an outline, not notes.
  Everything it asserts comes from the briefing or from what the author
  said in this interview. Invent nothing.

Show both to the author and **wait for them to confirm, change, or reject
them.** Apply their changes and show the result again until they say to
write it. Only their confirming turn authorizes the write.

## The write

Call `section_create(chapter_id, brief, draft, turn)` once, where `turn` is
the number of **the author's turn that confirmed** - hand-checked by turn
number, never an assistant turn, never the turn in which you proposed the
draft. The section is appended to the chapter as two commits under two
authorizations from that turn: the brief alone (`authorized-scope: SEC-nnnn
brief`) and the prose (`SEC-nnnn draft`), each carrying `authorized-by:
SES-...#Tnnn`. `trace()` walks either back to the turn.

Close by naming the new `SEC-` id and the turn the commits cite, and in as
many words:

> The section is in the outline now. Its brief is yours to edit under the
> section's PURPOSE card or in Obsidian; its prose is first-class
> manuscript prose, and `trace()` says how it came to exist.
