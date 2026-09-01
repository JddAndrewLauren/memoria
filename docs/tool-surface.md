# The tool surface

What Memoria exposes to a session model, and what is settled about it.
Implemented by `src/memoria/mcp/`, over the core read side that
`docs/adr/0004-the-read-side-is-functions-over-a-repository-value.md` places.

Part 11 §25 lists ten candidate tools. This document records the ones whose
signatures are **forced** — closed, with a reason — and leaves the rest
explicitly open, so that "still open" is a statement someone made rather than
a gap nobody noticed.

| Tool | State |
|---|---|
| `read(ref)` | **Forced** — issue #11, below |
| `search_text(query, filters)` | Open — issue #12 |
| `search_semantic`, `expand`, `timeline`, `grep_repo`, `trace`, `backlinks`, `list` | Open; §25 does not commit to shipping them |

## The constraint that binds all of it

From `poc-plan.md` §7, and it **may not be weakened**:

> retrieval must be a **superset of grep**: verbatim source text (never
> summarized-only), decorated with the curated overlay, a raw full-source read
> available, and every read ledgered in `events.jsonl`.

The reason is not purity. Evidence lives outside the session's working repo
and direct reads are routed back to the tools by a hook
(`.claude/hooks/route-evidence-reads.sh`, `poc-plan.md` §3). That hook is a
**router, not a wall** — Bash can still reach the files. It only works while
the tool returns *more* than a raw read does. The moment reading through the
tool is worse than `cat`, the router becomes an obstacle and people go around
it, and the ledger that makes the context manifest a record rather than a
request stops being complete.

So: the verbatim text is served unmodified and contiguously, and the
full-source read may never be removed or degraded.

## `read(ref)` — forced 2026-09-01, issue #11

```
read(ref: str) -> str
```

One tool, not a family. Dispatch is read off the reference, because the ID
scheme of part 04 §4 already names the type. The former per-type list
(`read_source`, `read_session`, `read_change`, …) was withdrawn by §25 as an
enumeration of kinds, and had already drifted.

### What it accepts

| Form | Serves | Where the form comes from |
|---|---|---|
| `SRC-000184` | the whole record, verbatim | part 04 §4 |
| `SRC-000184 ¶17` / `SRC-000184 P17` | that paragraph | part 04 §4's prose citation |
| `SRC-000184#src-000184-p17` | that paragraph | part 04 §4's markdown link |
| `#src-000184-p17` | that paragraph | the fragment alone |
| `src-000184-p17` | that paragraph | `index.SearchResult.anchor`, verbatim |
| `docs/poc-plan.md` | the file, verbatim | a repository-relative path |

The bare anchor is accepted deliberately. `SearchResult` carries
`(src_id, anchor, source_type)`, so a search hit feeds straight back into
`read` — without it, #12 would have to reassemble a citation string inside an
adapter, which is the duplication §40.1 exists to forbid.

`SRC-` IDs are six digits, zero-padded. `SRC-184` is refused with a message
saying so, rather than guessed at.

Paths are repository-relative, and reads are confined to the repository by
**two** checks, because one is not enough. The reference is refused if it says
it leaves the tree — absolute, a drive letter, a `..` component, or any
backslash (one component on POSIX, three on Windows, and a rule that holds
only on the developer's platform is not a rule). The resolved path is then
refused if it turns out to leave the tree, which is the case a symlink makes:
the reference is an ordinary relative path and only the target escapes.

A reference is treated as an ID only when its kind is upper case, as part 04
§4 writes them. Without that, `open-problems.md` — a file in this repository —
was answered with "unknown reference kind OPEN-".

### What it returns

A record ID with no paragraph returns **the record file exactly as it is on
disk** — frontmatter, anchors and all, byte for byte what `cat` gives. That is
the raw undecorated full-source read the constraint requires.

**A full-source read is returned bare** — the file and nothing else, with no
header and no delimiter. It is the undecorated read, and it should be
indistinguishable from `cat` at the surface, not only in the value the core
returns. Path reads are bare for the same reason.

That was learned rather than designed. The first live read carried a `ref:`
line and a `---` above the record's own frontmatter opener; the reader saw two
consecutive `---` lines, took them for an empty pair, and reported the payload
as corrupted. The envelope was correct and the report was wrong — which is
precisely the problem. The routing hook is a router, not a wall, and a tool
whose output reads as damaged loses the traffic it depends on. The line was
redundant anyway: the record's frontmatter states its own `id`.

**A paragraph reference** returns that paragraph's bytes, with the record's
metadata in a header above a `---` delimiter — a paragraph genuinely does not
carry the fields a reader needs to judge it.

Two properties of that header are contracts, not styling:

- **The verbatim text appears contiguously and unmodified** — never wrapped,
  re-indented, escaped, or interleaved with anything.
- **There is exactly one delimiter convention.** The curated overlay (#20)
  appends after the text using it; it does not interleave. The full-source
  read has no delimiter because it has no decoration — that is what makes it
  the raw one.

`original_locator` is printed and never parsed. It is a pointer a person
follows, not an offset — issue #25 depends on that staying true.

### What it refuses, and how

Reference kinds part 04 §4 defines but this build does not resolve —
`SES-` (with or without a `#T` turn), `CHG-`, `CLM-`, `RES-`, `DEC-`,
`SUB-x`, `SUB-x/y` — return an error **naming the kind**, never a silent empty
result. A kind that is not part of the scheme at all is named too, and
distinguished from one that is merely unbuilt.

Errors reach the model as `ToolError`, which is the SDK's anticipated-failure
type: the call comes back `is_error` with the message intact. Any other
exception is reported as `Error executing tool read` with the reason stripped,
which would be exactly the silent failure #11 forbids — so the adapter maps
the core's one error type onto it.

### What is deliberately still missing

- **No ledger.** `events.jsonl` is issue #13. Until it lands, a served read
  is not recorded anywhere, and the §7 constraint is met only in part. The
  routing hook's message says only what is true today for the same reason.
- **No overlay.** Decoration with entry links, exclusions and citing
  settlements is issue #20, at M2.
- **No `raw` parameter.** Every read is undecorated today, so the
  full-source read is raw by accident rather than by contract. **#20 owes the
  parameter**: when it adds decoration it must also add the flag that turns it
  off, because "a raw full-source read remains available" is a constraint on
  the surface after M2, not just before it. This is the one part of the
  signature this slice did not force, and it is recorded here so that #20
  finds it rather than discovering it.
- **No raw *original*.** Reading the pre-normalization source at
  `original_file` is #64/#25's "Open original", not this.

## Registering the server

`.mcp.json` at the repository root, committed:

```json
{
  "mcpServers": {
    "memoria": {
      "type": "stdio",
      "command": ".venv/bin/python",
      "args": ["-m", "memoria.mcp"]
    }
  }
}
```

One committed file, correct in the primary checkout and in every worktree,
each of which has its own `.venv`, and with nothing machine-specific in it.

Three facts it depends on, **measured on Claude Code 2.1.252 rather than
assumed**, by registering a probe server that recorded what it was handed:

- **A project stdio server is launched with the project directory as its
  working directory.** That is what makes the relative `command` resolve, and
  what lets the server find the repository root by walking up for
  `pyproject.toml`. Pass `--repo-root` if you ever need to be explicit.
- **`${CLAUDE_PROJECT_DIR}` is *not* expanded in `.mcp.json`.** It is a hooks
  variable. A config that uses it is reported by `claude mcp list` as
  `Missing environment variables: CLAUDE_PROJECT_DIR`, and the literal string
  is passed through unexpanded. (`CLAUDE_PROJECT_DIR` *is* present in the
  spawned process's own environment — it is the config-time substitution that
  does not happen. Nothing here relies on either.)
- **`env` in `.claude/settings.json` / `settings.local.json` does not reach
  the server process.** It applies to Claude Code's own tool execution.

`python -m memoria.mcp` rather than the `memoria-mcp` console script: a module
works the moment the package is importable, while a newly added console script
does not exist until the environment is reinstalled.

A project-scoped server needs approving once — `claude mcp list` shows
`⏸ Pending approval` until then, and `/mcp` reports its state inside a
session.

### A finding worth not rediscovering

The settings-`env` fact above is why `orca.yaml`'s mechanism for handing a
worktree its `MEMORIA_EVIDENCE_ROOT` — writing `.claude/settings.local.json`
at setup — will not reach this server.

It does not matter yet: `read(ref)` resolves everything from the repository
root and never touches evidence, which is why the committed registration
carries no `env` block at all. It will matter the first time a tool reads
evidence. The options then are forwarding it (`"env": {"VAR": "${VAR}"}`,
which works only if the variable is exported in the shell that launched
`claude`), a machine-local `claude mcp add --scope local`, or an
`--evidence-root` argument written by the setup hook. None is built.

The `.venv/bin/python` path is POSIX; `orca.yaml` already requires WSL on
Windows for the same class of reason.
