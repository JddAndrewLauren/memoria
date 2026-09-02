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
    "Evidence reads route through the Memoria MCP tools: read(ref) returns "
    "the same verbatim text, addressed by SRC- ID, paragraph anchor, or "
    "repository path, and search_text(query, filters) finds it - including "
    "the from_/to filters (#111), so looking for a sender or recipient is a "
    "filter, not a grep. Served reads land in the session ledger "
    "(events.jsonl) - see docs/tool-surface.md. Direct file access to the "
    "evidence repo is disabled in this workspace."
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


# --- allowed: the false positives #118 fixed ------------------------------
#
# The router denies reads of the routed roots. These commands carry a routed
# path without reading one, and denying them was the router getting in the
# way of the work it exists to route.


def test_allows_memoria_cli_with_inline_evidence_root(project_dir, evidence_root):
    """`MEMORIA_EVIDENCE_ROOT=<slice> memoria normalize` is the sanctioned
    invocation: the evidence path is in the command text by design."""
    result = run_hook(
        "Bash",
        {"command": f"MEMORIA_EVIDENCE_ROOT={evidence_root} memoria normalize"},
        project_dir=project_dir,
        evidence_root=evidence_root,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_memoria_cli_naming_a_routed_root(project_dir):
    result = run_hook(
        "Bash",
        {"command": "memoria rebuild --index .memoria/index.db"},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_git_commit_message_mentioning_a_routed_root(project_dir):
    """Self-demonstrating: #112's own commit message would have tripped the
    hook it shipped."""
    result = run_hook(
        "Bash",
        {"command": 'git commit -m "deny Bash reads of sources/normalized"'},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_gh_pr_body_mentioning_a_routed_root(project_dir):
    result = run_hook(
        "Bash",
        {"command": 'gh pr create --body "routes .memoria/ to the MCP tools"'},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_gh_issue_comment_mentioning_a_routed_root(project_dir):
    result = run_hook(
        "Bash",
        {"command": 'gh issue comment 112 --body "sources/normalized is denied"'},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_allows_grep_whose_pattern_names_a_routed_root(project_dir):
    """The pattern is the text searched for; docs/ is the place searched."""
    result = run_hook(
        "Bash",
        {"command": 'grep -rn ".memoria/" docs/'},
        project_dir=project_dir,
    )
    assert result.returncode == 0
    assert result.stderr == ""


# --- the fix opens no hole ------------------------------------------------


def test_denies_git_command_whose_path_argument_is_a_routed_root(project_dir):
    result = run_hook(
        "Bash",
        {"command": "git add sources/normalized/SRC-000001.md"},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_grep_whose_search_path_is_a_routed_root(project_dir):
    result = run_hook(
        "Bash",
        {"command": 'grep -rn "foo" sources/normalized/'},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


def test_denies_read_chained_after_a_memoria_cli_call(project_dir):
    """A command carrying shell operators is matched raw: nothing hides
    behind the CLI allowance."""
    result = run_hook(
        "Bash",
        {"command": "memoria rebuild && cat sources/normalized/SRC-000001.md"},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert result.stderr.strip() == ROUTER_MESSAGE


# --- the message names the tools that can actually answer ------------------


def test_router_message_points_at_search_text_header_filters(project_dir):
    """#111 landed `from`/`to` on search_text, so an agent that was about to
    grep for a sender is told the filter exists."""
    result = run_hook(
        "Bash",
        {"command": "grep -rl 'skilling@enron.com' sources/normalized/"},
        project_dir=project_dir,
    )
    assert result.returncode == 2
    assert "search_text" in result.stderr
    assert "from_/to" in result.stderr
    assert "read(ref)" in result.stderr
