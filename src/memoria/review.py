"""The Review surface: the results of an audit the author asked for, and the
one act it offers that writes - applying a proposed rewrite (#43, part 19
§19.3 as amended by §19.11, part 10 §19.3).

**Review is a results view, not an inbox.** Nothing arrives here unbidden:
``review_section`` is a plain read over the audit verdicts a session already
recorded through ``audit_record`` (#40) - decoded back from the memo table
on every call, current keys only (``memoria.audit.located_findings_in_scope``)
- and this module can neither run an audit nor record one.
``tests/test_audit.py``'s sweep already forbids any module but ``audit.py``
and the MCP server from calling the recording functions, and this module
imports none of them. A section nobody has audited has no findings and
says so through ``verdicts_current`` being zero; the surface tells that
apart from an audit that found nothing.

**Findings are disagreement sets** (part 06 §8.10). Each carries its members,
the resolutions its shape admits - read off the set by
``Finding.available_resolutions``, never stored - its confidence, the
subject that raised it, and an optional proposed rewrite. No verdict label
and no severity: part 19 §19.3's ``CONTRADICTED``/``4 high`` are example
content, and what this serves is what the audit actually recorded.

**Applying a rewrite goes through the one write path.** ``apply_rewrite`` is
the author's explicit act - part 10 §19.3 names ``Apply`` among the
interface actions that constitute authorization - and it is scoped to one
paragraph: the draft is spliced at that paragraph's own byte span and
every other byte is left exactly as it was. The write is ``memoria.write``'s
(ADR-0003): a staleness token minted when the draft was served, presented
back, and a draft changed underneath rejected whole. It commits as the
author (``memoria.write.repository_actor`` at the adapter), the same class
of thing as an edit made in Obsidian. The durable authorization record and
``trace()`` are #42's; this is the seam they attach to.

**No path here edits a brief.** The only file this module can write is a
section's ``draft.md``; it names no brief filename and imports no brief
writer, which ``tests/test_manuscript.py``'s guards hold structurally. The
"passage + brief" shape's resolutions still say "open a conversation about
the brief", and that is all the surface offers for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from memoria import write
from memoria.audit import (
    DRAFT_FILENAME,
    LocatedFinding,
    located_findings_in_scope,
    manuscript_paragraphs,
    paragraph_spans,
    pending_for_target,
)
from memoria.manuscript import draft_relative_path, list_chapters, resolve_section
from memoria.repository import Repository
from memoria.scope import resolve_scope
from memoria.write import Actor, Rejected, WriteResult

# Part 10 §21's tiers, highest first - the one ordering a finding list has
# (part 06 §8.10: "confidence ... Not severity, and not kind of problem").
CONFIDENCE_ORDER = ("high", "moderate", "low")


class ReviewError(Exception):
    """A review could not be composed or a rewrite could not be attempted -
    an unknown section, a section with no draft, a paragraph index the
    draft does not have."""


@dataclass(frozen=True)
class Review:
    """What the Review surface renders for one section.

    ``findings`` is ordered by confidence, per §21's tiers.
    ``verdicts_current`` and ``verdicts_not_current`` count the section's
    (paragraph, entry) audit verdicts on each side of the staleness map -
    zero current with a non-zero not-current is a section no audit has
    been run over (or one whose every judgement has since gone stale),
    which is a different thing from an audit that found nothing.
    ``token`` is ``memoria.write.serve``'s staleness token for the draft as
    read this call, for ``apply_rewrite`` to present back; ``None`` when the
    section has no draft to rewrite.
    """

    section_id: str
    chapter_number: int
    section_number: int
    findings: tuple[LocatedFinding, ...]
    verdicts_current: int
    verdicts_not_current: int
    token: str | None


def _chapter_number_of(repository: Repository, section_dir) -> int:
    for chapter in list_chapters(repository):
        if section_dir.parent.parent == chapter.dir:
            return chapter.number
    raise ReviewError(f"no chapter holds {section_dir}")


def review_section(repository: Repository, section_id: str) -> Review:
    """The Review for one ``SEC-`` id, at this call - see the module
    docstring. Raises ``memoria.manuscript.ManuscriptError`` for an id no
    section carries."""
    section = resolve_section(repository, section_id)
    chapter_number = _chapter_number_of(repository, section.dir)
    draft_path = section.dir / DRAFT_FILENAME

    findings = sorted(
        located_findings_in_scope(
            repository, chapter_number=chapter_number, section_number=section.number
        ),
        key=lambda item: CONFIDENCE_ORDER.index(item.finding.confidence)
        if item.finding.confidence in CONFIDENCE_ORDER
        else len(CONFIDENCE_ORDER),
    )

    paragraph_count = sum(
        1
        for paragraph in manuscript_paragraphs(repository)
        if paragraph.chapter_number == chapter_number
        and paragraph.section_number == section.number
    )
    entry_count = len(resolve_scope(repository, section.brief).entry_ids)
    not_current = sum(
        1
        for item in pending_for_target(
            repository, chapter_number=chapter_number, section_number=section.number
        )
        if item.kind == "audit_verdict"
    )

    token = None
    if draft_path.is_file():
        token = write.serve(repository, draft_relative_path(repository, section)).token

    return Review(
        section_id=section.brief.id,
        chapter_number=chapter_number,
        section_number=section.number,
        findings=tuple(findings),
        verdicts_current=paragraph_count * entry_count - not_current,
        verdicts_not_current=not_current,
        token=token,
    )


def apply_rewrite(
    repository: Repository,
    section_id: str,
    paragraph_index: int,
    token: str,
    text: str,
    actor: Actor,
) -> WriteResult:
    """Replace one paragraph of a section's draft with ``text`` - the
    author applying a proposed rewrite from Review.

    Scoped to the one paragraph: the draft is spliced at that paragraph's
    span and nothing else moves. Through ``memoria.write.write`` with the
    ``token`` the draft was served under, so a draft edited underneath -
    in Obsidian, or by another audit's apply - is ``Rejected`` whole rather
    than merged (ADR-0003). ``text`` is written stripped: a paragraph is
    what sits between blank lines, and surrounding whitespace would either
    vanish on the next read or fuse two paragraphs.
    """
    section = resolve_section(repository, section_id)
    relative = draft_relative_path(repository, section)
    if not (repository.root / relative).is_file():
        raise ReviewError(f"{section_id} has no draft to rewrite")
    served = write.serve(repository, relative)
    if served.token != token:
        return Rejected(outcome="stale", path=relative)
    spans = paragraph_spans(served.text)
    if not 1 <= paragraph_index <= len(spans):
        raise ReviewError(
            f"{section_id} has {len(spans)} paragraph(s); there is no paragraph "
            f"{paragraph_index}"
        )
    replacement = text.strip()
    if not replacement:
        raise ReviewError("a rewrite cannot be empty")
    start, end = spans[paragraph_index - 1]
    content = served.text[:start] + replacement + served.text[end:]
    return write.write(repository, relative, token, content, actor)
