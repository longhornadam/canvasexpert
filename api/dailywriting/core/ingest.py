"""One rep, start to finish.

Not in the handoff's file list, but something has to own the order, and the
order is where the invariants live:

    scrub -> segment -> score -> observe -> evaluate directives

Scrubbing is first because every span quoted downstream comes out of the text
this step produced (INV-7). Scoring comes before observing and before directive
evaluation because neither of those may influence it (INV-1), and it receives
segments rather than raw text so provided words cannot be mistaken for the
student's (INV-2 is what the later steps are for).

Nothing here writes to Canvas or touches a gradebook.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from api.dailywriting.core import directives as directives_module
from api.dailywriting.core import observations as observations_module
from api.dailywriting.core import scoring, scrub, segmentation
from api.dailywriting.core.directives import Acknowledgment
from api.dailywriting.core.models import (
    AssignmentContext,
    CriteriaSet,
    Directive,
    Observation,
    Score,
    Submission,
    utc_now,
)


@dataclass(frozen=True)
class IngestResult:
    submission: Submission
    score: Score
    observations: list[Observation] = field(default_factory=list)
    directives: list[Directive] = field(default_factory=list)
    acknowledgments: list[Acknowledgment] = field(default_factory=list)

    @property
    def acknowledgment(self) -> Acknowledgment | None:
        """The one acknowledgment this feedback message gets."""
        return directives_module.choose_acknowledgment(self.acknowledgments)


@dataclass(frozen=True)
class UnscoredIngestResult:
    """An extended piece (an ECR), ingested and segmented but not scored.

    No `Score`, on purpose: a checklist written for a one-sentence daily rep
    cannot honestly grade a 400-1500 word essay. `observations` carries only
    flag-derived noticings -- `no_student_text` and `exceeds_word_cap`, from
    `core.observations.observe_flags` -- because a criteria-derived
    observation requires a comparison this path never runs.
    """
    submission: Submission
    observations: list[Observation] = field(default_factory=list)


def _process(
    *,
    submission_id: str,
    rep_id: str,
    pseudonym_id: str,
    submitted_at: datetime,
    text: str,
    context: AssignmentContext,
    vault=None,
    roster_map: list[tuple] | None = None,
) -> Submission:
    """Scrub, segment, and build the `Submission` record.

    Shared by `ingest()` and `ingest_unscored()` so the scored path's
    behaviour cannot drift from what an unscored piece goes through: both
    call this one function rather than two copies of the same five lines.
    """
    scrubbed = scrub.scrub_writing(text, vault=vault, roster_map=roster_map)
    segmented = segmentation.segment_submission(scrubbed.text, context)

    return Submission(
        submission_id=submission_id,
        rep_id=rep_id,
        pseudonym_id=pseudonym_id,
        submitted_at=submitted_at,
        raw_text=scrubbed.text,
        segments=segmented.segments,
        student_word_count=segmented.student_word_count,
        flags=list(segmented.flags),
        scrub_findings=scrubbed.findings,
    )


def ingest(
    *,
    submission_id: str,
    rep_id: str,
    pseudonym_id: str,
    submitted_at: datetime,
    text: str,
    context: AssignmentContext,
    criteria_set: CriteriaSet,
    open_directives: Iterable[Directive] = (),
    vault=None,
    roster_map: list[tuple] | None = None,
    now: datetime | None = None,
) -> IngestResult:
    """Process one submission into a stored-shape record set.

    Raises `scoring.CriteriaNotPublishedError` when the checklist postdates the
    work, before doing anything else: measuring a student against criteria they
    had not been shown is not a result worth computing.
    """
    stamped = now or utc_now()

    scoring.assert_criteria_published(criteria_set.published_at, submitted_at)

    submission = _process(
        submission_id=submission_id, rep_id=rep_id, pseudonym_id=pseudonym_id,
        submitted_at=submitted_at, text=text, context=context, vault=vault,
        roster_map=roster_map,
    )

    score = scoring.score_submission(
        submission.segments_for_scoring(),
        criteria_set,
        context,
        submission_id=submission_id,
        raw_text=submission.raw_text,
        now=stamped,
    )

    # Observations are dated to the work, not to this run. `scored_at` above is
    # legitimately the processing time; an observation's date is what the
    # profile window and the weekly digest select on, so it has to be the
    # submission's own timestamp or a Wednesday backfill relocates Monday.
    observations = observations_module.observe_submission(
        submission, score, criteria_set, now=submitted_at, vault=vault)

    updated_directives, acknowledgments = directives_module.evaluate_all(
        list(open_directives), submission, tier=context.tier, now=stamped,
        rep_id=rep_id)

    return IngestResult(
        submission=submission,
        score=score,
        observations=observations,
        directives=updated_directives,
        acknowledgments=acknowledgments,
    )


def ingest_unscored(
    *,
    submission_id: str,
    rep_id: str,
    pseudonym_id: str,
    submitted_at: datetime,
    text: str,
    context: AssignmentContext,
    vault=None,
    roster_map: list[tuple] | None = None,
) -> UnscoredIngestResult:
    """Ingest an extended piece without checklist scoring.

    A sibling to `ingest()`, not an optional `criteria_set` on it:
    `IngestResult.score` is a required field with four consumers, and
    threading `None` through them to serve one new case would be worse than
    a second entry point that shares `_process`. Takes no `criteria_set` and
    calls no `CriteriaNotPublishedError` check, because there is no criteria
    comparison to publish a date against. Runs no directive evaluation
    either: directives are checked against checklist-scored reps.
    """
    submission = _process(
        submission_id=submission_id, rep_id=rep_id, pseudonym_id=pseudonym_id,
        submitted_at=submitted_at, text=text, context=context, vault=vault,
        roster_map=roster_map,
    )
    observations = observations_module.observe_flags(
        submission, now=submitted_at, vault=vault)
    return UnscoredIngestResult(submission=submission, observations=observations)


def record_gap(
    open_directives: Iterable[Directive],
    rep_id: str,
    *,
    now: datetime | None = None,
) -> list[Directive]:
    """Log a rep a student did not turn in.

    Absence is `na`, not `unmet`. A student who was out sick on Thursday has
    not broken a streak, and a system that says otherwise teaches them that
    follow-through is luck.
    """
    updated, _acks = directives_module.evaluate_all(
        list(open_directives), None, now=now, rep_id=rep_id)
    return updated
