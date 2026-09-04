"""Validate one worker's readings file and cache it.

    python record.py READINGS.json --chunk waves/<n>/chunk-<k>.json [--dry-run]

READINGS is a JSON array of one object per paragraph, the shape the MCP
``extraction_record`` tool takes:

    {"anchor": "...", "placements": [{"entry_id", "surface_form"}],
     "unplaced": [{"surface_form", "subject_id"}],
     "relations": [{"from_ref", "verb", "to_ref"}]}

Structural problems (an anchor missing, duplicated or not in the chunk; a
subject id the brief does not list; an empty surface form; a brief that has
changed since the chunk was served) stop the run before anything is written.
A surface form that is not verbatim in the paragraph is a warning: the core
does not require it, but the author should hear about it.

Recording goes through ``extraction.record_batch`` - the very function the
MCP tool wraps - so the cache rows are identical to a session-recorded pass.
The per-element outcome is printed the way the tool renders it; a rejected
element names its reason and the rest are kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from memoria import extraction
from memoria.mcp.server import render_record_outcome
from memoria.repository import from_env


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("readings", type=Path)
    parser.add_argument("--chunk", type=Path, required=True, help="the chunk file this readings file answers")
    parser.add_argument("--dry-run", action="store_true", help="validate only; write nothing")
    args = parser.parse_args()

    repository = from_env()
    chunk = json.loads(args.chunk.read_text(encoding="utf-8"))
    served = {p["anchor"]: p["text"] for p in chunk["paragraphs"]}

    current_brief = extraction.brief(repository)
    brief_sha = hashlib.sha256(
        (current_brief.extraction_prompt + "\n" + current_brief.subjects_digest).encode("utf-8")
    ).hexdigest()
    subject_ids = {s.id for s in current_brief.subjects} | {""}

    problems: list[str] = []
    warnings: list[str] = []
    if chunk.get("brief_sha") != brief_sha:
        problems.append("a subject prompt changed since this chunk was served; serve again and re-read")

    try:
        data = json.loads(args.readings.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"PROBLEM: readings file unreadable: {exc}")
        return 1
    if not isinstance(data, list):
        print("PROBLEM: readings file is not a JSON array")
        return 1

    seen: set[str] = set()
    recorded: list[extraction.RecordedParagraph] = []
    for item in data:
        anchor = item.get("anchor")
        if anchor not in served:
            problems.append(f"{anchor!r} is not in the chunk")
            continue
        if anchor in seen:
            problems.append(f"{anchor} appears twice")
            continue
        seen.add(anchor)
        unplaced = []
        for u in item.get("unplaced", []) or []:
            form, subject = str(u.get("surface_form", "")), str(u.get("subject_id", ""))
            if not form.strip():
                problems.append(f"{anchor}: empty surface form")
                continue
            if subject not in subject_ids:
                problems.append(f"{anchor}: unknown subject_id {subject!r}")
            if norm(form) not in norm(served[anchor]):
                warnings.append(f"{anchor}: form not verbatim in the paragraph: {form!r}")
            unplaced.append(extraction.RecordedForm(form, subject))
        placements = [
            extraction.RecordedPlacement(str(p["entry_id"]), str(p["surface_form"]))
            for p in item.get("placements", []) or []
        ]
        relations = [
            extraction.RecordedRelation(str(r["from_ref"]), str(r["verb"]), str(r["to_ref"]))
            for r in item.get("relations", []) or []
        ]
        recorded.append(extraction.RecordedParagraph(anchor, placements, unplaced, relations))
    missing = [a for a in served if a not in seen]
    if missing:
        problems.append(f"{len(missing)} served anchors missing: {' '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}")

    for w in warnings:
        print("WARNING:", w)
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        print(f"nothing recorded ({len(problems)} problems)")
        return 1
    if args.dry_run:
        print(f"dry run: {len(recorded)} readings valid, {len(warnings)} warnings, nothing recorded")
        return 0

    outcome = extraction.record_batch(
        repository, [(r.anchor, r.to_extraction()) for r in recorded]
    )
    print(render_record_outcome(outcome, len(recorded)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
