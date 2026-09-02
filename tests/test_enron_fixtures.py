"""The Enron fixtures: what the email converter (#78) will have to handle.

These messages are structurally faithful to the EDRM Enron export and
textually invented - real bodies in that corpus carry named people's private
and medical details, and a committed file is forever. Provenance and the
recon findings behind each case are in ``docs/corpora/enron.md``.

The tests here assert the fixtures still exhibit the property each is named
for. Nothing converts them yet; that is #78. This is the contract those
fixtures are held to in the meantime, so a well-meaning tidy-up cannot quietly
remove the defect that makes them worth keeping.
"""

import base64
import email
import re
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "enron"

# ZL's production wrote this bare line into the header block. It has no colon,
# so the standard library reads it as the header/body separator and silently
# swallows every header below it (docs/corpora/enron.md, finding 1).
BOGUS_HEADER = re.compile(rb"^Microsoft Mail Internet Headers Version [\d.]+\r?\n", re.MULTILINE)


def _read(name):
    return (FIXTURES / f"{name}.eml").read_bytes()


def _repaired(name):
    return email.message_from_bytes(BOGUS_HEADER.sub(b"", _read(name), count=1))


def _body(message):
    if not message.is_multipart():
        part = message
    else:
        part = next(p for p in message.walk() if p.get_content_type() == "text/plain")
    return part.get_payload(decode=True).decode(part.get_content_charset() or "latin-1")


def test_every_fixture_uses_crlf_as_the_corpus_does():
    for path in sorted(FIXTURES.glob("*.eml")):
        raw = path.read_bytes()
        assert b"\r\n" in raw, path.name
        assert not re.search(rb"(?<!\r)\n", raw), f"{path.name} has a bare LF"


def test_the_stray_header_line_defeats_the_standard_library():
    """The finding the converter exists to survive, pinned as a test."""
    message = email.message_from_bytes(_read("plain"))

    assert message.defects, "the fixture no longer reproduces the defect"
    assert message.get("From") is None
    assert message.get("Subject") is None


def test_removing_that_one_line_recovers_every_header():
    message = _repaired("plain")

    assert not message.defects
    assert message.get("Subject").strip() == "Zonal congestion report"
    assert "Dana.Reyes@example.com" in message.get("From")


def test_every_body_carries_the_zl_attribution_footer():
    """Not the sender's words: #78 cuts it before the paragraph splitter."""
    for name in ("plain", "quoted-angle", "outlook-original-message",
                 "interleaved", "thread-parent", "thread-child", "attachment"):
        assert "EDRM Enron Email Data Set has been produced" in _body(_repaired(name)), name


def test_no_fixture_carries_a_reply_header():
    """`In-Reply-To` is absent from the whole corpus - finding 2."""
    for path in sorted(FIXTURES.glob("*.eml")):
        message = email.message_from_bytes(BOGUS_HEADER.sub(b"", path.read_bytes(), count=1))
        assert message.get("In-Reply-To") is None, path.name
        assert message.get("References") is None, path.name


def test_thread_index_makes_the_parent_recoverable():
    """The substitute for `In-Reply-To`: a reply appends five bytes."""
    def index(name):
        raw = _repaired(name).get("Thread-Index").strip()
        return base64.b64decode(raw + "=" * (-len(raw) % 4))

    parent, child = index("thread-parent"), index("thread-child")

    assert len(parent) == 22
    assert len(child) == 27
    assert child[:-5] == parent
    assert child[:22] == parent[:22], "same conversation"


def test_each_quoting_style_the_cut_rules_name_is_represented():
    assert re.search(r"^> > > ", _body(_repaired("quoted-angle")), re.MULTILINE)

    outlook = _body(_repaired("outlook-original-message"))
    assert "-----Original Message-----" in outlook
    assert re.search(r"^Sent: ", outlook, re.MULTILINE)

    # Interleaved: quoted line, the sender's answer, then quoting again. The
    # splitter keeps the sender's lines in order rather than cutting at the
    # first marker (part 05 §5.4).
    interleaved = _body(_repaired("interleaved"))
    assert len(re.findall(r"^> ", interleaved, re.MULTILINE)) == 2
    assert "No, it rotates." in interleaved


def test_the_attachment_fixture_is_multipart_with_a_named_file():
    message = _repaired("attachment")

    assert message.is_multipart()
    names = [part.get_filename() for part in message.walk() if part.get_filename()]
    assert names == ["western-load.xls"]


def test_the_fixtures_name_no_real_person_or_domain():
    """RFC 2606 reserved domain, invented people. Nothing to scrub."""
    for path in sorted(FIXTURES.glob("*.eml")):
        text = path.read_bytes().decode("iso-8859-1")
        assert "@enron.com" not in text.lower(), path.name
        for address in re.findall(r"[\w.+-]+@[\w.-]+", text):
            if address.endswith((".xls", ".eml")):
                continue
            assert address.endswith(("example.com", "corp.example.com")), (path.name, address)
