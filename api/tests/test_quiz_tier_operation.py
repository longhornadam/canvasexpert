"""PII-negative tests for differentiated QuizForge operation behavior.

Tests the full operation-ledger lifecycle for ``content.quiz`` in
differentiated mode using mocked Canvas calls and mocked plan subprocesses.
Same pattern as ``test_assignment_tier_operation.py``.
"""
import copy
import json

import pytest

from api.operation_ledger import (
    batches, executor, models, operations, paths, registry, storage,
)
from api.operation_ledger.adapters import QuizAdapter
from api.operation_ledger.adapters import quiz as quiz_adapter_module
from api.operation_ledger.adapters.assignment_groups import (
    GroupResolutionError, resolve_assignment_groups,
)
from api.platform_services import canvas_client, config


# ── Sample variant plans ─────────────────────────────────────────────────

VARIANT_PLAN_A = {
    "version": 1,
    "title": "Algebra Quiz - Support",
    "source_path": "/tmp/algebra_support.txt",
    "quiz_payload": {
        "quiz": {
            "title": "Algebra Quiz - Support",
            "points_possible": 50.0,
            "grading_type": "points",
            "quiz_settings": {},
        },
    },
    "items": [
        {"index": 1, "source_item_id": "q1", "source_type": "MC",
         "payload": {"item": {"entry_type": "Item", "position": 1, "points_possible": 25.0}}},
        {"index": 2, "source_item_id": "q2", "source_type": "MC",
         "payload": {"item": {"entry_type": "Item", "position": 2, "points_possible": 25.0}}},
    ],
    "assignment_settings": {
        "due_at": "2026-08-01T23:59:00Z",
        "published": True,
        "post_to_sis": False,
    },
    "module": {"module_name": "Unit 1"},
}

VARIANT_PLAN_B = {
    "version": 1,
    "title": "Algebra Quiz - Extend",
    "source_path": "/tmp/algebra_extend.txt",
    "quiz_payload": {
        "quiz": {
            "title": "Algebra Quiz - Extend",
            "points_possible": 100.0,
            "grading_type": "points",
            "quiz_settings": {},
        },
    },
    "items": [
        {"index": 1, "source_item_id": "q1", "source_type": "ESSAY",
         "payload": {"item": {"entry_type": "Item", "position": 1, "points_possible": 100.0}}},
    ],
    "assignment_settings": {
        "due_at": "2026-08-01T23:59:00Z",
        "published": True,
        "post_to_sis": False,
    },
    "module": {"module_name": "Unit 1"},
}

VARIANT_PLAN_C = {
    "version": 1,
    "title": "Algebra Quiz - Accelerate",
    "source_path": "/tmp/algebra_accelerate.txt",
    "quiz_payload": {
        "quiz": {
            "title": "Algebra Quiz - Accelerate",
            "points_possible": 150.0,
            "grading_type": "points",
            "quiz_settings": {},
        },
    },
    "items": [
        {"index": 1, "source_item_id": "q1", "source_type": "MC",
         "payload": {"item": {"entry_type": "Item", "position": 1, "points_possible": 50.0}}},
        {"index": 2, "source_item_id": "q2", "source_type": "ESSAY",
         "payload": {"item": {"entry_type": "Item", "position": 2, "points_possible": 100.0}}},
    ],
    "assignment_settings": {
        "due_at": "2026-08-01T23:59:00Z",
        "published": True,
        "post_to_sis": False,
    },
    "module": {},
}

# ── Helpers ──────────────────────────────────────────────────────────────


def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root


def _mock_active_courses(monkeypatch, courses=None):
    if courses is None:
        courses = [
            {"id": "101", "name": "Algebra 1", "active": True},
            {"id": "102", "name": "Biology", "active": True},
        ]
    monkeypatch.setattr(config, "active_courses", lambda: courses)


def _mock_get_extra_time(monkeypatch, entries=None):
    """Mock config.get_extra_time, defaulting to empty."""
    monkeypatch.setattr(config, "get_extra_time", lambda cid: entries or [])


def _mock_plan_subprocess(monkeypatch, plan_map=None):
    """Mock run_json_object to return plans by path."""
    plan_map = plan_map or {}

    def fake_run_json_object(args, extra_env=None, timeout=30, max_output_bytes=2_000_000):
        for path, plan in plan_map.items():
            if path in args:
                return plan
        raise ValueError(f"no mock plan for {args}")

    monkeypatch.setattr(quiz_adapter_module, "run_json_object", fake_run_json_object)


def _mock_canvas_send(monkeypatch, responses=None):
    """Mock _canvas_send with a queue of (response, error) tuples."""
    calls = []
    queue = list(responses or [])

    def fake_send(method, path, payload, timeout=30):
        calls.append({"method": method, "path": path, "payload": payload})
        if queue:
            return queue.pop(0)
        return None, "no more mock responses"

    monkeypatch.setattr(canvas_client, "_canvas_send", fake_send)
    return calls


def _mockcanvas_get(monkeypatch, responses=None):
    """Mock canvas_get with a queue of (data, error) tuples."""
    calls = []
    queue = list(responses or [])

    def fake_get(path, params=None, timeout=20):
        calls.append({"path": path, "params": params})
        if queue:
            return queue.pop(0)
        return None, "no more mock responses"

    monkeypatch.setattr(canvas_client, "canvas_get", fake_get)
    return calls


def _mockcanvas_get_all(monkeypatch, responses=None):
    """Mock canvas_get_all with a queue of (list, error) tuples."""
    queue = list(responses or [])

    def fake_get_all(path, params=None, timeout=30):
        if queue:
            return queue.pop(0)
        return [], None

    monkeypatch.setattr(canvas_client, "canvas_get_all", fake_get_all)


def _make_variants(*plans):
    """Build a variants list from plan dicts."""
    group_names = ["Blue", "Gold", "Silver"]
    return [
        {"path": f"/tmp/v{i}.txt", "group_name": group_names[i], "plan": p}
        for i, p in enumerate(plans)
    ]


def _get_all_canned(path, params=None, timeout=30):
    """Canned canvas_get_all for group resolution."""
    if "group_categories" in path:
        return [{"id": 10, "name": " Blue "}, {"id": 20, "name": "GOLD"}], None
    if "/groups/10/memberships" in path:
        return [{"user_id": 9001}, {"user_id": 9002}], None
    if "/groups/20/memberships" in path:
        return [{"user_id": 9003}], None
    if "/enrollments" in path:
        return [{"user_id": 9001}, {"user_id": 9002}, {"user_id": 9003}], None
    if "/assignments" in path:
        return [], None
    return [], None


class Context:
    def __init__(self):
        self.steps = []
    def before_send(self, key, digest):
        step = models.new_step(key)
        step["state"] = "claimed"
        step["payload_digest"] = digest
        self._put(step)
        return copy.deepcopy(step)
    def checkpoint_step(self, step, returned_object_id=None, returned_object_url=None):
        step = copy.deepcopy(step)
        if returned_object_id is not None:
            step["returned_object_id"] = returned_object_id
        if returned_object_url is not None:
            step["returned_object_url"] = returned_object_url
        self._put(step)
        return step
    def _put(self, step):
        self.steps = [row for row in self.steps if row["step_key"] != step["step_key"]] + [copy.deepcopy(step)]


# ── Protocol conformance ─────────────────────────────────────────────────

def test_adapter_is_registered():
    adapter = registry.get_adapter("content.quiz")
    assert adapter is not None
    assert adapter.kind == "content.quiz"


# ── Build payload tests ──────────────────────────────────────────────────

def test_build_payload_differentiated(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_B,
    })

    adapter = QuizAdapter()
    payload = adapter.build_payload({
        "mode": "differentiated",
        "variants": [
            {"path": "/tmp/v0.txt", "group_name": "Blue"},
            {"path": "/tmp/v1.txt", "group_name": "Gold"},
        ],
    })
    assert payload["mode"] == "differentiated"
    assert len(payload["variants"]) == 2
    assert payload["variants"][0]["group_name"] == "Blue"
    assert payload["variants"][1]["group_name"] == "Gold"
    assert payload["variants"][0]["plan"]["title"] == "Algebra Quiz - Support"
    assert payload["variants"][1]["plan"]["title"] == "Algebra Quiz - Extend"

    digest = adapter.source_digest(payload)
    assert len(digest) == 64


def test_build_payload_rejects_single_variant(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_plan_subprocess(monkeypatch, {"/tmp/v0.txt": VARIANT_PLAN_A})

    adapter = QuizAdapter()
    with pytest.raises(ValueError, match="at least two variants"):
        adapter.build_payload({
            "mode": "differentiated",
            "variants": [{"path": "/tmp/v0.txt", "group_name": "Blue"}],
        })


def test_build_payload_accepts_duplicate_titles(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_A,  # same title
    })

    adapter = QuizAdapter()
    payload = adapter.build_payload({
            "mode": "differentiated",
            "variants": [
                {"path": "/tmp/v0.txt", "group_name": "Blue"},
                {"path": "/tmp/v1.txt", "group_name": "Gold"},
            ],
        })
    assert [variant["plan"]["title"] for variant in payload["variants"]] == [
        VARIANT_PLAN_A["title"], VARIANT_PLAN_A["title"]
    ]


def test_build_payload_rejects_missing_group_name(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_B,
    })

    adapter = QuizAdapter()
    with pytest.raises(ValueError, match="each variant requires path and group_name"):
        adapter.build_payload({
            "mode": "differentiated",
            "variants": [
                {"path": "/tmp/v0.txt", "group_name": "Blue"},
                {"path": "/tmp/v1.txt"},  # missing group_name
            ],
        })


def test_source_digest_deterministic(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_B,
    })

    adapter = QuizAdapter()
    p1 = adapter.build_payload({
        "mode": "differentiated",
        "variants": [
            {"path": "/tmp/v0.txt", "group_name": "Blue"},
            {"path": "/tmp/v1.txt", "group_name": "Gold"},
        ],
    })
    p2 = adapter.build_payload({
        "mode": "differentiated",
        "variants": [
            {"path": "/tmp/v0.txt", "group_name": "Blue"},
            {"path": "/tmp/v1.txt", "group_name": "Gold"},
        ],
    })
    assert adapter.source_digest(p1) == adapter.source_digest(p2)


# ── Baseline / drift tests ──────────────────────────────────────────────

def test_capture_baseline_differentiated(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_active_courses(monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_B,
    })
    _mockcanvas_get(monkeypatch, [
        ([], None),  # no existing Support quiz
        ([], None),  # no existing Extend quiz
    ])

    # Mock resolve_assignment_groups directly
    resolved = {
        "safe": {
            "selected_category_id": "7", "roster_count": 3, "roster_digest": "abc",
            "tiers": [
                {"index": 0, "label": "variant_0", "group_name": "Blue",
                 "group_id": "10", "student_count": 2, "membership_digest": "d1"},
                {"index": 1, "label": "variant_1", "group_name": "Gold",
                 "group_id": "20", "student_count": 1, "membership_digest": "d2"},
            ],
        },
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(
        quiz_adapter_module, "resolve_assignment_groups",
        lambda *a, **k: resolved,
    )

    adapter = QuizAdapter()
    payload = adapter.build_payload({
        "mode": "differentiated",
        "variants": [
            {"path": "/tmp/v0.txt", "group_name": "Blue"},
            {"path": "/tmp/v1.txt", "group_name": "Gold"},
        ],
    })

    baseline = adapter.capture_baseline(payload, {"course_id": "101"})
    assert "canvas_error" not in baseline
    assert "group_snapshot" in baseline
    assert len(baseline["group_snapshot"]["tiers"]) == 2
    assert baseline["group_snapshot"]["tiers"][0]["group_name"] == "Blue"
    assert baseline["group_snapshot"]["tiers"][1]["group_name"] == "Gold"
    # No PII in safe snapshot
    safe_text = json.dumps(baseline["group_snapshot"])
    assert all(value not in safe_text for value in ("9001", "9002", "9003"))


def test_group_snapshot_drift_detected(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    _mock_active_courses(monkeypatch)
    _mock_plan_subprocess(monkeypatch, {
        "/tmp/v0.txt": VARIANT_PLAN_A,
        "/tmp/v1.txt": VARIANT_PLAN_B,
    })

    # Mock resolve_assignment_groups directly
    resolved = {
        "safe": {
            "selected_category_id": "7", "roster_count": 3, "roster_digest": "abc",
            "tiers": [
                {"index": 0, "label": "variant_0", "group_name": "Blue",
                 "group_id": "10", "student_count": 2, "membership_digest": "d1"},
                {"index": 1, "label": "variant_1", "group_name": "Gold",
                 "group_id": "20", "student_count": 1, "membership_digest": "d2"},
            ],
        },
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(
        quiz_adapter_module, "resolve_assignment_groups",
        lambda *a, **k: resolved,
    )

    adapter = QuizAdapter()
    payload = adapter.build_payload({
        "mode": "differentiated",
        "variants": [
            {"path": "/tmp/v0.txt", "group_name": "Blue"},
            {"path": "/tmp/v1.txt", "group_name": "Gold"},
        ],
    })

    # Mock GET responses for assignment lookups in capture_baseline
    _mockcanvas_get(monkeypatch, [
        ([], None),  # no existing Support (first call)
        ([], None),  # no existing Extend (first call)
    ])

    baseline = adapter.capture_baseline(payload, {"course_id": "101"})

    # Different snapshot triggers drift
    # check_drift calls capture_baseline again, needs more GET responses
    _mockcanvas_get(monkeypatch, [
        ([], None),  # no existing Support (second call)
        ([], None),  # no existing Extend (second call)
    ])
    different_baseline = copy.deepcopy(baseline)
    different_baseline["group_snapshot"]["tiers"][0]["student_count"] = 99
    assert adapter.check_drift(payload, {"course_id": "101", "steps": []}, different_baseline) is True


# ── Review tests ─────────────────────────────────────────────────────────

def test_review_is_safe(monkeypatch):
    _mock_active_courses(monkeypatch)
    adapter = QuizAdapter()
    monkeypatch.setattr(canvas_client, "canvas_get_all", _get_all_canned)
    resolved = resolve_assignment_groups(
        "101",
        [{"label": "variant_0", "group": "Blue"}, {"label": "variant_1", "group": "Gold"}],
        canvas_get_all=_get_all_canned, selected_category_id="7",
    )
    baseline = {
        "group_snapshot": resolved["safe"],
        "existing_by_title": {"Algebra Quiz - Support": [], "Algebra Quiz - Extend": []},
    }
    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    review = adapter.freeze_review(payload, {"course_id": "101"}, baseline)
    assert review["mode"] == "differentiated"
    assert review["variant_count"] == 2
    assert review["variants"][0]["group_name"] == "Blue"
    assert review["variants"][1]["group_name"] == "Gold"
    assert review["only_visible_to_overrides"] is True
    assert review["tiers"][0]["group"] == "Blue"
    assert review["tiers"][1]["group"] == "Gold"
    # No PII in review
    review_text = json.dumps(review)
    assert all(value not in review_text for value in ("9001", "9002", "9003"))


def test_review_with_three_variants(monkeypatch):
    _mock_active_courses(monkeypatch)
    adapter = QuizAdapter()

    def three_group_getter(path, params=None, timeout=30):
        if "group_categories" in path:
            return [{"id": 10, "name": "Blue"}, {"id": 20, "name": "Gold"}, {"id": 30, "name": "Silver"}], None
        if "/groups/10/memberships" in path:
            return [{"user_id": 9001}], None
        if "/groups/20/memberships" in path:
            return [{"user_id": 9002}], None
        if "/groups/30/memberships" in path:
            return [{"user_id": 9003}], None
        if "/enrollments" in path:
            return [{"user_id": 9001}, {"user_id": 9002}, {"user_id": 9003}], None
        return [], None

    resolved = resolve_assignment_groups(
        "101",
        [{"label": "variant_0", "group": "Blue"}, {"label": "variant_1", "group": "Gold"},
         {"label": "variant_2", "group": "Silver"}],
        canvas_get_all=three_group_getter, selected_category_id="7",
    )
    baseline = {
        "group_snapshot": resolved["safe"],
        "existing_by_title": {
            "Algebra Quiz - Support": [], "Algebra Quiz - Extend": [],
            "Algebra Quiz - Accelerate": [],
        },
    }
    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B, VARIANT_PLAN_C),
    }
    review = adapter.freeze_review(payload, {"course_id": "101"}, baseline)
    assert review["variant_count"] == 3
    assert review["variants"][0]["group_name"] == "Blue"
    assert review["variants"][2]["group_name"] == "Silver"


# ── Apply tests ──────────────────────────────────────────────────────────

def test_two_variant_write_order_and_transient_ids(monkeypatch):
    """Verify per-variant create/restrict/override/item/patch/module order."""
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch)
    adapter = QuizAdapter()

    # Mock resolve_assignment_groups to return canned data
    resolved = {
        "safe": {
            "selected_category_id": "7",
            "roster_count": 3,
            "roster_digest": "abc",
            "tiers": [
                {"index": 0, "label": "variant_0", "group_name": "Blue",
                 "group_id": "10", "student_count": 2, "membership_digest": "blue_digest"},
                {"index": 1, "label": "variant_1", "group_name": "Gold",
                 "group_id": "20", "student_count": 1, "membership_digest": "gold_digest"},
            ],
        },
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(
        quiz_adapter_module,
        "resolve_assignment_groups",
        lambda *a, **k: resolved,
    )

    # Mock GET responses: patch verifies and module lookups
    _mockcanvas_get(monkeypatch, [
        ({"id": 1001, "name": "Quiz A", "published": True}, None),  # verify patch v0
        ({"id": 1006, "name": "Quiz B", "published": True}, None),  # verify patch v1
    ])
    _mockcanvas_get_all(monkeypatch, [
        ([{"id": 301, "name": "Unit 1"}], None),  # module lookup v0
        ([{"id": 301, "name": "Unit 1"}], None),  # module lookup v1 (cached)
    ])

    writes = []
    def send(method, path, body, timeout=30):
        writes.append((path, copy.deepcopy(body)))
        if "quizzes" in path and "items" not in path and "modules" not in path and "overrides" not in path:
            return {"id": 100 + len(writes)}, None
        if isinstance(body, dict) and body.get("assignment", {}).get("only_visible_to_overrides"):
            return {"id": 1001}, None
        if "overrides" in path:
            return {"id": 700 + len(writes)}, None
        if "items" in path:
            return {"id": 200 + len(writes)}, None
        if "modules" in path:
            return {"id": 300 + len(writes)}, None
        return {"id": 100 + len(writes)}, None
    monkeypatch.setattr(canvas_client, "_canvas_send", send)

    baseline = {
        "group_snapshot": resolved["safe"],
        "existing_by_title": {"Algebra Quiz - Support": [], "Algebra Quiz - Extend": []},
    }
    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    context = Context()
    result = adapter.execute(
        payload, {"course_id": "101", "steps": []},
        baseline, {}, context,
    )
    assert result["state"] == "applied"

    # Write order: variant 0 (quiz, restrict, override, items, patch, module),
    #             variant 1 (quiz, restrict, override, items, patch, module)
    quiz_paths = [path for path, _ in writes if "quizzes" in path and "items" not in path and "modules" not in path]
    restrict_bodies = [body for _, body in writes if isinstance(body, dict) and body.get("assignment", {}).get("only_visible_to_overrides")]
    assert len(quiz_paths) == 2  # one quiz per variant
    assert len(restrict_bodies) == 2  # one restrict per variant

    # Override call uses transient student IDs
    override_bodies = [body for path, body in writes if "overrides" in path]
    assert len(override_bodies) == 2
    assert override_bodies[0]["assignment_override"]["student_ids"] == ["9001", "9002"]
    assert override_bodies[1]["assignment_override"]["student_ids"] == ["9003"]

    # No PII in durable steps
    durable = json.dumps(context.steps)
    assert all(value not in durable for value in ("9001", "9002", "9003"))


def test_quiz_create_failure_stops_variant(monkeypatch):
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch)
    adapter = QuizAdapter()
    resolved = {
        "safe": {"tiers": [
            {"index": 0, "label": "variant_0", "group_name": "Blue", "group_id": "10",
             "student_count": 2, "membership_digest": "d1"},
        ]},
        "student_ids_by_group": {"10": ["9001", "9002"]},
    }
    monkeypatch.setattr(quiz_adapter_module, "resolve_assignment_groups", lambda *a, **k: resolved)

    calls = []
    def send(method, path, body, timeout=30):
        calls.append(path)
        return None, "HTTP 400: bad request"  # first quiz create fails
    monkeypatch.setattr(canvas_client, "_canvas_send", send)

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    baseline = {"group_snapshot": resolved["safe"]}
    result = adapter.execute(
        payload, {"course_id": "101", "steps": []},
        baseline, {}, Context(),
    )
    assert result["state"] == "failed"
    assert len(calls) == 1  # only create_quiz:0 attempted


def test_item_rejection_identifies_source_item_in_differentiated_push(monkeypatch):
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch)
    adapter = QuizAdapter()
    resolved = {
        "safe": {"tiers": [
            {"index": 0, "label": "variant_0", "group_name": "Blue", "group_id": "10",
             "student_count": 2, "membership_digest": "d1"},
            {"index": 1, "label": "variant_1", "group_name": "Gold", "group_id": "20",
             "student_count": 1, "membership_digest": "d2"},
        ]},
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(quiz_adapter_module, "resolve_assignment_groups", lambda *a, **k: resolved)

    calls = []
    def send(method, path, body, timeout=30):
        calls.append(path)
        if len(calls) == 4:  # item 1 of variant 0
            return None, "HTTP 422: invalid accept shape"
        if "quizzes" in path and "items" not in path and "modules" not in path:
            return {"id": 100}, None
        if isinstance(body, dict) and body.get("assignment", {}).get("only_visible_to_overrides"):
            return {"id": 101}, None
        if "overrides" in path:
            return {"id": 102}, None
        return {"id": 103}, None
    monkeypatch.setattr(canvas_client, "_canvas_send", send)

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    baseline = {"group_snapshot": resolved["safe"]}
    result = adapter.execute(
        payload, {"course_id": "101", "steps": []},
        baseline, {}, Context(),
    )

    assert result["state"] == "partial"
    assert result["failed_items"] == [{
        "item_index": 1,
        "field": "item",
        "id": "q1",
        "source_type": "MC",
        "canvas_status": 422,
        "reason": "Canvas rejected this quiz item.",
    }]
    assert "9001" not in json.dumps(result)


def test_second_variant_failure_is_partial(monkeypatch):
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch)
    adapter = QuizAdapter()
    resolved = {
        "safe": {"tiers": [
            {"index": 0, "label": "variant_0", "group_name": "Blue", "group_id": "10",
             "student_count": 2, "membership_digest": "d1"},
            {"index": 1, "label": "variant_1", "group_name": "Gold", "group_id": "20",
             "student_count": 1, "membership_digest": "d2"},
        ]},
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(quiz_adapter_module, "resolve_assignment_groups", lambda *a, **k: resolved)

    calls = []
    def send(method, path, body, timeout=30):
        calls.append(path)
        # Fail on first override of second variant (call index 3 after quiz, restrict, override of v0)
        if len(calls) == 4:
            return None, "HTTP 400: rejected"
        if "quizzes" in path and "items" not in path and "modules" not in path:
            return {"id": 100 + len(calls)}, None
        if isinstance(body, dict) and body.get("assignment", {}).get("only_visible_to_overrides"):
            return {"id": 1001}, None
        if "overrides" in path:
            return {"id": 700 + len(calls)}, None
        if "items" in path:
            return {"id": 200 + len(calls)}, None
        return {"id": 100 + len(calls)}, None
    monkeypatch.setattr(canvas_client, "_canvas_send", send)

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    baseline = {"group_snapshot": resolved["safe"]}
    result = adapter.execute(
        payload, {"course_id": "101", "steps": []},
        baseline, {}, Context(),
    )
    assert result["state"] == "partial"


def test_retry_verifies_exact_ids_and_resumes(monkeypatch):
    """Retry verifies completed variant quiz/items and resumes at next step."""
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch)
    adapter = QuizAdapter()
    resolved = {
        "safe": {"tiers": [
            {"index": 0, "label": "variant_0", "group_name": "Blue", "group_id": "10",
             "student_count": 2, "membership_digest": "d1"},
            {"index": 1, "label": "variant_1", "group_name": "Gold", "group_id": "20",
             "student_count": 1, "membership_digest": "d2"},
        ]},
        "student_ids_by_group": {"10": ["9001", "9002"], "20": ["9003"]},
    }
    monkeypatch.setattr(quiz_adapter_module, "resolve_assignment_groups", lambda *a, **k: resolved)

    # First variant's quiz and items already exist; GET returns them
    get_responses = [
        ({"id": 101, "title": "Algebra Quiz - Support"}, None),  # quiz verify v0
        ({"id": 201}, None),  # item verify v0:1
        ({"id": 202}, None),  # item verify v0:2
        ({"id": 101, "name": "Algebra Quiz - Support", "published": True}, None),  # assignment verify after patch v0
        ({"id": 701}, None),  # override verify v0:0
        ({"id": 401}, None),  # module item verify attach_module:0
        ({"id": 102, "name": "Algebra Quiz - Extend", "published": True}, None),  # verify patch v1
    ]
    _mockcanvas_get(monkeypatch, get_responses)
    _mockcanvas_get_all(monkeypatch, [
        ([{"id": 301, "name": "Unit 1"}], None),  # module lookup v0
        ([{"id": 301, "name": "Unit 1"}], None),  # module lookup v1
    ])

    # Only the second variant's quiz/items need to be created
    send_calls = _mock_canvas_send(monkeypatch, [
        ({"id": 102}, None),  # create_quiz:1
        ({"id": 1001}, None),  # restrict_assignment:1
        ({"id": 702}, None),  # create_override:1:0
        ({"id": 202}, None),  # create_item:1:1
        ({"id": 102}, None),  # patch_assignment:1
        ({"id": 402}, None),  # attach_module:1
    ])

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    baseline = {"group_snapshot": resolved["safe"]}

    # Pre-populate variant 0 completed steps
    existing_steps = [
        {"step_key": "create_quiz:0", "state": "applied", "returned_object_id": "101",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "restrict_assignment:0", "state": "applied",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "create_override:0:0", "state": "applied", "returned_object_id": "701",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "create_item:0:1", "state": "applied", "returned_object_id": "201",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "create_item:0:2", "state": "applied", "returned_object_id": "202",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "patch_assignment:0", "state": "applied",
         "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        {"step_key": "attach_module:0", "state": "applied", "returned_object_id": "401",
         "module_id": "301", "outbound_started_at": "2026-01-01T00:00:00+00:00"},
    ]

    context = Context()
    result = adapter.execute(
        payload, {"course_id": "101", "steps": copy.deepcopy(existing_steps)},
        baseline, {}, context,
    )
    assert result["state"] == "applied"
    assert len(send_calls) == 6  # quiz, restrict, override, item, patch, module for variant 1


def test_extra_time_buckets_create_separate_overrides(monkeypatch):
    """Extra-time roster creates separate override buckets per variant."""
    _mock_active_courses(monkeypatch)
    _mock_get_extra_time(monkeypatch, [
        {"id": "9001", "days": 3},
    ])
    adapter = QuizAdapter()
    resolved = {
        "safe": {"tiers": [
            {"index": 0, "label": "variant_0", "group_name": "Blue", "group_id": "10",
             "student_count": 2, "membership_digest": "d1"},
        ]},
        "student_ids_by_group": {"10": ["9001", "9002"]},
    }
    monkeypatch.setattr(quiz_adapter_module, "resolve_assignment_groups", lambda *a, **k: resolved)

    # Mock GET for verify-after-patch and module lookup
    _mockcanvas_get(monkeypatch, [
        ({"id": 101, "name": "Quiz", "published": True}, None),  # verify patch
    ])
    _mockcanvas_get_all(monkeypatch, [
        ([{"id": 301, "name": "Unit 1"}], None),  # module lookup
    ])

    writes = []
    def send(method, path, body, timeout=30):
        writes.append((path, copy.deepcopy(body)))
        if "quizzes" in path and "items" not in path and "modules" not in path:
            return {"id": 101}, None
        if isinstance(body, dict) and body.get("assignment", {}).get("only_visible_to_overrides"):
            return {"id": 1001}, None
        if "overrides" in path:
            return {"id": 700 + len(writes)}, None
        if "items" in path:
            return {"id": 201}, None
        if "modules" in path:
            return {"id": 301}, None
        return {"id": 100 + len(writes)}, None
    monkeypatch.setattr(canvas_client, "_canvas_send", send)

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A),
        "settings": {"due_at": "2026-08-01T23:59:00Z"},
    }
    baseline = {"group_snapshot": resolved["safe"]}
    context = Context()
    result = adapter.execute(
        payload, {"course_id": "101", "steps": []},
        baseline, {}, context,
    )
    assert result["state"] == "applied"

    # Should have created overrides
    override_writes = [(path, body) for path, body in writes if "overrides" in path]
    assert len(override_writes) >= 1

    # No PII in durable steps
    durable = json.dumps(context.steps)
    assert all(value not in durable for value in ("9001", "9002"))


# ── Reconciliation tests ─────────────────────────────────────────────────

def test_reconcile_verifies_variant_quiz_ids(monkeypatch):
    _mock_active_courses(monkeypatch)
    adapter = QuizAdapter()

    get_responses = []
    # Module GET (single module by ID)
    get_responses.append(({"id": 10, "name": "Unit 1"}, None))
    # Verify quiz 101
    get_responses.append(({"id": 101, "title": "Algebra Quiz - Support"}, None))
    # Verify items for variant 0
    get_responses.append(({"id": 201}, None))  # item 1
    get_responses.append(({"id": 202}, None))  # item 2
    # Module item GET for attach_module:0 (falls through to canvas_get_all)
    get_responses.append((None, "no match"))  # returned as (item, error); error truthy → fall through
    # Verify quiz 102
    get_responses.append(({"id": 102, "title": "Algebra Quiz - Extend"}, None))
    # Verify items for variant 1
    get_responses.append(({"id": 203}, None))  # item 1
    # Module item GET for attach_module:1 (falls through)
    get_responses.append((None, "no match"))
    _mockcanvas_get(monkeypatch, get_responses)
    _mockcanvas_get_all(monkeypatch, [
        ([{"id": 401, "type": "Assignment", "content_id": 101}], None),
        ([{"id": 402, "type": "Assignment", "content_id": 102}], None),
    ])

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    target = {
        "course_id": "101",
        "steps": [
            {"step_key": "create_module", "state": "applied", "returned_object_id": "10",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_quiz:0", "state": "applied", "returned_object_id": "101",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "restrict_assignment:0", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_override:0:0", "state": "applied", "returned_object_id": "701",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:0:1", "state": "applied", "returned_object_id": "201",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:0:2", "state": "applied", "returned_object_id": "202",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "patch_assignment:0", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "attach_module:0", "state": "applied", "returned_object_id": "401",
             "module_id": "10", "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_quiz:1", "state": "applied", "returned_object_id": "102",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "restrict_assignment:1", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_override:1:0", "state": "applied", "returned_object_id": "702",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:1:1", "state": "applied", "returned_object_id": "203",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "patch_assignment:1", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "attach_module:1", "state": "applied", "returned_object_id": "402",
             "module_id": "10", "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        ],
    }
    result = adapter.reconcile(payload, target, {})
    assert result["state"] == "applied"


def test_reconcile_missing_quiz_id_is_pending(monkeypatch):
    _mock_active_courses(monkeypatch)
    adapter = QuizAdapter()

    _mockcanvas_get(monkeypatch, [
        ([], None),  # no existing assignments found
    ])

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    target = {"course_id": "101", "steps": []}
    result = adapter.reconcile(payload, target, {})
    assert result["state"] == "pending"


def test_reconcile_no_pii_in_projected_steps(monkeypatch):
    """Verify projected reconciliation steps contain no student IDs."""
    _mock_active_courses(monkeypatch)
    adapter = QuizAdapter()

    _mockcanvas_get(monkeypatch, [
        ({"id": 101, "title": "Algebra Quiz - Support"}, None),
        ({"id": 201}, None),
        ({"id": 202}, None),
        ({"id": 102, "title": "Algebra Quiz - Extend"}, None),
        ({"id": 203}, None),
    ])
    _mockcanvas_get_all(monkeypatch, [
        ([{"id": 10, "name": "Unit 1"}], None),
        ([{"id": 401, "type": "Assignment", "content_id": 101}], None),
        ([{"id": 402, "type": "Assignment", "content_id": 102}], None),
    ])

    payload = {
        "mode": "differentiated",
        "variants": _make_variants(VARIANT_PLAN_A, VARIANT_PLAN_B),
    }
    target = {
        "course_id": "101",
        "steps": [
            {"step_key": "create_module", "state": "applied", "returned_object_id": "10",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_quiz:0", "state": "applied", "returned_object_id": "101",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "restrict_assignment:0", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_override:0:0", "state": "applied", "returned_object_id": "701",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:0:1", "state": "applied", "returned_object_id": "201",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:0:2", "state": "applied", "returned_object_id": "202",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "patch_assignment:0", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "attach_module:0", "state": "applied", "returned_object_id": "401",
             "module_id": "10", "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_quiz:1", "state": "applied", "returned_object_id": "102",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "restrict_assignment:1", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_override:1:0", "state": "applied", "returned_object_id": "702",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "create_item:1:1", "state": "applied", "returned_object_id": "203",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "patch_assignment:1", "state": "applied",
             "outbound_started_at": "2026-01-01T00:00:00+00:00"},
            {"step_key": "attach_module:1", "state": "applied", "returned_object_id": "402",
             "module_id": "10", "outbound_started_at": "2026-01-01T00:00:00+00:00"},
        ],
    }
    result = adapter.reconcile(payload, target, {})
    result_text = json.dumps(result)
    assert all(value not in result_text for value in ("9001", "9002", "9003"))
