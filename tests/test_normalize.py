"""``memoria normalize``: the skip-unchanged normalization run (part 05 §5.4)."""

import mailbox
from email.message import EmailMessage

from memoria.index import build_index, search
from memoria.manifest import DEFAULT_MANIFEST_RELATIVE_PATH
from memoria.normalize import CONVERTERS, EMAIL_CONVERTER_VERSION, normalize
from memoria.records import NORMALIZED_RELATIVE_PATH, record_to_markdown, read_all
from memoria.repository import Repository
from memoria.validate import validate


def _write_raw_file(evidence_root, rel_path, content):
    full = evidence_root / "raw" / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return full


def _email_message(
    *, from_, to, date, message_id, body, cc=None, in_reply_to=None, attachment=None
):
    message = EmailMessage()
    message["From"] = from_
    message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Date"] = date
    message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    message.set_content(body)
    if attachment is not None:
        filename, content_bytes = attachment
        message.add_attachment(
            content_bytes,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )
    return message


def _write_mbox(evidence_root, rel_path, messages):
    full = evidence_root / "raw" / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    box = mailbox.mbox(str(full))
    for message in messages:
        box.add(message)
    box.flush()
    box.close()
    return full


def test_normalize_converts_a_new_plain_text_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "First paragraph.\n\nSecond paragraph.")
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    assert report.added_units == ["SRC-000001"]
    assert report.converted == ["SRC-000001"]
    assert report.skipped == []

    (record,) = read_all(repository)
    assert record.id == "SRC-000001"
    assert record.paragraphs == ["First paragraph.", "Second paragraph."]
    assert record.original_file == "raw/a.txt"
    assert record.converter == CONVERTERS[".txt"][1]
    assert len(record.raw_sha256) == 64


def test_a_run_over_unchanged_input_produces_no_diff(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "Hello.\n\nWorld.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    record_path = repository.root / NORMALIZED_RELATIVE_PATH / "SRC-000001.md"
    before = record_path.read_bytes()

    report = normalize(repository, evidence_root)

    after = record_path.read_bytes()
    assert before == after
    assert report.converted == []
    assert report.skipped == ["SRC-000001"]


def test_a_new_unit_that_sorts_before_existing_ones_renumbers_nothing(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "m.txt", "Middle file.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    _write_raw_file(evidence_root, "a.txt", "Alphabetically first.")
    report = normalize(repository, evidence_root)

    records = {r.original_file: r.id for r in read_all(repository)}
    assert records["raw/m.txt"] == "SRC-000001"
    assert records["raw/a.txt"] == "SRC-000002"
    assert report.added_units == ["SRC-000002"]
    assert report.converted == ["SRC-000002"]


def test_deleting_a_raw_unit_leaves_its_number_reserved_and_skips_it(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "Gone soon.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    path_a.unlink()
    _write_raw_file(evidence_root, "b.txt", "New arrival.")
    report = normalize(repository, evidence_root)

    records = {r.original_file: r.id for r in read_all(repository)}
    assert records["raw/b.txt"] == "SRC-000002"
    # The deleted unit's record is untouched; its ID was never reassigned.
    assert "SRC-000001.md" in [
        p.name for p in (repository.root / NORMALIZED_RELATIVE_PATH).glob("*.md")
    ]
    assert report.added_units == ["SRC-000002"]


def test_a_changed_raw_hash_reconverts_only_that_unit(tmp_path):
    evidence_root = tmp_path / "evidence"
    path_a = _write_raw_file(evidence_root, "a.txt", "Original.")
    _write_raw_file(evidence_root, "b.txt", "Unchanged.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    path_a.write_text("Changed content.")
    report = normalize(repository, evidence_root)

    assert report.converted == ["SRC-000001"]
    assert report.skipped == ["SRC-000002"]
    records = {r.id: r for r in read_all(repository)}
    assert records["SRC-000001"].paragraphs == ["Changed content."]


def test_a_changed_converter_version_reconverts_the_unit(tmp_path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "Content.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    from memoria import normalize as normalize_module

    monkeypatch.setitem(
        normalize_module.CONVERTERS,
        ".txt",
        (normalize_module.convert_plain_text, "plain-text 2"),
    )
    report = normalize(repository, evidence_root)

    assert report.converted == ["SRC-000001"]
    (record,) = read_all(repository)
    assert record.converter == "plain-text 2"


def test_all_forces_every_unit_to_reconvert(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "One.")
    _write_raw_file(evidence_root, "b.txt", "Two.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)

    report = normalize(repository, evidence_root, force_all=True)

    assert sorted(report.converted) == ["SRC-000001", "SRC-000002"]
    assert report.skipped == []


def test_reconverting_with_force_all_is_still_byte_identical(tmp_path):
    """The real idempotence check: forcing a reconversion of unchanged input
    must reproduce exactly the same bytes, not merely be skipped. A
    skip-path-only byte-identity test would pass even if the converter or
    the serializer were nondeterministic, since it would never re-run
    either of them on unchanged input."""
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.txt", "One.\n\nTwo.")
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    record_path = repository.root / NORMALIZED_RELATIVE_PATH / "SRC-000001.md"
    before = record_path.read_bytes()

    report = normalize(repository, evidence_root, force_all=True)

    assert report.converted == ["SRC-000001"]
    assert record_path.read_bytes() == before


def test_a_unit_with_no_registered_converter_is_reported_but_not_converted(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_raw_file(evidence_root, "a.docx", "not really a docx")
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    assert report.added_units == ["SRC-000001"]
    assert report.unconvertible == ["SRC-000001"]
    assert report.converted == []
    assert read_all(repository) == []


# --- email: a message is a raw unit finer than the file (#78) -------------


def test_mbox_thread_yields_three_records_with_a_shared_thread_and_a_reply_chain(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="Kickoff message.",
            ),
            _email_message(
                from_="bob@example.com", to="alice@example.com",
                date="Mon, 17 Oct 2011 10:00:00 -0500", message_id="<m2@x>",
                in_reply_to="<m1@x>", body="First reply.",
            ),
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 11:00:00 -0500", message_id="<m3@x>",
                in_reply_to="<m2@x>", body="Second reply.",
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")

    normalize(repository, evidence_root)

    records = read_all(repository)
    assert len(records) == 3
    assert len({r.id for r in records}) == 3
    assert len({r.thread_id for r in records}) == 1
    assert all(r.source_type == "email" for r in records)
    by_body = {r.paragraphs[0]: r for r in records}
    assert by_body["Kickoff message."].in_reply_to == ""
    assert by_body["First reply."].in_reply_to == by_body["Kickoff message."].id
    assert by_body["Second reply."].in_reply_to == by_body["First reply."].id


def test_a_reply_quoting_its_parent_drops_the_quote_and_search_hits_the_parent_only(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="The quokka statistic belongs only to this message.",
            ),
            _email_message(
                from_="bob@example.com", to="alice@example.com",
                date="Mon, 17 Oct 2011 10:00:00 -0500", message_id="<m2@x>",
                in_reply_to="<m1@x>",
                body=(
                    "Sounds good.\n\n"
                    "On Mon, Oct 17, 2011, alice@example.com wrote:\n"
                    "> The quokka statistic belongs only to this message."
                ),
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    records = read_all(repository)
    build_index(repository, records)

    reply = next(r for r in records if r.paragraphs == ["Sounds good."])
    assert reply.quoted_excised is True

    results = search(repository, "quokka")
    assert len(results) == 1
    assert results[0].src_id != reply.id


def test_an_interleaved_reply_keeps_sender_lines_in_order_and_drops_quote_markers(tmp_path):
    evidence_root = tmp_path / "evidence"
    interleaved_body = (
        "> Original point one.\n"
        "Agreed on point one.\n"
        "> Original point two.\n"
        "Disagree on point two."
    )
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="Original point one.\n\nOriginal point two.",
            ),
            _email_message(
                from_="bob@example.com", to="alice@example.com",
                date="Mon, 17 Oct 2011 10:00:00 -0500", message_id="<m2@x>",
                in_reply_to="<m1@x>", body=interleaved_body,
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")

    normalize(repository, evidence_root)

    reply = next(r for r in read_all(repository) if r.in_reply_to)
    assert reply.quoted_excised is True
    assert reply.paragraphs == ["Agreed on point one.\nDisagree on point two."]


def test_a_spreadsheet_attachment_is_listed_stored_and_gets_no_record(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="See the attached budget.",
                attachment=("budget.xlsx", b"pretend-spreadsheet-bytes"),
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    (record,) = read_all(repository)
    assert record.attachments == [{"filename": "budget.xlsx", "type": "xlsx"}]

    attachment_path = evidence_root / "raw" / "thread.mbox.attachments" / "0000-00-budget.xlsx"
    assert attachment_path.is_file()
    assert attachment_path.read_bytes() == b"pretend-spreadsheet-bytes"
    # The container (thread.mbox) and the attachment file both get reserved
    # IDs but no record of their own.
    assert len(report.unconvertible) == 2


def test_email_headers_are_in_frontmatter_and_never_in_the_body(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com", cc="carol@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="Body text only.",
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")

    normalize(repository, evidence_root)

    (record,) = read_all(repository)
    assert record.email_from == "alice@example.com"
    assert record.email_to == "bob@example.com"
    assert record.email_cc == "carol@example.com"
    assert record.paragraphs == ["Body text only."]

    markdown = record_to_markdown(record)
    assert "from: alice@example.com" in markdown
    for header_value in ("alice@example.com", "bob@example.com", "carol@example.com"):
        assert header_value not in "\n".join(record.paragraphs)


def test_converting_the_same_mbox_fixture_twice_is_byte_identical(tmp_path):
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="One.\n\nTwo.",
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")
    normalize(repository, evidence_root)
    (record_path,) = (repository.root / NORMALIZED_RELATIVE_PATH).glob("SRC-*.md")
    before = record_path.read_bytes()

    report = normalize(repository, evidence_root)

    assert record_path.read_bytes() == before
    assert report.converted == []
    (skipped_record,) = read_all(repository)
    assert report.skipped == [skipped_record.id]
    assert skipped_record.converter == EMAIL_CONVERTER_VERSION


def test_normalized_email_corpus_passes_validate(tmp_path):
    """Regression: a message entry shares its `path` with the export file
    (`_process_email_containers`'s docstring), and `validate`'s per-entry
    hash check used to hash that shared path against the message's own
    (different) `sha256`, failing every email record it validated."""
    evidence_root = tmp_path / "evidence"
    _write_mbox(
        evidence_root,
        "thread.mbox",
        [
            _email_message(
                from_="alice@example.com", to="bob@example.com",
                date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<m1@x>",
                body="Kickoff message.",
                attachment=("budget.xlsx", b"pretend-spreadsheet-bytes"),
            ),
            _email_message(
                from_="bob@example.com", to="alice@example.com",
                date="Mon, 17 Oct 2011 10:00:00 -0500", message_id="<m2@x>",
                in_reply_to="<m1@x>", body="First reply.",
            ),
        ],
    )
    repository = Repository(root=tmp_path / "repo")

    normalize(repository, evidence_root)

    assert validate(evidence_root, repo_root=repository.root) == []


def test_a_standalone_eml_file_converts_to_one_record(tmp_path):
    """A `.eml` file is an export holding exactly one message (part 05
    §5.4's "the standard library for mbox and .eml"): it goes through the
    same message-is-a-raw-unit handling as an `.mbox`, so it gets its own
    email record (and the file itself a reserved but record-less ID), with
    no parent to resolve `in_reply_to`/`thread_id` against but itself."""
    evidence_root = tmp_path / "evidence"
    eml_path = evidence_root / "raw" / "standalone.eml"
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    message = _email_message(
        from_="alice@example.com", to="bob@example.com",
        date="Mon, 17 Oct 2011 09:00:00 -0500", message_id="<standalone@x>",
        body="Standalone message body.",
    )
    eml_path.write_bytes(bytes(message))
    repository = Repository(root=tmp_path / "repo")

    report = normalize(repository, evidence_root)

    assert len(report.unconvertible) == 1  # the .eml file itself
    (record,) = read_all(repository)
    assert record.source_type == "email"
    assert record.paragraphs == ["Standalone message body."]
    assert record.in_reply_to == ""
    assert record.thread_id == "standalone@x"
