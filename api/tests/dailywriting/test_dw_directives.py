"""Directives and uptake. Acceptance tests T-7, T-8, T-9."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.dailywriting.config import thresholds
from api.dailywriting.core import directives
from api.dailywriting.core.models import (
    BannedPhraseDetector,
    Directive,
    JudgmentDetector,
    RequiredMoveDetector,
    Segment,
    Submission,
)

WHEN = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)


def _submission(text: str, submission_id: str = "sub-x",
                scaffold_text: str = "") -> Submission:
    segments = []
    cursor = 0
    if scaffold_text:
        segments.append(Segment(span_start=0, span_end=len(scaffold_text),
                                text=scaffold_text, origin="scaffold",
                                confidence=1.0, method="exact_match"))
        cursor = len(scaffold_text)
    segments.append(Segment(span_start=cursor, span_end=cursor + len(text),
                            text=text, origin="student", confidence=1.0,
                            method="residual"))
    return Submission(submission_id=submission_id, rep_id="rep-x",
                      pseudonym_id="Sparky McGee", submitted_at=WHEN,
                      raw_text=scaffold_text + text, segments=segments,
                      student_word_count=len(text.split()))


def _directive(detector, text="Stop opening with \"this shows that.\""):
    return Directive(directive_id="dir-x", pseudonym_id="Sparky McGee",
                     issued_at=WHEN, text=text,
                     target_pattern="commentary_formulaic", detector=detector)


# --- T-7 --------------------------------------------------------------------


def test_t7_praise_fires_once_at_the_third_consecutive_met(run_sequence):
    """T-7: exactly one praise, at the third met, citing count 3."""
    directive, acknowledgments, compiled = run_sequence(9)

    assert compiled.deterministic
    assert isinstance(compiled.detector, BannedPhraseDetector)

    praise = [a for a in acknowledgments if a.kind == "praise"]
    assert len(praise) == 1, [a.kind for a in acknowledgments]
    assert praise[0].streak == thresholds.PRAISE_THRESHOLD == 3
    assert "3 pieces" in praise[0].text
    assert directive.current_streak == 3
    assert directive.best_streak == 3

    results = [record.result for record in directive.evaluations]
    assert results == ["unmet", "met", "met", "met"]


def test_t7_praise_quotes_the_directive_as_the_student_was_given_it(
        run_sequence):
    directive, acknowledgments, _compiled = run_sequence(9)
    praise = next(a for a in acknowledgments if a.kind == "praise")
    assert directive.text in praise.text


def test_t7_praise_never_claims_a_count_the_detector_did_not_confirm(
        run_sequence):
    directive, acknowledgments, _compiled = run_sequence(9)
    praise = next(a for a in acknowledgments if a.kind == "praise")
    confirmed = sum(1 for record in directive.evaluations
                    if record.result == "met")
    assert praise.streak <= confirmed


# --- T-8 --------------------------------------------------------------------


def test_t8_lapse_fires_and_resets_the_streak_keeping_the_best(run_sequence):
    """T-8: lapse message fires, current_streak == 0, best_streak == 3."""
    directive, acknowledgments, _compiled = run_sequence(10)

    lapses = [a for a in acknowledgments if a.kind == "lapse"]
    assert len(lapses) == 1, "a second lapse message would be nagging"
    assert lapses[0].streak == 3
    assert "3 pieces" in lapses[0].text

    assert directive.current_streak == 0
    assert directive.best_streak == 3
    assert directive.status == "lapsed"

    results = [record.result for record in directive.evaluations]
    assert results == ["met", "met", "met", "unmet", "unmet"]


def test_t8_lapse_text_differs_from_praise_text(run_sequence):
    _directive_9, acks_9, _c9 = run_sequence(9)
    _directive_10, acks_10, _c10 = run_sequence(10)
    praise = next(a for a in acks_9 if a.kind == "praise")
    lapse = next(a for a in acks_10 if a.kind == "lapse")
    assert praise.text != lapse.text
    assert "Keep going" in praise.text
    assert "Keep going" not in lapse.text


# --- T-9 --------------------------------------------------------------------


def test_t9_a_missing_submission_is_na_and_does_not_break_the_streak(
        run_sequence):
    """T-9: the gap is logged na and the streak survives it."""
    directive, acknowledgments, _compiled = run_sequence(11)

    results = [record.result for record in directive.evaluations]
    assert results == ["met", "met", "na", "met"]

    gap = directive.evaluations[2]
    assert gap.result == "na"
    assert gap.submission_id.startswith("missing:")
    assert "streak unchanged" in gap.note

    assert directive.current_streak == 3
    praise = [a for a in acknowledgments if a.kind == "praise"]
    assert len(praise) == 1
    assert praise[0].streak == 3


def test_a_directive_that_does_not_apply_at_this_tier_is_na():
    directive = _directive(BannedPhraseDetector(phrases=["this shows that"]))
    updated, acknowledgments = directives.evaluate_all(
        [directive], _submission("This shows that it is fine."), tier=2,
        directive_tiers={"dir-x": 4}, now=WHEN, rep_id="rep-x")
    assert updated[0].evaluations[-1].result == "na"
    assert updated[0].current_streak == 0
    assert not acknowledgments


# --- Detectors --------------------------------------------------------------


def test_a_banned_phrase_inside_a_provided_stem_is_not_the_students_doing():
    """The detector reads student prose only."""
    directive = _directive(BannedPhraseDetector(phrases=["this shows that"]))
    submission = _submission("the school ignored families.",
                             scaffold_text="This shows that ")
    updated, _acks = directives.evaluate_all([directive], submission, now=WHEN)
    assert updated[0].evaluations[-1].result == "met"


def test_a_required_move_detector_cites_the_span_it_matched():
    directive = _directive(
        RequiredMoveDetector(pattern=r"\bline\s+\d+", description="cites a line"),
        text="Cite the line number when you quote.")
    result, span, _note = directives.run_detector(
        directive.detector, _submission("The narrator says this in line 14."))
    assert result == "met"
    assert "line 14" in span


def test_a_judgment_detector_returns_na_rather_than_inventing_a_verdict():
    """An invented met becomes praise the system cannot prove."""
    directive = _directive(
        JudgmentDetector(question="Does the commentary commit to a reading?"))
    result, span, note = directives.run_detector(
        directive.detector, _submission("Maybe it kind of shows something."))
    assert result == "na"
    assert span is None
    assert "not evaluated" in note


def test_an_unsafe_teacher_regex_is_refused_rather_than_run():
    with pytest.raises(directives.DetectorError):
        directives.compile_pattern(r"(a+)+b")
    with pytest.raises(directives.DetectorError):
        directives.compile_pattern("(unclosed")


def test_a_broken_detector_reports_na_instead_of_failing_the_rep():
    directive = _directive(RequiredMoveDetector(pattern="(unclosed"))
    result, _span, note = directives.run_detector(
        directive.detector, _submission("Anything at all."))
    assert result == "na"
    assert "could not run" in note


def test_prose_that_cannot_be_compiled_says_so_instead_of_pretending():
    compiled = directives.compile_directive(
        "Write with more conviction and stop being so wishy-washy.")
    assert not compiled.deterministic
    assert isinstance(compiled.detector, JudgmentDetector)
    assert "rewriting it" in compiled.explanation.lower()


def test_a_required_move_compiles_from_a_line_number_instruction():
    compiled = directives.compile_directive(
        "Always give me the line number when you quote the passage.")
    assert compiled.deterministic
    assert isinstance(compiled.detector, RequiredMoveDetector)


def test_retirement_stops_the_directive_from_nagging_forever():
    directive = _directive(BannedPhraseDetector(phrases=["this shows that"]))
    clean = _submission("The town owes them their pensions outright.")
    for index in range(thresholds.RETIRE_THRESHOLD):
        directive, _record, _ack = directives.evaluate(
            directive, clean, now=WHEN, rep_id=f"rep-{index}")
    assert directive.status == "retired"
    assert directive.current_streak == thresholds.RETIRE_THRESHOLD

    after, acknowledgments = directives.evaluate_all([directive], clean, now=WHEN)
    assert after[0].status == "retired"
    assert not acknowledgments
    assert len(after[0].evaluations) == thresholds.RETIRE_THRESHOLD


def test_a_lapsed_directive_met_again_fires_a_return_not_a_first_time_praise():
    directive = _directive(BannedPhraseDetector(phrases=["this shows that"]))
    clean = _submission("The town owes them their pensions outright.")
    dirty = _submission("This shows that the town owes them something.")

    for index in range(3):
        directive, _record, _ack = directives.evaluate(
            directive, clean, now=WHEN, rep_id=f"rep-{index}")
    directive, _record, lapse = directives.evaluate(directive, dirty, now=WHEN,
                                                    rep_id="rep-lapse")
    assert lapse.kind == "lapse"
    assert directive.status == "lapsed"

    directive, _record, comeback = directives.evaluate(directive, clean,
                                                       now=WHEN, rep_id="rep-back")
    assert comeback.kind == "return"
    assert comeback.text != lapse.text
    assert directive.status == "open"


def test_only_one_acknowledgment_reaches_a_feedback_message():
    praise = directives.Acknowledgment("praise", "d1", "praise text", 3)
    lapse = directives.Acknowledgment("lapse", "d2", "lapse text", 4)
    comeback = directives.Acknowledgment("return", "d3", "return text", 1)
    chosen = directives.choose_acknowledgment([lapse, comeback, praise])
    assert chosen is praise
    assert directives.choose_acknowledgment([]) is None


def test_uptake_never_changes_a_score(ingest_fixture):
    """INV-1 again, from the other side: acknowledgments do not touch totals."""
    from dataclasses import replace

    result = ingest_fixture(1)
    baseline = result.score.total
    directive = _directive(BannedPhraseDetector(phrases=["never appears here"]))
    updated, acknowledgments = directives.evaluate_all(
        [replace(directive, pseudonym_id=result.submission.pseudonym_id)],
        result.submission, now=WHEN)
    assert updated[0].evaluations[-1].result == "met"
    assert result.score.total == baseline
