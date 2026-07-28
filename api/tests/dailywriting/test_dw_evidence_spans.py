"""Evidence spans must be locatable in the stored submission text."""
from __future__ import annotations

from datetime import date, datetime, timezone

from api.dailywriting.config import criteria_loader
from api.dailywriting.core import digest, ingest, observations
from api.dailywriting.core.models import (
    AssignmentContext,
    CriteriaSet,
    CriterionItem,
    ItemResult,
    Score,
    Submission,
)
from api.dailywriting.fixtures import loader


_TEXT = (
    'Phones should stay in backpacks during class. The article says "test '
    'scores fell twelve percent in classrooms that allowed phones," which is '
    'a big drop. That number matters because it shows the distraction costs '
    'real learning. It connects back to why the rule should change.'
)


def _context() -> AssignmentContext:
    return AssignmentContext(
        rep_id="evidence-span-repro",
        date=date(2026, 10, 21),
        tier=4,
        prompt_text=("Should phones stay in backpacks during class? Quote the "
                     "article and explain."),
        criteria_set_id="tier4_commentary.v1",
    )


def _result(text: str):
    return ingest.ingest(
        submission_id="evidence-span-repro",
        rep_id="evidence-span-repro",
        pseudonym_id="fictional-student",
        submitted_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        text=text,
        context=_context(),
        criteria_set=criteria_loader.load_all_tiers()[4],
    )


def test_evidence_span_repros_reach_the_record_and_point_into_raw_text():
    """AC1-3: paragraph whitespace cannot drop evidence-backed noticings."""
    single = _result(_TEXT)
    two_paragraphs = _result(_TEXT.replace(" That number", "\n\nThat number"))

    for result in (single, two_paragraphs):
        expected = {
            item_id
            for item_id, item in result.score.per_item.items()
            if not item.met and item_id in observations._ITEM_PATTERNS
        }
        recorded = {observation.criterion_id for observation in result.observations}
        assert expected <= recorded
        for item in result.score.per_item.values():
            if item.evidence_span:
                span = item.evidence_span
                assert result.submission.raw_text[span.start:span.end] == span.text

    assert {
        (observation.criterion_id, observation.pattern_tag)
        for observation in single.observations
    } == {
        (observation.criterion_id, observation.pattern_tag)
        for observation in two_paragraphs.observations
    }


def test_unlocatable_unmet_evidence_is_flagged_for_the_weekly_digest():
    """AC4: INV-3 still drops an unquotable noticing, but never silently."""
    item = CriterionItem(
        item_id="evidence_relevant",
        label="Evidence is relevant",
        student_facing_text="",
        check_description="",
        check_id="evidence_relevant",
    )
    criteria = CriteriaSet(
        criteria_set_id="test", tier=4, version=1, items=[item],
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    submission = Submission(
        submission_id="unlocatable", rep_id="test", pseudonym_id="fictional-student",
        submitted_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        raw_text="A response whose proof cannot be located.", segments=[],
        student_word_count=7,
    )
    score = Score(
        submission_id=submission.submission_id,
        criteria_set_id=criteria.criteria_set_id,
        per_item={item.item_id: ItemResult(
            item_id=item.item_id, met=False, evidence_span=None,
            note="a constructed missing span",
        )},
        total=0, possible=1, scored_at=submission.submitted_at,
        scorer_version="test",
    )

    assert observations.observe_submission(submission, score, criteria) == []
    assert any(flag.code == "unlocatable_evidence_span" for flag in submission.flags)
    report = digest.build_digest(
        "test", date(2026, 10, 20), date(2026, 10, 24),
        enrolled_pseudonyms=[submission.pseudonym_id],
        submissions=[submission], scores={submission.submission_id: score},
        observations=[], directives=[], criteria_set=criteria,
    )
    assert [(flag.submission_id, flag.code) for flag in report.needs_human_eyes] == [
        (submission.submission_id, "unlocatable_evidence_span")
    ]


def test_every_fixture_score_span_is_an_exact_raw_text_slice(ingest_fixture):
    """AC3: this is geometry, so exercise the pinned fixture corpus too."""
    for fixture_number in loader.single_numbers():
        result = ingest_fixture(fixture_number)
        for item in result.score.per_item.values():
            if item.evidence_span:
                span = item.evidence_span
                assert result.submission.raw_text[span.start:span.end] == span.text
