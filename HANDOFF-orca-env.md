# Handoff: the Orca worker environment costs every batch

**Written:** 2026-09-02, after the memoria M1/M2 fallout batch (Orca run `run_25432138626e`,
six issues, PR #126).

## Goal

Make an Orca worker worktree usable out of the box, so a batch does not pay a per-worker
tax and does not lose its conflict-recovery path.

This is not memoria code. It is Orca configuration plus the repo's `orca.yaml`, and it
needs you in the loop — one item is a policy decision, and one collides with work already
in flight.

## Collision warning, read first

`orca-ide worktree list` shows a worktree named **`orca setup`** in state `in-progress`.
Someone (possibly another session) is already working this area. **Check what it is doing
before touching `orca.yaml` or Orca settings** — do not start by editing the same file
from two directions. `git fetch` and re-check branch/PR state first, per the standing
rule in CLAUDE.md.

## The three problems

### 1. The setup hook never runs (highest cost, best understood)

`orca.yaml`'s `scripts.setup` is a bash body. Orca on this machine runs it under
`cmd.exe`, where bash syntax dies immediately and silently. The result is the worst
possible shape: **a new worktree reports a clean create and has no `.venv`, with no
warning anywhere.** Nothing in the Orca UI or the setup log says the gate failed.

Cost in this batch alone: six workers and seven reviewer passes each had to detect the
missing venv and hand-build one before doing any work —

```
export PATH="$HOME/.local/bin:$PATH"; export UV_LINK_MODE=copy
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
```

Every worker spec and every reviewer prompt in the batch carried that paragraph. It works,
but it is a workaround pasted into a dozen prompts, and a worker that forgets it tests
against another tree's Python or fails confusingly.

The fix is known and unmerged: force the hook through `wsl.exe`. Existing memory notes
[[orca-hooks-run-under-cmd-on-windows]] and [[orca-setup-hook-precedence]] cover the
mechanism — note in particular that a local setup script can silently disable `orca.yaml`,
so **fix the source policy, not just this box.**

Acceptance: create a throwaway worktree from a repo with the hook, and confirm `.venv`
exists and `.venv/bin/pytest` runs, without any manual step. "It should work now" is not
done — render it.

### 2. Worker worktrees deny `git merge` / `git rebase`

The #115 worker was given a rebase assignment and could not execute it: its worktree's
permission classifier denied `git merge` and `git rebase` outright, with no approver
available to prompt. It reported the block rather than guessing, which was correct.

Why this matters more than it looks: the orca-goal protocol routes "PR conflicts with the
moved integration branch" back to a worker as a rebase assignment, and explicitly forbids
the orchestrator from resolving conflicts itself. **If workers cannot merge or rebase,
that entire recovery path is dead** and a batch has no legal way to resolve a conflict.

It did not bite this time only by luck — `origin/main` never moved during the batch and
every PR trial-merged clean. A batch touching a moving main would have stalled.

**This is the item that needs your decision.** Options, roughly: allow git merge/rebase in
worker worktrees; or accept the restriction and change the protocol so conflicts escalate
to the operator instead of to a worker. Either is defensible; I should not pick for you.

### 3. `worker-start --retry-of` is rejected

```
orca-ide orchestration worker-start --task <t> --retry-of <dispatch> --worktree name:issue-N ...
-> "Task <t> cannot retry from Dispatch <d>"
```

Both retries in this batch had to be re-dispatched without it. That works, but the
replacement attempt is then unlinked from the original, and a re-dispatch is a **fresh
session** with no memory of the first attempt — so the review feedback has to be posted to
the GitHub issue as the durable assignment, and the new worker told explicitly not to
restart from scratch or open a second PR. That worked reliably; it is just undocumented
ceremony that every orchestrator has to rediscover.

Already recorded in [[orca-goal-retry-mechanics]]. Lowest priority of the three — the
workaround is solid. Worth fixing or documenting, not worth blocking on.

Minor, related: `worker-release` returns `release_unknown` / `identity_unproven` once the
worktree has been removed. Terminals are archived correctly; only the accounting is untidy.

## Context to load

- `orca.yaml` at the memoria repo root — the setup hook, with a long comment block
  explaining why `uv` and not `python3 -m venv` (Python 3.14 here ships no `ensurepip`).
- `/home/john/.claude/skills/orca-goal/ORCHESTRATOR.md` — the protocol, especially the
  **Retry** section (which is what `--retry-of` breaks) and the conflict/rebase rule in it
  (which is what problem 2 breaks).
- `/home/john/.claude/skills/orca-goal/IMPLEMENTER.md` — the worker contract, which
  assumes "deps were installed by setup hooks".
- Memory: [[orca-hooks-run-under-cmd-on-windows]], [[orca-setup-hook-precedence]],
  [[orca-goal-retry-mechanics]], [[orca-goal-loop-mechanics]],
  [[orca-worker-worktree-denies-git-merge]].
- Evidence from this batch: Orca run `run_25432138626e`; PR #126's FINDINGS section
  records all three problems with the specific symptoms.

## The named missing decision

**Problem 2:** should worker worktrees be allowed to run `git merge` / `git rebase`, or
should the orca-goal protocol stop assigning rebases to workers and escalate conflicts to
the operator instead? Everything else here is mechanical once that is settled.
