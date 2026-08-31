<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 40 of the original memoria-plan.md -->

# 40. Interfaces

The responsive web interface should be part of the first usable Memoria build rather than a late-stage convenience layer.

This follows directly from the product promise:

> **Bring the whole archive. Ask the real question. Memoria handles the context.**

The user should interact in terms of questions, chapters, themes, arcs, evidence, and manuscript changes—not commands, token budgets, context manifests, or retrieval mechanics.

The early UI should expose Memoria's intelligence without attempting to replace every mature writing tool.

---

## 40.1 One core service layer

Every interface should use the same Memoria service layer.

```text
Desktop browser ─┐
Phone browser   ─┼──► Memoria web/API service ──► Repository
CLI             ─┘             │                  SQLite
                               │                  Git
                               └──► ModelBackend / Curator
```

Business logic should not be duplicated between the CLI, web UI, and Curator.

The web application owns no unique intellectual state. It is an interface to the same canonical repository and service layer.

---

## 40.2 Responsive web first

Memoria should initially target a responsive web application rather than separate native mobile applications.

A phone is particularly well suited to:

- asking book-wide questions;
- continuing a conversation;
- reviewing research;
- opening cited sources;
- inspecting themes and arcs;
- reviewing manuscript impacts;
- previewing candidate rewrites;
- authorizing or rejecting changes;
- capturing a thought;
- and telling Memoria to draft or revise something.

Desktop may present multiple panes simultaneously.

Phone should present one focused surface at a time.

The same backend and canonical repository serve both.

---

## 40.3 Initial web surfaces

The first useful web version should remain deliberately small.

### Home / Ask Memoria

General book-wide conversation. This is the simplest expression of the product promise: ask the question and let Memoria handle context assembly and retrieval.

### Section

Show:

```text
Purpose
Current draft
Checkpoint
Decisions
Open questions
Attention
Relevant themes/arcs
Source packet
Unresolved impacts
Resume
```

### Source viewer

Show the normalized source, exact cited location, temporal metadata, backlinks, and an **Open original** action.

### Theme / Arc

Show the current interpretation, supporting and contradicting claims, provenance, affected manuscript passages, and open threads.

### Research conversation

Allow searches and source reads to appear as the model works without requiring the author to manage those operations manually.

### Review

Show manuscript impacts and candidate changes with actions such as:

```text
View evidence
Explain
Preview diff
Rewrite
Apply
Dismiss
```

These surfaces are enough for an early desktop-and-phone product.

---

## 40.4 What not to build early

The first web UI should not attempt to replace a mature desktop writing application.

Avoid making the initial build depend on:

- a sophisticated rich-text editor;
- offline-first synchronization;
- native iOS or Android applications;
- push notifications;
- collaborative editing;
- a full visual graph explorer;
- or elaborate dashboards.

Viewing manuscript prose and directing AI-assisted changes should work well on mobile. Serious manual long-form editing may continue in Obsidian or another editor.

---

## 40.5 Authentication and remote access

Phone access requires secure authentication and HTTPS.

For a personal deployment, the preferred early model is private-network or tailnet access rather than direct public-internet exposure.

The Memoria host contains:

```text
repository
SQLite index
Git
web/API service
Claude Code authentication
model runtime
```

The phone contains no Anthropic credentials. It is only a client.

This keeps model authentication and the private archive centralized on the Memoria host.

---

## 40.6 Single write coordinator

Once multiple interfaces exist, all automated writes should pass through one write coordinator.

This prevents conflicts between:

- Obsidian;
- the web UI;
- phone actions;
- AI sessions;
- and the Curator.

Writes should be checked against the current Git revision. Stale operations should be rejected or reconciled rather than silently overwriting newer work.

---

## 40.7 Streaming and visible activity

The web service should support streamed model output and structured activity updates.

The UI may show concise status such as:

```text
Searching 2011 email…
Reading SRC-0184…
Checking Bob aliases…
Comparing retrospective accounts…
```

This helps make large-corpus reasoning legible without making the user manage the context window or retrieval loop.

---

## 40.8 CLI remains administrative

The CLI remains useful for operations such as:

```text
memoria ingest
memoria rebuild
memoria validate
memoria sync
memoria trace
```

It does not need to be the primary daily interface.

The primary product experience should be the responsive web interface.

---
