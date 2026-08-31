<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: Preamble + 0, 0.1 of the original memoria-plan.md -->

# Memoria — Build Plan

> **Project name:** Memoria  
> **Purpose:** An attributable AI research-and-writing environment for working accurately across a book-sized source archive far beyond any single model context window.

---

## 0. Purpose

Memoria is an AI research-and-writing system for working accurately across a source archive far larger than any model context window.

Its primary promise is simple:

> **The author should be able to work at the scale of the book without having to manage the limits of the model.**

The user should not have to think about token budgets, manually decide which source files fit into a prompt, repeatedly summarize earlier research, or wonder whether the AI has become confused because the archive is too large.

Memoria absorbs that complexity.

It maintains a durable model of the book, assembles focused working context, searches the wider archive when needed, expands back to original sources, and preserves the provenance of every important conclusion. This makes it possible to use frontier models across a book-sized corpus without treating a large context window as a substitute for evidence discipline.

Memoria should behave less like a chatbot with document access and more like a research and writing collaborator that:

- can work across a source archive much larger than any single model context;
- automatically assembles the right context for the task at hand;
- retrieves deeper evidence on demand rather than forcing the whole corpus into one prompt;
- distinguishes primary evidence from retrospective evidence and later interpretation;
- shows exactly which sources were searched and which evidence supports a conclusion;
- reasons across themes, arcs, people, events, claims, chapters, and time without collapsing those distinctions;
- can independently research contested questions and actively seek disconfirming evidence;
- knows the current state of the book and where a section fits into the whole;
- can directly draft and revise canonical manuscript prose when explicitly authorized;
- can notice when changes elsewhere in the project imply changes to the manuscript;
- can propose those manuscript changes without applying them unprompted;
- preserves the author's evolving intent over time;
- can resume work after long gaps without reconstruction;
- and can explain why it believes anything it believes.

The final requirement is foundational.

Memoria must never become an opaque second memory whose conclusions can no longer be traced to their origins.

Every durable assertion must be attributable.

A durable statement should ultimately resolve to one or more of:

1. an immutable source record;
2. an exact author turn in a preserved AI conversation;
3. an exact direct human edit preserved in Git;
4. or, for model inference, an explicit argument grounded in such material.

The goal is therefore not simply persistent memory.

It is **persistent, inspectable, attributable memory in service of a manuscript**.

## 0.1 Product Thesis

Memoria's selling point is not that it remembers where the author left off, although it does.

Its central value is that it makes **large-context AI work trustworthy and usable**.

A frontier model should be able to help with a project whose relevant evidence is far larger than its context window without requiring the author to become a retrieval engineer. Memoria provides the persistent state, retrieval loop, source expansion, provenance, temporal discipline, and scope reporting that make this possible.

The promise is:

> **Bring the whole archive. Ask the real question. Memoria handles the context.**

Resumability follows naturally because the understanding required to answer future questions is stored durably instead of being trapped inside one model session.

---
