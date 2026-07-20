"""Parser handling of the two rationale shapes + the choice-id auto-fix."""

import logging

from engine.spec_engine.parser import parse_news_json


def _spec(body: str) -> str:
    return "<QUIZFORGE_JSON>\n" + body + "\n</QUIZFORGE_JSON>"


_ITEMS = '"items":[{"type":"TF","prompt":"x","answer":true}]'


def test_single_string_rationale_is_accepted():
    """The single-rationale form (non-MC types) is now carried, not dropped."""
    spec = _spec(
        '{"version":"3.0-json","title":"T",' + _ITEMS +
        ',"rationales":[{"item_id":"q1","rationale":"True because reasons."}]}'
    )
    payload = parse_news_json(spec)
    assert len(payload.rationales) == 1
    assert payload.rationales[0].text == "True because reasons."
    assert payload.rationales[0].choices == []


def test_per_choice_rationale_is_accepted():
    spec = _spec(
        '{"version":"3.0-json","title":"T",' + _ITEMS +
        ',"rationales":[{"item_id":"q1","choices":['
        '{"id":"A","correct":true,"rationale":"why A"},'
        '{"id":"B","correct":false,"rationale":"why B"}]}]}'
    )
    payload = parse_news_json(spec)
    assert len(payload.rationales[0].choices) == 2


def test_choice_missing_id_is_auto_assigned():
    """A choice with no id gets A/B/... by position instead of being dropped."""
    spec = _spec(
        '{"version":"3.0-json","title":"T",' + _ITEMS +
        ',"rationales":[{"item_id":"q1","choices":['
        '{"correct":true,"rationale":"why first"},'
        '{"correct":false,"rationale":"why second"}]}]}'
    )
    payload = parse_news_json(spec)
    ids = [c.id for c in payload.rationales[0].choices]
    assert ids == ["A", "B"]


def test_missing_item_id_rationale_warns_and_drops(caplog):
    spec = _spec(
        '{"version":"3.0-json","title":"T",' + _ITEMS +
        ',"rationales":[{"rationale":"no item_id here"}]}'
    )
    with caplog.at_level(logging.WARNING, logger="engine.spec_engine.parser"):
        payload = parse_news_json(spec)
    assert payload.rationales == []
    assert any("missing or non-string 'item_id'" in r.getMessage() for r in caplog.records)
