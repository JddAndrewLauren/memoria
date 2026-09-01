# Memoria

Memoria is a system for writing a book from a large personal archive without the
author managing context windows. This glossary records terms as they are settled.
The build plan under `docs/plan/` defines the rest of the vocabulary; terms here
are the ones resolved in working sessions and take precedence where they differ.

## Language

### The subject system

**Subject**:
A named dimension along which the archive connects to the book — People, Timeline,
Events, Themes, Arcs, and others the author adds. It is both a check the Curator
performs on new manuscript prose and an index a writing agent reads instead of the
corpus. Its prompt carries three things: what counts as a match, the matching hazards,
and **the audit questions this subject asks of new prose**. Every audit question in
the system belongs to some subject; there is no central list.
On screen the three trees are `MANUSCRIPT` / `SUBJECTS` / `SOURCES`, and a new
subject is added with `+ New subject`.
_Avoid_: Axis, group, category, object type, dimension, lens

**Entry**:
One instance under a subject — Bob under People, the acquisition under Events. The
subject says what a kind of entry is; the entry's body is shared territory carrying
the author's testimony and Memoria's badged statements, with ownership read off the
badge (see [[audit-visible-body]]). Testimony is the author's hand alone.
_Avoid_: Item, object, record, node

**Audit-visible body**:
The part of an entry's body that assembly loads and the audit compares prose
against — testimony, settlements, and the `[author]`/`[source]`/`[inferred]`
statements. `[open]` lines and [[memoria-note]]s sit outside it, excluded from
write-side assembly and from the audit, retrievable in Think and Research modes.
_Avoid_: Entry content, loaded body, canonical body, annex

**Match terms**:
How one entry is referenced, beyond the subject default — Bob, Robert, R., my
brother-in-law. Kept on the entry and owned by the author, they are the system's
only alias store; there is no canonical alias map. Discipline that spans entries —
do not merge people sharing a surname — is a subject hazard, not a map row.
_Avoid_: Alias map, aliases.yaml, aliases file, name variants

**Gathered set**:
The sources a subject matched to an entry. Derived, rebuildable, and asserts nothing
on its own.
_Avoid_: Matches, index, link set, results

**Pin** / **Exclude**:
Author acts overlaying a gathered set — pin keeps a source in regardless of what the
pass finds; exclude keeps one out. Both are attributable and survive a rebuild.
_Avoid_: Include/ignore, accept/reject, approve/deny

### The two consumers

**Assembly**:
Resolving a declared scope ("dates X to Y, Bob, the conflict in the capital") through
the subjects into a working context to write from. Happens at write time, in service of a
session; it is not curation.
_Avoid_: Context building, retrieval, gathering

**Working context**:
The Tier 1-3 load [[assembly]] produces for one session — the briefs, the draft, the
named entries' audit-visible bodies and the structural neighbourhood. Bounded by the
size of the declared scope, not by corpus size, subject count or entry count.
_Avoid_: Context window, prompt, loaded files, the context

**Supplied context**:
The [[working-context]] plus every read served since, for one session. It is an account
of what Memoria supplied and asserts nothing about what the model still holds — the
client may compact served reads away, and Memoria cannot see that it has. The author's
own reads in the interface are not part of it — they are served to nobody, and the ledger
behind this account records only what the tool surface served to a session (§10.4).
Reported in countable domain units; token counts belong to the session's context
manifest, never to a surface.
_Avoid_: Context window usage, what the model has seen, context budget, token usage

**Audit**:
Evaluating manuscript prose — hand-written or AI-written — against the entries, asking
the audit questions each subject declares, bounded by the entries the section's brief
resolves to. It runs **only on demand**: a button on a section or a chapter, or on a
highlighted passage. Impact analysis is not a second mechanism — it is the audit
re-run because an entry changed.
_Avoid_: Review, check, validation, impact analysis, scan

**Not current**:
The state of a paragraph whose audit judgement is missing or stale — never audited,
edited since, touching an entry or subject prompt that has changed since, or (for
audit verdicts) judged against a gathered set whose membership has since changed.
Judgements are memoized per paragraph, entry and subject prompt — audit verdicts
additionally on gathered-set membership — so this is a hash comparison: it costs
nothing, needs no model, and is known across the whole manuscript at all times even
though evaluation never runs unasked. It is what the manuscript view tints.
_Avoid_: Stale, unaudited, dirty, pending

### The Curator's two halves

**Index maintainer**:
The Curator half that writes derived state only — ingest matching, candidates,
gathered sets, appearances, invalidation, the staleness map. Everything it writes
is rebuildable and asserts nothing, so no restraint rule binds it.
_Avoid_: Indexer, librarian, gatherer, background pass

**Record extractor**:
The Curator half that writes durable records — post-session decisions, questions,
and badged entry statements. The only half the curation restraint rules and the
entry write matrix constrain; testimony is never its to write.
_Avoid_: Scribe, harvester, note-taker, summarizer

### Author knowledge

**Author testimony**:
A fact the author asserts in an entry with no documentary basis — Bob's birth year,
his build. The entry is its own source, and it outranks documentary evidence that
disagrees.
_Avoid_: Author note, recollection, memory, annotation

**Settlement**:
A recorded author resolution of a surfaced conflict, naming which side was chosen and
when. Downstream passages relying on it inherit the resolution and stay silent.
_Avoid_: Dismissal, decision, override, resolution

### Ownership

**Memoria note**:
The author-facing note the Curator appends when evidence conflicts with a statement
it may not rewrite — a human-touched or author-supreme one. It never loads into
write-side assembly and the audit never evaluates against it. The §19.6 amber card
is this note drawn.
_Avoid_: Annex, annotation, machine note, comment

**Human-touched flag**:
An index flag set at Curator-pass time on statements changed by non-Curator commits
since the last pass. Set once, monotonic, never recomputed — reflow cannot unset it.
The Curator does not rewrite a flagged statement; conflicts become [[memoria-note]]s.
_Avoid_: Ownership bit, blame, dirty flag, lock

### The manuscript

**Brief**:
The single editable prose field a book, a chapter or a section carries — what this
part of the manuscript is, what it covers and what it is for. Manuscript-class and
author-supreme, with three write paths: the author writes it, an AI writes it from a
grilling conversation the author answered, or an AI drafts it by summarizing prose
that already exists. Assembly resolves it; the audit checks new prose against it.
_Avoid_: State, note, purpose, overview, section spec

**Unconfirmed brief**:
A brief drafted by summarizing existing prose, not yet confirmed or edited by the
author. Structurally partial — summarizing recovers coverage but never intent — and
circular, since it was derived from the prose it would otherwise constrain. Assembly
uses it; the audit does not check drift against it. This is what the desktop design's
`LEGACY DRAFT` badge is actually marking, and it is a state of the brief rather than
of the prose.
_Avoid_: Legacy draft, draft note, provisional state, auto-summary

**Declared scope**:
What a section's brief says it covers — "June 1839 to October 1841, and my
interactions with Bob about the conflict in the capital". Not a field of its own: it
is part of the brief and has no separate durable existence. Assembly resolves it
through the subjects at write time, and the resolution is recorded in that session's
context manifest, never written back onto the section.
_Avoid_: Scope field, coverage, section spec

**Outline**:
Not an artifact. The outline is the ordered tree of chapters and sections together
with their briefs; a planned section is a section whose brief is written and whose
draft is empty. Reordering renumbers directories, and the stable IDs in frontmatter
keep references intact. There is no outline file.
_Avoid_: outline.md, table of contents, structure document

**Appearances**:
The manuscript passages an entry turns out to touch, with a short note on how. Derived
and rebuildable, held only in the index, and never authoritative: it is prose the
author has already written, not material to write from, so it is kept separate from
the [[gathered set]] and never flows back into the entry. Produced by matching for
subjects that can match, and by a memoized model pass for subjects like Themes and
Arcs that cannot. It carries no pin or exclude overlay, because an author act against
one passage would be a durable pointer into mutable prose.
_Avoid_: Affected passages, backlinks, manuscript matches, edges

### Writing to the repository

**Write path**:
The one route every durable write takes — the author's through a surface, and the
Curator's. It checks the [[staleness token]], writes the file whole or not at all, and
commits it, attributed to whoever acted — an author's edit through a surface commits as
the author's own, the same class of thing as an edit made in Obsidian, and a Curator pass
commits as the machine. It holds nothing back: no queue, no lock, no
reconciliation, no merge. Derived state does not go through it, having no author work to
protect and nothing to be stale against.
_Avoid_: Write coordinator, transaction, save handler, commit service

**Staleness token**:
The evidence a write carries that the file is still as it was read. Issued when a file is
served for editing and presented back when the write is made; if the file has moved
underneath, the write is rejected, naming the file, and the author's text stays on screen
to be re-applied. It asks whether this file changed since it was read — a different
question from whether the file holds uncommitted human work, which is what the
[[human-touched flag]]'s companion dirty-tree rule asks, and neither answers the other.
_Avoid_: Version, revision, lock, etag, generation
