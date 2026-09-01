#!/usr/bin/env python3
"""Run the M0 check-suite and report pass/fail per check.

M0's promise is that the normalized evidence can be trusted, and part 16's
build order puts normalization first because "it is the one place a mistake
silently invalidates every downstream number". This is the one command that
says whether that promise still holds.

It runs three things, in order:

    memoria validate    raw-file hashes, dangling SRC- IDs, answer-key drift
    memoria rebuild     the whole derived state, regenerated from evidence
    pytest tests/       201 checks, of which 91 run against the real corpus

**Why a runner rather than a `memoria check` subcommand.** Every count this
suite reconciles against `RECON.md` is already asserted in a test, and those
tests are where the reasoning for each deviation is written down. A subcommand
that re-asserted them would put the same numbers in a second place and let the
two drift - the hazard `rebuild()` already carries against `normalize`. So this
script asserts nothing itself. It sequences, reports, and refuses to accept a
skip.

**The skip is the point.** Every real-corpus check is gated on
MEMORIA_EVIDENCE_ROOT, so with no corpus they all skip and `pytest` still exits
0 - the entire reconciliation absent rather than failing, which is precisely the
silence M0 exists to break. This script refuses to start without the corpus, and
counts a skipped `m0` check as a failed one.

Usage, from anywhere in the repo:

    MEMORIA_EVIDENCE_ROOT=../thoreau-evidence .venv/bin/python scripts/m0-check.py

See `docs/m0-check-suite.md` for the reconciliation table and the map from each
M0 mismatch to the regression test that would catch it again.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from memoria.cli import EVIDENCE_ROOT_ENV_VAR, evidence_root, repo_root

# The five reconciliations part 16's check-suite line item names, each pinned to
# the test that asserts it. Named here so that renaming or deleting one of them
# fails this command instead of quietly shrinking the M0 suite to four checks.
# The figures live in the tests and in docs/m0-check-suite.md, never here.
REQUIRED_CHECKS = {
    "RECON §3 date headings": (
        "tests/test_normalize.py::TestAgainstTheRealEvidenceCorpus"
        "::test_date_headings_found_are_reconciled_against_recon"
    ),
    "RECON §5 letters": (
        "tests/test_letters.py::TestAgainstTheRealEvidenceCorpus"
        "::test_letter_count_matches_recon"
    ),
    "RECON §5 recipients": (
        "tests/test_letters.py::TestAgainstTheRealEvidenceCorpus"
        "::test_recipient_count_matches_recon"
    ),
    "RECON §4(a) footnote markers": (
        "tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus"
        "::test_footnote_marker_counts_reconcile_against_recon"
    ),
    "RECON §4(a) bracketed spans": (
        "tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus"
        "::test_bracketed_span_counts_reconcile_against_recon"
    ),
    "no editorial voice in sampled evidence": (
        "tests/test_editorial.py::TestAgainstTheRealEvidenceCorpus"
        "::test_sampled_evidence_records_contain_no_editorial_voice"
    ),
}


class Report:
    """Per-check pass/fail lines, printed as they are decided."""

    def __init__(self) -> None:
        self.failed = 0

    def record(self, ok: bool, name: str, detail: str = "") -> bool:
        self.failed += not ok
        suffix = f"  {detail}" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{suffix}", flush=True)
        return ok


def require_corpus() -> Path:
    """Resolve the evidence corpus, or refuse to run.

    Refusing is the whole contract: a missing corpus must not be reported as a
    suite that passed, and every corpus check would skip into green without
    this.
    """
    root = evidence_root()
    if (root / "raw" / "gutenberg" / "manifest.yaml").is_file():
        return root
    print(
        f"m0-check: no evidence corpus at {root.resolve()}\n"
        f"m0-check: set {EVIDENCE_ROOT_ENV_VAR} to the thoreau-evidence checkout.\n"
        "m0-check: refusing to run - without the corpus every reconciliation "
        "check skips and the suite would report green having checked nothing.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def run_cli(report: Report, root: Path, command: str) -> bool:
    """Run one `memoria` subcommand over the full corpus."""
    completed = subprocess.run(
        [sys.executable, "-m", "memoria.cli", command],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        report.record(False, f"memoria {command}", f"exit {completed.returncode}")
        print(completed.stdout.rstrip("\n") or completed.stderr.rstrip("\n"))
        return False
    # normalize/rebuild print their counts; keep the last line as evidence the
    # run really covered the corpus rather than an empty tree.
    last = [line for line in completed.stdout.splitlines() if line.strip()]
    return report.record(True, f"memoria {command}", last[-1] if last else "")


def run_pytest(report: Report, root: Path) -> bool:
    """Run the whole suite, and read per-test outcomes out of the JUnit XML.

    The whole suite, not `-m m0`: the gate asks for the corpus reconciliations
    *and* for every mismatch found during M0 to still have a regression test,
    and most of those regression tests are synthetic and unmarked.
    """
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "junit.xml"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "--strict-markers",
                f"--junit-xml={report_path}",
            ],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if not report_path.is_file():
            report.record(False, "pytest tests/", "produced no report")
            print(completed.stdout.rstrip("\n") or completed.stderr.rstrip("\n"))
            return False
        outcomes = {
            _node_id(case): _outcome(case)
            for case in ET.parse(report_path).getroot().iter("testcase")
        }

    failures = sorted(n for n, o in outcomes.items() if o == "failure")
    for node in failures:
        report.record(False, node)

    # A skipped m0 check is a check that did not run. Reported as a failure so
    # that an absent corpus can never read as a passing suite.
    skipped = sorted(n for n, o in outcomes.items() if o == "skipped")
    for node in skipped:
        report.record(False, node, "skipped - the corpus check did not run")

    for name, node in REQUIRED_CHECKS.items():
        if node not in outcomes:
            report.record(False, name, f"missing: no test named {node}")
        elif outcomes[node] == "passed":
            report.record(True, name)

    ok = not failures and not skipped
    report.record(
        ok and completed.returncode == 0,
        "pytest tests/",
        f"{sum(o == 'passed' for o in outcomes.values())}/{len(outcomes)} passed",
    )
    return ok


def _node_id(case: ET.Element) -> str:
    """Rebuild pytest's `path::Class::name` node id from a JUnit testcase."""
    parts = case.get("classname", "").split(".")
    name = case.get("name", "")
    if not parts or parts == [""]:
        return name
    # classname is `tests.test_letters.TestAgainstTheRealEvidenceCorpus` for a
    # method and `tests.test_letters` for a module-level test.
    for index, part in enumerate(parts):
        if part.startswith("test_") and (
            index + 1 == len(parts) or not parts[index + 1].startswith("test_")
        ):
            path = "/".join(parts[: index + 1]) + ".py"
            return "::".join([path, *parts[index + 1 :], name])
    return "::".join(["/".join(parts) + ".py", name])


def _outcome(case: ET.Element) -> str:
    for tag in ("failure", "error"):
        if case.find(tag) is not None:
            return "failure"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def main() -> int:
    root = repo_root()
    corpus = require_corpus()
    print(f"m0-check: repo {root}")
    print(f"m0-check: corpus {corpus.resolve()}\n")

    report = Report()
    # validate before rebuild: rebuild regenerates everything validate checks,
    # so running it first would hide a corpus that had drifted from its
    # manifest behind freshly-written derived state.
    run_cli(report, root, "validate")
    run_cli(report, root, "rebuild")
    run_pytest(report, root)

    print()
    if report.failed:
        print(f"m0-check: FAIL - {report.failed} check(s) failed")
        return 1
    print("m0-check: PASS - the M0 check-suite reconciles against RECON.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
