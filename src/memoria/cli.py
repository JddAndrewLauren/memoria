"""Memoria CLI entry point."""

import argparse
import os
import sys
from pathlib import Path

from memoria.validate import validate

EVIDENCE_ROOT_ENV_VAR = "MEMORIA_EVIDENCE_ROOT"
DEFAULT_EVIDENCE_ROOT = "../thoreau-evidence"


def evidence_root() -> Path:
    return Path(os.environ.get(EVIDENCE_ROOT_ENV_VAR, DEFAULT_EVIDENCE_ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="memoria")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "validate", help="Verify the raw evidence corpus against its manifest"
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        errors = validate(evidence_root())
        for error in errors:
            print(error)
        if errors:
            return 1
        print("validate: OK")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
