"""Segmentation as alignment. Acceptance tests T-3, T-4, T-5.

The mid-prompt-fragment and dead-Origin-value tests below belong to the ECR
substrate brief (docs/handoffs/CanvasExpert-WritingRecord-ECRSubstrate-BRIEF.md
Sec 5, AC4 and AC6)."""
from __future__ import annotations

import typing

import pytest

from api.dailywriting.config import thresholds
from api.dailywriting.core import segmentation
from api.dailywriting.core.models import Origin
from api.dailywriting.fixtures import loader


def _segment(fixture_number: int):
    raw = loader.single(fixture_number)
    return segmentation.segment_submission(raw["text"],
                                           loader.rep(raw["rep_id"]))


def _origins(result) -> list[str]:
    return [segment.origin for segment in result.segments]


def test_t3_copied_prompt_plus_eight_words_counts_eight():
    """T-3: a student who copies the prompt and adds eight words wrote eight."""
    result = _segment(3)
    assert result.student_word_count == 8
    assert "assignment" in _origins(result)
    student = [s for s in result.segments if s.origin == "student"]
    assert len(student) == 1
    assert "lockers" in student[0].text


def test_t3_prompt_is_matched_exactly_not_guessed():
    result = _segment(3)
    provided = [s for s in result.segments if s.origin == "assignment"]
    assert provided
    assert all(s.method == "exact_match" and s.confidence == 1.0
               for s in provided)


def test_t4_completed_stem_splits_into_scaffold_prefix_and_student_interior():
    """T-4a: stem literal is scaffold, the blank's fill is student."""
    result = _segment(4)
    scaffold = [s for s in result.segments if s.origin == "scaffold"]
    student = [s for s in result.segments if s.origin == "student"]
    assert scaffold and student
    assert scaffold[0].span_start < student[0].span_start
    assert "This shows that" in scaffold[0].text
    assert "school cared" in student[0].text
    assert result.student_word_count > 0
    assert not any(f.code == "empty_stem_blank" for f in result.flags)


def test_t4_empty_stem_blank_is_zero_student_words_and_flagged():
    """T-4b: the stem submitted with nothing in it is detectable."""
    result = _segment(5)
    assert result.student_word_count == 0
    codes = {flag.code for flag in result.flags}
    assert "empty_stem_blank" in codes
    assert "no_student_text" in codes
    assert "student" not in _origins(result)


def test_t5_quoted_source_is_its_own_origin_and_not_counted():
    """T-5: the quotation is quoted_source, not scaffold, and not student words."""
    result = _segment(6)
    quoted = [s for s in result.segments if s.origin == "quoted_source"]
    assert quoted, "the quotation from the passage was not recognised"
    assert "scaffold" not in _origins(result)

    quoted_text = " ".join(s.text for s in quoted)
    assert "saws running" in quoted_text

    quoted_words = sum(len(segmentation.tokenize(s.text)) for s in quoted)
    whole = len(segmentation.tokenize(loader.single(6)["text"]))
    assert result.student_word_count < whole
    assert quoted_words > 0
    # The quoted words are excluded from the student count but still present
    # for the evidence criteria to read.
    assert result.text_for("quoted_source").strip()
    assert result.text_for("student").strip()


def test_dropped_quote_is_still_recognised_as_quoted_source():
    result = _segment(7)
    assert any(s.origin == "quoted_source" for s in result.segments)


def test_segments_tile_the_whole_text():
    """No character falls outside a segment, so punctuation is never lost."""
    for number in (1, 3, 4, 6, 7, 12):
        raw = loader.single(number)
        result = _segment(number)
        rebuilt = "".join(s.text for s in result.segments)
        assert rebuilt == segmentation.normalize(raw["text"]), (
            f"fixture {number} segments do not tile its text")


def test_normalization_preserves_offsets():
    text = 'He said “no” — and meant it…'
    normalized = segmentation.normalize(text)
    assert len(normalized) == len(text)
    assert '"' in normalized and "“" not in normalized


def test_cross_submission_repetition_flags_without_changing_origin():
    """Repeated residual text is surfaced to the teacher, never acted on."""
    shared = "the author uses this to show the reader what really matters"
    flags = segmentation.flag_cross_submission_repetition({
        "sub-a": f"I think {shared} here.",
        "sub-b": f"Honestly {shared} too.",
        "sub-c": f"In my opinion {shared} again.",
        "sub-d": "Nothing in common with the others at all.",
    })
    assert set(flags) == {"sub-a", "sub-b", "sub-c"}
    assert all(f.code == "cross_submission_repeat"
               for notes in flags.values() for f in notes)
    assert "sub-d" not in flags


# Vocabulary for building a long, otherwise-original response with none of
# rep_t4_lockdown's own words in it (its prompt, its "This shows that"
# scaffold, and its source passage all stay clear of this list), so nothing
# but the deliberately embedded fragment below can be claimed by any stage.
_FILLER_VOCABULARY = (
    "mill town grew slowly around the river bend and every generation "
    "added its own memory to the same stretch of water without writing any "
    "of it down before deciding whether to stay or leave for a city that "
    "promised something steadier than lumber prices could ever hold across "
    "three different decades of neighbors who kept working the same long "
    "shift"
).split()


def _filler(word_count: int, start: int = 0) -> str:
    return " ".join(_FILLER_VOCABULARY[(start + i) % len(_FILLER_VOCABULARY)]
                    for i in range(word_count)) + "."


def test_mid_prompt_fragment_buried_in_a_long_response_is_assignment_not_student():
    """AC4: a verbatim run of >= EMBEDDED_QUOTE_MIN_TOKENS tokens lifted from
    the *middle* of prompt_text, buried three paragraphs into a long (400+
    word) response, is attributed `assignment` and excluded from
    student_word_count.

    Stage 1 (exact) and stage 2 (fuzzy) both only ever look for a window
    sized to the *whole* prompt's own token length, so neither can find this
    fragment -- this is exactly the shape stage 5 (mid-prompt fragment,
    modelled on `_claim_embedded_quote`) exists for. Without stage 5 this
    fragment would fall through to stage 6 and be counted as the student's
    own words, so this test goes red without it: `assignment_segments` would
    be empty and `student_word_count` would equal `total_tokens`. The
    response is well above `MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS` on
    purpose -- the length gate exists precisely so a short rep's opening
    thesis is never a candidate for this stage (see
    test_short_rep_prompt_echo_is_left_as_the_students below), and a test
    that stayed near the gate's edge would not distinguish "the gate is open"
    from "the gate doesn't matter here"."""
    context = loader.rep("rep_t4_lockdown")
    fragment = "the school communicated well enough with families"
    assert fragment in context.prompt_text.lower()
    assert len(segmentation.tokenize(fragment)) >= 5

    paragraph_three = (
        "Looking back, some families felt " + fragment + " because three "
        "separate updates went out within the first hour, which is why most "
        "parents said they were not panicking by the time the bell rang.")
    paragraphs = [
        _filler(100, start=0),
        _filler(100, start=17),
        paragraph_three,
        _filler(100, start=33),
        _filler(100, start=51),
    ]
    text = "\n\n".join(paragraphs)
    total_tokens = len(segmentation.tokenize(text))
    assert total_tokens >= 400, "this response must be a genuinely long piece"
    assert total_tokens >= thresholds.MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS

    result = segmentation.segment_submission(text, context)

    assignment = [s for s in result.segments if s.origin == "assignment"]
    assert assignment, "the mid-prompt fragment was not recognised"
    assignment_text = " ".join(s.text for s in assignment).lower()
    for token in segmentation.tokenize(fragment):
        assert token.norm in assignment_text

    fragment_tokens = len(segmentation.tokenize(fragment))
    assert result.student_word_count == total_tokens - fragment_tokens

    rebuilt = "".join(s.text for s in result.segments)
    assert rebuilt == segmentation.normalize(text)


def test_short_rep_prompt_echo_is_left_as_the_students():
    """Senior review regression: the mid-prompt-fragment stage's first cut
    reclassified fixture 2's whole 10-word thesis ('be allowed to keep their
    phones with them during class') as `assignment`, collapsing
    student_word_count from 12 to 2 -- cannibalising `observations.py`'s
    already-designed `restates_prompt` pattern one layer too early, on a
    12-word response nowhere near the length extended writing runs at. Below
    `MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS`, this stage must not run at
    all, so that mechanism still gets to see the words."""
    result = _segment(2)
    assert len(segmentation.tokenize(loader.single(2)["text"])) < (
        thresholds.MID_PROMPT_FRAGMENT_MIN_RESPONSE_TOKENS)
    assert result.student_word_count == 12
    assert _origins(result) == ["student"]


def test_short_rep_correct_answer_echoing_the_prompts_topic_is_not_penalised():
    """Senior review regression: fixture 6 is a strong, correct tier-3 answer
    that opens with the prompt's own topic words ('The mill owner keeps
    cutting'). The stage's first cut clipped 5 of those words to
    `assignment`, dropping student_word_count from 38 to 33. A model answer
    must not lose words for answering the question."""
    result = _segment(6)
    assert result.student_word_count == 38
    assert "The mill owner keeps cutting" in result.text_for("student")


def test_full_prompt_copy_precedent_is_unaffected_by_the_new_stage():
    """AC5, restated at the unit level the new stage touches directly: fixture
    3's whole-prompt-copy case must still be claimed by stage 1 (exact match,
    confidence 1.0), not re-claimed or altered by the new mid-prompt-fragment
    stage that runs after it."""
    result = _segment(3)
    provided = [s for s in result.segments if s.origin == "assignment"]
    assert provided
    assert all(s.method == "exact_match" and s.confidence == 1.0
               for s in provided)
    assert result.student_word_count == 8


# Every `singles.json` fixture's student_word_count and origin set, pinned to
# their values from before the mid-prompt-fragment stage existed (git HEAD
# b2ee610, confirmed by running segment_submission with the stage's call
# site removed). Two of these silently changed -- fixture 2 and fixture 6,
# both discussed above -- when the stage's first cut shipped with a green
# suite, because nothing asserted these values anywhere. This test is the
# fix for that gap, not just for this one regression: it is what would catch
# the *next* segmentation change that shifts a fixture nobody happened to
# write a narrower assertion for.
_EXPECTED_FIXTURE_RESULTS = {
    1: (24, frozenset({"student"})),
    2: (12, frozenset({"student"})),
    3: (8, frozenset({"assignment", "student"})),
    4: (13, frozenset({"scaffold", "student"})),
    5: (0, frozenset({"scaffold"})),
    6: (38, frozenset({"quoted_source", "student"})),
    7: (17, frozenset({"quoted_source", "student"})),
    8: (18, frozenset({"student"})),
    12: (60, frozenset({"quoted_source", "scaffold", "student"})),
}


def test_pinned_fixture_set_covers_the_whole_fixture_corpus():
    """A completeness check on the pin above: if a fixture is ever added to
    singles.json without a matching entry here, this fails loudly instead of
    the new fixture silently going unpinned."""
    assert sorted(_EXPECTED_FIXTURE_RESULTS) == loader.single_numbers()


@pytest.mark.parametrize("fixture_number", sorted(_EXPECTED_FIXTURE_RESULTS))
def test_every_fixture_student_word_count_and_origins_are_pinned(fixture_number):
    expected_count, expected_origins = _EXPECTED_FIXTURE_RESULTS[fixture_number]
    result = _segment(fixture_number)
    assert result.student_word_count == expected_count
    assert set(_origins(result)) == expected_origins


def test_no_produced_segment_has_the_dead_unknown_origin():
    """AC6: `Origin` no longer advertises a value `segment_submission` cannot
    produce. Runs the real segmenter over every fixture the tiling test
    already covers (plain prompt copy, stem, quoted source, dropped quote),
    which between them exercise every stage -- if stage 6 ever left an owner
    slot unset, one of these would show it."""
    assert "unknown" not in typing.get_args(Origin)
    for number in (1, 3, 4, 6, 7, 12):
        result = _segment(number)
        origins = {s.origin for s in result.segments}
        assert origins <= set(typing.get_args(Origin))
        assert "unknown" not in origins


def test_low_confidence_provided_text_is_flagged_for_human_eyes():
    """A fuzzy provided-text match reports itself rather than being trusted."""
    context = loader.rep("rep_t1_phones")
    reworded = ("Should pupils be permitted to retain their phones with them "
                "throughout class? State a position in a single sentence. "
                "Phones belong in lockers.")
    result = segmentation.segment_submission(reworded, context)
    fuzzy = [s for s in result.segments if s.method == "fuzzy_match"]
    if fuzzy:
        assert result.low_confidence or all(s.confidence >= 0.9 for s in fuzzy)
