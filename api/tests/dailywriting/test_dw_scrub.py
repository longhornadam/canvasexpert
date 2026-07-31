"""INV-7: roster names never leave the tenant. Acceptance test T-6.

What is scrubbed is what the vault knows: real names, the nicknames the teacher
entered, and Canvas/SIS ids. Nothing is inferred from capitalisation. The tests
below hold both halves of that -- every roster alias goes, and ordinary
capitalised writing is returned untouched -- because the second half used to be
false and quietly destroyed the records this product exists to keep.
"""
from __future__ import annotations

import pytest

from api.dailywriting.core import scrub
from api.dailywriting.fixtures import loader


def test_t6_no_roster_name_or_alias_survives_anywhere(ingest_fixture):
    """T-6: absent from stored text and from every stored span."""
    raw = loader.single(8)
    result = ingest_fixture(8)

    stored_surfaces = [result.raw_text]
    stored_surfaces += [segment.text for segment in result.segments]

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
        text=result.raw_text,
        findings=result.scrub_findings,
    ), pseudonyms=pseudonyms)
    for name in raw["names_that_must_not_survive"]:
        assert name.lower() not in outbound.text.lower()
    assert "Sparky McGee" not in outbound.text


def test_a_roster_name_becomes_its_pseudonym(ingest_fixture):
    result = ingest_fixture(8)
    assert "Sparky" in result.raw_text
    kinds = {finding.kind for finding in result.scrub_findings}
    assert kinds <= {"roster_name", "roster_id"}


def test_a_non_roster_name_is_left_alone_deliberately(ingest_fixture):
    """The trade this product makes, asserted so it cannot drift back.

    Fixture 8 is "My brother Diego says Marcus texts him...". Marcus is on the
    roster and goes. Diego is a sibling on no roster, and stays: the accepted
    residual risk is a non-roster first name reaching the teacher's own AI
    tenant inside a quoted sentence. The alternative -- guessing at capitalised
    tokens -- redacted 30 of 37 capitalised tokens in ordinary seventh-grade
    writing, every one of them wrong.
    """
    result = ingest_fixture(8)
    raw = loader.single(8)
    for name in raw["names_that_survive_by_decision"]:
        assert name in result.raw_text


def test_findings_never_record_the_value_they_removed(ingest_fixture):
    """A finding is stored beside the text, so it must not undo the redaction."""
    raw = loader.single(8)
    result = ingest_fixture(8)
    for finding in result.scrub_findings:
        for name in raw["names_that_must_not_survive"]:
            assert name.lower() not in finding.detail.lower()
            assert name.lower() not in finding.replacement.lower()


# --- the regression this file exists to prevent ------------------------------

ACADEMIC_WRITING = [
    # (label, text) -- no roster name in any of them, so a single character of
    # difference after scrubbing is a bug.
    ("argument",
     "Dogs make better pets than cats for a busy family. Golden Retrievers are "
     "loyal and can be trained in a few weeks."),
    ("history",
     "The Battle of Gettysburg was the turning point of the Civil War. General "
     "Lee marched north into Pennsylvania. Union soldiers held the high ground "
     "at Cemetery Ridge."),
    ("science",
     "Photosynthesis happens in the chloroplast. Sunlight, water, and carbon "
     "dioxide go in. Plants near the Equator get more light all year, so they "
     "grow faster than plants in Canada."),
    ("literary analysis",
     "Ponyboy changes the most in the novel. Johnny dies, and after that "
     "Ponyboy stops seeing the Socs as only enemies."),
    ("narrative",
     "Last summer my family drove to Colorado. Mountains looked purple in the "
     "morning. Wednesday was the day we hiked the highest trail."),
]


@pytest.mark.parametrize("label,text", ACADEMIC_WRITING,
                         ids=[label for label, _ in ACADEMIC_WRITING])
def test_ordinary_capitalised_writing_is_returned_untouched(label, text, roster_map):
    """Every one of these lost content to the old heuristic pass.

    Measured before it was removed: "The [name] of [name] was the turning point
    of the [name] [name]." Stored, not displayed -- so the record, the quoted
    evidence behind every observation, and the input to every checklist check
    all inherited it. Run with a real roster map, because production always has
    one and it must not change this answer.
    """
    result = scrub.scrub_writing(text, roster_map=roster_map)
    assert result.text == text
    assert result.findings == []


def test_no_redaction_placeholder_reaches_stored_text(ingest_fixture):
    """A cheap guard on the whole decision: nothing in the ingest path may put
    a `[name]` marker into a stored record. The only legitimate use of that
    placeholder is `model_ready_text`, on the way out of the tenant."""
    for number in loader.single_numbers():
        result = ingest_fixture(number)
        assert scrub.NAME_PLACEHOLDER not in result.raw_text
        for segment in result.segments:
            assert scrub.NAME_PLACEHOLDER not in segment.text


# --- the vault is the mechanism ---------------------------------------------

def test_a_nickname_the_teacher_entered_is_covered(roster_map):
    """The answer to "what about the name you did not catch": enter it.

    "Marc" is a nickname on Marcus Bell's vault entry, and it resolves to the
    same pseudonym the full name does. This is the supported way to extend
    coverage, and it is why no heuristic is needed to guess at one.
    """
    result = scrub.scrub_writing("Marc sat next to me during the test.",
                                 roster_map=roster_map)
    assert "Marc " not in result.text
    assert "Sparky McGee" in result.text


def test_a_roster_first_name_alone_is_still_caught(roster_map):
    result = scrub.scrub_writing("Marcus said the same thing in class.",
                                 roster_map=roster_map)
    assert "Marcus" not in result.text
    assert "Sparky" in result.text


def test_a_full_roster_name_maps_to_the_full_pseudonym(roster_map):
    result = scrub.scrub_writing("Priya Raman disagreed with me.",
                                 roster_map=roster_map)
    assert result.text.strip().startswith("Waffles Pinkerton")


def test_id_placeholder_is_used_for_a_real_id_in_free_text(roster_map):
    result = scrub.scrub_writing("My number is F990001 if you need it.",
                                 roster_map=roster_map)
    assert "990001" not in result.text
    assert any(f.kind == "roster_id" for f in result.findings)


def test_no_roster_map_scrubs_nothing_and_says_so():
    """Passing neither vault nor roster_map removes nothing. That is right for a
    fixture and wrong in production, which is what `assert_clean_for_storage`
    exists to catch -- it raises rather than letting the text be stored."""
    text = "Marcus said the same thing in class."
    assert scrub.scrub_writing(text).text == text


def test_the_student_is_credited_for_every_word_they_wrote(ingest_fixture):
    """18, not the 17 this fixture used to report.

    A roster name replaced by a pseudonym still counts, because a pseudonym is
    a word. `[name]` did not: the old heuristic pass cost this student a word
    off their own count for writing "Diego". So the removed pass was not only
    mangling the text, it was quietly understating how much each kid wrote --
    which is one of the few numbers the record uses to describe a writer.
    """
    result = ingest_fixture(8)
    assert result.student_word_count == 18
