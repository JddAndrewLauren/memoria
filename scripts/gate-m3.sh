#!/usr/bin/env bash
# Walk the M3 gate (docs/gates/m3-gate-walk.md) end to end, in a real
# browser, and leave an artifact a person can read.
#
# Usage: scripts/gate-m3.sh [--artifact PATH] [--keep]
#
#   --artifact PATH  where to write the run's record (default gate/last-run.md)
#   --keep           do not delete the scratch repository afterwards, and
#                    print where it is
#
# What this owns, and why it is a shell script rather than a Playwright
# `webServer` block: the walk needs a *prepared repository*, not just a
# server. Seeding subjects, normalizing the corpus, writing the entry,
# committing it and rebuilding the index all happen here, in a throwaway
# checkout, because two of the seven steps are durable writes that commit -
# and this repository is not a place to commit `subjects/people/skilling.md`
# into (the gate doc's own Cleanup section).
#
# The corpus is `gate/corpus/`, three invented Enron-shaped messages, and it
# is small deliberately: the four-custodian slice takes ~50 minutes to
# normalize and over an hour to rebuild (#172 times the phases; the fix waits
# on its numbers), which makes a check nobody can run twice. See gate/README.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO="$PWD"

artifact="$REPO/gate/last-run.md"
keep=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --artifact) artifact="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"; shift 2 ;;
        --keep) keep=1; shift ;;
        *) echo "gate-m3: unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -x .venv/bin/memoria ]]; then
    echo "gate-m3: no .venv - run scripts/run.sh once to install both toolchains" >&2
    exit 1
fi
MEMORIA="$REPO/.venv/bin/memoria"

if [[ ! -d ui/node_modules ]]; then
    (cd ui && npm install)
fi
# Always rebuilt: a gate walk that drove last week's bundle would answer the
# wrong question.
(cd ui && npm run build >/dev/null)

scratch="$(mktemp -d -t memoria-gate-m3-XXXXXX)"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
server_pid=""

cleanup() {
    if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    if [[ "$keep" -eq 1 ]]; then
        echo "gate-m3: scratch repository kept at $scratch"
    else
        rm -rf "$scratch"
    fi
}
trap cleanup EXIT

# --- the prepared repository -------------------------------------------------
mkdir -p "$scratch/evidence/raw"
cp "$REPO"/gate/corpus/*.eml "$scratch/evidence/raw/"
# `memoria.repository.discover_root` walks up for a pyproject.toml, so the
# scratch checkout needs one to be a repository at all.
printf '[project]\nname = "memoria-gate-scratch"\nversion = "0.0.0"\n' > "$scratch/pyproject.toml"
git -C "$scratch" init -q
git -C "$scratch" config user.name "M3 gate walk"
git -C "$scratch" config user.email "gate@memoria.invalid"

export MEMORIA_EVIDENCE_ROOT="$scratch/evidence"
cd "$scratch"
"$MEMORIA" seed-subjects > "$scratch/prepare.log" 2>&1
"$MEMORIA" normalize >> "$scratch/prepare.log" 2>&1
mkdir -p "$scratch/subjects/people"
cp "$REPO/gate/skilling.md" "$scratch/subjects/people/skilling.md"
git -C "$scratch" add -A
git -C "$scratch" commit -qm "The gate's seeded state, before the walk writes anything"
seed_commit="$(git -C "$scratch" rev-parse --short HEAD)"
"$MEMORIA" rebuild >> "$scratch/prepare.log" 2>&1
cd "$REPO"

records="$(sed -n 's/^normalize: converted \([0-9]*\).*/\1/p' "$scratch/prepare.log" | head -1)"
if [[ -z "$records" || "$records" == "0" ]]; then
    echo "gate-m3: the corpus produced no records - the walk would pass over an empty page" >&2
    cat "$scratch/prepare.log" >&2
    exit 1
fi

# --- the server --------------------------------------------------------------
(cd "$scratch" && exec "$REPO/.venv/bin/python" -m uvicorn memoria.web.app:create_app \
    --factory --host 127.0.0.1 --port "$port" > "$scratch/server.log" 2>&1) &
server_pid=$!

for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        echo "gate-m3: the server exited during startup:" >&2
        cat "$scratch/server.log" >&2
        exit 1
    fi
    sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$port/api/subjects" >/dev/null 2>&1; then
    echo "gate-m3: the server never came up on port $port" >&2
    cat "$scratch/server.log" >&2
    exit 1
fi

# --- the walk ----------------------------------------------------------------
mkdir -p "$(dirname "$artifact")"
{
    echo "# M3 gate walk — run of $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo
    echo "Walked by \`scripts/gate-m3.sh\` in Chromium at 1280×720, over a scratch"
    echo "repository built from \`gate/corpus/\` (${records:-?} records normalized,"
    echo "seeded at \`$seed_commit\`). Memoria at \`$(git -C "$REPO" rev-parse --short HEAD)\`."
    echo
    echo "## What each step did"
    echo
} > "$artifact"

set +e
(cd ui && MEMORIA_GATE_URL="http://127.0.0.1:$port" \
          MEMORIA_GATE_REPO="$scratch" \
          MEMORIA_GATE_ARTIFACT="$artifact" \
          npm run gate -- m3-gate-walk)
walk_status=$?
set -e

# Step 2's other half: the write is durable *and attributed*, which is a fact
# about the git history rather than about the page.
commit_subject="$(git -C "$scratch" log -1 --format='%s')"
commit_author="$(git -C "$scratch" log -1 --format='%an')"
commit_paths="$(git -C "$scratch" log -1 --name-only --format='')"
commit_paths="$(echo "$commit_paths" | tr -s '\n' ' ' | sed 's/ *$//')"

{
    echo
    echo "## The durable write, in git"
    echo
    if [[ "$commit_paths" == "subjects/people/skilling.md" ]]; then
        echo "- The last commit is path-scoped to \`subjects/people/skilling.md\` and"
        echo "  nothing else, authored by \`$commit_author\`: \"$commit_subject\""
    else
        echo "- **Unexpected:** the last commit touched \`$commit_paths\`, not"
        echo "  \`subjects/people/skilling.md\` alone. Subject: \"$commit_subject\""
    fi
    echo
    echo "## Result"
    echo
    if [[ "$walk_status" -eq 0 ]]; then
        echo "**Passed.** All seven steps behaved as \`docs/gates/m3-gate-walk.md\` describes."
    else
        echo "**Failed** (playwright exit $walk_status). The step that failed is the last"
        echo "one missing from the list above; its trace is under \`ui/test-results/\`."
    fi
} >> "$artifact"

echo
echo "gate-m3: artifact written to $artifact"
[[ "$commit_paths" == "subjects/people/skilling.md" ]] || {
    echo "gate-m3: the durable write's commit was not path-scoped as expected" >&2
    exit 1
}
exit "$walk_status"
