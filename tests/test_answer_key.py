"""The answer key and its two-edition admission rule (issue #9)."""

import os

import pytest
import yaml

from memoria.answer_key import (
    _work_citation_re,
    build_answer_key,
    write_answer_key,
)
from memoria.cross_references import extract_cross_references
from memoria.editions import read_reference_volume, tokenize
from memoria.editorial import extract_editorial_apparatus
from memoria.normalize import (
    normalize_journals,
    normalize_letters,
    normalize_targets,
)
from memoria.year_resolution import resolve_years

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"


class TestCitationParsing:
    def test_reads_the_ordinary_semicolon_form(self):
        match = _work_citation_re("Week").search("[_Week_, p. 319; Riv. 395.]")
        assert match.group("primary") == "319"
        assert match.group("riverside") == "395"

    def test_reads_the_parenthesized_form(self):
        # "p. 265 (Riv. 372, 373)" instead of "p. 265; Riv. 372, 373" -
        # the same citation, and 6 links were lost to it before the pattern
        # allowed the bracket.
        match = _work_citation_re("Walden").search(
            "[_Walden_, p. 265 (Riv. 372, 373), where October is the month named.]"
        )
        assert match.group("primary") == "265"
        assert match.group("riverside") == "372, 373"

    def test_reads_a_title_that_lost_its_italics(self):
        # A transcription inconsistency in the source, not a different
        # citation form (docs/cross-reference-schema.md).
        assert _work_citation_re("Week").search("[Week, p. 66; Riv. 82, 83.]")

    def test_scopes_each_work_to_its_own_pages_in_a_two_work_footnote(self):
        body = "[_Week_, p. 183; Riv. 227. _The Service_, p. 13.]"
        week = _work_citation_re("Week").search(body)
        assert (week.group("primary"), week.group("riverside")) == ("183", "227")
        # The Service has no Riverside page of its own, and must not be
        # allowed to borrow Week's by matching across the sentence break.
        assert _work_citation_re("The Service").search(body) is None

    def test_ignores_a_riverside_page_belonging_to_another_work(self):
        # Here the Riv. numbers are _Misc._'s, and Week's own pages are
        # Roman numerals with nothing to look up.
        body = "[See _Week_, pp. xx, xxi; _Misc._, Riv. 8, 9 (Emerson's Sketch).]"
        assert _work_citation_re("Week").search(body) is None

    def test_ignores_a_mention_with_no_riverside_page_at_all(self):
        body = "[_Walden_, p. 242, where he makes his age four instead of five.]"
        assert _work_citation_re("Walden").search(body) is None


@pytest.mark.skipif(
    EVIDENCE_ROOT_ENV_VAR not in os.environ,
    reason=f"{EVIDENCE_ROOT_ENV_VAR} not set; skipping real-corpus integration test",
)
class TestAgainstTheRealEvidenceCorpus:
    @pytest.fixture(scope="class")
    @staticmethod
    def built():
        # The same pipeline `memoria normalize` runs, from evidence rather
        # than from whatever happens to be on disk under sources/.
        root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        journals = normalize_journals(root)
        resolve_years(journals, root)
        editorial = extract_editorial_apparatus(root, journals)
        letters = normalize_letters(root, start_id=len(journals) + 1)
        targets = normalize_targets(
            root, start_id=len(journals) + len(letters) + 1
        )
        records = journals + letters + targets
        cross_references = extract_cross_references(editorial)
        rows, summaries, editions = build_answer_key(root, cross_references, records)
        return rows, summaries, editions, {r.id: r for r in records}

    def test_every_resolvable_cross_reference_gets_a_row(self, built):
        rows, _, _, _ = built
        # 379 of the 668 cross-references land on a held work
        # (docs/cross-reference-schema.md): 257 Week, 122 Walden. None is
        # dropped - a link that could not be resolved stays in the file
        # with a status saying why, because coverage that is not in the
        # artifact is coverage nobody checks.
        assert len(rows) == 379
        assert sum(1 for r in rows if r.target_work == "Week") == 257
        assert sum(1 for r in rows if r.target_work == "Walden") == 122

    def test_the_admitted_and_rejected_counts(self, built):
        rows, _, _, _ = built
        counts = {}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        assert counts == {
            "resolved": 365,
            "unanchored": 7,
            "no-page-pair": 6,
            "editions-disagree": 1,
        }

    def test_link_ids_are_unique(self, built):
        rows, _, _, _ = built
        # 40 journal paragraphs carry two footnote markers citing the same
        # work, so the anchor and work alone do not identify a link.
        ids = [r.link_id for r in rows]
        assert len(set(ids)) == len(ids)

    def test_the_two_editions_drift_apart_slowly_and_predictably(self, built):
        _, summaries, _, _ = built
        for summary in summaries:
            # About three Riverside pages over four hundred. Small, but far
            # too large to ignore: uncorrected it would reject most of the
            # back half of each volume.
            assert 0 < summary.drift_slope < 0.02, summary.work
            assert summary.pairs_fitted >= 100, summary.work
            # Every admitted row sits inside the tolerance by construction;
            # this asserts the tolerance is not doing all the work.
            assert summary.worst_residual <= 2.0, summary.work

    def test_a_resolved_row_quotes_the_paragraphs_it_names(self, built):
        rows, _, _, by_id = built
        for row in rows:
            if row.status != "resolved":
                continue
            quoted = []
            for anchor in row.target_anchors:
                record = by_id[anchor.rsplit("-p", 1)[0].upper()]
                quoted.append(record.paragraphs[int(anchor.rsplit("-p", 1)[1]) - 1])
            assert "\n\n".join(quoted) == row.target_text, row.link_id

    def test_a_resolved_row_points_only_at_its_own_work(self, built):
        rows, _, _, by_id = built
        for row in rows:
            if row.status != "resolved":
                continue
            for record_id in row.target_record_ids:
                assert by_id[record_id].work == row.target_work, row.link_id

    def test_a_row_lands_on_the_text_its_cited_page_actually_carries(self, built):
        # The end-to-end check, on the volume whose leaf numbering happens
        # to need no correction. J01's April 8 entry on the six-horse team
        # is footnoted "[_Walden_, p. 8; Riv. 14, 15.]", and Manuscript
        # page 8 carries "Look at the teamster on the highway".
        rows, _, _, _ = built
        row = next(r for r in rows if r.link_id == "src-000113-p1/Walden")
        assert row.status == "resolved"
        assert "six-horse team" in row.source_excerpt
        assert "teamster on the" in row.target_text
        assert row.target_locator.startswith("Walden / Economy / paragraphs")

    def test_every_resolved_row_spans_the_page_it_was_anchored_on(self, built):
        # The span is grown from the cited page's own token range out to
        # paragraph boundaries, so the page's text must lie inside it. A
        # row where it does not means the span was computed from a
        # different page than the one that was anchored.
        rows, _, _, by_id = built
        root = os.environ[EVIDENCE_ROOT_ENV_VAR]
        volumes = {
            "Week": read_reference_volume(root, "writingsofhenryd01thor"),
            "Walden": read_reference_volume(root, "writingsofhenryd02thoruoft"),
        }
        for row in rows:
            if row.status != "resolved":
                continue
            page = tokenize(volumes[row.target_work].pages[row.manuscript_pages[0]])
            span = set(tokenize(row.target_text))
            # OCR damage means not every word survives; most must.
            shared = sum(1 for token in page if token in span)
            assert shared > 0.8 * len(page), (row.link_id, shared, len(page))

    def test_the_key_round_trips_through_yaml(self, built, tmp_path):
        rows, summaries, editions, _ = built
        path = write_answer_key(rows, summaries, editions, tmp_path / "key.yaml")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert document["method"] == "two-edition-alignment"
        assert len(document["links"]) == 379
        assert len(document["editions"]) == 4
        resolved = [d for d in document["links"] if d["status"] == "resolved"]
        assert all(d["target_text"] and d["target_anchors"] for d in resolved)
        # A rejected row keeps its citation and its reason, and carries no
        # target it did not earn.
        rejected = [d for d in document["links"] if d["status"] != "resolved"]
        assert all(d["note"] and "target_text" not in d for d in rejected)
