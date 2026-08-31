<!-- Part of the Memoria build plan. Index: ./plan-index.md -->
<!-- Source sections: 45, 46, 48 of the original memoria-plan.md -->

# 45. Optional Future Retrieval Infrastructure

Memoria initially does **not** require:

- Qdrant;
- GraphRAG;
- Neo4j;
- Open WebUI;
- a graph database;
- a hierarchical summary pyramid;
- persistent specialist agents.

Any may eventually become worthwhile.

The process for adding one is:

```text
Observe real failure
        ↓
Turn failure into benchmark
        ↓
Prototype heavier approach
        ↓
Compare against existing Memoria
        ↓
Adopt only if materially better
```

The existing file model should survive regardless.

Retrieval implementations are replaceable.

The repository is durable.

---

---

# 46. Optional Future Specialist Agents

Memoria begins with capabilities expressed as skills over shared state.

Possible future roles include:

- Research Editor;
- Continuity Editor;
- Theme Analyst;
- Fact Checker;
- Structural Editor.

A role earns persistent agent state only if experiments show that loading the relevant skill plus explicit Memoria state does not provide sufficient continuity.

Separate agents must not develop private canonical memories disconnected from the repository.

Anything durable they learn belongs in Memoria.

---

---

# 48. Privacy and Provider Independence

Memoria should not depend conceptually on a particular model vendor.

A model needs:

- repository read access;
- controlled write access;
- retrieval tools;
- skills;
- context;
- provenance rules;
- manuscript authorization rules.

The underlying model may change over the lifetime of the book.

The durable intellectual state remains in ordinary files.

The preferred initial deployment uses a local Claude Code installation authenticated to the author's own supported Anthropic subscription. Authentication credentials remain on the Memoria host rather than being distributed to browsers or phones.

If external model APIs are later used, privacy, billing, and source-upload policies are configuration decisions rather than architectural assumptions.

---
