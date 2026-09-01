#!/usr/bin/env bash
# PreToolUse router: direct reads of the evidence repo are redirected to the
# Memoria tool surface. Router, not wall - see docs/poc-plan.md section 3.
# The evidence path comes from MEMORIA_EVIDENCE_ROOT, never a hardcoded corpus
# name: the Thoreau corpus was retired 2026-09-01 and a literal match on it
# would make this router silently match nothing -- a failure with no error
# message. With no corpus configured there is nothing to route, and the hook
# correctly does nothing.
input=$(cat)
if [ -z "${MEMORIA_EVIDENCE_ROOT:-}" ]; then
  exit 0
fi
target=$(printf '%s' "$input" | MEMORIA_EVIDENCE_ROOT="$MEMORIA_EVIDENCE_ROOT" python3 -c "
import json, os, sys
root = os.path.realpath(os.environ['MEMORIA_EVIDENCE_ROOT'])
d = json.load(sys.stdin)
i = d.get('tool_input') or {}
vals = [i.get('file_path'), i.get('path')]
if d.get('tool_name') == 'Glob':
    vals.append(i.get('pattern'))
def inside(v):
    # realpath resolves '..' and symlinks so a relative or indirect path to the
    # evidence repo is caught the same as an absolute one.
    p = os.path.realpath(v)
    return p == root or p.startswith(root + os.sep)
print(next((v for v in vals if v and inside(v)), ''))
" 2>/dev/null)
if [ -n "$target" ]; then
  echo "Evidence reads route through the Memoria MCP tools (search / read_source / expand): same verbatim text plus the curated overlay - entry links, exclusions, settlements citing the paragraph - and the read lands in the session ledger (events.jsonl). Direct file access to the evidence repo is disabled in this workspace." >&2
  exit 2
fi
exit 0
