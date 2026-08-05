import json

import pytest

from api import ai_transmission, openrouter_client, operational_log
from api.feedback_vault import Vault
from api.platform_services import canvas_client


def _reset_operational_log():
    with operational_log._LOCK:
        if operational_log._HANDLER is not None:
            operational_log._LOGGER.removeHandler(operational_log._HANDLER)
            operational_log._HANDLER.close()
        operational_log._HANDLER = None
        operational_log._HANDLER_PATH = None


def _safe_bundle():
    return {
        "contract_version": "synthetic",
        "students": [
            {"pseudonym": "P-T1", "responses": [{"item_id": "item-t1", "response": "text"}]},
            {"pseudonym": "P-M1", "responses": [{"item_id": "item-m1", "response": "media", "media": [{"item_id": "item-m1"}]}]},
            {"pseudonym": "P-M2", "responses": [{"item_id": "item-m2", "response": "media", "media": [{"item_id": "item-m2"}]}]},
        ],
    }


def test_unsafe_bundle_cannot_reach_budget_or_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _reset_operational_log()
    vault = Vault(str(tmp_path / "vault.json"))
    with vault.transaction():
        vault.get_or_assign("student-1", "Synthetic Student", "sis-1")

    counters = {"budget": 0, "transport": 0}

    def budget(*_args, **_kwargs):
        counters["budget"] += 1
        return {"ok": True, "model_metadata": {"input_modalities": ["text"]}}

    def transport(*_args, **_kwargs):
        counters["transport"] += 1
        return []

    monkeypatch.setattr(ai_transmission.openrouter_client, "teacher_workflow_budget", budget)
    unsafe = {
        "students": [{
            "pseudonym": "P-1",
            "real_name": "Synthetic Student",
            "canvas_id": "student-1",
            "responses": [{"item_id": "item-1", "response": "answer"}],
        }],
    }
    with pytest.raises(ai_transmission.TransmissionSafetyBlocked):
        ai_transmission.score_openrouter_bundle(
            unsafe,
            vault,
            "rubric",
            {"name": "TA"},
            api_key="synthetic-key",
            model="synthetic-model",
            feedback_pattern=None,
            output_tokens_per_student=100,
            transport=transport,
        )
    assert counters == {"budget": 0, "transport": 0}

    clean = {"students": [{"pseudonym": "P-1", "responses": [{"item_id": "item-1", "response": "answer"}]}]}
    real_scan = ai_transmission.feedback_safety.scan_payload
    scan_calls = {"count": 0}

    def unsafe_exact_scan(payload, checked_vault):
        scan_calls["count"] += 1
        if scan_calls["count"] == 2:
            return {"green": False, "hard": ["synthetic"], "soft": []}
        return real_scan(payload, checked_vault)

    monkeypatch.setattr(ai_transmission.feedback_safety, "scan_payload", unsafe_exact_scan)
    with pytest.raises(ai_transmission.TransmissionSafetyBlocked):
        ai_transmission.score_openrouter_bundle(
            clean,
            vault,
            "rubric",
            {"name": "TA"},
            api_key="synthetic-key",
            model="synthetic-model",
            feedback_pattern=None,
            output_tokens_per_student=100,
            transport=transport,
        )
    assert counters["budget"] == 1
    assert counters["transport"] == 0
    serialized = json.dumps(operational_log.tail())
    assert "Synthetic Student" not in serialized
    assert "student-1" not in serialized
    assert "synthetic-key" not in serialized


def test_safe_send_and_canvas_failure_emit_only_allowlisted_records(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    _reset_operational_log()
    vault = Vault(str(tmp_path / "vault.json"))
    calls = []

    monkeypatch.setattr(
        ai_transmission.openrouter_client,
        "teacher_workflow_budget",
        lambda *args, **kwargs: {
            "ok": True,
            "estimated_cost": 0.01,
            "model_metadata": {"model": "synthetic-model", "input_modalities": ["text", "image"]},
        },
    )

    def transport(bundle, *_args, **kwargs):
        calls.append((bundle["students"][0]["pseudonym"], kwargs["model_metadata"]))
        student = bundle["students"][0]
        return [{"pseudonym": student["pseudonym"], "item_id": student["responses"][0]["item_id"], "score": 8}]

    result = ai_transmission.score_openrouter_bundle(
        _safe_bundle(),
        vault,
        "rubric",
        {"name": "TA"},
        api_key="synthetic-key",
        model="synthetic-model",
        feedback_pattern=None,
        output_tokens_per_student=100,
        transport=transport,
    )
    assert result["requested"] == 3
    assert result["successful"] == 3
    assert len(result["results"]) == 3
    assert len(calls) == 3
    assert all(metadata["model"] == "synthetic-model" for _, metadata in calls)

    class CanvasResponse:
        status_code = 500
        text = (
            "Synthetic Student student-1 sk-test-token https://synthetic.invalid/private "
            "C:\\Synthetic\\private.txt"
        )

    monkeypatch.setattr(canvas_client.config, "get_token", lambda: "synthetic-token")
    monkeypatch.setattr(canvas_client.config, "get_canvas_base", lambda: "https://canvas.invalid")
    monkeypatch.setattr(canvas_client.requests, "get", lambda *args, **kwargs: CanvasResponse())
    data, error = canvas_client.canvas_get("/synthetic", timeout=1)
    assert data is None
    assert "HTTP 500" in error
    assert "Synthetic Student" in error

    records = operational_log.tail()
    allowed = {
        "timestamp", "app_version", "event", "outcome", "duration_ms",
        "status_code", "error_class", "count",
    }
    assert records
    assert all(set(record) <= allowed for record in records)
    assert all(record["app_version"] for record in records)
    assert all(isinstance(record.get("duration_ms"), int) and record["duration_ms"] >= 0 for record in records)
    assert all("status_code" not in record or isinstance(record["status_code"], int) for record in records)
    assert all("count" not in record or isinstance(record["count"], int) for record in records)
    serialized = json.dumps(records)
    for sensitive in (
        "Synthetic Student", "student-1", "sk-test-token", "https://synthetic.invalid/private",
        "C:\\Synthetic\\private.txt",
    ):
        assert sensitive not in serialized
