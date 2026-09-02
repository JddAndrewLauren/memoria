# The Enron email corpus

What it is, where it came from, what it is licensed under, and what it is and is
not good for. Written 2026-09-01.

**This document does not decide `docs/open-problems.md` §2.4.** No corpus is
chosen; §2.4 stays open, `orca.yaml`'s `MEMORIA_EVIDENCE_ROOT` probe stays
commented out, and `require_evidence_root` still raises. What is settled here is
narrower: a corpus has been acquired, pinned and characterised, so that the
choice can eventually be made against measurements rather than against a guess.

## Why an email corpus at all

Part 05 §5.2's working assumption is that the real archive's top formats are
docx, pdf and **email exports**. Every email-only field in
`docs/normalized-record-schema.md` — `thread_id`, `from`/`to`/`cc`,
`in_reply_to`, `quoted_excised`, `attachments` — is specified and unexercised,
as is §5.4's quoted-reply splitter and the whole of the email converter (#78).
Nothing in the repository can be built against them, because there is no email
to build against. An Enron export is that format literally, not by analogy.

## The bounded claim

Recorded here so that whoever closes §2.4 inherits it rather than re-deriving it.

Enron is strong on the **evidence** side: real Exchange headers, real
attachments, real entity messiness (`Jeff`, `Skilling`, `Skilling, Jeff`,
several people sharing a surname — part 05 §7's matching hazards with actual
instances), and 149 custodians of genuine scale for §43's large-corpus claim.

It gives **nothing to the manuscript side**. There is no author, no testimony,
no book derived from the archive, and every message is contemporaneous — so §6's
distinction between "what happened in July 2001?" and "what did I believe in
July 2001?" collapses, and the audit, appearances, briefs and declared scope
stay untestable. Enron closes half of `docs/open-problems.md` §4.1's gap. Saying
it closes the whole one would repeat the Thoreau error in the other direction.

Ground truth from headers — who, whom, when — is free and mechanical, which is
its virtue and its trap. It measures **metadata retrieval**, not whether the
extraction reads facts correctly out of prose. §43.14's three numbers stay owed
and are not answerable from this corpus alone. §45's discipline applies: observe
a real failure before building a mechanism, and do not build a benchmark harness
on an instrument whose validity has not been established.

## Source

**EDRM Enron Email Data Set v2 XML**, via the Internet Archive:
<https://archive.org/details/edrm.enron.email.data.set.v2.xml> — 149
per-custodian zip archives, 5 MB to 4 GB, 79 GB in total.

Lineage: the messages were originally made public by the US Federal Energy
Regulatory Commission during its Enron investigation. EDRM republished them;
ZL Technologies produced the EML, PST and NSF forms.

**Licence: Creative Commons Attribution 3.0 United States**
(<https://creativecommons.org/licenses/by/3.0/us/>). The licence requires citing
the producer: *"ZL Technologies, Inc. (http://www.zlti.com)."* That attribution
is also appended as a footer to every message body — see **What the recon found**
below, because it has a consequence for the converter.

Each custodian archive holds the same messages three ways: `.eml` under
`native_*`, extracted plain text under `text_*`, and one XML load file, plus the
attachments as loose native files. **Only the `.eml` are raw units.** The rest is
the same evidence again and must not be numbered a second time.

### Caveat

EDRM withdrew v2 over unscreened personally identifiable information; the
Internet Archive mirror persists. The upstream README warns that the content is
unedited, may be offensive, and may carry viruses — these are real people's
private mail, most of whom did nothing wrong. Treat it accordingly:

- The corpus is **never committed**. It is fetched into an evidence root outside
  this repository, and that root is not a git repository.
- **No Enron bytes are committed at all**, not even scrubbed ones. The `.eml`
  under `tests/fixtures/enron/` are structurally faithful to the export -
  the stray header line, CRLF, quoted-printable, the `X-ZL-*` headers, the
  attribution footer, `Thread-Index` chaining - and textually invented, with
  RFC 2606 `example.com` addresses and people who do not exist. Real bodies
  in this corpus carry named individuals' medical and family details, which is
  what EDRM withdrew v2 over, and a commit is forever. `tests/test_enron_fixtures.py`
  holds the fixtures to that contract in both directions: each still exhibits
  its parsing defect, and none names a real person or domain.
- Attachments are executable-adjacent formats (`.doc`, `.xls`, `.ppt`). Nothing
  in Memoria opens them and nothing should.

## Why not the other two sources

**FERC directly** (ferc.gov, XERA, eLibrary) — the original, and not usable. It
is behind a bot challenge, runs past 100 GB, and is delivered as iCONECT /
Concordance flat-file databases with static images rather than MIME. It is not
scriptable and not parseable by the standard-library path §5.4 commits to.

**CMU / CALO** (<https://www.cs.cmu.edu/~enron/>, `enron_mail_20150507.tar.gz`,
443 MB gzipped, ~517k messages, 150 custodians, maildir) — live, the most-cited
version, and the easiest to acquire. Rejected as the primary because it was
redacted at employees' request, carries **no attachments**, and had its
`Message-ID`s regenerated with the reply headers stripped. Worth revisiting only
if a volume corpus is later wanted for §43's large-corpus claim, where its size
and its single pinned URL are advantages and the missing headers do not matter.

## How to reproduce the slice

```bash
# 1. Fetch the pinned archives. Verifies sha1 against the pins, records sha256
#    on first fetch, then enforces it. Idempotent.
.venv/bin/python scripts/fetch-enron.py --dest ../enron-evidence

# 2. Characterise what landed. Read-only, deterministic, no network.
.venv/bin/python scripts/enron-recon.py ../enron-evidence/raw/enron
```

The corpus is `scripts/fetch-enron.py` plus
`docs/corpora/enron-acquisition.yaml`: given the pins, any machine reproduces
the same bytes, and the recorded hashes are what makes that checkable. Nothing
needs storing.

`RECON.md` is written to the evidence root, deliberately **not** under `raw/` —
`manifest.sync` walks `raw/**` and would number a report there as a raw unit
(ADR-0006), and an ID once given is never reused.

## What the recon found

The numbers live in `RECON.md` beside the corpus and are regenerated, not
transcribed. Three findings are load-bearing enough to record here, because they
are inputs to the email converter (#78) rather than facts about one slice.

**1. A third to a half of the messages do not parse with the standard library.**
ZL's production wrote a bare `Microsoft Mail Internet Headers Version 2.0` line
into the middle of the header block. It contains no colon, so
`email.message_from_bytes` treats it as the blank line separating headers from
body, and every header below it — `From`, `To`, `Subject`, `Thread-Index`, the
whole `X-ZL-*` set — is silently read as body text. No exception is raised. A
converter that skipped this would simply believe those messages had no sender.
Deleting that one line before parsing is the entire fix and takes remaining
defects to approximately zero.

**2. `In-Reply-To` is absent, and `Thread-Index` is the substitute.**
`docs/normalized-record-schema.md` resolves `in_reply_to` "from `Message-ID` /
`In-Reply-To` within the same export", per §5.4. In this corpus `In-Reply-To`
is present on **none** of the messages and `References` on a handful. Enron ran
Exchange, and the export preserves Outlook's `Thread-Index` instead — on roughly
a third of messages. That is a deterministic substitute rather than a heuristic:
the first 22 bytes identify the conversation and each reply appends exactly
five, so a message's parent is the one whose `Thread-Index` is its own less the
final five bytes. `thread_id` comes from the 22-byte root; `in_reply_to` from
the longest proper prefix present in the export.

This is a genuine amendment owed to §5.4 and the schema, not a shortcoming of
the slice. The schema's rule that `in_reply_to` is "empty when the headers are
missing or the parent is not in the archive" already covers the degraded case
honestly — but a corpus where the named mechanism never fires would leave the
field permanently untested, which is why the custodian set is chosen on the
measured parent-present rate.

**3. Half the correspondents are named rather than addressed.** `From` carries an
actual email address on 48% of messages and `To` on 61%. The rest hold bare
display names, comma-separated — `To: Tim Belden, Teri Whitcomb, Kathy Axford` —
and the comma is ambiguous, because `Belden, Tim` is one person written the
other way round and a single header may mix both conventions. `X-ZL-To`, which
carries X.500 distinguished names, covers only 40% and is not a fallback. So
`from`/`to`/`cc` in the record schema cannot be assumed to be addresses. This is
part 05 §7's alias problem arriving in the headers instead of in the prose:
resolving a correspondent to a person is entry match-term work, not a parse, and
the converter should keep the header verbatim and leave the resolution to the
subject system. It is also the reason a corpus like this is worth having — the
mess is real, and no synthetic fixture would have predicted it.

**4. Every body carries the ZL attribution footer.** Fenced by asterisk rules
and appended to the message text. It is not the sender's words, so #78 must cut
it before the paragraph splitter runs, exactly as quoted replies are cut. Left
in, every record gains a paragraph that says nothing and every paragraph hash —
the extraction's memo key, part 06 §8.12 — depends on it.

## The slice

Nine candidate custodians were fetched as a pool and measured; the four kept are
the connected core. Of the 351 messages in the pool that cross from one
custodian to another, **262 are between these four**:

| custodian | | |
|---|---|---|
| `scholtes-d` | Diana Scholtes | west power desk |
| `semperger-c` | Cara Semperger | west power desk |
| `crandall-s` | Sean Crandall | west power desk |
| `salisbury-h` | Holden Salisbury | west power desk |

The other five stay pinned in `enron-acquisition.yaml` so the measurement is
reproducible and the set can be widened without a second search. A custodian who
exchanges nothing with the others adds volume and no threading, and choosing on
volume rather than on the measured property is the mistake §2.4 records.

Correspondence had to be counted by surname appearing anywhere in the header
text, not by address equality — see finding 3, and note that one person here has
several address forms (`sean.crandall@enron.com`, `Sean Crandall@ECT`, an X.500
DN). Matching on exact addresses undercounted the same traffic by an order of
magnitude, which is worth remembering before any retrieval number is computed
over this corpus.

## Vocabulary

Per `docs/agents/domain.md` and `CONTEXT.md`: a message here is a **raw unit**
and becomes a **normalized record**. It is never an "entry" — that is an
instance under a subject — and never a "document", "item" or "source file".
