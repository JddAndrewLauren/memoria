#!/usr/bin/env bash
# Walk the M5 gate (docs/gates/m5-gate-walk.md) end to end - the manuscript
# layer's acts in the core, the tints, the supplied context and the Settle
# click in a real browser - and leave an artifact a person can read.
#
# Usage: scripts/gate-m5.sh [--artifact PATH] [--keep]
#
#   --artifact PATH  where to write the run's record (default gate/last-run.md)
#   --keep           do not delete the scratch repository afterwards, and
#                    print where it is
#
# A copy of scripts/gate-m5.sh with the phases M5 needs (gate/README.md:
# "do not generalise them first"). The prepared repository is the same
# seeded corpus; everything the gate is about - the legacy chapter, the
# piece's brief, the authorized draft, the audit and the settlement - is
# laid down by gate/m5/records.py in three core phases, with the browser
# looking between them. None of it may land in the checkout you are
# working in, which is why it all happens in a `mktemp -d`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"

artifact="$REPO/gate/last-run.md"
keep=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --artifact) artifact="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
        --keep) keep=1; shift ;;
        *) echo "gate-m5: unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -x .venv/bin/memoria ]]; then
    echo "gate-m5: no .venv - run scripts/run.sh once to install both toolchains" >&2
    exit 1
fi
MEMORIA="$REPO/.venv/bin/memoria"
PYTHON="$REPO/.venv/bin/python"

if [[ ! -d ui/node_modules ]]; then
    (cd ui && npm install)
fi
(cd ui && npm run build >/dev/null)

scratch="$(mktemp -d -t memoria-gate-m5-XXXXXX)"
# Logs live beside the scratch repository, not in it: the seed commit adds
# everything, and a tracked log the server keeps writing would be an
# uncommitted human modification to the dirty-tree rule.
logs="$(mktemp -d -t memoria-gate-m5-logs-XXXXXX)"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    if [[ "$keep" -eq 1 ]]; then
        echo "gate-m5: scratch repository kept at $scratch"
    else
        rm -rf "$scratch"
    fi
    rm -rf "$logs"
}
trap cleanup EXIT

# --- the prepared repository -------------------------------------------------
mkdir -p "$scratch/evidence/raw"
cp "$REPO"/gate/corpus/*.eml "$scratch/evidence/raw/"
printf '[project]\nname = "memoria-gate-scratch"\nversion = "0.0.0"\n' > "$scratch/pyproject.toml"
# The index directory is derived state and never tracked, as in this
# repository's own .gitignore: a tracked index.db would read as an
# uncommitted human modification to the dirty-tree rule the moment a pass
# touched it.
printf '.memoria%s\n' / > "$scratch/.gitignore"
git -C "$scratch" init -q
# The author's identity: every hand commit below is theirs, and the
# human-touched flag is defined over exactly that distinction.
git -C "$scratch" config user.name "M5 gate walk"
git -C "$scratch" config user.email "gate@memoria.invalid"

export MEMORIA_EVIDENCE_ROOT="$scratch/evidence"
export MEMORIA_GATE_ARTIFACT="$artifact"
export MEMORIA_BIN="$MEMORIA"
cd "$scratch"
"$MEMORIA" seed-subjects > "$logs/prepare.log" 2>&1
"$MEMORIA" normalize >> "$logs/prepare.log" 2>&1
mkdir -p "$scratch/subjects/people"
cp "$REPO/gate/skilling.md" "$scratch/subjects/people/skilling.md"
git -C "$scratch" add -A
git -C "$scratch" commit -qm "The gate's seeded state, before the session"
seed_commit="$(git -C "$scratch" rev-parse --short HEAD)"
"$MEMORIA" rebuild >> "$logs/prepare.log" 2>&1
cd "$REPO"

records="$(sed -n 's/^normalize: converted \([0-9]*\).*/\1/p' "$logs/prepare.log" | head -1)"
if [[ -z "$records" || "$records" == "0" ]]; then
    echo "gate-m5: the corpus produced no records - the walk would pass over an empty page" >&2
    cat "$logs/prepare.log" >&2
    exit 1
fi

# --- the artifact's frame ------------------------------------------------------
mkdir -p "$(dirname "$artifact")"
{
    echo "# M5 gate walk — run of $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo
    echo "Walked by \`scripts/gate-m5.sh\`: the manuscript layer in the core, the tints,"
    echo "the supplied context and the Settle click in Chromium at 1280×720, over a"
    echo "scratch repository built from"
    echo "\`gate/corpus/\` (${records:-?} records normalized, seeded at \`$seed_commit\`)"
    echo "and the staged session in \`gate/m5/session.jsonl\`. Memoria at"
    echo "\`$(git -C "$REPO" rev-parse --short HEAD)\`."
    echo
    echo "## What each step did"
    echo
} > "$artifact"

# --- the phases -------------------------------------------------------------------
# The core acts are laid down by gate/m5/records.py; each browser phase looks
# at what the core act before it laid down: the tints and the supplied
# context after acts 1-4; the audit's results, the Settle click and the tint
# that returned after act 5; current-only-through-re-audit after act 6.
browser() {
    (cd ui && MEMORIA_GATE_URL="http://127.0.0.1:$port" \
              MEMORIA_GATE_REPO="$scratch" \
              MEMORIA_GATE_ARTIFACT="$artifact" \
              MEMORIA_GATE_PHASE="$1" \
              npm run gate -- m5-gate-walk)
}
core() {
    (cd "$scratch" && "$PYTHON" "$REPO/gate/m5/records.py" "$1")
}

walk_status=0
core_status=0
failed_at=""

# --- acts 1-4, in the core ---------------------------------------------------------
# Captured like every later phase, so a failure here still ends in the
# artifact's `## Result` instead of exiting through the trap.
set +e
core before; core_status=$?; failed_at="records.py before"
set -e

if [[ "$core_status" -eq 0 ]]; then
    # --- the server -------------------------------------------------------------
    (cd "$scratch" && exec "$PYTHON" -m uvicorn memoria.web.app:create_app \
        --factory --host 127.0.0.1 --port "$port" > "$logs/server.log" 2>&1) &
    server_pid=$!

    for _ in $(seq 1 60); do
        if curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
            break
        fi
        if ! kill -0 "$server_pid" 2>/dev/null; then
            echo "gate-m5: the server exited during startup:" >&2
            cat "$logs/server.log" >&2
            exit 1
        fi
        sleep 0.5
    done
    if ! curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
        echo "gate-m5: the server never came up on port $port" >&2
        cat "$logs/server.log" >&2
        exit 1
    fi

    # --- the three browser phases, with the core acts between them -----------------
    set +e
    browser before; walk_status=$?
    if [[ "$walk_status" -eq 0 ]]; then core audit; core_status=$?; failed_at="records.py audit"; fi
    if [[ "$walk_status" -eq 0 && "$core_status" -eq 0 ]]; then browser audit; walk_status=$?; fi
    if [[ "$walk_status" -eq 0 && "$core_status" -eq 0 ]]; then core reaudit; core_status=$?; failed_at="records.py reaudit"; fi
    if [[ "$walk_status" -eq 0 && "$core_status" -eq 0 ]]; then browser after; walk_status=$?; fi
    set -e
fi

{
    echo
    echo "## Result"
    echo
    if [[ "$walk_status" -eq 0 && "$core_status" -eq 0 ]]; then
        echo "**Passed.** Every step behaved as \`docs/gates/m5-gate-walk.md\` describes."
    elif [[ "$core_status" -ne 0 ]]; then
        echo "**Failed** in the core acts (\`gate/m5/$failed_at\`, exit $core_status)."
        echo "The act that failed is the last one missing from the list above."
    else
        echo "**Failed** (playwright exit $walk_status). The step that failed is the last"
        echo "one missing from the list above; its trace is under \`ui/test-results/\`."
    fi
} >> "$artifact"

echo
echo "gate-m5: artifact written to $artifact"
[[ "$core_status" -eq 0 ]] || exit "$core_status"
exit "$walk_status"
