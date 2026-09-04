"""Compare several models' readings of the same paragraphs (the pilot step).

    python compare.py --chunk CHUNK.json --readings haiku.json sonnet.json ... --out DIR

Each readings file is named for its model. Writes DIR/compare.json and
DIR/compare.md. Judges nothing: counts and set arithmetic only. The ranking
is the comparator sub-agent's job, over the paragraphs this lists.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path


def norm(form: str) -> str:
    return " ".join(form.lower().split())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chunk", type=Path, required=True)
    parser.add_argument("--readings", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    chunk = json.loads(args.chunk.read_text(encoding="utf-8"))
    paragraphs = chunk["paragraphs"] if isinstance(chunk, dict) else chunk
    texts = {p["anchor"]: p["text"] for p in paragraphs}
    served = list(texts)

    readings: dict[str, dict[str, list[tuple[str, str]]]] = {}
    problems: list[str] = []
    for path in args.readings:
        model = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{model}: unreadable ({exc})")
            continue
        by_anchor: dict[str, list[tuple[str, str]]] = {}
        for item in data:
            a = item.get("anchor")
            if a not in texts:
                problems.append(f"{model}: unknown anchor {a!r}")
                continue
            forms = []
            for u in item.get("unplaced", []) or []:
                sf, sid = str(u.get("surface_form", "")), str(u.get("subject_id", ""))
                if not sf.strip():
                    continue
                if norm(sf) not in norm(texts[a]):
                    problems.append(f"{model}: {a} form not in text: {sf!r}")
                forms.append((sf, sid))
            by_anchor[a] = forms
        missing = [a for a in served if a not in by_anchor]
        if missing:
            problems.append(f"{model}: {len(missing)} anchors missing")
        readings[model] = by_anchor
    models = list(readings)

    def formset(m: str, a: str) -> set[str]:
        return {norm(sf) for sf, _ in readings[m].get(a, [])}

    per_model = {}
    for m in models:
        forms = [f for fs in readings[m].values() for f in fs]
        per_model[m] = {
            "paragraphs_with_forms": sum(1 for fs in readings[m].values() if fs),
            "total_forms": len(forms),
            "distinct_forms": len({norm(sf) for sf, _ in forms}),
            "by_subject": dict(Counter(sid or '""' for _, sid in forms)),
        }

    pairwise = {}
    for x, y in itertools.combinations(models, 2):
        jac, exact = [], 0
        for a in served:
            sx, sy = formset(x, a), formset(y, a)
            u = sx | sy
            jac.append(len(sx & sy) / len(u) if u else 1.0)
            exact += sx == sy
        pairwise[f"{x}/{y}"] = {"mean_jaccard": round(sum(jac) / len(jac), 3), "exact_match_paragraphs": exact}

    scores = {}
    for a in served:
        sets = {m: formset(m, a) for m in models}
        if not any(sets.values()) or len(models) < 2:
            scores[a] = 0.0
            continue
        js = []
        for x, y in itertools.combinations(models, 2):
            u = sets[x] | sets[y]
            js.append(len(sets[x] & sets[y]) / len(u) if u else 1.0)
        scores[a] = round(1 - sum(js) / len(js), 3)

    found_by: dict[tuple[str, str], set[str]] = defaultdict(set)
    for m in models:
        for a in served:
            for f in formset(m, a):
                found_by[(a, f)].add(m)
    only_one = Counter(next(iter(ms)) for ms in found_by.values() if len(ms) == 1)
    by_all = sum(1 for ms in found_by.values() if len(ms) == len(models))

    disagreements = []
    for a in served:
        sid_by_form: dict[str, dict[str, str]] = defaultdict(dict)
        for m in models:
            for sf, sid in readings[m].get(a, []):
                sid_by_form[norm(sf)][m] = sid
        for f, ms in sid_by_form.items():
            if len(set(ms.values())) > 1:
                disagreements.append({"anchor": a, "form": f, "by_model": ms})

    top = [a for a in sorted(served, key=lambda a: -scores[a]) if scores[a] > 0][:15]
    agreed = [a for a in served if scores[a] == 0 and any(formset(m, a) for m in models)][:5]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "compare.json").write_text(json.dumps({
        "problems": problems, "models": models, "per_model": per_model, "pairwise": pairwise,
        "forms_found_by_only_one_model": dict(only_one), "forms_found_by_all_models": by_all,
        "distinct_forms_union": len(found_by), "subject_disagreements": disagreements,
        "top_disagreement_paragraphs": [{"anchor": a, "score": scores[a]} for a in top],
        "full_agreement_paragraphs_with_forms": agreed,
    }, indent=1))

    lines = [f"# Comparison of {len(models)} readings of the same {len(served)} paragraphs", ""]
    if problems:
        lines += ["## Problems", *[f"- {p}" for p in problems], ""]
    lines += ["## Per model", "", "| model | paragraphs with forms | total forms | distinct forms | by subject |", "|---|---|---|---|---|"]
    for m in models:
        pm = per_model[m]
        lines.append(f"| {m} | {pm['paragraphs_with_forms']} | {pm['total_forms']} | {pm['distinct_forms']} | {pm['by_subject']} |")
    lines += ["", "## Pairwise agreement (forms per paragraph, normalised)", "", f"| pair | mean Jaccard | exact-match paragraphs / {len(served)} |", "|---|---|---|"]
    for k, v in pairwise.items():
        lines.append(f"| {k} | {v['mean_jaccard']} | {v['exact_match_paragraphs']} |")
    lines += ["", f"Distinct (paragraph, form) pairs across all models: {len(found_by)}",
              f"Found by every model: {by_all}", f"Found by only one model: {dict(only_one)}", ""]
    lines += ["## Subject disagreements on the same form", ""]
    lines += [f"- {d['anchor']} `{d['form']}`: {d['by_model']}" for d in disagreements[:40]]
    if len(disagreements) > 40:
        lines.append(f"- ... {len(disagreements) - 40} more")
    lines += ["", "## Highest-disagreement paragraphs", ""]
    for a in top:
        lines.append(f"### {a} (disagreement {scores[a]})")
        for m in models:
            fs = readings[m].get(a, [])
            lines.append(f"- **{m}**: " + ("; ".join(f"{sf} [{sid or '-'}]" for sf, sid in fs) if fs else "(none)"))
        lines.append("")
    lines += ["## Full-agreement paragraphs that have forms", ""]
    lines += [f"- {a}: " + "; ".join(f"{sf} [{sid or '-'}]" for sf, sid in readings[models[0]].get(a, [])) for a in agreed] if models else []
    (args.out / "compare.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[: 12 + len(models)]))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
