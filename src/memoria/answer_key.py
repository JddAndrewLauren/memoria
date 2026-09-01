"""The answer key: which held book passage each cross-referenced journal
passage became (issue #9).

A cross-reference (issue #8) carries a trustworthy journal side - the 1906
editors' own footnote, resolved to a ``SRC-`` ID and paragraph anchor - and
an untrustworthy target side: a page number in an edition the corpus does
not hold. ``memoria.editions`` turns that page number into a position in
the held text. This module joins the two and decides which links are good
enough to score against.

**The admission rule is two independent editions agreeing.** Almost every
footnote cites the same passage twice - once by Manuscript Edition page,
once by Riverside (``[_Week_, p. 319; Riv. 395.]``). Those are different
printings, separately scanned, separately OCR'd, separately anchored. When
both land on the same place in the held text, the target is corroborated by
evidence that shares no failure mode with itself. When they do not, the row
is kept in the file with a status saying so and is not scored.

**What this module may not do.** It may not narrow within a cited page by
comparing the journal passage against candidate book paragraphs. That
operation - similarity between evidence and manuscript prose - is precisely
what the benchmark measures, and using it here would make the key agree with
the machinery under test by construction. The target is therefore a
page-sized span of paragraphs, because a page is what the editors cited.

**A citation wider than two pages is not a target.** A handful of footnotes
cite a stretch of book rather than a passage - one runs to 65 pages - and
the span such a citation covers is not something retrieval can be asked to
match. Those rows are kept and not scored. See ``docs/answer-key-protocol.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from memoria.cross_references import CrossReference, HELD_WORKS
from memoria.editions import (
    REFERENCE_EDITIONS,
    PageMap,
    WorkText,
    build_page_map,
)
from memoria.normalize import NormalizedRecord

ANSWER_KEY_RELATIVE_PATH = "benchmark/answer-key.yaml"

# How far the two editions may disagree, in Riverside pages, once the
# systematic drift between the two page-number series is taken out.
#
# Chosen after seeing the spread, and said plainly because it matters how
# much weight the number can carry. Of the 349 links where both editions
# anchor, the median residual is 0.42 pages, 29 are past 1.0 and three past
# 1.5; the worst admitted is 1.78 and the single rejection sits at 2.16. So
# the threshold is not separating two populations - it is a line drawn
# across a 0.38-page gap in one tail. What the tolerance genuinely shows is
# that the apparatus is self-consistent almost everywhere; what it does not
# show is that the one row past it is wrong and the row at 1.78 is right.
_MAX_RESIDUAL_PAGES = 2.0

# The most Manuscript pages one citation may cover and still name a passage.
# A passage lives on a page, and sometimes crosses onto the next. "[See
# _Week_, pp. 356-420; Riv. 442-518.]" is the editors recording that a
# stretch of journal became a stretch of book - true, and not a
# passage-level link. It matters because the target span is what issue #14
# hands retrieval as the *probe*: a 65-page citation is not a noisy probe
# but a different task, and scoring it would quietly corrupt the number the
# harness exists to produce. Wider citations keep their row with a status
# saying so and are not scored.
_MAX_CITED_PAGES = 2

# The first ~160 characters of the journal paragraph, so the key can be
# read without resolving the SRC- ID against anything.
_EXCERPT_CHARS = 160


def _work_citation_re(work: str) -> re.Pattern:
    """Match one work's page pair inside a footnote body.

    Scoped to the named work because one footnote can cite two - ``[_Week_,
    p. 183; Riv. 227. _The Service_, p. 13.]`` - and the whole body is
    stored verbatim on both rows (docs/cross-reference-schema.md). The
    underscores are optional for the same reason ``_WORK_RE`` makes them
    optional: a handful of citations lost their italic markup in
    transcription.
    """
    return re.compile(
        r"(?<![A-Za-z])_?" + re.escape(work) + r"_?,?\s*"
        r"pp?\.\s*(?P<primary>\d+(?:\s*[,\-]\s*\d+)*)"
        # The Riverside page is usually introduced by a semicolon and
        # sometimes parenthesized instead - "p. 265 (Riv. 372, 373)" - which
        # cost 12 links on the first pass. Only punctuation and whitespace
        # may sit between, so the pattern cannot skip past an intervening
        # work's citation to borrow its Riverside number.
        r"\s*[;,]?\s*\(?\s*Riv\.\s*(?P<riverside>\d+(?:\s*[,\-]\s*\d+)*)"
    )


def _pages(group: str) -> list[int]:
    return [int(n) for n in re.findall(r"\d+", group)]


@dataclass
class AnswerKeyRow:
    link_id: str
    status: str
    source_record_id: str
    source_anchor: str
    source_excerpt: str
    citation: str
    target_work: str
    manuscript_pages: list[int] = field(default_factory=list)
    riverside_pages: list[int] = field(default_factory=list)
    target_record_ids: list[str] = field(default_factory=list)
    target_anchors: list[str] = field(default_factory=list)
    target_locator: str = ""
    target_text: str = ""
    residual_pages: float | None = None
    manuscript_votes: int | None = None
    note: str = ""


@dataclass
class WorkSummary:
    work: str
    links: int
    resolved: int
    editions_disagree: int
    no_page_pair: int
    unanchored: int
    not_passage_level: int
    drift_intercept: float | None
    drift_slope: float | None
    pairs_fitted: int
    worst_residual: float | None
    median_span_paragraphs: float | None
    mean_span_paragraphs: float | None
    max_span_paragraphs: int | None


def _fit_drift(pairs: list[tuple[int, int]]) -> tuple[float, float] | None:
    """Least-squares fit of ``diff = a + b * manuscript_page``.

    The two page-number series drift apart slowly - about three Riverside
    pages over four hundred - so a fixed tolerance would be far too loose at
    one end of a volume and too tight at the other. Fitting the drift is
    what makes a two-page tolerance mean the same thing on page 12 and page
    412. The fit has two parameters over a hundred-odd points, and both are
    written into the key so the correction is inspectable rather than
    implicit.
    """
    if len(pairs) < 10:
        return None
    n = len(pairs)
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    sxx = sum(x * x for x, _ in pairs)
    sxy = sum(x * y for x, y in pairs)
    denominator = n * sxx - sx * sx
    if denominator == 0:
        return None
    slope = (n * sxy - sx * sy) / denominator
    return (sy - slope * sx) / n, slope


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def build_answer_key(
    evidence_root: Path,
    cross_references: list[CrossReference],
    records: list[NormalizedRecord],
) -> tuple[list[AnswerKeyRow], list[WorkSummary], list[dict]]:
    """Resolve every held-work cross-reference to a target passage.

    Returns the rows, a per-work summary, and the page-map statistics -
    all three get written into the key, because coverage that is not in the
    artifact is coverage nobody checks.
    """
    by_id = {record.id: record for record in records}
    rows: list[AnswerKeyRow] = []
    summaries: list[WorkSummary] = []
    map_stats: list[dict] = []

    for work in sorted(HELD_WORKS):
        work_records = [r for r in records if r.work == work]
        work_text = WorkText.from_records(work_records)
        maps: dict[str, PageMap] = {}
        for edition in REFERENCE_EDITIONS:
            if edition["work"] != work:
                continue
            page_map = build_page_map(evidence_root, edition, work_text)
            maps[edition["series"]] = page_map
            map_stats.append(
                {
                    "identifier": page_map.identifier,
                    "work": work,
                    "series": page_map.series,
                    "label": edition["label"],
                    "printed_page_offset": page_map.printed_page_offset,
                    "printed_page_offset_evidence": (
                        f"{page_map.printed_page_offset_agreeing} of "
                        f"{page_map.printed_page_offset_voting} pages state "
                        "their own number in a running head"
                    ),
                    "pages_anchored": len(page_map.offsets),
                    "pages_unanchored": len(page_map.unanchored),
                    "pages_dropped_out_of_order": len(page_map.non_monotonic),
                }
            )
        manuscript, riverside = maps["manuscript"], maps["riverside"]

        work_links = [c for c in cross_references if c.target_work == work]
        pattern = _work_citation_re(work)
        parsed: list[tuple[CrossReference, list[int], list[int]]] = []
        for link in work_links:
            match = pattern.search(link.citation)
            if match is None:
                parsed.append((link, [], []))
            else:
                parsed.append(
                    (
                        link,
                        _pages(match.group("primary")),
                        _pages(match.group("riverside")),
                    )
                )

        # The drift is a property of the two page-number series, so it is
        # fitted once per work over the distinct page pairs - not once per
        # link, which would weight a pair by how many journal passages
        # happen to cite it.
        distinct: dict[tuple[int, int], int] = {}
        for _, primary, riv in parsed:
            if not primary or not riv:
                continue
            if primary[0] not in manuscript.offsets:
                continue
            predicted = riverside.page_containing(manuscript.offsets[primary[0]])
            if predicted is None:
                continue
            distinct[(primary[0], riv[0])] = predicted - riv[0]
        fit = _fit_drift([(p, d) for (p, _), d in distinct.items()])

        counts = {
            "resolved": 0,
            "disagree": 0,
            "no_pair": 0,
            "unanchored": 0,
            "not_passage_level": 0,
        }
        residuals: list[float] = []
        spans: list[float] = []
        seen: dict[str, int] = {}
        for link, primary, riv in parsed:
            base = f"{link.source_anchor}/{work}"
            seen[base] = seen.get(base, 0) + 1
            link_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
            source = by_id.get(link.source_record_id)
            excerpt = ""
            if source is not None:
                number = int(link.source_anchor.rsplit("-p", 1)[1])
                if 1 <= number <= len(source.paragraphs):
                    text = " ".join(source.paragraphs[number - 1].split())
                    excerpt = text[:_EXCERPT_CHARS]
                    if len(text) > _EXCERPT_CHARS:
                        excerpt += "..."
            row = AnswerKeyRow(
                link_id=link_id,
                status="",
                source_record_id=link.source_record_id,
                source_anchor=link.source_anchor,
                source_excerpt=excerpt,
                citation=link.citation,
                target_work=work,
                manuscript_pages=primary,
                riverside_pages=riv,
            )

            if not primary or not riv:
                row.status = "no-page-pair"
                row.note = (
                    "the footnote cites no Manuscript/Riverside page pair for "
                    "this work, so there is nothing to corroborate against"
                )
                counts["no_pair"] += 1
                rows.append(row)
                continue

            cited_pages = primary[-1] - primary[0] + 1
            if cited_pages > _MAX_CITED_PAGES:
                row.status = "not-passage-level"
                row.note = (
                    f"the footnote's Manuscript pages run {primary[0]}-"
                    f"{primary[-1]}, a {cited_pages}-page stretch rather than "
                    "the page or two a passage occupies, so it names a part of "
                    "the book and not a target to score against"
                )
                counts["not_passage_level"] += 1
                rows.append(row)
                continue

            # Both ends, not just the first: the span below is grown from
            # one to the other, and an unanchored last page would otherwise
            # reach `span()` as None.
            missing = [
                page
                for page in (primary[0], primary[-1])
                if page not in manuscript.offsets
            ]
            if missing:
                row.status = "unanchored"
                row.note = (
                    f"Manuscript page {missing[0]} could not be placed in the "
                    "held text"
                )
                counts["unanchored"] += 1
                rows.append(row)
                continue

            predicted = riverside.page_containing(manuscript.offsets[primary[0]])
            if predicted is None or fit is None:
                row.status = "unanchored"
                row.note = "the Riverside page map has no counterpart to check against"
                counts["unanchored"] += 1
                rows.append(row)
                continue

            residual = (predicted - riv[0]) - (fit[0] + fit[1] * primary[0])
            row.residual_pages = round(residual, 2)
            row.manuscript_votes = manuscript.votes[primary[0]]
            if abs(residual) > _MAX_RESIDUAL_PAGES:
                row.status = "editions-disagree"
                row.note = (
                    f"Riverside page {riv[0]} sits {residual:+.1f} pages from "
                    f"where Manuscript page {primary[0]} puts it, past the "
                    f"{_MAX_RESIDUAL_PAGES:.0f}-page tolerance"
                )
                counts["disagree"] += 1
                rows.append(row)
                continue

            start = manuscript.span(primary[0])[0]
            end = manuscript.span(primary[-1])[1]
            overlapping = work_text.paragraphs_overlapping(start, end)
            row.status = "resolved"
            row.target_record_ids = sorted({s.record_id for s in overlapping})
            row.target_anchors = [
                by_id[s.record_id].anchor_id(s.paragraph_number)
                for s in overlapping
            ]
            first, last = overlapping[0], overlapping[-1]
            chapters = sorted({by_id[s.record_id].chapter for s in overlapping})
            row.target_locator = (
                f"{work} / {' + '.join(chapters)} / paragraphs "
                f"{first.paragraph_number}-{last.paragraph_number}"
                if len(overlapping) > 1
                else f"{work} / {chapters[0]} / paragraph {first.paragraph_number}"
            )
            row.target_text = "\n\n".join(
                by_id[s.record_id].paragraphs[s.paragraph_number - 1]
                for s in overlapping
            )
            residuals.append(abs(residual))
            spans.append(len(overlapping))
            counts["resolved"] += 1
            rows.append(row)

        summaries.append(
            WorkSummary(
                work=work,
                links=len(work_links),
                resolved=counts["resolved"],
                editions_disagree=counts["disagree"],
                no_page_pair=counts["no_pair"],
                unanchored=counts["unanchored"],
                not_passage_level=counts["not_passage_level"],
                drift_intercept=round(fit[0], 4) if fit else None,
                drift_slope=round(fit[1], 6) if fit else None,
                pairs_fitted=len(distinct),
                worst_residual=round(max(residuals), 2) if residuals else None,
                median_span_paragraphs=_median(spans),
                # The median alone hid a row spanning 198 paragraphs. The
                # tail is the part that would corrupt a recall number, so
                # the tail is reported too.
                mean_span_paragraphs=(
                    round(sum(spans) / len(spans), 2) if spans else None
                ),
                max_span_paragraphs=int(max(spans)) if spans else None,
            )
        )

    rows.sort(key=lambda r: (r.target_work, r.source_record_id, r.link_id))
    return rows, summaries, map_stats


def write_answer_key(
    rows: list[AnswerKeyRow],
    summaries: list[WorkSummary],
    map_stats: list[dict],
    output_path: Path,
) -> Path:
    """Write the key as YAML - committed, durable, and readable without
    Memoria software (issue #9).

    Every link gets a row, including the ones not scored: coverage that is
    not visible in the artifact is coverage nobody checks.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "protocol": "docs/answer-key-protocol.md",
        "method": "two-edition-alignment",
        "editions": map_stats,
        "summary": [
            {
                "work": s.work,
                "links": s.links,
                "resolved": s.resolved,
                "editions_disagree": s.editions_disagree,
                "no_page_pair": s.no_page_pair,
                "unanchored": s.unanchored,
                "not_passage_level": s.not_passage_level,
                "drift_intercept": s.drift_intercept,
                "drift_slope": s.drift_slope,
                "pairs_fitted": s.pairs_fitted,
                "worst_admitted_residual_pages": s.worst_residual,
                "median_span_paragraphs": s.median_span_paragraphs,
                "mean_span_paragraphs": s.mean_span_paragraphs,
                "max_span_paragraphs": s.max_span_paragraphs,
            }
            for s in summaries
        ],
        "links": [
            {
                key: value
                for key, value in {
                    "link_id": r.link_id,
                    "status": r.status,
                    "source_record_id": r.source_record_id,
                    "source_anchor": r.source_anchor,
                    "source_excerpt": r.source_excerpt,
                    "citation": r.citation,
                    "target_work": r.target_work,
                    "manuscript_pages": r.manuscript_pages or None,
                    "riverside_pages": r.riverside_pages or None,
                    "target_record_ids": r.target_record_ids or None,
                    "target_anchors": r.target_anchors or None,
                    "target_locator": r.target_locator or None,
                    "target_text": r.target_text or None,
                    "residual_pages": r.residual_pages,
                    "manuscript_votes": r.manuscript_votes,
                    "note": r.note or None,
                }.items()
                if value is not None
            }
            for r in rows
        ],
    }
    output_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=88),
        encoding="utf-8",
    )
    return output_path
