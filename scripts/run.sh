#!/usr/bin/env bash
# The one command that installs, builds and runs everything, from a clean
# checkout (#24's acceptance criteria) - a Python venv for the core and the
# FastAPI app, an npm install and a production build for the React client,
# then a single uvicorn process serving the API under /api and the built
# client at / (memoria.web.app's static-file mount) from one origin.
#
# Usage: scripts/run.sh
# Ctrl-C stops the server. Safe to re-run: an existing .venv or
# ui/node_modules is left alone rather than reinstalled.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
fi

if [[ ! -d ui/node_modules ]]; then
    (cd ui && npm install)
fi

(cd ui && npm run build)

exec .venv/bin/python -m uvicorn memoria.web.app:create_app --factory --host 127.0.0.1 --port 8000
