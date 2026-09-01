<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 19, 20, 21, 36, 37, 38 of the original memoria-plan.md -->

# 19. Manuscript Authorization

Memoria recognizes three levels of manuscript authority.

## 19.1 Reading and analysis, on request

**Analysis of manuscript prose runs only when the author asks for it** — a button on a
section, a chapter, or a highlighted passage. This trims Invariant 8, which granted
autonomy in observation and reasoning; see part 06 §8.12. What stays autonomous is
everything that needs no model: which paragraphs are **not current**, §47's health
report, and §23's validation.

When an audit is requested, no further authorization is required to detect:

- contradictions;
- stale interpretations;
- structural problems;
- continuity problems;
- potential improvements;
- downstream consequences of changes elsewhere.

---

## 19.2 Suggestions

Within a requested audit, Memoria may without further authorization:

- explain why a passage may need attention;
- prepare candidate rewrites;
- generate diffs;
- rank findings by confidence.

No impact records are created; findings are derived and recomputed (part 09 §17).

Preparing prose is not the same as modifying canonical prose.

---

## 19.3 Authorized manuscript modification

Memoria may directly modify `draft.md` **or a brief** when the author explicitly
authorizes the work. Both are manuscript-class (§3), and both are author-supreme.

Authorization may occur through natural language:

```text
Rewrite that paragraph.

Apply this suggestion.

Fix those four factual conflicts.

Take a pass at chapter 2 using the revised Bob arc.

Draft section 8.3 from the source packet.

Apply all high-confidence chronology fixes, but only
show me suggestions for interpretive changes.
```

Authorization may also occur through interface actions such as:

```text
Apply
Rewrite
Accept selected
Apply high-confidence fixes
```

Authorization is scoped.

A request to rewrite one paragraph does not authorize unrelated changes elsewhere in the chapter.

A request to revise a chapter may authorize broad work within that chapter.

A request to apply a defined batch of findings authorizes that batch.

Memoria records the authorization boundary before writing.

**Briefs are authorized separately and never in a batch.** A brief is written by a
deliberate act on that brief — the author editing it, or a conversation whose purpose
is the brief, of which the most common form is Memoria interviewing the author about
what a new section is for and writing down the conclusion. A brief may also be drafted
by summarizing prose that already exists, which produces an *unconfirmed* brief (§2.1).
No finding card and no batch action may write one.

---

---

# 20. Provenance of AI-Written Manuscript

AI-authored prose is first-class manuscript prose.

Memoria does not label it as lesser, temporary, or noncanonical merely because a model wrote it.

What matters is being able to reconstruct how it came to exist.

**Provenance is composed, not stored.** Nothing durable points at a paragraph (§4.1),
and no per-passage provenance record is written. The chain is reconstructed on demand
by `trace()` (§26) from records that already exist:

```text
paragraph  --git blame-->  commit
commit     --commit trailer-->  session
session    --context-manifest.json (§33)-->  what was loaded to write from
session    --transcript.md #T017-->  the turn that authorized it
```

So the question "how did this passage get here?" is answered by walking backwards
through git and the session records, and it produces the same account the plan
previously asked Memoria to write down:

```text
chapters/02 ¶7

Written:
    2026-11-03

By:
    AI during SES-20261103-1041

Authorized by:
    SES-20261103-1041#T008
    "Rewrite it using the corrected timeline."

Assembled from:
    SUB-people/bob, SUB-timeline/chronology
    SRC-0184, SRC-0391

Commit:
    31cb8d2
```

What this account cannot do is survive heavy reflow: blame is always right about which
commit last touched a line and can be coarse about which paragraph that line belongs
to. That degradation is honest — it loses precision, never correctness — and it is the
same fragility part 08's ownership question already carries.

The useful question is not merely:

> Human or AI?

It is:

> **How did this passage get here?**

Memoria should answer that precisely.

---

---

# 21. Batch Authorization

Author supervision should not become approval-dialog theater.

Memoria may group related findings from an audit the author asked for.

For example:

```text
12 findings after auditing chapter 2

4 high confidence
    Direct factual contradictions

5 medium confidence
    Existing prose relies on superseded interpretations

3 low confidence
    Possible framing implications
```

The author may issue a scoped instruction such as:

> Rewrite the four high-confidence conflicts. Prepare diffs for the five medium-confidence changes. Leave the low-confidence ones alone.

Memoria may then modify all four canonical passages directly.

Each resulting modification remains individually traceable, by §20's composition, to
its trigger, its evidence, its authorizing turn and its Git change.

A batch may contain only prose rewrites. **No batch may write a brief** (§19.3).

---

---

# 36. Manuscript Rules

The manuscript's prose has exactly one canonical home:

```text
chapters/**/draft.md
```

and its intent has one more — the briefs `book.md`, `chapter.md` and `section.md`
(§2.1). Those two, plus stable IDs in frontmatter, are the manuscript layer's entire
durable footprint. There is no `state.md` and no `outline.md`.

There is no human manuscript and AI manuscript.

There is only the current canonical text.

Passages may have been:

- written directly by the author;
- drafted by AI at the author's request;
- generated from a research packet;
- heavily rewritten by AI;
- lightly polished by AI;
- written by AI and then substantially edited by the author;
- rewritten because a source, chronology, theme, arc, or claim changed.

These histories remain recoverable through Git and Memoria provenance.

External DOCX, PDF, or other formats are export artifacts rather than synchronized authorities.

---

---

# 37. AI Manuscript Authorship

AI manuscript authorship is explicitly in scope.

During an authorized operation, the model may:

- draft new prose;
- rewrite existing prose;
- restructure passages;
- move material;
- reconcile multiple drafts;
- incorporate source material;
- revise framing;
- improve continuity;
- adjust voice;
- shorten or expand;
- apply factual corrections;
- implement approved findings.

The AI should have enough authority within the authorized scope to perform the actual work.

Memoria should not force the author to manually copy AI-generated text back into the manuscript.

The key restriction is:

> **The model may not independently decide that canonical prose should change and then apply that change without authorization.**

Analysis is requested, not autonomous (§19.1).

Within a requested audit, recommendations and candidate patches need no further
authorization.

Canonical manuscript modification is authorized.

---

---

# 38. Manuscript Change Workflow

```text
Evidence / entry / subject-prompt change
                  |
                  v
      Judgements invalidated  (hash comparison, free)
                  |
                  v
      Paragraphs marked NOT CURRENT, with a count
                  |
        - - - the author asks for an audit - - -
                  |
                  v
              Findings
                  |
           Author decision
          /                \
     Decline              Authorize
        |                     |
        v                     v
  craft direction        AI modifies
  in the brief,          canonical text
  if worth keeping             |
                               v
                          Git commit
```

The left branch is where §15's dismissal memory now lives. A decline is not stored
against the passage — there is nothing durable to store it against (§4.1) — so a
decline worth remembering is written into the section's brief as craft direction:
*"the narrator overstates Bob's age in the opening scene on purpose."* Written that
way it is read by every future audit as part of the section's contract.

A decline **not** worth writing down will be raised again the next time that passage is
audited. That is the accepted cost of storing no passage pointers, and recurrence is
read as a signal that the brief or the entry is missing something rather than as noise
to suppress.

There is no separate provenance-record step: provenance is composed from the commit and
the session (§20).
