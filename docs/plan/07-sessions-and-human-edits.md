<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 10, 11, 41 of the original memoria-plan.md -->

# 10. Session Records

Every Memoria AI session is a permanent part of the project record.

A session directory contains:

```text
transcript.md
metadata.yaml
context-manifest.json
events.jsonl
```

## 10.1 transcript.md

Contains the human-readable conversation.

Every turn receives a stable anchor:

```markdown
## T016 — Assistant

...

## T017 — Author

I think what I've been calling ambition is actually more about fear of losing control.

## T018 — Assistant

...
```

The transcript is immutable once the session closes.

Corrections or annotations are layered separately rather than silently changing history.

---

## 10.2 metadata.yaml

Records information such as:

```yaml
session_id:
started:
ended:
model:
provider:
mode:
chapter:
section:
system_prompt_version:
```

This does not attempt to reproduce the model.

It records enough context to understand what kind of interaction occurred.

---

## 10.3 context-manifest.json

Records what Memoria supplied to the model.

For example:

```text
book.md
chapter 8 brief
section 8.3 state
theme/control
arc/bob-relationship
five source records
two research memos
```

It also records:

- token budgeting;
- truncation;
- explicitly excluded material;
- retrieval performed during the session.

This provides a boundary around model knowledge.

A later audit can distinguish:

> The model concluded X after inspecting these 14 sources.

from:

> The model spoke as though it knew the archive but had only seen three documents.

---

## 10.4 events.jsonl

This is the detailed machine audit record.

It may contain:

- tool calls;
- searches;
- retrieved result IDs;
- files opened;
- writes performed;
- Curator handoff events.

The Markdown transcript remains the human interface.

The event log exists when deeper reconstruction is required.

---

---

# 11. Direct Human Edits

The author should be able to work normally in Obsidian or another editor.

Memoria should not require every thought to pass through the AI.

A lightweight repository watcher or synchronization layer observes human changes.

After a meaningful editing burst, or before an agent modifies affected files, Memoria creates a human checkpoint commit.

That change receives an identifier such as:

```text
CHG-20261014-0917
```

A machine-generated projection under `changes/` provides a human-readable view:

```markdown
# CHG-20261014-0917

Date: 2026-10-14 09:17
Commit: 9b07fa1
Files:
- themes/control.md

## Diff

-Control appears primarily as a professional concern.
+Control is fundamentally personal and only later becomes professional.
```

Git remains canonical.

`changes/` is a deterministic, rebuildable view that makes Git history easy to link from Markdown and the UI.

A direct edit proves **what changed**.

Memoria must not invent **why** it changed unless that reason exists in a conversation, note, or explicit commit annotation.

---

---

# 41. Git as Audit and Authorship Infrastructure

Git serves:

1. history;
2. rollback;
3. attribution;
4. ownership;
5. manuscript-authorization audit.

Curator commits are machine-authored.

Direct human changes are human-authored.

AI manuscript changes are committed with references to their authorizing interaction.

Example:

```text
manuscript: revise ch2 ¶7 for corrected Bob timeline

authorized-by:
  SES-20261103-1041#T008

triggered-by:
  CHG-20261103-1024
  IMP-20261103-004

evidence:
  SRC-0184
  SRC-0391
```

A later author or model can reconstruct both:

- why Memoria wanted the passage changed;
- and why it had authority to change it.

A bad Curator or AI writing pass should be reversible with ordinary Git operations.

---
