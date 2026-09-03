#!/usr/bin/env python3
"""Time the phases of ``index.rebuild`` over a synthetic corpus (#172).

Builds a throwaway repository of ``--records`` normalized records with
``--paragraphs`` seeded pseudo-random paragraphs each, rebuilds it once
without an embedder and once with ``memoria.embeddings.default_embed_fn``
(the CPU ONNX model ``memoria rebuild`` uses), and prints the per-phase
breakdown as a Markdown table ready to paste into the issue.

Deterministic corpus (``random.Random(0)``), no network beyond whatever the
embedder's first model download needs, nothing written outside a temporary
directory that is removed afterwards. The ``changes/`` projection is not
timed here: it reads git history, and the temporary directory has none, so
that number only means anything from ``memoria rebuild`` on a real clone.

Usage::

    .venv/bin/python scripts/bench-rebuild.py --records 4000
    .venv/bin/python scripts/bench-rebuild.py --records 50 --no-embed   # smoke
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import tempfile
from pathlib import Path

from memoria import index
from memoria.records import NORMALIZED_RELATIVE_PATH, NormalizedRecord, write_normalized_records
from memoria.repository import Repository

_WORDS = (
    "the a of to and in that for on with as at by from about into over after "
    "meeting call deal contract gas power price market trade risk credit "
    "schedule pipeline capacity storage plant unit turbine outage forecast "
    "report memo draft review approve sign send forward attach copy note "
    "monday tuesday wednesday thursday friday morning afternoon tomorrow "
    "please thanks regards question answer confirm update status issue plan "
    "houston portland london calgary omaha enron dynegy reliant mirant duke"
).split()


def _paragraph(rng: random.Random) -> str:
    sentences = []
    for _ in range(rng.randint(1, 4)):
        words = [rng.choice(_WORDS) for _ in range(rng.randint(6, 22))]
        words[0] = words[0].capitalize()
        sentences.append(" ".join(words) + ".")
    return " ".join(sentences)


def _corpus(count: int, paragraphs: int, rng: random.Random) -> list[NormalizedRecord]:
    records = []
    for n in range(1, count + 1):
        day = 1 + (n % 28)
        month = 1 + (n // 28) % 12
        date = f"2001-{month:02d}-{day:02d}"
        records.append(
            NormalizedRecord(
                id=f"SRC-{n:06d}",
                source_type="email",
                recorded_date=date,
                event_date=date,
                date_confidence="exact",
                contemporaneous=True,
                original_file=f"raw/maildir/user{n % 4}/sent/{n}.eml",
                original_locator=f"message {n}",
                paragraphs=[_paragraph(rng) for _ in range(paragraphs)],
                email_from=f"user{n % 4}@example.com",
                email_to=f"user{(n + 1) % 4}@example.com",
            )
        )
    return records


def _run(repository: Repository, *, embed_fn) -> index.RebuildReport:
    return index.rebuild(repository, reset_cache=True, embed_fn=embed_fn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--records", type=int, default=4000)
    parser.add_argument("--paragraphs", type=int, default=5)
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="skip the run with the real embedder (fast; for checking the script)",
    )
    args = parser.parse_args(argv)

    root = Path(tempfile.mkdtemp(prefix="memoria-bench-"))
    try:
        (root / "pyproject.toml").write_text("")
        records = _corpus(args.records, args.paragraphs, random.Random(0))
        write_normalized_records(records, root / NORMALIZED_RELATIVE_PATH)
        repository = Repository(root=root)
        paragraph_count = sum(len(r.paragraphs) for r in records)
        print(f"corpus: {len(records)} records, {paragraph_count} paragraphs, at {root}")
        sys.stdout.flush()

        without = _run(repository, embed_fn=None)
        print(f"without embed_fn: {without.elapsed_seconds:.1f}s")
        sys.stdout.flush()
        with_embed = None
        if not args.no_embed:
            from memoria.embeddings import default_embed_fn

            with_embed = _run(repository, embed_fn=default_embed_fn)
            print(f"with embed_fn: {with_embed.elapsed_seconds:.1f}s")

        print()
        print(f"| phase | without embed_fn | with embed_fn |")
        print(f"|---|---:|---:|")
        with_map = dict(with_embed.phases) if with_embed else {}
        for name, seconds in without.phases:
            right = f"{with_map[name]:.2f}s" if with_embed else "-"
            print(f"| {name} | {seconds:.2f}s | {right} |")
        total_right = f"{with_embed.elapsed_seconds:.1f}s" if with_embed else "-"
        print(f"| **total** | {without.elapsed_seconds:.1f}s | {total_right} |")
        if with_embed:
            per = with_map["embedding"] / paragraph_count * 1000
            print()
            print(f"embedding: {per:.1f} ms/paragraph over {paragraph_count} paragraphs")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
