"""Every module under ``memoria`` imports on its own (FINAL-GATE item 1 on
#194).

A batch-introduced import cycle - ``record_extractor`` -> ``human_touched``
-> ``index`` -> ``records`` -> ``record_extractor`` - meant ``import
memoria.record_extractor`` and ``import memoria.records`` each raised
``ImportError`` for a partially initialized module, depending on which
module in the cycle happened to be imported first. The project's test suite
stayed green through this because every test file reaches a loop-breaking
module first (directly or via a fixture), so the broken order was never
exercised on its own.

This runs each module's import in a fresh subprocess - never the process
already running the suite, which has every module cached in ``sys.modules``
and so cannot see an ordering-dependent cycle at all - so import order
starts fresh for each one, the same as a user's first ``python -c "import
memoria.<mod>"``.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
PACKAGE_ROOT = SRC_ROOT / "memoria"


def _public_modules() -> list[str]:
    """Every public module under ``src/memoria``, dotted: ``*.py`` at the
    package root plus the ``mcp`` and ``web`` sub-packages, skipping
    ``__init__``/private (leading-underscore) names."""
    modules = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT)
        parts = relative.with_suffix("").parts
        if parts[-1] == "__init__" or parts[-1].startswith("_"):
            continue
        modules.append(".".join(parts))
    return sorted(modules)


@pytest.mark.parametrize("module", _public_modules())
def test_module_imports_in_isolation(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=SRC_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"import {module} failed in a fresh subprocess:\n{result.stderr}"
    )
