"""`python -m scripts.seed` actually runs.

Found by the fresh-clone check, which is the only thing that could have found it: every
other test *imports* `scripts.seed`, and importing binds every name in the module
regardless of the order they appear in. Running it as `__main__` executes top to bottom,
and the `if __name__ == "__main__": main()` block sat above two functions `main` calls —
so the README's fourth setup step died on `NameError: name '_create_rentals_schema' is
not defined` while 181 tests stayed green.

This test runs the script the way the README tells a reader to run it: as a subprocess,
in its own process, with nothing pre-imported. That is the only arrangement in which
definition order matters, which is exactly why the defect survived a suite this size.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_the_seed_script_runs_as_a_module(tmp_path: Path) -> None:
    """The README's `python -m scripts.seed`, verbatim, against a throwaway database."""
    database = tmp_path / "fresh.db"

    finished = subprocess.run(
        [sys.executable, "-m", "scripts.seed"],
        cwd=PROJECT_ROOT,
        env={
            "PATH": "/usr/bin:/bin",
            "DATABASE_URL": f"sqlite:///{database}",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert finished.returncode == 0, (
        "the README's seed step failed.\n"
        f"stdout: {finished.stdout}\nstderr: {finished.stderr}"
    )
    assert database.exists(), "the script reported success but wrote no database"
    assert "seeded" in finished.stdout, finished.stdout


def test_the_seed_script_reports_what_it_wrote(tmp_path: Path) -> None:
    """The line a reader checks their setup against.

    A seed that succeeds silently gives somebody following the README nothing to compare
    against the documented fingerprints — 11 items and 3 quarantine records.
    """
    database = tmp_path / "fresh.db"

    finished = subprocess.run(
        [sys.executable, "-m", "scripts.seed"],
        cwd=PROJECT_ROOT,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": f"sqlite:///{database}"},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert "11 hardware items" in finished.stdout, finished.stdout
    assert "3 quarantine records" in finished.stdout, finished.stdout
