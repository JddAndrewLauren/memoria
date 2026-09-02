#!/usr/bin/env bash
# The one command that runs both test suites (#24's acceptance criteria):
# pytest for the core and its adapters, vitest for the React client.
# Assumes both toolchains are already installed - see "Installing" in
# README.md, or run scripts/run.sh once, which installs both.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

.venv/bin/pytest tests/ -q
(cd ui && npm test)
