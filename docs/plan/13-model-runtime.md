<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 24 of the original memoria-plan.md -->
<!-- §24.2 revised 2026-08-31: memoria.read() mirrors §25's unified read(ref). -->

# 24. Model Runtime

> **Reduced for the PoC, 2026-08-31** (`../poc-plan.md` §3 and §5). Memoria is an
> **MCP server** and Claude Code, used interactively in its ordinary supported way,
> is the client. There is no web service driving Claude Code headless, no
> `ModelBackend` abstraction, and no capacity scheduler. What the PoC keeps from this
> part is §24.1's division of responsibility and §24.2's controlled tool surface.
> The stack diagrams below and §§24.3–24.5 are retained as the future-option record
> for a remote or multi-backend deployment — nothing the PoC builds.
>
> **Amended 2026-09-04** (`../adr/0010-model-calls-enter-by-choice-and-the-session-stays-the-default.md`):
> §24.5's API backend now exists, as `memoria.model` — one function per provider
> behind a plain callable rather than a `ModelBackend` class — off by default and
> switched on by the author under Settings > Model. Its policy is the first of the
> four §24.5 lists, "subscription only", until the author chooses the third for a
> pass by asking for a direct run; every metered call is a `model_call` ledger line,
> which is §24.5's "the author should be able to tell" made mechanical.

Memoria should separate its durable architecture from the model runtime used to operate on it.

The preferred initial runtime is **Claude Code authenticated through the author's own supported Anthropic Claude subscription**, rather than requiring pay-as-you-go API usage for normal personal operation.

Conceptually:

```text
Phone / browser
      ↓
Memoria web service
      ↓
ModelBackend
      ↓
Claude subscription backend
      ↓
Claude Code
      ↓
Author's Claude Pro / Max subscription
```

The subscription-backed runtime is an implementation choice, not canonical architecture. Memoria's repository, provenance model, retrieval rules, manuscript authorization, and intellectual state must remain independent of it.

The runtime boundary should look like:

```text
                 Memoria
                    │
              ModelBackend
                    │
        ┌───────────┴───────────┐
        │                       │
ClaudeSubscriptionBackend   AnthropicAPIBackend
        │                       │
   Claude Code               optional later
```

Only the subscription-backed backend is required initially. The abstraction exists so Memoria can later add API access, another provider, local models, specialized models, or a hybrid policy without changing durable project state.

---

## 24.1 Division of responsibility

Claude Code already supplies much of the generic agent runtime Memoria would otherwise need to build.

### Claude Code provides

- authenticated model access through a supported Anthropic subscription;
- multi-step agentic execution;
- tool invocation;
- streaming responses;
- resumable model sessions where useful;
- file-aware execution;
- and MCP/tool integration.

### Memoria provides

- canonical repository state;
- source normalization;
- provenance;
- context assembly;
- retrieval;
- temporal discipline;
- interpretation state;
- research procedures;
- manuscript authorization;
- the audit, when the author asks for one;
- Git history;
- resumability;
- and the user interface.

Claude Code is the initial **agent runtime**.

Memoria is the **intellectual system**.

---

## 24.2 Controlled tool access

Memoria should not simply grant Claude Code unrestricted authority over the repository.

The preferred arrangement is to expose controlled Memoria tools, for example:

```text
memoria.search()
memoria.search_semantic()
memoria.read()
memoria.timeline()
memoria.trace()
memoria.backlinks()
memoria.build_source_packet()
memoria.propose_manuscript_change()
memoria.apply_authorized_change()
```

`memoria.read()` is §25's `read(ref)`: one read tool over the §4 stable IDs, under
`poc-plan.md` §7's superset-of-grep constraint. There are no per-type read tools.

Research sessions can operate with canonical writes disabled except for explicit durable research outputs.

Interpretation changes pass through Curator ownership and provenance rules.

Canonical manuscript writes pass through the explicit authorization model defined in this plan.

Read-side, the same surface is the sole evidence path: the corpus lives outside the
session's working repo and direct reads are routed back to the tools by hook
(`poc-plan.md` §3), with every served read ledgered in `events.jsonl` (§10.4).

This allows Memoria to benefit from a powerful agent runtime without weakening its invariants.

---

## 24.3 Subscription usage is variable capacity

A subscription-backed runtime must be treated as a capacity-constrained resource rather than infinitely available compute.

Memoria must not hard-code assumptions about message counts, token allowances, model availability, or reset windows. Capacity can vary with subscription tier, provider policy, model choice, conversation length, tool use, and research depth.

If model capacity is temporarily unavailable:

```text
Claude available
      ↓
normal operation

usage capacity unavailable
      ↓
preserve current state
      ↓
keep repository / search / UI available
      ↓
defer non-urgent model work
      ↓
resume safely when capacity returns
```

A usage limit must never cause loss of research state, manuscript work, pending Curator actions, authorization records, or provenance.

---

## 24.4 Interactive work has priority

Subscription capacity should be allocated according to user value.

Default priority:

```text
1. Interactive author conversation and writing
2. Explicitly requested research
3. Necessary post-session curation
4. Manuscript-impact analysis
5. Digest regeneration
6. Health scans and speculative background analysis
```

When capacity is constrained, lower-priority work waits. Memoria should not consume substantial subscription capacity on housekeeping while preventing the author from working interactively.

---

## 24.5 Optional API fallback

An Anthropic API backend may be added later. Possible policies include:

```text
subscription only
subscription preferred, API fallback
API only
provider-selectable per task
```

The initial build does not require API fallback.

If fallback is added, it should be explicit and configurable because API usage has separate billing behavior. The author should be able to tell whether a task is using subscription capacity or metered API usage.

---
