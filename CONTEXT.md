# Memoria

Memoria is a system for writing a book from a large personal archive without the
author managing context windows. This glossary records terms as they are settled.
The build plan under `docs/plan/` defines the rest of the vocabulary; terms here
are the ones resolved in working sessions and take precedence where they differ.

## Language

### The subject system

**Subject**:
A named dimension along which the archive connects to the book — People, Timeline,
Events, Themes, Arcs, and others the author adds. It is both a check the Curator
performs on new manuscript prose and an index a writing agent reads instead of the
corpus. On screen the three trees are `MANUSCRIPT` / `SUBJECTS` / `SOURCES`, and a
new one is added with `+ New subject`.
_Avoid_: Axis, group, category, object type, dimension, lens

**Entry**:
One instance under a subject — Bob under People, the acquisition under Events. The
subject says what a kind of entry is; the entry carries the links and the author's
own knowledge.
_Avoid_: Item, object, record, node

**Gathered set**:
The sources a subject matched to an entry. Derived, rebuildable, and asserts nothing
on its own.
_Avoid_: Matches, index, link set, results

**Pin** / **Exclude**:
Author acts overlaying a gathered set — pin keeps a source in regardless of what the
pass finds; exclude keeps one out. Both are attributable and survive a rebuild.
_Avoid_: Include/ignore, accept/reject, approve/deny

### The two consumers

**Assembly**:
Resolving a declared scope ("dates X to Y, Bob, the conflict in the capital") through
the subjects into a working context to write from. Happens at write time, in service of a
session; it is not curation.
_Avoid_: Context building, retrieval, gathering

**Audit**:
Evaluating new manuscript prose — hand-written or AI-written — against the entries,
bounded by the subjects. Only new text is audited, and only on subjects that exist.
_Avoid_: Review, check, validation, impact analysis

### Author knowledge

**Author testimony**:
A fact the author asserts in an entry with no documentary basis — Bob's birth year,
his build. The entry is its own source, and it outranks documentary evidence that
disagrees.
_Avoid_: Author note, recollection, memory, annotation

**Settlement**:
A recorded author resolution of a surfaced conflict, naming which side was chosen and
when. Downstream passages relying on it inherit the resolution and stay silent.
_Avoid_: Dismissal, decision, override, resolution
