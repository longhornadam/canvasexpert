"""Live probe: can the saved PAT reach the New Quizzes API?

A hand-run diagnostic, not part of the suite. It lived in api/tests/ and was the
one permanent skip there, since it needs a real course id and a saved token that
no automated run has. Moved here so a skip in `pytest api/tests` means something.
Run it explicitly when you want to re-measure the New Quizzes auth question:

    # PowerShell
    $env:CE_LIVE_COURSE = "12345"          # course id to probe
    $env:CE_LIVE_NQ_ASSIGNMENT = "67890"   # optional: a New Quiz assignment_id
    py -m pytest api/scripts/probe_newquizzes_auth.py -s

It needs a token saved in the app (keyring) — the same one the Web UI uses. The
test asserts only that we get a *conclusive* auth signal (not a network error),
then prints the verdict on whether a PAT works for New Quizzes. It deliberately
does NOT assert that the PAT works or fails — that's the open question we're
measuring (see api/README.md and api/diagnose_newquizzes.py). Use `-s` to see
the per-probe output.
"""
import os

import pytest

from api.diagnose_newquizzes import run_diagnostics
from api.webui import config

_COURSE = os.environ.get("CE_LIVE_COURSE")
_ASSIGNMENT = os.environ.get("CE_LIVE_NQ_ASSIGNMENT")

pytestmark = pytest.mark.skipif(
    not (_COURSE and config.token_is_set() and config.get_canvas_base()),
    reason="set CE_LIVE_COURSE and save a Canvas token to run the live NQ probe",
)


def test_new_quizzes_auth_probe(capsys):
    results, summary = run_diagnostics(_COURSE, _ASSIGNMENT)

    # Print the full report so `-s` surfaces the actual finding.
    print("\n=== New Quizzes auth probe ===")
    for r in results:
        print(f"[{r['status']}] {r['label']} -> {r['interpretation']}")
    print("VERDICT:", summary["verdict"])

    # 1. The token must be valid at all (core API sanity probe).
    assert results[0]["status"] == 200, (
        f"Token failed the core-API sanity check: {results[0]['interpretation']}")

    # 2. The New Quizzes READ probe must return a *conclusive* auth signal —
    #    a real status code, not a network error. 200/401/403/400/409 are all
    #    conclusive; None (network/exception) is a broken test, not a finding.
    nq_read = results[1]["status"]
    assert nq_read in (200, 400, 401, 403, 409), (
        f"Inconclusive New Quizzes probe (HTTP {nq_read}): {results[1]['body']}")
