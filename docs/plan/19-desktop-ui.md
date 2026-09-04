<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source: Claude Design canvas "Memoria Desktop", incorporated 2026-08-31. -->
<!-- Not from the original memoria-plan.md. The written interface spec is §40, part 14. -->

# 19. Desktop UI — as designed

A desktop interface for Memoria was designed on a Claude Design canvas. This part
records it **as it stands**. It describes the design; it does not revise it, and it
does not resolve the places where it runs ahead of the rest of the plan — those are
named in §19.11 and left open.

> **This part is illustrative throughout.** Every screen, label, verdict, badge,
> severity, count and card here is example content, chosen to make a picture
> legible. **None of it is a specification, and none of it may drive data
> structures.** Where the plan and this design disagree, the plan governs; where
> the design shows something the plan lacks, that is a question to settle, not a
> decision already taken. Recorded 2026-08-31.

- Canvas: `https://claude.ai/design/p/afc56bdd-88ec-478e-91a7-ebec712d872c`
- Source as incorporated: [`../design/memoria-desktop.dc.html`](../design/memoria-desktop.dc.html)
  (canvas source; it needs the canvas runtime and is not a standalone page)

The scenario it renders is part 18's walkthrough: the acquisition, Bob's
foreknowledge, `CLM-0041`, Chapter 2 ¶7, and the "12 manuscript impacts found after
chronology revision" of §21. It is a picture of the plan's own example, not a new one.

Six screens, two overlays, one persistent shell.

---

## 19.1 The shell

A 232px sidebar is always present. Everything else is one main column.

**Identity** — "Memoria" in Newsreader, and beneath it `THE ARCHIVE · 2004–2019` in
mono. A `⌕` glyph opens the global search dialog (§19.9).

**Destinations** — two: **Ask Memoria** and **Review**, the latter carrying a maroon
count badge (`12`). Selection is a 3px maroon left bar plus a sand background.

**Three trees**, each collapsible, each with its own affordance for adding:

| Tree | Contents in the design | Add affordance |
|---|---|---|
| `MANUSCRIPT` | Ch 2 — The Call (§2.1 Thursday, §2.2 The board letter, §2.3 An hour with Bob); Ch 5 — Signatures (§5.1 The filing, §5.2 Managing Bob); Ch 8 — Aftermath (§8.1 The announcement, §8.2 Cleveland, §8.3 The Acquisition) | `+` add chapter, `+ Add section` per chapter, `⠿` drag handles to reorder |
| `SUBJECTS` | Themes (Control, Loyalty, Inheritance) · Arcs (Bob relationship, Loss of institutional trust) · Timeline (Chronology, Acquisition timeline · 2011) · People (Bob, Alice) · Events (The acquisition, The resignation) · Claims (CLM-0041 · Bob's foreknowledge, CLM-0057 · Freedom as exposure) | `+` per subject adds an entry; `+ New subject` adds a subject |
| `SOURCES` | Primary sources `2,847` (Journals · 2004–2019, Email exports, Messages, Transcripts & documents) · Conversations `184` (SES-20260912 · control theme correction, SES-20261018 · acquisition timeline, SES-20261103 · ch 2 rewrite) | `+` add sources, `+ Add sources…` |

**Footer** — `⚙ Settings`, `✉ Feedback`, and a green status dot reading
**"Curator idle · last pass 09:41"**.

---

## 19.2 Ask Memoria

The home screen, and the only one with a second rail.

**Conversations rail** (264px): `CONVERSATIONS` header with `+ New`, then a list where
each entry is a two-line serif title plus a mono-ish meta line — "Today · book-wide",
"Yesterday · Chapter 6", "Nov 28 · research", "Sep 12 · Theme · Control",
"Oct 18 · § 8.3". The selected conversation gets a card background and a maroon
inset bar.

**Main column** (760px): "Ask Memoria / Book-wide conversation · the whole archive is
in reach". The transcript alternates:

- **Author turns** — right-aligned sand bubbles, serif, e.g. *"What changed in my
  understanding of Bob between 2011 and 2014?"*
- **Memoria turns** — left, serif at 16.5/1.62, with **inline citation chips**
  (`SRC-0184 ¶17`) set in mono on sand; clicking one opens the slide-over source
  panel, hover inverts it to maroon.
- **A scope note** in a left-ruled grey block: *"Searched July 2011 – June 2014
  journals and Bob-linked email; compared contemporaneous entries against your 2018
  recollections. I did not search unrelated correspondence from that period."*
- **An `IN THE MANUSCRIPT` row** — chips linking to `Ch 2 ¶7 — the call`,
  `Ch 5 ¶12 — managing Bob`, closed by an amber gap note: *"· the 2012 shift in
  language is not yet in the draft"*.

The second turn additionally shows:

- **The activity log** — mono lines behind a left rule, exactly the §40.7 shape:
  `› searching 2011 email · "acquisition" + Bob aliases (Bob, Robert, R.) — 34 hits`,
  `› reading SRC-0184 ¶12–19 · journal, Jul 17 2011`,
  `› searching for disconfirming evidence · Jul–Sep 2011 — 3 candidates`,
  `› comparing contemporaneous vs. retrospective accounts`.
- **A verdict** — "**probably supported**, moderate confidence", with the reasoning
  about which documents are contemporaneous and which are retrospective.
- **A green confirmation** — `✓ Saved as research memo RES-20261018-003 · linked to
  CLM-0041`.

The composer is pinned at the bottom of the column: *"Ask anything about the book or
the archive…"* with a `⏎` key hint.

---

## 19.3 Review

"Draft-vs-archive audit · Chapter 2 · **nothing changes without your say-so**".

**Summary bar** — "**12 findings** after the chronology revision", then severity
counts (`4` high — factual conflicts, `5` medium — stale framing, `3` low), then a
dark button: **Apply high-confidence fixes…**

**One expanded finding**, in a card with a 4px maroon left border:

```
Chapter 2 ¶7    CONTRADICTED                       IMP-20261103-004
The draft states Bob knew by July 15. Contemporaneous evidence
places his probable knowledge on July 18.
The paragraph treats his July 15 behavior as evidence of
foreknowledge; the revised timeline makes that reading
unavailable to the narrator at the time.
Supporting: SRC-0184 ¶17  SRC-0391 ¶4
Contradicting the draft: SRC-1102 ¶8
[View evidence] [Explain] [Preview diff]        [Rewrite] [Dismiss]
```

**Three collapsed findings** beneath it, one line each — verdict label, locator,
statement: `Chapter 3 ¶2 OVERSTATED`, `Chapter 4 ¶9 HINDSIGHT LEAKAGE`, and a dimmed
`Chapter 6 ¶14 SUPPORTED` ("The draft's account matches contemporaneous records").

---

## 19.4 Source viewer

`SRC-0184` · **Journal — July 17, 2011**, with a badge row: `CONTEMPORANEOUS` (green),
`recorded 2011-07-17`, `event 2011-07-17 · exact`, `journal · 2011.docx`.

The normalized text runs at 17px/1.72 with mono ¶ numbers in the margin. The cited
paragraph (`¶17`) is highlighted amber with an inset rule; the surrounding paragraphs
are dimmed but present.

Right rail (230px):

- **Open original ↗** as the primary dark action;
- `CITED BY` — `CLM-0041 · Bob's foreknowledge`, `Theme · Control`,
  `Arc · Bob relationship`, `RES-20261018-003`, `IMP-20261103-004`,
  `Chapter 8 source packet`;
- `PROVENANCE` — *"Normalized from 2011.docx, 'Entry dated July 17, 2011' ·
  normalizer v3 · anchors verified"*.

---

## 19.5 Section

`SECTION 8.3` · **The Acquisition**, with a maroon **Resume →** button top-right and
the line *"Last worked October 18, 2026 · six weeks ago · `LEGACY DRAFT`"*.

Prose is capped at 640px, Newsreader 17.5/1.75. Every paragraph highlights on hover
and is click-to-edit. The flagged paragraph sits on an amber ground with an inset
rule and carries an inline flag row:

```
⚑ May overstate Bob's foreknowledge after the chronology revision
                                  [Preview rewrite] [View impact]
```

Right rail (290px, sticky), one card per plan concept:

| Card | Content in the design |
|---|---|
| `PURPOSE` | "Show the first point at which the narrator realizes that Bob may have known substantially more than he admitted." |
| `CHECKPOINT` | "Opening works. Middle section overstates certainty…" + **Next** — "rewrite the final three paragraphs using only contemporaneous evidence." |
| `NEEDS ATTENTION` (amber) | "¶7 may overstate Bob's foreknowledge. View impact" |
| `DECISIONS` | "Do not reveal Alice's later account until §8.5. `DEC-0088`" · "Keep Bob's knowledge ambiguous here." |
| `OPEN QUESTION` | "Did Bob receive the July 14 document? · researching" |
| `RELEVANT` | chips: Control, Loyalty, Bob relationship, CLM-0041; links: Acquisition knowledge timeline, Bob / Alice account comparison |

---

## 19.6 Theme

`THEME` · **Control**, with a **💬 Discuss this** button.

**The interpretation card** leads with an `AUTHOR` badge (blue) and its provenance in
mono — `SES-20260912-1432 · T017` — then the interpretation itself in serif:
*"Control was never really about professional authority — that was a symptom. It is
about the fear of dependence: on Bob, on the institution, on being taken care of."*
Footer: *"Adopted from conversation, September 12 · see the exact turn · when did this
change?"*

**Two columns beneath:**

- `SUPPORTING CLAIMS` — `CLM-0041` — Bob probably knew before July 17 `INFERRED`;
  `CLM-0057` — The resignation was framed as freedom, felt as exposure `SOURCE`
- `AFFECTED PASSAGES` — Chapter 2 ¶14–17 (frames episode as ambition), Chapter 5 ¶12
  (likely framing conflict), Chapter 9 ¶4 (possible implication)

**`MEMORIA NOTE — 2026-10-18`** (amber card) closes the page: *"Later research cuts
against part of the reading above… **Your text has been left unchanged** — worth a
conversation? See RES-20261018-003 and SRC-1102 ¶8."*

That card is the ownership safe default drawn: the Curator annotates and asks; it
does not rewrite the author's interpretation.

---

## 19.7 Chapter editor

`CHAPTER 2` · **The Call**, **Resume →**, and *"Last worked November 3, 2026 ·
`LEGACY DRAFT` · **every edit saves as yours**"*.

Sections appear inline as mono rules — `§ 2.1 · THURSDAY`, `§ 2.2 · THE BOARD LETTER`,
`§ 2.3 · AN HOUR WITH BOB` — rather than as separate pages. The flagged paragraph in
§2.2 carries *"⚑ May conflict with the revised timeline (knowledge likely July 18)"*
with `[Preview rewrite] [Explain]`.

**Editing** is paragraph-at-a-time. Clicking a paragraph (`✎ click to edit`) turns it
into a bordered editable box with `Save` / `Cancel` and, aligned right:

```
will commit as author-authored · supreme
```

After saving:

```
✓ Saved as your edit · commit d41f2a9 · the Curator may ask whether
  this changes the Bob arc
```

The right rail is the same card stack as §19.5, scoped to the chapter. The chapter
ends on a mono rule: `END OF CHAPTER 2`.

---

## 19.8 Search

A 620px dialog over a scrim, query `Bob acquisition july`. Results are **grouped by
layer**, each group a card with a coloured left border and tinted header:

| Group | Colour | Glyph | Count line |
|---|---|---|---|
| `MANUSCRIPT` | maroon `#7a3327` | `✎` | 3 passages |
| `SUBJECTS` | blue `#3d5a78` | `◈` | 4 records |
| `SOURCES` | green `#4c5c3c` | `▤` | 34 records · evidence |

Each hit is a mono locator (`Ch 2 ¶7`, `§ 8.3`, `Theme · Control`, `CLM-0041`,
`SRC-0184 ¶17`) plus a snippet with matched terms highlighted; source hits append
`journal · 2011-07-17`. The sources group ends on:

```
31 more · refine with filters — dates, people, contemporaneous only
```

---

## 19.9 The slide-over source panel — the flagship interaction

Clicking any citation chip slides a 440px panel in from the right (0.22s) over a
scrim that starts at x=232, so the sidebar stays lit. The panel shows the source id
and attribution badge, the title, `recorded {date} · {type} · {origin}`, the
paragraphs with the cited one highlighted, and a two-button footer:
**Open full source** / **Open original ↗**.

The point of it: **checking a citation never costs you your place**. The full source
viewer (§19.4) remains available from inside the panel.

The canvas exposes this as an explicit, unresolved design choice — a prop
`citationPattern` with options `slide-over` (default) and `full-screen`, switchable
on the canvas.

---

## 19.10 Visual system and vocabulary

**Palette**

```text
page      #f6f2ea    panel/sand #efe9dd    card    #fdfbf7    rail  #f4f0e7
hover     #e6decd    borders    #ddd3c0 · #e2d9c6 · #ece4d4 · #cdbfa4
ink       #241f18    body       #33291d    second. #6b6152    muted #8a7f6d
faint     #a99d88
maroon    #7a3327    selection, primary-action hover, MANUSCRIPT layer
blue      #3d5a78    links, AUTHOR attribution, INTERPRETATION layer
green     #4c5c3c on #e4ead9   contemporaneous, confirmations, SOURCES layer
amber     #a8762a on #f3e6c8 / #fbf4e4   citation chips, flags, attention, curator note
```

The three layer colours are load-bearing information design, not decoration: the same
maroon/blue/green identify manuscript, subjects and evidence in the sidebar,
the search results, the badges and the card borders.

**Type** — Newsreader for prose and titles; IBM Plex Mono for identifiers, section
labels, ¶ numbers and the activity log; system-ui for chrome and controls. Chrome
14px; prose 16.5–17.5px at 1.62–1.75, measure capped at 640px. Radii 6–10px, 1px
borders, 3px inset left rules for emphasis, 3–4px left bars for selection and
severity.

**Identifier forms the design puts on screen**

```text
SRC-0184 ¶17              source + paragraph
CLM-0041                  claim
DEC-0088                  decision
RES-20261018-003          research memo, date-stamped
IMP-20261103-004          manuscript impact, date-stamped
SES-20260912-1432 · T017  session + transcript anchor
commit d41f2a9            the git commit for an author edit
```

**Badges** — `CONTEMPORANEOUS`, `AUTHOR`, `SOURCE`, `INFERRED`, `LEGACY DRAFT`.
**Finding verdicts** — `CONTRADICTED`, `OVERSTATED`, `HINDSIGHT LEAKAGE`, `SUPPORTED`.
**Confidence** is written in words: "probably supported, moderate confidence".

---

## 19.11 How this sits against the rest of the plan

**Rendered directly from the plan.**

- All six §40.3 surfaces exist: Ask Memoria, Section, Source viewer, Theme, Research
  conversation (as the activity log inside Ask Memoria), Review.
- §33 search-scope honesty appears twice — as the "I did not search…" note in an
  answer, and as the filter line under the search results.
- §40.7 streamed activity is the mono `›` log, in the plan's own wording.
- §1.7 supremacy is on screen as "will commit as author-authored · supreme".
- The part 08 safe default — the Curator does not rewrite prose a human has touched —
  is the `MEMORIA NOTE` card in §19.6.
- §21 authorization is the Review header: "nothing changes without your say-so".

**Added beyond §40, which specifies surfaces but no navigation.**

- The persistent three-tree sidebar as primary navigation, mirroring the repository's
  own division into manuscript / interpretation / sources.
- Cross-layer global search, colour-coded by layer.
- The slide-over citation panel.
- A chapter-level editor with click-to-edit paragraphs.
- Manuscript structure editing in the sidebar: add chapter, add section, drag to
  reorder. **Adopted 2026-08-31**: there is no `outline.md`, so the ordered tree *is*
  the outline and reordering renumbers directories; §4's stable IDs keep references
  intact. See part 04 §2.1.
- `Timeline` as a sixth group. **Adopted 2026-08-31**: Timeline is a built-in subject,
  and §04's `chronology.md` is an entry under it.
- A browsable conversation history, scoped per §31 mode ("book-wide", "Chapter 6",
  "research", "Theme · Control", "§ 8.3"). The plan records sessions; it never
  offers them back as a list to return to.
- Entry points from an object into a conversation about it: **💬 Discuss this** on a
  Theme, "see the exact turn", "when did this change?". `trace()` and `backlinks()`
  exist as tools; these affordances do not.
- Hand-creation from the UI — `+` on each group, and `+ New group`. **Adopted
  2026-08-31** as `+ New subject`, with manual entry creation on any subject; see
  part 06 §8.4.
- A `SUPPORTED` verdict, and severity worded as a diagnosis. **Superseded
  2026-08-31**: findings carry no category at all. See part 06 §8.10 and the banner
  at the head of this part.
- A `LEGACY DRAFT` badge on pre-Memoria manuscript text. **Resolved 2026-08-31**: it is
  not a state of the prose but of the **brief** — one drafted by summarizing existing
  prose and not yet confirmed by the author. §3 needs no new class. See part 04 §2.1.
- A Curator status line. **Adopted 2026-08-31** in a different form: what the interface
  surfaces is the **not current** count — *"142 paragraphs not current · 12 stale since
  you revised Control · Audit section"* — which is free to compute and is the trigger
  for the audit rather than a report on a background pass. There is no background pass.
- The `CHECKPOINT` card and its *"Next — rewrite the final three paragraphs"*.
  **Superseded 2026-08-31**: the checkpoint is removed entirely (part 12 §39).
  `Resume →` becomes "open a session on this section"; *"Last worked October 18"*
  survives because it is a git fact. Of §19.5's six right-rail cards, only `PURPOSE`
  reads a file — it reads the brief — and the other five compose live.
- `Settings` and `Feedback`. **Settings adopted 2026-09-04** (ADR-0009): the
  footer's `⚙ Settings` opens a dialog whose first setting is the writing style, a
  durable file the dialog edits through the write path. **Its second row, the same
  day** (ADR-0010): Model — the switch for direct runs, the model id and the API key,
  machine-local and never a durable file. `Feedback` stays unresolved.

**Runs ahead of decisions that are still open. Recorded, not resolved.**

- **Ask Memoria is the home screen** and the flagship of the design. `poc-plan.md` §5
  defers it as the one surface needing a model driver. This part does not change that
  reduction; it records that the design assumes it.
- **The Review queue is drawn as an inbox** the Curator filled unasked — "twelve
  findings after the chronology revision". **Superseded 2026-08-31**: audits run only
  on demand, so Review is the results view for an audit the author asked for, reached
  from the section or chapter button or from a highlighted passage. Invariant 8 is
  amended accordingly.
- **In-app prose editing** sits against §40.4 ("do not depend on a sophisticated
  rich-text editor") and the PoC's "Obsidian is the editor". The design's editor is
  paragraph-at-a-time rather than rich text, but it is still a second write path into
  the manuscript, and it is what the reduced §40.6 stale-revision check would have to
  cover.
- **Every locator on screen** — `Ch 2 ¶7`, `SRC-0184 ¶17`, `Chapter 2 ¶14–17`.
  **Resolved 2026-08-31, and the UI is unblocked.** Nothing durable points at a
  passage (part 04 §4.1): source locators are stable because evidence is immutable,
  and manuscript locators are computed per view from the index and from `git blame`.
  A locator is display state with the lifetime of one render, never a stored pointer.
- **Review actions differ from §40.3's list.** The card offers View evidence, Explain,
  Preview diff, Rewrite, Dismiss; `Apply` is not a per-finding action but the batch
  **Apply high-confidence fixes…** in the summary bar.
- **Section view** does not show §40.3's `Source packet` or `Unresolved impacts` as
  blocks; the source packet appears only as a backlink on the source page ("Chapter 8
  source packet"), and unresolved impacts are folded into `NEEDS ATTENTION`.
- **Drag-to-reorder chapters** implies manuscript structure is editable from the app.
  Nothing in the plan describes that operation.
- **Identifier width.** `IMP-20261103-004` appears on the finding card and in the
  vocabulary list. **Superseded 2026-08-31**: impact records do not exist, findings are
  identified by their disagreement set, and `IMP-` is gone from §4. The remaining id
  forms on screen come from §4 —
  `RES-20261018-003`, `DEC-0088`, `SES-20260912-1432 · T017` are the plan's own
  examples. The one divergence is `SRC-0184` against §4's `SRC-000184`.

---

<!-- Editorial note appended 2026-08-31, from the axis-system grilling session. -->
<!-- The section text above is unchanged. -->

## Editorial note — the Review verdicts, as a worked instance

The banner above applies to the whole part. §19.3 is recorded here as the worked
instance, because it is the screen most likely to be mistaken for a schema: its
verdicts — `CONTRADICTED`, `OVERSTATED`, `HINDSIGHT LEAKAGE`, `SUPPORTED` — and its
severity wording — `4 high · factual conflicts`, `5 medium · stale framing`,
`3 low` — read like enumerations. They are not. They must not drive curation data
structures.

Whether a review finding carries a category at all is **open**. §19.11 already
records that these four verdicts sit against §18's ten impact categories, and that
§19.3's severities are kinds of problem where §21's tiers are confidence levels.
Neither list is adopted by recording the other.

Two candidates the labels may be standing in for — which axis raised the finding,
and which resolutions the finding admits — are noted here as candidates only, and
are not decided.

---

<!-- Editorial note appended 2026-09-01, from the supplied-context grilling session. -->
<!-- The section text above is unchanged. -->

## Editorial note — the supplied-context surface, which the design does not have

The design draws §33's honesty for the **search** half — the scope note under an answer,
*"I did not search unrelated correspondence from that period"* — and §40.7's activity log
for the **retrieval** half. It draws nothing for the **assembly** half, which §33.1 calls
the harder case: an index reports nothing about its own recall.

**Adopted 2026-09-01**: a **supplied-context** surface, reporting for one session the
working context assembly produced and every read served since. Its shape, and the
reasoning that kept it clear of Invariant 1, are in `../adr/0001-supplied-context-is-inspectable.md`.
In summary: opened rather than watched, live only while open, an opener that carries no
count, countable domain units rather than tokens, and anything the budget truncated named
outright.

Its home in the PoC is the **Section view** (§19.5), because part 16 builds assembly and
that view together at M5 while **Ask Memoria never ships** (`poc-plan.md` §5). The
semantically right home is beside the scope note in §19.2, paired with the sibling
obligation it discharges — that is a second opener onto the same surface, and it arrives
with Ask Memoria, post-PoC.

This is the second line in §19.11's "runs ahead of decisions" list to resolve toward
*more* interface rather than less, after `+ New subject`. The design was not wrong to
omit it; the plan had simply never said what "assembly must report what it resolved"
looked like on a screen.
