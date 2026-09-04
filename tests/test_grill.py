"""A new section from the app or from a grilling (ADR-0011): the committed
creation in ``memoria.manuscript``, the briefing ``memoria.grill`` serves,
the direct run in ``memoria.drivers`` against a scripted fake, and the
session run's write in ``memoria.authorship`` under two authorizations
from one turn.
"""

import json
import subprocess

import pytest

from memoria import authorship, drivers, grill, manuscript, style
from memoria.authorship import AuthorshipError, write_section_from_conversation
from memoria.index import build_index
from memoria.ledger import event_path
from memoria.model import ModelReply, ModelRequest, ModelUsage
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository
from memoria.subjects import write_builtin_subjects
from memoria.write import Actor, checkpoint

SESSION = "SES-20260904-1200-abcdef012345"
AUTHOR = Actor(name="Local Author", email="local@memoria.test")
PROSE = (
    "The deck went up unchanged, and nobody said a word about it.\n\n"
    "By evening the whole street had seen it.\n"
)


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _repo(tmp_path, *, paragraphs=("The deck went up unchanged.", "Nobody dared touch it.")):
    """A git repository with a book, one chapter holding one drafted and one
    planned section, one source, and a clean human-authored history."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Local Author")
    _git(tmp_path, "config", "user.email", "local@memoria.test")
    repository = Repository(root=tmp_path)
    write_builtin_subjects(repository)
    manuscript.create_book(repository, "A book about the street.")
    chapter = manuscript.create_chapter(repository, "The summer the deck went up.")
    first = manuscript.create_section(repository, chapter.number, "How it started.")
    (first.dir / "draft.md").write_text("It started with a plank.\n", encoding="utf-8")
    manuscript.create_section(repository, chapter.number, "What the neighbours said.")
    record = NormalizedRecord(
        id="SRC-000001",
        source_type="journal",
        recorded_date="Oct. 22.",
        event_date="Oct. 22.",
        date_confidence="exact",
        contemporaneous=True,
        original_file="raw/vol-01/text.txt",
        original_locator="Journal I",
        paragraphs=list(paragraphs),
    )
    write_normalized_records([record], tmp_path / NORMALIZED_RELATIVE_PATH)
    build_index(repository, [record])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return repository, chapter


def _messages(tmp_path) -> list[str]:
    return [m.strip() for m in _git(tmp_path, "log", "--format=%B%x00").split("\x00")[:-1]]


def _ledger(repository, session=SESSION):
    path = event_path(repository, session)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class FakeModel:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        answer = self.handler(request)
        if isinstance(answer, ModelReply):
            return answer
        return ModelReply(
            text=json.dumps(answer),
            stop_reason="end_turn",
            usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=3),
        )


# --- creation through the write path -------------------------------------------


def test_a_planned_section_is_appended_to_the_chapter_and_minted_but_not_written(tmp_path):
    repository, chapter = _repo(tmp_path)

    planned = manuscript.plan_section(repository, chapter.brief.id)

    assert planned.number == 3
    assert planned.brief_id == "SEC-0003"
    assert planned.dir == chapter.dir / "sections" / "03"
    assert not planned.path.exists()
    assert len(manuscript.list_sections(repository, chapter.number)) == 2


def test_planning_a_section_of_an_unknown_chapter_is_refused(tmp_path):
    repository, _ = _repo(tmp_path)
    with pytest.raises(manuscript.ManuscriptError, match="no such chapter"):
        manuscript.plan_section(repository, "CHP-0099")


def test_adding_a_section_and_its_draft_commits_each_as_the_actor(tmp_path):
    repository, chapter = _repo(tmp_path)
    before = len(_messages(tmp_path))

    planned = manuscript.plan_section(repository, chapter.brief.id)
    section = manuscript.add_section(repository, planned, "The evening the street saw it.", AUTHOR)
    relative = manuscript.add_draft(repository, section, PROSE, AUTHOR)

    assert section.brief.id == "SEC-0003"
    assert manuscript.parse_brief(section.path.read_text()).text == "The evening the street saw it."
    assert relative == "chapters/01/sections/03/draft.md"
    assert (tmp_path / relative).read_text() == PROSE
    messages = _messages(tmp_path)
    assert len(messages) == before + 2
    assert messages[1].startswith("write: chapters/01/sections/03/section.md")
    assert messages[0].startswith("write: chapters/01/sections/03/draft.md")
    # A human actor's write carries a change-id (ADR-0008), and is theirs.
    assert all("change-id:" in message for message in messages[:2])
    assert _git(tmp_path, "log", "-1", "--format=%an <%ae>").strip() == "Local Author <local@memoria.test>"
    assert _git(tmp_path, "status", "--porcelain").strip() == ""
    # The outline sees it, appended.
    assert [s.brief.id for s in manuscript.list_sections(repository, chapter.number)] == [
        "SEC-0001",
        "SEC-0002",
        "SEC-0003",
    ]


def test_a_draft_that_already_exists_is_not_overwritten(tmp_path):
    repository, chapter = _repo(tmp_path)
    first = manuscript.list_sections(repository, chapter.number)[0]
    with pytest.raises(manuscript.ManuscriptError, match="already exists"):
        manuscript.add_draft(repository, first, "Replacement.", AUTHOR)
    assert (first.dir / "draft.md").read_text() == "It started with a plank.\n"


def test_a_brief_from_prose_is_the_first_paragraph_shortened():
    assert manuscript.brief_from_prose(PROSE) == (
        "The deck went up unchanged, and nobody said a word about it."
    )
    long = "word " * 100
    derived = manuscript.brief_from_prose(long)
    assert len(derived) <= manuscript.BRIEF_FROM_PROSE_LIMIT
    assert derived.endswith("…")
    assert manuscript.brief_from_prose("\n\n  \n") == ""


# --- the briefing ----------------------------------------------------------------


def test_the_brief_carries_the_manuscript_around_the_new_section(tmp_path):
    repository, chapter = _repo(tmp_path)

    served = grill.brief(repository, chapter.brief.id)
    rendered = grill.render_brief(served)

    assert served.chapter_id == "CHP-0001"
    assert served.next_section_number == 3
    assert served.book_brief == "A book about the street."
    assert [n.id for n in served.neighbours] == ["SEC-0001", "SEC-0002"]
    assert [n.has_draft for n in served.neighbours] == [True, False]
    assert served.source is None
    assert served.served == ["CHP-0001"]
    assert rendered.startswith(grill.GRILL_PROMPT)
    assert "Section 1.3 of chapter CHP-0001" in rendered
    assert "A book about the street." in rendered
    assert "The summer the deck went up." in rendered
    assert "1.1 - SEC-0001 (drafted)" in rendered
    assert "1.2 - SEC-0002 (planned, no prose yet)" in rendered
    assert "No writing style is set." in rendered
    assert "opened from" not in rendered


def test_the_brief_carries_the_source_and_the_writing_style_when_there_are_any(tmp_path):
    repository, chapter = _repo(tmp_path)
    style.set_style(
        repository,
        style.WritingStyle(direction="Stay in the moment.", observations=(), sample_sources=()),
        None,
        AUTHOR,
    )

    served = grill.brief(repository, chapter.brief.id, "src-000001-p2")
    rendered = grill.render_brief(served)

    assert served.source is not None
    assert served.source.id == "SRC-000001"
    assert served.source.paragraph == 2
    assert served.source.truncated is False
    assert served.served == ["CHP-0001", "SRC-000001"]
    assert "Stay in the moment." in rendered
    assert "## The source this interview was opened from (SRC-000001)" in rendered
    assert "reading paragraph 2" in rendered
    assert "The deck went up unchanged.\n\nNobody dared touch it." in rendered


def test_a_long_source_is_bounded_and_says_so(tmp_path):
    many = [f"Paragraph {n}." for n in range(1, grill.SOURCE_PARAGRAPH_LIMIT + 5)]
    repository, chapter = _repo(tmp_path, paragraphs=many)

    served = grill.brief(repository, chapter.brief.id, "SRC-000001")

    assert served.source.truncated is True
    assert f"Paragraph {grill.SOURCE_PARAGRAPH_LIMIT}." in served.source.text
    assert f"Paragraph {grill.SOURCE_PARAGRAPH_LIMIT + 1}." not in served.source.text
    assert "the source runs longer" in grill.render_brief(served)


@pytest.mark.parametrize(
    "chapter_id, source_ref, message",
    [
        ("CHP-0099", None, "no such chapter"),
        ("CHP-0001", "SRC-000999", "SRC-000999"),
        ("CHP-0001", "SUB-people/bob", "not a source reference"),
        ("CHP-0001", "not a ref at all", "not a source reference"),
    ],
)
def test_an_unknown_chapter_or_source_is_refused(tmp_path, chapter_id, source_ref, message):
    repository, _ = _repo(tmp_path)
    with pytest.raises(grill.GrillError, match=message):
        grill.brief(repository, chapter_id, source_ref)


# --- the direct run -----------------------------------------------------------------


def _question(request):
    return {
        "done": False,
        "question": "What does the reader know by the end of this section?",
        "recommended_answer": "That the deck stayed - the street's silence is the point.",
        "brief": "",
        "draft": "",
    }


def test_the_first_turn_asks_and_puts_the_whole_briefing_in_front_of_the_model(tmp_path):
    repository, chapter = _repo(tmp_path)
    model = FakeModel(_question)

    run = drivers.run_grill(
        repository, model, SESSION, chapter_id=chapter.brief.id, source_ref="SRC-000001", turns=()
    )

    assert run.done is False
    assert run.question.startswith("What does the reader know")
    assert run.recommended_answer.startswith("That the deck stayed")
    assert run.brief == "" and run.draft == ""
    assert run.rejected == ()
    assert run.spend.calls == 1 and run.spend.model == "fake-model"
    (request,) = model.requests
    assert request.pass_name == "grill"
    assert request.schema == drivers.GRILL_SCHEMA
    assert request.system.startswith(grill.GRILL_PROMPT)
    assert "The deck went up unchanged." in request.system
    assert request.user == "The interview is starting. Ask your first question."
    # Served then spent: the briefing line names what entered the context,
    # the model_call line what it cost - and carries no `served` key.
    brief_line, call_line = _ledger(repository)
    assert brief_line["tool"] == "grill_brief"
    assert brief_line["served"] == ["CHP-0001", "SRC-000001"]
    assert call_line["tool"] == "model_call"
    assert call_line["pass"] == "grill"
    assert "served" not in call_line


def test_the_transcript_is_the_clients_and_goes_back_whole(tmp_path):
    repository, chapter = _repo(tmp_path)
    model = FakeModel(
        lambda request: {
            "done": True,
            "question": "",
            "recommended_answer": "",
            "brief": "The evening the street saw the deck.",
            "draft": PROSE.strip(),
        }
    )
    turns = (
        drivers.GrillTurn("interviewer", "What does the reader know by the end?"),
        drivers.GrillTurn("author", "That the deck stayed."),
        drivers.GrillTurn("interviewer", "Where does it open?"),
        drivers.GrillTurn("author", "On the street at dusk. Write it now."),
    )

    run = drivers.run_grill(
        repository, model, SESSION, chapter_id=chapter.brief.id, source_ref=None, turns=turns
    )

    assert run.done is True
    assert run.brief == "The evening the street saw the deck."
    assert run.draft == PROSE.strip()
    assert run.question == "" and run.recommended_answer == ""
    (request,) = model.requests
    assert request.user.index("### Interviewer") < request.user.index("### Author")
    assert "That the deck stayed." in request.user
    assert "Write it now." in request.user
    # Nothing was written: the draft is the author's to edit and write. (The
    # ledger under sessions/ is interaction record, untracked by design.)
    assert len(manuscript.list_sections(repository, chapter.number)) == 2
    assert _git(tmp_path, "status", "--porcelain", "--", "chapters").strip() == ""


@pytest.mark.parametrize(
    "answer, reason",
    [
        (
            ModelReply(
                text="", stop_reason="refusal",
                usage=ModelUsage(model="fake-model", input_tokens=7, output_tokens=0),
                refusal="no",
            ),
            "refused",
        ),
        ({"done": True, "question": "", "recommended_answer": "", "brief": "b", "draft": ""}, "drafted nothing"),
        ({"done": False, "question": "", "recommended_answer": "", "brief": "", "draft": ""}, "asked nothing"),
        ({"done": "yes", "question": "q", "recommended_answer": "", "brief": "", "draft": ""}, "not a boolean"),
    ],
)
def test_a_reply_the_run_cannot_use_is_one_rejection_and_still_spend(tmp_path, answer, reason):
    repository, chapter = _repo(tmp_path)
    model = FakeModel(lambda request: answer)

    run = drivers.run_grill(
        repository, model, SESSION, chapter_id=chapter.brief.id, source_ref=None, turns=()
    )

    assert run.done is False
    assert run.question == run.draft == ""
    (rejection,) = run.rejected
    assert rejection.anchor == "interview"
    assert reason in rejection.reason
    assert run.spend.calls == 1


# --- the session run's write ----------------------------------------------------------


def test_a_section_from_a_conversation_is_two_commits_under_two_authorizations(tmp_path):
    repository, chapter = _repo(tmp_path)

    written = write_section_from_conversation(
        repository,
        chapter.brief.id,
        "The evening the street saw the deck.",
        PROSE,
        session_id=SESSION,
        turn=17,
    )

    assert written.section_id == "SEC-0003"
    assert written.brief.path == "chapters/01/sections/03/section.md"
    assert written.draft.path == "chapters/01/sections/03/draft.md"
    assert written.brief.authorized_by == written.draft.authorized_by == f"{SESSION}#T017"
    section = manuscript.resolve_section(repository, "SEC-0003")
    assert section.brief.text == "The evening the street saw the deck."
    assert section.brief.unconfirmed is False
    assert (section.dir / "draft.md").read_text() == PROSE
    draft_message, brief_message = _messages(tmp_path)[:2]
    assert f"authorized-by: {SESSION}#T017" in brief_message
    assert "authorized-scope: SEC-0003 brief" in brief_message
    assert f"authorized-by: {SESSION}#T017" in draft_message
    assert "authorized-scope: SEC-0003 draft" in draft_message
    # An AI write: no change-id, and the machine actor.
    assert "change-id:" not in brief_message and "change-id:" not in draft_message
    assert _git(tmp_path, "log", "-1", "--format=%an").strip() == authorship.WRITER.name


def test_a_conversation_write_checkpoints_the_authors_outside_edits_first(tmp_path):
    repository, chapter = _repo(tmp_path)
    first = manuscript.list_sections(repository, chapter.number)[0]
    (first.dir / "draft.md").write_text("Edited in Obsidian.\n", encoding="utf-8")

    write_section_from_conversation(
        repository, chapter.brief.id, "Brief.", "Prose.", session_id=SESSION, turn=2
    )

    messages = _messages(tmp_path)
    assert any("change-id:" in m and "write:" not in m for m in messages[:3])
    assert _git(tmp_path, "status", "--porcelain").strip() == ""


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(chapter_id="CHP-0099"), "no such chapter"),
        (dict(session_id="not-a-session"), "not a citable session"),
        (dict(turn=0), "1-based"),
        (dict(brief_text="   "), "needs its brief"),
        (dict(draft="\n"), "needs its prose"),
    ],
)
def test_a_conversation_write_that_cannot_be_authorized_writes_nothing(tmp_path, kwargs, message):
    repository, chapter = _repo(tmp_path)
    arguments = dict(
        chapter_id=chapter.brief.id, brief_text="Brief.", draft="Prose.", session_id=SESSION, turn=3
    )
    arguments.update(kwargs)

    with pytest.raises(AuthorshipError, match=message):
        write_section_from_conversation(
            repository,
            arguments["chapter_id"],
            arguments["brief_text"],
            arguments["draft"],
            session_id=arguments["session_id"],
            turn=arguments["turn"],
        )

    assert len(manuscript.list_sections(repository, chapter.number)) == 2
    assert _git(tmp_path, "status", "--porcelain").strip() == ""
