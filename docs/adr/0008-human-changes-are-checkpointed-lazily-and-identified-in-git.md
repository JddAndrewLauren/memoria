# Human changes are checkpointed lazily, identified in the commit, and projected from it

§11 asked for "a lightweight repository watcher or synchronization layer" that observes
human edits and, "after a meaningful editing burst, or before an agent modifies affected
files", creates a human checkpoint commit carrying an identifier like `CHG-20261014-0917`,
with a `changes/` projection giving it a readable view. The plan named that mechanism in
five places and no issue built it. ADR-0003 then took half the ground out from under it:
an accepted write through the write path already commits, path-scoped and attributed, so
edits made through a Memoria surface need no catching. What remained uncovered was the
case §11 was written for — the author working in Obsidian, where nothing commits at all.
ADR-0003 explicitly deferred the rest, recording that `CHG-` IDs and the projection were
"filed as their own issue" and that its own job was to secure "that the commits exist now".
We settle that issue on 2026-09-01. **There is no watcher. Checkpoints are lazy, every
human-authored commit is identified by a trailer, and `changes/` is a rendered view of git
rather than a stored fact.**

## The shape

- **Two triggers, both explicit.** Automatically, before any machine actor writes to
  durable files; and on demand, via `memoria checkpoint`. The first is where correctness
  lives — it is the moment the dirty-tree rule (#32) stops protecting a file and the
  human-touched flag has to take over — and the second is where granularity lives, as an
  author act rather than a heuristic.
- **A checkpoint commits tracked, modified files under durable state classes (§3).**
  Never untracked files, never `git add -A`, never Derived. One checkpoint is one commit
  with one `CHG-` ID.
- **Every human-authored commit carries a `CHG-` ID** — checkpoints of outside edits and
  writes through the write path alike. Curator and AI manuscript commits carry none;
  §41 already distinguishes them by their own trailers.
- **The ID is `CHG-YYYYMMDD-NNN`**, a per-day sequence in the `RES-20261018-003` form
  rather than the `HHMM` form the plan's examples show. The clock time survives in the
  projection's `Date:` line.
- **The commit message carries a `change-id:` trailer, and git history is the ledger.**
  Minting counts the day's existing trailers; `read(CHG-…)` finds the commit by them.
- **One renderer, two callers.** A single function renders a commit into the §11
  projection. `read(CHG-…)` calls it against git; `memoria rebuild` calls it in a loop and
  writes `changes/CHG-*.md`, which is **gitignored**. The read path never consults those
  files, so the projection has no staleness semantics at all.

## Considered Options

**A repository watcher, as §11's wording says.** Rejected. It would be the first
long-running process in a system that otherwise has none, and it buys only earlier commit
timestamps: the case that actually needs a commit is an agent about to write, which is
synchronous, checkable and testable without a daemon. The uncommitted-edit window a
watcher would close is already safe — the dirty-tree rule protects it — so the daemon
would be carrying a lifecycle, a crash story and a per-platform install to improve
granularity alone. `memoria checkpoint` buys that granularity for one CLI verb.

**Defining "a meaningful editing burst".** Rejected as vocabulary belonging to the
rejected branch. A quiet period, a debounce or a change threshold exists so a daemon can
guess when the author stopped typing. With two explicit triggers there is nothing to
guess, and leaving the term in the plan would invite someone to implement a heuristic
nobody needs. §11 is amended to say so.

**Committing everything dirty in the tree.** Rejected. It sweeps in Derived state and
scratch files, and it contradicts ADR-0003's path-scoping decision outright.

**Scoping the checkpoint to only the files the agent is about to touch.** Genuinely
defensible — the most conservative reading of §11, and it removes the dirty-tree shield
only where the Curator actually needs in. Rejected as harder to state and to test than
"durable, tracked, modified", for a difference that self-corrects: any file left dirty is
checkpointed the next time an agent reaches it, and the human-touched flag is monotonic.

**`CHG-` on checkpoints only, leaving app writes as ordinary commits.** Rejected. It
makes an epistemic distinction out of a surface accident: §41 calls a direct human change
human-authored whether Obsidian or the app was open. Under it, §41's `triggered-by:`
could never name a change the author made through the app, and `read(CHG-…)` would cover
outside edits only. The cost of uniformity is real but small — minute-resolution IDs
collide once app writes are frequent, which is what moves the ID to a per-day sequence.

**Committing the `changes/` projection.** Rejected, and this is the decision most worth
recording. A tracked projection means every `rebuild` writes regenerated machine output
into the git history that §41 designates as the audit and authorship record — history,
rollback, attribution, ownership, manuscript-authorization audit. Every other cost weighed
here is reversible; that one accumulates in history permanently. It would also be the
repository's first tracked derived state, against a rule `.gitignore` already states for
`.memoria/`, and it would need a staleness finding in `memoria validate` — which today
refuses to run at all without `MEMORIA_EVIDENCE_ROOT`, so the check would be unreachable
on every machine now that the Thoreau corpus is retired.

**Computing the projection on read and writing no files.** Rejected as silently amending
§11 and §2: the plan draws `changes/CHG-….md` as a real path, and "the repository should
remain understandable without Memoria-specific software" is not answered by a function
call. The observation that dissolved this option is that it was never an alternative to
writing the files — rendering a commit is one pure function, and the only question is who
calls it.

**Building the IDs now and deferring the projection.** Rejected once the ID became
uniform. It would mint identifiers that get written into `triggered-by:` trailers and that
`read(ref)` refuses to resolve — the mintable-but-unresolvable shape this codebase already
refuses elsewhere, in `references.py`'s `UnknownReference` and in the MCP server's
`ToolError` handling.

**A ledger file mapping `CHG-` to commit SHA.** Rejected for the reason ADR-0006 rejected
a separate allocation file for `SRC-` IDs: a second store for facts the committed record
already holds, which drifts the first time one is edited without the other. It is worse
here than there, because it would record SHAs and every rebase would invalidate it.

**Deriving the ID positionally from history**, as "the Nth human-authored commit that
day", with no trailer. Rejected as the same failure ADR-0006 rejected for sorted-order
`SRC-` IDs: an interactive rebase that inserts or drops a commit renumbers everything
after it, and every `triggered-by:` reference goes stale at once. A trailer written when
the commit is made survives rebase and cherry-pick as message text, even though the SHA
does not.

## Consequences

- `.gitignore` gains `changes/`, with a comment recording that it is derived and
  regenerated by `memoria rebuild`, in the style of the existing `.memoria/` entry.
- `changes/` is the only derived state in the system whose input — git history — ships
  inside the clone. `memoria rebuild` regenerates it on a bare clone with no evidence
  root, no corpus and no normalized records, which is what makes gitignoring it cheap.
- §11 is amended: the watcher and the editing burst come out, the two triggers go in.
- The `CHG-20261014-0917` and `CHG-20261103-1024` examples in §4, §11 and §41 are
  amended to the `CHG-YYYYMMDD-NNN` form.
- The two parameterized tests that pin `CHG-20261014-0917` on the *not-yet-implemented*
  reference path must move off it when `CHG` starts resolving. A `CHG-` ref that returns
  "not yet built" is the current correct behaviour and stops being so.
- #70 gains a dependency on #66. Both make a path-scoped, attributed commit, #66 defines
  that primitive, and there is no git invocation anywhere in the codebase today.
- **Revisit if** the manuscript comes to cite `changes/` *paths* as durable links rather
  than `CHG-` refs — a reader with no tooling would then need the files, §2 would become
  decisive, and the history cost of tracking them would have to be paid.
