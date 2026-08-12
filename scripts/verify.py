"""Run the repository's dependency-free acceptance checks."""

from __future__ import annotations

import compileall
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "tests"


def main() -> int:
    if str(SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(SOURCE_ROOT))

    suite = unittest.defaultTestLoader.discover(str(TEST_ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    if not compileall.compile_dir(SOURCE_ROOT, quiet=1):
        return 1
    if not compileall.compile_dir(TEST_ROOT, quiet=1):
        return 1

    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(SOURCE_ROOT)
        if not existing_pythonpath
        else str(SOURCE_ROOT) + os.pathsep + existing_pythonpath
    )
    smoke = subprocess.run(
        [sys.executable, "-m", "personal_ai_agent", "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
    )
    return smoke.returncode


if __name__ == "__main__":
    raise SystemExit(main())
