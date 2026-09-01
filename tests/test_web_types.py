"""The committed TypeScript client types must match the current schema (#64).

`docs/adr/0002-ui-is-a-react-client.md`: TypeScript types are generated
rather than hand-written, so a backend field rename becomes a compile error
in `ui/` instead of a runtime surprise nobody sees - but only while the
committed file is kept in sync. This test is the check that fails when it
is not: run `scripts/generate-web-types.sh` and commit the result.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate-web-types.sh"
COMMITTED = REPO_ROOT / "ui" / "src" / "api" / "schema.d.ts"


def test_the_committed_typescript_types_are_not_stale(tmp_path):
    assert COMMITTED.is_file(), "no committed types - run scripts/generate-web-types.sh"

    regenerated = tmp_path / "schema.d.ts"
    subprocess.run(
        ["bash", str(SCRIPT), str(regenerated)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        timeout=120,
    )

    assert regenerated.read_text(encoding="utf-8") == COMMITTED.read_text(
        encoding="utf-8"
    ), "ui/src/api/schema.d.ts is stale - run scripts/generate-web-types.sh and commit it"
