"""The writing style (ADR-0009): the durable file, the uploaded samples, the
analysis brief, and the proposed observations the author confirms."""

import subprocess

import pytest

from memoria import style
from memoria.assembly import assemble
from memoria.context_manifest import build_context_manifest
from memoria.index import build_index, connect
from memoria.ledger import event_path
from memoria.manuscript import Brief
from memoria.records import (
    NORMALIZED_RELATIVE_PATH,
    NormalizedRecord,
    write_normalized_records,
)
from memoria.repository import Repository
from memoria.style import (
    STYLE_RELATIVE_PATH,
    RecordedObservation,
    StyleError,
    WritingStyle,
    add_sample,
    brief,
    confirm_observation,
    discard_observation,
    list_samples,
    load_style,
    parse_style,
    pending_observations,
    record_observations,
    serve_style,
    set_style,
    style_to_markdown,
    writing_style_prompt,
)
from memoria.write import Actor, Rejected, Written

AUTHOR = Actor(name="Local Author", email="local@memoria.test")
PARAGRAPHS = [
    "The deck went up unchanged. Nobody dared touch it.",
    "I wrote to Bob that evening - three lines, no greeting - and heard nothing.",
]


def _record(repository, observations):
    """``record_observations`` bound to the key the brief currently serves -
    the skill echoes it, and the tests here never change samples mid-batch."""
    return record_observations(repository, observations, brief(repository).analysis_key)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, *, records=True) -> Repository:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    if records:
        record = NormalizedRecord(
            id="SRC-000184",
            source_type="journal",
            recorded_date="Oct. 22.",
            event_date="Oct. 22.",
            date_confidence="exact",
            contemporaneous=True,
            original_file="raw/vol-01/text.txt",
            original_locator="Journal I",
            paragraphs=PARAGRAPHS,
        )
        write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
        build_index(repository, [record])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial", "--allow-empty")
    return repository


def _style(**overrides) -> WritingStyle:
    fields = dict(
        direction="Keep me inside what I knew at the time.",
        observations=("Keep sentences short.", "End on the concrete noun."),
        sample_sources=("SRC-000184",),
    )
    fields.update(overrides)
    return WritingStyle(**fields)


# --- the file -----------------------------------------------------------------


def test_the_file_round_trips_exactly():
    text = style_to_markdown(_style())
    assert parse_style(text) == _style()
    assert style_to_markdown(parse_style(text)) == text


def test_the_file_reads_as_a_person_would_write_it():
    text = style_to_markdown(_style())
    assert text.startswith("---\nid: STYLE\nsample_sources:\n- SRC-000184\n---\n")
    assert "## Direction\n\nKeep me inside what I knew at the time.\n" in text
    assert text.endswith("## Observations\n\n- Keep sentences short.\n- End on the concrete noun.\n")


def test_a_hand_edited_file_still_parses():
    text = (
        "---\nid: STYLE\nsample_sources: []\n---\n"
        "## Direction\n\nPlain,\nunhurried.\n\n\n## Observations\n"
        "* Short sentences.\n- A long one,\n  wrapped by hand.\n"
    )
    parsed = parse_style(text)
    assert parsed.direction == "Plain,\nunhurried."
    assert parsed.observations == ("Short sentences.", "A long one, wrapped by hand.")


def test_an_unknown_frontmatter_field_is_named_not_swallowed():
    with pytest.raises(StyleError, match="does not define: tone"):
        parse_style("---\nid: STYLE\ntone: dry\n---\n\n## Direction\n")


def test_normalization_drops_empty_observations_and_duplicate_sources():
    normalized = style.normalize_style(
        WritingStyle(
            direction="  x \r\n",
            observations=("  ", "one\nline"),
            sample_sources=("SRC-1", " SRC-1", "SRC-2"),
        )
    )
    assert normalized == WritingStyle("x", ("one line",), ("SRC-1", "SRC-2"))


# --- the write path -----------------------------------------------------------


def test_the_first_write_creates_and_commits_as_the_author(tmp_path):
    repository = _repo(tmp_path)
    assert serve_style(repository) == (None, None)

    result = set_style(repository, _style(), None, AUTHOR)

    assert isinstance(result, Written)
    assert load_style(repository) == _style()
    log = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>%n%B", "--", STYLE_RELATIVE_PATH],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout
    assert log.startswith("Local Author <local@memoria.test>")
    assert "change-id:" in log


def test_a_second_write_needs_the_token_and_a_stale_one_is_rejected(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(), None, AUTHOR)
    _, token = serve_style(repository)

    # No token where a file exists: the "changed underneath" answer.
    assert isinstance(set_style(repository, _style(direction="x"), None, AUTHOR), Rejected)
    stale = set_style(repository, _style(direction="x"), "not-the-token", AUTHOR)
    assert isinstance(stale, Rejected) and stale.outcome == "stale"
    assert load_style(repository) == _style()

    assert isinstance(set_style(repository, _style(direction="x"), token, AUTHOR), Written)
    assert load_style(repository).direction == "x"


def test_a_sample_source_that_names_no_record_is_refused_before_writing(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(StyleError, match="SRC-999999"):
        set_style(repository, _style(sample_sources=("SRC-999999",)), None, AUTHOR)
    assert load_style(repository) is None


def test_an_unattributed_actor_is_refused(tmp_path):
    repository = _repo(tmp_path)
    with pytest.raises(StyleError, match="attributed"):
        set_style(repository, _style(), None, Actor(name="", email=""))


# --- the rendering a writer receives ------------------------------------------


def test_the_prompt_is_one_rendering_and_nothing_when_empty():
    assert writing_style_prompt(None) is None
    assert writing_style_prompt(WritingStyle()) is None
    rendered = writing_style_prompt(_style())
    assert rendered == (
        "# Writing style\n\nKeep me inside what I knew at the time.\n\n"
        "Observed in the author's own writing. Follow each:\n\n"
        "- Keep sentences short.\n- End on the concrete noun."
    )


def test_assembly_loads_the_style_as_tier_one_and_ledgers_the_fact(tmp_path):
    repository = _repo(tmp_path)
    brief_ = Brief(id="SEC-0001", text="About nothing in particular.")

    before = assemble(repository, "SES-test", brief_)
    assert before.writing_style is None

    set_style(repository, _style(), None, AUTHOR)
    after = assemble(repository, "SES-test", brief_)

    assert after.writing_style == writing_style_prompt(_style())
    lines = event_path(repository, "SES-test").read_text(encoding="utf-8").splitlines()
    assert '"writing_style": null' in lines[0]
    assert f'"writing_style": "{STYLE_RELATIVE_PATH}"' in lines[1]
    # The fact, never the text, reaches the ledger.
    assert "concrete noun" not in lines[1]
    resolutions = build_context_manifest(repository, "SES-test")["scope_resolutions"]
    assert [r["writing_style"] for r in resolutions] == [None, STYLE_RELATIVE_PATH]


# --- uploaded samples ---------------------------------------------------------


def test_an_uploaded_text_file_becomes_a_sample_under_style(tmp_path):
    repository = _repo(tmp_path)

    result = add_sample(repository, "Letter to Bob.txt", b"Dear Bob,\r\n\r\nNo.\r\n", AUTHOR)

    assert result == Written(path="style/samples/letter-to-bob.md")
    (sample,) = list_samples(repository)
    assert sample.title == "Letter to Bob"
    assert sample.original_file == "Letter to Bob.txt"
    assert sample.paragraphs == ("Dear Bob,", "No.")
    assert isinstance(
        add_sample(repository, "letter-to-bob.txt", b"again", AUTHOR), Rejected
    )


@pytest.mark.parametrize("filename", ["notes.rtf", "photo.png"])
def test_an_unsupported_upload_is_refused(tmp_path, filename):
    repository = _repo(tmp_path)
    with pytest.raises(StyleError, match="supported"):
        add_sample(repository, filename, b"x", AUTHOR)


def test_an_empty_upload_is_refused(tmp_path):
    with pytest.raises(StyleError, match="no text"):
        add_sample(_repo(tmp_path), "empty.txt", b"  \n\n ", AUTHOR)


# --- the analysis: serve, then record ----------------------------------------


def test_the_brief_refuses_to_serve_nothing(tmp_path):
    with pytest.raises(StyleError, match="choose sources or upload"):
        brief(_repo(tmp_path))


def test_the_brief_serves_the_prompt_verbatim_and_every_sample(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)

    served = brief(repository)

    assert served.prompt == style.STYLE_ANALYSIS_PROMPT
    assert [s.ref for s in served.samples] == ["SRC-000184", "style/samples/letter.md"]
    assert served.samples[0].text == "\n\n".join(PARAGRAPHS)
    assert served.samples[0].truncated is False
    assert served.samples[1].text == "Dear Bob,\n\nNo."
    assert served.current == load_style(repository)


def test_a_long_source_is_truncated_and_says_so(tmp_path, monkeypatch):
    repository = _repo(tmp_path)
    set_style(repository, _style(), None, AUTHOR)
    monkeypatch.setattr(style, "SAMPLE_PARAGRAPH_LIMIT", 1)

    (sample,) = brief(repository).samples
    assert sample.truncated is True
    assert sample.text == PARAGRAPHS[0]


def test_recording_keeps_the_honest_and_refuses_the_rest(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)

    outcome = _record(
        repository,
        [
            RecordedObservation("rhythm", "Keep sentences short.", "Nobody dared touch it."),
            RecordedObservation("", "x", "Nobody dared touch it."),
            RecordedObservation("register", "Be warm.", "With love, as ever."),
            # Whitespace differs from the sample; the words do not.
            RecordedObservation("dashes", "Use dashes.", "three lines,  no greeting"),
        ],
    )

    assert len(outcome.accepted) == 2
    assert [ordinal for ordinal, _ in outcome.rejected] == [2, 3]
    assert "not in a sample verbatim" in outcome.rejected[1][1]
    pending = pending_observations(repository)
    assert [o.observation for o in pending] == ["Keep sentences short.", "Use dashes."]
    assert all(o.status == "proposed" for o in pending)


def test_a_quote_that_spans_two_samples_is_refused(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)

    # The words run from the source's last sentence into the uploaded one:
    # contiguous once every sample is concatenated, contiguous in neither.
    outcome = _record(
        repository,
        [RecordedObservation("splice", "Do not.", "heard nothing. Dear Bob,")],
    )

    assert outcome.accepted == ()
    assert "not in a sample verbatim" in outcome.rejected[0][1]


def test_a_batch_is_refused_when_the_samples_changed_since_the_brief(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)
    served = brief(repository).analysis_key

    add_sample(repository, "extra.txt", b"Another voice entirely.", AUTHOR)

    with pytest.raises(StyleError, match="samples changed"):
        record_observations(
            repository,
            [RecordedObservation("a", "Say no.", "Nobody dared touch it.")],
            served,
        )
    assert pending_observations(repository) == []


def test_a_second_batch_over_the_same_samples_replaces_the_proposed_rows(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)
    _record(
        repository, [RecordedObservation("a", "First opinion.", "Nobody dared touch it.")]
    )
    (first,) = pending_observations(repository)
    discard_observation(repository, first.id)
    _record(
        repository, [RecordedObservation("a", "Kept.", "Nobody dared touch it.")]
    )

    _record(
        repository, [RecordedObservation("a", "Second opinion.", "Nobody dared touch it.")]
    )

    assert [o.observation for o in pending_observations(repository)] == ["Second opinion."]
    assert style.status(repository).discarded == 1


def test_confirming_writes_the_style_first_and_marks_the_row_only_on_success(tmp_path):
    repository = _repo(tmp_path)
    set_style(repository, _style(observations=()), None, AUTHOR)
    _record(
        repository, [RecordedObservation("a", "As proposed.", "Nobody dared touch it.")]
    )
    (proposed,) = pending_observations(repository)

    stale = confirm_observation(repository, proposed.id, None, "wrong-token", AUTHOR)
    assert isinstance(stale, Rejected)
    assert load_style(repository).observations == ()
    assert pending_observations(repository) == [proposed]

    _, token = serve_style(repository)
    written = confirm_observation(repository, proposed.id, "As changed.", token, AUTHOR)

    assert isinstance(written, Written)
    assert load_style(repository).observations == ("As changed.",)
    assert pending_observations(repository) == []
    resolved = style.get_observation(repository, proposed.id)
    assert (resolved.status, resolved.resolved_text) == ("confirmed", "As changed.")
    with pytest.raises(StyleError, match="already confirmed"):
        confirm_observation(repository, proposed.id, None, token, AUTHOR)


def test_confirming_with_no_style_file_yet_creates_one(tmp_path):
    repository = _repo(tmp_path)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)
    _record(repository, [RecordedObservation("a", "Say no.", "No.")])
    (proposed,) = pending_observations(repository)

    assert isinstance(confirm_observation(repository, proposed.id, None, None, AUTHOR), Written)
    assert load_style(repository) == WritingStyle(observations=("Say no.",))


def test_discarding_writes_nothing_durable(tmp_path):
    repository = _repo(tmp_path)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)
    _record(repository, [RecordedObservation("a", "Say no.", "No.")])
    (proposed,) = pending_observations(repository)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout

    discarded = discard_observation(repository, proposed.id)

    assert discarded.status == "discarded"
    assert load_style(repository) is None
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout == head
    with pytest.raises(StyleError, match="no such observation"):
        discard_observation(repository, 999)


def test_a_rebuild_keeps_the_proposed_rows(tmp_path):
    repository = _repo(tmp_path)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)
    _record(repository, [RecordedObservation("a", "Say no.", "No.")])

    build_index(repository, [])
    assert [o.observation for o in pending_observations(repository)] == ["Say no."]

    build_index(repository, [], reset_cache=True)
    assert pending_observations(repository) == []


def test_the_status_counts_everything_the_surfaces_need(tmp_path):
    repository = _repo(tmp_path)
    assert style.status(repository).exists is False
    set_style(repository, _style(), None, AUTHOR)
    add_sample(repository, "letter.txt", b"Dear Bob,\n\nNo.", AUTHOR)
    _record(repository, [RecordedObservation("a", "Say no.", "No.")])

    state = style.status(repository)

    assert (state.exists, state.direction_set, state.observations) == (True, True, 2)
    assert (state.sample_sources, state.uploaded_samples) == (1, 1)
    assert (state.proposed, state.confirmed, state.discarded) == (1, 0, 0)


def test_the_observations_table_is_preserved_by_name():
    from memoria.index import PRESERVED_TABLES

    assert "style_observations" in PRESERVED_TABLES
