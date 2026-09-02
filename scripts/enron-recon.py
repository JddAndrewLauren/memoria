#!/usr/bin/env python3
"""Measure a fetched Enron slice and write RECON.md next to it.

Read-only and deterministic: no network, no writes into the raw tree, same
numbers on every run. It exists for the reason the retired Thoreau corpus's
RECON.md did - a corpus is characterised before a converter is written
against it, and the counts here are what the email converter (#78) is later
checked against.

It answers the questions part 05 §5.2-§5.4 and
``docs/normalized-record-schema.md`` actually ask of an email export: can a
record carry ``thread_id`` and ``in_reply_to`` at all, what do the quoted-reply
cut rules have to handle, what attachments exist, and what does the text need
doing to it before a paragraph splitter sees it.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import collections
import email
import email.utils
import re
from dataclasses import dataclass, field
from datetime import timezone
from email.message import Message
from pathlib import Path

# ZL's production wrote a bare "Microsoft Mail Internet Headers Version 2.0"
# line into the middle of the header block. It has no colon, so the standard
# library treats it as the blank line that ends the headers and every header
# below it - From, To, Subject, Thread-Index, the X-ZL-* set - is silently
# read as body text instead. Stripping the line is what makes an otherwise
# well-formed message parse; the recon reports how many messages need it.
BOGUS_HEADER = re.compile(rb"^Microsoft Mail Internet Headers Version [\d.]+\r?\n", re.MULTILINE)

# Every body carries the CC-BY attribution ZL appended, fenced by asterisk
# rules. It is not the sender's words and must not become a paragraph.
ZL_FOOTER = re.compile(r"\*{6,}\s*\n\s*EDRM Enron Email Data Set has been produced", re.MULTILINE)

# The three cut rules part 05 §5.4 names. Interleaved replies - new text between
# quoted runs - are not detected here; that is #78's problem to measure.
QUOTE_MARKERS = {
    "angle-prefix": re.compile(r"^\s*>", re.MULTILINE),
    "on-wrote": re.compile(r"^\s*On .{0,120}\bwrote:\s*$", re.MULTILINE),
    "outlook-block": re.compile(r"^\s*-+\s*Original Message\s*-+\s*$|^From:.*\n(?:.*\n){0,3}?Sent:.*\n", re.MULTILINE),
}


@dataclass
class Custodian:
    """Everything the recon counts for one custodian."""

    name: str
    eml: int = 0
    bytes: int = 0
    needed_repair: int = 0
    still_defective: int = 0
    headers: collections.Counter = field(default_factory=collections.Counter)
    charsets: collections.Counter = field(default_factory=collections.Counter)
    quotes: collections.Counter = field(default_factory=collections.Counter)
    attachments: collections.Counter = field(default_factory=collections.Counter)
    attachment_types: collections.Counter = field(default_factory=collections.Counter)
    anomalies: collections.Counter = field(default_factory=collections.Counter)
    crlf: int = 0
    zl_footer: int = 0
    empty_body: int = 0
    dates: list = field(default_factory=list)
    sizes: list = field(default_factory=list)
    sidecars: collections.Counter = field(default_factory=collections.Counter)


@dataclass
class Msg:
    """One parsed message, reduced to what the reply graph needs."""

    custodian: str
    path: Path
    message_id: str
    thread_index: bytes | None
    sender: str
    recipients: tuple[str, ...]
    sender_text: str
    recipient_text: str
    subject: str


def parse(raw: bytes) -> tuple[Message, bool]:
    """Parse a message, repairing ZL's stray header line. Returns (msg, repaired)."""
    fixed = BOGUS_HEADER.sub(b"", raw, count=1)
    return email.message_from_bytes(fixed), fixed != raw


def body_text(msg: Message) -> str:
    part = msg
    if msg.is_multipart():
        for candidate in msg.walk():
            if candidate.get_content_type() == "text/plain":
                part = candidate
                break
        else:
            return ""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "latin-1"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("latin-1", errors="replace")


def addresses(msg: Message, header: str) -> tuple[str, ...]:
    """Addresses in one header.

    Filtered to strings containing an ``@``: many ``To`` headers in this export
    are unquoted ``Lastname, Firstname`` display names, which ``getaddresses``
    splits on the comma into two bare tokens. Left in, "robert" and "jeff"
    arrive as addresses and the correspondence table is fiction.
    """
    raw = msg.get_all(header) or []
    return tuple(a.lower() for _, a in email.utils.getaddresses(raw) if "@" in a)


def scan(root: Path) -> tuple[dict[str, Custodian], list[Msg]]:
    custodians: dict[str, Custodian] = {}
    messages: list[Msg] = []

    for custodian_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        c = Custodian(custodian_dir.name)
        custodians[c.name] = c

        for path in sorted(custodian_dir.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix != ".eml":
                c.sidecars[suffix or "(none)"] += 1
                continue

            raw = path.read_bytes()
            c.eml += 1
            c.bytes += len(raw)
            c.sizes.append(len(raw))
            if b"\r\n" in raw:
                c.crlf += 1
            msg, repaired = parse(raw)
            if repaired:
                c.needed_repair += 1
            if msg.defects:
                c.still_defective += 1

            for header in ("Message-ID", "Date", "From", "To", "Cc", "Subject",
                           "In-Reply-To", "References", "Thread-Index", "Thread-Topic",
                           "X-ZL-To"):
                if msg.get(header):
                    c.headers[header] += 1
            for header in ("From", "To"):
                if "@" in " ".join(msg.get_all(header) or []):
                    c.headers[f"{header} with an address"] += 1

            declared = (msg.get_content_charset() or "(unset)").lower()
            c.charsets[declared] += 1
            if declared != "(unset)":
                try:
                    codecs.lookup(declared)
                except LookupError:
                    c.anomalies["unknown charset"] += 1
            for part in msg.walk():
                if part.get_content_maintype() != "text":
                    continue
                payload = part.get_payload(decode=True) or b""
                try:
                    payload.decode("utf-8")
                except UnicodeDecodeError:
                    c.anomalies["body not valid UTF-8"] += 1
                    break

            for part in msg.walk():
                name = part.get_filename()
                if name:
                    c.attachments[Path(name).suffix.lower() or "(none)"] += 1
                if name or part.get_content_disposition() == "attachment":
                    c.attachment_types[part.get_content_type()] += 1

            text = body_text(msg)
            if ZL_FOOTER.search(text):
                c.zl_footer += 1
            stripped = ZL_FOOTER.split(text)[0].strip()
            if not stripped:
                c.empty_body += 1
            for label, pattern in QUOTE_MARKERS.items():
                if pattern.search(stripped):
                    c.quotes[label] += 1

            date_header = msg.get("Date")
            try:
                parsed_date = email.utils.parsedate_to_datetime(date_header) if date_header else None
            except (TypeError, ValueError):
                parsed_date = None
            if parsed_date is None:
                c.anomalies["no parseable Date"] += 1
            else:
                if not 1995 <= parsed_date.year <= 2003:
                    c.anomalies["Date outside 1995-2003"] += 1
                if parsed_date.tzinfo is None:
                    # A minority of Date headers carry no zone. Read them as
                    # UTC so the range is comparable, and say how many.
                    c.anomalies["Date without a timezone"] += 1
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                c.dates.append(parsed_date)

            message_id = (msg.get("Message-ID") or "").strip()
            if not message_id:
                c.anomalies["no Message-ID"] += 1
            if not msg.get("From"):
                c.anomalies["no From"] += 1

            thread_index = None
            raw_index = (msg.get("Thread-Index") or "").strip()
            if raw_index:
                try:
                    thread_index = base64.b64decode(raw_index + "=" * (-len(raw_index) % 4))
                except Exception:
                    c.anomalies["undecodable Thread-Index"] += 1

            messages.append(Msg(
                custodian=c.name,
                path=path,
                message_id=message_id,
                thread_index=thread_index,
                sender=(addresses(msg, "From") or ("",))[0],
                recipients=addresses(msg, "To") + addresses(msg, "Cc"),
                sender_text=" ".join(msg.get_all("From") or []).lower(),
                recipient_text=" ".join((msg.get_all("To") or []) + (msg.get_all("Cc") or [])).lower(),
                subject=(msg.get("Subject") or "").strip(),
            ))

    return custodians, messages


def reply_graph(messages: list[Msg]) -> dict:
    """What threading is recoverable, and how much of it crosses custodians.

    ``In-Reply-To`` is what part 05 §5.4 says resolves ``in_reply_to``. Where
    it is absent, Outlook's ``Thread-Index`` is the only other deterministic
    route: the first 22 bytes are the conversation, and each reply appends
    five bytes, so a message's parent is the message whose Thread-Index is its
    own minus the last five bytes.
    """
    by_index = {m.thread_index: m for m in messages if m.thread_index}
    conversations = collections.Counter(m.thread_index[:22] for m in messages if m.thread_index)

    resolved = cross = 0
    for m in messages:
        if not m.thread_index or len(m.thread_index) <= 22:
            continue
        parent = by_index.get(m.thread_index[:-5])
        if parent is not None:
            resolved += 1
            if parent.custodian != m.custodian:
                cross += 1

    duplicates = sum(n - 1 for n in collections.Counter(
        m.message_id for m in messages if m.message_id).values() if n > 1)

    # Who mails whom, custodian to custodian. A custodian's own address is the
    # one appearing most often across their mailbox - inbound and outbound
    # both name it - which is checkable, and printed, rather than guessed from
    # the directory slug.
    seen: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for m in messages:
        for address in ((m.sender,) if m.sender else ()) + m.recipients:
            seen[m.custodian][address] += 1
    def own_address(custodian: str, counts: collections.Counter) -> str:
        """The custodian's own address.

        Archives are named ``surname-initial``. The most frequent address in a
        mailbox is not reliably its owner's - a busy distribution list beats
        them - so prefer the most frequent address whose local part carries the
        surname, and fall back to sheer frequency only when none does.
        """
        surname = custodian.rsplit("-", 1)[0].replace("-", "")
        for address, _ in counts.most_common():
            local = address.split("@", 1)[0].replace(".", "").replace("-", "")
            if surname in local:
                return address
        return counts.most_common(1)[0][0]

    owner = {c: own_address(c, counts) for c, counts in seen.items() if counts}
    # One person has several addresses here - `robert.badeer@enron.com`,
    # `Robert Badeer@ECT`, an X.500 form - so matching an address to a
    # custodian by equality undercounts badly. Match on the surname in the
    # local part instead. That the corpus needs this at all is part 05 §7's
    # match-terms problem arriving in the raw data.
    surnames = {c: c.rsplit("-", 1)[0].replace("-", "") for c in owner}
    assert len(set(surnames.values())) == len(surnames), "two custodians share a surname"

    def named_in(text: str) -> set[str]:
        """Which custodians a header names, by address form or by bare name."""
        flat = text.replace(".", "").replace("-", "").replace(" ", "")
        return {c for c, surname in surnames.items() if surname in flat}

    edges: collections.Counter = collections.Counter()
    for m in messages:
        senders = named_in(m.sender_text)
        if len(senders) != 1:
            continue
        sender = senders.pop()
        for recipient in named_in(m.recipient_text):
            if recipient != sender:
                edges[(sender, recipient)] += 1

    return {
        "with_thread_index": len(by_index),
        "conversations": len(conversations),
        "in_multi_message_conversation": sum(n for n in conversations.values() if n > 1),
        "parent_present": resolved,
        "parent_in_another_custodian": cross,
        "duplicate_message_ids": duplicates,
        "internal_edges": edges,
        "owner": owner,
    }


def pct(n: int, total: int) -> str:
    return f"{100 * n / total:5.1f}%" if total else "    -"


def kb(sorted_sizes: list, quantile: float) -> str:
    """The size at ``quantile`` of an ascending list, in KB."""
    if not sorted_sizes:
        return "-"
    index = min(len(sorted_sizes) - 1, int(quantile * len(sorted_sizes)))
    return f"{sorted_sizes[index] / 1e3:,.1f} KB"


def render(custodians: dict[str, Custodian], graph: dict) -> str:
    total_eml = sum(c.eml for c in custodians.values())
    every_date = [d for c in custodians.values() for d in c.dates]
    out: list[str] = []
    w = out.append

    w("# Enron slice reconnaissance")
    w("")
    w("Generated by `scripts/enron-recon.py`. Read-only, deterministic, no network:")
    w("re-running it over the same slice produces the same file. Provenance and licence")
    w("are in `docs/corpora/enron.md`; the pins are in")
    w("`docs/corpora/enron-acquisition.yaml`.")
    w("")
    w(f"- Custodians: **{len(custodians)}**")
    w(f"- Messages (`.eml`): **{total_eml:,}**")
    w(f"- Bytes of `.eml`: **{sum(c.bytes for c in custodians.values()) / 1e6:,.1f} MB**")
    if every_date:
        w(f"- Date range: **{min(every_date).date()} to {max(every_date).date()}**")
    every_size = sorted(n for c in custodians.values() for n in c.sizes)
    if every_size:
        w(f"- Message size: min {every_size[0] / 1e3:,.1f} KB, median {kb(every_size, 0.5)}, "
          f"p90 {kb(every_size, 0.9)}, max {every_size[-1] / 1e3:,.1f} KB")
    w("")

    w("## Per custodian")
    w("")
    w("| custodian | .eml | MB | median KB | from | to | needs header repair | Thread-Index | Cc | quoted |")
    w("|---|---:|---:|---:|---|---|---:|---:|---:|---:|")
    for name, c in sorted(custodians.items()):
        quoted = max(c.quotes.values()) if c.quotes else 0
        span = f"{min(c.dates).date()} | {max(c.dates).date()}" if c.dates else "- | -"
        w(f"| {name} | {c.eml:,} | {c.bytes / 1e6:,.1f} | {kb(sorted(c.sizes), 0.5)} | {span} "
          f"| {pct(c.needed_repair, c.eml)} "
          f"| {pct(c.headers['Thread-Index'], c.eml)} | {pct(c.headers['Cc'], c.eml)} "
          f"| {pct(quoted, c.eml)} |")
    w("")

    w("## The header defect")
    w("")
    repair = sum(c.needed_repair for c in custodians.values())
    left = sum(c.still_defective for c in custodians.values())
    w(f"**{repair:,} of {total_eml:,} messages ({pct(repair, total_eml).strip()}) do not "
      "parse with the standard library as shipped.** ZL's production wrote a bare")
    w("`Microsoft Mail Internet Headers Version 2.0` line into the header block. It has")
    w("no colon, so `email.message_from_bytes` reads it as the header/body separator and")
    w("every header below it - `From`, `To`, `Subject`, `Thread-Index`, the `X-ZL-*`")
    w("set - is silently swallowed into the body. No exception is raised; the message")
    w("simply appears to have no sender.")
    w("")
    w("Deleting that one line is the whole fix, and it is what the counts below assume.")
    w(f"After it, **{left:,}** {'message' if left == 1 else 'messages'} still "
      f"{'carries' if left == 1 else 'carry'} a parse defect.")
    w("")
    w("Part 05 §5.4 says email parsing is Memoria's own, using the standard library.")
    w("That holds - but #78 needs this pre-pass, and a converter that skipped it would")
    w(f"lose the sender of {pct(repair, total_eml).strip()} of the corpus without failing.")
    w("")

    w("## Headers")
    w("")
    w("| header | present | of messages |")
    w("|---|---:|---:|")
    for header in ("Message-ID", "Date", "From", "From with an address", "To",
                   "To with an address", "Cc", "Subject", "In-Reply-To", "References",
                   "Thread-Index", "Thread-Topic", "X-ZL-To"):
        n = sum(c.headers[header] for c in custodians.values())
        name, _, qualifier = header.partition(" ")
        label = f"`{name}`" + (f" {qualifier}" if qualifier else "")
        w(f"| {label} | {n:,} | {pct(n, total_eml)} |")
    w("")

    with_from_address = sum(c.headers["From with an address"] for c in custodians.values())
    with_to_address = sum(c.headers["To with an address"] for c in custodians.values())
    zl_to = sum(c.headers["X-ZL-To"] for c in custodians.values())
    w("### Half the correspondents are named, not addressed")
    w("")
    w(f"`From` carries an actual address on **{with_from_address:,}** messages "
      f"({pct(with_from_address, total_eml).strip()}); `To` on **{with_to_address:,}** "
      f"({pct(with_to_address, total_eml).strip()}). The rest hold bare display names, "
      "comma-separated:")
    w("")
    w("```text")
    w("To: Tim Belden, Teri Whitcomb, Kathy Axford, Mitch McClintock")
    w("```")
    w("")
    w("So `from`/`to`/`cc` in `docs/normalized-record-schema.md` cannot be assumed to be")
    w("addresses, and the comma is ambiguous - `Belden, Tim` is one person written the")
    w("other way round, and the same header may mix both conventions. This is part 05 §7's")
    w("alias problem arriving in the headers rather than in the prose: resolving a")
    w("correspondent to a person is entry match-term work, not a parse. The converter")
    w("should keep the header verbatim and leave the resolution to the subject system.")
    w("")
    w(f"`X-ZL-To`, which carries X.500 distinguished names, is present on **{zl_to:,}** "
      f"({pct(zl_to, total_eml).strip()}) - not enough to fall back to.")
    w("")

    in_reply_to = sum(c.headers["In-Reply-To"] for c in custodians.values())
    w("### What this means for `in_reply_to` and `thread_id`")
    w("")
    w("`docs/normalized-record-schema.md` resolves `in_reply_to` \"from `Message-ID` /")
    w("`In-Reply-To` within the same export\", per part 05 §5.4.")
    w("")
    w(f"**`In-Reply-To` is present on {in_reply_to:,} of {total_eml:,} messages.** Enron ran")
    w("Exchange, and this export preserves Outlook's `Thread-Index` instead. That is a")
    w("deterministic substitute and not a heuristic: the first 22 bytes are the")
    w("conversation, and each reply appends exactly five, so a message's parent is the")
    w("message whose `Thread-Index` is its own less the final five bytes.")
    w("")
    w(f"- messages carrying a decodable `Thread-Index`: **{graph['with_thread_index']:,}** "
      f"({pct(graph['with_thread_index'], total_eml).strip()})")
    w(f"- distinct conversations: **{graph['conversations']:,}**")
    w(f"- messages in a conversation of more than one: **{graph['in_multi_message_conversation']:,}**")
    w(f"- messages whose immediate parent is also in this slice: **{graph['parent_present']:,}**")
    w(f"  - of those, parent held by a different custodian: **{graph['parent_in_another_custodian']:,}**")
    w(f"- duplicate `Message-ID`s across the slice: **{graph['duplicate_message_ids']:,}**")
    w("")
    w("The last two numbers are what a custodian set is chosen on: unrelated custodians")
    w("leave `in_reply_to` empty and the field goes untested.")
    w("")

    w("### Who mails whom, inside the slice")
    w("")
    w("Mail from one custodian in the set to another. This is the number a custodian set")
    w("is chosen on: a set whose members do not correspond is a set of unrelated")
    w("mailboxes, and every threading and relation path stays untested.")
    w("")
    w("Counted by surname appearing anywhere in the `From` / `To` / `Cc` text, since half")
    w("of those headers carry no address at all and one person has several address forms.")
    w("Each custodian's own address, the most frequent in their mailbox carrying their")
    w("surname:")
    w("")
    w("| custodian | address |")
    w("|---|---|")
    for custodian, address in sorted(graph["owner"].items()):
        w(f"| {custodian} | {address} |")
    w("")
    edges = graph["internal_edges"]
    if not edges:
        w("No two custodians in this slice correspond.")
    else:
        inbound: collections.Counter = collections.Counter()
        for (_, target), n in edges.items():
            inbound[target] += n
        w("| from | to | messages |")
        w("|---|---|---:|")
        for (sender, target), n in edges.most_common():
            w(f"| {sender} | {target} | {n:,} |")
        w("")
        w(f"Messages crossing custodians inside the set: **{sum(edges.values()):,}** "
          f"across **{len(edges)}** ordered pairs.")
    w("")

    w("### Slice recommendation")
    w("")
    w("Custodians ranked by mail exchanged with the rest of the set, which is the only")
    w("property that makes a set more than a pile of unrelated mailboxes.")
    w("")
    traffic: collections.Counter = collections.Counter()
    for (sender, target), n in edges.items():
        traffic[sender] += n
        traffic[target] += n
    w("| custodian | messages exchanged with the set | correspondents |")
    w("|---|---:|---:|")
    partners: collections.Counter = collections.Counter()
    for (sender, target) in edges:
        partners[sender] += 1
        partners[target] += 1
    for custodian, n in traffic.most_common():
        w(f"| {custodian} | {n:,} | {partners[custodian]} |")
    for custodian in sorted(set(custodians) - set(traffic)):
        w(f"| {custodian} | 0 | 0 |")
    w("")
    w("Keep the connected core and drop the tail: a custodian exchanging nothing with the")
    w("others contributes volume and no threading, which is what the retired corpus's")
    w("lesson warns against - measure the property before building on it.")
    w("")

    w("## Bodies")
    w("")
    footer = sum(c.zl_footer for c in custodians.values())
    w(f"**The ZL attribution footer is appended to {footer:,} of {total_eml:,} bodies "
      f"({pct(footer, total_eml).strip()}).** It is fenced by asterisk rules and carries the")
    w("CC-BY attribution. It is not the sender's words, so #78 must cut it before the")
    w("paragraph splitter runs, exactly as quoted replies are cut - left in, every record")
    w("gains a paragraph that says nothing, and every paragraph hash depends on it.")
    w("")
    w(f"- messages whose body is empty once footer and whitespace are removed: "
      f"**{sum(c.empty_body for c in custodians.values()):,}**")
    w(f"- messages containing CRLF line endings: "
      f"**{sum(c.crlf for c in custodians.values()):,}** "
      f"({pct(sum(c.crlf for c in custodians.values()), total_eml).strip()})")
    w("")
    w("`.gitattributes` forces LF and `normalize.convert_plain_text` already replaces")
    w("CRLF, so this is noted rather than owed.")
    w("")

    w("### Quoted-reply markers")
    w("")
    w("Messages matching each of the cut rules part 05 §5.4 names. A message can match")
    w("more than one.")
    w("")
    w("| marker | messages | of total |")
    w("|---|---:|---:|")
    for label in QUOTE_MARKERS:
        n = sum(c.quotes[label] for c in custodians.values())
        w(f"| {label} | {n:,} | {pct(n, total_eml)} |")
    w("")

    w("### Charsets")
    w("")
    w("As declared in the Content-Type header. Bodies that fail a strict UTF-8 decode")
    w("and charsets Python cannot look up are counted under Anomalies.")
    w("")
    w("| declared charset | messages |")
    w("|---|---:|")
    charsets: collections.Counter = collections.Counter()
    for c in custodians.values():
        charsets.update(c.charsets)
    for name, n in charsets.most_common(12):
        w(f"| {name} | {n:,} |")
    w("")

    w("## Attachments")
    w("")
    w("By extension, as named in the MIME parts. `attachments` is frontmatter only; a")
    w("record of its own is owed just for formats Memoria converts (part 05 §5.4).")
    w("")
    attachments: collections.Counter = collections.Counter()
    for c in custodians.values():
        attachments.update(c.attachments)
    w(f"Total attachment parts: **{sum(attachments.values()):,}**")
    w("")
    w("| extension | parts |")
    w("|---|---:|")
    for name, n in attachments.most_common(20):
        w(f"| {name} | {n:,} |")
    w("")
    types: collections.Counter = collections.Counter()
    for c in custodians.values():
        types.update(c.attachment_types)
    w("| MIME type | parts |")
    w("|---|---:|")
    for name, n in types.most_common(20):
        w(f"| {name} | {n:,} |")
    w("")

    w("## Sidecar files")
    w("")
    w("Each custodian archive ships `.eml` under `native_*`, plain text under `text_*`,")
    w("one XML load file, and the attachments as loose native files. By the archive's")
    w("layout the text and XML are the same messages again - assumed, not verified by")
    w("`Message-ID`. Only the `.eml` are raw units, so `fetch-enron.py` unpacks nothing")
    w("else; anything counted here arrived some other way and will be numbered a second")
    w("time by `manifest.sync` (ADR-0006), which never gives an ID back.")
    w("")
    sidecars: collections.Counter = collections.Counter()
    for c in custodians.values():
        sidecars.update(c.sidecars)
    w("| extension | files |")
    w("|---|---:|")
    for name, n in sidecars.most_common(20):
        w(f"| {name} | {n:,} |")
    w("")

    w("## Anomalies")
    w("")
    anomalies: collections.Counter = collections.Counter()
    for c in custodians.values():
        anomalies.update(c.anomalies)
    if not anomalies:
        w("None counted.")
    else:
        w("| anomaly | messages |")
        w("|---|---:|")
        for name, n in anomalies.most_common():
            w(f"| {name} | {n:,} |")
    w("")
    return "\n".join(out) + "\n"


def default_out(root: Path) -> Path:
    """Where RECON.md goes: the evidence root, never inside ``raw/``.

    ``manifest.sync`` walks ``raw/**`` and numbers every file it finds as a raw
    unit (ADR-0006), so a report written under there would be given a ``SRC-``
    ID and, since IDs are never reused, keep it forever.
    """
    for parent in root.parents:
        if parent.name == "raw":
            return parent.parent / "RECON.md"
    return root.parent / "RECON.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="the raw/enron directory of a fetched slice")
    parser.add_argument("-o", "--out", type=Path, help="output path (default: <root>/../RECON.md)")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    custodians, messages = scan(root)
    if not messages:
        raise SystemExit(f"no .eml found under {root}")
    graph = reply_graph(messages)

    out = args.out or default_out(root)
    out.write_text(render(custodians, graph), encoding="utf-8")
    print(f"{len(messages):,} messages across {len(custodians)} custodians -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
