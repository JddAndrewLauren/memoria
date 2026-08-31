<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 19, 20, 21, 36, 37, 38 of the original memoria-plan.md -->

# 19. Manuscript Authorization

Memoria recognizes three levels of manuscript authority.

## 19.1 Autonomous reading and analysis

Memoria may read and reason over the manuscript whenever appropriate.

No authorization is required to detect:

- contradictions;
- stale interpretations;
- structural problems;
- continuity problems;
- potential improvements;
- downstream consequences of changes elsewhere.

---

## 19.2 Autonomous suggestions

Memoria may autonomously:

- create manuscript-impact records;
- explain why a passage may need attention;
- prepare candidate rewrites;
- generate diffs;
- rank suggested changes by confidence or importance.

Preparing prose is not the same as modifying canonical prose.

---

## 19.3 Authorized manuscript modification

Memoria may directly modify `draft.md` when the author explicitly authorizes the work.

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

A request to apply a defined batch of manuscript-impact suggestions authorizes that batch.

Memoria records the authorization boundary before writing.

---

---

# 20. Provenance of AI-Written Manuscript

AI-authored prose is first-class manuscript prose.

Memoria does not label it as lesser, temporary, or noncanonical merely because a model wrote it.

What matters is being able to reconstruct how it came to exist.

A canonical manuscript change made by AI should preserve, where applicable:

```text
manuscript location
previous text
new text
authorizing session + turn
triggering change or research
manuscript-impact record
source packet
relevant claims
relevant evidence
model/provider metadata
Git commit
```

For example:

```text
chapters/02/draft.md#p7

Written:
    2026-11-03

By:
    AI during SES-20261103-1041

Authorized by:
    SES-20261103-1041#T008
    "Rewrite it using the corrected timeline."

Triggered by:
    CHG-20261103-1024

Suggestion:
    IMP-20261103-004

Evidence:
    SRC-0184
    SRC-0391

Commit:
    31cb8d2
```

The useful question is not merely:

> Human or AI?

It is:

> **How did this passage get here?**

Memoria should answer that precisely.

---

---

# 21. Batch Authorization

Author supervision should not become approval-dialog theater.

Memoria may group related manuscript-impact suggestions.

For example:

```text
12 manuscript impacts found after chronology revision

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

Each resulting modification remains individually traceable to:

- its trigger;
- evidence;
- suggestion;
- authorization;
- Git change.

---

---

# 36. Manuscript Rules

The manuscript has exactly one canonical home:

```text
chapters/**/draft.md
```

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
- implement approved manuscript-impact suggestions.

The AI should have enough authority within the authorized scope to perform the actual work.

Memoria should not force the author to manually copy AI-generated text back into the manuscript.

The key restriction is:

> **The model may not independently decide that canonical prose should change and then apply that change without authorization.**

Analysis may be autonomous.

Recommendations may be autonomous.

Candidate patches may be autonomous.

Canonical manuscript modification is authorized.

---

---

# 38. Manuscript Change Workflow

The standard workflow is:

```text
Evidence / interpretation / author change
                  ↓
         Dependency analysis
                  ↓
         Manuscript impact scan
                  ↓
       Suggested change or patch
                  ↓
           Author decision
          ↙              ↘
       Reject          Authorize
                          ↓
                    AI modifies
                    canonical text
                          ↓
                    Git commit
                          ↓
                 Provenance record
                          ↓
                Curator coherence pass
```

Rejecting a suggestion is itself useful working state.

Memoria should avoid repeatedly proposing the same rejected change unless materially new evidence or interpretation emerges.

---

<!-- Editorial note appended 2026-08-31, when the desktop design was incorporated. -->
<!-- The section text above is unchanged. -->

## Editorial note — the desktop design

§21 is the Review summary bar, near-verbatim: **"Apply high-confidence fixes…"** over
*"4 high — factual conflicts, 5 medium — stale framing, 3 low."* §19.1–§19.2 autonomy
is the Curator having produced twelve findings unasked; §19.3 is the header line
*"nothing changes without your say-so."*

Two divergences worth recording:

- **The per-finding action set differs from §40.3's list.** The card offers
  View evidence, Explain, Preview diff, **Rewrite**, Dismiss. `Apply` is not on the
  card at all — it exists only as the batch action above.
- **The design edits prose in the app.** §1.7 supremacy is written on screen —
  *"will commit as author-authored · supreme"* beside Save, *"every edit saves as
  yours"* under the chapter title, and *"✓ Saved as your edit · commit d41f2a9"*
  after. That is a second write path into `chapters/**/draft.md`, which §19.3's
  authorization rules and the reduced §40.6 stale-revision check both have to cover.

Full reconciliation: [19. Desktop UI — as designed](19-desktop-ui.md) §19.11.
