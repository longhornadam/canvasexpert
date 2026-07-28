"""Segmentation as alignment. Acceptance tests T-3, T-4, T-5."""
from __future__ import annotations

from api.dailywriting.core import segmentation
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
