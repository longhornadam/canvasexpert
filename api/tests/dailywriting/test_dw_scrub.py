"""INV-7: names never leave the tenant. Acceptance test T-6.

The hard case is the one the existing roster scrubber cannot see: a student
writes about his brother, who is on no roster anywhere.
"""
from __future__ import annotations

import pytest

from api.dailywriting.core import scrub
from api.dailywriting.core.observations import assert_span_storable
from api.dailywriting.fixtures import loader


def test_t6_neither_the_classmate_nor_the_sibling_survives(ingest_fixture):
    """T-6: both names absent from stored text and from every stored span."""
    raw = loader.single(8)
    result = ingest_fixture(8)

    stored_surfaces = [result.submission.raw_text]
    stored_surfaces += [segment.text for segment in result.submission.segments]
    stored_surfaces += [observation.evidence_span
                        for observation in result.observations]
    stored_surfaces += [item.evidence_span.text
                        for item in result.score.per_item.values()
                        if item.evidence_span]
    stored_surfaces += [observation.claim_text
                        for observation in result.observations]

    for name in raw["names_that_must_not_survive"]:
        for surface in stored_surfaces:
            assert name.lower() not in surface.lower(), (
                f"{name!r} survived into stored text: {surface!r}")


def test_t6_outbound_representation_requires_scrubbed_text(ingest_fixture):
    """No raw string can be handed to a future model client by accident."""
    raw = loader.single(8)
    pseudonyms = {entry["pseudonym"] for entry in loader.vault_entries()}
    with pytest.raises(scrub.UnsanitizedOutboundError):
        scrub.model_ready_text(raw["text"], pseudonyms=pseudonyms)

    result = ingest_fixture(8)
    outbound = scrub.model_ready_text(scrub.ScrubResult(
        text=result.submission.raw_text,
        findings=result.submission.scrub_findings,
    ), pseudonyms=pseudonyms)
    for name in raw["names_that_must_not_survive"]:
        assert name.lower() not in outbound.text.lower()
    assert "Sparky McGee" not in outbound.text


def test_t6_roster_name_becomes_its_pseudonym_and_the_sibling_is_redacted(
        ingest_fixture):
    result = ingest_fixture(8)
    text = result.submission.raw_text
    # The classmate resolves to the stable pseudonym the vault already assigned.
    assert "Sparky" in text
    # The sibling is on no roster, so there is no pseudonym to resolve to.
    assert scrub.NAME_PLACEHOLDER in text
    kinds = {finding.kind for finding in result.submission.scrub_findings}
    assert "general_name" in kinds


def test_findings_never_record_the_value_they_removed(ingest_fixture):
    """A finding is stored beside the text, so it must not undo the redaction."""
    raw = loader.single(8)
    result = ingest_fixture(8)
    for finding in result.submission.scrub_findings:
        for name in raw["names_that_must_not_survive"]:
            assert name.lower() not in finding.detail.lower()
            assert name.lower() not in finding.replacement.lower()


def test_general_pass_leaves_ordinary_capitalised_words_alone():
    text = ("Students should not lose recess. The article says that Monday "
            "practice was cancelled. However, that is not the same problem.")
    result = scrub.scrub_writing(text, protected=set())
    assert result.text == text, result.text
    assert result.general_name_hits == 0


def test_general_pass_catches_a_bare_first_name_with_no_cue():
    result = scrub.scrub_writing("Yesterday Tobias forgot his folder again.",
                                 protected=set())
    assert "Tobias" not in result.text
    assert result.general_name_hits == 1


def test_a_kinship_cue_beats_the_ordinary_word_lexicon():
    """"My friend Grace" is a person even though "grace" is a common word."""
    plain = scrub.scrub_writing("Grace is what the author is describing here.",
                                protected=set())
    assert "Grace" in plain.text

    cued = scrub.scrub_writing("My friend Grace said the same thing.",
                               protected=set())
    assert "Grace" not in cued.text


def test_an_ambiguous_name_word_is_redacted_mid_sentence():
    """Sentence-initial capitals are grammar; mid-sentence capitals are evidence."""
    opener = scrub.scrub_writing("Will is the word the author repeats.",
                                 protected=set())
    assert "Will" in opener.text

    middle = scrub.scrub_writing("I told Will about the assignment.",
                                 protected=set())
    assert "Will" not in middle.text


def test_a_title_marks_the_following_word_as_a_surname():
    result = scrub.scrub_writing("Coach Whitlock made us run it again.",
                                 protected=set())
    assert "Whitlock" not in result.text


def test_the_assignment_corpus_shields_names_from_the_passage():
    """A name in the source passage is course content, not a disclosure."""
    context = loader.rep("rep_t3_forest")
    text = ("The mill owner in Blackwood Hollow keeps cutting because money "
            "matters more to him than the pines do.")
    without = scrub.scrub_writing(text, protected=set())
    assert "Blackwood" not in without.text

    with_corpus = scrub.scrub_writing(
        text, protected=set(),
        assignment_corpus=[context.prompt_text,
                           "The mill in Blackwood Hollow ran for eighty years."])
    assert "Blackwood Hollow" in with_corpus.text


def test_protected_literary_names_survive_the_general_pass():
    """Quoting Ponyboy is the assignment, not a privacy problem."""
    text = "Ponyboy learns that the Socs are afraid of being ordinary."
    redacted = scrub.scrub_writing(text, protected=set())
    assert "Ponyboy" not in redacted.text

    kept = scrub.scrub_writing(text, protected={"ponyboy", "socs"})
    assert "Ponyboy" in kept.text


def test_a_roster_name_is_scrubbed_even_when_it_is_also_protected(roster_map):
    """Privacy wins over a literary match, matching feedback_scrub's ordering."""
    result = scrub.scrub_writing(
        "Marcus said the same thing in class.",
        roster_map=roster_map, protected={"marcus"})
    assert "Marcus" not in result.text
    assert "Sparky" in result.text


def test_the_pseudonym_the_roster_pass_introduced_is_not_then_redacted(
        roster_map):
    result = scrub.scrub_writing("Priya Raman disagreed with me.",
                                 roster_map=roster_map, protected=set())
    assert result.text.strip().startswith("Waffles Pinkerton")
    assert scrub.NAME_PLACEHOLDER not in result.text


def test_scrubbing_preserves_the_student_word_count(ingest_fixture):
    """Redaction replaces a token with a token, so nobody loses credit for it."""
    result = ingest_fixture(8)
    assert result.submission.student_word_count == 17


def test_an_observation_without_a_span_is_refused():
    with pytest.raises(Exception):
        assert_span_storable("   ")


def test_id_placeholder_is_used_for_a_real_id_in_free_text(roster_map):
    result = scrub.scrub_writing("My number is F990001 if you need it.",
                                 roster_map=roster_map, protected=set())
    assert "990001" not in result.text
    assert any(f.kind == "roster_id" for f in result.findings)
