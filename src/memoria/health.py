"""The §47 health report (#44, docs/plan/15-validation-and-health.md §47).

"Memoria should periodically be able to report" eleven things about the
manuscript and archive - not an audit, and not an approval queue: §47's own
words are "It reports what has gone stale; it does not form an opinion about
the prose." **Everything in it is computed without a model** - hash
comparisons, git facts and mechanical validation - which is exactly what
lets it run autonomously where the audit (Invariant 8) may not.

``compute_health_report`` is stateless and read-only: it writes nothing
durable and is recomputed fresh on every call, the same discipline
``memoria.audit.compute_staleness_map`` (#37) already keeps for the same
reason - "known across the whole manuscript at all times" means nothing here
can itself go stale.

**The staleness map does the heavy lifting, once** (#37, reused rather than
forked - the batch note on #44 is explicit that #40 and #44 share it). Three
of §47's eleven bullets are one fact read three ways: "paragraphs, sections
and chapters that are not current, and why", "themes with substantial new
evidence but no recent review" and "arcs whose cached judgements have gone
stale" are the *same* ``StalenessMap`` (#37), filtered to ``SUB-themes/*``
and ``SUB-arcs/*`` entry ids for the latter two - never a second scan. The
final bullet, "manuscript passages affected by changed chronology, themes,
arcs, claims or source status", is explicitly "the staleness map, not a
scan" in the plan doc's own words, so it is the same field again rather than
a twelfth thing this module computes.

**Two bullets have no mechanical source yet, and this module does not
invent one.** "Human/Curator conflicts" is the Memoria note the Curator
writes when evidence conflicts with a human-touched statement (CONTEXT.md's
"Memoria note" / "Human-touched flag") - part 08 §14.2's write path is not
built anywhere in this codebase yet. "Unsupported interpretation statements"
is, in the plan doc's own words, "the one check [in §23] that needs a
model" - the opposite of what this report is allowed to do. Both fields
below are always empty rather than backed by an invented proxy (an
``[inferred]`` regex heuristic, say) that later work would have to unwind;
the category is reported - present in the shape below - honestly empty
until its producing mechanism exists.

**Two more degrade gracefully rather than failing** when no evidence corpus
is configured (``docs/open-problems.md`` §2.4 - none is chosen yet):
"broken provenance" (``memoria.validate.validate``) and "unprocessed source
additions" (the manifest ledger against ``sources/normalized/``) both need
``repository.evidence_root``, and read ``None`` rather than an empty tuple
when it is unset - ``None`` says "not checked", an empty tuple would say
"checked, nothing wrong", and those are different claims.
"""

from __future__ import annotations

import html
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from memoria.audit import NotCurrentJudgement, StalenessMap, compute_staleness_map
from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH, load_manifest
from memoria.manuscript import book_path, list_chapters, list_sections, parse_brief
from memoria.record_extractor import QUESTIONS_FILENAME, RESEARCH_MEMOS_RELATIVE_PATH
from memoria.records import NORMALIZED_RELATIVE_PATH
from memoria.repository import Repository
from memoria.validate import validate as run_validate

# Themes and Arcs are subjects like any other (`memoria.subjects.BUILTIN_SUBJECTS`);
# their entry ids carry these prefixes, which is all filtering the staleness
# map by subject takes - no second lookup.
THEMES_SUBJECT_PREFIX = "SUB-themes/"
ARCS_SUBJECT_PREFIX = "SUB-arcs/"

# A section with no commit touching it in this many days counts as "not
# worked on recently". No value is stated anywhere in the plan docs; picked
# as a plain, documented default rather than left unconfigurable - CLI
# callers can override it (`memoria health --stale-after-days`).
STALE_SECTION_DAYS_DEFAULT = 30

# An open question (`questions.md`, part 12 §34.4's queue) older than this
# many days counts as "old" for §47's "old unresolved questions" bullet.
# Same reasoning as the section threshold above.
OLD_QUESTION_DAYS_DEFAULT = 30

# The trailing separator is `\n\n` between blocks, but a hand-edited
# `questions.md` may end its final block at EOF with one newline or none -
# `record_question` always writes the blank line, so this only guards the
# hand-edited case rather than fixing a live bug.
_QUESTION_BLOCK_RE = re.compile(
    r"\[open\] (?P<text>.*?)\n\n— (?P<citation>SES-\S+)(?:\n\n|\n?\Z)", re.DOTALL
)
_SES_DATE_RE = re.compile(r"^SES-(\d{4})(\d{2})(\d{2})-")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- sections not worked on recently (a git fact) ----------------------------


@dataclass(frozen=True)
class SectionRecency:
    """One section, and the date of the most recent commit that touched its
    directory (brief and draft together) - ``None`` if git has no such
    commit at all, which this report treats as maximally stale rather than
    an error: an uncommitted section is the least "worked on recently" of
    any of them."""

    chapter_number: int
    section_number: int
    last_touched: str | None


def _last_touched(repository: Repository, path: Path) -> str | None:
    """The most recent commit date to touch ``path``, as ``YYYY-MM-DD`` - a
    git fact, mechanically read, never a model judgement. ``None`` covers
    every reason git has nothing to say: no repository, no commits yet, or a
    path git has never committed."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d", "--", str(path)],
            cwd=repository.root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    date = result.stdout.strip()
    return date or None


def _stale_sections(
    repository: Repository, *, stale_after_days: int, now: datetime
) -> tuple[SectionRecency, ...]:
    cutoff = (now - timedelta(days=stale_after_days)).date()
    stale = []
    for chapter in list_chapters(repository):
        for section in list_sections(repository, chapter.number):
            last = _last_touched(repository, section.dir)
            if last is None or datetime.fromisoformat(last).date() <= cutoff:
                stale.append(
                    SectionRecency(
                        chapter_number=chapter.number,
                        section_number=section.number,
                        last_touched=last,
                    )
                )
    return tuple(stale)


# --- unconfirmed briefs (§2.1's `unconfirmed` field) -------------------------


@dataclass(frozen=True)
class UnconfirmedBrief:
    """One brief still in the summarized-from-existing-prose state
    (``manuscript.Brief.unconfirmed``) - CONTEXT.md's "Unconfirmed brief":
    "assembly uses it; the audit does not check drift against it"."""

    id: str
    level: str  # "book" | "chapter" | "section"
    chapter_number: int | None
    section_number: int | None


def _unconfirmed_briefs(repository: Repository) -> tuple[UnconfirmedBrief, ...]:
    found: list[UnconfirmedBrief] = []
    book_file = book_path(repository)
    if book_file.is_file():
        brief = parse_brief(book_file.read_text(encoding="utf-8"), source=str(book_file))
        if brief.unconfirmed:
            found.append(
                UnconfirmedBrief(
                    id=brief.id, level="book", chapter_number=None, section_number=None
                )
            )
    for chapter in list_chapters(repository):
        if chapter.brief.unconfirmed:
            found.append(
                UnconfirmedBrief(
                    id=chapter.brief.id,
                    level="chapter",
                    chapter_number=chapter.number,
                    section_number=None,
                )
            )
        for section in list_sections(repository, chapter.number):
            if section.brief.unconfirmed:
                found.append(
                    UnconfirmedBrief(
                        id=section.brief.id,
                        level="section",
                        chapter_number=chapter.number,
                        section_number=section.number,
                    )
                )
    return tuple(found)


# --- old unresolved questions (`questions.md`, the queue) --------------------


@dataclass(frozen=True)
class OpenQuestion:
    """One entry from ``questions.md`` (part 12 §34.4) - always ``[open]``
    by construction (``record_extractor.record_question``), so this report's
    only job is to say how old it is, not whether it is resolved: nothing in
    this codebase marks one resolved yet."""

    text: str
    citation: str
    date: str | None  # YYYY-MM-DD, read off the citation's SES- session id


def _open_questions(repository: Repository) -> tuple[OpenQuestion, ...]:
    path = repository.root / QUESTIONS_FILENAME
    if not path.is_file():
        return ()
    text = path.read_text(encoding="utf-8")
    questions = []
    for match in _QUESTION_BLOCK_RE.finditer(text):
        citation = match.group("citation")
        date_match = _SES_DATE_RE.match(citation)
        date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else None
        questions.append(
            OpenQuestion(text=html.unescape(match.group("text")), citation=citation, date=date)
        )
    return tuple(questions)


# --- incomplete research projects (`research/memos/`) ------------------------


@dataclass(frozen=True)
class IncompleteResearchMemo:
    """A research memo (§34.1) whose own "Unresolved questions" section -
    ``record_extractor._render_research_memo``'s heading - is non-empty: the
    research it records left something open rather than a source this
    report closed the loop on."""

    id: str


def _incomplete_research_memos(repository: Repository) -> tuple[IncompleteResearchMemo, ...]:
    directory = repository.root / RESEARCH_MEMOS_RELATIVE_PATH
    if not directory.is_dir():
        return ()
    incomplete = []
    for path in sorted(directory.glob("RES-*.md")):
        if "## Unresolved questions" in path.read_text(encoding="utf-8"):
            incomplete.append(IncompleteResearchMemo(id=path.stem))
    return tuple(incomplete)


# --- broken provenance and unprocessed source additions ----------------------
# Both need an evidence corpus to compare against; both read `None` rather
# than fail, or report a false "nothing wrong", when none is configured.


def _broken_provenance(repository: Repository) -> tuple[str, ...] | None:
    if repository.evidence_root is None:
        return None
    return tuple(run_validate(repository.evidence_root, repository.root))


def _unprocessed_source_additions(repository: Repository) -> tuple[str, ...] | None:
    if repository.evidence_root is None:
        return None
    manifest_path = repository.evidence_root / DEFAULT_MANIFEST_RELATIVE_PATH
    entries = load_manifest(manifest_path)
    normalized_dir = repository.root / NORMALIZED_RELATIVE_PATH
    normalized_ids = (
        {path.stem for path in normalized_dir.glob("*.md")} if normalized_dir.is_dir() else set()
    )
    return tuple(sorted(entry.id for entry in entries if not entry.deleted and entry.id not in normalized_ids))


# --- the report ----------------------------------------------------------------


@dataclass(frozen=True)
class HealthReport:
    """§47's health report, as of ``generated_at``. Model-free by
    construction - see the module docstring - and safe to run unasked
    (contrast ``memoria.audit``'s audit, on demand only): nothing here
    approves or dismisses anything, and computing it writes no durable
    state."""

    generated_at: str
    stale_after_days: int
    old_question_days: int

    stale_sections: tuple[SectionRecency, ...]
    not_current: StalenessMap
    unconfirmed_briefs: tuple[UnconfirmedBrief, ...]
    open_questions: tuple[OpenQuestion, ...]
    themes_not_current: tuple[NotCurrentJudgement, ...]
    arcs_not_current: tuple[NotCurrentJudgement, ...]
    human_curator_conflicts: tuple[str, ...]
    unsupported_statements: tuple[str, ...]
    broken_provenance: tuple[str, ...] | None
    unprocessed_source_additions: tuple[str, ...] | None
    incomplete_research_memos: tuple[IncompleteResearchMemo, ...]

    def old_questions(self) -> tuple[OpenQuestion, ...]:
        """Open questions at least ``old_question_days`` old, measured
        against ``generated_at`` rather than a fresh clock read - so the
        same report gives the same answer however long it is held. A
        question with no parseable date (never produced by
        ``record_question`` itself, only by a hand-edited ``questions.md``)
        counts as old: surfaced, not silently dropped."""
        cutoff = (datetime.fromisoformat(self.generated_at) - timedelta(days=self.old_question_days)).date()
        return tuple(
            q for q in self.open_questions if q.date is None or datetime.fromisoformat(q.date).date() <= cutoff
        )


def compute_health_report(
    repository: Repository,
    *,
    stale_after_days: int = STALE_SECTION_DAYS_DEFAULT,
    old_question_days: int = OLD_QUESTION_DAYS_DEFAULT,
) -> HealthReport:
    """Compute §47's health report for ``repository``, fresh, as of now.

    No model call anywhere in this call graph (``tests/test_health.py``
    holds both halves of that claim the way ``test_audit.py`` does for
    ``compute_staleness_map``: an AST sweep against a model-client import,
    and a run with sockets made to raise - subprocess is not blocked, since
    a git fact is one of the three inputs §47 allows). No durable write
    either: every function this calls is a read.
    """
    now = datetime.now(timezone.utc)
    staleness = compute_staleness_map(repository)
    return HealthReport(
        generated_at=now.isoformat(timespec="seconds"),
        stale_after_days=stale_after_days,
        old_question_days=old_question_days,
        stale_sections=_stale_sections(repository, stale_after_days=stale_after_days, now=now),
        not_current=staleness,
        unconfirmed_briefs=_unconfirmed_briefs(repository),
        open_questions=_open_questions(repository),
        themes_not_current=tuple(
            item for item in staleness.not_current if item.entry_id.startswith(THEMES_SUBJECT_PREFIX)
        ),
        arcs_not_current=tuple(
            item for item in staleness.not_current if item.entry_id.startswith(ARCS_SUBJECT_PREFIX)
        ),
        # Always empty - see the module docstring's "Two bullets have no
        # mechanical source yet" paragraph.
        human_curator_conflicts=(),
        unsupported_statements=(),
        broken_provenance=_broken_provenance(repository),
        unprocessed_source_additions=_unprocessed_source_additions(repository),
        incomplete_research_memos=_incomplete_research_memos(repository),
    )
