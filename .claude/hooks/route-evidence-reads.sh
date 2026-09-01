#!/usr/bin/env bash
# PreToolUse router: direct reads of the evidence repo are redirected to the
# Memoria tool surface. Router, not wall - see docs/poc-plan.md section 3.
input=$(cat)
target=$(printf '%s' "$input" | python3 -c "
import json, sys
d = json.load(sys.stdin)
i = d.get('tool_input') or {}
vals = [i.get('file_path'), i.get('path')]
if d.get('tool_name') == 'Glob':
    vals.append(i.get('pattern'))
print(next((v for v in vals if v and 'thoreau-evidence' in v), ''))
" 2>/dev/null)
if [ -n "$target" ]; then
  echo "Evidence reads route through the Memoria MCP tools (search / read_source / expand): same verbatim text plus the curated overlay - entry links, exclusions, settlements citing the paragraph - and the read lands in the session ledger (events.jsonl). Direct file access to the evidence repo is disabled in this workspace." >&2
  exit 2
fi
exit 0
