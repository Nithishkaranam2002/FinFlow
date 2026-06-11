#!/usr/bin/env python3
"""Run Alembic migrations programmatically."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
