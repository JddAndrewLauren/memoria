"""Serve one wave of the extraction to sub-agent workers.

Writes the brief once and the next pending paragraphs as disjoint chunk files,
one per worker, under a run directory. Reads only: it uses the same core
functions the MCP server's ``extraction_brief`` and
``extraction_next_paragraphs`` call, and records nothing. A paragraph leaves
the pending set only when ``record.py`` caches its reading, so a wave served
and never recorded is simply served again.

    python serve.py RUN_DIR --workers 8 --batch 300 [--oversize 20000]

Layout under RUN_DIR:
    brief.md                 the brief, verbatim, written on the first call
    brief.sha                digest of the brief; every chunk carries it
    waves/<n>/chunk-<k>.json {"brief_sha", "wave", "chunk", "paragraphs": [{anchor, text}]}
    oversize/<anchor>.json   one paragraph above --oversize, same shape, chunk 0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from memoria import extraction
from memoria.ledger import append_extraction_batch, append_extraction_brief, session_id_from_env
from memoria.mcp.server import render_brief
from memoria.repository import from_env


def prompt_digest(brief: extraction.Brief) -> str:
    """What a cached reading is keyed on, besides the paragraph itself."""
    return hashlib.sha256(
        (brief.extraction_prompt + "\n" + brief.subjects_digest).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch", type=int, default=300)
    parser.add_argument("--oversize", type=int, default=20000, help="chars; larger paragraphs go to oversize/")
    args = parser.parse_args()

    repository = from_env()
    # Served batches are ledgered exactly as the MCP tools ledger them, so the
    # supplied-context account (ADR-0001) still names the session that read
    # everything. Set MEMORIA_SESSION_ID to the orchestrating session's id.
    session = session_id_from_env()
    run_dir: Path = args.run_dir
    (run_dir / "waves").mkdir(parents=True, exist_ok=True)
    (run_dir / "oversize").mkdir(exist_ok=True)

    current = extraction.brief(repository)
    brief_text = render_brief(current)
    # The digest mirrors the cache key (prompt + subject prompts), not the
    # rendered brief: the entry list and the pending count change without
    # invalidating a single cached reading.
    brief_sha = prompt_digest(current)
    brief_path = run_dir / "brief.md"
    sha_path = run_dir / "brief.sha"
    if sha_path.exists() and sha_path.read_text().strip() != brief_sha:
        print("a subject prompt changed since this run started; every reading is pending again - start a new run dir", file=sys.stderr)
        return 2
    if not brief_path.exists() or brief_path.read_text(encoding="utf-8") != brief_text:
        # Rewritten whenever entries change, so workers see the current list.
        brief_path.write_text(brief_text, encoding="utf-8")
        sha_path.write_text(brief_sha + "\n")
        append_extraction_brief(repository, session, [s.id for s in current.subjects])

    pending = extraction.pending_paragraphs(repository)
    if not pending:
        print("nothing pending: every paragraph is read under the current prompts")
        return 0

    oversize = [p for p in pending if len(p.text) > args.oversize]
    # One reading per distinct text: the cache is keyed on the text, so the
    # first anchor's reading marks every identical paragraph read. Serving
    # the duplicates would spend workers on paragraphs already covered.
    seen_keys: set[str] = set()
    regular = []
    duplicates = 0
    for p in pending:
        if len(p.text) > args.oversize:
            continue
        if p.memo_key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(p.memo_key)
        regular.append(p)
    for p in oversize:
        target = run_dir / "oversize" / f"{p.anchor}.json"
        if not target.exists():
            target.write_text(json.dumps(
                {"brief_sha": brief_sha, "wave": 0, "chunk": 0,
                 "paragraphs": [{"anchor": p.anchor, "text": p.text}]},
                ensure_ascii=False), encoding="utf-8")

    existing = [int(d.name) for d in (run_dir / "waves").iterdir() if d.name.isdigit()]
    wave = max(existing, default=0) + 1
    wave_dir = run_dir / "waves" / str(wave)
    wave_dir.mkdir()
    take = regular[: args.workers * args.batch]
    chunks = [take[i : i + args.batch] for i in range(0, len(take), args.batch)]
    for k, chunk in enumerate(chunks, start=1):
        (wave_dir / f"chunk-{k}.json").write_text(json.dumps(
            {"brief_sha": brief_sha, "wave": wave, "chunk": k,
             "paragraphs": [{"anchor": p.anchor, "text": p.text} for p in chunk]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        append_extraction_batch(repository, session, [p.anchor for p in chunk])

    print(f"session: {session}")
    print(f"pending: {len(pending)} ({len(regular)} distinct regular, {duplicates} duplicates of those, {len(oversize)} oversize > {args.oversize} chars)")
    print(f"wave {wave}: {len(chunks)} chunks, {len(take)} paragraphs, under {wave_dir}")
    for k, chunk in enumerate(chunks, start=1):
        print(f"  chunk-{k}.json: {len(chunk)} paragraphs, {chunk[0].anchor} .. {chunk[-1].anchor}")
    if oversize:
        print("oversize (one worker each, largest-context model):")
        for p in sorted(oversize, key=lambda p: -len(p.text)):
            print(f"  {p.anchor}: {len(p.text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
