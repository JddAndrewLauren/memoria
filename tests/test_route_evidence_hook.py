"""Tests for `.claude/hooks/route-evidence-reads.sh` (issue #112).

Feeds the hook the same PreToolUse JSON Claude Code would, over stdin, and
asserts its exit code and stderr message -- the hook has no other surface.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "route-evidence-reads.sh"

ROUTER_MESSAGE = (
    "Evidence reads route through the Memoria MCP tool read(ref): the same "
    "verbatim text, addressed by SRC- ID, paragraph anchor, or repository "
    "path, and the read lands in the session ledger (events.jsonl) - see "
    "docs/tool-surface.md. Direct file access to the evidence repo is "
    "disabled in this workspace."
)


def run_hook(tool_name, tool_input, *, project_dir, evidence_root=None):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    if evidence_root is None:
        env.pop("MEMORIA_EVIDENCE_ROOT", None)
    else:
        env["MEMORIA_EVIDENCE_ROOT"] = str(evidence_root)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def project_dir(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    return d


@pytest.fixture
def evidence_root(tmp_path):
    d = tmp_path / "evidence"
    d.mkdir()
    return d


# --- denied: this repo's own derived records, evidence root unset ---------


def test_denies_read_under_sources_normalized_with_root_unset(project_dir):
    result = run_hook(
        "Read",
        {"file_path": str(project_dir / "sources" / "normalized" / "SRC-000001.md")},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_read_under_dot_memoria_with_root_unset(project_dir):
    result = run_hook(
        "Read",
        {"file_path": str(project_dir / ".memoria" / "index.db")},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_grep_path_under_sources_normalized(project_dir):
    result = run_hook(
        "Grep",
        {"path": str(project_dir / "sources" / "normalized")},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_glob_pattern_under_dot_memoria(project_dir):
    result = run_hook(
        "Glob",
        {"pattern": str(project_dir / ".memoria" / "**")},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_dotdot_path_resolving_into_sources_normalized(project_dir):
    sneaky = project_dir / "other" / ".." / "sources" / "normalized" / "SRC-1.md"
    result = run_hook("Read", {"file_path": str(sneaky)}, project_dir=project_dir)
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


# --- denied: MEMORIA_EVIDENCE_ROOT, when set (unchanged) ------------------


def test_denies_read_under_evidence_root_when_set(project_dir, evidence_root):
    result = run_hook(
        "Read",
        {"file_path": str(evidence_root / "foo.eml")},
        project_dir=project_dir,
        evidence_root=evidence_root,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


# --- allowed --------------------------------------------------------------


def test_allows_unrelated_read_with_root_unset(project_dir):
    """The unset-variable no-op: unrelated to any routed root."""
    result = run_hook(
        "Read",
        {"file_path": str(project_dir / "README.md")},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_unrelated_read_outside_evidence_root_when_set(project_dir, evidence_root):
    result = run_hook(
        "Read",
        {"file_path": str(project_dir / "README.md")},
        project_dir=project_dir,
        evidence_root=evidence_root,
    )
    assert result.returncode == 0
    assert result.stderr == ""


# --- Bash: exact-string containment against the command text --------------


def test_denies_bash_command_naming_sources_normalized(project_dir):
    result = run_hook(
        "Bash",
        {"command": "grep -r foo sources/normalized/"},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_bash_command_naming_dot_memoria(project_dir):
    result = run_hook(
        "Bash",
        {"command": "sqlite3 .memoria/index.db 'select 1'"},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_bash_command_naming_resolved_evidence_root(project_dir, evidence_root):
    result = run_hook(
        "Bash",
        {"command": f"grep -r foo {evidence_root}"},
        project_dir=project_dir,
        evidence_root=evidence_root,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_allows_unrelated_bash_command(project_dir):
    result = run_hook(
        "Bash",
        {"command": "ls src/memoria"},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_unrelated_bash_command_with_root_set(project_dir, evidence_root):
    result = run_hook(
        "Bash",
        {"command": "pytest tests/ -q"},
        project_dir=project_dir,
        evidence_root=evidence_root,
    )
    assert result.returncode == 0
    assert result.stderr == ""
