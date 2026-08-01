"""Run the Panels console JavaScript suite under pytest.

panels_clipboard.js is a plain browser script: no build step, no bundler, and
no JS test runner in this repo. Its tests run on node's built-in runner
instead, matching api/tests/smartdeck/test_display_js.py's bridge so
`py -m pytest api/tests` stays the single verification gate.

Node is not a declared dependency of this project, so a machine without it
skips these. That is a real coverage hole, not a pass: the skip reason says
so, and test_javascript_suites_are_discovered fails loudly if the suite
itself goes missing.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[2]
SUITES = sorted(HERE.glob("*.test.mjs"))
NODE = shutil.which("node")


def test_javascript_suites_are_discovered():
    """Guard the glob: a rename should fail here, not silently test nothing."""
    assert SUITES, f"no *.test.mjs suites found in {HERE}"


@pytest.mark.skipif(
    NODE is None,
    reason="node is not installed, so the Panels clipboard JavaScript went untested")
@pytest.mark.parametrize("suite", SUITES, ids=lambda path: path.name)
def test_panels_javascript(suite):
    """Run one node suite and surface its output verbatim when it fails."""
    result = subprocess.run(
        [NODE, "--test", str(suite)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            f"{suite.name} failed (exit {result.returncode})\n\n"
            f"{result.stdout}\n{result.stderr}",
            pytrace=False,
        )
