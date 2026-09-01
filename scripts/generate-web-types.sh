#!/usr/bin/env bash
# Regenerate the TypeScript client types from the FastAPI app's OpenAPI
# schema (#64). This is the mitigation `docs/adr/0002-ui-is-a-react-client.md`
# names for a two-language stack in a repo with no CI: a backend field
# rename becomes a compile error in `ui/`, not a runtime surprise nobody
# sees.
#
# Usage: scripts/generate-web-types.sh [output-path]
#   output-path defaults to ui/src/api/schema.d.ts, the committed file.
#   Run with no argument after changing src/memoria/web/, then commit the
#   result. `tests/test_web_types.py` fails the suite when it goes stale.
#
# Exits with a line starting "TOOLCHAIN-UNAVAILABLE:" on stderr, rather than
# a bare command-not-found or a raw npx failure, when the venv or node/npx
# is missing - so a caller (the test included) can tell "the tool isn't set
# up here" from "the generated output actually changed".
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${1:-ui/src/api/schema.d.ts}"

PYTHON=".venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    echo "TOOLCHAIN-UNAVAILABLE: no $PYTHON - run the env gate (uv venv .venv && uv pip install --python .venv/bin/python -e \".[dev]\") first" >&2
    exit 3
fi

if ! command -v npx >/dev/null 2>&1; then
    echo "TOOLCHAIN-UNAVAILABLE: npx not found on PATH - node/npm is required to regenerate TypeScript types" >&2
    exit 3
fi

SCHEMA_JSON="$(mktemp)"
trap 'rm -f "$SCHEMA_JSON"' EXIT

"$PYTHON" -c "
import json
from memoria.web.app import create_app

print(json.dumps(create_app().openapi()))
" > "$SCHEMA_JSON"

mkdir -p "$(dirname "$OUT")"
if ! npx --yes openapi-typescript@7 "$SCHEMA_JSON" -o "$OUT"; then
    echo "TOOLCHAIN-UNAVAILABLE: npx could not run openapi-typescript (offline, or the package registry is unreachable)" >&2
    exit 3
fi
