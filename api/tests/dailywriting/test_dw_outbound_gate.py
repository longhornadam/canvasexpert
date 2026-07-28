"""The outbound safety gate must see this subsystem's fields (INV-7).

`api.feedback_safety.scan_payload` is field-name-keyed: it scans free text only
in the names listed in `_TEXT_FIELDS`. A payload carrying student writing under
an unlisted name is not scanned at all and comes back green whatever is inside
it. That is a quiet failure mode, so it gets a test rather than a comment.
"""
from __future__ import annotations

import pytest

from api import feedback_safety
from api.dailywriting.core import scrub
from api.dailywriting.fixtures import loader


class _FixtureVault:
    """Minimal vault surface: what `feedback_safety` and `feedback_scrub` read."""

    def __init__(self, section: str = "section_2a"):
        self._entries = loader.vault_entries(section)

    def entries(self):
        return list(self._entries)

    def all_real_identifiers(self):
        names: set[str] = set()
        ids: set[str] = set()
        for entry in self._entries:
            names.add(entry["real_name"])
            names.update(entry["real_name"].split())
            names.update(entry.get("nicknames", []))
            ids.add(str(entry["canvas_id"]))
            ids.add(str(entry["sis_id"]))
        return names, ids


@pytest.fixture
def vault() -> _FixtureVault:
    return _FixtureVault()


# Every free-text field this subsystem can put student writing into.
# "score_note" is the outbound key for ItemResult.note
# (api/dailywriting/projection.py's _item_result_row): several of
# core.scoring's notes interpolate a slice of the student's own thesis,
# argument, or commentary, so the field is exactly as identity-bearing as a
# quoted span, not machine-only prose. Named "score_note" rather than the
# model's own "note" because a bare "note" key already has different,
# non-text semantics elsewhere in this codebase -- see the comment above
# feedback_safety._TEXT_FIELDS.
DAILYWRITING_TEXT_FIELDS = (
    "raw_text", "evidence_span", "claim_text", "next_focus",
    "student_facing_text", "prompt_text", "strong_text", "near_miss_text",
    "one_thing", "acknowledgment", "score_note",
)


@pytest.mark.parametrize("field", DAILYWRITING_TEXT_FIELDS)
def test_every_dailywriting_text_field_is_scanned(field, vault):
    """A raw name under any of these names must not come back green."""
    verdict = feedback_safety.scan_payload(
        {field: "Marcus texts him all through science class"}, vault)
    assert not verdict["green"] or verdict["soft"], (
        f"a real roster name inside {field!r} was neither blocked nor flagged; "
        "the field is missing from feedback_safety._TEXT_FIELDS"
    )


@pytest.mark.parametrize("field", DAILYWRITING_TEXT_FIELDS)
def test_a_real_id_in_a_dailywriting_field_is_a_hard_block(field, vault):
    verdict = feedback_safety.scan_payload({field: "my number is F990001"}, vault)
    assert not verdict["green"]
    assert verdict["hard"]


def test_the_declared_field_set_matches_what_the_gate_actually_scans():
    """Keeps this test honest if someone trims the gate's set later."""
    missing = set(DAILYWRITING_TEXT_FIELDS) - feedback_safety._TEXT_FIELDS
    assert not missing, (
        f"field(s) {sorted(missing)} are produced by api/dailywriting but are "
        "no longer scanned by the outbound gate"
    )


def test_a_properly_scrubbed_span_still_passes(vault, roster_map):
    """The gate must not become so broad that clean pseudonymised text fails."""
    scrubbed = scrub.scrub_writing(
        "My brother Diego says Marcus texts him all through science class.",
        roster_map=roster_map, protected=set())
    verdict = feedback_safety.scan_payload(
        {"evidence_span": scrubbed.text}, vault)
    assert verdict["green"], verdict
    assert not verdict["soft"]


def test_canvas_id_stays_a_forbidden_key_so_stored_records_cannot_be_exported(
        vault):
    """Records are keyed by canvas_id on disk; that key must never go outbound.

    This is the property that makes a canvas-id-keyed private store safe: if a
    stored record is ever handed to a payload builder wholesale, the gate stops
    it on the key alone, before anyone has to have noticed.
    """
    verdict = feedback_safety.scan_payload(
        {"canvas_id": "990001", "evidence_span": "Sparky texts him"}, vault)
    assert not verdict["green"]
    assert any("canvas_id" in message for message in verdict["hard"])
