from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tools import canvasmirror_release_benchmark as benchmark


def test_synthetic_self_check_writes_only_aggregate_output(tmp_path):
    output = tmp_path / "release.json"
    result = benchmark.synthetic_self_check(output, workspace_root=tmp_path / "workspace")
    assert result["classification"] == "synthetic_self_check"
    assert json.loads(output.read_text(encoding="utf-8"))["aggregate"]["bytes"] == 0


def test_output_refuses_repo_or_workspace():
    with pytest.raises(ValueError):
        benchmark.validate_output_path(benchmark.REPO_ROOT / "release.json")
    with pytest.raises(ValueError):
        benchmark.validate_output_path("C:/tmp/release.json", workspace_root="C:/tmp")


def test_live_readonly_orchestration_uses_fresh_roots_and_aggregate_only_output():
    from api.mirror import store
    roots, full_calls, delta_calls, focused_calls = [], [], [], []

    def temp_root():
        root = Path(tempfile.mkdtemp(prefix="release-test-"))
        roots.append(root)
        return root

    def context(course_id, **_kwargs):
        return {"state": "current", "lifecycle": "current" if course_id == "c" else "concluded"}

    def full(course_id, *, root, skip_new_quiz_metadata, **_kwargs):
        full_calls.append((course_id, skip_new_quiz_metadata, root))
        store.write_assignments(course_id, [{"id": "private-assignment", "name": "Private"}], root=root)
        return {"ok": True}

    def delta(course_id, *, root, **_kwargs):
        delta_calls.append((course_id, root))
        return {"ok": True}

    def focused(course_id, assignment_id, *, root, **_kwargs):
        focused_calls.append((course_id, assignment_id, root))
        return {"ok": True}

    result = benchmark.run_live_readonly(
        [{"id": "c"}, {"id": "x"}, {"id": "y"}], canvas_get=lambda *_a, **_k: ({}, None),
        canvas_get_all=lambda *_a, **_k: ([], None),
        canvas_get_all_complete=lambda *_a, **_k: ([], None, True), context_refresh=context,
        full_pass=full, delta_pass=delta, focused_refresh=focused, temp_root_factory=temp_root,
        focused_assignment_id="private-assignment")
    assert result["classification"] == "live_readonly"
    assert result["cold"]["run_count"] == result["warm"]["run_count"] == result["focused"]["run_count"] == 3
    assert len(full_calls) == 9 and all(skip for course, skip, _root in full_calls if course in {"x", "y"})
    assert [course for course, _root in delta_calls] == ["c", "c", "c"]
    assert len(focused_calls) == 3
    assert all(not root.exists() for root in roots)
    assert "private-assignment" not in json.dumps(result) and '"c"' not in json.dumps(result)


def test_live_readonly_refuses_non_matching_profile_and_cleans_validation_root():
    roots = []

    def temp_root():
        root = Path(tempfile.mkdtemp(prefix="release-test-"))
        roots.append(root)
        return root

    with pytest.raises(benchmark.ProfileRefusal):
        benchmark.run_live_readonly(
            [{"id": "only"}], canvas_get=lambda *_a, **_k: ({}, None),
            canvas_get_all=lambda *_a, **_k: ([], None),
            canvas_get_all_complete=lambda *_a, **_k: ([], None, True),
            context_refresh=lambda *_a, **_k: {"state": "current", "lifecycle": "current"},
            temp_root_factory=temp_root)
    assert roots and all(not root.exists() for root in roots)
