"""Offline tests: mirror-first reads for routine sweeps / display consumers.

Fixture style mirrors ``api/tests/test_mirror_queries.py`` /
``api/tests/test_work_providers_mirror.py``: the workspace root is redirected
to ``tmp_path`` and the mirror is populated with ``store.write_*`` writers +
``store.record_pass(course_id, "full"/"roster", ok=True)``. ``store.now_iso()``
marks a pass fresh; a pinned old ISO string marks it stale.

Slice-2 write-path finding (documented here, not just in the summary): the
single sweep compute is now the operation-ledger adapter's ``_compute_sweep``
(``api/operation_ledger/adapters/sweep.py``) — it feeds ``/api/sweep/preview``
AND the baseline/drift/execute path behind apply (slice 00b removed the
direct-PUT apply route; slice 00c deleted the broken
``gradebook_service._sweep_compute``). A mirror-served sweep compute could
feed a write built on stale data, which locked decision 1 forbids, so the
compute stays fully live (unflipped);
``test_sweep_compute_is_not_flipped_and_stays_live`` locks that in. The same
write-value analysis applies inside
``routines_builtin._run_routine_sweep`` (assignments/submissions feed the
``seconds_late_override`` it writes in the same pass) and
``_run_routine_curve`` (assignments/submissions feed the ``posted_grade`` it
writes in "apply" mode) — those two reads per function stay live too; only
the name-lookup student reads in each, and the audit-only baseline read in
``_curve_apply_core``, are mirror-first. Tests below lock in exactly that
split, substituting for the spec's "``_sweep_compute`` identical output"
bullet with an equivalent check on ``_run_routine_grading_debt`` (the sibling
routine with no write path at all, fully flipped).
"""
from __future__ import annotations

from api.mirror import store
from api.operation_ledger.adapters.sweep import _compute_sweep
from api.webui import mirror_reads, workspace
from api.webui.routes import routines_builtin

COURSE = "555201"

ASSIGNMENTS = [
    {"id": 700200, "name": "Lab Report", "due_at": "2026-01-01T09:00:00Z",
     "points_possible": 10, "published": True, "html_url": "u",
     "submission_types": ["online_text_entry"]},
]
USERS = [
    {"id": 900201, "name": "Learner One", "sortable_name": "One, Learner",
     "short_name": "Lee", "sis_user_id": "SIS-900201", "enrollments": []},
    {"id": 900202, "name": "Learner Two", "sortable_name": "Two, Learner",
     "short_name": "Learner Two", "sis_user_id": "SIS-900202", "enrollments": []},
]
# One old, ungraded "submitted" row (grading-debt candidate) and one graded
# row (not a debt). Old enough that "days ungraded" clears any min_days
# threshold regardless of when the suite runs.
SUBMISSIONS = [
    {"assignment_id": 700200, "user_id": 900201, "workflow_state": "submitted",
     "submitted_at": "2020-01-01T09:00:00Z", "score": None,
     "submission_comments": []},
    {"assignment_id": 700200, "user_id": "900202", "workflow_state": "graded",
     "submitted_at": "2020-01-02T09:00:00Z", "score": 8,
     "submission_comments": []},
]


def _populate(root, *, fresh=True):
    stamp = store.now_iso() if fresh else "2020-01-01T00:00:00Z"
    store.write_roster(COURSE, USERS, {}, root=root, attempted_at=stamp)
    store.write_assignments(COURSE, ASSIGNMENTS, root=root, attempted_at=stamp)
    store.merge_submissions(COURSE, "700200", SUBMISSIONS, root=root,
                            attempted_at=stamp, replace=True)
    for pass_name in ("full", "roster"):
        store.record_pass(COURSE, pass_name, ok=True, attempted_at=stamp, root=root)


def _mount(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


def _explode(*_args, **_kwargs):
    raise AssertionError("live Canvas read attempted")


# --- (a) each helper serves fresh-mirror rows with zero live calls -----------------

def test_students_or_live_serves_fresh_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)
    rows, err, source = mirror_reads.students_or_live(COURSE)
    assert err is None and source == "mirror"
    assert {r["id"] for r in rows} == {"900201", "900202"}


def test_assignments_or_live_serves_fresh_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)
    rows, err, source = mirror_reads.assignments_or_live(COURSE)
    assert err is None and source == "mirror"
    assert {r["id"] for r in rows} == {"700200"}


def test_submissions_or_live_serves_fresh_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)
    rows, err, source = mirror_reads.submissions_or_live(COURSE)
    assert err is None and source == "mirror"
    assert {r["user_id"] for r in rows} == {"900201", "900202"}


# --- (b) stale mirror -> live fallback with source "canvas" -----------------------

def test_students_or_live_falls_back_live_when_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    live_rows = [{"id": 1, "name": "Live Student"}]
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", lambda *a, **k: (live_rows, None))
    rows, err, source = mirror_reads.students_or_live(COURSE)
    assert err is None and source == "canvas" and rows == live_rows


def test_assignments_or_live_falls_back_live_when_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    live_rows = [{"id": 1, "name": "Live Assignment"}]
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", lambda *a, **k: (live_rows, None))
    rows, err, source = mirror_reads.assignments_or_live(COURSE)
    assert err is None and source == "canvas" and rows == live_rows


def test_submissions_or_live_falls_back_live_when_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    live_rows = [{"user_id": 1, "assignment_id": 1}]
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", lambda *a, **k: (live_rows, None))
    rows, err, source = mirror_reads.submissions_or_live(COURSE)
    assert err is None and source == "canvas" and rows == live_rows


def test_helper_falls_back_live_when_mirror_read_errors(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    from api.mirror import queries as mirror_queries
    monkeypatch.setattr(mirror_queries, "course_assignments", lambda course_id, **k: (None, "boom"))
    live_rows = [{"id": 1}]
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", lambda *a, **k: (live_rows, None))
    rows, err, source = mirror_reads.assignments_or_live(COURSE)
    assert err is None and source == "canvas" and rows == live_rows


# --- routines_builtin integration: flipped sites vs. sites left live --------------

def test_grading_debt_reads_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    """_run_routine_grading_debt has no write path — both course-scoped reads
    are safe to flip and both do, per the spec's line range (~252-258)."""
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)
    monkeypatch.setattr(routines_builtin.config, "active_courses",
                        lambda: [{"id": COURSE, "nickname": "Course"}])
    monkeypatch.setattr(routines_builtin.config, "get_sweep_settings",
                        lambda: {"skip_weekends": True, "holidays": []})
    monkeypatch.setattr(routines_builtin.config, "get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    result = routines_builtin._run_routine_grading_debt({"school_days": 3})
    assert result["ok"] is True
    assert "1 ungraded" in result["summary"]


def test_grading_debt_falls_back_live_when_stale(monkeypatch, tmp_path):
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path), fresh=False)
    monkeypatch.setattr(routines_builtin.config, "active_courses",
                        lambda: [{"id": COURSE, "nickname": "Course"}])
    monkeypatch.setattr(routines_builtin.config, "get_sweep_settings",
                        lambda: {"skip_weekends": True, "holidays": []})
    monkeypatch.setattr(routines_builtin.config, "get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})

    def fake_get(path, params=None, timeout=None):
        if path.endswith("/assignments"):
            return [{"id": "live-a", "name": "Live Assignment"}], None
        return [{"assignment_id": "live-a", "user_id": "live-u",
                 "workflow_state": "submitted",
                 "submitted_at": "2020-01-01T09:00:00Z"}], None

    monkeypatch.setattr(routines_builtin, "_canvas_get_all", fake_get)
    result = routines_builtin._run_routine_grading_debt({"school_days": 3})
    assert result["ok"] is True
    assert "1 ungraded" in result["summary"]


def test_grading_debt_output_identical_mirror_served_vs_live_served(monkeypatch, tmp_path):
    """Substitutes for the spec's 'sweep compute identical output' bullet:
    the sweep compute is deliberately left live (see module docstring), so this
    equivalence check runs against the sibling routine that was safely and
    fully flipped instead — same fixture served from the mirror, then from an
    equivalent live stand-in, must produce the same report."""
    _mount(monkeypatch, tmp_path)
    monkeypatch.setattr(routines_builtin.config, "active_courses",
                        lambda: [{"id": COURSE, "nickname": "Course"}])
    monkeypatch.setattr(routines_builtin.config, "get_sweep_settings",
                        lambda: {"skip_weekends": True, "holidays": []})
    monkeypatch.setattr(routines_builtin.config, "get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})

    _populate(str(tmp_path))
    mirror_served = routines_builtin._run_routine_grading_debt({"school_days": 3})

    _populate(str(tmp_path), fresh=False)

    def fake_get(path, params=None, timeout=None):
        if path.endswith("/assignments"):
            return [dict(ASSIGNMENTS[0])], None
        return [dict(row) for row in SUBMISSIONS], None

    monkeypatch.setattr(routines_builtin, "_canvas_get_all", fake_get)
    live_served = routines_builtin._run_routine_grading_debt({"school_days": 3})

    assert mirror_served == live_served


def test_sweep_reads_students_from_mirror_but_assignments_and_submissions_stay_live(
        monkeypatch, tmp_path):
    """_run_routine_sweep writes seconds_late_override computed straight from
    assignments (due_at) + submissions (submitted_at) fetched in the same
    pass — locked decision 1 keeps both live. Only the name-lookup students
    read is mirror-first."""
    from datetime import datetime, timedelta
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(routines_builtin.config, "active_courses",
                        lambda: [{"id": COURSE, "nickname": "Course"}])
    monkeypatch.setattr(routines_builtin.config, "get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    monkeypatch.setattr(routines_builtin.config, "get_extra_time", lambda course_id: [])

    recent_due = (datetime.now().date() - timedelta(days=5)).isoformat() + "T09:00:00Z"
    live_calls = []

    def fake_get_all(path, params=None, timeout=None):
        live_calls.append(path)
        if path.endswith("/assignments"):
            return [{"id": 700200, "name": "Lab Report", "due_at": recent_due,
                     "points_possible": 10, "published": True}], None
        return [], None  # no live submissions -> nothing to write, harmless

    monkeypatch.setattr(routines_builtin, "_canvas_get_all", fake_get_all)
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)  # students must not go live

    result = routines_builtin._run_routine_sweep({})
    assert result["ok"] is True
    assert any(p.endswith("/assignments") for p in live_calls)
    assert any(p.endswith("/students/submissions") for p in live_calls)


def test_curve_apply_core_reads_audit_baseline_from_mirror(monkeypatch, tmp_path):
    """current_subs in _curve_apply_core only records score_at_apply_time
    (audit trail) — it does not determine the curved value written, so it is
    safe to flip. course_submissions() returns all assignments, filtered here
    to the target one."""
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(mirror_reads, "_canvas_get_all", _explode)
    monkeypatch.setattr(routines_builtin, "_canvas_get",
                        lambda path: ({"name": "Lab Report"}, None))
    sent = []
    monkeypatch.setattr(routines_builtin, "_canvas_send",
                        lambda method, path, payload: (sent.append((method, path, payload)) or ({}, None)))
    monkeypatch.setattr(routines_builtin, "_load_curve_events", lambda: [])
    saved = []
    monkeypatch.setattr(routines_builtin, "_save_curve_events", lambda events: saved.append(events))

    rows = [{"user_id": "900201", "student_name": "Learner One",
            "original_score": None, "curved_score": 5, "changed": True}]
    all_ok, event_id, push_results = routines_builtin._curve_apply_core(
        COURSE, "700200", "target_average", {}, rows)
    assert all_ok is True
    assert saved[0][0]["students"][0]["score_at_apply_time"] is None  # 900201 was ungraded


def test_sweep_compute_is_not_flipped_and_stays_live(monkeypatch, tmp_path):
    """Locked decision: the adapter's _compute_sweep feeds /api/sweep/preview
    AND the write set behind apply (single owner since slice 00c), so it must
    stay fully live even when the mirror is fresh — this test fails loudly if
    a future edit "helpfully" flips it to mirror reads."""
    _mount(monkeypatch, tmp_path)
    _populate(str(tmp_path))
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
        lambda: {"no_count_dates": []})
    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.config.get_extra_time",
        lambda course_id: [])

    live_calls = []

    def fake_get_all(path, params=None, timeout=None):
        live_calls.append(path)
        return [], None

    monkeypatch.setattr(
        "api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all",
        fake_get_all)
    entries, skipped, err = _compute_sweep(COURSE, {})
    assert err is None
    assert live_calls  # mirror was fresh, but _compute_sweep went live anyway
