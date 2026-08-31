<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 24 of the original memoria-plan.md -->

# 24. Model Runtime

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
- manuscript-impact analysis;
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
memoria.read_source()
memoria.timeline()
memoria.trace()
memoria.backlinks()
memoria.read_theme()
memoria.read_arc()
memoria.read_claim()
memoria.build_source_packet()
memoria.propose_manuscript_change()
memoria.apply_authorized_change()
```

Research sessions can operate with canonical writes disabled except for explicit durable research outputs.

Interpretation changes pass through Curator ownership and provenance rules.

Canonical manuscript writes pass through the explicit authorization model defined in this plan.

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
