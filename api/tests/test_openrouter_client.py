"""Offline tests for the OpenRouter client — request build, response parse, and the
injected-http score path. No network, no key."""
import json

import pytest

from api import openrouter_client as orc

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


def test_estimate_tokens_positive():
    assert orc.estimate_tokens(BUNDLE, "rubric") > 0
