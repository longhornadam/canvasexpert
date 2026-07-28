"""Acceptance coverage for profiles, feedback, and the weekly digest.

These tests keep the history-facing features on their side of the scorer's
boundary while proving the student-visible and teacher-reviewable outputs that
the substrate is responsible for now.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from api.dailywriting.core import digest, feedback, profile
from api.dailywriting.core.directives import Acknowledgment
from api.dailywriting.core.models import (
    BannedPhraseDetector,
    Directive,
    Observation,
    PatternSummary,
    ProfileFieldError,
    SegmentationFlag,
    SubmissionRef,
    build_profile,
)
from api.dailywriting.fixtures import loader


WHEN = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def _profile(*, pseudonym_id: str = "Waffles Pinkerton", ready: bool = False):
    directive = Directive(
        directive_id="dir-profile", pseudonym_id=pseudonym_id, issued_at=WHEN,
        text="State your claim directly.", target_pattern="thesis_not_arguable",
        detector=BannedPhraseDetector(phrases=["maybe"]),
    )
    return build_profile(
        pseudonym_id=pseudonym_id,
        generated_at=WHEN,
        window_start=date(2026, 10, 17),
        window_end=date(2026, 11, 14),
        tier=3,
        per_criterion_rate={"arguable": 0.75},
        active_patterns=[PatternSummary(
            pattern_tag="thesis_too_general", count=2, rate=0.5,
            evidence=["The point is about stuff."],
            first_seen=date(2026, 11, 8), last_seen=date(2026, 11, 13),
        )],
        open_directives=[directive],
        best_piece=SubmissionRef("sub-best", "rep-best", date(2026, 11, 13),
                                 4, 4),
        next_focus="State a position someone could disagree with.",
        ready_for_tier_advance=ready,
    )


def test_t10_profile_rejects_non_writing_field_and_renders_every_field():
    fields = dict(_profile().__dict__)
    fields["behavior_notes"] = "tries hard in class"
    with pytest.raises(ProfileFieldError, match="writing-only"):
        build_profile(**fields)

    record = _profile()
    view = profile.student_view(record)
    rendered = "\n".join(
        value if isinstance(value, str) else "\n".join(value)
        for value in view.values()
    )
    assert record.pseudonym_id == view["student"]
    assert record.generated_at.isoformat() == view["updated"]
    assert record.window_start.isoformat() in view["window"]
    assert record.window_end.isoformat() in view["window"]
    assert f"Tier {record.tier}" == view["tier"]
    assert "75%" in rendered
    assert "thesis too general" in rendered
    assert record.open_directives[0].text in view["what_i_was_asked"]
    assert record.best_piece.rep_id in view["best_piece"]
    assert record.next_focus == view["next_focus"]
    assert "Keep working" in view["ready_for_next_tier"]


class _WindowOnlySource:
    """A profile source whose old profile must never be consulted."""

    def __init__(self, submission, score, observation):
        self.submission = submission
        self.score = score
        self.observation = observation
        self.window = None
        self.read_profile_called = False

    def submissions_in_window(self, pseudonym_id, start, end):
        self.window = (pseudonym_id, start, end)
        return [self.submission]

    def scores_for(self, submission_ids):
        assert submission_ids == [self.submission.submission_id]
        return {self.submission.submission_id: self.score}

    def observations_in_window(self, pseudonym_id, start, end):
        assert (start, end) == self.window[1:]
        return [self.observation]

    def directives_for(self, pseudonym_id):
        return []

    def current_tier(self, pseudonym_id):
        return 1

    def read_profile(self, pseudonym_id):
        self.read_profile_called = True
        raise AssertionError("regeneration must not read a prior profile")


def test_t11_t12_regeneration_uses_only_window_records_and_no_prior_profile(
        ingest_fixture, criteria):
    result = ingest_fixture(1)
    observation = Observation(
        obs_id="window-only", pseudonym_id=result.submission.pseudonym_id,
        submission_id=result.submission.submission_id, observed_at=WHEN,
        criterion_id="specific", pattern_tag="thesis_too_general",
        claim_text="The claim is broad.", evidence_span="the temptation",
        source="machine",
    )
    source = _WindowOnlySource(result.submission, result.score, observation)

    regenerated = profile.regenerate_profile(
        result.submission.pseudonym_id, date(2026, 11, 14), source=source,
        criteria_set=criteria[1], now=WHEN)

    assert source.window == (
        result.submission.pseudonym_id, date(2026, 10, 17), date(2026, 11, 14))
    assert not source.read_profile_called
    assert [p.pattern_tag for p in regenerated.active_patterns] == [
        "thesis_too_general"
    ]
    assert "commentary_formulaic" not in {
        p.pattern_tag for p in regenerated.active_patterns
    }


def test_t13_feedback_order_one_focus_cap_and_peer_name_rejection(
        ingest_fixture, criteria):
    result = ingest_fixture(1)
    acknowledgment = Acknowledgment(
        kind="praise", directive_id="d-1",
        text="You met your stated goal for 3 pieces. Keep going.", streak=3)
    exemplar = feedback.ExemplarPair(
        rep_id=result.submission.rep_id,
        strong_text="A writer takes a clear side and gives a reason.",
        near_miss_text="A writer repeats the question without a reason.",
        what_separates_them="The strong answer makes a claim.",
    )
    recipient = result.submission.pseudonym_id
    forbidden = loader.real_names() | {
        entry["pseudonym"] for entry in loader.vault_entries()
        if entry["pseudonym"] != recipient
    }
    message = feedback.assemble_feedback(
        result.submission, result.score, criteria[1],
        next_focus="Make your position arguable.", acknowledgment=acknowledgment,
        exemplar=exemplar, forbidden_names=forbidden, now=WHEN)
    rendered = message.render()
    assert rendered.index("Checklist:") < rendered.index(acknowledgment.text)
    assert rendered.index(acknowledgment.text) < rendered.index(
        "One thing to work on:") < rendered.index("Two answers")
    assert rendered.count("One thing to work on:") == 1
    assert message.word_count <= 120
    for name in forbidden:
        assert name.lower() not in rendered.lower()

    with pytest.raises(feedback.PeerNameError):
        feedback.assemble_feedback(
            result.submission, result.score, criteria[1],
            exemplar=replace(exemplar, strong_text="Marcus makes a clear claim."),
            forbidden_names=forbidden, now=WHEN)

    enormous = Acknowledgment(
        kind="praise", directive_id="d-2", text="word " * 200, streak=3)
    capped = feedback.assemble_feedback(
        result.submission, result.score, criteria[1],
        next_focus="Make your position arguable.", acknowledgment=enormous,
        exemplar=exemplar, forbidden_names=forbidden, now=WHEN)
    assert capped.word_count <= 120
    assert "uptake acknowledgment" in capped.dropped_for_length

    with pytest.raises(feedback.FeedbackLengthError):
        feedback.assemble_feedback(
            result.submission, result.score, criteria[1], word_cap=1,
            forbidden_names=forbidden, now=WHEN)


def test_digest_includes_class_views_and_low_confidence_flags(
        ingest_fixture, criteria):
    first = ingest_fixture(1)
    flagged_submission = replace(
        first.submission, submission_id="sub-low-confidence",
        flags=[SegmentationFlag(code="low_confidence_segment",
                                detail="fuzzy provided-text match")],
    )
    flagged_score = replace(first.score, submission_id=flagged_submission.submission_id)
    observation = Observation(
        obs_id="obs-digest", pseudonym_id=first.submission.pseudonym_id,
        submission_id=first.submission.submission_id, observed_at=WHEN,
        criterion_id="arguable", pattern_tag="thesis_not_arguable",
        claim_text="The claim has no stance marker.", evidence_span="Students should",
        source="machine",
    )
    lapsed = Directive(
        directive_id="dir-lapsed", pseudonym_id=first.submission.pseudonym_id,
        issued_at=WHEN, text="State your claim directly.",
        target_pattern="thesis_not_arguable",
        detector=BannedPhraseDetector(phrases=["maybe"]), status="lapsed",
    )
    report = digest.build_digest(
        "section-2a", date(2026, 11, 9), date(2026, 11, 15),
        enrolled_pseudonyms=[first.submission.pseudonym_id, "Absent Student"],
        submissions=[replace(first.submission, submitted_at=WHEN),
                     replace(flagged_submission, submitted_at=WHEN)],
        scores={first.submission.submission_id: replace(first.score, scored_at=WHEN),
                flagged_submission.submission_id: replace(flagged_score, scored_at=WHEN)},
        observations=[observation], directives=[lapsed],
        profiles=[_profile(pseudonym_id=first.submission.pseudonym_id, ready=True)],
        criteria_set=criteria[1], prior_week_scores=[replace(first.score, total=0)],
        now=WHEN,
    )
    assert report.top_patterns and report.criterion_trends
    assert report.ready_for_tier_advance == [first.submission.pseudonym_id]
    assert report.lapsed_directives == [(first.submission.pseudonym_id,
                                         lapsed.text)]
    assert report.no_submissions_this_week == ["Absent Student"]
    assert [(flag.submission_id, flag.code) for flag in report.needs_human_eyes] == [
        (flagged_submission.submission_id, "low_confidence_segment")
    ]


def test_t15_calibration_is_blind_stratified_and_reports_agreement(
        ingest_fixture):
    result = ingest_fixture(1)
    submissions = []
    machine_scores = {}
    for index, total in enumerate((0, 1, 2, 4)):
        submission = replace(result.submission, submission_id=f"sub-cal-{index}")
        score = replace(result.score, submission_id=submission.submission_id,
                        total=total, possible=4)
        submissions.append(submission)
        machine_scores[submission.submission_id] = score

    sample = digest.build_calibration_sample(
        submissions, machine_scores, sample_id="cal-2026-11", size=4,
        strata=4, now=WHEN)
    assert {item.stratum for item in sample.items} == {0, 1, 2, 3}
    assert not hasattr(sample, "machine_scores")
    assert all(not hasattr(item, "score") for item in sample.items)

    teacher_scores = {
        item.submission_id: {
            item_id: result.met for item_id, result in
            machine_scores[item.submission_id].per_item.items()
        }
        for item in sample.items
    }
    first_item = sample.items[0]
    item_id = next(iter(teacher_scores[first_item.submission_id]))
    teacher_scores[first_item.submission_id][item_id] = not teacher_scores[
        first_item.submission_id][item_id]
    agreement = digest.calibration_agreement(sample, machine_scores,
                                             teacher_scores)
    assert agreement.compared_submissions == 4
    assert {item.item_id for item in agreement.per_criterion} == {
        item.item_id for item in result.score.per_item.values()
    }
    assert any(item.rate < 1.0 for item in agreement.per_criterion)
