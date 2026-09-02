"""Transcript derivation from Claude Code's per-session JSONL (#28, part 04
§4, part 16 M4).

Memoria does not own the conversation loop (``poc-plan.md`` §3). Claude Code
writes its own per-session JSONL, with a uuid per message and a
``parentUuid`` chain linking each message to the one before it. This module
**derives** the human-readable session record from that JSONL as a
post-session pass:

- ``transcript.md`` - the conversation, one ``## T017 — Role`` block per
  turn, with the served-reads ledger (#13's ``events.jsonl``, already
  sitting in the same directory) folded in under each turn it served;
- ``metadata.yaml`` - the session id, when it started and ended, and the
  repository revision it was worked at.

**Turn numbers are positions in the reconstructed conversation, not in the
file.** The JSONL is a DAG, not a list: a resumed or edited session can carry
more than one root-to-leaf path, and entries unrelated to the visible
conversation (tool-result echoes, sidechains) share the same file. Numbering
by line position would make a turn's number depend on bytes nothing in the
conversation actually determines. Instead this walks the ``parentUuid``
chain from the session's own leaf back to its root - the one path that is
actually "what got said, in order" - and numbers only the entries on it that
carry visible text. That walk is a pure function of the JSONL's own uuids, so
it is stable across re-derivation of the same file (part 04 §4's "the #T
anchors ... anchor stability is therefore a hard requirement").

**Session records are immutable once derived** (part 04 §3): a second
derivation of the same session either reproduces ``transcript.md`` byte for
byte (a no-op) or is refused, naming the session, rather than silently
overwriting a citable record.

**A resumed session is a known gap, accepted.** Claude Code's ``--resume``
appends further turns to the *same* JSONL, while the Memoria session id
(``memoria.ledger``) is minted per MCP server process - a fresh one each time
a client reconnects. Deriving twice at different points in a growing file
therefore hits the immutability refusal above rather than an update. Nothing
in this build's acceptance criteria asks for a live-appending transcript,
and a completed session's JSONL does not grow after the fact, which is the
case this module is built for.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

from memoria.repository import Repository

METADATA_FILENAME = "metadata.yaml"
TRANSCRIPT_FILENAME = "transcript.md"

# Only these two JSONL entry types are turns at all; everything else (a
# `summary` entry from a compaction, for instance) is DAG scaffolding this
# module has no use for.
_ROLE_BY_TYPE = {"user": "Author", "assistant": "Assistant"}

# Structure is re-read from the rendered markdown, so structure and turn
# text must not be able to pass for each other. Every structural line - the
# anchor a heading is matched together with, the ledger's ``Served:`` line -
# opens with ``<``, and a turn's text is rendered with ``<`` (and ``&``, so
# the escape reverses exactly) as entities. A message whose own text carries
# a heading or a ``Served:`` line therefore cannot forge a turn boundary or
# lose its last paragraph to the ledger's stripping: what a ``#T`` citation
# resolves to is what that role actually said. The anchor tag is matched as
# part of the heading rather than on its own because it sits on the line
# *before* the next turn's heading, and a reader splitting on the heading
# alone would leak that next-turn anchor into the end of this turn's body.
_TURN_HEADING = re.compile(
    r'<a id="t\d+"></a>\n\n## T(?P<n>\d+) — (?P<role>Author|Assistant)'
)
_STRUCTURE_AFTER_BODY = re.compile(r"\n\n<")


class SessionError(Exception):
    """Raised when a session, or a turn of one, cannot be served or derived."""


@dataclass(frozen=True)
class Turn:
    """One rendered turn: its position in the reconstructed conversation,
    who spoke, what they said, and when - the last is what lets served reads
    be folded in by timestamp rather than by a field the JSONL does not
    carry."""

    number: int
    role: str
    text: str
    timestamp: str


@dataclass(frozen=True)
class DerivationResult:
    """What ``derive_session`` did, for a caller to report (cli.py's own
    ``_report_*`` idiom)."""

    session_id: str
    transcript_path: Path
    metadata_path: Path
    turns: int
    changed: bool


def session_dir(repository: Repository, session_id: str) -> Path:
    """Where this session's on-disk record lives - the directory
    ``events.jsonl`` already occupies (#13), which ``transcript.md`` and
    ``metadata.yaml`` land in beside it (part 04 §2).

    Local import: ``memoria.ledger`` imports ``memoria.index``, which
    imports ``memoria.records`` at the top level, which imports this module
    at the top level for the ``SES-`` dispatch in ``read()`` - importing
    ledger back here at module scope would cycle. The same shape
    ``memoria.records`` already uses for its own local import of
    ``memoria.index``.
    """
    from memoria.ledger import event_path

    return event_path(repository, session_id).parent


def transcript_path(repository: Repository, session_id: str) -> Path:
    return session_dir(repository, session_id) / TRANSCRIPT_FILENAME


def metadata_path(repository: Repository, session_id: str) -> Path:
    return session_dir(repository, session_id) / METADATA_FILENAME


def read_session(repository: Repository, session_id: str, turn: int | None = None) -> str:
    """Serve a session's transcript, whole or one turn of it.

    A bare reference returns ``transcript.md`` exactly as it is on disk -
    the same full-source contract ``memoria.records.read`` gives a chapter
    or a section. A turn reference returns just what was said in it,
    verbatim: the text between its heading and the first structural line
    after it (the ledger's ``Served:`` line, provenance rather than speech,
    or the next turn's anchor), with the rendering's entities undone.
    """
    path = transcript_path(repository, session_id)
    if not path.is_file():
        raise SessionError(f"no such session: {session_id}")
    text = path.read_text(encoding="utf-8")
    if turn is None:
        return text

    headings = list(_TURN_HEADING.finditer(text))
    for position, match in enumerate(headings):
        if int(match.group("n")) != turn:
            continue
        start = match.end()
        stop = headings[position + 1].start() if position + 1 < len(headings) else len(text)
        body = text[start:stop].strip("\n")
        structure = _STRUCTURE_AFTER_BODY.search(body)
        if structure is not None:
            body = body[: structure.start()]
        return html.unescape(body)
    raise SessionError(
        f"{session_id} has {len(headings)} turn(s); there is no T{turn:03d}"
    )


def derive_session(repository: Repository, session_id: str, jsonl_path: Path) -> DerivationResult:
    """Derive ``transcript.md`` and ``metadata.yaml`` for ``session_id`` from
    Claude Code's own per-session JSONL at ``jsonl_path``.

    Writes into the same directory ``events.jsonl`` for this session already
    lives in (or would, since a session's ledger and its transcript are the
    same interaction record, part 04 §3), so the two always agree on where a
    session lives. Refuses rather than overwrites when a prior derivation's
    ``transcript.md`` does not match this one byte for byte (see the module
    docstring on immutability); returns with ``changed=False`` when it
    matches exactly, which is the no-op re-derivation case.
    """
    entries = _load_entries(Path(jsonl_path))
    turns = _build_turns(entries)
    events = _load_events(repository, session_id)
    served_by_turn = _served_by_turn(events, turns)
    transcript_text = _render_transcript(turns, served_by_turn)

    directory = session_dir(repository, session_id)
    transcript_file = directory / TRANSCRIPT_FILENAME
    metadata_file = directory / METADATA_FILENAME

    if transcript_file.is_file():
        existing = transcript_file.read_text(encoding="utf-8")
        if existing != transcript_text:
            raise SessionError(
                f"{session_id}: {TRANSCRIPT_FILENAME} already exists and "
                "differs from this derivation - session records are "
                "immutable once derived (part 04 §3)"
            )
        return DerivationResult(session_id, transcript_file, metadata_file, len(turns), False)

    directory.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text(transcript_text, encoding="utf-8")
    metadata = {
        "session_id": session_id,
        "started": turns[0].timestamp if turns else None,
        "ended": turns[-1].timestamp if turns else None,
        "repo_revision": _current_revision(repository),
    }
    metadata_file.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    return DerivationResult(session_id, transcript_file, metadata_file, len(turns), True)


# --- Claude Code's JSONL, read -----------------------------------------------


def _load_entries(jsonl_path: Path) -> dict[str, dict]:
    """Every non-sidechain entry, keyed by its own ``uuid``.

    A sidechain entry (``isSidechain: true``) forks off the main
    conversation - a compaction summary, a subagent exchange - and never
    becomes an ancestor of anything back on it, so dropping it here is
    enough to keep the chain walk below on the one thread that is the
    visible conversation.
    """
    entries: dict[str, dict] = {}
    if not jsonl_path.is_file():
        raise SessionError(f"no such session transcript source: {jsonl_path}")
    for entry in _load_jsonl(jsonl_path):
        if entry.get("isSidechain"):
            continue
        uuid = entry.get("uuid")
        if uuid is None:
            continue
        entries[uuid] = entry
    return entries


def _load_jsonl(path: Path) -> list[dict]:
    """Every non-blank line of ``path`` parsed as JSON, or ``SessionError``
    naming the file and line that would not parse - a JSONL caught mid-append
    with a truncated last line, say. One error type crosses this module's
    boundary (the convention ``memoria.records.read`` states), so a caller
    that catches ``SessionError`` never sees ``json.JSONDecodeError``."""
    parsed = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SessionError(f"{path}: line {number} is not valid JSON ({exc})") from exc
    return parsed


def _build_turns(entries: dict[str, dict]) -> list[Turn]:
    """Reconstruct the conversation as one ordered list of turns.

    The chain is walked backward from the leaf - the one entry that is
    nobody's parent - because that is the entry a linear scan cannot find
    positionally: it is "whatever the conversation ended on", not "the last
    line in the file". Multiple candidate leaves (a resumed or edited
    session can leave more than one) are resolved by picking the one with
    the latest timestamp, which is the final state of the conversation
    rather than an abandoned branch.
    """
    if not entries:
        return []

    parents = {entry.get("parentUuid") for entry in entries.values()}
    leaves = [uuid for uuid in entries if uuid not in parents]
    if not leaves:
        # Every entry is somebody's parent - a cycle, which a well-formed
        # JSONL never produces. Nothing to render rather than an infinite
        # walk below.
        return []
    leaf = max(leaves, key=lambda uuid: (entries[uuid].get("timestamp") or "", uuid))

    chain: list[str] = []
    current: str | None = leaf
    seen: set[str] = set()
    while current is not None and current in entries and current not in seen:
        seen.add(current)
        chain.append(current)
        current = entries[current].get("parentUuid")
    chain.reverse()

    turns = []
    number = 0
    for uuid in chain:
        entry = entries[uuid]
        role = _ROLE_BY_TYPE.get(entry.get("type"))
        if role is None:
            continue
        text = _extract_text(entry.get("message"))
        if not text:
            # A tool-only turn (an assistant's tool call with no reply text,
            # or a user entry that is really a tool result echoed back) -
            # machine detail events.jsonl already covers, not conversation.
            continue
        number += 1
        turns.append(Turn(number=number, role=role, text=text, timestamp=entry.get("timestamp", "")))
    return turns


def _extract_text(message: object) -> str:
    """The spoken text of one message, dropping tool calls and results.

    ``content`` is a plain string for the simplest messages and a list of
    typed blocks otherwise (``{"type": "text", "text": ...}`` among
    ``tool_use``/``tool_result`` blocks this function is not interested in -
    the transcript is the human interface, the machine detail lives in
    ``events.jsonl``, part 04 §10.4).
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "").strip()
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n\n".join(part for part in parts if part)
    return ""


# --- the served-reads ledger, folded in --------------------------------------


def _load_events(repository: Repository, session_id: str) -> list[dict]:
    path = session_dir(repository, session_id) / "events.jsonl"
    if not path.is_file():
        return []
    return _load_jsonl(path)


def _served_by_turn(events: list[dict], turns: list[Turn]) -> dict[int, list[str]]:
    """Which turn each served read belongs to.

    ``events.jsonl`` carries no turn reference - it is written by the tool
    surface, which has no notion of one (#13) - only a timestamp. A read
    served between two turns was served while the model was producing the
    later one, so it is attributed to the first turn whose own timestamp is
    at or after the event's: the reply that read went into.
    """
    if not events or not turns:
        return {}
    boundaries = [_parse_timestamp(t.timestamp) for t in turns]
    served: dict[int, list[str]] = {}
    for event in events:
        at = _parse_timestamp(event.get("timestamp", ""))
        index = bisect_left(boundaries, at)
        turn_number = turns[index if index < len(turns) else -1].number
        bucket = served.setdefault(turn_number, [])
        for citation in event.get("served") or []:
            if citation not in bucket:
                bucket.append(citation)
    return served


def _parse_timestamp(value: str) -> datetime:
    """An ISO-8601 timestamp, whichever of Claude Code's or the ledger's own
    two spellings it comes in - a trailing ``Z`` (``memoria.ledger`` never
    writes one, but nothing says Claude Code's own JSONL will not) or an
    explicit offset (what ``ledger._append`` writes). An empty or unparsable
    value sorts first rather than raising, so one malformed timestamp cannot
    take the whole fold-in down."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


# --- rendering ----------------------------------------------------------------


def _render_transcript(turns: list[Turn], served_by_turn: dict[int, list[str]]) -> str:
    """One ``<a id="t017"></a>`` / ``## T017 — Role`` block per turn (part 04
    §4's own markdown-link example cites the lower-case anchor form), each
    followed by what it served, when it served anything.

    The turn's text has ``&`` and ``<`` rendered as entities (see
    ``_TURN_HEADING``): markdown shows them as typed, and ``read_session``
    reverses them, but no line of turn text can open with the ``<`` every
    structural line does."""
    blocks = []
    for turn in turns:
        heading = f'<a id="t{turn.number:03d}"></a>\n\n## T{turn.number:03d} — {turn.role}'
        blocks.append(f"{heading}\n\n{_escape_turn_text(turn.text)}")
        served = served_by_turn.get(turn.number)
        if served:
            blocks.append(f"<small>Served: {', '.join(served)}</small>")
    return "\n\n".join(blocks) + "\n"


def _escape_turn_text(text: str) -> str:
    """``&`` then ``<`` as entities - exactly the pair ``html.unescape``
    reverses without touching anything else, and the least alteration that
    keeps ``<`` out of the rendered text. ``>`` stays: a blockquote the
    author typed still renders as one."""
    return text.replace("&", "&amp;").replace("<", "&lt;")


def _current_revision(repository: Repository) -> str | None:
    """The repository's ``HEAD`` commit, or ``None`` when there is none to
    name - no git repository yet, or one with no commits. Soft-failing here
    rather than raising: the field it fills in is "enough context to
    understand what kind of interaction occurred" (part 04 §10.2), not
    something the derivation should fail over."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository.root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()
