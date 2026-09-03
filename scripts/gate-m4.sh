#!/usr/bin/env bash
# Walk the M4 gate (docs/gates/m4-gate-walk.md) end to end - the record
# extractor's three acts in the core, the click-through in a real browser -
# and leave an artifact a person can read.
#
# Usage: scripts/gate-m4.sh [--artifact PATH] [--keep]
#
#   --artifact PATH  where to write the run's record (default gate/last-run.md)
#   --keep           do not delete the scratch repository afterwards, and
#                    print where it is
#
# A copy of scripts/gate-m3.sh with the preparation M4 needs (gate/README.md:
# "do not generalise them first"). The prepared repository here carries a
# manuscript section, a derived research session that touched it, and the
# records the extractor wrote from that session - the things the gate is
# about - and none of it may land in the checkout you are working in, which
# is why it all happens in a `mktemp -d`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"

artifact="$REPO/gate/last-run.md"
keep=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --artifact) artifact="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
        --keep) keep=1; shift ;;
        *) echo "gate-m4: unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -x .venv/bin/memoria ]]; then
    echo "gate-m4: no .venv - run scripts/run.sh once to install both toolchains" >&2
    exit 1
fi
MEMORIA="$REPO/.venv/bin/memoria"
PYTHON="$REPO/.venv/bin/python"

if [[ ! -d ui/node_modules ]]; then
    (cd ui && npm install)
fi
(cd ui && npm run build >/dev/null)

scratch="$(mktemp -d -t memoria-gate-m4-XXXXXX)"
# Logs live beside the scratch repository, not in it: the seed commit adds
# everything, and a tracked log the server keeps writing would be an
# uncommitted human modification to the dirty-tree rule.
logs="$(mktemp -d -t memoria-gate-m4-logs-XXXXXX)"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    if [[ "$keep" -eq 1 ]]; then
        echo "gate-m4: scratch repository kept at $scratch"
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
git -C "$scratch" config user.name "M4 gate walk"
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
    echo "gate-m4: the corpus produced no records - the walk would pass over an empty page" >&2
    cat "$logs/prepare.log" >&2
    exit 1
fi

# --- the artifact's frame ------------------------------------------------------
mkdir -p "$(dirname "$artifact")"
{
    echo "# M4 gate walk — run of $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo
    echo "Walked by \`scripts/gate-m4.sh\`: the record extractor in the core, the"
    echo "click-through in Chromium at 1280×720, over a scratch repository built from"
    echo "\`gate/corpus/\` (${records:-?} records normalized, seeded at \`$seed_commit\`)"
    echo "and the staged session in \`gate/m4/session.jsonl\`. Memoria at"
    echo "\`$(git -C "$REPO" rev-parse --short HEAD)\`."
    echo
    echo "## What each step did"
    echo
} > "$artifact"

# --- acts 1 and 2, in the core --------------------------------------------------
(cd "$scratch" && "$PYTHON" "$REPO/gate/m4/records.py" before)

# --- the server -----------------------------------------------------------------
(cd "$scratch" && exec "$PYTHON" -m uvicorn memoria.web.app:create_app \
    --factory --host 127.0.0.1 --port "$port" > "$logs/server.log" 2>&1) &
server_pid=$!

for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        echo "gate-m4: the server exited during startup:" >&2
        cat "$logs/server.log" >&2
        exit 1
    fi
    sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
    echo "gate-m4: the server never came up on port $port" >&2
    cat "$logs/server.log" >&2
    exit 1
fi

# --- the click-through, in the browser -------------------------------------------
set +e
(cd ui && MEMORIA_GATE_URL="http://127.0.0.1:$port" \
          MEMORIA_GATE_REPO="$scratch" \
          MEMORIA_GATE_ARTIFACT="$artifact" \
          npm run gate -- m4-gate-walk)
walk_status=$?
set -e

# --- act 3 and validate, in the core ----------------------------------------------
# After the browser steps: the hand edit and the note change the entry the
# browser step 5 then re-reads, so the browser's second look is real.
after_status=0
if [[ "$walk_status" -eq 0 ]]; then
    set +e
    (cd "$scratch" && "$PYTHON" "$REPO/gate/m4/records.py" after)
    after_status=$?
    set -e
    if [[ "$after_status" -eq 0 ]]; then
        set +e
        (cd ui && MEMORIA_GATE_URL="http://127.0.0.1:$port" \
                  MEMORIA_GATE_REPO="$scratch" \
                  MEMORIA_GATE_ARTIFACT="$artifact" \
                  MEMORIA_GATE_PHASE="after" \
                  npm run gate -- m4-gate-walk)
        walk_status=$?
        set -e
    fi
fi

{
    echo
    echo "## Result"
    echo
    if [[ "$walk_status" -eq 0 && "$after_status" -eq 0 ]]; then
        echo "**Passed.** Every step behaved as \`docs/gates/m4-gate-walk.md\` describes."
    elif [[ "$after_status" -ne 0 ]]; then
        echo "**Failed** in the record steps (\`gate/m4/records.py after\`, exit $after_status)."
        echo "The act that failed is the last one missing from the list above."
    else
        echo "**Failed** (playwright exit $walk_status). The step that failed is the last"
        echo "one missing from the list above; its trace is under \`ui/test-results/\`."
    fi
} >> "$artifact"

echo
echo "gate-m4: artifact written to $artifact"
[[ "$after_status" -eq 0 ]] || exit "$after_status"
exit "$walk_status"
