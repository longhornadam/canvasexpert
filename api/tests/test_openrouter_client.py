"""Offline tests for the OpenRouter client — request build, response parse, and the
injected-http score path. No network, no key."""
import json
import base64

import pytest

from api import openrouter_client as orc
from api.webui import config

BUNDLE = {"quiz_title": "THG", "students": [
    {"pseudonym": "S001", "responses": [
        {"item_id": "1003", "prompt": "Why blue sky?", "response": "Scattering.", "possible": 10}]}]}
PERSONA = {"name": "Sage", "personality": "warm and specific"}


def test_build_request_shape():
    req = orc.build_request(BUNDLE, "RUBRIC TEXT HERE", PERSONA, "anthropic/claude-x")
    assert req["model"] == "anthropic/claude-x"
    system = req["messages"][0]["content"]
    assert "Sage" in system and "warm and specific" in system and "RUBRIC TEXT HERE" in system
    user = req["messages"][1]["content"]
    assert "S001" in user                       # pseudonymous bundle is the payload


def test_multimodal_request_puts_association_text_before_image(tmp_path):
    image = tmp_path / "safe.png"
    image.write_bytes(b"synthetic image bytes")
    bundle = {"quiz_title": "Synthetic", "students": [{
        "pseudonym": "S001", "responses": [{
            "item_id": "item-1", "prompt": "Look", "response": "See image.",
            "media": [{"item_id": "item-1", "local_path": str(image),
                       "media_type": "image/png", "filename": "attachment-1"}],
        }],
    }]}
    request = orc.build_request(bundle, "rubric", PERSONA, "vision/model")
    content = request["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert "pseudonym S001" in content[1]["text"]
    assert content[2]["type"] == "image_url"
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")
    assert str(image) not in json.dumps(request)


def test_budget_rejects_media_for_text_only_model():
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{"id": "text/model", "architecture": {"input_modalities": ["text"]},
                              "pricing": {"prompt": "0.000001", "completion": "0.000001"}}]}

    bundle = {"students": [{"pseudonym": "S001", "responses": [{
        "item_id": "1", "response": "x", "media": [{"item_id": "1", "local_path": __file__}],
    }]}]}
    result = orc.teacher_workflow_budget(
        bundle, "", "text/model", http_get=lambda *a, **k: _Resp(), student_count=1,
    )
    assert result["ok"] is False
    assert any("image input" in reason for reason in result["reasons"])


def test_parse_response_extracts_results():
    content = json.dumps([{"pseudonym": "S001", "item_id": "1003", "score": 9,
                           "feedback": "Good.", "disclosure": "AI."}])
    resp = {"choices": [{"message": {"content": content}}]}
    results = orc.parse_response(resp)
    assert results[0]["pseudonym"] == "S001" and results[0]["score"] == 9


def test_score_uses_injected_post_and_endpoint():
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(
                [{"pseudonym": "S001", "item_id": "1003", "score": 8, "feedback": "ok"}])}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url; captured["headers"] = headers; captured["body"] = json
        return _Resp()

    results = orc.score(BUNDLE, "RUBRIC", PERSONA, api_key="sk-test",
                        model="anthropic/claude-x", http_post=fake_post)
    assert results[0]["score"] == 8
    assert captured["url"] == orc.ENDPOINT
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_score_requires_key():
    with pytest.raises(ValueError):
        orc.score(BUNDLE, "", PERSONA, api_key="", model="m")


def test_score_reports_non_json_response_body():
    class _Resp:
        status_code = 200
        text = "<html>provider unavailable</html>"

        def raise_for_status(self): pass

        def json(self):
            raise json.JSONDecodeError("Expecting value", "", 0)

    with pytest.raises(orc.OpenRouterResponseError) as exc:
        orc.score(
            BUNDLE,
            "RUBRIC",
            PERSONA,
            api_key="sk-test",
            model="anthropic/claude-x",
            http_post=lambda *a, **k: _Resp(),
        )

    msg = str(exc.value)
    assert "OpenRouter scoring returned non-JSON response" in msg
    assert "HTTP 200" in msg
    assert "provider unavailable" in msg


def test_model_pricing_reports_empty_non_json_response():
    class _Resp:
        status_code = 503
        text = ""

        def raise_for_status(self): pass

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    with pytest.raises(orc.OpenRouterResponseError) as exc:
        orc.model_pricing("deepseek/deepseek-v4-pro", http_get=lambda *a, **k: _Resp())

    msg = str(exc.value)
    assert "OpenRouter model list returned non-JSON response" in msg
    assert "HTTP 503" in msg
    assert "<empty response body>" in msg


def test_score_reports_http_error_response_body():
    class _Resp:
        status_code = 429
        text = '{"error":{"message":"rate limited by provider"}}'

        def raise_for_status(self):
            raise RuntimeError("429 Client Error")

        def json(self):
            raise AssertionError("json should not be parsed after HTTP failure")

    with pytest.raises(orc.OpenRouterResponseError) as exc:
        orc.score(
            BUNDLE,
            "RUBRIC",
            PERSONA,
            api_key="sk-test",
            model="anthropic/claude-x",
            http_post=lambda *a, **k: _Resp(),
        )

    msg = str(exc.value)
    assert "OpenRouter scoring returned HTTP 429" in msg
    assert "rate limited by provider" in msg
    assert exc.value.status_code == "429"


def test_estimate_tokens_positive():
    assert orc.estimate_tokens(BUNDLE, "rubric") > 0
    assert orc.estimate_request_input_tokens(BUNDLE, "rubric", PERSONA) >= orc.estimate_tokens(BUNDLE, "rubric")


def test_teacher_budget_allows_default_model():
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{"id": "deepseek/deepseek-v4-pro",
                              "pricing": {"prompt": "0.000000435",
                                          "completion": "0.00000087"}}]}

    verdict = orc.teacher_workflow_budget(
        BUNDLE, "rubric", "deepseek/deepseek-v4-pro", student_count=30,
        http_get=lambda *a, **k: _Resp(),
    )
    assert verdict["ok"] is True
    assert verdict["pricing"]["input_per_mtok"] == pytest.approx(0.435)
    assert verdict["pricing"]["output_per_mtok"] == pytest.approx(0.87)


def test_teacher_budget_allows_output_token_preset():
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{"id": "deepseek/deepseek-v4-pro",
                              "pricing": {"prompt": "0.000000435",
                                          "completion": "0.00000087"}}]}

    verdict = orc.teacher_workflow_budget(
        BUNDLE,
        "rubric",
        "deepseek/deepseek-v4-pro",
        student_count=4,
        output_tokens_per_student=600,
        http_get=lambda *a, **k: _Resp(),
    )

    assert verdict["estimated_output_tokens"] == 2400


def test_teacher_budget_allows_verified_premium_model_with_warning():
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": [{"id": "openai/gpt-5.5",
                              "pricing": {"prompt": "0.000005",
                                          "completion": "0.00003"}}]}

    verdict = orc.teacher_workflow_budget(
        BUNDLE, "rubric", "openai/gpt-5.5", student_count=30,
        http_get=lambda *a, **k: _Resp(),
    )
    assert verdict["ok"] is True
    assert verdict["pricing"]["output_per_mtok"] == pytest.approx(30.00)
    assert any("premium-priced model" in r for r in verdict["warnings"])


def test_teacher_budget_blocks_auto_router():
    verdict = orc.teacher_workflow_budget(BUNDLE, "", "openrouter/auto", student_count=1)
    assert verdict["ok"] is False
    assert any("Auto Router" in r for r in verdict["reasons"])


def test_teacher_budget_blocks_unverified_model_pricing():
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"data": []}

    verdict = orc.teacher_workflow_budget(
        BUNDLE, "rubric", "some/new-model", student_count=30,
        http_get=lambda *a, **k: _Resp(),
    )
    assert verdict["ok"] is False
    assert any("live pricing could not be verified" in r for r in verdict["reasons"])


def test_legacy_auto_router_setting_resolves_to_default(monkeypatch):
    monkeypatch.setattr(config._io, "_machine_load", lambda: {"openrouter_model": "openrouter/auto"})
    assert config.get_openrouter_model() == "deepseek/deepseek-v4-pro"


def test_model_presets_start_with_default_and_include_latest_aliases():
    presets = config.openrouter_model_presets()
    ids = [p["id"] for p in presets]
    assert ids[0] == config.DEFAULT_OPENROUTER_MODEL
    assert any("-latest" in model_id for model_id in ids)
    assert all("input_per_mtok" in p and "output_per_mtok" in p for p in presets)
    assert all("scenario_cost" in p for p in presets)
    assert any(p["id"] == "~anthropic/claude-sonnet-latest" for p in presets)
    assert any(p["id"] == "~openai/gpt-latest" for p in presets)
    assert any(p.get("cost_tier") == "$$$" for p in presets if "-latest" in p["id"])
