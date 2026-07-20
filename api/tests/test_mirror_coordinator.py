"""Offline contract tests for the fixed CanvasMirror coordinator."""
from __future__ import annotations

import threading
import time

from api.mirror.coordinator import MirrorCoordinator


def _wait(coordinator, plan_id):
    for _ in range(100):
        plan = coordinator.status(plan_id)["plans"][0]
        if plan["state"] in {"succeeded", "failed", "cancelled"}:
            return plan
        time.sleep(0.01)
    raise AssertionError("coordinator did not settle")


def test_scope_dependencies_coalescing_promotion_and_sanitized_state():
    calls = []
    lock = threading.Lock()

    def runner(scope):
        def run(course_id):
            with lock:
                calls.append((scope, course_id))
        return run

    coordinator = MirrorCoordinator({scope: runner(scope) for scope in (
        "course_context", "course_structure", "roster", "groups",
        "submissions.course_delta", "new_quizzes.metadata",
    )})
    first = coordinator.submit(["local-course"], ["groups"], priority="background")
    second = coordinator.submit(["local-course"], ["groups"], priority="focus")
    assert _wait(coordinator, first)["state"] == "succeeded"
    assert _wait(coordinator, second)["state"] == "succeeded"
    assert calls == [("course_context", "local-course"), ("roster", "local-course"),
                     ("groups", "local-course")]
    jobs = coordinator.status(first)["plans"][0]["jobs"]
    assert [job["scope"] for job in jobs] == ["course_context", "roster", "groups"]
    assert all(set(job) <= {"job_id", "course_id", "scope", "priority", "state",
                            "error_class", "queue_wait_ms", "yield_count", "cancel_count"} for job in jobs)


def test_failure_isolated_and_cancellation_cooperates_before_get():
    started = threading.Event()
    release = threading.Event()

    def fail(_course):
        raise RuntimeError("private detail must not escape")

    def wait_for_cancel(_course):
        started.set()
        release.wait(1)

    coordinator = MirrorCoordinator({
        "course_context": lambda _course: None,
        "course_structure": fail,
        "roster": lambda _course: None,
        "groups": lambda _course: None,
        "submissions.course_delta": wait_for_cancel,
        "new_quizzes.metadata": lambda _course: None,
    })
    failed = coordinator.submit(["course"], ["course_structure", "roster"], priority="manual")
    failed_plan = _wait(coordinator, failed)
    assert failed_plan["state"] == "failed"
    assert {job["state"] for job in failed_plan["jobs"]} >= {"failed", "succeeded"}

    plan_id = coordinator.submit(["course"], ["submissions.course_delta"], priority="background")
    assert started.wait(1)
    assert coordinator.cancel(plan_id) is True
    release.set()
    plan = _wait(coordinator, plan_id)
    assert plan["state"] == "cancelled"


def test_background_get_yields_to_foreground():
    gate = threading.Event()
    observed = []
    holder = {}

    def run(_course):
        gate.set()
        observed.append(holder["coordinator"].before_physical_get())

    coordinator = MirrorCoordinator({
        "course_context": run, "course_structure": run, "roster": run,
        "groups": run, "submissions.course_delta": run, "new_quizzes.metadata": run,
    })
    holder["coordinator"] = coordinator
    with coordinator.foreground_interval():
        plan_id = coordinator.submit(["course"], ["course_context"], priority="background")
        assert gate.wait(1)
        time.sleep(0.03)
        assert observed == []
    plan = _wait(coordinator, plan_id)
    assert plan["state"] == "succeeded"
    assert observed and observed[0][0] >= 20 and observed[0][1] is False


def test_course_refresh_is_one_compatibility_job_and_history_is_bounded():
    calls = []
    coordinator = MirrorCoordinator({"course.refresh": lambda course: calls.append(course) or {"ok": True}},
                                    history_limit=2)
    first = coordinator.submit(["one"])
    assert _wait(coordinator, first)["jobs"][0]["scope"] == "course.refresh"
    for course in ("two", "three", "four"):
        assert _wait(coordinator, coordinator.submit([course]))["state"] == "succeeded"
    # The next submit trims atomically: stale plans, jobs, and coalescing keys
    # disappear together while the two newest completed plans remain observable.
    assert len(coordinator._plans) == 2
    assert len(coordinator._jobs) == 2
    assert len(coordinator._by_key) == 2
    assert calls == ["one", "two", "three", "four"]


def test_failed_result_blocks_dependents_but_not_unrelated_work():
    ran = []
    coordinator = MirrorCoordinator({
        "course_context": lambda course: {"ok": False} if course == "bad" else {"ok": True},
        "course_structure": lambda course: ran.append(("structure", course)) or {"ok": True},
        "roster": lambda course: ran.append(("roster", course)) or {"ok": True},
        "groups": lambda course: ran.append(("groups", course)) or {"ok": True},
        "submissions.course_delta": lambda course: {"ok": True},
        "new_quizzes.metadata": lambda course: {"ok": True},
        "course.refresh": lambda course: {"ok": True},
    })
    failed = coordinator.submit(["bad"], ["groups"])
    unrelated = coordinator.submit(["good"], ["course_structure"])
    failed_plan = _wait(coordinator, failed)
    assert failed_plan["state"] == "failed"
    assert [job["state"] for job in failed_plan["jobs"]] == ["failed", "cancelled", "cancelled"]
    assert _wait(coordinator, unrelated)["state"] == "succeeded"
    assert ran == [("structure", "good")]


def test_concluded_get_yields_to_foreground():
    entered = threading.Event()
    observed = []
    holder = {}

    def run(_course):
        entered.set()
        observed.append(holder["coordinator"].before_physical_get())

    coordinator = MirrorCoordinator({"course.refresh": run})
    holder["coordinator"] = coordinator
    with coordinator.foreground_interval():
        plan_id = coordinator.submit(["concluded"], priority="concluded")
        assert entered.wait(1)
        time.sleep(0.03)
        assert observed == []
    assert _wait(coordinator, plan_id)["state"] == "succeeded"
    assert observed[0][0] >= 20
