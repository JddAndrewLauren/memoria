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
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${1:-ui/src/api/schema.d.ts}"
SCHEMA_JSON="$(mktemp)"
trap 'rm -f "$SCHEMA_JSON"' EXIT

.venv/bin/python -c "
import json
from memoria.web.app import create_app

print(json.dumps(create_app().openapi()))
" > "$SCHEMA_JSON"

mkdir -p "$(dirname "$OUT")"
npx --yes openapi-typescript@7 "$SCHEMA_JSON" -o "$OUT"
