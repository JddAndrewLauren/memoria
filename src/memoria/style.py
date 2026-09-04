"""The writing style: book-wide craft direction every writing agent receives,
and the analysis that proposes it from the author's own samples.

**What it is.** ``style/writing-style.md`` is one durable file holding the
author's writing style - free-prose *direction* and a list of confirmed
*observations*, each phrased as a directive a writer can follow - plus the
sources chosen as samples of the author's own writing. It is author-supreme
and editable in Obsidian like every other durable file, and the Settings
surface is only the app's window onto it (ADR-0009). It is craft direction,
not testimony (part 06 §8.6): nothing in it is a claim about the world, and
the audit never checks prose against it.

**Where it reaches a writer.** ``writing_style_prompt`` is the one rendering
of the file as the text a writing agent receives, and every caller serves
that same string: ``memoria.assembly.assemble`` loads it into the working
context as Tier 1 "voice guidance" (part 18 §52.4); the MCP ``writing_style``
tool serves it to a session on demand; ``audit_pending`` prints it above a
batch so a proposed rewrite follows it. There is no second rendering to
drift from the first.

**The analysis is a conversation, not a service.** No adapter and no core
module calls a model (``docs/poc-plan.md`` §3, ``docs/tool-surface.md``), so
the analysis is the same serve-then-record shape as the extraction:
``brief`` serves ``STYLE_ANALYSIS_PROMPT`` verbatim with the sample texts,
the session reads them, and ``record_observations`` takes the observations
back as tool arguments. Each recorded observation must quote an example that
occurs verbatim in the served samples - the honesty check the core holds
rather than the prompt, the same way ``extraction_record`` refuses a relation
to an unplaced form.

**Proposed observations assert nothing.** They live in ``.memoria/index.db``
(``style_observations``, a preserved table like the memo cache), never in a
durable file, and become part of the style only when the author confirms
one - possibly edited - in Settings, which is a write to the durable file
committed as the author's own. A discarded one stays discarded. This is the
candidate/promote shape of ADR-0005 applied to craft direction: the session
proposes, the author promotes.

**Uploaded samples are not evidence.** ``style/samples/*.md`` are documents
the author supplied for their style alone: never normalized, never gathered,
never searchable and never citable. They are durable (the author put them
there) but they carry no ``SRC-`` id and no anchor.

Every write here goes through ``memoria.write`` (ADR-0003); this module
opens no file for writing itself.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from memoria import index, normalize, records, write
from memoria.repository import Repository
from memoria.write import Actor, Rejected, WriteResult, Written

STYLE_RELATIVE_PATH = "style/writing-style.md"
SAMPLES_RELATIVE_DIR = "style/samples"
STYLE_ID = "STYLE"

# How many paragraphs of one chosen source the brief serves. A journal
# volume or an email export can run to thousands; a style is legible from
# far fewer, and the cap is what keeps one sample from crowding out the
# others in the session's context. The brief says when it truncated.
SAMPLE_PARAGRAPH_LIMIT = 80

# Bumped when the composition of an analysis key changes. A key names the
# prompt and the samples an observation was proposed from, so a re-run over
# the same samples replaces its still-proposed rows rather than piling up.
ANALYSIS_KEY_VERSION = "memoria-style-v1"


class StyleError(Exception):
    """A style operation that cannot be attempted at all - a malformed
    file, an unknown sample source, an unsupported upload, an observation
    id that names nothing. Distinct from a stale token, which is the normal
    ``Rejected`` outcome the caller reports (ADR-0003)."""


# --- the file, both directions ------------------------------------------------


@dataclass(frozen=True)
class WritingStyle:
    """The writing style as the file holds it.

    ``direction`` is the author's own prose; ``observations`` are the
    confirmed observations, one directive each; ``sample_sources`` are the
    ``SRC-`` ids chosen as samples of the author's writing. Every value is
    normalized (``normalize_style``) before it is written, so the on-disk
    form round-trips exactly.
    """

    direction: str = ""
    observations: tuple[str, ...] = ()
    sample_sources: tuple[str, ...] = ()


_DIRECTION_HEADING = "## Direction"
_OBSERVATIONS_HEADING = "## Observations"
_FRONTMATTER_FIELDS = ("id", "sample_sources")
_WHITESPACE = re.compile(r"\s+")


def _one_line(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def normalize_style(style: WritingStyle) -> WritingStyle:
    """The canonical form ``style_to_markdown`` writes: direction stripped,
    each observation on one line with no empties, sample ids deduplicated in
    the order given."""
    seen: list[str] = []
    for source_id in style.sample_sources:
        source_id = source_id.strip()
        if source_id and source_id not in seen:
            seen.append(source_id)
    return WritingStyle(
        direction=style.direction.replace("\r\n", "\n").strip(),
        observations=tuple(
            line for line in (_one_line(o) for o in style.observations) if line
        ),
        sample_sources=tuple(seen),
    )


def style_to_markdown(style: WritingStyle) -> str:
    """Serialize a style to its on-disk Markdown form.

    Frontmatter carrying only ``id`` and ``sample_sources``, then the two
    headed sections. The form is deliberately the one a person would write
    by hand in Obsidian - a heading, some prose, a heading, a bullet list -
    so the file stays readable without Memoria-specific software.
    """
    style = normalize_style(style)
    frontmatter = {"id": STYLE_ID, "sample_sources": list(style.sample_sources)}
    lines = [
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False).rstrip("\n"),
        "---",
        "",
        _DIRECTION_HEADING,
        "",
    ]
    if style.direction:
        lines += [style.direction, ""]
    lines += [_OBSERVATIONS_HEADING, ""]
    lines += [f"- {observation}" for observation in style.observations]
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_style(text: str, *, source: str = "<string>") -> WritingStyle:
    """Parse a style file back into a ``WritingStyle``.

    The inverse of ``style_to_markdown`` for anything it wrote, and lenient
    about what a hand edit leaves behind: a missing section is empty, a
    bullet may use ``-`` or ``*``, and blank lines are free. A frontmatter
    key the file does not define is named rather than swallowed, the
    discipline ``manuscript.parse_brief`` keeps.
    """
    if text.startswith("---\r\n"):
        raise StyleError(f"{source}: the style has CRLF line endings - the format is LF")
    if not text.startswith("---\n"):
        raise StyleError(f"{source}: not a writing style - no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise StyleError(f"{source}: frontmatter is not terminated")
    try:
        frontmatter = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise StyleError(f"{source}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise StyleError(f"{source}: frontmatter is not a mapping")
    unexpected = set(frontmatter) - set(_FRONTMATTER_FIELDS)
    if unexpected:
        raise StyleError(
            f"{source}: frontmatter carries fields a writing style does not define: "
            + ", ".join(sorted(unexpected))
        )
    if frontmatter.get("id") != STYLE_ID:
        raise StyleError(f"{source}: 'id' must be {STYLE_ID!r}")
    sample_sources = frontmatter.get("sample_sources") or []
    if not isinstance(sample_sources, list) or not all(
        isinstance(item, str) for item in sample_sources
    ):
        raise StyleError(f"{source}: 'sample_sources' must be a list of record ids")

    body = text[end + len("\n---\n") :]
    direction_lines: list[str] = []
    observations: list[str] = []
    section: str | None = None
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped == _DIRECTION_HEADING:
            section = "direction"
            continue
        if stripped == _OBSERVATIONS_HEADING:
            section = "observations"
            continue
        if section == "direction":
            direction_lines.append(line)
        elif section == "observations":
            if stripped.startswith(("- ", "* ")):
                observations.append(stripped[2:])
            elif stripped and observations:
                # A bullet wrapped onto a second line by hand.
                observations[-1] = observations[-1] + " " + stripped
            elif stripped:
                observations.append(stripped)
    return normalize_style(
        WritingStyle(
            direction="\n".join(direction_lines),
            observations=tuple(observations),
            sample_sources=tuple(sample_sources),
        )
    )


def _style_path(repository: Repository) -> Path:
    return repository.root / STYLE_RELATIVE_PATH


def load_style(repository: Repository) -> WritingStyle | None:
    """The writing style, or ``None`` when none has been written."""
    path = _style_path(repository)
    if not path.is_file():
        return None
    return parse_style(path.read_text(encoding="utf-8"), source=STYLE_RELATIVE_PATH)


def serve_style(repository: Repository) -> tuple[WritingStyle | None, str | None]:
    """The style plus the staleness token a later ``set_style`` must present
    (ADR-0003) - both ``None`` when there is no file yet, in which case the
    first write goes through ``write.create`` and needs no token."""
    if not _style_path(repository).is_file():
        return None, None
    served = write.serve(repository, STYLE_RELATIVE_PATH)
    return parse_style(served.text, source=STYLE_RELATIVE_PATH), served.token


def set_style(
    repository: Repository,
    style: WritingStyle,
    token: str | None,
    actor: Actor,
) -> WriteResult:
    """Replace the writing style - an author act through the one write path.

    ``token`` is what ``serve_style`` minted, or ``None`` for the first
    write, which goes through ``write.create`` and is ``Rejected`` with
    ``outcome="exists"`` if a file has appeared since - the same "changed
    underneath" answer a stale token gives, for the same reason.

    Refused before the file is touched: an unattributed actor, and a sample
    source that names no normalized record - a style file naming a record
    that does not exist would make every later ``brief`` fail.
    """
    if not actor.name.strip() or not actor.email.strip():
        raise StyleError(
            "cannot write the writing style: an author act must be attributed - "
            "actor name and email may not be empty"
        )
    style = normalize_style(style)
    for source_id in style.sample_sources:
        try:
            records.load(repository, source_id)
        except records.ReadError as exc:
            raise StyleError(f"sample source {source_id}: {exc}") from exc
    content = style_to_markdown(style)
    if token is None:
        return write.create(repository, STYLE_RELATIVE_PATH, content, actor)
    return write.write(repository, STYLE_RELATIVE_PATH, token, content, actor)


def is_empty(style: WritingStyle | None) -> bool:
    return style is None or (not style.direction and not style.observations)


def writing_style_prompt(style: WritingStyle | None) -> str | None:
    """The style as the text a writing agent receives - the one rendering
    every server of it uses. ``None`` when there is nothing to say, so a
    caller prints nothing rather than an empty heading."""
    if is_empty(style):
        return None
    assert style is not None
    lines = ["# Writing style", ""]
    if style.direction:
        lines += [style.direction, ""]
    if style.observations:
        lines += ["Observed in the author's own writing. Follow each:", ""]
        lines += [f"- {observation}" for observation in style.observations]
    return "\n".join(lines).rstrip("\n")


# --- uploaded samples -----------------------------------------------------------


@dataclass(frozen=True)
class UploadedSample:
    """One document the author uploaded for its style alone."""

    path: str
    title: str
    original_file: str
    paragraphs: tuple[str, ...]


_SAMPLE_FIELDS = ("title", "original_file")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

# Which converter reads which upload. ``.docx`` and ``.pdf`` need the
# ``convert`` extra; ``normalize`` imports those libraries inside the
# converter, so the ImportError surfaces here as a ``StyleError`` the
# surface can show, and the core stays importable without them.
_CONVERTERS = {
    ".txt": normalize.convert_plain_text,
    ".md": normalize.convert_plain_text,
    ".docx": normalize.convert_docx,
    ".pdf": normalize.convert_pdf,
}


def sample_slug(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = _SLUG_STRIP.sub("-", stem).strip("-")
    return slug or "sample"


def _sample_to_markdown(sample: UploadedSample) -> str:
    frontmatter = {"title": sample.title, "original_file": sample.original_file}
    return (
        "---\n"
        + yaml.safe_dump(frontmatter, sort_keys=False)
        + "---\n\n"
        + "\n\n".join(sample.paragraphs)
        + "\n"
    )


def _parse_sample(text: str, path: str) -> UploadedSample:
    if not text.startswith("---\n"):
        raise StyleError(f"{path}: not a style sample - no frontmatter")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise StyleError(f"{path}: frontmatter is not terminated")
    try:
        frontmatter = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise StyleError(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise StyleError(f"{path}: frontmatter is not a mapping")
    body = text[end + len("\n---\n") :].strip()
    paragraphs = tuple(p.strip() for p in normalize._BLANK_LINE.split(body) if p.strip())
    return UploadedSample(
        path=path,
        title=str(frontmatter.get("title") or Path(path).stem),
        original_file=str(frontmatter.get("original_file") or ""),
        paragraphs=paragraphs,
    )


def list_samples(repository: Repository) -> list[UploadedSample]:
    """Every uploaded sample, in path order."""
    directory = repository.root / SAMPLES_RELATIVE_DIR
    if not directory.is_dir():
        return []
    return [
        _parse_sample(
            path.read_text(encoding="utf-8"),
            f"{SAMPLES_RELATIVE_DIR}/{path.name}",
        )
        for path in sorted(directory.glob("*.md"))
    ]


def add_sample(
    repository: Repository, filename: str, data: bytes, actor: Actor
) -> WriteResult:
    """Bring one uploaded document in as a style sample.

    Converted with the same converters ``memoria normalize`` uses, so a
    ``.docx`` or ``.pdf`` reads the same way here as it would as evidence -
    but it is written under ``style/samples/``, not ``sources/``, and gets no
    id: it is not evidence and never will be. ``write.create`` refuses a
    name already taken (``Rejected(outcome="exists")``) rather than
    overwriting.
    """
    if not actor.name.strip() or not actor.email.strip():
        raise StyleError(
            "cannot add a style sample: an author act must be attributed - "
            "actor name and email may not be empty"
        )
    suffix = Path(filename).suffix.lower()
    converter = _CONVERTERS.get(suffix)
    if converter is None:
        raise StyleError(
            f"cannot add {filename!r} as a style sample: only "
            + ", ".join(sorted(_CONVERTERS))
            + " are supported"
        )
    try:
        draft = converter(data)
    except ImportError as exc:
        raise StyleError(
            f"cannot convert {filename!r}: the converter for {suffix} is not "
            "installed - install the `convert` extra (pip install -e '.[convert]')"
        ) from exc
    except Exception as exc:  # a corrupt upload - the converter's own message
        raise StyleError(f"cannot convert {filename!r}: {exc}") from exc
    paragraphs = tuple(p for p in draft.paragraphs if not records.is_page_marker(p))
    if not paragraphs:
        raise StyleError(f"cannot add {filename!r} as a style sample: it holds no text")
    sample = UploadedSample(
        path=f"{SAMPLES_RELATIVE_DIR}/{sample_slug(filename)}.md",
        title=Path(filename).stem,
        original_file=Path(filename).name,
        paragraphs=paragraphs,
    )
    return write.create(repository, sample.path, _sample_to_markdown(sample), actor)


# --- the analysis: serve, then record -----------------------------------------


STYLE_ANALYSIS_PROMPT = """\
# Analysing a writing style

You are reading samples of one author's own writing, in order to describe
how they write - not what they wrote about, and not whether it is good. The
description will be handed to a writing agent drafting prose in this
author's book, so every observation must be something a writer can act on.

Read all of the samples first. Then write between eight and fifteen
observations. Cover, where the samples give you grounds:

- sentence length and rhythm - long or short, varied or even, where the
  weight of a sentence falls;
- diction and register - plain or ornate, formal or conversational, the
  kind of word reached for and the kind avoided;
- person and tense, and how steadily they are held;
- paragraphing - how long a paragraph runs and what makes the author break;
- punctuation habits - dashes, semicolons, parentheses, fragments, lists;
- imagery and figures of speech, and how often they appear;
- humour, irony, understatement, and where they are permitted;
- how time is handled - dates, sequence, looking back versus staying in the
  moment;
- how other people are brought in - named, quoted, paraphrased, judged;
- what the author does not do, when that is as telling as what they do.

Each observation has three parts:

- `aspect` - which of the above it concerns, in a word or two;
- `observation` - the observation itself, written as a directive in the
  second person, one or two sentences: "Keep sentences short and end them
  on the concrete noun", not "The author's sentences are short";
- `example` - a passage quoted **verbatim from the samples** that shows it,
  long enough to show the habit and no longer. The example must occur in
  the samples exactly as you quote it; one that does not is refused.

Do not describe the subject matter. Do not infer facts about the author's
life. Do not recommend changes: you are describing the style that exists so
that it can be kept, and the author will confirm or correct every
observation before it is used.
"""


@dataclass(frozen=True)
class Sample:
    """One sample as the brief serves it: a chosen source (``ref`` is its
    ``SRC-`` id) or an uploaded document (``ref`` is its path)."""

    ref: str
    title: str
    text: str
    truncated: bool = False


@dataclass(frozen=True)
class Brief:
    """Everything one analysis needs: the prompt, the samples, what the
    style already says, and the key the recorded observations are filed
    under."""

    prompt: str
    samples: tuple[Sample, ...]
    current: WritingStyle | None
    analysis_key: str


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def analysis_key(samples: tuple[Sample, ...]) -> str:
    """One digest over the prompt and the served samples, in served order."""
    parts = [ANALYSIS_KEY_VERSION, _h(STYLE_ANALYSIS_PROMPT)]
    for sample in samples:
        parts += [sample.ref, _h(sample.text)]
    return _h("\n".join(parts))


def sample_texts(repository: Repository, style: WritingStyle | None) -> tuple[Sample, ...]:
    """The samples an analysis reads: the chosen sources first, then every
    uploaded document."""
    samples: list[Sample] = []
    for source_id in (style.sample_sources if style else ()):
        try:
            record = records.load(repository, source_id)
        except records.ReadError as exc:
            raise StyleError(f"sample source {source_id}: {exc}") from exc
        paragraphs = records.real_paragraphs(record)
        truncated = len(paragraphs) > SAMPLE_PARAGRAPH_LIMIT
        text = "\n\n".join(paragraphs[:SAMPLE_PARAGRAPH_LIMIT])
        title = record.subject or record.original_locator or record.original_file
        samples.append(Sample(ref=source_id, title=title, text=text, truncated=truncated))
    for uploaded in list_samples(repository):
        samples.append(
            Sample(ref=uploaded.path, title=uploaded.title, text="\n\n".join(uploaded.paragraphs))
        )
    return tuple(samples)


def brief(repository: Repository) -> Brief:
    """The briefing for one analysis. Refuses to serve nothing: an analysis
    with no samples has nothing to read, and the answer is to choose some in
    Settings, not to guess."""
    style = load_style(repository)
    samples = sample_texts(repository, style)
    if not samples:
        raise StyleError(
            "no samples to analyse - choose sources or upload documents under "
            "Settings > Writing style first"
        )
    return Brief(
        prompt=STYLE_ANALYSIS_PROMPT,
        samples=samples,
        current=style,
        analysis_key=analysis_key(samples),
    )


def render_brief_prompt(served: Brief) -> str:
    """The instruction half of a brief: the analysis prompt verbatim, then
    what the style already says so nothing is proposed twice. The one
    rendering (ADR-0004, ADR-0009) the ``style_brief`` tool and a direct
    run's system block both serve."""
    lines = [served.prompt, "", "## What the style already says", ""]
    current = writing_style_prompt(served.current)
    if current is None:
        lines.append("Nothing yet - every observation is new.")
    else:
        lines += ["Do not repeat these; propose only what they do not already say.", "", current]
    return "\n".join(lines)


def render_brief_samples(served: Brief) -> str:
    """The sample half of a brief: every sample contiguous and unmodified,
    the same contract ``read`` keeps for evidence."""
    lines = [f"## The samples ({len(served.samples)})", ""]
    for sample in served.samples:
        lines += [f"### {sample.ref} - {sample.title}", ""]
        if sample.truncated:
            lines += [
                f"(the first {SAMPLE_PARAGRAPH_LIMIT} paragraphs; the source runs longer)",
                "",
            ]
        lines += [sample.text, ""]
    return "\n".join(lines).rstrip("\n")


@dataclass
class RecordedObservation:
    """One observation as the model sends it back."""

    aspect: str
    observation: str
    example: str


@dataclass(frozen=True)
class Observation:
    """One observation as the index holds it."""

    id: int
    aspect: str
    observation: str
    example: str
    status: str
    resolved_text: str | None = None


@dataclass(frozen=True)
class RecordOutcome:
    """Per-element outcomes of one recorded batch: the ids of the rows
    written, and each rejection with its reason."""

    accepted: tuple[int, ...]
    rejected: tuple[tuple[int, str], ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_observations(
    repository: Repository, results: list[RecordedObservation], key: str
) -> RecordOutcome:
    """Record one batch of proposed observations against the served brief.

    ``key`` is the ``analysis_key`` ``brief`` served. Between serving the
    brief and recording against it the author may have changed the chosen
    sources or uploaded a sample; the whole batch is refused when the key no
    longer matches, because the examples were checked and the rows would be
    filed against samples the model never read. The skill fetches the brief
    afresh and analyses the new samples.

    With the key confirmed, each element is accepted or rejected on its own.
    An element is refused for an empty field, or for an ``example`` that does
    not occur verbatim (whitespace-normalized) within a single served sample
    - the type cannot hold that rule, so the core does.

    A batch replaces the still-proposed rows under the same analysis key:
    running the analysis twice over the same samples is a second opinion,
    not a doubled list. Rows the author already confirmed or discarded are
    kept under any key.
    """
    served = brief(repository)
    if key != served.analysis_key:
        raise StyleError(
            "the samples changed since the brief was served: fetch style_brief "
            "again and analyse what it serves"
        )
    samples = [_one_line(sample.text) for sample in served.samples]
    accepted_rows: list[tuple[int, RecordedObservation]] = []
    rejected: list[tuple[int, str]] = []
    for ordinal, result in enumerate(results, start=1):
        aspect = _one_line(result.aspect)
        observation = _one_line(result.observation)
        example = _one_line(result.example)
        if not aspect or not observation or not example:
            rejected.append((ordinal, "aspect, observation and example are all required"))
            continue
        if not any(example in sample for sample in samples):
            rejected.append(
                (ordinal, f"example is not in a sample verbatim: {example[:60]!r}")
            )
            continue
        accepted_rows.append((ordinal, RecordedObservation(aspect, observation, example)))

    con = index.connect(repository)
    try:
        con.execute(
            "DELETE FROM style_observations WHERE analysis_key = ? AND status = 'proposed'",
            (served.analysis_key,),
        )
        now = _now()
        ids: list[int] = []
        for ordinal, row in accepted_rows:
            cursor = con.execute(
                "INSERT INTO style_observations "
                "(analysis_key, ordinal, aspect, observation, example, status, written_at) "
                "VALUES (?, ?, ?, ?, ?, 'proposed', ?)",
                (served.analysis_key, ordinal, row.aspect, row.observation, row.example, now),
            )
            ids.append(int(cursor.lastrowid))
        con.commit()
    finally:
        con.close()
    return RecordOutcome(accepted=tuple(ids), rejected=tuple(rejected))


def _row_to_observation(row) -> Observation:
    return Observation(
        id=int(row[0]),
        aspect=row[1],
        observation=row[2],
        example=row[3],
        status=row[4],
        resolved_text=row[5],
    )


_SELECT = (
    "SELECT id, aspect, observation, example, status, resolved_text "
    "FROM style_observations"
)


def pending_observations(repository: Repository) -> list[Observation]:
    """Every proposed observation the author has not yet acted on, oldest
    first - the order the Settings surface walks them in."""
    con = index.connect(repository)
    try:
        rows = con.execute(_SELECT + " WHERE status = 'proposed' ORDER BY id").fetchall()
    finally:
        con.close()
    return [_row_to_observation(row) for row in rows]


def get_observation(repository: Repository, observation_id: int) -> Observation:
    con = index.connect(repository)
    try:
        row = con.execute(_SELECT + " WHERE id = ?", (observation_id,)).fetchone()
    finally:
        con.close()
    if row is None:
        raise StyleError(f"no such observation: {observation_id}")
    return _row_to_observation(row)


def _resolve(repository: Repository, observation_id: int, status: str, text: str | None) -> None:
    con = index.connect(repository)
    try:
        con.execute(
            "UPDATE style_observations SET status = ?, resolved_text = ? WHERE id = ?",
            (status, text, observation_id),
        )
        con.commit()
    finally:
        con.close()


def confirm_observation(
    repository: Repository,
    observation_id: int,
    text: str | None,
    token: str | None,
    actor: Actor,
) -> WriteResult:
    """The author confirms one proposed observation - as proposed, or as
    ``text`` where they changed it - and it joins the style.

    The durable write comes first: the observation is appended to the style
    file through ``set_style`` and committed as the author's, and only a
    ``Written`` outcome marks the row confirmed. A stale token leaves both
    the file and the row exactly as they were.
    """
    observation = get_observation(repository, observation_id)
    if observation.status != "proposed":
        raise StyleError(
            f"observation {observation_id} is already {observation.status}"
        )
    confirmed = _one_line(text if text is not None else observation.observation)
    if not confirmed:
        raise StyleError("a confirmed observation may not be empty")
    current = load_style(repository) or WritingStyle()
    result = set_style(
        repository,
        WritingStyle(
            direction=current.direction,
            observations=(*current.observations, confirmed),
            sample_sources=current.sample_sources,
        ),
        token,
        actor,
    )
    if isinstance(result, Written):
        _resolve(repository, observation_id, "confirmed", confirmed)
    return result


def discard_observation(repository: Repository, observation_id: int) -> Observation:
    """The author discards one proposed observation. Nothing durable moves."""
    observation = get_observation(repository, observation_id)
    if observation.status != "proposed":
        raise StyleError(
            f"observation {observation_id} is already {observation.status}"
        )
    _resolve(repository, observation_id, "discarded", None)
    return get_observation(repository, observation_id)


@dataclass(frozen=True)
class StyleStatus:
    """What a session or a surface needs to know before doing anything."""

    exists: bool
    direction_set: bool
    observations: int
    sample_sources: int
    uploaded_samples: int
    proposed: int
    confirmed: int
    discarded: int


def status(repository: Repository) -> StyleStatus:
    style = load_style(repository)
    con = index.connect(repository)
    try:
        counts = dict(
            con.execute(
                "SELECT status, COUNT(*) FROM style_observations GROUP BY status"
            ).fetchall()
        )
    finally:
        con.close()
    return StyleStatus(
        exists=style is not None,
        direction_set=bool(style and style.direction),
        observations=len(style.observations) if style else 0,
        sample_sources=len(style.sample_sources) if style else 0,
        uploaded_samples=len(list_samples(repository)),
        proposed=int(counts.get("proposed", 0)),
        confirmed=int(counts.get("confirmed", 0)),
        discarded=int(counts.get("discarded", 0)),
    )


__all__ = [
    "ANALYSIS_KEY_VERSION",
    "Brief",
    "Observation",
    "RecordOutcome",
    "RecordedObservation",
    "Rejected",
    "SAMPLES_RELATIVE_DIR",
    "SAMPLE_PARAGRAPH_LIMIT",
    "STYLE_ANALYSIS_PROMPT",
    "STYLE_ID",
    "STYLE_RELATIVE_PATH",
    "Sample",
    "StyleError",
    "StyleStatus",
    "UploadedSample",
    "WritingStyle",
    "add_sample",
    "analysis_key",
    "brief",
    "confirm_observation",
    "discard_observation",
    "get_observation",
    "is_empty",
    "list_samples",
    "load_style",
    "normalize_style",
    "parse_style",
    "pending_observations",
    "record_observations",
    "sample_slug",
    "sample_texts",
    "serve_style",
    "set_style",
    "status",
    "style_to_markdown",
    "writing_style_prompt",
]
