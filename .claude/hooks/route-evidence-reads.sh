#!/usr/bin/env bash
# PreToolUse router: direct reads of the evidence repo, and of this repo's
# own derived records, are redirected to the Memoria tool surface. Router,
# not wall - see docs/poc-plan.md section 3.
#
# Two roots, checked independently:
#   - MEMORIA_EVIDENCE_ROOT, when set: the sibling evidence repo. Never a
#     hardcoded corpus name -- the Thoreau corpus was retired 2026-09-01 and
#     a literal match on it would make this router silently match nothing,
#     a failure with no error message. Unset means there is nothing to route
#     for this root, and the hook correctly does nothing for it.
#   - This repo's own sources/normalized/ and .memoria/, always, whether or
#     not MEMORIA_EVIDENCE_ROOT is set. The M1 gate (#15) found the bypass
#     was never the raw evidence: normalized records and the index are what
#     a session actually reads, and both exist regardless of whether an
#     evidence corpus is configured.
repo_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
input=$(cat)
tool_name=$(printf '%s' "$input" | python3 -c "import json, sys; print(json.load(sys.stdin).get('tool_name', ''))" 2>/dev/null)

# Says only what is true today. It used to promise the curated overlay and
# a session ledger, and to name read_source/expand -- tools part 11 section
# 25 withdrew in favour of the unified read(ref). A router that advertises
# what it cannot deliver teaches people to ignore it. #13 restored the
# ledger clause; issue #20 still owes the overlay clause.
message="Evidence reads route through the Memoria MCP tool read(ref): the same verbatim text, addressed by SRC- ID, paragraph anchor, or repository path, and the read lands in the session ledger (events.jsonl) - see docs/tool-surface.md. Direct file access to the evidence repo is disabled in this workspace."

if [ "$tool_name" = "Bash" ]; then
  # Bash text is not a path, and this router does not attempt to parse shell
  # -- a router only has to make the routed path the obvious one, and every
  # bypass the M1 gate observed named the directory literally. Exact-string
  # containment against the raw command is enough for that job; anything
  # quoting-aware or variable-expanding is wall-building effort a router
  # deliberately does not spend.
  command=$(printf '%s' "$input" | python3 -c "import json, sys; print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))" 2>/dev/null)
  needles=("sources/normalized" ".memoria/")
  if [ -n "${MEMORIA_EVIDENCE_ROOT:-}" ]; then
    needles+=("$(python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$MEMORIA_EVIDENCE_ROOT")")
  fi
  for needle in "${needles[@]}"; do
    if [ -n "$needle" ] && printf '%s' "$command" | grep -qF -- "$needle"; then
      echo "$message" >&2
      exit 2
    fi
  done
  exit 0
fi

target=$(printf '%s' "$input" | MEMORIA_EVIDENCE_ROOT="${MEMORIA_EVIDENCE_ROOT:-}" MEMORIA_REPO_ROOT="$repo_root" python3 -c "
import json, os, sys
d = json.load(sys.stdin)
i = d.get('tool_input') or {}
vals = [i.get('file_path'), i.get('path')]
if d.get('tool_name') == 'Glob':
    vals.append(i.get('pattern'))

roots = []
evidence_root = os.environ.get('MEMORIA_EVIDENCE_ROOT')
if evidence_root:
    roots.append(os.path.realpath(evidence_root))
repo_root = os.environ['MEMORIA_REPO_ROOT']
roots.append(os.path.realpath(os.path.join(repo_root, 'sources', 'normalized')))
roots.append(os.path.realpath(os.path.join(repo_root, '.memoria')))

def inside(v):
    # realpath resolves '..' and symlinks so a relative or indirect path to
    # any routed root is caught the same as an absolute one.
    p = os.path.realpath(v)
    return any(p == root or p.startswith(root + os.sep) for root in roots)

print(next((v for v in vals if v and inside(v)), ''))
" 2>/dev/null)
if [ -n "$target" ]; then
  echo "$message" >&2
  exit 2
fi
exit 0
