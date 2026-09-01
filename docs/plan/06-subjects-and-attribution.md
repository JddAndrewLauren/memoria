<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 8, 9 of the original memoria-plan.md -->
<!-- §8 was REWRITTEN 2026-08-31 in the subject-system grilling session and is no -->
<!-- longer verbatim. The original five-object-type §8 is in _original-memoria-plan.md. -->
<!-- §8.2, §8.6, §8.12 and §9.5 revised 2026-08-31: ownership by badge. See part 08 §14. -->
<!-- §8.2 revised again 2026-08-31: match terms are the only alias store (part 05 §7). -->
<!-- §8.3 and §8.4 revised 2026-08-31: gathered-set recall and the promotion miss -->
<!-- rate are harness numbers (poc-plan §3, part 15 §43.14). -->
<!-- §9.2's CHG- example amended 2026-09-01 to a per-day sequence. ADR-0008. -->

# 8. The Subject System

A **subject** is a named dimension along which the archive connects to the book.

It is one construct serving two jobs:

- an **index** a writing agent reads instead of the corpus;
- a **check** the Curator performs on new manuscript prose.

The built-in subjects are **People**, **Timeline**, **Events**, **Themes** and
**Arcs**. The author adds more at any time.

Subjects replace §8's original five fixed object types. Four of those types became
subjects; the fifth — claims — became something else, described in §8.9.

On screen the repository's three divisions are `MANUSCRIPT` / `SUBJECTS` /
`SOURCES`, and a new subject is added with `+ New subject`.

---

## 8.1 The subject prompt

Each subject carries a prompt holding three things.

**One — what counts as a match.**

```text
An entry under People represents a person.
```

Discovery, gathering and assembly all fall out of matching.

**Two — the subject's matching hazards**, because they are corpus-specific and a model
will not guess them:

```text
Match aliases, initials, honorifics, married names and location forms.
Do not merge people sharing a surname without corroboration.
```

§7's alias discipline and the hazards catalogued in the evidence repo's own recon —
one person named under several forms, several people sharing a surname — are what
this exists to carry. The hazards are stated as classes here; their instances come
from whatever archive is ingested.

**Three — the audit questions this subject asks of manuscript prose.**

```text
Does the passage contradict a settled fact about this person?
Does it mischaracterize them under the current reading?
```

**Every audit question in the system belongs to a subject. There is no central list.**
§17's fixed list of impact questions is withdrawn; each question moved onto the subject
that can answer it. A subject the author adds is not finished until it says what it
asks, which is §1.11 applied to checks as well as to structure — the check earns its
existence where the dimension does.

This matters most for the subjects whose entries hold a reading rather than facts.
"Compare the prose against what the entry contains" is a workable instruction for
People and Events and an empty one for Themes, where the entry holds an interpretation
and the question that matters is §22's: *is the framing still in step?* No amount of
matching produces that question, which is why it had to be stated.

**Four — whether the subject auto-promotes** (added 2026-09-01, ADR-0005).

```text
auto-promote: no
```

Off means candidates above the recurrence filter wait, ranked, for a one-key
promotion. On means they become entries with an empty overlay and the author demotes
what is wrong. Themes and Arcs ship off, because a wrong entry there sits in Tier 2 and
the audit until noticed; a subject like Locations may say yes. To the extraction
(§8.4) a subject is an entity type: the match definition and hazards are what it is
handed.

The whole prompt is a few lines per subject, not a schema.

---

## 8.2 Entries

An **entry** is one instance under a subject: Bob under People, the acquisition
under Events, control under Themes.

The subject says what a kind of entry is. The entry carries four things, and they do
not share an authority:

| | What it is | Authority |
|---|---|---|
| **Body** | testimony and badged statements about this entry | shared territory; ownership is carried by the badge — see below |
| **Match terms** | how *this* entry is referenced, beyond the subject default | the author's |
| **Settlements** | recorded resolutions of surfaced conflicts | attributable author acts |
| **Gathered set** | the sources this subject matched to this entry | derived and rebuildable |

Match terms are the system's **only alias store**: §7 withdrew the canonical alias
map, and the discipline that spans entries — do not merge people sharing a surname —
is a subject hazard (§8.1), not a map row.

**The body is shared territory, and the §9 badge is the ownership marker.** There is
no separate machine region, and nothing infers authorship from git blame (§14): who
may write a statement, and who may revise it, is read off the statement itself.

| Statement | Who writes it | Who revises it |
|---|---|---|
| unbadged **testimony** | the author's hand only — the Curator never writes unbadged text, no exceptions | the author |
| `[author]` | the Curator, on a citing transcript turn; §13.1's bar decides `[author]` against `[open]` | the Curator, only on a new citing turn |
| `[source]` / `[inferred]` / `[open]` | the Curator, freely (so may the author) | the Curator, freely — unless the statement is human-touched (§14.2) |
| a **settlement** | click-authorized (§8.7) | a new settlement |

The **audit-visible body** is testimony, settlements, and the `[author]`, `[source]`
and `[inferred]` statements. It is what assembly loads (§32's Tier 2, badges visible)
and what the audit compares prose against; a finding that disagrees with a `[source]`
or `[inferred]` statement ranks below one that disagrees with testimony or a
settlement, through §8.10's confidence ordering. `[open]` lines and Memoria notes
(§14.2) sit outside it — excluded from write-side assembly and from the audit,
retrievable in Think and Research modes.

An entry with an **empty gathered set is a valid state**, not an error. An entry may
exist entirely on author testimony — someone the archive barely names, or an entry
created before any ingest. Nothing prunes it. Invariant 11 applies.

---

## 8.3 The gathered set

The gathered set is derived. It asserts nothing, so it carries no attribution, and
`memoria rebuild` regenerates it.

Over it sits a small **curated overlay** of two author acts:

```text
pin      this source belongs to this entry, whatever the pass finds
exclude  this source does not (wrong Bob)
```

Pins and exclusions are attributable and survive a rebuild. They are the same
machinery §15 requires for human deletions and that `poc-plan.md` §3 requires from
the first Curator pass.

**Recall is the central risk of the whole design.** A source that never joins an
entry's gathered set is invisible to a writing agent, which cannot know it is
missing. This is worse than search under §33: a search reports its query; an index
reports nothing about its own completeness. The PoC's 348 resolved
cross-references measure it directly — **gathered-set recall** over those links, a
set metric asking whether the passage is in the set at all rather than where it
ranks, *is* the measure of whether the index is complete enough to write from. It
is the second of the benchmark harness's three numbers (`poc-plan.md` §3, part 15
§43.14).

---

## 8.4 Candidates and promotion

The gathered set exists **before the entry does**.

~~A subject matches the corpus continuously and holds a **candidate** for everything it
finds.~~ **Revised 2026-09-01** (ADR-0005): candidates come from the **extraction**, an
author-launched model pass over every paragraph that records, per paragraph, the
entries it places, the surface forms it cannot place, and the relations between them,
and proposes from that the candidates under every subject, the **clusters** it offers
under Themes and Arcs, and match terms for the entries it placed. It is the one
candidate engine; the lexical pass it replaces survives only as gathering (§8.3), which
stays deterministic over match terms. Candidates are index rows. They never load into a
session.

The Curator proposes candidates for promotion; the author promotes — unless the
subject declares **auto-promote** (§8.1), in which case candidates above the recurrence
filter become entries on their own. An **entry is a promoted candidate**, and promotion
is what earns it author text, settlements and a seat in the working context.

Consequences:

- **proposing costs nothing** — the candidate is already indexed;
- **promoting is instant** — the entry materializes with its gathered set already
  built;
- **assembly never dead-ends** — a declared scope naming something with no entry
  falls back to the candidate, and says that it did;
- **context is safe** — unpromoted candidates never enter a session.

Recurrence is a strong filter: on any archive, most distinct capitalized-name
candidates appear once or twice, and requiring five or more collapses the list by
an order of magnitude. The promotable set is dozens, not hundreds.

The collapse faces the other way too: a threshold that makes promotion tractable
discards real entries that happen to be mentioned rarely, so the filter is a
guaranteed miss generator. This was to be quantified by the benchmark's
**promotion miss rate**, which was withdrawn with the Thoreau corpus
(`../open-problems.md` §2.4). Until an archive with known ground truth exists the
mitigation is structural rather than measured: **candidates the filter rejects
stay enumerable**, so the misses are countable rather than invisible.

The author may also **create an entry manually**, on any subject, at any time. A
manually created entry has no matched history, so it needs its own match terms
before a subject can gather for it.

**A promoted cluster becomes a Theme or Arc whose match terms are entries and
relations** — `Bob`, `the acquisition`, `Bob -> pressures -> author` — and it gathers
the paragraphs where those co-occur, joined over the extraction's placements. It does
not remember the cluster it came from; cluster identity does not survive
re-clustering, and match terms do. The author tunes a Theme the way they tune a
person.

---

## 8.5 The two consumers

Neither consumer writes entries.

**Assembly** — write-side. A section declares its scope in the author's own terms:

```text
Covers June 1839 to October 1841, and my interactions with Bob about
the conflict in the capital.
```

Assembly resolves that declaration through the subjects into a working context: the
named entries' audit-visible bodies (§8.2), loaded with badges visible; their gathered
sets, queryable; everything else, retrieved if it becomes relevant. This is §32's
Tier 2, declared rather than inferred.

Assembly is not curation. It happens at write time, in service of a session.

**Audit** — check-side. Manuscript prose, hand-written or AI-written, is evaluated
against the entries, asking the audit questions each subject declares (§8.1). Its
scope is the entries the section's brief resolves to, which makes the brief the
audit's contract as well as assembly's.

Scope is inspectable and is reported in terms of entries, not abstract check types:

> Compared against Bob, the acquisition, and the 1837–1846 timeline.
> Themes did not run.

That is Invariant 10 applied to curation, which the plan does not otherwise do.

**The audit runs only on demand.** A button on a section or a chapter, or on a
highlighted passage. Nothing evaluates prose unasked — see §8.12.

---

## 8.6 Author testimony

Author text in an entry is **self-sourcing**. The entry is its own record.

```markdown
Bob was born in 1962 in Cleveland. Heavyset, slow-spoken.
```

No badge, no citation, no basis. This terminates provenance legitimately: §1.4's
terminal records are original source evidence **and attributable author actions**,
and writing in an entry is an attributable author act with a commit behind it.

**Author testimony outranks documentary evidence.** If the notes say Bob seemed to be
in his mid-thirties and the entry says he was born in 1962, he was born in 1962. The
conflict is surfaced; it is never resolved against the author. This is §1.7 applied
to fact as well as to reading, and it deliberately inverts the
contemporaneous-beats-retrospective instinct the rest of the system leans on: a
contemporaneous note records an *impression*, where the author may hold the fact.

The cost, accepted knowingly: **the audit cannot flag author misremembering as an
error.** It can only report the divergence. The value therefore lives entirely in
when and where that divergence is shown.

**Testimony is never machine-written.** An AI-drafted statement the author approves
stays badged: approval authorizes recording, not belief, and promoting compiled facts
into unbadged supremacy would launder them past every future audit — §8.8's reasoning,
one level up. To claim a statement as their own, the author strips its badge; that is
an attributable author act with a commit behind it.

One boundary: **craft direction is not testimony.** "Bob should read as unreliable
early on" is not a claim about the world, must never be checked against evidence, and
must never reach a writing agent as fact. It belongs in the section's **brief**
(§2.1), not an entry — and so does a dismissal worth remembering, since "the narrator
overstates Bob's age in the opening scene on purpose" is craft direction rather than a
fact about the world.

---

## 8.7 Settlements

A **settlement** is the author's recorded resolution of a surfaced conflict.

It is one action, available in either direction, and it records what was chosen,
against what, and when:

```markdown
birth year 1962 — chosen over SRC-0184 ¶12, 2026-08-31
```

A settlement is stored **on the entry** and silences every downstream passage that
relies on it, so it needs no manuscript anchor: the passage where the conflict
surfaced is provenance of the act, recorded as the session it happened in. §15's
dismissal memory is the mechanism.

Resolving toward the manuscript updates the entry. That is a Curator write into
human-supreme text, and it is legitimate **only because the author's click
authorizes it** — §51's principle applied one level below prose. Autonomous
harvesting of manuscript prose into entries remains forbidden, for the reasons in
§8.8.

---

## 8.8 Structure accretes from settlements

Entry facts are **prose by default**.

A **structured, machine-checkable fact is created only where a conflict has actually
been settled.** No schema up front. Fields are earned one resolved conflict at a
time, which is §1.11 followed literally rather than invoked.

This also bounds the cost of the audit. Facts nobody has fought about are compared as
prose; facts that have been settled are compared as values. The expensive comparison
shrinks as the book matures.

**Manuscript prose never updates an entry on its own.** Narrative prose is not
assertion — §17 asks whether a passage reveals information too early, and §19.5's
`DEC-0088` says "keep Bob's knowledge ambiguous here." The book deliberately says
things the author does not believe and withholds things they do. A Curator that
harvested prose as assertion would learn the book's tactical choices as convictions,
and where the passage was AI-drafted under §1.10 authorization it would launder
generated text into author belief, defeating Invariant 6 through a side door. The
authorization was to write prose, not to form a belief.

---

## 8.9 Claims are the accretion layer

Claims are **not** a subject.

Every other type names a thing in the world or the book — a person, an event, a
period, a recurring concern, a transformation. A claim names a **proposition with a
truth value and a confidence**. Bob is not an assertion; `CLM-0041` is.

A settlement *is* a claim. It has a proposition, a status, supporting and
contradicting evidence, a date, and reasoning — which is §8.5's original claim
template exactly.

So claims are what settlements accrete into: a propositional layer cutting across
every subject. This supplies the mechanism §8.5 always lacked. It said claims
"become first-class when they are important, contested, repeatedly referenced,"
without saying who notices or when. A claim is now born at the moment a disagreement
was contested enough that the author had to settle it.

Claims remain a superset of settlements — the author may still assert one outright,
with no conflict behind it. The original claim file format is unchanged:

```markdown
# CLM-0041

## Claim

Bob probably knew about the acquisition before July 17.

## Status

inferred

## Confidence

moderate

## Supporting evidence

- [SRC-00184 ¶17](...)

## Contradicting evidence

- [SRC-01102 ¶8](...)

## Reasoning

...
```

§26's `trace()` is unaffected and improved: a settlement-born claim records the
`THEME -> CLM -> SRC` chain as a byproduct of the author clicking, rather than
requiring someone to construct it afterwards.

---

## 8.10 Findings carry no category

A **finding** is a disagreement set plus prose saying how they disagree.

```text
{ chapters/02 ¶7, SUB-people/bob, SRC-0184 }
The draft has Bob at fifty-nine. The entry gives 1962, which makes him
forty-nine. SRC-0184 puts him in his mid-thirties.
```

Everything else derives from the set:

- **available actions** — a passage and a source admits rewrite or exclude; a
  passage, an entry and a source admits settlement in three directions; a passage and
  a decision admits rewrite or revise the decision. Finding types are never
  enumerated; the set is read.
- **which subject raised it** — already known, since the audit is subject-bounded.
- **ordering** — confidence, per §21's tiers. Not severity, and not kind of problem.
- **identity** — the set *is* the identity, which is what §15 needs in order not to
  re-raise a settled disagreement. No finding IDs to mint or drift.

The verdict vocabulary in §19.3 — `CONTRADICTED`, `OVERSTATED`, `HINDSIGHT LEAKAGE`,
`SUPPORTED` — is illustrative example content and is **not** a specification. See the
banner at the head of part 19.

---

## 8.11 Appearances

**Appearances** are the manuscript passages an entry turns out to touch, with a short
note on how. §19.6's `AFFECTED PASSAGES` card and §27's `backlinks()` both render them.

They are derived, rebuildable, held only in the index, and never authoritative. They
are kept separate from the gathered set on purpose, and the reason is §8.8's: a
gathered set is **evidence you write from**, while appearances are **prose you have
already written**. Merging them would put manuscript text into the structure a writing
agent reads as material, and the book deliberately says things the author does not
believe. Two names keep that door shut.

Appearances carry **no pin or exclude overlay**. An author act against one passage
would be a durable pointer into mutable prose, which §4.1 forbids; the overlay stays a
gathered-set affordance over immutable sources, where anchors are stable. An
appearance the author wants suppressed is a sentence in the brief.

**Two engines, one name.** For People, Timeline and Events, an appearance is a match —
names, aliases, dates — using the same lexical machinery as the gathered set. For
Themes and Arcs, *gathering* now works — their match terms name entries and relations
and the set is a co-occurrence join (§8.4, 2026-09-01) — but an appearance still does
not, because manuscript prose is not extracted and there are no match terms that work
against it: a paragraph about the fear of
dependence need not contain any of the entry's words, and §19.6's card carries
judgements — *"frames episode as ambition"* — rather than matches. Those require a
model reading the passage against the entry.

**Recall is unreported here too**, and worse than in §8.3. An appearances list over two
thousand paragraphs will miss some and cannot say which. For People that can be
sanity-checked against aliases; for Control there is no ground truth at all.

---

## 8.12 Memoization, and when anything runs

Both the appearances pass and the audit evaluate the same unit: one paragraph against
one entry. Every such judgement is cached on the things it depends on — and the two
kinds of judgement do not depend on the same things.

An **engagement judgement** — the appearances pass — asks whether the paragraph
engages the entry. It depends on three inputs:

```text
key    = hash(paragraph text)
       + hash(entry audit-visible body)
       + hash(subject prompt)
value  = { engages: yes/no, note: "frames episode as ambition" }
```

An **audit verdict** asks the subject's questions of the paragraph, and its answer can
turn on evidence — findings cite sources (§8.10). Its key therefore carries a fourth
hash:

```text
key    = the three above
       + hash(gathered-set membership, pins and exclusions applied)
value  = clear, or a finding: the disagreement-set members, the prose
         stating how they disagree, and a confidence (§8.10)
```

The **extraction** (§8.4) is memoized the same way, one paragraph at a time:

```text
key    = hash(paragraph text)
       + hash(extraction prompt)
       + hash(every subject prompt)
value  = { placements, unplaced surface forms, relations }
```

Match terms are deliberately **not** in the key: placement against them is a
deterministic rebuild step over the cached value, so accepting a proposed term never
re-reads the corpus. Changing a subject prompt does, for every paragraph, which is the
same price §8.1 already puts on editing a subject.

Membership, not content: evidence is immutable (Invariant 3), so only *which* sources
belong to an entry can change. A newly ingested source that joins the gathered set
stales the entry's audit verdicts — never its engagement judgements, whose answers do
not depend on evidence and would otherwise churn on every ingest. A pin or an
exclusion stales audit verdicts too, deliberately: a finding that leaned on an
excluded source should be recomputed. One cache, two key compositions.

The audit-visible body (§8.2) includes settlements. `[open]` lines and Memoria notes
sit outside it, so appending either invalidates nothing. Under ownership by badge the
body hash often moves when the Curator folds new evidence into `[source]` statements,
staling the same verdicts twice over — harmless, since both hashes point at the same
re-evaluation.

Three consequences follow, and they replace a good deal of machinery.

**One — the audit and manuscript impact analysis are the same mechanism.** The audit
fires when the prose changes; §17's impact analysis fires when an entry changes. Both
recompute the same value from the same key. There are not two systems, and part 09's
dependency graph and impact scan collapse into this one. The rule is not "only new
text" but **only changed inputs**: Memoria never re-derives a judgement whose inputs
have not moved.

**Two — invalidation is impact analysis.** Editing the Control entry invalidates every
cached Control judgement in the book. The set of passages needing re-evaluation *is*
the answer to "what does this change affect", and the difference between the old and
new judgements *is* the impact set. Editing a theme is expensive in exactly the way it
should be: it re-reads the book against your revised reading.

**Three — staleness is free, and evaluation is not automatic.** Deciding that a
judgement is missing or stale is a hash comparison: no model, no cost, known across the
whole manuscript at all times. Producing the judgement is a model call and **happens
only when the author asks for it.** So Memoria always knows what is **not current** and
never audits unasked.

A paragraph is not current when it has never been audited, when it has been edited
since, when an entry or subject prompt it touches has changed since, or — for audit
verdicts — when a source has joined or left a gathered set it was judged against. All
four are cache misses and are shown identically — a quiet tint on the paragraph —
with the distinction carried in the summary line above the prose, where it can be
acted on:

```text
142 paragraphs not current · 12 stale since you revised Control ·
37 stale since 4 sources joined Bob · Audit section
```

There is no act that marks a stale count acknowledged without re-evaluating: the
count clears only through an audit. An acknowledgement affordance would be structure
with no earned existence (§1.11).

This trims **Invariant 8**. The invariant granted autonomy in observation, reasoning
and recommendation, reserving authorization for canonical authorship. Evaluation is no
longer autonomous. What remains autonomous is everything that needs no model: the
staleness map, §47's health report, and validation.

---

---

# 9. Attribution Model

Every durable interpretive statement must carry its epistemic status and provenance.

## 9.1 Source statements

```markdown
[source] Bob called on July 17.
— [SRC-00184 ¶17](...)
```

This means the cited source directly states or supports the assertion.

---

## 9.2 Author statements

```markdown
[author] I now think the conflict was primarily about autonomy.
— [SES-20260912-1432 T017](...)
```

or:

```markdown
[author] The conflict should be framed primarily around autonomy.
— [CHG-20261014-003](...)
```

The Curator must not turn the AI's suggestion into an `[author]` position merely
because the author discussed it.

There must be identifiable author evidence.

---

## 9.3 Inferred statements

```markdown
[inferred] Fear of losing control appears to intensify after the acquisition.

Basis:
- [SRC-00184 ¶17](...)
- [SES-20260912-1432 T017](...)
```

An inference should identify both its conclusion and its basis.

For important inferences, the reasoning should be preserved as a claim rather than
regenerated from scratch each time.

---

## 9.4 Open interpretations

Exploratory thinking should remain exploratory.

```markdown
[open] One possibility is that the later hostility reflects embarrassment
rather than betrayal.
```

An `[open]` idea is not part of the current accepted interpretation.

---

## 9.5 Author testimony needs no badge

There is deliberately **no fifth status**.

Author text in an entry (§8.6) is self-sourcing: the entry is the record, and §1.7
governs it. A badge would imply the statement rests on something else, when the
point is that it does not.

This holds because the Curator never writes unbadged text (§8.2): inside an entry
body, the absence of a badge *is* the attribution.

The date is carried by the commit, and by any settlement the statement is party to.
