"""The direct runs (ADR-0010): each serve/record pass driven to completion
by a scripted fake model, with nothing leaving the process.

The fake answers from what the driver actually sent it - the anchor in the
user turn, the kind of an audit task, the samples heading of a style brief
- so every test also pins what a run puts in front of the model.
"""

import json
import socket
import subprocess

import pytest

from memoria import audit, drivers, extraction as ex, style
from memoria.audit import manuscript_paragraphs
from memoria.index import build_index, gather
from memoria.ledger import event_path
from memoria.manuscript import create_chapter, create_section
from memoria.model import ModelError, ModelReply, ModelRequest, ModelUsage
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    record_path,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.subjects import Entry, entry_to_markdown, write_builtin_subjects
from memoria.write import Actor

SESSION = "SES-20260904-1200-abcdef012345"
AUTHOR = Actor(name="Local Author", email="local@memoria.test")


class FakeModel:
    """A ``ModelFn`` answering from ``handler(request)``: a dict is sent
    back as JSON, a str as text, a ``ModelReply`` as itself. Records every
    request so a test can assert what the driver put in front of it."""

    def __init__(self, handler):
        self.handler = handler
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        answer = self.handler(request)
        usage = ModelUsage(model="fake-model", input_tokens=7, output_tokens=3)
        if isinstance(answer, ModelReply):
            return answer
        if isinstance(answer, dict):
            answer = json.dumps(answer)
        return ModelReply(text=answer, stop_reason="end_turn", usage=usage)


def _refusal():
    return ModelReply(
        text="",
        stop_reason="refusal",
        usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=0),
        refusal="general_harms: no",
    )


def _truncated(text):
    return ModelReply(
        text=text, stop_reason="max_tokens", usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=3)
    )


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _record(paragraphs, record_id="SRC-000001"):
    return NormalizedRecord(
        id=record_id,
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=paragraphs,
    )


def _repo(tmp_path, paragraphs, entries=()):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    for entry in entries:
        subject_slug, slug = entry.id[len("SUB-") :].split("/", 1)
        (tmp_path / "subjects" / subject_slug / f"{slug}.md").write_text(entry_to_markdown(entry))
    record = _record(paragraphs)
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return repository


def _ledger(repository, session_id=SESSION):
    path = event_path(repository, session_id)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _model_calls(repository):
    return [event for event in _ledger(repository) if event["tool"] == "model_call"]


# --- the extraction ------------------------------------------------------------


def _reading_of(request):
    """The scripted reading: every paragraph mentions Bob, unplaced."""
    anchor = request.user.split("\n", 1)[0].removeprefix("anchor: ")
    assert request.pass_name == drivers.PASS_EXTRACTION
    assert request.schema == drivers.EXTRACTION_SCHEMA
    return {
        "placements": [],
        "unplaced": [{"surface_form": "Bob", "subject_id": "SUB-people"}],
        "relations": [],
    }


def _summary_or_reading(request):
    if request.pass_name == drivers.PASS_CLUSTER_SUMMARY:
        assert request.schema is None
        assert request.system == ex.CLUSTER_SUMMARY_PROMPT
        return "Bob, throughout."
    return _reading_of(request)


def test_the_extraction_runs_in_bounded_steps_until_done(tmp_path):
    repository = _repo(tmp_path, ["Bob and the acquisition.", "Bob again."])
    model = FakeModel(_summary_or_reading)

    first = drivers.run_extraction(repository, model, SESSION, limit=1, recurrence_threshold=1)
    assert first.phase == "paragraphs"
    assert (first.paragraphs_read, first.paragraphs_accepted, first.paragraphs_remaining) == (1, 1, 1)
    assert first.finished is False
    assert first.spend.calls == 1
    assert first.spend.model == "fake-model"

    second = drivers.run_extraction(repository, model, SESSION, limit=1, recurrence_threshold=1)
    assert second.phase == "paragraphs"
    assert second.paragraphs_remaining == 0
    assert ex.pending_paragraphs(repository) == []

    third = drivers.run_extraction(repository, model, SESSION, limit=5, recurrence_threshold=1)
    assert third.phase == "summaries"
    assert third.finished is True
    assert third.summaries_written >= 1
    assert third.summaries_remaining == 0
    assert third.rejected == ()

    fourth = drivers.run_extraction(repository, model, SESSION, limit=5, recurrence_threshold=1)
    assert fourth.phase == "done"
    assert fourth.spend.calls == 0
    assert fourth.summaries_written == 0

    # What the model saw: the brief as the system block, one paragraph per
    # call, read alone.
    readings = [r for r in model.requests if r.pass_name == drivers.PASS_EXTRACTION]
    assert len(readings) == 2
    assert all(ex.EXTRACTION_PROMPT in r.system for r in readings)
    assert readings[0].user.startswith("anchor: src-000001-p1\n---\nBob and the acquisition.")
    assert readings[1].user.startswith("anchor: src-000001-p2\n---\nBob again.")
    summaries = [r for r in model.requests if r.pass_name == drivers.PASS_CLUSTER_SUMMARY]
    assert summaries and "Bob and the acquisition." in summaries[0].user

    state = ex.status(repository)
    assert state.extracted == 2 and state.pending == 0
    assert state.summaries_pending == 0 and state.summaries_done >= 1
    assert ex.cluster_summary(repository, summaries[0].user.split("\n", 1)[0].removeprefix("cluster: ")) == "Bob, throughout."


def test_every_call_is_ledgered_as_spend_beside_what_was_served(tmp_path):
    repository = _repo(tmp_path, ["Bob and the acquisition.", "Bob again."])
    model = FakeModel(_summary_or_reading)
    drivers.run_extraction(repository, model, SESSION, limit=2, recurrence_threshold=1)

    events = _ledger(repository)
    tools = [event["tool"] for event in events]
    assert tools[:2] == ["extraction_brief", "extraction_next_paragraphs"]
    assert tools.count("model_call") == 2
    served = [event for event in events if event["tool"] == "extraction_next_paragraphs"]
    assert served[0]["served"] == ["src-000001-p1", "src-000001-p2"]

    call = _model_calls(repository)[0]
    assert call["pass"] == "extraction"
    assert call["provider"] == "anthropic"
    assert call["model"] == "fake-model"
    assert (call["input_tokens"], call["output_tokens"]) == (7, 3)
    assert call["stop_reason"] == "end_turn"
    assert call["anchor"] == "src-000001-p1"
    assert "served" not in call, "a spend line must never read as a served read"

    drivers.run_extraction(repository, model, SESSION, limit=5, recurrence_threshold=1)
    summary_calls = [c for c in _model_calls(repository) if c["pass"] == "cluster_summary"]
    assert summary_calls
    assert any(event["tool"] == "extraction_next_summary" for event in _ledger(repository))


def test_a_refusal_a_truncation_and_bad_json_reject_one_item_each_and_the_run_goes_on(tmp_path):
    repository = _repo(
        tmp_path, ["Bob refused.", "Bob cut off.", "Bob garbled.", "Bob fine."]
    )

    def handler(request):
        if "refused" in request.user:
            return _refusal()
        if "cut off" in request.user:
            return _truncated('{"placements": [')
        if "garbled" in request.user:
            return "not json at all"
        return _reading_of(request)

    report = drivers.run_extraction(repository, FakeModel(handler), SESSION, limit=10)
    assert report.paragraphs_read == 4
    assert report.paragraphs_accepted == 1
    reasons = {r.anchor: r.reason for r in report.rejected}
    assert "refused" in reasons["src-000001-p1"] and "general_harms" in reasons["src-000001-p1"]
    assert "max_tokens" in reasons["src-000001-p2"]
    assert "not JSON" in reasons["src-000001-p3"]
    assert report.paragraphs_remaining == 3
    assert report.spend.calls == 4
    refused = [c for c in _model_calls(repository) if c["stop_reason"] == "refusal"]
    assert len(refused) == 1, "a refusal was billed for its input and is ledgered"


def test_a_reading_the_core_rejects_is_reported_with_the_cores_reason(tmp_path):
    repository = _repo(tmp_path, ["Bob and Alice."])

    def handler(request):
        return {
            "placements": [],
            "unplaced": [{"surface_form": "Bob", "subject_id": "SUB-people"}],
            # A relation whose ends are not placed - the core refuses it.
            "relations": [{"from_ref": "SUB-people/bob", "verb": "meets", "to_ref": "SUB-people/alice"}],
        }

    report = drivers.run_extraction(repository, FakeModel(handler), SESSION)
    assert report.paragraphs_accepted == 0
    assert len(report.rejected) == 1
    assert report.rejected[0].anchor == "src-000001-p1"
    assert ex.pending_paragraphs(repository), "nothing was cached for a rejected reading"


def test_an_off_schema_reply_is_rejected_not_crashed_on(tmp_path):
    repository = _repo(tmp_path, ["Bob."])
    report = drivers.run_extraction(
        repository, FakeModel(lambda r: {"placements": "no", "unplaced": [], "relations": []}), SESSION
    )
    assert report.paragraphs_accepted == 0
    assert "placements" in report.rejected[0].reason


def test_a_provider_failure_stops_the_run_and_keeps_what_was_recorded(tmp_path):
    repository = _repo(tmp_path, ["Bob one.", "Bob two.", "Bob three."])
    seen = []

    def handler(request):
        seen.append(request.user)
        if len(seen) == 2:
            raise ModelError("rate-limited")
        return _reading_of(request)

    # The batch is recorded after every call in it - so a failure on the
    # second call loses the first call's reading. That is the accepted
    # cost of one record_batch per step; the paragraph is simply read
    # again next time, at one call's price.
    with pytest.raises(ModelError):
        drivers.run_extraction(repository, FakeModel(handler), SESSION, limit=3)
    # The failed call is ledgered too - the author may have been billed for
    # it - as an error line with no usage figures, and the run stops there.
    calls = _model_calls(repository)
    assert [c["stop_reason"] for c in calls] == ["end_turn", "error"]
    assert calls[1]["error"] == "rate-limited"
    assert calls[1]["input_tokens"] == 0 and calls[1]["model"] == ""
    assert len(ex.pending_paragraphs(repository)) == 3


def test_a_limit_below_one_is_refused(tmp_path):
    repository = _repo(tmp_path, ["Bob."])
    with pytest.raises(ValueError):
        drivers.run_extraction(repository, FakeModel(_reading_of), SESSION, limit=0)


def test_the_whole_direct_run_leaves_no_process_and_opens_no_socket(tmp_path, monkeypatch):
    """The driver itself never leaves the process - the fake is the only
    thing standing where a model would, and the run is otherwise the same
    derive-and-summarize loop `test_extraction.py` holds to this."""
    repository = _repo(tmp_path, ["Bob and the acquisition.", "Bob again."])

    def refuse(*args, **kwargs):
        raise AssertionError("the direct run left the process")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)

    model = FakeModel(_summary_or_reading)
    while True:
        report = drivers.run_extraction(repository, model, SESSION, limit=10, recurrence_threshold=1)
        if report.phase == "done":
            break
    assert ex.pending_cluster_summaries(repository) == []


def test_the_summary_of_a_parent_is_written_from_its_children_and_never_a_paragraph(tmp_path):
    """The one structural rule of the summary loop, held here as it is held
    for a session: a parent's user turn carries child summaries only."""
    repository = _repo(tmp_path, ["Bob and the acquisition.", "Bob again."])
    model = FakeModel(_summary_or_reading)
    while drivers.run_extraction(repository, model, SESSION, limit=10, recurrence_threshold=1).phase != "done":
        pass
    for request in model.requests:
        if request.pass_name != drivers.PASS_CLUSTER_SUMMARY:
            continue
        if "## Its child clusters' summaries" in request.user:
            assert "Bob and the acquisition." not in request.user
        else:
            assert "## Its member paragraphs" in request.user


# --- the audit -----------------------------------------------------------------


def _manuscript(tmp_path, *, draft="Bob went to town.", sources=("Bob went to market.",)):
    entry = Entry(id="SUB-people/bob", match_terms=["Bob"], body="Bob is tall.")
    repository = _repo(tmp_path, list(sources), entries=(entry,))
    chapter = create_chapter(repository, "A chapter.")
    section = create_section(repository, chapter.number, "About Bob.")
    (section.dir / "draft.md").write_text(draft, encoding="utf-8")
    return repository, chapter, section


def _answer_audit(request):
    assert request.pass_name == drivers.PASS_AUDIT
    if "kind: engagement" in request.user:
        assert request.schema == drivers.ENGAGEMENT_SCHEMA
        return {"engages": True, "note": "names Bob"}
    assert request.schema == drivers.VERDICT_SCHEMA
    return {
        "clear": False,
        "finding": {
            "disagreement_set": [
                {"kind": "passage", "ref": request.user.split("\n", 1)[0].removeprefix("anchor: ").split("|")[0]},
                {"kind": "entry", "ref": "SUB-people/bob"},
            ],
            "statement": "The town is not the market.",
            "confidence": "high",
            "patch": "",
        },
    }


def test_the_audit_answers_every_task_of_a_target_and_records_them(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)
    before = audit.pending_for_target(repository, chapter_number=chapter.number, section_number=section.number)
    assert before

    model = FakeModel(_answer_audit)
    report = drivers.run_audit(
        repository, model, SESSION, chapter_number=chapter.number, section_number=section.number
    )

    assert report.rejected == ()
    assert report.accepted == len(before)
    assert report.remaining == 0
    assert report.findings == 1
    assert report.spend.calls == len(before)
    assert audit.pending_for_target(
        repository, chapter_number=chapter.number, section_number=section.number
    ) == ()
    paragraph = manuscript_paragraphs(repository)[0]
    findings = audit.findings_in_scope(repository, chapter_number=chapter.number)
    assert any(f.statement == "The town is not the market." for f in findings)
    assert paragraph.slot in {m.ref for f in findings for m in f.disagreement_set}


def test_the_audit_serves_the_policy_the_entry_and_the_gathered_evidence(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)
    assert gather(repository, "SUB-people/bob"), "the fixture's source must gather"
    model = FakeModel(_answer_audit)
    drivers.run_audit(repository, model, SESSION, chapter_number=chapter.number, section_number=section.number)

    verdicts = [r for r in model.requests if "kind: audit_verdict" in r.user]
    assert verdicts
    # The policy rides on each verdict task, as audit_pending serves it - and
    # on no engagement task, which a session never sees it on either.
    assert audit.AUTHOR_TESTIMONY_POLICY in verdicts[0].user
    assert audit.AUTHOR_TESTIMONY_POLICY not in verdicts[0].system
    engagements = [r for r in model.requests if "kind: engagement" in r.user]
    assert engagements
    assert all(audit.AUTHOR_TESTIMONY_POLICY not in r.user for r in engagements)
    assert "Bob is tall." in verdicts[0].user
    assert "Bob went to town." in verdicts[0].user
    assert "gathered evidence:" in verdicts[0].user
    assert "Bob went to market." in verdicts[0].user, "a session would read(ref) it; the driver inlines it"
    reads = [e for e in _ledger(repository) if e["tool"] == "read"]
    assert reads and reads[0]["ref"] == "src-000001-p1"


def test_the_audit_rejects_a_verdict_when_its_gathered_evidence_cannot_be_read(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)
    assert gather(repository, "SUB-people/bob"), "the stale index must still name the source"
    record_path(repository, "SRC-000001").unlink()
    model = FakeModel(_answer_audit)

    report = drivers.run_audit(
        repository, model, SESSION, chapter_number=chapter.number, section_number=section.number
    )

    assert report.accepted == 1, "the evidence-free engagement judgement can still be recorded"
    assert report.remaining == 1
    assert len(report.rejected) == 1
    assert "src-000001-p1" in report.rejected[0].reason
    assert "could not be read" in report.rejected[0].reason
    assert not any("kind: audit_verdict" in request.user for request in model.requests)


def test_the_audit_puts_the_writing_style_above_a_verdict(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)
    style.set_style(repository, style.WritingStyle(direction="Stay plain."), None, AUTHOR)
    model = FakeModel(_answer_audit)
    drivers.run_audit(repository, model, SESSION, chapter_number=chapter.number, section_number=section.number)
    assert "Stay plain." in model.requests[0].system


def test_a_clear_verdict_and_an_empty_patch_round_trip(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)

    def handler(request):
        if "kind: engagement" in request.user:
            return {"engages": False, "note": ""}
        return {"clear": True, "finding": {"disagreement_set": [], "statement": "", "confidence": "", "patch": ""}}

    report = drivers.run_audit(
        repository, FakeModel(handler), SESSION, chapter_number=chapter.number, section_number=section.number
    )
    assert report.rejected == ()
    assert report.findings == 0
    assert report.remaining == 0


def test_an_audit_reply_off_shape_is_rejected_per_task(tmp_path):
    repository, chapter, section = _manuscript(tmp_path)

    def handler(request):
        if "kind: engagement" in request.user:
            return {"engages": "yes", "note": ""}
        return {"clear": False, "finding": "none"}

    report = drivers.run_audit(
        repository, FakeModel(handler), SESSION, chapter_number=chapter.number, section_number=section.number
    )
    assert report.accepted == 0
    assert {r.reason for r in report.rejected} == {
        "'engages' is not a boolean",
        "a verdict that is not clear needs a finding",
    }
    assert report.remaining > 0


def test_the_audit_refuses_a_passage_without_its_section(tmp_path):
    repository, chapter, _ = _manuscript(tmp_path)
    with pytest.raises(ValueError):
        drivers.run_audit(repository, FakeModel(_answer_audit), SESSION, chapter_number=chapter.number, paragraph_index=1)


def test_an_audit_with_nothing_pending_makes_no_call(tmp_path):
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    chapter = create_chapter(repository, "A chapter.")
    model = FakeModel(_answer_audit)
    report = drivers.run_audit(repository, model, SESSION, chapter_number=chapter.number)
    assert report.spend.calls == 0 and report.remaining == 0
    assert model.requests == []


# --- the writing-style analysis -------------------------------------------------


def _style_repo(tmp_path):
    repository = _repo(tmp_path, ["The deck went up unchanged.", "Nobody dared touch it."])
    style.set_style(
        repository,
        style.WritingStyle(direction="Stay in the moment.", sample_sources=("SRC-000001",)),
        None,
        AUTHOR,
    )
    return repository


def test_the_style_analysis_records_what_quotes_the_samples_and_refuses_what_does_not(tmp_path):
    repository = _style_repo(tmp_path)

    def handler(request):
        assert request.pass_name == drivers.PASS_STYLE
        assert request.schema == drivers.STYLE_SCHEMA
        assert style.STYLE_ANALYSIS_PROMPT in request.system
        assert "Stay in the moment." in request.system
        assert "## The samples (1)" in request.user
        assert "Nobody dared touch it." in request.user
        return {
            "observations": [
                {"aspect": "rhythm", "observation": "End on the noun.", "example": "Nobody dared touch it."},
                {"aspect": "register", "observation": "Stay plain.", "example": "This never appears."},
            ]
        }

    report = drivers.run_style(repository, FakeModel(handler), SESSION)
    assert report.accepted == 1
    assert len(report.rejected) == 1
    assert report.rejected[0].anchor == "2"
    assert "not in the samples verbatim" in report.rejected[0].reason
    pending = style.pending_observations(repository)
    assert [o.observation for o in pending] == ["End on the noun."]
    events = _ledger(repository)
    assert [e["tool"] for e in events] == ["style_brief", "model_call"]
    assert events[0]["served"] == ["SRC-000001"]
    assert events[1]["pass"] == "style"


def test_a_style_analysis_with_nothing_to_read_refuses_before_any_call(tmp_path):
    repository = _repo(tmp_path, ["A paragraph."])
    model = FakeModel(lambda r: {"observations": []})
    with pytest.raises(style.StyleError):
        drivers.run_style(repository, model, SESSION)
    assert model.requests == []


def test_a_refused_or_empty_style_analysis_is_one_rejection(tmp_path):
    repository = _style_repo(tmp_path)
    refused = drivers.run_style(repository, FakeModel(lambda r: _refusal()), SESSION)
    assert refused.accepted == 0 and "refused" in refused.rejected[0].reason
    empty = drivers.run_style(repository, FakeModel(lambda r: {"observations": []}), SESSION)
    assert empty.accepted == 0 and "no observations" in empty.rejected[0].reason
    assert style.pending_observations(repository) == []
