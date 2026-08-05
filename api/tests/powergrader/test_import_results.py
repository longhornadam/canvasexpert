import copy
import json
import sys
import threading
from pathlib import Path

from api.feedback_vault import Vault

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.powergrader.import_results import import_results_into_session
from api.webui.routes import powergrader as powergrader_routes


def _bundle(first_pseudonym, second_pseudonym):
    return {
        "contract_version": "1.0",
        "quiz_title": "Fictional Essay",
        "students": [
            {
                "pseudonym": first_pseudonym,
                "responses": [{
                    "item_id": "101",
                    "prompt": "",
                    "response": "A safe fictional response.",
                    "possible": 2,
                }],
            },
            {
                "pseudonym": second_pseudonym,
                "responses": [{
                    "item_id": "202",
                    "prompt": "",
                    "response": "Another safe fictional response.",
                    "possible": 2,
                }],
            },
        ],
    }


def _result(pseudonym, item_id, feedback="Clear evidence.", observation=""):
    return [{
        "pseudonym": pseudonym,
        "item_id": item_id,
        "score": 2,
        "feedback": feedback,
        "disclosure": "Drafted by Sage (AI), reviewed by your teacher.",
        **({"writing_process_observations": observation} if observation else {}),
    }]


def _session(tmp_path, vault):
    first = vault.get_or_assign("9001", "Ada Lovelace", "5001")
    second = vault.get_or_assign("9002", "Alan Turing", "5002")
    vault.save()
    safe_bundle = tmp_path / "safe_bundle.json"
    safe_bundle.write_text(json.dumps(_bundle(first, second)), encoding="utf-8")
    return {
        "session_id": "sid",
        "privacy_artifacts": {"safe_bundle": str(safe_bundle)},
        "students": [
            {"user_id": "9001", "real_name": "Ada Lovelace", "ai_score": None, "ai_feedback": None},
            {"user_id": "9002", "real_name": "Alan Turing", "ai_score": None, "ai_feedback": None},
        ],
        "copilot_packet": {
            "batches": [
                {
                    "batch_id": "batch-01",
                    "status": "pending",
                    "expected_results": [{"pseudonym": first, "item_id": "101"}],
                },
                {
                    "batch_id": "batch-02",
                    "status": "pending",
                    "expected_results": [{"pseudonym": second, "item_id": "202"}],
                },
            ],
        },
    }, first, second


def _run_import(session, vault, results, batch_id=""):
    saved = {}
    payload, status = import_results_into_session(
        "sid",
        json.dumps(results),
        batch_id=batch_id,
        load_session=lambda session_id: session,
        save_session=lambda s: saved.update(s),
        vault_factory=lambda: vault,
    )
    return payload, status, saved


def _response_json(response):
    return json.loads(response.body)


def _route_session(tmp_path, vault):
    session, first, second = _session(tmp_path, vault)
    session.update({
        "course_id": "course-1",
        "assignment_id": "assignment-1",
        "assignment_name": "Fictional Essay",
        "mode": "packet",
        "canvas_writeback_supported": True,
        "auto_post": {
            "enabled": True,
            "authorized_at": "2026-07-15T12:00:00+00:00",
            "disabled_at": None,
            "policy_version": 2,
        },
        "auto_post_log": [],
        "auto_post_summary": None,
    })
    session["students"][0].update({
        "submission_id": "submission-9001",
        "body": "A fictional submitted response.",
        "posted": False,
        "status": "pending",
        "submission_baseline": {
            "attempt": 1,
            "submitted_at": "2026-07-15T11:00:00Z",
        },
    })
    session["students"][1].update({
        "submission_id": "submission-9002",
        "body": "Another fictional submitted response.",
        "posted": False,
        "status": "pending",
        "submission_baseline": {
            "attempt": 1,
            "submitted_at": "2026-07-15T11:05:00Z",
        },
    })
    return session, first, second


def _fresh_submission(user_id="9001"):
    submitted_at = "2026-07-15T11:00:00Z" if user_id == "9001" else "2026-07-15T11:05:00Z"
    return {
        "id": f"submission-{user_id}",
        "user_id": user_id,
        "attempt": 1,
        "submitted_at": submitted_at,
        "workflow_state": "submitted",
        "excused": False,
        "score": None,
        "submission_comments": [],
        "assignment": {
            "id": "assignment-1",
            "course_id": "course-1",
            "points_possible": 2,
            "submission_types": ["online_text_entry"],
            "grading_type": "points",
            "group_category_id": None,
        },
    }


def _persisted_route_environment(monkeypatch, tmp_path, session, vault_path, *, canvas_get_all):
    """Use the real disk session store while asserting route lock ownership."""
    store = powergrader_routes.session_store
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(store, "pg_dir", lambda: str(sessions_dir))
    real_load = store.load_session
    real_save = store.save_session
    real_lock = store.session_lock
    real_save(copy.deepcopy(session))

    boundary_events = []

    def lock_owned():
        lock = real_lock(session["session_id"])
        return bool(getattr(lock, "_is_owned")())

    def locked_load(session_id):
        assert lock_owned(), "route loaded authoritative session outside session_lock"
        boundary_events.append("load")
        return real_load(session_id)

    def locked_save(saved_session):
        assert lock_owned(), "route saved authoritative session outside session_lock"
        boundary_events.append("save")
        real_save(saved_session)

    sends = []
    sends_guard = threading.Lock()

    def canvas_send(method, path, payload):
        assert lock_owned(), "Canvas PUT occurred outside session_lock"
        with sends_guard:
            sends.append((method, path, copy.deepcopy(payload)))
        return {"ok": True}

    monkeypatch.setattr(powergrader_routes, "_load_session", locked_load)
    monkeypatch.setattr(powergrader_routes, "_save_session", locked_save)
    monkeypatch.setattr(powergrader_routes, "_vault", lambda: Vault(str(vault_path)))
    monkeypatch.setattr(powergrader_routes, "canvas_get_all", canvas_get_all)
    monkeypatch.setattr(
        powergrader_routes,
        "canvas_get",
        lambda path: (_fresh_submission()["assignment"], None),
    )
    monkeypatch.setattr(powergrader_routes, "_canvas_send", canvas_send)
    return {
        "store": store,
        "real_load": real_load,
        "real_save": real_save,
        "real_lock": real_lock,
        "lock_owned": lock_owned,
        "boundary_events": boundary_events,
        "sends": sends,
    }


def test_batch_import_updates_only_matching_batch(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(first, "101"), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert payload["batch_status"] == "imported"
    assert saved["students"][0]["ai_score"] == 2
    assert "Clear evidence" in saved["students"][0]["ai_feedback"]
    assert saved["students"][1]["ai_score"] is None
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"
    assert saved["copilot_packet"]["batches"][1]["status"] == "pending"


def test_batch_import_preserves_teacher_only_writing_observation_separately(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, _ = _session(tmp_path, vault)
    observation = "Revision activity spans several fictional timestamps."

    payload, status, saved = _run_import(
        session,
        vault,
        _result(first, "101", observation=observation),
        "batch-01",
    )

    assert status == 200
    assert payload["ok"] is True
    student = saved["students"][0]
    assert student["writing_process_observations"] == observation
    assert observation not in student["ai_feedback"]


def test_wrong_batch_paste_fails_without_updates(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(second, "202"), "batch-01")

    assert status == 200
    assert payload["ok"] is False
    assert "do not belong to this Copilot batch" in payload["error"]
    assert saved == {}
    assert session["students"][0]["ai_score"] is None
    assert session["students"][1]["ai_score"] is None
    assert session["copilot_packet"]["batches"][0]["status"] == "pending"
    assert session["copilot_packet"]["batches"][1]["status"] == "pending"


def test_batch_reimport_updates_feedback_and_keeps_imported(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(first, "101", "Original feedback."), "batch-01")
    assert status == 200
    assert payload["ok"] is True
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"

    payload, status, saved = _run_import(session, vault, _result(first, "101", "Revised feedback."), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"
    assert "Revised feedback" in saved["students"][0]["ai_feedback"]
    assert saved["copilot_packet"]["batches"][1]["status"] == "pending"


def test_partial_batch_import_marks_partial_and_warns(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)
    session["copilot_packet"]["batches"][0]["expected_results"].append(
        {"pseudonym": second, "item_id": "202"}
    )

    payload, status, saved = _run_import(session, vault, _result(first, "101"), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert payload["batch_status"] == "partial"
    assert saved["copilot_packet"]["batches"][0]["status"] == "partial"
    assert any("no result for" in warning for warning in payload["validation"]["warnings"])


def test_legacy_import_without_copilot_packet_still_works(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)
    session.pop("copilot_packet")

    payload, status, saved = _run_import(session, vault, _result(first, "101"))

    assert status == 200
    assert payload["ok"] is True
    assert "batch_id" not in payload
    assert saved["students"][0]["ai_score"] == 2
    assert "Clear evidence" in saved["students"][0]["ai_feedback"]
    assert saved["students"][1]["ai_score"] is None


def test_batch_with_nonexistent_bundle_fails_closed(tmp_path):
    """When a batch names a safe_bundle path that is missing, the import
    must fail closed instead of silently falling back to the top-level bundle."""
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)
    # Point the batch at a nonexistent bundle path
    session["copilot_packet"]["batches"][0]["safe_bundle"] = str(tmp_path / "nonexistent.json")

    payload, status, saved = _run_import(session, vault, _result(first, "101"), "batch-01")

    assert status == 200
    assert payload["ok"] is False
    assert "Safe AI Packet student response bundle is missing" in payload["error"]
    assert saved == {}


def test_concurrent_route_imports_are_serialized_and_make_one_put(monkeypatch, tmp_path):
    """Two route triggers share one authoritative load-through-save lock boundary."""
    vault_path = tmp_path / "vault.json"
    vault = Vault(str(vault_path))
    session, first, _ = _route_session(tmp_path, vault)
    env = _persisted_route_environment(
        monkeypatch,
        tmp_path,
        session,
        vault_path,
        canvas_get_all=lambda path, params: ([_fresh_submission()], None),
    )
    results_json = json.dumps(_result(first, "101"))
    start = threading.Barrier(3)
    outcomes = []
    outcomes_guard = threading.Lock()

    def import_route():
        start.wait(timeout=5)
        response = powergrader_routes.pg_import_results(
            "sid", results=results_json, batch_id="batch-01"
        )
        with outcomes_guard:
            outcomes.append(_response_json(response))

    threads = [threading.Thread(target=import_route, name=f"route-import-{i}") for i in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert len(outcomes) == 2
    assert all(result["ok"] is True for result in outcomes)
    assert len(env["sends"]) == 1
    assert env["sends"][0][0] == "PUT"
    assert env["boundary_events"][0] == "load"
    assert env["boundary_events"][-1] == "save"
    persisted = env["real_load"]("sid")
    assert persisted["students"][0]["posted"] is True
    assert persisted["students"][0]["status"] == "auto_pushed"


def test_disable_serializes_first_and_stale_import_cannot_reenable(monkeypatch, tmp_path):
    """A queued import reloads after disable and retains drafts without any PUT."""
    vault_path = tmp_path / "vault.json"
    vault = Vault(str(vault_path))
    session, first, _ = _route_session(tmp_path, vault)
    stale_enabled_session = copy.deepcopy(session)
    env = _persisted_route_environment(
        monkeypatch,
        tmp_path,
        session,
        vault_path,
        canvas_get_all=lambda path, params: ([_fresh_submission()], None),
    )
    results_json = json.dumps(_result(first, "101"))
    original_lock = env["real_lock"]
    import_waiting = threading.Event()
    prelock_loads = []
    prelock_saves = []

    def tracked_session_lock(session_id):
        lock = original_lock(session_id)
        if threading.current_thread().name == "stale-import":
            import_waiting.set()
        return lock

    def authoritative_load(session_id):
        if not env["lock_owned"]():
            prelock_loads.append(session_id)
            return copy.deepcopy(stale_enabled_session)
        env["boundary_events"].append("load")
        return env["real_load"](session_id)

    def authoritative_save(saved_session):
        if not env["lock_owned"]():
            prelock_saves.append(bool((saved_session.get("auto_post") or {}).get("enabled")))
        env["boundary_events"].append("save")
        env["real_save"](saved_session)

    monkeypatch.setattr(env["store"], "session_lock", tracked_session_lock)
    monkeypatch.setattr(powergrader_routes, "_load_session", authoritative_load)
    monkeypatch.setattr(powergrader_routes, "_save_session", authoritative_save)

    import_result = {}

    def run_import():
        response = powergrader_routes.pg_import_results(
            "sid", results=results_json, batch_id="batch-01"
        )
        import_result.update(_response_json(response))

    with original_lock("sid"):
        thread = threading.Thread(target=run_import, name="stale-import")
        thread.start()
        assert import_waiting.wait(timeout=5)
        disable = _response_json(powergrader_routes.pg_auto_post_disable("sid"))
        assert disable["ok"] is True
        assert disable["auto_post"]["enabled"] is False
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert import_result["ok"] is True
    assert prelock_loads == []
    assert prelock_saves == []
    assert env["sends"] == []
    persisted = env["real_load"]("sid")
    assert persisted["auto_post"]["enabled"] is False
    assert persisted["auto_post"]["disabled_at"]
    assert persisted["students"][0]["ai_score"] == 2
    assert persisted["students"][0]["posted"] is False


def test_import_route_fresh_fetch_failure_persists_skipped_summary(monkeypatch, tmp_path):
    """A Canvas read failure is a normal saved draft result, not a route exception."""
    vault_path = tmp_path / "vault.json"
    vault = Vault(str(vault_path))
    session, first, _ = _route_session(tmp_path, vault)
    env = _persisted_route_environment(
        monkeypatch,
        tmp_path,
        session,
        vault_path,
        canvas_get_all=lambda path, params: (None, "fictional Canvas read failure"),
    )

    response = powergrader_routes.pg_import_results(
        "sid", results=json.dumps(_result(first, "101")), batch_id="batch-01"
    )
    payload = _response_json(response)

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["updated_user_ids"] == ["9001"]
    assert payload["auto_post_summary"]["pushed"] == 0
    assert payload["auto_post_summary"]["skipped_reason"].startswith("fresh_fetch_failed:")
    assert env["sends"] == []
    persisted = env["real_load"]("sid")
    assert persisted["students"][0]["ai_score"] == 2
    assert persisted["students"][0]["posted"] is False
    assert persisted["auto_post_summary"]["skipped_reason"].startswith("fresh_fetch_failed:")
    assert persisted["auto_post_log"][-1]["trigger"] == "packet_import"
    assert persisted["auto_post_log"][-1]["skipped_reason"].startswith("fresh_fetch_failed:")
