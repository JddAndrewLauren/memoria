"""The extraction: the subject system's one candidate engine.

Part 06 §8.4 and §8.12, and `docs/adr/0005-extraction-is-the-candidate-engine.md`.

The **extraction** is an author-launched pass in which a model reads every
paragraph of the archive for what it mentions - the entries it places, the
surface forms it cannot place, the relations between them - and from that
proposes candidates under every subject, clusters offered under Themes and
Arcs, and match terms on the entries it placed. It asserts nothing.

Three properties shape every function here.

**The model proposes; match terms decide.** Nothing in this module resolves
identity on its own authority. The model's reading is cached verbatim, and
the durable paragraph-to-entry mapping is recomputed from it *plus the
entries' current match terms*, deterministically, at every ``memoria
rebuild``. A placement the terms do not license is a proposed match term and
nothing more, until the author accepts it. There is still exactly one alias
store (part 05 §7).

**Match terms are not in the memo key.** Accepting a proposed term therefore
changes what is placed without re-reading one paragraph. Changing a *subject
prompt* does re-read everything, which is the same price part 06 §8.1
already puts on editing a subject.

**No model is called from here.** This module cannot call one and must not:
part 08 §12.1 says nothing that needs a model runs unasked, and
`docs/poc-plan.md` §3 forbids a model-driving service. The pass is driven by
a Claude Code session through the MCP tools, which hand paragraphs out and
take structured results back; everything in this file is either serving,
recording, or model-free computation over what was recorded.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from memoria import clustering
from memoria.clustering import ClusteringUnavailable, CoOccurrence
from memoria.index import (
    INDEX_RELATIVE_PATH,
    SearchFilters,
    SearchResult,
    connect,
    filter_predicate,
)
from memoria.records import read_all
from memoria.repository import Repository
from memoria.subjects import (
    Entry,
    Subject,
    SubjectError,
    classify_match_term,
    entry_slug_for,
    entry_to_markdown,
    load_all_entries,
    load_all_subjects,
    subject_to_markdown,
)
from memoria.write import Actor, Rejected, WriteError, create

# The recurrence filter's default (part 06 §8.4). Five or more distinct
# paragraphs collapses a candidate list by an order of magnitude, which is
# what makes promotion tractable. It is also a guaranteed miss generator,
# which is why a rejected candidate keeps all of its rows.
RECURRENCE_THRESHOLD_DEFAULT = 5

# How many match terms a promotion seeds at most. Part 06 §8.4 says the
# author tunes a Theme by editing its match terms; a Theme that promotes with
# two hundred of them is not tunable, so the promotion is an affordance
# rather than a dump.
MAX_SEEDED_MATCH_TERMS = 12

# The subjects whose entries gather by co-occurrence (ADR-0005 decision 6)
# rather than by being mentioned. Their entries are never handed to the model
# as placeable and never license a placement: a Theme named "grief" must not
# collect every paragraph containing the word, because its gathered set is
# #18's join over the placements of the entries and relations that define it.
CO_OCCURRENCE_SUBJECTS = frozenset({"SUB-themes", "SUB-arcs"})


def placeable_entries(entries: dict[str, Entry]) -> dict[str, Entry]:
    """The entries the extraction may place: everything outside
    ``CO_OCCURRENCE_SUBJECTS``."""
    return {
        entry_id: entry
        for entry_id, entry in entries.items()
        if entry_id.split("/", 1)[0] not in CO_OCCURRENCE_SUBJECTS
    }

# How much of a candidate's gloss is forms and how much is relations.
GLOSS_FORMS = 5
GLOSS_RELATIONS = 5

# The prefix that tells a candidate ref from an entry ref in the relation and
# cluster tables. `SUB-` is taken, and a candidate is not addressable outside
# the index - it has no file and nothing cites it.
CANDIDATE_REF_PREFIX = "CAND:"

# Why a surface form did not become a placement.
UNPLACED_BY_MODEL = "unplaced_by_model"
UNLICENSED_PLACEMENT = "unlicensed_placement"
NO_SUCH_ENTRY = "no_such_entry"
# Two entries license the same form. Surfaced, never resolved (part 05 §7).
AMBIGUOUS_TERMS = "ambiguous_terms"


class ExtractionError(Exception):
    """The pass was asked for something it cannot do, and why.

    One exception type, so the MCP adapter has exactly one thing to map onto
    ``ToolError`` - the same shape ``records.ReadError`` has for ``read``.
    """


# --- the prompts -------------------------------------------------------------
#
# These live here, as module constants, rather than as files in the
# repository. `subjects.BUILTIN_SUBJECTS` is the precedent: a body of prompt
# text is a versioned constant in the module that owns its meaning.
#
# The reason is the memo key. Every paragraph's cache entry is keyed on a
# hash of EXTRACTION_PROMPT, so the prompt has to be something the core can
# hash with no file read and no repository state - and, more importantly,
# something that changes only when a human changed it *in a reviewed commit*.
# A file under `subjects/` would be author territory, where an edit in
# Obsidian would silently invalidate every memo row in the archive with
# nobody having decided to.
#
# EDITING EITHER OF THESE INVALIDATES EVERY MEMO ROW IN EVERY ARCHIVE.
# The next extraction re-reads the whole corpus. Change them in a commit
# that says that is what it is doing.

EXTRACTION_PROMPT = """\
# The extraction

You are reading one paragraph of a personal archive at a time, recording what
it mentions. You are not summarizing it, answering questions about it, or
deciding what any of it means.

Below you are given the subject prompts - what counts as a match under each
subject, and that subject's matching hazards - and the names of the entries
that already exist. For each paragraph, record three things.

## 1. Placements

The entries you believe this paragraph mentions. For each, give the entry's
reference and **the exact surface form in this paragraph that made you place
it** - the words as they appear, not the entry's name.

Place only against the entries listed. If a paragraph mentions someone who
has no entry, that is an unplaced surface form, not a new entry: you have no
authority to create one.

## 2. Unplaced surface forms

Every mention you could not tie to a listed entry - a person, a date range,
an event, a place - with the subject you would file it under if you can tell.

**Unplaced is a first-class answer, not a failure.** These forms are how the
candidate list grows, and they are the only record of what the archive
mentions that the index does not yet know about. A mention you quietly drop
is invisible forever.

## 3. Relations

Links between two entries **you placed in this paragraph**, phrased with a
verb from the paragraph's own language: `Bob -> pressures -> the author`.

Both ends must be entries you placed in this same paragraph. Not a relation
to an unplaced form; not a relation to something in a different paragraph;
not a relation you know to be true from elsewhere in the archive or from
general knowledge. If the paragraph does not state it, it is not here.

## The discipline

- **Judge each paragraph alone.** Do not carry anything over from paragraphs
  earlier in this batch or this pass. What you record is cached against this
  paragraph's text and these prompts and nothing else, so a reading that
  depended on something you read earlier would be a cache entry that lies
  about what produced it.
- **You are proposing.** A placement the author's match terms do not license
  becomes a proposed match term for them to accept or reject - it does not
  rename anything and it does not settle who is who. Where two people might
  share a name, follow the subject's hazards and leave the mention unplaced
  rather than guessing.
- **Most paragraphs mention nothing on any subject.** Empty lists are the
  common and correct answer. Do not manufacture placements to look useful.
- **Do not quote the paragraph back.** Record identifiers and surface forms,
  not prose.
"""

CLUSTER_SUMMARY_PROMPT = """\
# Cluster summaries

You are writing the standing description of one cluster - a group of
paragraphs the extraction found because the same entries and relations recur
across them.

You will be given one of two things, and it decides what you write from.

- **A leaf cluster** gives you its member paragraphs. Write from those.
- **A parent cluster** gives you the summaries of its child clusters. Write
  from those, and only those. Do not reach past a child to the paragraphs
  underneath it: the whole point of the nesting is that an upper level is a
  compression of a compression.

Say what recurs across the members and what holds them together - the people,
the period, the situation, the change over time. Name what is actually there.

This text is `[inferred]`. It is **never evidence**: it is a compression, and
anything asserted from it has to be checked against the paragraphs it
compresses. Do not quote the paragraphs, do not cite them, and do not write
anything that would read as a finding. Someone who needs to know what the
archive says will read the archive.
"""

# Bumped when the *composition* of a key changes - which components go into
# it, or in what order. Changing this moves every key, which is the honest
# thing to do: a cache computed under different rules is not this cache.
MEMO_KEY_VERSION = "memoria-extraction-v1"
SUMMARY_KEY_VERSION = "memoria-cluster-summary-v1"


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _subject_digest(subject: Subject) -> str:
    """One subject prompt's contribution to the memo key.

    The whole serialized prompt, per part 06 §8.12's "hash(every subject
    prompt)" - which means flipping ``auto-promote`` or fixing a typo in an
    audit question costs a full-corpus re-read, even though ADR-0005 §5 hands
    the extractor only the match definition and the hazards. That is the
    spec taken literally, and §8.1 already prices editing a subject at a
    re-read, so it is not a surprise the author has not been sold.

    It is isolated in this function anyway: narrowing the key to
    ``(id, match, hazards)`` later is a change to this line and to one test.

    Hashing ``subject_to_markdown`` rather than the file's bytes is what
    keeps the key a function of *meaning*. Re-saving ``_subject.md`` with a
    different YAML key order or a trailing newline must not re-read the
    corpus, and reusing the existing serializer means there is no second
    canonical form to drift from the first.
    """
    return _h(subject_to_markdown(subject))


def subject_prompts_digest(subjects: Sequence[Subject]) -> str:
    """One digest over every subject prompt, ordered by subject id.

    Directory order and ``BUILTIN_SUBJECTS`` order are both accidents; the id
    order is the only one that is a fact about the repository.
    """
    ordered = sorted(subjects, key=lambda subject: subject.id)
    return _h("\n".join(_subject_digest(subject) for subject in ordered))


def paragraph_memo_key(paragraph_text: str, subjects_digest: str) -> str:
    """The cache key for one paragraph's extraction (part 06 §8.12).

    ``hash(paragraph) + hash(extraction prompt) + hash(every subject
    prompt)``, and deliberately **not** the entries' match terms: placement
    against those is a rebuild step over this cached value, so accepting a
    proposed term never re-reads the corpus.

    Composed as digests joined by newlines rather than as concatenated text,
    so no component can migrate across a boundary into the next.
    """
    return _h(
        "\n".join(
            [
                MEMO_KEY_VERSION,
                _h(paragraph_text),
                _h(EXTRACTION_PROMPT),
                subjects_digest,
            ]
        )
    )


def cluster_summary_memo_key(members: Sequence[str], *, member_kind: str) -> str:
    """The cache key for one cluster's summary.

    Keyed on **membership**, never on the cluster id: ids do not survive
    re-clustering (ADR-0005 decision 6), and the point of memoizing here is
    that a re-run landing on the same membership keeps the summary it already
    paid for.

    ``member_kind`` is ``'anchors'`` for a leaf, whose members are its
    paragraphs, and ``'summaries'`` for a parent, whose members are its
    children's summary keys. That second case is what makes "a parent's
    summary is generated from its children's summaries" structural rather
    than a promise the prompt makes: the parent's key cannot be computed
    without them, so a child whose summary changes moves every ancestor's key
    and regenerates the lot.

    The summary prompt's hash is in here too. ADR-0005 names membership only,
    but leaving the prompt out would mean editing ``CLUSTER_SUMMARY_PROMPT``
    silently kept every stale summary - the exact failure the extraction
    prompt's presence in the paragraph key exists to prevent.
    """
    if member_kind not in ("anchors", "summaries"):
        raise ExtractionError(f"unknown cluster member kind: {member_kind!r}")
    return _h(
        "\n".join(
            [
                SUMMARY_KEY_VERSION,
                _h(CLUSTER_SUMMARY_PROMPT),
                member_kind,
                _h("\n".join(sorted(members))),
            ]
        )
    )


# --- what the model returns --------------------------------------------------


@dataclass(frozen=True)
class ProposedPlacement:
    """The model's reading that this paragraph mentions ``entry_id``.

    ``surface_form`` is not decoration. It is the string that becomes the
    proposed match term when the entry's terms do not license the placement,
    and it is half of the derived gloss. Without it, "a placement match terms
    do not license becomes a proposed match term" has no term to propose.
    """

    entry_id: str
    surface_form: str


@dataclass(frozen=True)
class ProposedForm:
    """A mention the model could not tie to any entry, and where it would file
    it. ``subject_id`` may be empty when it fits no subject."""

    surface_form: str
    subject_id: str = ""


@dataclass(frozen=True)
class ProposedRelation:
    """A link the model read between two entries it placed in this paragraph.

    Both ends are entry references, validated against the same paragraph's
    placements. The type is therefore what enforces the prompt's two hardest
    rules: there is no second anchor field, so a cross-paragraph relation
    cannot be expressed at all, and an end that was not placed is refused
    rather than silently kept.
    """

    from_ref: str
    verb: str
    to_ref: str


@dataclass(frozen=True)
class ParagraphExtraction:
    """One paragraph's reading, as it is cached."""

    placements: tuple[ProposedPlacement, ...] = ()
    unplaced: tuple[ProposedForm, ...] = ()
    relations: tuple[ProposedRelation, ...] = ()

    def to_json(self) -> str:
        return json.dumps(
            {
                "placements": [
                    {"entry_id": p.entry_id, "surface_form": p.surface_form}
                    for p in self.placements
                ],
                "unplaced": [
                    {"surface_form": u.surface_form, "subject_id": u.subject_id}
                    for u in self.unplaced
                ],
                "relations": [
                    {"from_ref": r.from_ref, "verb": r.verb, "to_ref": r.to_ref}
                    for r in self.relations
                ],
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(text: str) -> "ParagraphExtraction":
        raw = json.loads(text)
        return ParagraphExtraction(
            placements=tuple(
                ProposedPlacement(p["entry_id"], p["surface_form"])
                for p in raw.get("placements", [])
            ),
            unplaced=tuple(
                ProposedForm(u["surface_form"], u.get("subject_id", ""))
                for u in raw.get("unplaced", [])
            ),
            relations=tuple(
                ProposedRelation(r["from_ref"], r["verb"], r["to_ref"])
                for r in raw.get("relations", [])
            ),
        )


# --- normalizing a surface form ----------------------------------------------

_WHITESPACE = re.compile(r"\s+")


def normalize_form(surface_form: str) -> str:
    """The comparable form of a mention.

    NFKC, casefold, collapse internal whitespace, strip surrounding
    punctuation. Deliberately no more than that: no stemming, no substring
    containment, no edit distance. Anything looser would be this module
    deciding that two different strings name the same thing, which is exactly
    the authority part 05 §7 withholds from it and which ADR-0005 decision 4
    rejects by name. Two forms that are genuinely one entry are joined by the
    author adding a match term, and that is the only way they are joined.
    """
    folded = unicodedata.normalize("NFKC", surface_form).casefold()
    folded = _WHITESPACE.sub(" ", folded).strip()
    return folded.strip(".,;:!?\"'()[]{}<>-—–“”‘’")


def implicit_name_term(entry_id: str) -> str:
    """The match term every entry has without declaring one - its own name.

    Part 06 §8.2 says match terms are how an entry is referenced *beyond the
    subject default*, and the default is the entry's own name. This is not
    stated in #17, and without it the system is absurd: an entry the author
    created by hand (§8.4 explicitly permits one) would place nothing, and
    every mention of its own name would come back as a proposed match term
    for its own name.
    """
    slug = entry_id.split("/", 1)[-1]
    return slug.replace("-", " ")


# --- the memo cache ----------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_paragraph_memo(
    repository: Repository,
    memo_key: str,
    anchor: str,
    value: ParagraphExtraction,
) -> None:
    """Cache one paragraph's reading.

    Writing goes through here, not through the adapter, because the value
    being written survives every rebuild: a malformed reading cached is a bad
    reading that no ``memoria rebuild`` will ever clear. Validation is the
    caller's (``record_extraction``); this is the write.
    """
    con = connect(repository)
    try:
        con.execute(
            "INSERT OR REPLACE INTO memo (key, kind, anchor, value, written_at) "
            "VALUES (?, 'paragraph', ?, ?, ?)",
            (memo_key, anchor, value.to_json(), _now()),
        )
        con.commit()
    finally:
        con.close()


def record_cluster_summary(repository: Repository, memo_key: str, text: str) -> None:
    """Cache one cluster summary, keyed on its membership.

    Stored under the same table as paragraph readings, because the predicate
    that decides what survives a rebuild is not "paragraph or cluster" but
    "can this be recomputed without a model" - and both answer no. Part 06
    §8.12's "one cache, two key compositions", made literal.
    """
    if not text.strip():
        raise ExtractionError("a cluster summary cannot be empty")
    con = connect(repository)
    try:
        con.execute(
            "INSERT OR REPLACE INTO memo (key, kind, anchor, value, written_at) "
            "VALUES (?, 'cluster_summary', '', ?, ?)",
            (memo_key, text, _now()),
        )
        con.commit()
    finally:
        con.close()


def _memo_values(con: sqlite3.Connection, kind: str) -> dict[str, str]:
    return {
        row[0]: row[1]
        for row in con.execute("SELECT key, value FROM memo WHERE kind = ?", (kind,))
    }


# --- deriving -----------------------------------------------------------------


@dataclass(frozen=True)
class DerivedCounts:
    """What one derive produced. Reported by ``memoria rebuild`` and by the
    pass, because #17 asks for the raw and filtered candidate counts and a
    number nobody prints is a number nobody checks."""

    paragraphs: int
    memo_hits: int
    memo_misses: int
    placements: int
    unplaced_forms: int
    relations: int
    candidates_raw: int
    candidates_above_threshold: int
    proposed_match_terms: int
    clusters: int
    recurrence_threshold: int
    clustering_backend: str
    per_subject: dict[str, tuple[int, int]] = field(default_factory=dict)


def candidate_id_for(subject_id: str, normalized_form: str) -> str:
    """A candidate's id, derived from what it is rather than where it sits.

    Content-derived so it survives a rebuild unchanged, which is what lets the
    author come back to a ranked list tomorrow and find the same rows.
    """
    digest = hashlib.sha1(f"{subject_id}\n{normalized_form}".encode("utf-8")).hexdigest()
    return f"{subject_id}#{digest[:12]}"


def derive(
    repository: Repository,
    *,
    recurrence_threshold: int = RECURRENCE_THRESHOLD_DEFAULT,
) -> DerivedCounts:
    """Recompute every derived extraction row from the memo cache plus the
    entries' current match terms. No model, no network.

    This is where "the model proposes; match terms decide" actually happens.
    The cache holds what the model read, unchanged since the pass; what the
    index holds is recomputed from it every time, against whatever the author
    has since decided their entries are called. Accepting a proposed match
    term and running ``memoria rebuild`` moves placements without a single
    paragraph being read again.

    Safe to run repeatedly; it destroys nothing but derived state.
    """
    subjects = load_all_subjects(repository)
    entries = load_all_entries(repository)
    digest = subject_prompts_digest(subjects)

    paragraphs = _paragraph_texts(repository)
    con = connect(repository)
    try:
        cached = _memo_values(con, "paragraph")

        readings: dict[str, ParagraphExtraction] = {}
        misses = 0
        for anchor, text in paragraphs.items():
            value = cached.get(paragraph_memo_key(text, digest))
            if value is None:
                misses += 1
                continue
            readings[anchor] = ParagraphExtraction.from_json(value)

        state = _Derived(
            entries=placeable_entries(entries), threshold=recurrence_threshold
        )
        state.read_placements(readings)
        state.build_candidates()
        state.read_relations(readings)
        state.build_glosses()
        backend = state.build_clusters()

        _clear_derived(con)
        state.write(con, recurrence_threshold, backend)
        con.commit()
    finally:
        con.close()

    return DerivedCounts(
        paragraphs=len(paragraphs),
        memo_hits=len(readings),
        memo_misses=misses,
        placements=len(state.placements),
        unplaced_forms=len(state.unplaced),
        relations=len(state.relations),
        candidates_raw=len(state.candidates),
        candidates_above_threshold=sum(
            1 for c in state.candidates.values() if c["above_threshold"]
        ),
        proposed_match_terms=len(state.proposed_terms),
        clusters=len(state.clusters),
        recurrence_threshold=recurrence_threshold,
        clustering_backend=backend,
        per_subject=state.per_subject_counts(),
    )


def _paragraph_texts(repository: Repository) -> dict[str, str]:
    """Every paragraph in the archive, by anchor, read from the record files.

    From the records rather than from the FTS5 copy beside them, and the
    reason is the same one ``read(ref)`` has: the index is derived state that
    carries no authority (part 04 §42), so evidence served out of it would be
    a pointer that may go stale rather than the thing itself. The two agree
    today - ``build_index`` inserts the paragraph verbatim - which is exactly
    why taking the convenient one would never be noticed if they ever stopped
    agreeing.

    It also means the extraction does not need an index at all: a pass can
    read and cache paragraphs on a repository where ``memoria rebuild`` has
    never run.
    """
    texts = {}
    for record in read_all(repository):
        for number, paragraph in enumerate(record.paragraphs, start=1):
            texts[record.anchor_id(number)] = paragraph
    return texts


def _clear_derived(con: sqlite3.Connection) -> None:
    """Empty the extraction's derived tables, leaving the FTS5 index and the
    memo cache alone. ``build_index`` drops them; this is the in-place form
    for a derive that runs without a full rebuild."""
    for table in (
        "placements",
        "unplaced_forms",
        "relations",
        "candidates",
        "candidate_forms",
        "candidate_paragraphs",
        "proposed_match_terms",
        "clusters",
        "cluster_members",
        "cluster_relations",
        "cluster_paragraphs",
        "extraction_meta",
    ):
        con.execute(f"DELETE FROM {table}")


class _Derived:
    """One derive's working state.

    A class rather than a chain of functions because every pass over the
    readings needs the one before it: candidates cannot be grouped until the
    unplaced forms are collected, relations cannot be resolved until the
    candidates exist to resolve them to, and the glosses need both.
    """

    def __init__(self, entries: dict[str, Entry], threshold: int):
        self.entries = entries
        self.threshold = threshold
        self.licensing = {
            entry_id: _licensing_terms(entry) for entry_id, entry in entries.items()
        }
        # The same terms the other way round: normalized form -> every entry
        # that licenses it. One owner is a placement; two are an ambiguity to
        # surface rather than a coin to toss.
        self.by_form: dict[str, list[tuple[str, str]]] = {}
        for entry_id, terms in sorted(self.licensing.items()):
            for form, term in sorted(terms.items()):
                self.by_form.setdefault(form, []).append((entry_id, term))
        self.placements: list[tuple[str, str, str, str]] = []
        self.unplaced: list[tuple[str, str, str, str, str]] = []
        self.relations: list[tuple[str, str, str, str]] = []
        self.proposed_terms: dict[tuple[str, str], int] = {}
        self.candidates: dict[str, dict] = {}
        self.candidate_forms: dict[str, dict[str, int]] = {}
        self.candidate_paragraphs: dict[str, set[str]] = {}
        # (anchor, normalized form) -> candidate id, for resolving relations.
        self._form_index: dict[tuple[str, str], str] = {}
        # anchor -> {normalized form: entry_id} for the placements that landed.
        self._placed: dict[str, dict[str, str]] = {}
        self.clusters: list[dict] = []
        self.cluster_members: list[tuple[str, str]] = []
        self.cluster_relations: list[tuple[str, str, str, str, int]] = []
        self.cluster_paragraphs: list[tuple[str, str]] = []

    # -- pass 1: placements, unplaced forms, proposed terms ------------------

    def read_placements(self, readings: dict[str, ParagraphExtraction]) -> None:
        """Apply the licensing rule to every surface form the model recorded.

        **Every** form, placed or unplaced. The model's ``entry_id`` is a
        proposal about which entry a form names; what decides is whether some
        entry's match terms license the form. Three cases follow, and the
        third is the one that closes the loop:

        - the model placed it and the named entry's terms license it -> a
          placement, recording which term did it;
        - the model placed it and nothing licenses it -> **two** rows, a
          proposed match term on the entry it named, and an unplaced form
          saying the mention itself is still unplaced. #17 says "appears as a
          proposed match term on the entry and is otherwise unplaced", which
          is two statements about two different things;
        - the model could not place it, but some entry's match terms license
          it anyway -> **a placement**. This is what makes promotion mean
          something: the author promotes a candidate, its surface forms
          become that entry's match terms, and at the next rebuild every
          paragraph the model left unplaced under that name is placed - with
          no model, and without re-reading a single paragraph.

        A form that two entries both license is placed against **neither**.
        Part 05 §7 has this module surface ambiguity rather than resolve it,
        and the People hazard says in as many words not to merge two people
        who share a name. Picking one would be the misidentification the
        whole design is arranged to avoid; the row says ``ambiguous_terms``
        and waits for the author to make one of the terms more specific.

        Entry-reference and relation match terms are not consulted here. They
        are how a Theme *gathers* - a co-occurrence join over placements,
        which is #18's - and a Theme is never itself placed by the extractor:
        ``derive`` hands this state ``placeable_entries`` only, so a Theme's
        name licenses nothing and a placement naming one is unplaced as
        ``NO_SUCH_ENTRY``.
        """
        for anchor in sorted(readings):
            reading = readings[anchor]
            placed = self._placed.setdefault(anchor, {})
            for placement in reading.placements:
                form = normalize_form(placement.surface_form)
                if not form:
                    continue
                if placement.entry_id not in self.entries:
                    self._license_or_unplace(
                        anchor, placement.surface_form, "", NO_SUCH_ENTRY, "", placed
                    )
                    continue
                licensed_by = self.licensing[placement.entry_id].get(form)
                if licensed_by is None:
                    key = (placement.entry_id, placement.surface_form)
                    self.proposed_terms[key] = self.proposed_terms.get(key, 0) + 1
                    self._license_or_unplace(
                        anchor,
                        placement.surface_form,
                        placement.entry_id.split("/", 1)[0],
                        UNLICENSED_PLACEMENT,
                        placement.entry_id,
                        placed,
                    )
                    continue
                self._place(
                    anchor, placement.entry_id, placement.surface_form, licensed_by, placed
                )
            for form in reading.unplaced:
                self._license_or_unplace(
                    anchor,
                    form.surface_form,
                    form.subject_id,
                    UNPLACED_BY_MODEL,
                    "",
                    placed,
                )

    def _license_or_unplace(
        self,
        anchor: str,
        surface_form: str,
        subject_id: str,
        reason: str,
        entry_id: str,
        placed: dict[str, str],
    ) -> None:
        """Place a form the author's terms license, else record it unplaced."""
        form = normalize_form(surface_form)
        if not form:
            return
        owners = self.by_form.get(form, ())
        if len(owners) == 1:
            owner, term = owners[0]
            self._place(anchor, owner, surface_form, term, placed)
            return
        if len(owners) > 1:
            self.unplaced.append(
                (anchor, surface_form, subject_id, AMBIGUOUS_TERMS, "")
            )
            return
        self.unplaced.append((anchor, surface_form, subject_id, reason, entry_id))

    def _place(
        self,
        anchor: str,
        entry_id: str,
        surface_form: str,
        licensed_by: str,
        placed: dict[str, str],
    ) -> None:
        self.placements.append((anchor, entry_id, surface_form, licensed_by))
        placed[normalize_form(surface_form)] = entry_id

    # -- pass 2: candidates --------------------------------------------------

    def build_candidates(self) -> None:
        """Group unplaced forms into candidates and apply the recurrence filter.

        Grouped by ``(subject, normalized form)``. **Different forms are never
        merged**: "Bob" and "Robert" stay two candidates until the author
        promotes one and adds the other as a match term. That inflates the
        list, and the inflation is the point - merging by matching titles is
        the misidentification path ADR-0005 declined the whole `graphrag`
        library over, and it would do it here with no author in the loop.

        A form the model filed under no subject stays enumerable as an
        unplaced row but produces no candidate: a candidate has to be a
        candidate *for* something, and there is no subject to rank it under.
        """
        for anchor, surface_form, subject_id, reason, entry_id in self.unplaced:
            if not subject_id:
                continue
            form = normalize_form(surface_form)
            candidate_id = candidate_id_for(subject_id, form)
            self._form_index[(anchor, form)] = candidate_id
            candidate = self.candidates.setdefault(
                candidate_id,
                {
                    "candidate_id": candidate_id,
                    "subject_id": subject_id,
                    "label": surface_form,
                    "gloss": "",
                    "recurrence": 0,
                    "above_threshold": 0,
                },
            )
            forms = self.candidate_forms.setdefault(candidate_id, {})
            forms[surface_form] = forms.get(surface_form, 0) + 1
            self.candidate_paragraphs.setdefault(candidate_id, set()).add(anchor)

        for candidate_id, candidate in self.candidates.items():
            recurrence = len(self.candidate_paragraphs[candidate_id])
            candidate["recurrence"] = recurrence
            candidate["above_threshold"] = 1 if recurrence >= self.threshold else 0
            candidate["label"] = _most_common(self.candidate_forms[candidate_id])

    # -- pass 3: relations ---------------------------------------------------

    def read_relations(self, readings: dict[str, ParagraphExtraction]) -> None:
        """Resolve each relation's ends to a placed entry or a candidate.

        Nodes on both sides, because a relation between two things the author
        has not promoted yet is exactly as real as one between two entries -
        and on a fresh archive it is the only kind there is.
        """
        seen = set()
        for anchor in sorted(readings):
            for relation in readings[anchor].relations:
                verb = _WHITESPACE.sub(" ", relation.verb).strip()
                if not verb:
                    continue
                from_ref = self._resolve(anchor, relation.from_ref)
                to_ref = self._resolve(anchor, relation.to_ref)
                if from_ref is None or to_ref is None or from_ref == to_ref:
                    continue
                row = (anchor, from_ref, verb, to_ref)
                if row in seen:
                    continue
                seen.add(row)
                self.relations.append(row)

    def _resolve(self, anchor: str, ref: str) -> str | None:
        """One relation end, as an entry id or a ``CAND:`` ref.

        The model gives entry references, but a reference it proposed may not
        have survived licensing - so an end is resolved against what actually
        landed in this paragraph, then against the candidate the same form
        rolled into, and is otherwise dropped. An end that resolves to
        nothing means the relation has nowhere to hang.
        """
        placed = self._placed.get(anchor, {})
        if ref in placed.values():
            return ref
        form = normalize_form(ref)
        if form in placed:
            return placed[form]
        candidate_id = self._form_index.get((anchor, form))
        if candidate_id is not None:
            return f"{CANDIDATE_REF_PREFIX}{candidate_id}"
        # The model named an entry that exists but that this paragraph's
        # placement did not license - its own surface form is what rolled
        # into a candidate, so look that up too.
        if ref in self.entries:
            name = normalize_form(implicit_name_term(ref))
            candidate_id = self._form_index.get((anchor, name))
            if candidate_id is not None:
                return f"{CANDIDATE_REF_PREFIX}{candidate_id}"
        return None

    # -- pass 4: glosses -----------------------------------------------------

    def build_glosses(self) -> None:
        """Label every candidate from rows the extraction already wrote.

        ADR-0005 build shape 2: no per-entity descriptions. GraphRAG has the
        model describe every entity in every chunk and merges the
        descriptions; we do not, because that is new model output about a
        thing nobody has promoted, and because prose about an entry has a
        designed producer already (the research memo, part 12). What makes a
        candidate legible instead is a **derived gloss** - its surface forms
        and its most frequent relations - computed here from rows that exist.
        """
        by_node = _relations_by_node(self.relations)
        for candidate_id, candidate in self.candidates.items():
            ref = f"{CANDIDATE_REF_PREFIX}{candidate_id}"
            candidate["gloss"] = self.gloss(
                self.candidate_forms[candidate_id], by_node.get(ref, {})
            )

    def gloss(self, forms: dict[str, int], relations: dict[tuple[str, str], int]) -> str:
        """Surface forms, then most frequent relations. The same rule labels a
        cluster, which is why it is one function with two callers."""
        top_forms = [
            form
            for form, _ in sorted(forms.items(), key=lambda item: (-item[1], item[0]))
        ][:GLOSS_FORMS]
        top_relations = sorted(
            relations.items(), key=lambda item: (-item[1], item[0])
        )[:GLOSS_RELATIONS]
        parts = [", ".join(top_forms)] if top_forms else []
        parts += [
            f"{verb} -> {self.label_for(other)} ({count})"
            for (verb, other), count in top_relations
        ]
        return " · ".join(part for part in parts if part)

    def label_for(self, ref: str) -> str:
        """A ref rendered for a reader.

        An entry keeps its reference - ``SUB-people/bob``, not ``bob`` -
        because a cluster label is what the author reads before promoting it,
        and #74 renders the same string. A slug alone would be ambiguous
        across subjects and would not resolve through ``read(ref)``; a
        candidate has no reference to give, so it gives its label.
        """
        if ref.startswith(CANDIDATE_REF_PREFIX):
            candidate = self.candidates.get(ref[len(CANDIDATE_REF_PREFIX) :])
            return candidate["label"] if candidate else ref
        return ref

    # -- pass 5: clusters ----------------------------------------------------

    def build_clusters(self) -> str:
        """Cluster by co-occurrence, and record what came back.

        **A cluster's members are placed entries and candidates together.**
        This reads past #17's literal wording and it is forced: on a fresh
        archive nothing is promoted, so entries alone co-occur nowhere and
        "clusters are proposed under Themes and Arcs" fails on every archive's
        first run. It is also what ADR-0005 decision 1 means - entities *are*
        entries, and a candidate is precisely an un-promoted one - and the
        summary half exists for part 11 §29's patterns nobody has thought to
        ask about, which live in the things nobody has promoted.

        Admission: every placed entry regardless of recurrence, because the
        author promoting it is the evidence that it matters; plus candidates
        above the recurrence filter, because recurrence is the only evidence
        the rest have. One knob, doing the job it already does.
        """
        paragraphs_by_node: dict[str, set[str]] = {}
        for anchor, entry_id, _, _ in self.placements:
            paragraphs_by_node.setdefault(entry_id, set()).add(anchor)
        for candidate_id, candidate in self.candidates.items():
            if candidate["above_threshold"]:
                ref = f"{CANDIDATE_REF_PREFIX}{candidate_id}"
                paragraphs_by_node[ref] = set(self.candidate_paragraphs[candidate_id])

        nodes = sorted(paragraphs_by_node)
        if not nodes:
            return clustering.BACKEND_UNAVAILABLE

        links = []
        for i, left in enumerate(nodes):
            for right in nodes[i + 1 :]:
                shared = paragraphs_by_node[left] & paragraphs_by_node[right]
                if shared:
                    links.append(CoOccurrence(left, right, len(shared)))

        try:
            assignments, backend = clustering.cluster(nodes, links)
        except ClusteringUnavailable:
            # The core is installable without the `graph` extra, and an
            # extraction with candidates but no clusters is diminished rather
            # than broken.
            return clustering.BACKEND_UNAVAILABLE

        by_members = {
            assignment.members: clustering.cluster_id(
                assignment.level, assignment.members
            )
            for assignment in assignments
        }
        relations_by_node = _relations_by_node(self.relations)
        for assignment in assignments:
            cluster_id = by_members[assignment.members]
            parent_id = (
                by_members.get(assignment.parent_members, "")
                if assignment.parent_members
                else ""
            )
            anchors = sorted(
                set().union(*(paragraphs_by_node[node] for node in assignment.members))
            )
            # Direction is kept. A relation reads one way - Bob pressures the
            # author, not the reverse - so normalizing the ends into sorted
            # order to dedupe them would silently reverse half of them, and
            # the label would then say the opposite of what the paragraph did.
            weighted: dict[tuple[str, str, str], int] = {}
            for node in assignment.members:
                for (verb, other), count in relations_by_node.get(node, {}).items():
                    if other in assignment.members:
                        key = (node, verb, other)
                        weighted[key] = weighted.get(key, 0) + count
            self.clusters.append(
                {
                    "cluster_id": cluster_id,
                    "level": assignment.level,
                    "parent_id": parent_id,
                    "label": self._cluster_label(assignment.members, weighted),
                    "membership_hash": cluster_summary_memo_key(
                        anchors, member_kind="anchors"
                    ),
                    "anchors": anchors,
                }
            )
            self.cluster_members += [
                (cluster_id, node) for node in assignment.members
            ]
            self.cluster_paragraphs += [(cluster_id, anchor) for anchor in anchors]
            self.cluster_relations += [
                (cluster_id, from_ref, verb, to_ref, count)
                for (from_ref, verb, to_ref), count in sorted(weighted.items())
            ]
        return backend

    def _cluster_label(
        self, members: Sequence[str], relations: dict[tuple[str, str, str], int]
    ) -> str:
        """A cluster named by the entries and relations that define it."""
        forms = {self.label_for(member): 1 for member in members}
        folded = {
            (verb, to_ref): count
            for (from_ref, verb, to_ref), count in relations.items()
        }
        return self.gloss(forms, folded)

    def per_subject_counts(self) -> dict[str, tuple[int, int]]:
        """Raw and above-threshold candidate counts, per subject."""
        counts: dict[str, list[int]] = {}
        for candidate in self.candidates.values():
            row = counts.setdefault(candidate["subject_id"], [0, 0])
            row[0] += 1
            row[1] += candidate["above_threshold"]
        return {subject: (raw, kept) for subject, (raw, kept) in sorted(counts.items())}

    # -- writing -------------------------------------------------------------

    def write(self, con: sqlite3.Connection, threshold: int, backend: str) -> None:
        con.executemany(
            "INSERT OR IGNORE INTO placements "
            "(anchor, entry_id, surface_form, licensed_by) VALUES (?, ?, ?, ?)",
            self.placements,
        )
        con.executemany(
            "INSERT OR IGNORE INTO unplaced_forms "
            "(anchor, surface_form, subject_id, reason, proposed_entry_id) "
            "VALUES (?, ?, ?, ?, ?)",
            self.unplaced,
        )
        con.executemany(
            "INSERT OR IGNORE INTO relations (anchor, from_ref, verb, to_ref) "
            "VALUES (?, ?, ?, ?)",
            self.relations,
        )
        con.executemany(
            "INSERT OR REPLACE INTO candidates "
            "(candidate_id, subject_id, label, gloss, recurrence, above_threshold) "
            "VALUES (:candidate_id, :subject_id, :label, :gloss, :recurrence, "
            ":above_threshold)",
            list(self.candidates.values()),
        )
        con.executemany(
            "INSERT OR REPLACE INTO candidate_forms "
            "(candidate_id, surface_form, occurrences) VALUES (?, ?, ?)",
            [
                (candidate_id, form, count)
                for candidate_id, forms in self.candidate_forms.items()
                for form, count in sorted(forms.items())
            ],
        )
        con.executemany(
            "INSERT OR IGNORE INTO candidate_paragraphs (candidate_id, anchor) "
            "VALUES (?, ?)",
            [
                (candidate_id, anchor)
                for candidate_id, anchors in self.candidate_paragraphs.items()
                for anchor in sorted(anchors)
            ],
        )
        con.executemany(
            "INSERT OR REPLACE INTO proposed_match_terms "
            "(entry_id, term, term_kind, occurrences) VALUES (?, ?, ?, ?)",
            [
                (entry_id, term, _term_kind(term), count)
                for (entry_id, term), count in sorted(self.proposed_terms.items())
            ],
        )
        con.executemany(
            "INSERT OR REPLACE INTO clusters "
            "(cluster_id, level, parent_id, label, membership_hash, summary_key) "
            "VALUES (:cluster_id, :level, :parent_id, :label, :membership_hash, '')",
            self.clusters,
        )
        con.executemany(
            "INSERT OR IGNORE INTO cluster_members (cluster_id, member_ref) "
            "VALUES (?, ?)",
            self.cluster_members,
        )
        con.executemany(
            "INSERT OR IGNORE INTO cluster_paragraphs (cluster_id, anchor) "
            "VALUES (?, ?)",
            self.cluster_paragraphs,
        )
        con.executemany(
            "INSERT OR IGNORE INTO cluster_relations "
            "(cluster_id, from_ref, verb, to_ref, weight) VALUES (?, ?, ?, ?, ?)",
            self.cluster_relations,
        )
        con.executemany(
            "INSERT OR REPLACE INTO extraction_meta (key, value) VALUES (?, ?)",
            [
                ("recurrence_threshold", str(threshold)),
                ("clustering_backend", backend),
                ("extraction_prompt_hash", _h(EXTRACTION_PROMPT)),
                ("summary_prompt_hash", _h(CLUSTER_SUMMARY_PROMPT)),
                ("derived_at", _now()),
            ],
        )


def _licensing_terms(entry: Entry) -> dict[str, str]:
    """An entry's word-kind match terms plus its implicit name, normalized,
    each mapped back to the term that licensed it."""
    # Local, not at module scope, for the same reason `rebuild` keeps its
    # `implicit_name_term` import local: `memoria.scope` imports this
    # module, so the reverse import must stay local to avoid a cycle.
    from memoria.scope import match_terms_for

    match_terms = match_terms_for(entry.id, entry)
    terms = {normalize_form(match_terms[0]): ""}
    for term in match_terms[1:]:
        normalized = normalize_form(term)
        if normalized:
            # Overwrites rather than `setdefault`: when a declared term and
            # the implicit name normalize the same, `licensed_by` should name
            # the term the author actually wrote, so the row shows their work
            # rather than a bare `''` meaning "the subject default".
            terms[normalized] = term
    return terms


def _term_kind(term: str) -> str:
    try:
        return classify_match_term(term)
    except SubjectError:
        return "word"


def _most_common(counts: dict[str, int]) -> str:
    """The most frequent key, ties broken lexically.

    The tie-break is not cosmetic: a candidate's label becomes an entry's slug
    on promotion, so a label that depended on dictionary order would make
    promotion non-reproducible.
    """
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _relations_by_node(
    relations: Sequence[tuple[str, str, str, str]],
) -> dict[str, dict[tuple[str, str], int]]:
    """Relations indexed by the node they touch, counting (verb, other end)."""
    by_node: dict[str, dict[tuple[str, str], int]] = {}
    for _, from_ref, verb, to_ref in relations:
        outgoing = by_node.setdefault(from_ref, {})
        outgoing[(verb, to_ref)] = outgoing.get((verb, to_ref), 0) + 1
    return by_node


# --- promotion ----------------------------------------------------------------


@dataclass(frozen=True)
class Promotion:
    """One candidate or cluster that became an entry."""

    entry_id: str
    path: str
    match_terms: tuple[str, ...]
    seeded_from: str
    # Match terms are the author's (CONTEXT.md), so a seed that was cut to
    # ``MAX_SEEDED_MATCH_TERMS`` says how many it left behind rather than
    # letting the author believe the entry carries everything the extraction
    # proposed.
    dropped: int = 0


def promote_candidate(
    repository: Repository,
    candidate_id: str,
    actor: Actor,
    *,
    entry_slug: str | None = None,
) -> Promotion:
    """Turn one candidate into an entry, seeded with the match terms the
    extraction proposed for it.

    The entry materializes with an **empty body**: ADR-0005 build shape 2
    keeps machine prose out of an entry, and part 06 §8.4's auto-promote says
    "an entry with an empty overlay". What it gets instead is its surface
    forms as match terms, which is what makes the gathered set appear the
    instant the entry does.
    """
    con = connect(repository)
    try:
        row = con.execute(
            "SELECT subject_id, label FROM candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ExtractionError(f"no such candidate: {candidate_id}")
        subject_id, label = row
        forms = [
            form
            for form, in con.execute(
                "SELECT surface_form FROM candidate_forms WHERE candidate_id = ? "
                "ORDER BY occurrences DESC, surface_form",
                (candidate_id,),
            )
        ]
    finally:
        con.close()
    return _materialize(
        repository,
        subject_id,
        entry_slug or entry_slug_for(label),
        forms[:MAX_SEEDED_MATCH_TERMS],
        actor,
        seeded_from=candidate_id,
        dropped=max(0, len(forms) - MAX_SEEDED_MATCH_TERMS),
    )


def _would_seed(
    members: Sequence[str],
    relations: Sequence[tuple[str, str, str]],
    candidate_labels: Mapping[str, str] = {},
) -> tuple[str, ...]:
    """The full, ordered match-term list ``promote_cluster`` would seed an
    entry with from this cluster's members and relations - relation terms
    split around the member terms, deduplicated, in the same order
    ``promote_cluster`` writes them in. Returned untruncated, in seed order,
    so a caller that needs the cap (``promote_cluster``, to report how many
    it dropped; ``_route_for``, to know what would actually be seeded today)
    slices ``[:MAX_SEEDED_MATCH_TERMS]`` itself.

    The one ordering implementation both ``promote_cluster`` and
    ``_route_for`` share (docs/tool-surface.md) - if they drift, a cluster's
    promotion and its own routing test can disagree about what it seeds.
    """
    member_terms: list[str] = []
    for node in members:
        if node.startswith(CANDIDATE_REF_PREFIX):
            word = candidate_labels.get(node)
            if word:
                member_terms.append(word)
        else:
            member_terms.append(node)
    relation_terms = [
        f"{from_ref} -> {verb} -> {to_ref}"
        for from_ref, verb, to_ref in relations
        if not from_ref.startswith(CANDIDATE_REF_PREFIX)
        and not to_ref.startswith(CANDIDATE_REF_PREFIX)
    ]
    # The cap holds room for relations. Members alone would fill it on any
    # cluster of MAX_SEEDED_MATCH_TERMS members and more, and a Theme seeded
    # with no relation at all is not what AC 8 promises; so the strongest
    # relations take up to half, members follow, and the rest of the
    # relations fill whatever is left.
    half = MAX_SEEDED_MATCH_TERMS // 2
    return tuple(
        _deduplicate(relation_terms[:half] + member_terms + relation_terms[half:])
    )


def promote_cluster(
    repository: Repository,
    cluster_id: str,
    actor: Actor,
    *,
    subject_id: str = "SUB-themes",
    entry_slug: str | None = None,
) -> Promotion:
    """Turn one cluster into a Theme or an Arc, seeded with the entries and
    relations that defined it.

    Three shapes of match term come out of a cluster, and which one a member
    gets is forced rather than chosen:

    - a member that is a **promoted entry** seeds an entry reference;
    - a defining relation whose **both** ends are promoted entries seeds
      ``SUB-a/b -> verb -> SUB-c/d``. A relation touching a candidate cannot
      be seeded at all, because ``classify_match_term`` refuses a relation
      whose ends are not entry references - so the format decides this, not
      us;
    - a member that is still a **candidate** seeds its label as a plain word,
      the only shape left. It degrades well: the Theme gathers on the word
      until the author promotes that candidate and swaps the word for a
      reference.

    The promoted entry does not point back at the cluster. Cluster identity
    does not survive re-clustering and match terms do (ADR-0005 decision 6),
    so pointing at one would be a durable reference to a transient row.
    """
    con = connect(repository)
    try:
        row = con.execute(
            "SELECT label FROM clusters WHERE cluster_id = ?", (cluster_id,)
        ).fetchone()
        if row is None:
            raise ExtractionError(f"no such cluster: {cluster_id}")
        label = row[0]
        nodes = [
            node
            for node, in con.execute(
                "SELECT member_ref FROM cluster_members WHERE cluster_id = ? "
                "ORDER BY member_ref",
                (cluster_id,),
            )
        ]
        relations = con.execute(
            "SELECT from_ref, verb, to_ref FROM cluster_relations "
            "WHERE cluster_id = ? ORDER BY weight DESC, from_ref, verb, to_ref",
            (cluster_id,),
        ).fetchall()
        candidate_labels = {
            f"{CANDIDATE_REF_PREFIX}{candidate_id}": candidate_label
            for candidate_id, candidate_label in con.execute(
                "SELECT candidate_id, label FROM candidates"
            )
        }
    finally:
        con.close()

    terms = list(_would_seed(nodes, relations, candidate_labels))
    seeded = terms[:MAX_SEEDED_MATCH_TERMS]
    slug = entry_slug or entry_slug_for(label or cluster_id)
    return _materialize(
        repository,
        subject_id,
        slug,
        seeded,
        actor,
        seeded_from=cluster_id,
        dropped=len(terms) - len(seeded),
    )


def _materialize(
    repository: Repository,
    subject_id: str,
    slug: str,
    match_terms: Sequence[str],
    actor: Actor,
    *,
    seeded_from: str,
    dropped: int = 0,
) -> Promotion:
    """Write one entry file through the durable write path, and commit it."""
    entry_id = f"{subject_id}/{slug}"
    # An ``entry_slug`` reaches promotion straight from the author's tool
    # call, so it bypasses ``entry_slug_for`` - and a subject_id does the
    # same on a cluster promotion. Neither may write an id ``parse_entry``
    # will refuse to read back (#119): the archive must not accept a write it
    # cannot serve. ``classify_match_term`` applies the one
    # ``SUB-<subject>/<entry>`` rule the read side enforces, rather than a
    # second copy of it here; it strips before matching, so a slug that is
    # only padded is caught alongside it.
    try:
        kind = classify_match_term(entry_id)
    except SubjectError:
        kind = None
    if kind != "entry" or entry_id.strip() != entry_id:
        raise ExtractionError(
            f"cannot promote to {entry_id!r}: an entry id must be of the "
            "form SUB-<subject>/<entry-slug>, with lowercase slugs. Promote "
            "under a slug of that shape, or leave the slug unset and let the "
            "label decide it."
        )
    relative_path = f"subjects/{subject_id[len('SUB-'):]}/{slug}.md"
    content = entry_to_markdown(
        Entry(id=entry_id, match_terms=list(match_terms), body="")
    )
    result = create(repository, relative_path, content, actor)
    if isinstance(result, Rejected):
        raise ExtractionError(
            f"cannot promote to {entry_id}: {relative_path} already exists. "
            "Rename the existing entry or promote under an explicit slug - "
            "nothing is renumbered automatically, because a promotion that "
            "silently picked a different name would not be repeatable."
        )
    return Promotion(
        entry_id=entry_id,
        path=relative_path,
        match_terms=tuple(match_terms),
        seeded_from=seeded_from,
        dropped=dropped,
    )


def _deduplicate(terms: Iterable[str]) -> list[str]:
    seen = set()
    ordered = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered


def auto_promote(repository: Repository, actor: Actor) -> list[Promotion]:
    """Promote above-threshold candidates under every subject that declares
    ``auto-promote: yes``.

    Part 06 §8.4's "nothing promotes itself" became "nothing promotes itself
    unless its subject says so" (ADR-0005 decision 5). Themes and Arcs ship
    off, because a wrong entry there sits in Tier 2 and in the audit until
    somebody notices.

    A candidate whose slug already resolves to an existing entry is skipped
    rather than failing the pass, so running the extraction twice creates
    nothing new.
    """
    auto = {
        subject.id
        for subject in load_all_subjects(repository)
        if subject.auto_promote
    }
    if not auto:
        return []
    con = connect(repository)
    try:
        rows = con.execute(
            "SELECT candidate_id, subject_id, label FROM candidates "
            "WHERE above_threshold = 1 ORDER BY recurrence DESC, candidate_id"
        ).fetchall()
    finally:
        con.close()

    existing = set(load_all_entries(repository))
    promotions = []
    for candidate_id, subject_id, label in rows:
        if subject_id not in auto:
            continue
        try:
            slug = entry_slug_for(label)
        except SubjectError:
            continue
        if f"{subject_id}/{slug}" in existing:
            continue
        try:
            promotions.append(
                promote_candidate(repository, candidate_id, actor, entry_slug=slug)
            )
        except (ExtractionError, WriteError):
            # One unpromotable candidate - a slug collision with a file the
            # author put there by hand - must not stop the rest of the pass.
            continue
        existing.add(f"{subject_id}/{slug}")
    return promotions


# --- what the pass serves and takes back --------------------------------------


@dataclass(frozen=True)
class PendingParagraph:
    """One paragraph the pass has not read under the current prompts."""

    anchor: str
    text: str
    memo_key: str


@dataclass(frozen=True)
class Brief:
    """The briefing for one pass: the prompt, the subjects, the entries.

    Held by value and cheap to re-fetch, which is what makes resuming trivial
    - a session that was compacted or ran out of capacity asks for this again
    and is exactly where it was.
    """

    extraction_prompt: str
    subjects: tuple[Subject, ...]
    entry_names: tuple[tuple[str, str], ...]
    subjects_digest: str
    pending: int


@dataclass(frozen=True)
class PendingSummary:
    """One cluster still needing a summary.

    Exactly one of ``member_anchors`` and ``child_summaries`` is populated. A
    leaf is written from its paragraphs; a parent from its children's
    summaries and never from the paragraphs underneath them, which is
    enforced here by simply not serving them.
    """

    cluster_id: str
    level: int
    label: str
    memo_key: str
    member_anchors: tuple[str, ...] = ()
    child_summaries: tuple[str, ...] = ()


def brief(repository: Repository) -> Brief:
    """Everything one pass needs to start, or to resume."""
    subjects = load_all_subjects(repository)
    entries = load_all_entries(repository)
    digest = subject_prompts_digest(subjects)
    return Brief(
        extraction_prompt=EXTRACTION_PROMPT,
        subjects=tuple(subjects),
        entry_names=tuple(
            (entry_id, implicit_name_term(entry_id))
            for entry_id in sorted(placeable_entries(entries))
        ),
        subjects_digest=digest,
        pending=len(pending_paragraphs(repository)),
    )


def pending_paragraphs(
    repository: Repository, *, limit: int | None = None
) -> list[PendingParagraph]:
    """Paragraphs with no memo row under the current prompts.

    This is the whole of the pass's state. There is no cursor and no open
    pass to close: "what is left to do" is a query over what is absent, so an
    interrupted run resumes by asking again and a finished one comes back
    empty.

    A re-run after ingesting one record therefore reads exactly one
    paragraph, and a subject-prompt edit moves the digest and so returns the
    whole corpus - the price part 06 §8.1 already names.
    """
    digest = subject_prompts_digest(load_all_subjects(repository))
    paragraphs = _paragraph_texts(repository)
    con = connect(repository)
    try:
        cached = {
            row[0] for row in con.execute("SELECT key FROM memo WHERE kind = 'paragraph'")
        }
    finally:
        con.close()
    pending = []
    for anchor in sorted(paragraphs):
        key = paragraph_memo_key(paragraphs[anchor], digest)
        if key in cached:
            continue
        pending.append(
            PendingParagraph(anchor=anchor, text=paragraphs[anchor], memo_key=key)
        )
        if limit is not None and len(pending) >= limit:
            break
    return pending


@dataclass(frozen=True)
class RecordOutcome:
    """One batch's per-element result.

    Per element rather than per call, because the failure atom and the call
    atom are different sizes here: one tool call per paragraph would spend an
    envelope on every paragraph in the archive, and a batch that dies on one
    bad element throws away every good one beside it.
    """

    accepted: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]


def record_batch(
    repository: Repository, results: Sequence[tuple[str, ParagraphExtraction]]
) -> RecordOutcome:
    """Validate and cache a batch of readings, one outcome per element.

    The corpus text and the subject digest are read **once** for the whole
    batch. Doing it per paragraph would re-read every record file in the
    archive for every paragraph in the batch, which is quadratic in exactly
    the dimension that grows.
    """
    texts = _paragraph_texts(repository)
    subjects = load_all_subjects(repository)
    entries = load_all_entries(repository)
    digest = subject_prompts_digest(subjects)

    accepted, rejected = [], []
    con = connect(repository)
    try:
        for anchor, value in results:
            try:
                _validate(anchor, value, texts, entries)
            except ExtractionError as exc:
                rejected.append((anchor, str(exc)))
                continue
            con.execute(
                "INSERT OR REPLACE INTO memo "
                "(key, kind, anchor, value, written_at) "
                "VALUES (?, 'paragraph', ?, ?, ?)",
                (
                    paragraph_memo_key(texts[anchor], digest),
                    anchor,
                    value.to_json(),
                    _now(),
                ),
            )
            accepted.append(anchor)
        con.commit()
    finally:
        con.close()
    return RecordOutcome(accepted=tuple(accepted), rejected=tuple(rejected))


def record_extraction(
    repository: Repository, anchor: str, value: ParagraphExtraction
) -> None:
    """Validate and cache one paragraph's reading.

    The single-paragraph form of ``record_batch``, kept because a test and a
    caller with one paragraph should not have to build a list. It raises
    rather than returning an outcome, since with one element there is nothing
    to partially succeed.
    """
    outcome = record_batch(repository, [(anchor, value)])
    if outcome.rejected:
        raise ExtractionError(outcome.rejected[0][1])


def _validate(
    anchor: str,
    value: ParagraphExtraction,
    texts: dict[str, str],
    entries: dict[str, Entry],
) -> None:
    """Refuse a reading that must not enter the cache.

    Validation is in the core rather than in the adapter because what is
    written here survives every rebuild: a malformed reading cached is a bad
    reading that no ``memoria rebuild`` will ever clear, and an adapter is the
    wrong place to be the last line of defence for something that permanent.

    A relation whose ends are not both placed *in this paragraph* is refused
    outright rather than dropped quietly. Dropping it would hide the mistake
    the model is most likely to make - reaching across paragraphs, or into
    what it already knows - behind a silently smaller result.
    """
    if anchor not in texts:
        raise ExtractionError(
            f"{anchor} is not a paragraph of this archive - anchors come back "
            "from the batch and are passed through unchanged"
        )
    placed = set()
    for placement in value.placements:
        if placement.entry_id not in entries:
            raise ExtractionError(
                f"{anchor}: {placement.entry_id} is not a promoted entry. Place "
                "only against the entries the brief lists; anything else is an "
                "unplaced surface form."
            )
        if not placement.surface_form.strip():
            raise ExtractionError(
                f"{anchor}: a placement of {placement.entry_id} carries no "
                "surface form - the words that placed it are what becomes a "
                "proposed match term"
            )
        placed.add(placement.entry_id)
    for relation in value.relations:
        for end in (relation.from_ref, relation.to_ref):
            if end not in placed:
                raise ExtractionError(
                    f"{anchor}: relation end {end!r} is not among this "
                    "paragraph's placements. A relation links two entries "
                    "placed in this same paragraph - never one placed "
                    "elsewhere, and never an unplaced form."
                )
        if not relation.verb.strip():
            raise ExtractionError(f"{anchor}: a relation carries no verb")


def _summary_keys(
    clusters: Sequence[tuple], summaries: dict[str, str]
) -> tuple[dict[str, str | None], dict[str, list[str]]]:
    """Each cluster's summary memo key, and the child index used to build it.

    A leaf's key is its membership hash - the paragraphs it holds. A parent's
    is computed over its **children's summary keys**, which is what makes
    "written from its children's summaries" a property of the key rather than
    a request in a prompt: the key cannot be computed until every child has a
    summary, and a child whose summary changes moves every ancestor's key.

    A parent whose children are not all summarized yet has a key of ``None``:
    not an error, just not offerable yet.
    """
    children: dict[str, list[str]] = {}
    for cluster_id, _, parent_id, _, _ in clusters:
        if parent_id:
            children.setdefault(parent_id, []).append(cluster_id)

    keys: dict[str, str | None] = {}
    # Deepest level first, so a parent is only reached once its children have
    # keys of their own.
    for cluster_id, _, _, _, membership_hash in sorted(
        clusters, key=lambda row: (-row[1], row[0])
    ):
        kids = sorted(children.get(cluster_id, []))
        if not kids:
            keys[cluster_id] = membership_hash
            continue
        child_keys = [keys.get(kid) for kid in kids]
        if any(key is None or key not in summaries for key in child_keys):
            keys[cluster_id] = None
            continue
        keys[cluster_id] = cluster_summary_memo_key(
            [key for key in child_keys if key], member_kind="summaries"
        )
    return keys, children


def pending_cluster_summaries(repository: Repository) -> list[PendingSummary]:
    """Clusters with no summary for their current membership, leaves first.

    **A parent is not offered until every child has a summary**, because a
    parent is written from its children's summaries and its memo key is
    computed from them. That one ordering rule is what makes "a parent's
    summary comes from its children, never from raw text" structural rather
    than something the prompt asks for nicely - and it is also what makes a
    stopped pass resume correctly: the order is total, so where it stopped is
    where it starts.
    """
    con = connect(repository)
    try:
        clusters = con.execute(
            "SELECT cluster_id, level, parent_id, label, membership_hash FROM clusters"
        ).fetchall()
        anchors: dict[str, list[str]] = {}
        for cluster_id, anchor in con.execute(
            "SELECT cluster_id, anchor FROM cluster_paragraphs ORDER BY anchor"
        ):
            anchors.setdefault(cluster_id, []).append(anchor)
        summaries = _memo_values(con, "cluster_summary")
    finally:
        con.close()

    keys, children = _summary_keys(clusters, summaries)
    pending = []
    for cluster_id, level, _, label, _ in sorted(
        clusters, key=lambda row: (-row[1], row[0])
    ):
        key = keys.get(cluster_id)
        if key is None or key in summaries:
            continue
        kids = sorted(children.get(cluster_id, []))
        if kids:
            pending.append(
                PendingSummary(
                    cluster_id=cluster_id,
                    level=level,
                    label=label,
                    memo_key=key,
                    child_summaries=tuple(
                        summaries[keys[kid]] for kid in kids if keys.get(kid)
                    ),
                )
            )
        else:
            pending.append(
                PendingSummary(
                    cluster_id=cluster_id,
                    level=level,
                    label=label,
                    memo_key=key,
                    member_anchors=tuple(anchors.get(cluster_id, [])),
                )
            )
    return pending


def cluster_summary(repository: Repository, cluster_id: str) -> str | None:
    """The ``[inferred]`` text held for one cluster, or ``None``.

    What ``search_global(summarize=True)`` serves (#74). **Never generated on
    the call**: no adapter can reach a model, so a cluster with no summary
    says so rather than producing one.
    """
    con = connect(repository)
    try:
        clusters = con.execute(
            "SELECT cluster_id, level, parent_id, label, membership_hash FROM clusters"
        ).fetchall()
        summaries = _memo_values(con, "cluster_summary")
    finally:
        con.close()
    keys, _ = _summary_keys(clusters, summaries)
    key = keys.get(cluster_id)
    return summaries.get(key) if key else None


def record_summary(
    repository: Repository, cluster_id: str, membership_hash: str, text: str
) -> None:
    """Cache one cluster's summary, guarded by the hash it was served under.

    The echoed hash is not ceremony. Between the moment a summary task is
    served and the moment it comes back, a rebuild may have re-clustered and
    that cluster's membership may be different - in which case the text
    describes paragraphs it is about to be filed against, and nobody would
    ever find out. Refusing the mismatch is the only point at which that is
    detectable.
    """
    pending = {
        summary.cluster_id: summary for summary in pending_cluster_summaries(repository)
    }
    summary = pending.get(cluster_id)
    if summary is None:
        raise ExtractionError(
            f"{cluster_id} is not waiting for a summary - it either has one "
            "already, does not exist, or is a parent whose children are not "
            "summarized yet"
        )
    if summary.memo_key != membership_hash:
        raise ExtractionError(
            f"{cluster_id} has been re-clustered since this summary was "
            "started: it now holds different members. Fetch the next summary "
            "task again and write from what it serves."
        )
    record_cluster_summary(repository, membership_hash, text)


@dataclass(frozen=True)
class Status:
    """Where the pass stands. Read-only, and safe outside a pass."""

    paragraphs: int
    extracted: int
    pending: int
    candidates_raw: int
    candidates_above_threshold: int
    per_subject: dict[str, tuple[int, int]]
    unplaced_forms: int
    proposed_match_terms: int
    clusters_by_level: dict[int, int]
    summaries_done: int
    summaries_pending: int
    recurrence_threshold: int
    clustering_backend: str
    derived: bool


def status(repository: Repository) -> Status:
    """What an author is shown before being asked whether to start.

    This is where "nothing that needs a model runs unasked" (part 08 §12.1)
    actually bites: the tools are registered in every session, so the thing
    standing between a session and a full-corpus model pass is the author
    seeing these numbers and saying go.
    """
    pending = pending_paragraphs(repository)
    paragraphs = len(_paragraph_texts(repository))
    con = connect(repository)
    try:
        meta = {
            key: value for key, value in con.execute("SELECT key, value FROM extraction_meta")
        }
        candidates = con.execute(
            "SELECT subject_id, COUNT(*), SUM(above_threshold) FROM candidates "
            "GROUP BY subject_id ORDER BY subject_id"
        ).fetchall()
        unplaced = con.execute("SELECT COUNT(*) FROM unplaced_forms").fetchone()[0]
        proposed = con.execute("SELECT COUNT(*) FROM proposed_match_terms").fetchone()[0]
        levels = dict(
            con.execute(
                "SELECT level, COUNT(*) FROM clusters GROUP BY level ORDER BY level"
            ).fetchall()
        )
        done = con.execute(
            "SELECT COUNT(*) FROM memo WHERE kind = 'cluster_summary'"
        ).fetchone()[0]
    finally:
        con.close()
    per_subject = {
        subject_id: (raw, kept or 0) for subject_id, raw, kept in candidates
    }
    return Status(
        paragraphs=paragraphs,
        extracted=paragraphs - len(pending),
        pending=len(pending),
        candidates_raw=sum(raw for raw, _ in per_subject.values()),
        candidates_above_threshold=sum(kept for _, kept in per_subject.values()),
        per_subject=per_subject,
        unplaced_forms=unplaced,
        proposed_match_terms=proposed,
        clusters_by_level=levels,
        summaries_done=done,
        summaries_pending=len(pending_cluster_summaries(repository)),
        recurrence_threshold=int(
            meta.get("recurrence_threshold", RECURRENCE_THRESHOLD_DEFAULT)
        ),
        clustering_backend=meta.get("clustering_backend", ""),
        derived="derived_at" in meta,
    )



# --- enumeration -------------------------------------------------------------
#
# #17: "candidates the filter rejects stay enumerable, and so do unplaced
# surface forms" - both miss rates are countable the day ground truth exists.
# `status` counts; these list, and they are the only route by which an author
# reaches a candidate or cluster id to promote.


@dataclass(frozen=True)
class Candidate:
    """One candidate as the recurrence filter left it, kept either way."""

    candidate_id: str
    subject_id: str
    label: str
    gloss: str
    recurrence: int
    above_threshold: bool


@dataclass(frozen=True)
class UnplacedForm:
    """A mention the pass could not tie to an entry."""

    anchor: str
    surface_form: str
    subject_id: str
    reason: str
    proposed_entry_id: str


@dataclass(frozen=True)
class ClusterMembers:
    """One cluster opened up: its members, its paragraphs, its children."""

    cluster_id: str
    level: int
    parent_id: str
    label: str
    members: tuple[str, ...]
    anchors: tuple[str, ...]
    children: tuple[str, ...]
    summary: str | None


def candidates(
    repository: Repository,
    *,
    subject_id: str | None = None,
    above_threshold: bool | None = None,
    limit: int | None = None,
) -> list[Candidate]:
    """Candidates ranked by recurrence - all of them, or one subject's, or
    only those on one side of the filter."""
    clauses, params = [], []
    if subject_id is not None:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if above_threshold is not None:
        clauses.append("above_threshold = ?")
        params.append(int(above_threshold))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    tail = "" if limit is None else f" LIMIT {int(limit)}"
    con = connect(repository)
    try:
        rows = con.execute(
            "SELECT candidate_id, subject_id, label, gloss, recurrence, "
            f"above_threshold FROM candidates {where} "
            f"ORDER BY recurrence DESC, subject_id, label{tail}",
            params,
        ).fetchall()
    finally:
        con.close()
    return [
        Candidate(candidate_id, subject_id, label, gloss, recurrence, bool(above))
        for candidate_id, subject_id, label, gloss, recurrence, above in rows
    ]


def unplaced_forms(
    repository: Repository, *, limit: int | None = None
) -> list[UnplacedForm]:
    """Every mention left unplaced, by anchor."""
    tail = "" if limit is None else f" LIMIT {int(limit)}"
    con = connect(repository)
    try:
        rows = con.execute(
            "SELECT anchor, surface_form, subject_id, reason, proposed_entry_id "
            f"FROM unplaced_forms ORDER BY anchor, surface_form{tail}"
        ).fetchall()
    finally:
        con.close()
    return [UnplacedForm(*row) for row in rows]


def cluster_members(repository: Repository, cluster_id: str) -> ClusterMembers:
    """One cluster's members, member paragraphs and child clusters (AC 12).

    The summary comes back too when one exists for this membership, so an
    author inspecting a cluster before promoting it sees everything the pass
    holds about it in one place.
    """
    con = connect(repository)
    try:
        row = con.execute(
            "SELECT level, parent_id, label, membership_hash FROM clusters "
            "WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()
        if row is None:
            raise ExtractionError(f"no such cluster: {cluster_id}")
        level, parent_id, label, membership_hash = row
        members = [
            ref
            for ref, in con.execute(
                "SELECT member_ref FROM cluster_members WHERE cluster_id = ? "
                "ORDER BY member_ref",
                (cluster_id,),
            )
        ]
        anchors = [
            anchor
            for anchor, in con.execute(
                "SELECT anchor FROM cluster_paragraphs WHERE cluster_id = ? "
                "ORDER BY anchor",
                (cluster_id,),
            )
        ]
        children = [
            child
            for child, in con.execute(
                "SELECT cluster_id FROM clusters WHERE parent_id = ? "
                "ORDER BY cluster_id",
                (cluster_id,),
            )
        ]
    finally:
        con.close()
    return ClusterMembers(
        cluster_id=cluster_id,
        level=level,
        parent_id=parent_id,
        label=label,
        members=tuple(members),
        anchors=tuple(anchors),
        children=tuple(children),
        summary=cluster_summary(repository, cluster_id),
    )


# --- search_global (#74) ------------------------------------------------------


@dataclass(frozen=True)
class ClusterGroup:
    """One matched cluster, as ``search_global`` groups paragraph references.

    ``entry_id`` names the Theme or Arc this cluster routes to, when one has
    been promoted from it (ADR-0005 decision 6, part 06 §8.4: "a cluster that
    has been promoted routes to the entry, not to its stale label"). A
    promoted entry never points back at its origin cluster - cluster identity
    does not survive re-clustering - so this is read the only way it can be:
    forward, off the entry's own current match terms, checked for exact
    equality against what this cluster would seed today (``_route_for``). It
    is ``None`` before any promotion, after one whose match terms have since
    been edited past what this cluster still defines, and for every other
    cluster the entry's terms do not exactly equal - an ancestor of the real
    origin cluster included, since a coarser level's members are always a
    superset of a finer one's.

    ``summary`` is the cluster's memoized ``[inferred]`` text - never
    generated here, only served (ADR-0005 build shape 3) - and is ``None``
    both when the call did not ask for one and when nothing has been written
    for this membership yet; ``GlobalSearchResult.summarize`` is how a caller
    tells the two apart.
    """

    cluster_id: str
    level: int
    label: str
    entry_id: str | None
    results: tuple[SearchResult, ...]
    summary: str | None


@dataclass(frozen=True)
class GlobalSearchResult:
    """What one ``search_global`` call returns: cluster groups, and the
    §33-style scope line naming what ran (part 11 §25, §33.1)."""

    groups: tuple[ClusterGroup, ...]
    level: int
    scope: str
    summarize: bool
    summary_served: bool


_YEAR_RE = re.compile(r"(1[6-9]\d{2}|20\d{2})")


def _year_range(dates: Iterable[str]) -> str | None:
    """A best-effort ``YYYY`` or ``YYYY``-``YYYY`` span for the scope line.

    ``event_date`` is a verbatim frontmatter string with no sortable value
    (docs/tool-surface.md's ``SearchFilters`` note) - this is a display aid
    for the scope line, never a filter, so a plain four-digit year is pulled
    out of whatever string is there and a date carrying none contributes
    nothing rather than breaking the scan.
    """
    years = []
    for date in dates:
        if not date:
            continue
        match = _YEAR_RE.search(date)
        if match:
            years.append(int(match.group(0)))
    if not years:
        return None
    lo, hi = min(years), max(years)
    return str(lo) if lo == hi else f"{lo}–{hi}"


def _scope_line(paragraphs: int, clusters: int, level: int, year_range: str | None) -> str:
    """The part 11 §25 scope line - *"clustered 1,842 paragraphs across
    2009-2014; 3 clusters matched"* - always naming the level actually used
    (#74's acceptance criteria), since a query with no ``level`` filter
    resolves one silently and §33's discipline is that assembly reports what
    it resolved rather than leaving it implicit."""
    across = f" across {year_range}" if year_range else ""
    paragraph_word = "paragraph" if paragraphs == 1 else "paragraphs"
    cluster_word = "cluster" if clusters == 1 else "clusters"
    return (
        f"clustered {paragraphs} {paragraph_word}{across}; {clusters} "
        f"{cluster_word} matched at level {level}"
    )


def _theme_routes(repository: Repository) -> dict[frozenset[str], str]:
    """Every Theme's or Arc's entry- and relation-shaped match terms, as a
    set, mapped back to its entry id - the routing table ``search_global``
    checks a matched cluster's own defining terms against (see
    ``_route_for``). Not every entry here was promoted from a cluster - a
    Theme may be hand-authored (part 06 §8.4) - so this table alone
    over-matches; ``_route_for`` is what tells the two apart.

    Sorted by entry id first and inserted with ``setdefault``, so two entries
    that happen to carry the identical term set - a real collision, not
    ambiguity ``_route_for`` resolves - route to the earliest one
    deterministically rather than whichever was seen last."""
    routes: dict[frozenset[str], str] = {}
    for entry_id, entry in sorted(load_all_entries(repository).items()):
        if entry_id.split("/", 1)[0] not in CO_OCCURRENCE_SUBJECTS:
            continue
        terms = frozenset(
            term for term in entry.match_terms if classify_match_term(term) != "word"
        )
        if terms:
            routes.setdefault(terms, entry_id)
    return routes


def _route_for(
    members: Sequence[str],
    relations: Sequence[tuple[str, str, str]],
    routes: dict[frozenset[str], str],
    candidate_labels: Mapping[str, str] = {},
) -> str | None:
    """The entry this cluster (``members``, ``relations``) routes to, if a
    Theme's or Arc's own seeded set still defines it - see
    ``_theme_routes``.

    **Exact, not bounded.** One-way containment (an entry's terms are a
    subset of the cluster's) is not enough: it also matches a hand-authored
    Theme whose terms merely happen to overlap an unrelated cluster's larger
    membership, and it matches every ancestor of the cluster an entry was
    actually promoted from, since a coarser level's members are always a
    superset of a finer one's (``clustering.py``'s nesting). A bounded slack
    on top of containment cannot fix this without also re-opening it: any
    cardinality allowance forgiven for "the cap could have crowded a member
    out" is indistinguishable from "the cluster is just bigger than the
    entry" once enough candidate-shaped members are present, and real
    extractions carry many (review round 3).

    So this does not approximate what ``promote_cluster`` might have seeded
    - it computes what ``promote_cluster`` **would seed today**, via the
    same ``_would_seed`` ordering, capped at ``MAX_SEEDED_MATCH_TERMS`` and
    stripped of the plain-word terms a candidate-shaped member contributes
    (``_theme_routes`` never puts those in ``routes`` either, since a Theme's
    own match terms are filtered the same way), and requires the cluster's
    would-seed set to equal a route's seed **exactly**. This forgives
    candidate crowding and the cap by construction - both are already baked
    into ``_would_seed``'s truncation - while still failing a hand-authored
    overlap or a coarser ancestor no matter how many candidates either
    carries, because neither one's would-seed set is actually equal to the
    route it merely resembles.

    This still cannot tell a hand-authored Theme from a promoted one when
    the two are indistinguishable by construction - an entry whose terms
    exactly equal a real cluster's own definition, promoted or not. ADR-0005
    decision 6 rules out a durable pointer that would settle it; this is the
    residual and it is bounded, not open-ended.
    """
    would_seed = frozenset(
        term
        for term in _would_seed(members, relations, candidate_labels)[
            :MAX_SEEDED_MATCH_TERMS
        ]
        if classify_match_term(term) != "word"
    )
    if not would_seed:
        return None
    return routes.get(would_seed)


def search_global(
    repository: Repository,
    query: str | None,
    filters: SearchFilters | None = None,
    *,
    summarize: bool = False,
) -> GlobalSearchResult:
    """The global tool over the extraction's clusters (part 11 §25, #74).

    Returns paragraph references **grouped by cluster** rather than the flat,
    ranked list ``search`` (#12) gives - GraphRAG's global-search map step,
    handed to the session agent, which reduces it itself through part 11
    §28's loop (ADR-0005 "Build shape" 4). Every reference is a
    ``SearchResult`` carrying no text, exactly like ``search``: it feeds
    straight into ``read(ref)``, with no reconstruction and no evidence read
    out of derived state.

    ``query`` is optional (ADR-0005 "Build shape" 4). Given, it full-text
    searches the archive like ``search`` and groups the hits by the cluster
    each matched paragraph belongs to. ``None`` returns every paragraph of
    every matched cluster instead - the whole-corpus map step, most useful
    with ``filters.level`` set and ``summarize=True``.

    **One level per call.** A paragraph nests inside a cluster at every level
    of the hierarchy at once (ADR-0005 build shape 1), so grouping across all
    of them at once would show the same paragraph again under each of its
    ancestors. ``filters.level`` picks which grain to group at; left unset,
    the finest level the corpus currently has is used, and the level actually
    used is always named in the scope line - never left for a caller to
    infer (§33.1).

    The other six ``SearchFilters`` narrow the matched paragraphs exactly as
    they narrow ``search`` (#12); they have nothing to say about a cluster
    that query mode does not already start from a paragraph.

    **A promoted cluster routes to its entry, not to its stale label**
    (``ClusterGroup``, ADR-0005 decision 6, part 06 §8.4).

    **Summaries are served, never generated** (ADR-0005 build shape 3). With
    ``summarize=True`` each group carries the memoized ``[inferred]`` text for
    its cluster, or ``None`` when nothing has been written for it yet -
    ``summarize=False`` leaves ``ClusterGroup.summary`` at ``None``
    unconditionally, so a summary is never handed to a caller who did not ask.
    Nothing here calls a model; ``cluster_summary`` only reads the memo cache.

    A missing index - every fresh clone - returns no groups rather than
    raising or creating the database file, matching ``search`` and ``gather``.
    """
    db_path = repository.root / INDEX_RELATIVE_PATH
    if not db_path.exists():
        scope = _scope_line(0, 0, 0, None)
        return GlobalSearchResult(
            groups=(), level=0, scope=scope, summarize=summarize, summary_served=False
        )

    con = connect(repository)
    try:
        available_levels = [
            row[0] for row in con.execute("SELECT DISTINCT level FROM clusters")
        ]
        requested_level = filters.level if filters is not None else None
        level = (
            requested_level
            if requested_level is not None
            else (max(available_levels) if available_levels else 0)
        )

        predicate, predicate_params = filter_predicate(filters)
        if query:
            sql = (
                "SELECT records.src_id, records.anchor, records.source_type, "
                "paragraphs.event_date, cluster_paragraphs.cluster_id "
                "FROM records "
                "JOIN paragraphs ON paragraphs.anchor = records.anchor "
                "JOIN cluster_paragraphs ON cluster_paragraphs.anchor = records.anchor "
                "JOIN clusters ON clusters.cluster_id = cluster_paragraphs.cluster_id "
                "WHERE records MATCH ? AND clusters.level = ?"
            )
            params: list = [query, level]
        else:
            sql = (
                "SELECT paragraphs.src_id, cluster_paragraphs.anchor, "
                "paragraphs.source_type, paragraphs.event_date, "
                "cluster_paragraphs.cluster_id "
                "FROM cluster_paragraphs "
                "JOIN paragraphs ON paragraphs.anchor = cluster_paragraphs.anchor "
                "JOIN clusters ON clusters.cluster_id = cluster_paragraphs.cluster_id "
                "WHERE clusters.level = ?"
            )
            params = [level]
        if predicate:
            sql += f" AND {predicate}"
            params += predicate_params
        sql += " ORDER BY cluster_paragraphs.cluster_id, paragraphs.anchor"
        rows = con.execute(sql, params).fetchall()

        cluster_ids = sorted({row[4] for row in rows})
        labels: dict[str, str] = {}
        members: dict[str, list[str]] = {}
        relations: dict[str, list[tuple[str, str, str]]] = {}
        candidate_labels: dict[str, str] = {}
        if cluster_ids:
            placeholders = ",".join("?" for _ in cluster_ids)
            labels = dict(
                con.execute(
                    f"SELECT cluster_id, label FROM clusters "
                    f"WHERE cluster_id IN ({placeholders})",
                    cluster_ids,
                )
            )
            for cluster_id, member_ref in con.execute(
                f"SELECT cluster_id, member_ref FROM cluster_members "
                f"WHERE cluster_id IN ({placeholders})",
                cluster_ids,
            ):
                members.setdefault(cluster_id, []).append(member_ref)
            for cluster_id, from_ref, verb, to_ref in con.execute(
                f"SELECT cluster_id, from_ref, verb, to_ref FROM cluster_relations "
                f"WHERE cluster_id IN ({placeholders})",
                cluster_ids,
            ):
                relations.setdefault(cluster_id, []).append((from_ref, verb, to_ref))
            candidate_labels = {
                f"{CANDIDATE_REF_PREFIX}{candidate_id}": candidate_label
                for candidate_id, candidate_label in con.execute(
                    "SELECT candidate_id, label FROM candidates"
                )
            }
    finally:
        con.close()

    routes = _theme_routes(repository) if cluster_ids else {}
    by_cluster: dict[str, list[tuple[str, str, str, str]]] = {}
    for src_id, anchor, source_type, event_date, cluster_id in rows:
        by_cluster.setdefault(cluster_id, []).append(
            (src_id, anchor, source_type, event_date)
        )

    groups = []
    for cluster_id in cluster_ids:
        cluster_members = members.get(cluster_id, ())
        cluster_relations = relations.get(cluster_id, ())
        groups.append(
            ClusterGroup(
                cluster_id=cluster_id,
                level=level,
                label=labels.get(cluster_id, ""),
                entry_id=_route_for(
                    cluster_members, cluster_relations, routes, candidate_labels
                ),
                results=tuple(
                    SearchResult(src_id=src_id, anchor=anchor, source_type=source_type)
                    for src_id, anchor, source_type, _ in by_cluster[cluster_id]
                ),
                summary=cluster_summary(repository, cluster_id) if summarize else None,
            )
        )

    scope = _scope_line(
        paragraphs=len({row[1] for row in rows}),
        clusters=len(cluster_ids),
        level=level,
        year_range=_year_range(row[3] for row in rows),
    )
    return GlobalSearchResult(
        groups=tuple(groups),
        level=level,
        scope=scope,
        summarize=summarize,
        summary_served=summarize and any(group.summary for group in groups),
    )


@dataclass(frozen=True)
class PassReport:
    """What one author-launched pass did."""

    counts: DerivedCounts
    promotions: tuple[Promotion, ...]
    summaries_pending: int


def finish_pass(
    repository: Repository,
    actor: Actor | None = None,
    *,
    recurrence_threshold: int = RECURRENCE_THRESHOLD_DEFAULT,
) -> PassReport:
    """Close the author-launched pass: derive, auto-promote, derive again.

    The second derive is not belt and braces. Auto-promotion creates entries,
    and an entry that did not exist a moment ago licenses placements that
    were unplaced a moment ago - so without it the pass would end reporting
    candidates that are already entries and placements that have not landed.

    **This is the only place auto-promotion happens.** ``memoria rebuild``
    calls ``derive`` and nothing else: a command whose whole contract is that
    everything it touches is disposable must not be making durable, committed
    entry files as a side effect. The author launched this; nobody launched
    a rebuild.

    It does not require the summaries to be finished. A capacity limit (part
    13 §24.3) is expected to leave a complete extraction and a partial
    summary set, and whether a Theme candidate is above the recurrence filter
    has nothing to do with whether anyone has described it yet.
    """
    actor = actor or CURATOR
    if pending_paragraphs(repository, limit=1):
        raise ExtractionError(
            "the corpus is not fully extracted - finish the paragraph loop "
            "before closing the pass, or nothing promotes off a partial "
            "reading of the archive"
        )
    derive(repository, recurrence_threshold=recurrence_threshold)
    promotions = auto_promote(repository, actor)
    counts = derive(repository, recurrence_threshold=recurrence_threshold)
    return PassReport(
        counts=counts,
        promotions=tuple(promotions),
        summaries_pending=len(pending_cluster_summaries(repository)),
    )


# --- the shape the tools take ------------------------------------------------
#
# The MCP tool arguments, kept here rather than in the adapter, because they
# are the contract the *core* validates. Splitting them out would put the
# shape in one module and the only thing that checks it in another.


@dataclass
class RecordedRelation:
    """A relation as the model sends it back.

    ``from_ref`` and ``to_ref`` are entry references, checked against the same
    paragraph's placements. The type is doing enforcement here: there is no
    second anchor field, so a relation spanning two paragraphs cannot be
    expressed at all, and an end that was not placed is refused rather than
    silently kept.
    """

    from_ref: str
    verb: str
    to_ref: str


@dataclass
class RecordedPlacement:
    """A placement as the model sends it back."""

    entry_id: str
    surface_form: str


@dataclass
class RecordedForm:
    """An unplaced surface form as the model sends it back."""

    surface_form: str
    subject_id: str = ""


@dataclass
class RecordedParagraph:
    """One paragraph's reading, as one element of a recorded batch."""

    anchor: str
    placements: list[RecordedPlacement] = field(default_factory=list)
    unplaced: list[RecordedForm] = field(default_factory=list)
    relations: list[RecordedRelation] = field(default_factory=list)

    def to_extraction(self) -> ParagraphExtraction:
        return ParagraphExtraction(
            placements=tuple(
                ProposedPlacement(p.entry_id, p.surface_form) for p in self.placements
            ),
            unplaced=tuple(
                ProposedForm(u.surface_form, u.subject_id) for u in self.unplaced
            ),
            relations=tuple(
                ProposedRelation(r.from_ref, r.verb, r.to_ref) for r in self.relations
            ),
        )


# Who an auto-promotion commits as. The Curator is the machine half (part 06
# §41), so the commit carries no `change-id:` trailer and is told apart from
# the author's by exactly that (ADR-0008).
CURATOR = Actor(name="Memoria", email="curator@memoria.local", human=False)
