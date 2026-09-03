"""The subject system's durable half: subjects, entries, and match terms.

Part 06 §8 of the build plan. A **subject** is a named dimension along which
the archive connects to the book - People, Timeline, Events, Themes, Arcs,
and whatever the author adds. Its prompt carries four required declarations:
what counts as a match, the matching hazards, the audit questions it asks of
new prose, and whether it auto-promotes (ADR-0005). An **entry** is one
instance under a subject; its body is shared territory holding the author's
unbadged testimony alongside Memoria's badged statements, and its match terms
are the system's *only* alias store - there is no `_aliases.yaml`
(part 05 §7).

This module owns both directions of both formats, the same way
`memoria.records` owns the normalized record: a subject or entry prompt
written by `*_to_markdown` and read back by `parse_*` must round-trip, and a
change to either that the other does not match is a corruption.

`write_builtin_subjects` seeds the five built-ins the way
`records.write_normalized_records` writes derived records, and it never
overwrites a file the author has already touched - it is not a durable
write. The one durable write this module owns is `set_match_terms` (#26),
the author editing an entry's match terms, and it goes through `memoria.write`
like every other write to a durable state class (ADR-0003).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from pathlib import Path

import yaml

from memoria.repository import Repository
from memoria.write import Actor, WriteError, WriteResult, serve, write as write_file

# Where subjects live inside the book repository (part 04 §2's
# `subjects/<slug>/_subject.md`, `subjects/<slug>/<entry-slug>.md`).
SUBJECTS_RELATIVE_PATH = "subjects"

_SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_ENTRY_REF_RE = re.compile(rf"^SUB-{_SLUG}/{_SLUG}$")

_BADGE_RE = re.compile(r"^\[(author|source|inferred|open)\]\s*")


class SubjectError(Exception):
    """A subject or entry prompt could not be read, and why."""


@dataclass(frozen=True)
class Subject:
    """One subject's prompt - the four things part 06 §8.1 requires."""

    id: str
    match: str
    hazards: str
    audit_questions: str
    auto_promote: bool


@dataclass(frozen=True)
class OverlayAct:
    """One pin or exclusion recorded on an entry (part 06 §8.3's curated
    overlay). An attributable author act, not machine output - part 04 §42
    is explicit that it "is never regenerated" and survives even
    ``.memoria/index.db`` being deleted outright, which is why it is stored
    here rather than in the index. A later act against the same ``anchor``
    replaces this one rather than stacking a history of it, the same
    click-authorized shape as a settlement (§8.7).
    """

    anchor: str
    action: str
    actor_name: str
    actor_email: str
    at: str


@dataclass(frozen=True)
class Entry:
    """One entry under a subject.

    ``match_terms`` may name a plain word, an entry reference (``SUB-x/y``),
    or a relation between two entry references - part 06 §8.2/§8.4's
    extension. ``body`` is raw markdown: unbadged testimony and Memoria's
    badged statements, shared territory read by ``parse_statements``.
    ``overlay`` is the entry's pins and exclusions (``OverlayAct``); the
    gathered set itself is derived and carries no state of its own
    (``memoria.index.gather``).

    ``extra`` carries any frontmatter key this module does not itself model,
    untouched through ``parse_entry``/``entry_to_markdown`` - the same
    contract ``memoria.manifest.ManifestEntry.extra`` keeps. ``pin``/
    ``exclude`` (#21) are the first callers that rewrite an *existing*
    entry file rather than only ever creating one, so this is what stops
    that rewrite from silently dropping a field the author or a future
    writer put there.
    """

    id: str
    match_terms: list[str] = field(default_factory=list)
    body: str = ""
    overlay: list[OverlayAct] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Statement:
    """One paragraph of an entry body, with its badge if it has one.

    ``badge`` is ``None`` for author testimony - the absence of a badge *is*
    the attribution (part 06 §9.5).
    """

    badge: str | None
    text: str


# --- the subject prompt format ----------------------------------------------


def subject_to_markdown(subject: Subject) -> str:
    """Serialize a subject prompt: frontmatter, then its three sections."""
    frontmatter = {"id": subject.id, "auto-promote": subject.auto_promote}
    body = (
        f"## Match\n\n{subject.match}\n\n"
        f"## Hazards\n\n{subject.hazards}\n\n"
        f"## Audit questions\n\n{subject.audit_questions}\n"
    )
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + body


def parse_subject(text: str, *, source: str = "<string>") -> Subject:
    """Parse a subject prompt back into a ``Subject``.

    The inverse of ``subject_to_markdown``. Fails loudly, naming which of the
    four required declarations is missing, rather than defaulting one -
    ``memoria validate`` reports the same failure (issue #16).
    """
    frontmatter, body = _split_frontmatter(text, source)

    if "id" not in frontmatter:
        raise SubjectError(f"{source}: subject prompt is missing 'id'")
    if "auto-promote" not in frontmatter:
        raise SubjectError(
            f"{source}: subject prompt is missing its auto-promote "
            "declaration (part 06 §8.1's fourth requirement, ADR-0005)"
        )
    auto_promote = frontmatter["auto-promote"]
    if not isinstance(auto_promote, bool):
        raise SubjectError(
            f"{source}: 'auto-promote' must be a YAML boolean, got "
            f"{auto_promote!r}"
        )

    sections = _split_sections(body)
    if "match" not in sections:
        raise SubjectError(
            f"{source}: subject prompt is missing its match declaration "
            "(## Match) - what counts as a match under this subject"
        )
    if "hazards" not in sections:
        raise SubjectError(
            f"{source}: subject prompt is missing its hazards declaration "
            "(## Hazards) - the subject's matching hazards"
        )
    if "audit questions" not in sections:
        raise SubjectError(
            f"{source}: subject prompt is missing its audit questions "
            "declaration (## Audit questions)"
        )

    return Subject(
        id=str(frontmatter["id"]),
        match=sections["match"],
        hazards=sections["hazards"],
        audit_questions=sections["audit questions"],
        auto_promote=auto_promote,
    )


def _split_sections(body: str) -> dict[str, str]:
    """The ``## Heading`` sections of a prompt body, lower-cased and keyed."""
    heading_re = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(body))
    sections: dict[str, str] = {}
    for position, match in enumerate(matches):
        start = match.end()
        stop = matches[position + 1].start() if position + 1 < len(matches) else len(body)
        sections[match.group(1).strip().lower()] = body[start:stop].strip()
    return sections


# --- entries -----------------------------------------------------------------


def entry_to_markdown(entry: Entry) -> str:
    """Serialize an entry: frontmatter (id, match terms, overlay, then any
    ``extra`` keys), then its body. ``overlay`` is omitted from the
    frontmatter entirely when empty, the common case, rather than writing a
    bare ``overlay: []`` to every entry that has never been pinned or
    excluded. ``extra`` is appended last - the same order
    ``memoria.manifest.save_manifest`` uses - so a rewrite (``pin``/
    ``exclude``, #21) round-trips whatever this module does not itself
    model instead of dropping it."""
    frontmatter = {"id": entry.id, "match_terms": list(entry.match_terms)}
    if entry.overlay:
        frontmatter["overlay"] = [
            {
                "anchor": act.anchor,
                "action": act.action,
                "actor_name": act.actor_name,
                "actor_email": act.actor_email,
                "at": act.at,
            }
            for act in entry.overlay
        ]
    frontmatter.update(entry.extra)
    return (
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n\n" + entry.body + "\n"
    )


def parse_entry(text: str, *, source: str = "<string>") -> Entry:
    """Parse an entry back into an ``Entry``.

    ``id`` must be a well-formed ``SUB-<subject>/<entry-slug>`` reference -
    the same shape ``classify_match_term`` requires of an entry reference -
    so a malformed id (missing the ``SUB-`` prefix, missing its ``/<slug>``
    entirely, or with an empty segment on either side) is a checked property
    here rather than a hole below the directory-mismatch check (#91, #119).

    Every match term is classified with ``classify_match_term``, which
    raises on a malformed entry reference or relation - this is what makes
    "validation accepts all three shapes" a checked property rather than a
    hope.
    """
    frontmatter, body = _split_frontmatter(text, source)

    if "id" not in frontmatter:
        raise SubjectError(f"{source}: entry is missing 'id'")
    entry_id = str(frontmatter["id"])
    if not _ENTRY_REF_RE.match(entry_id):
        raise SubjectError(
            f"{source}: entry id {entry_id!r} is not of the form "
            "SUB-<subject>/<entry-slug>"
        )

    match_terms = frontmatter.get("match_terms", [])
    if not isinstance(match_terms, list):
        raise SubjectError(f"{source}: 'match_terms' must be a list")
    match_terms = [str(term) for term in match_terms]
    for term in match_terms:
        try:
            classify_match_term(term)
        except SubjectError as exc:
            raise SubjectError(f"{source}: {exc}") from exc

    overlay = [
        _parse_overlay_act(row, source) for row in frontmatter.get("overlay", [])
    ]
    extra = {
        key: value
        for key, value in frontmatter.items()
        if key not in ("id", "match_terms", "overlay")
    }

    # Exactly the separators entry_to_markdown inserted around the body -
    # the blank line after the frontmatter's closing "---" and the trailing
    # newline the file ends with - and no more.
    if body.startswith("\n"):
        body = body[1:]
    if body.endswith("\n"):
        body = body[:-1]

    return Entry(
        id=entry_id, match_terms=match_terms, body=body, overlay=overlay, extra=extra
    )


def _parse_overlay_act(row: object, source: str) -> OverlayAct:
    if not isinstance(row, dict):
        raise SubjectError(f"{source}: 'overlay' row is not a mapping: {row!r}")
    missing = {"anchor", "action", "actor_name", "actor_email", "at"} - row.keys()
    if missing:
        raise SubjectError(
            f"{source}: 'overlay' row is missing {sorted(missing)!r}: {row!r}"
        )
    action = str(row["action"])
    if action not in ("pin", "exclude"):
        raise SubjectError(
            f"{source}: 'overlay' row has action {action!r}, expected 'pin' "
            "or 'exclude'"
        )
    return OverlayAct(
        anchor=str(row["anchor"]),
        action=action,
        actor_name=str(row["actor_name"]),
        actor_email=str(row["actor_email"]),
        at=str(row["at"]),
    )


def classify_match_term(term: str) -> str:
    """Which of the three shapes a match term takes.

    Returns ``"word"``, ``"entry"`` or ``"relation"``. Raises ``SubjectError``
    for a term that looks like it is trying to be an entry reference or a
    relation but is malformed - a plain word is always accepted, since it
    carries no shape to get wrong.
    """
    term = term.strip()
    if " -> " in term:
        parts = term.split(" -> ")
        if len(parts) != 3:
            raise SubjectError(
                f"malformed relation match term: {term!r} - expected "
                "'entry -> verb -> entry'"
            )
        left, verb, right = parts
        if not verb.strip():
            raise SubjectError(
                f"malformed relation match term: {term!r} - relation is "
                "missing a verb"
            )
        if not _ENTRY_REF_RE.match(left) or not _ENTRY_REF_RE.match(right):
            raise SubjectError(
                f"malformed relation match term: {term!r} - both ends must "
                "be entry references (SUB-x/y)"
            )
        return "relation"
    if "->" in term:
        # An attempted relation missing its required spaces. Falling through
        # to the "SUB-" check below would diagnose this as a malformed
        # entry-reference when it starts with one - sending the author to
        # look at the wrong declaration - so a bare '->' is always a relation
        # complaint: part 06 §8.4 requires the spaced 'entry -> verb -> entry'
        # form, and this module does not invent a second, unspaced one.
        raise SubjectError(
            f"malformed relation match term: {term!r} - relations need "
            "spaces around '->': 'entry -> verb -> entry'"
        )
    if term.startswith("SUB-"):
        if not _ENTRY_REF_RE.match(term):
            raise SubjectError(
                f"malformed entry-reference match term: {term!r} - expected "
                "SUB-<subject>/<entry> (lowercase slugs)"
            )
        return "entry"
    return "word"


def parse_statements(body: str) -> list[Statement]:
    """An entry body's paragraphs, each with its badge if it has one.

    Testimony (no badge) and Memoria's badged statements (``[author]``,
    ``[source]``, ``[inferred]``, ``[open]``) are shared territory in the
    same body (part 06 §8.2); this is what makes them distinguishable rather
    than merely visually different.
    """
    statements = []
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        match = _BADGE_RE.match(paragraph)
        if match:
            statements.append(
                Statement(badge=match.group(1), text=paragraph[match.end():].strip())
            )
        else:
            statements.append(Statement(badge=None, text=paragraph))
    return statements


def is_audit_visible(statement: Statement) -> bool:
    """Whether a statement belongs to the **audit-visible body** - the part
    of an entry assembly loads and the audit compares prose against
    (CONTEXT.md, part 06 §8.2): testimony and every badged statement except
    ``[open]``.

    One owner for the rule, called by ``memoria.audit.audit_visible_body``
    (which decides a memoization key) and by the entry view (#26, which
    decides what renders inside the body and what renders outside it). Two
    copies of a one-line predicate is how the two drift, and the surface
    would then show as audit-visible something the audit never reads.

    Memoria notes sit outside the body too (part 08 §14.2), but this
    codebase does not write them yet (#32); when it does they join
    ``[open]`` here rather than at either call site.
    """
    return statement.badge != "open"


def _split_frontmatter(text: str, source: str) -> tuple[dict, str]:
    """The frontmatter mapping and the raw body below it."""
    if not text.startswith("---\n"):
        raise SubjectError(f"{source}: not a subject/entry file - no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise SubjectError(f"{source}: frontmatter is not terminated")
    try:
        frontmatter = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise SubjectError(f"{source}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise SubjectError(f"{source}: frontmatter is not a mapping")
    return frontmatter, text[end + len("\n---\n") :]


# --- locating files on disk --------------------------------------------------


def _slug(subject_id: str) -> str:
    if not subject_id.startswith("SUB-"):
        raise SubjectError(f"not a subject id: {subject_id!r}")
    return subject_id[len("SUB-") :]


def subject_path(repository: Repository, subject_id: str) -> Path:
    """Where a subject's prompt would live."""
    return repository.root / SUBJECTS_RELATIVE_PATH / _slug(subject_id) / "_subject.md"


def load_subject(repository: Repository, subject_id: str) -> Subject:
    """Read one subject's prompt off disk."""
    path = subject_path(repository, subject_id)
    if not path.is_file():
        raise SubjectError(f"no such subject: {subject_id}")
    return parse_subject(path.read_text(encoding="utf-8"), source=str(path))


def find_entry_path(
    repository: Repository, subject_id: str, entry_slug: str
) -> Path | None:
    """The path to the entry with this ID, or ``None``.

    Tries the slug-matching filename first, then falls back to scanning
    every entry in the subject directory for a frontmatter ``id`` match -
    which is what makes a renamed file still resolve (issue #16's "stable
    `SUB-x/y` IDs in frontmatter surviving file rename").

    A file that fails to parse - a stray malformed entry that is not the one
    being looked up - is skipped rather than left to blow up the search: this
    function is a probe over every file in the directory, and one sibling's
    bad match term must not stop it from finding another entry that renamed
    cleanly.
    """
    subject_dir = repository.root / SUBJECTS_RELATIVE_PATH / _slug(subject_id)
    if not subject_dir.is_dir():
        return None
    target_id = f"{subject_id}/{entry_slug}"

    candidate = subject_dir / f"{entry_slug}.md"
    if candidate.is_file():
        try:
            entry = parse_entry(candidate.read_text(encoding="utf-8"), source=str(candidate))
        except SubjectError:
            entry = None
        if entry is not None and entry.id == target_id:
            return candidate

    for path in sorted(subject_dir.glob("*.md")):
        if path.name == "_subject.md" or path == candidate:
            continue
        try:
            entry = parse_entry(path.read_text(encoding="utf-8"), source=str(path))
        except SubjectError:
            continue
        if entry.id == target_id:
            return path
    return None


def load_entry(repository: Repository, subject_id: str, entry_slug: str) -> Entry:
    """Read one entry off disk by ID, surviving a file rename."""
    subject_dir = repository.root / SUBJECTS_RELATIVE_PATH / _slug(subject_id)
    if not subject_dir.is_dir():
        raise SubjectError(f"no such subject: {subject_id}")
    path = find_entry_path(repository, subject_id, entry_slug)
    if path is None:
        raise SubjectError(f"no such entry: {subject_id}/{entry_slug}")
    return parse_entry(path.read_text(encoding="utf-8"), source=str(path))


def entry_relative_path(repository: Repository, subject_id: str, entry_slug: str) -> str:
    """Where this entry's file lives, relative to the repository root.

    The write path takes a repository-relative path, and resolving one is
    this module's job rather than a caller's: ``find_entry_path`` is what
    makes a renamed file still resolve, and a caller that rebuilt the path
    from the slug would silently write a *second* file beside the renamed
    one.
    """
    subject_dir = repository.root / SUBJECTS_RELATIVE_PATH / _slug(subject_id)
    if not subject_dir.is_dir():
        raise SubjectError(f"no such subject: {subject_id}")
    path = find_entry_path(repository, subject_id, entry_slug)
    if path is None:
        raise SubjectError(f"no such entry: {subject_id}/{entry_slug}")
    return path.relative_to(repository.root).as_posix()


def serve_entry(repository: Repository, subject_id: str, entry_slug: str) -> tuple[Entry, str]:
    """One entry, plus the staleness token a later write must present.

    ``load_entry`` reads; this serves *for editing* (ADR-0003): the second
    value is ``memoria.write.serve``'s content hash of the file as it was
    read, opaque to whoever carries it. #26 is where that token first
    crosses HTTP - the author edits match terms in a browser and presents it
    back - so it has to be an explicit value the caller holds rather than
    something re-derived at write time, which is exactly what it exists to
    detect a change against.

    The file is read once, through ``serve``, and parsed from those same
    bytes: reading it a second time to parse would open a window in which
    the token describes a file the returned ``Entry`` did not come from.
    """
    relative_path = entry_relative_path(repository, subject_id, entry_slug)
    served = serve(repository, relative_path)
    return parse_entry(served.text, source=relative_path), served.token


def set_match_terms(
    repository: Repository,
    subject_id: str,
    entry_slug: str,
    match_terms: list[str],
    token: str,
    actor: Actor,
) -> WriteResult:
    """Replace an entry's match terms - the author's first durable write.

    Match terms are the author's (part 06 §8.2) and the system's only alias
    store, so this is an author act: it goes through the single write path
    with the token ``serve_entry`` minted, and a file changed underneath
    since then is ``Rejected(outcome="stale")`` rather than merged. Stale is
    not an exception (ADR-0003 decision 5) - it is the normal outcome a
    surface reports.

    Two things happen before the file is touched at all, both for
    ``index._record_overlay``'s reason - ``write`` replaces the file before
    it commits, so anything checked afterwards would be checked after a
    partial application:

    - an unattributed ``actor`` is refused, because an author act that
      cannot be committed as anyone's must not land on disk;
    - every term is classified, so a malformed one is refused here rather
      than written into a file that ``parse_entry`` then cannot read back.
      That failure mode is total: a bad term makes the whole entry
      unparseable, taking its testimony and its overlay with it.

    Everything else on the entry - the body, the pin/exclude overlay,
    ``extra``'s unmodelled frontmatter keys - round-trips untouched, which
    is what makes this safe to do to a file the author also edits in
    Obsidian.
    """
    if not actor.name.strip() or not actor.email.strip():
        raise WriteError(
            f"cannot set match terms on {subject_id}/{entry_slug}: an author "
            "act must be attributed - actor name and email may not be empty"
        )
    for term in match_terms:
        classify_match_term(term)

    relative_path = entry_relative_path(repository, subject_id, entry_slug)
    # Read through `serve_entry`, so this module has exactly one way of
    # turning an entry file into an `Entry`. Its token is discarded on
    # purpose: minting a fresh one here and writing against *that* would
    # pass the staleness check every time, which is the one thing this
    # write must not do. The token compared is the caller's, from the read
    # that produced what the author actually edited.
    entry, _minted_here_and_unused = serve_entry(repository, subject_id, entry_slug)
    content = entry_to_markdown(dataclass_replace(entry, match_terms=list(match_terms)))
    return write_file(repository, relative_path, token, content, actor)


# --- the five built-in subjects ---------------------------------------------

BUILTIN_SUBJECTS: list[Subject] = [
    Subject(
        id="SUB-people",
        match="An entry under People represents a person.",
        hazards=(
            "Several people may share a surname; do not merge them without "
            "corroboration. One person may be referred to under several "
            "forms - name, role, initial, honorific, married name, or "
            "place - and matching must cover aliases, initials, honorifics, "
            "married names and location forms."
        ),
        audit_questions=(
            "Does the passage contradict a settled fact about this person?\n"
            "Does it mischaracterize them under the current reading?"
        ),
        auto_promote=False,
    ),
    Subject(
        id="SUB-timeline",
        match=(
            "An entry under Timeline represents a period or date range in "
            "the archive's chronology."
        ),
        hazards=(
            "Do not merge two periods on the strength of a shared label "
            "alone; a partial date may belong to more than one period. "
            "Contemporaneous and retrospective dating for the same period "
            "can disagree - do not silently prefer one."
        ),
        audit_questions=(
            "Does the passage place an event outside its settled period?\n"
            "Does it assume a chronology the archive does not support?"
        ),
        auto_promote=False,
    ),
    Subject(
        id="SUB-events",
        match=(
            "An entry under Events represents a discrete happening the "
            "archive records."
        ),
        hazards=(
            "Do not merge two events described from different vantage "
            "points without corroboration; the same happening can be "
            "reported under different names or dates by different sources. "
            "Do not conflate a recurring kind of event with one specific "
            "instance of it."
        ),
        audit_questions=(
            "Does the passage contradict a settled fact about this event?\n"
            "Does it place the event out of step with the entry's account?"
        ),
        auto_promote=False,
    ),
    Subject(
        id="SUB-themes",
        match=(
            "An entry under Themes represents a recurring concern the "
            "author reads across the archive, not a fact reported by any "
            "one source."
        ),
        hazards=(
            "Do not treat two differently-named concerns as one without "
            "checking whether the author's reading actually unifies them; "
            "a theme can drift as more evidence joins it, so a match made "
            "early may not hold later."
        ),
        audit_questions=(
            "Is the passage's framing still in step with the entry's "
            "current reading?\n"
            "Does the passage assert something as fact that the entry "
            "holds only as interpretation?"
        ),
        auto_promote=False,
    ),
    Subject(
        id="SUB-arcs",
        match=(
            "An entry under Arcs represents a transformation the author "
            "reads across the archive - a change in a relationship, a "
            "person, or a situation over time."
        ),
        hazards=(
            "Do not treat a single episode as the whole arc; do not assume "
            "the direction of change without corroboration across more "
            "than one point in the archive."
        ),
        audit_questions=(
            "Does the passage assert the arc has resolved before the entry "
            "says it has?\n"
            "Does it contradict the direction of change the entry "
            "currently reads?"
        ),
        auto_promote=False,
    ),
]


def write_builtin_subjects(repository: Repository) -> list[Path]:
    """Materialize the five built-in subjects, without touching one the
    author has already edited.

    Every subject the author "may change any of them" (part 06 §8.1), so
    this only fills in what is missing - it never overwrites an existing
    ``_subject.md``.
    """
    written = []
    for subject in BUILTIN_SUBJECTS:
        path = subject_path(repository, subject.id)
        if path.is_file():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(subject_to_markdown(subject), encoding="utf-8")
        written.append(path)
    return written


# --- loading everything, and naming a new entry ------------------------------


def load_all_subjects(repository: Repository) -> list[Subject]:
    """Every subject in the repository, by id.

    The extraction needs all of them at once - it hands their prompts to the
    model and hashes them into its memo key - and until now nothing did, so
    every caller walked ``subjects/`` itself. A subject directory whose
    ``_subject.md`` is missing is skipped; one that fails to parse raises,
    because a half-written subject silently dropped out of the digest would
    change every memo key without saying so.
    """
    root = repository.root / SUBJECTS_RELATIVE_PATH
    if not root.is_dir():
        return []
    subjects = []
    for directory in sorted(root.iterdir()):
        prompt = directory / "_subject.md"
        if not prompt.is_file():
            continue
        subjects.append(
            parse_subject(prompt.read_text(encoding="utf-8"), source=str(prompt))
        )
    return sorted(subjects, key=lambda subject: subject.id)


def is_seeded(repository: Repository) -> bool:
    """Whether ``memoria seed-subjects`` has run here (#157).

    The same condition ``load_all_subjects`` and ``load_all_entries`` both
    return empty on - the ``subjects/`` directory's existence. Without it a
    caller holding an empty subject list cannot tell an unseeded repository
    from a seeded one whose subjects were all deleted, and has to guess which
    to tell the author (ADR-0004).

    **The directory, not its contents.** A ``subjects/`` that exists holding
    no ``_subject.md`` reads as seeded-and-empty, which is a lie when seeding
    was interrupted part-way. Deliberate: the stricter test - does any
    subject prompt exist - is definitionally ``bool(load_all_subjects(...))``
    and so carries nothing the caller's own list did not already carry, which
    is exactly the third state this predicate exists to add. It would also
    make sources and subjects answer differently for structurally identical
    situations, since ``sources/normalized/`` holding no records is the state
    ``records.is_normalized`` reports as normalized-and-empty. The narrow
    case stays narrow: ``write_builtin_subjects`` lands each prompt with its
    directory, and git tracks no empty directory, so a fresh clone never has
    this shape.

    Additive: both loaders behave exactly as before.
    """
    return (repository.root / SUBJECTS_RELATIVE_PATH).is_dir()


def load_all_entries(repository: Repository) -> dict[str, Entry]:
    """Every entry in the repository, keyed by ``SUB-x/y``.

    Unlike ``load_all_subjects`` a file that fails to parse is **skipped**,
    matching ``find_entry_path``: this is a sweep across every entry the
    author has, and one malformed match term must not stop the extraction
    placing anything against the rest.
    """
    root = repository.root / SUBJECTS_RELATIVE_PATH
    if not root.is_dir():
        return {}
    entries: dict[str, Entry] = {}
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "_subject.md":
                continue
            try:
                entry = parse_entry(path.read_text(encoding="utf-8"), source=str(path))
            except SubjectError:
                continue
            entries[entry.id] = entry
    return entries


def entry_slug_for(label: str) -> str:
    """The entry slug a label promotes to.

    This module owns the ``SUB-<subject>/<entry>`` id format, so it owns the
    rule for making one - promotion (#17) is the first caller, and inventing
    a second slugifier next to ``_SLUG`` would let the two drift.

    Raises rather than returning something unusable when a label has no
    slug in it at all: a candidate labelled only with punctuation is a
    finding to look at, not an entry to name ``-``.
    """
    normalized = unicodedata.normalize("NFKD", label)
    ascii_only = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.casefold()).strip("-")
    # A slug must start with a letter (`_SLUG`), so a label that begins with a
    # digit - a year under Timeline, most obviously - is prefixed rather than
    # rejected.
    if slug and not slug[0].isalpha():
        slug = f"e-{slug}"
    if not slug or not re.fullmatch(_SLUG, slug):
        raise SubjectError(f"no entry slug can be made from label: {label!r}")
    return slug
