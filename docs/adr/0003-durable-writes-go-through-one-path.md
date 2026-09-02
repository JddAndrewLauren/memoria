# Durable writes go through one path, gated by a content hash and closed by a commit

M3 carries the first durable write in the system — the author editing an entry's match
terms (#26) — and §40.6's single write coordinator is the mechanism that governs it. The
plan names that mechanism five times and no issue built it; `../poc-plan.md` §5 reduces it
to "a stale-revision check", and §3 and §19.11 both say that check "is what has to hold
the two write paths apart", the app and Obsidian.

**Taken literally, the plan's own wording does not work.** §40.6 says *"Writes should be
checked against the current Git revision."* The author opens an entry in the app at
revision `abc`, edits the same file in Obsidian and does not commit — Obsidian has no
reason to. `HEAD` is still `abc`, the check passes, and the uncommitted edit is destroyed
by the mechanism that exists to prevent exactly that, in the direction §1.7's human-edit
supremacy most forbids.

**The decision.** One module carries every write to a durable state class (§3). Serving a
file for editing returns a **SHA-256 of its bytes**, opaque to the client; a write
presenting a token that no longer matches the file on disk is **rejected**, naming the
file, and is never merged, reconciled or partially applied. An accepted write replaces the
file whole via a temp file and `rename()`, then **commits it, path-scoped, attributed to
whoever acted** — §41: *"Curator commits are machine-authored. Direct human changes are
human-authored."* An author's edit through a surface is a direct human change and commits
as theirs; a Curator pass commits as the machine. Granularity is file-level; one write
targets one file. Derived state (§42) is outside this path entirely.

Committing is the half of this decision that is easy to miss and expensive to omit. Without
it, an app write leaves the file with uncommitted modifications, and #32's dirty-tree rule
— *"the Curator never writes into a file with uncommitted human modifications"* — then
closes every file the author touches in the app to the Curator until someone commits by
hand. That is a designed-in deadlock arriving at M4 from a decision left implicit at M3.
Committing also makes #32's human-touched flag work for free: it is defined over
non-Curator commits, and an app write committed as the author is one.

## Considered Options

**`HEAD` plus a dirty check.** The plan's literal reading, repaired. Rejected in both of
its forms. Repo-wide, it makes every file unwritable while the author has one unrelated
Obsidian buffer saved. Per-file, it cannot distinguish *dirty when I served it* from
*dirty since I served it* — so a file already modified in Obsidian, the normal state for
someone working there, rejects every write forever until a hand commit. That is the
mechanism denying the author access to their own file.

**mtime or size.** Rejected on both error directions. A save that rewrites byte-identical
content bumps mtime and produces a spurious rejection; and this repo lives on `/mnt/c`
under WSL's DrvFs, whose timestamp granularity is coarse enough to miss a fast edit
entirely — a false *pass*, which is the direction §1.7 forbids.

**Paragraph-level granularity.** Rejected, and it has only two implementations. Positional
("replace paragraph 12") is invalidated by any insert or delete above the target, so an
Obsidian edit elsewhere silently lands the write on the wrong prose — worse than an
overwrite, because nothing in git looks wrong afterwards. §4.1 removed durable passage
identity by design, so position is all that remains. Content-addressed ("replace the
paragraph hashing to X") works, but it is patch application onto a file that has moved:
reconciliation, which §40.6's reduction cut by name. Adopting it re-expands the
coordinator the PoC removed. `../open-problems.md` §1.2 reached the same conclusion from
a different premise, since corrected there.

**Not committing, and teaching the dirty-tree rule to tell an app write from a human
edit.** Rejected. The distinction needs a sidecar journal of what the app wrote — state
that can drift from the file it describes — and when that journal is stale or lost, the
Curator writes over a real human edit. It invents a mechanism to avoid using the one §41
already designates, and it fails toward the machine.

**Locking the read-compare-write sequence.** Rejected. A lock constrains only writers that
take it, and the writer this mechanism exists to defend against is Obsidian, which will
never take a lock Memoria invents. It would pay §40.6's coordinator cost to protect
against Memoria's own concurrent requests alone.

**Multi-file atomicity.** Rejected as having no caller. Every write the PoC names is
single-file: match terms (#26), badged statements (#31), settlements stored on the entry
(#33), a rewritten passage in one `draft.md` (#43). A Curator pass across many entries is
many independent writes, where partial application is correct rather than a defect.
Reordering the outline renumbers directories (§2.1), but that changes *paths*, not bytes —
a content hash would pass trivially while the thing that moved went unchecked. It needs a
different mechanism if it is ever built, not this one.

**Returning the file's current contents with a rejection.** Rejected, though it is not
reconciliation and was tempting. It puts a second copy of the read logic inside the write
endpoint — the pattern #36 exists to prevent — when #64 already builds the read and the
client can simply issue one.

## Consequences

- **A residual TOCTOU window is accepted and documented.** Between comparing the hash and
  writing the file, a concurrent save can land and be overwritten. Closing it requires the
  lock rejected above, which would not constrain the writer that matters. The
  temp-file-plus-`rename()` is unrelated to this and worth doing anyway: it makes the
  write itself atomic, so no reader sees a half-written file and a crash leaves the
  original intact.
- **The Curator is a second caller of the token check, not a special case.** Because app
  writes now commit, an author's edit made between the Curator's read and its write leaves
  a *clean* tree, which the dirty-tree rule cannot see. The Curator therefore passes two
  layered gates: the dirty-tree rule first (uncommitted human work — do not try), then the
  token check (committed work I have not seen). They answer different questions and neither
  subsumes the other. #31 and #32 are annotated accordingly.
- **The commit is path-scoped to the file written.** An unscoped commit would sweep in the
  author's in-progress Obsidian work, misattribute it to this write, and — worse — *clean*
  those files, silently defeating the dirty-tree rule for every one of them. The dirty tree
  is load-bearing; the write path must not tidy it.
- **Scope is by state class, not by caller.** Manuscript, Subjects, Claims, Working state
  and Change record go through the path; Derived does not. Scoping by caller would put the
  Curator outside it. This also keeps the "no module writes a repo file directly" test
  buildable: `normalize`, `editorial`, `cross_references` and `answer_key` all write into
  the repo today, all of it Derived, and a test not scoped to durable paths would be red on
  arrival. `rebuild` has no prior read and therefore no token, so routing it through the
  path would force a bypass — and a bypass inside the one module that carries every write
  is the hole that makes the rule unenforceable.
- **The rejection is a declared response model**, carrying the outcome and the file path
  and nothing else. #64 generates TypeScript types from the OpenAPI schema; a typed
  rejection is discriminable at compile time, where a string forces every client to
  re-parse prose in exactly the case that most needs to be handled correctly.
- **The client never clears its editing buffer except on success.** Recovery from a
  rejection is composed from what already exists — keep the author's text on screen, re-read
  through the normal read path for current contents and a fresh token. This is what makes
  file-level granularity survive the in-app prose editor if it is ever built: the cost of a
  rejection is a re-read, never lost work.
- **§11's human checkpoint commits are unblocked but not built here.** `CHG-` IDs and the
  `changes/` projection are filed as their own issue. §42 lists change projections among
  rebuildable derived state, so building the projection later costs nothing irrecoverable —
  provided the commits exist now, which this decision secures.
- **§40.6 is amended in place** to record that the git-revision comparison was wrong, so a
  future reader does not re-derive the trap from the plan text.
- **Creation is a second door, not a bypass** (amended 2026-09-01, #17). Promotion
  materializes an entry file that has no prior read and so no token. Rather than a
  token-less write around the module, `create` lives in it, gated by non-existence:
  `Rejected(outcome="exists")` if the path has a file behind it, otherwise the same
  confinement, checkpoint, atomic replace and path-scoped attributed commit as `write`.
  It can never overwrite, which is the property the token exists to protect; what it
  gives up is only the ability to be told a file was changed underneath it, and a file
  that does not exist has nothing underneath.
- **Revisit if** a durable write appears that genuinely needs two files changed together,
  or if Curator passes become atomic over a run rather than per-file — at which point the
  token is the wrong shape for that caller and it needs a pass-level baseline instead.
