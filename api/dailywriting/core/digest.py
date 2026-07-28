"""Teacher weekly digest, per section.

This is the artifact that makes "I read the class's work every week and design
the next week around it" true. It is aggregate by design: the teacher reads
individual work in full on major pieces, and reads the class here.

The calibration sample is the part to keep even when everything else gets
trimmed. Twenty submissions, stratified across the score range, presented with
the machine's scores hidden, for the teacher to score blind; agreement is then
reported per criterion. It is what keeps confidence in the instrument
falsifiable, and it never gets added later, so it is built in from the start.
`CalibrationSample` does not carry the machine scores at all: hiding them is a
property of the type rather than a promise about the UI.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from api.dailywriting.config import thresholds
from api.dailywriting.core.models import (
    CriteriaSet,
    Directive,
    Observation,
    RollingProfile,
    Score,
    Submission,
    utc_now,
)


@dataclass(frozen=True)
class PatternCount:
    pattern_tag: str
    count: int
    share_of_submissions: float
    students_affected: int
    example_spans: list[str]


@dataclass(frozen=True)
class CriterionTrend:
    item_id: str
    student_facing_text: str
    met_rate: float
    prior_met_rate: float | None
    delta: float | None
    scored: int


@dataclass(frozen=True)
class FlagNote:
    submission_id: str
    code: str
    detail: str


@dataclass(frozen=True)
class CalibrationItem:
    submission_id: str
    stratum: int
    criteria_set_id: str
    text: str


@dataclass(frozen=True)
class CalibrationSample:
    """Blind scoring set. Carries no machine scores, by construction."""

    sample_id: str
    generated_at: datetime
    strata: int
    items: list[CalibrationItem]

    @property
    def submission_ids(self) -> list[str]:
        return [item.submission_id for item in self.items]


@dataclass(frozen=True)
class CriterionAgreement:
    item_id: str
    agreed: int
    compared: int
    rate: float


@dataclass(frozen=True)
class CalibrationAgreement:
    sample_id: str
    compared_submissions: int
    per_criterion: list[CriterionAgreement]
    overall_rate: float
    disagreements: list[tuple[str, str, bool, bool]]


@dataclass(frozen=True)
class SectionDigest:
    section_id: str
    week_start: date
    week_end: date
    generated_at: datetime
    submissions_counted: int
    students_counted: int
    top_patterns: list[PatternCount] = field(default_factory=list)
    criterion_trends: list[CriterionTrend] = field(default_factory=list)
    ready_for_tier_advance: list[str] = field(default_factory=list)
    lapsed_directives: list[tuple[str, str]] = field(default_factory=list)
    no_submissions_this_week: list[str] = field(default_factory=list)
    needs_human_eyes: list[FlagNote] = field(default_factory=list)
    calibration: CalibrationSample | None = None
    coverage_notes: list[str] = field(default_factory=list)


def _met_rates(scores: list[Score]) -> tuple[dict[str, float], dict[str, int]]:
    met: dict[str, int] = defaultdict(int)
    seen: dict[str, int] = defaultdict(int)
    for score in scores:
        if score.status != "scored":
            continue
        for item_id, result in score.per_item.items():
            seen[item_id] += 1
            if result.met:
                met[item_id] += 1
    rates = {item_id: met[item_id] / seen[item_id]
             for item_id in seen if seen[item_id]}
    return rates, dict(seen)


def _top_patterns(observations: list[Observation],
                  submission_count: int) -> list[PatternCount]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.pattern_tag].append(observation)

    counts: list[PatternCount] = []
    for tag, group in grouped.items():
        spans: list[str] = []
        for observation in group:
            if observation.evidence_span not in spans:
                spans.append(observation.evidence_span)
            if len(spans) >= thresholds.DIGEST_SPANS_PER_PATTERN:
                break
        counts.append(PatternCount(
            pattern_tag=tag,
            count=len(group),
            share_of_submissions=(round(len(group) / submission_count, 4)
                                  if submission_count else 0.0),
            students_affected=len({o.pseudonym_id for o in group}),
            example_spans=spans,
        ))
    counts.sort(key=lambda p: (-p.count, p.pattern_tag))
    return counts[:thresholds.DIGEST_TOP_PATTERNS]


def build_calibration_sample(
    submissions: list[Submission],
    scores: dict[str, Score],
    *,
    sample_id: str,
    size: int | None = None,
    strata: int | None = None,
    now: datetime | None = None,
) -> CalibrationSample:
    """Stratified blind-scoring set across the whole score range.

    Stratifying matters: a random twenty is mostly middling work, and agreement
    on middling work says nothing about whether the instrument can tell a 4
    from a 2. Selection is deterministic (highest scores first within each
    band, ties by submission id) so the same week produces the same sample and
    a teacher can be handed it twice without it silently changing.
    """
    size = thresholds.CALIBRATION_SAMPLE_SIZE if size is None else size
    strata = thresholds.CALIBRATION_STRATA if strata is None else strata
    stamped = now or utc_now()

    scored = [(s, scores[s.submission_id]) for s in submissions
              if s.submission_id in scores
              and scores[s.submission_id].status == "scored"
              and scores[s.submission_id].possible]
    if not scored:
        return CalibrationSample(sample_id=sample_id, generated_at=stamped,
                                 strata=strata, items=[])

    buckets: dict[int, list[tuple[Submission, Score]]] = defaultdict(list)
    for submission, score in scored:
        fraction = score.total / score.possible
        index = min(strata - 1, int(fraction * strata))
        buckets[index].append((submission, score))
    for index in buckets:
        buckets[index].sort(key=lambda pair: (-pair[1].total,
                                              pair[0].submission_id))

    items: list[CalibrationItem] = []
    depth = 0
    while len(items) < size and any(len(b) > depth for b in buckets.values()):
        for index in range(strata):
            bucket = buckets.get(index, [])
            if len(bucket) <= depth or len(items) >= size:
                continue
            submission, _score = bucket[depth]
            items.append(CalibrationItem(
                submission_id=submission.submission_id,
                stratum=index,
                criteria_set_id=_score.criteria_set_id,
                text=submission.raw_text,
            ))
        depth += 1

    return CalibrationSample(sample_id=sample_id, generated_at=stamped,
                             strata=strata, items=items)


def calibration_agreement(
    sample: CalibrationSample,
    machine_scores: dict[str, Score],
    teacher_scores: dict[str, dict[str, bool]],
) -> CalibrationAgreement:
    """Per-criterion agreement between the machine and the teacher's blind read.

    `teacher_scores` maps submission_id to {item_id: met}. Only submissions the
    teacher actually scored are compared, and the count is reported, so a
    half-finished calibration reads as a half-finished calibration rather than
    as agreement.
    """
    agreed: dict[str, int] = defaultdict(int)
    compared: dict[str, int] = defaultdict(int)
    disagreements: list[tuple[str, str, bool, bool]] = []
    submissions_compared = 0

    for item in sample.items:
        teacher = teacher_scores.get(item.submission_id)
        machine = machine_scores.get(item.submission_id)
        if not teacher or machine is None:
            continue
        submissions_compared += 1
        for item_id, teacher_met in teacher.items():
            machine_result = machine.per_item.get(item_id)
            if machine_result is None:
                continue
            compared[item_id] += 1
            if bool(machine_result.met) == bool(teacher_met):
                agreed[item_id] += 1
            else:
                disagreements.append((item.submission_id, item_id,
                                      bool(machine_result.met),
                                      bool(teacher_met)))

    per_criterion = [
        CriterionAgreement(item_id=item_id, agreed=agreed[item_id],
                           compared=compared[item_id],
                           rate=round(agreed[item_id] / compared[item_id], 4))
        for item_id in sorted(compared) if compared[item_id]
    ]
    total_compared = sum(compared.values())
    total_agreed = sum(agreed.values())
    return CalibrationAgreement(
        sample_id=sample.sample_id,
        compared_submissions=submissions_compared,
        per_criterion=per_criterion,
        overall_rate=(round(total_agreed / total_compared, 4)
                      if total_compared else 0.0),
        disagreements=disagreements,
    )


def build_digest(
    section_id: str,
    week_start: date,
    week_end: date,
    *,
    enrolled_pseudonyms: list[str],
    submissions: list[Submission],
    scores: dict[str, Score],
    observations: list[Observation],
    directives: list[Directive],
    profiles: list[RollingProfile] | None = None,
    criteria_set: CriteriaSet | None = None,
    prior_week_scores: list[Score] | None = None,
    calibration: CalibrationSample | None = None,
    now: datetime | None = None,
) -> SectionDigest:
    """Assemble one section's weekly read.

    Everything here is derived from records the teacher can open. Nothing is
    summarised past the point where the underlying span can still be found.
    """
    stamped = now or utc_now()
    in_week = [s for s in submissions
               if week_start <= s.submitted_at.date() <= week_end]
    week_scores = [scores[s.submission_id] for s in in_week
                   if s.submission_id in scores]
    week_observations = [o for o in observations
                        if week_start <= o.observed_at.date() <= week_end]

    rates, seen = _met_rates(week_scores)
    prior_rates, _prior_seen = _met_rates(list(prior_week_scores or []))

    trends: list[CriterionTrend] = []
    item_order = ([item.item_id for item in criteria_set.items]
                  if criteria_set else sorted(rates))
    for item_id in item_order:
        if item_id not in rates:
            continue
        prior = prior_rates.get(item_id)
        item = criteria_set.item(item_id) if criteria_set else None
        trends.append(CriterionTrend(
            item_id=item_id,
            student_facing_text=item.student_facing_text if item else item_id,
            met_rate=round(rates[item_id], 4),
            prior_met_rate=None if prior is None else round(prior, 4),
            delta=None if prior is None else round(rates[item_id] - prior, 4),
            scored=seen.get(item_id, 0),
        ))

    submitted_pseudonyms = {s.pseudonym_id for s in in_week}
    missing = sorted(set(enrolled_pseudonyms) - submitted_pseudonyms)

    lapsed = sorted({(d.pseudonym_id, d.text) for d in directives
                     if d.status == "lapsed"})

    ready = sorted({p.pseudonym_id for p in (profiles or [])
                    if p.ready_for_tier_advance})

    flags = [
        FlagNote(submission_id=submission.submission_id, code=flag.code,
                 detail=flag.detail)
        for submission in in_week
        for flag in submission.flags
        if flag.code in ("low_confidence_segment", "cross_submission_repeat",
                         "empty_stem_blank", "no_student_text",
                         "unlocatable_evidence_span")
    ]

    coverage: list[str] = []
    if len(week_observations) and len(_top_patterns(week_observations,
                                                    len(in_week))) < len(
            {o.pattern_tag for o in week_observations}):
        shown = thresholds.DIGEST_TOP_PATTERNS
        total = len({o.pattern_tag for o in week_observations})
        coverage.append(
            f"Showing the top {shown} of {total} pattern types seen this week; "
            "the rest are in the record."
        )
    if not week_scores:
        coverage.append("No scored work in this week, so every rate is blank "
                        "rather than zero.")

    return SectionDigest(
        section_id=section_id,
        week_start=week_start,
        week_end=week_end,
        generated_at=stamped,
        submissions_counted=len(in_week),
        students_counted=len(submitted_pseudonyms),
        top_patterns=_top_patterns(week_observations, len(in_week)),
        criterion_trends=trends,
        ready_for_tier_advance=ready,
        lapsed_directives=lapsed,
        no_submissions_this_week=missing,
        needs_human_eyes=flags,
        calibration=calibration,
        coverage_notes=coverage,
    )
