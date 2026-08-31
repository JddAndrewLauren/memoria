<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 8, 9 of the original memoria-plan.md -->
<!-- §8 was REWRITTEN 2026-08-31 in the subject-system grilling session and is no -->
<!-- longer verbatim. The original five-object-type §8 is in _original-memoria-plan.md. -->

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

Each subject carries a prompt with exactly one job: **define what counts as a match
on this subject.**

```text
An entry under People represents a person.
```

Discovery, gathering, assembly and audit all fall out of matching. There is no
separate check instruction, because the audit compares new prose against what an
entry actually contains.

The prompt should also state the subject's **matching hazards**, because they are
corpus-specific and a model will not guess them:

```text
Match aliases, initials, honorifics, married names and location forms.
Do not merge people sharing a surname without corroboration.
```

This is one or two lines per subject, not a schema. §7's alias discipline and the
hazards catalogued in `sources/raw/gutenberg/RECON.md` — Emerson under four location
forms, four Thoreaus sharing a surname — are what it exists to carry.

---

## 8.2 Entries

An **entry** is one instance under a subject: Bob under People, the acquisition
under Events, control under Themes.

The subject says what a kind of entry is. The entry carries four things, and they do
not share an authority:

| | What it is | Authority |
|---|---|---|
| **Author text** | what the author knows and thinks about this entry | the author's, and supreme |
| **Match terms** | how *this* entry is referenced, beyond the subject default | the author's |
| **Settlements** | recorded resolutions of surfaced conflicts | attributable author acts |
| **Gathered set** | the sources this subject matched to this entry | derived and rebuildable |

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
reports nothing about its own completeness. The PoC's 364 resolvable
cross-references measure it directly — recall@10 over those links *is* the measure
of whether the index is complete enough to write from.

---

## 8.4 Candidates and promotion

The gathered set exists **before the entry does**.

A subject matches the corpus continuously and holds a **candidate** for everything it
finds. Candidates are index rows. They never load into a session.

The Curator proposes candidates for promotion; the author promotes. An **entry is a
promoted candidate**, and promotion is what earns it author text, settlements and a
seat in the working context.

Consequences:

- **proposing costs nothing** — the candidate is already indexed;
- **promoting is instant** — the entry materializes with its gathered set already
  built;
- **assembly never dead-ends** — a declared scope naming something with no entry
  falls back to the candidate, and says that it did;
- **context is safe** — unpromoted candidates never enter a session.

Recurrence is a strong filter. On the PoC corpus, distinct capitalized-name
candidates run 516 / 638 / 1,066 per volume; those appearing five or more times run
9 / 18 / 36, against `RECON.md`'s ground truth of 43 distinct letter recipients.
The promotable set is dozens, not hundreds.

The author may also **create an entry manually**, on any subject, at any time. A
manually created entry has no matched history, so it needs its own match terms
before a subject can gather for it.

---

## 8.5 The two consumers

Neither consumer writes entries.

**Assembly** — write-side. A section declares its scope in the author's own terms:

```text
Covers June 1839 to October 1841, and my interactions with Bob about
the conflict in the capital.
```

Assembly resolves that declaration through the subjects into a working context: the
named entries' author text and settlements, loaded; their gathered sets, queryable;
everything else, retrieved if it becomes relevant. This is §32's Tier 2, declared
rather than inferred.

Assembly is not curation. It happens at write time, in service of a session.

**Audit** — check-side. New manuscript prose, hand-written or AI-written, is
evaluated against the entries, bounded by the subjects that exist.

The audit evaluates **only new text**. Its scope is inspectable and is reported in
terms of entries, not abstract check types:

> Compared against Bob, the acquisition, and the 1837–1846 timeline.
> Themes did not run.

That is Invariant 10 applied to curation, which the plan does not otherwise do.

One consequence to accept: the audit only checks what a subject covers. Of §17's
seven impact questions, six map onto subjects; *"does it reveal information earlier
than the narrative plan permits?"* does not, and has no home. See §9 of part 09.

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

One boundary: **craft direction is not testimony.** "Bob should read as unreliable
early on" is not a claim about the world, must never be checked against evidence, and
must never reach a writing agent as fact. It belongs in section state, not an entry.

---

## 8.7 Settlements

A **settlement** is the author's recorded resolution of a surfaced conflict.

It is one action, available in either direction, and it records what was chosen,
against what, and when:

```markdown
birth year 1962 — chosen over SRC-0184 ¶12, 2026-08-31
```

Downstream passages relying on a settlement inherit it and stay silent. §15's
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

## 8.11 Entries and manuscript passages

The edge between an entry and a passage is drawn twice, capturing two different
facts.

**Derived, by the audit.** Evaluating new prose determines which entries it touches.
This is a free byproduct of a pass that must run anyway, it works for all prose
regardless of authorship, and it records what a passage *turns out to be about*.

**Recorded, by assembly.** Where a writing agent worked from a declared scope, the
entries and sources it actually drew on are recorded. This is genuine write-time
provenance — what the passage was *written from* — and it is a fact about the past.

Where the two disagree, that is informative rather than a conflict: the agent was
handed Bob's entry and the paragraph came out about the acquisition.

The author is never required to cite manually.

**This narrows the §4 anchoring problem.** Derived edges recompute every pass, so
anchor drift is survivable — re-run the audit and get fresh edges, with nothing
silently stale. What genuinely needs durable passage identity is much smaller:
**settlements** and **write-time provenance**, both rare, deliberate, author-triggered
acts rather than bulk machine output. See the editorial note in part 04.

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
— [CHG-20261014-0917](...)
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

The date is carried by the commit, and by any settlement the statement is party to.
