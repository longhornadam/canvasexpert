"""Diagnose whether the saved Canvas token can reach the New Quizzes API.

Background: it's long been *assumed* that a Personal Access Token (PAT) cannot
pull New Quizzes data (`/api/quiz/v1/...`) and that an admin-granted developer
key / OAuth is required — see api/README.md. The official docs only specify
OAuth2 *scopes* per endpoint; they never explicitly say a PAT is rejected. This
script settles it empirically on your own instance.

It is an **auth** probe, not a data pull, so it works against any course you can
reach — even an archived sandbox or an empty collab course with no students. The
status code is what matters:

  200/201            -> the token is accepted here (works).
  400 / 409          -> the request reached the endpoint's logic, i.e. it got
                        PAST auth -> the token IS accepted (400 = bad params on
                        our empty target, 409 = a report is already generating).
  401                -> token's developer key lacks the scope; an admin can grant
                        `url:...|/api/quiz/v1/...` to the key behind your token.
  403                -> the New Quizzes LTI service refuses this token outright;
                        you need a separate admin-issued developer key + OAuth.

The reports POST uses report_type=student_analysis (the CSV with full responses).

Usage:
    py diagnose_newquizzes.py --course <COURSE_ID> [--assignment <NQ_ASSIGNMENT_ID>]

Token + base URL come from the app config (keyring + machine config) — same as
the Web UI. Nothing is written; every call is read-only except a report-create
POST, which only enqueues a report (Canvas already generates these for the UI).
"""
import argparse
import sys
import time

import requests

try:                                  # running as a script from api/
    from webui import config
except ModuleNotFoundError:           # imported as api.diagnose_newquizzes (tests)
    from api.webui import config

# Statuses that prove the request got past authentication/authorization.
_AUTHORIZED = {200, 201, 202, 400, 409}
# Transient gateway/server errors from the quiz-LTI service — not auth failures.
_TRANSIENT = {429, 500, 502, 503, 504}


def _interpret(status: int) -> str:
    if status in (200, 201, 202):
        return "OK — token accepted here (works)."
    if status in (400, 409):
        return ("AUTHORIZED — request reached the endpoint past auth "
                f"(HTTP {status}); the token IS accepted for this surface.")
    if status == 401:
        return ("BLOCKED (401) — the developer key behind this token lacks the "
                "scope. An admin can grant the matching `url:...` scope to the key.")
    if status == 403:
        return ("BLOCKED (403) — New Quizzes refuses this token for THIS course. "
                "Most common cause: your enrollment here is concluded/inactive "
                "(New Quizzes is an LTI tool that needs an ACTIVE enrollment). "
                "Can also mean a missing developer-key scope. Compare with a "
                "course where you're actively enrolled.")
    if status == 404:
        return ("NOT FOUND (404) — wrong id, or the report subresource isn't "
                "available for this quiz/course (often follows a 403 on the course).")
    if status in _TRANSIENT:
        return (f"TRANSIENT (HTTP {status}) — reached the quiz-LTI service, which "
                "errored at the gateway (flaky, or no submissions to report on). "
                "This is NOT an auth failure; retry.")
    return f"Unexpected HTTP {status} — inspect the body."


def _probe(label, method, url, *, data=None, params=None, retries=0):
    """Issue one request; return a structured result dict (never raises).

    Retries up to `retries` times on transient 5xx/429 (the quiz-LTI gateway is
    known-flaky) so a transient blip isn't mistaken for the real result.
    """
    token = config.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, headers=headers, data=data,
                                 params=params, timeout=20)
        except requests.RequestException as e:
            last_exc = e
            break
        if r.status_code in _TRANSIENT and attempt < retries:
            time.sleep(1.5 * (attempt + 1))
            continue
        return {
            "label": label, "method": method, "url": url,
            "status": r.status_code,
            "authorized": r.status_code in _AUTHORIZED,
            "interpretation": _interpret(r.status_code),
            "body": (r.text or "")[:300],
        }
    return {"label": label, "method": method, "url": url,
            "status": None, "authorized": False,
            "interpretation": f"NETWORK ERROR — {last_exc}", "body": ""}


def _find_nq_assignment(base, course_id):
    """Find a New Quiz's assignment_id via the PAT-friendly core API.

    New Quizzes surface in the core assignments list with
    is_quiz_lti_assignment == True. Lets us probe the reports endpoint even when
    the /api/quiz/v1 list itself is forbidden.
    """
    token = config.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base}/api/v1/courses/{course_id}/assignments",
                         headers=headers, params={"per_page": 100}, timeout=20)
        if r.status_code != 200:
            return None
        for a in r.json():
            if a.get("is_quiz_lti_assignment"):
                return a.get("id")
    except (requests.RequestException, ValueError):
        return None
    return None


def _find_classic_quiz(base, course_id):
    """Find a Classic quiz id (the PAT control case)."""
    token = config.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base}/api/v1/courses/{course_id}/quizzes",
                         headers=headers, params={"per_page": 100}, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        return data[0]["id"] if data else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def run_diagnostics(course_id, assignment_id=None):
    """Run the probe set. Returns (results: list[dict], summary: dict)."""
    base = config.get_canvas_base().rstrip("/")
    results = []

    # 1. Token sanity — is the token even valid?
    results.append(_probe(
        "Token sanity (core API)", "GET", f"{base}/api/v1/users/self"))

    # 2. New Quizzes READ — can a PAT list New Quizzes at all?
    results.append(_probe(
        "New Quizzes list (read)", "GET",
        f"{base}/api/quiz/v1/courses/{course_id}/quizzes"))

    # 3. New Quizzes REPORTS — the actual goal (student_analysis CSV).
    aid = assignment_id or _find_nq_assignment(base, course_id)
    if aid:
        results.append(_probe(
            f"New Quizzes student_analysis report (assignment {aid})", "POST",
            f"{base}/api/quiz/v1/courses/{course_id}/quizzes/{aid}/reports",
            data={"quiz_report[report_type]": "student_analysis",
                  "quiz_report[format]": "csv"},
            retries=2))
    else:
        results.append({
            "label": "New Quizzes student_analysis report",
            "method": "POST", "url": "(skipped)", "status": None,
            "authorized": None,
            "interpretation": ("SKIPPED — no New Quiz found in this course. "
                               "Pass --assignment <id> to force the probe."),
            "body": ""})

    # 4. Classic Quizzes control — these SHOULD work with a PAT.
    qid = _find_classic_quiz(base, course_id)
    if qid:
        results.append(_probe(
            f"Classic Quizzes report control (quiz {qid})", "GET",
            f"{base}/api/v1/courses/{course_id}/quizzes/{qid}/reports",
            params={"quiz_report[report_type]": "student_analysis"}))
    else:
        results.append({
            "label": "Classic Quizzes report control",
            "method": "GET", "url": "(skipped)", "status": None,
            "authorized": None,
            "interpretation": "SKIPPED — no Classic quiz in this course to compare.",
            "body": ""})

    # Honest three-state verdict. "Blocked" requires a *definitive* 401/403;
    # a skipped report probe or a network error is INCONCLUSIVE, not blocked.
    token_valid   = results[0]["status"] == 200
    read_status   = results[1]["status"]            # New Quizzes list
    report_status = results[2]["status"]            # None if no NQ found/skipped

    reads_ok   = read_status in (200, 201)
    reports_ok = report_status in (200, 201, 202, 400, 409)
    works   = reads_ok or reports_ok
    blocked = read_status in (401, 403) or report_status in (401, 403)

    if report_status is None:
        report_note = (" (Reads succeeded, but the reports endpoint wasn't "
                       "exercised — point --assignment at a New Quiz to confirm "
                       "the actual report pull.)")
    elif reports_ok:
        report_note = " The report endpoint is reachable too — full pull is viable."
    elif report_status in _TRANSIENT:
        report_note = (f" Reads work, but the report POST hit a transient gateway "
                       f"error (HTTP {report_status}) — re-run against a quiz that "
                       "HAS submissions to confirm the pull end-to-end.")
    else:
        report_note = (f" Reads work; the report probe was inconclusive "
                       f"(HTTP {report_status}).")

    if not token_valid:
        state = "inconclusive"
        verdict = ("INCONCLUSIVE — the token failed the basic core-API sanity "
                   "check above. Fix/replace the token before trusting anything else.")
    elif works:
        state = "works"
        verdict = ("PAT CAN reach New Quizzes here — the blanket OAuth-only "
                   "assumption does NOT hold (it depends on active enrollment)."
                   + report_note)
    elif blocked:
        state = "blocked"
        verdict = ("PAT is blocked on New Quizzes for THIS course. Most likely "
                   "your enrollment here is concluded/inactive (try an actively-"
                   "enrolled course — the same PAT may well work there). 403 can "
                   "also mean a missing dev-key scope; 401 means an admin just "
                   "needs to grant the scope.")
    else:
        state = "inconclusive"
        verdict = ("INCONCLUSIVE — nothing conclusive was probed (no New Quiz / "
                   "Classic quiz found, or a network/other error). Re-run against "
                   "a course that HAS a New Quiz, or pass --assignment <id>. An "
                   "empty New Quiz in your collab course is enough — auth is all "
                   "we're testing.")

    summary = {
        "token_valid": token_valid,
        "state": state,
        "pat_works_for_new_quizzes": works,
        "verdict": verdict,
    }
    return results, summary


def _p(line):
    """Unicode-safe print for cp1252 consoles."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(enc, errors="replace").decode(enc))


def main():
    ap = argparse.ArgumentParser(description="Probe PAT access to New Quizzes.")
    ap.add_argument("--course", required=True, help="Course ID to probe.")
    ap.add_argument("--assignment", default=None,
                    help="New Quiz assignment_id (optional; auto-discovered).")
    args = ap.parse_args()

    if not config.token_is_set():
        raise SystemExit("No Canvas token saved — set one in the Web UI first.")

    base = config.get_canvas_base()
    if not base:
        raise SystemExit("No Canvas base URL saved — run onboarding first.")

    _p(f"Probing {base}  (course {args.course})\n" + "=" * 64)
    results, summary = run_diagnostics(args.course, args.assignment)
    for r in results:
        status = r["status"] if r["status"] is not None else "—"
        _p(f"\n[{status}] {r['label']}")
        _p(f"     {r['method']} {r['url']}")
        _p(f"     {r['interpretation']}")
    _p("\n" + "=" * 64)
    _p("VERDICT: " + summary["verdict"])


if __name__ == "__main__":
    main()
