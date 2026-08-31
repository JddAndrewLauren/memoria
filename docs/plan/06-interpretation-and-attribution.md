<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 8, 9 of the original memoria-plan.md -->

# 8. The Interpretation Layer

The interpretation layer is Memoria's maintained understanding of the book.

It consists initially of five major object types.

## 8.1 Themes

Examples:

```text
control
ambition
obligation
memory
inheritance
```

A theme file should answer:

- what the theme currently means;
- how it develops;
- where it appears;
- competing readings;
- important supporting claims;
- contradictions;
- unresolved threads;
- affected chapters or arcs.

---

## 8.2 Arcs

Arcs are first-class because they are directly useful to writing.

An arc represents change across time or narrative structure.

Examples:

```text
Bob relationship
loss of institutional trust
changing understanding of success
family obligation
```

An arc may span people, events, themes, and chapters.

A representative structure:

```markdown
# Bob Relationship

## Current reading

## Beginning state

## Turning points

## End state

## Evidence

## Competing interpretations

## Chapter use

## Open threads
```

Themes describe recurring meaning.

Arcs describe transformation.

They should not be collapsed merely because both involve interpretation.

---

## 8.3 People

Person files may contain:

- identity and aliases;
- role in events;
- relationship to the narrator;
- changing understanding over time;
- associated arcs;
- relevant claims;
- source trails;
- open ambiguities.

---

## 8.4 Events

Event files may collect:

- chronology;
- participants;
- source accounts;
- disagreements between accounts;
- later interpretations;
- relevant themes and arcs;
- unresolved factual questions.

---

## 8.5 Claims

Not every observation needs its own claim file.

Claims become first-class when they are:

- important;
- contested;
- repeatedly referenced;
- structurally consequential;
- or supported by a substantial case.

Example:

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
- [SRC-00391 ¶4](...)

## Contradicting evidence

- [SRC-01102 ¶8](...)

## Author material

- [SES-20260912-1432 T017](...)

## Reasoning

...

## Open questions

...
```

A claim is therefore not merely a sentence.

It is an inspectable argument.

---

---

# 9. Attribution Model

Every durable interpretation statement must carry its epistemic status and provenance.

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

The Curator must not turn the AI's suggestion into an `[author]` position merely because the author discussed it.

There must be identifiable author evidence.

---

## 9.3 Inferred statements

```markdown
[inferred] Fear of losing control appears to intensify after the acquisition.

Basis:
- [SRC-00184 ¶17](...)
- [SRC-00392 ¶8](...)
- [SES-20260912-1432 T017](...)
```

An inference should identify both its conclusion and its basis.

For important inferences, the reasoning should be preserved as a claim or research memo rather than regenerated from scratch each time.

---

## 9.4 Open interpretations

Exploratory thinking should remain exploratory.

```markdown
[open] One possibility is that the later hostility reflects embarrassment rather than betrayal.
```

An `[open]` idea is not part of the current accepted interpretation.

This gives interesting speculation a durable home without allowing it to silently harden into doctrine.

---
