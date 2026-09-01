# SRC- IDs are allocated by the manifest ledger

The normalized-record schema said a `SRC-` ID is "assigned sequentially in a deterministic
document order … not a hash or a counter file". That was written for a fixed ten-file
corpus, and it was correct there: the same input always produced the same numbering. It
is wrong for the archive Memoria is actually for, which arrives in deliveries — a second
email export, a folder found later. The first raw file that sorts into the middle of the
order renumbers every record after it, and every citation in every entry and every
manuscript paragraph goes stale at once. Since ADR-0005 the extraction's placements are
keyed by paragraph anchor too, so a renumber also orphans a model pass the author paid
for. We settle it on 2026-09-01: **the evidence manifest is the ID ledger**. A raw unit — a
file, or one message inside an export — is numbered on the run that first lists it in
`raw/manifest.yaml`, keeps that number forever, keeps it reserved if the unit is later
deleted, and no number is ever reused.

The rule the schema was protecting survives: an ID is still a function of committed
input, not of run order or process state. What changes is which input — the manifest,
which is already the hashed, committed, human-reviewable list of raw files, rather than a
sort of the filesystem.

## Considered Options

**Sequential over sorted input, as the schema said.** Simplest, no new state, and
verifiably deterministic. Rejected because it is deterministic over the *whole* input,
and the whole input changes every time the archive grows. It cannot be repaired by a
clever sort order: any order that places a late arrival anywhere but the end renumbers,
and "always at the end" is a ledger by another name.

**Content-derived IDs.** Hash the raw unit and its locator into the identifier. Stable
under growth and needs no ledger. Rejected because it abandons the six-digit form every
document, mockup and citation uses, a person can no longer read order or vintage off an
ID, and two deliveries of a byte-identical file — a common thing in email exports — would
collide rather than be noticed.

**A separate allocation file.** The ledger, but in its own file beside the manifest.
Rejected as a second store for facts the manifest already holds per unit; it would drift
from the manifest the first time one was edited without the other.

## Consequences

- `raw/manifest.yaml` gains an ID column per raw unit. For an email export, the manifest
  lists messages, not just the export file — a message is a raw unit.
- The schema's `id` row is reworded to "order of first appearance in the manifest".
  `memoria validate` checks the ledger is dense, monotonic, and that no ID appears twice.
- A normalization run (part 05 §5.4) over a new delivery appends to the ledger and writes
  only new records; nothing existing is renumbered. This is what makes skip-unchanged
  runs and the converter-drift report coherent.
- Reserved numbers for deleted units mean the count of records and the highest ID can
  differ. That is expected and the health report (part 15) says so rather than warning.
