"""Rolling profile regeneration (INV-4, INV-5, INV-6).

The working summary is rebuilt from a bounded recent window, never appended
to. Patterns must re-earn their place from in-window evidence every time.
Older observations stay in the immutable record for the teacher to read, and
they stop steering what the student is told, which is the difference between a
history and a reputation.

The self-confirmation guard is the part worth guarding: `active_patterns` is
derived from `Observation` records in the window and nothing else. This module
never reads a prior profile. Given the chance it would, September's label
would quietly become November's lens, and the student would be answering for
a sentence they wrote two months ago.

INV-5 is enforced by `models.build_profile`, which this module goes through
rather than around. INV-6 is enforced by `student_view`, which renders the
whole profile as plain strings: if a field cannot be shown to the student, it
has no business being in here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Protocol

from api.dailywriting.config import thresholds
from api.dailywriting.core.models import (
    CriteriaSet,
    Directive,
    Observation,
    PatternSummary,
    RollingProfile,
    Score,
    Submission,
    SubmissionRef,
    build_profile,
    utc_now,
)


class ProfileSource(Protocol):
    """What regeneration is allowed to read.

    Note the absence of any profile read. The protocol is the enforcement:
    a source that offered `read_profile` would still not be called, and the
    test for INV-4 asserts exactly that.
    """

    def submissions_in_window(self, pseudonym_id: str, start: date,
                              end: date) -> list[Submission]: ...

    def scores_for(self, submission_ids: list[str]) -> dict[str, Score]: ...

    def observations_in_window(self, pseudonym_id: str, start: date,
                               end: date) -> list[Observation]: ...

    def directives_for(self, pseudonym_id: str) -> list[Directive]: ...

    def current_tier(self, pseudonym_id: str) -> int: ...


def window_bounds(as_of: date, window_weeks: int) -> tuple[date, date]:
    return as_of - timedelta(weeks=window_weeks), as_of


def _per_criterion_rate(scores: list[Score]) -> dict[str, float]:
    """Met-rate per criterion across scored work in the window.

    Submissions with no student writing are excluded from the denominator.
    A copy-paste error is a flag, not a measurement of whether this student
    can write an arguable thesis.
    """
    met: dict[str, int] = defaultdict(int)
    seen: dict[str, int] = defaultdict(int)
    for score in scores:
        if score.status != "scored":
            continue
        for item_id, result in score.per_item.items():
            seen[item_id] += 1
            if result.met:
                met[item_id] += 1
    return {item_id: round(met[item_id] / seen[item_id], 4)
            for item_id in sorted(seen) if seen[item_id]}


def _active_patterns(observations: list[Observation],
                     scored_count: int) -> list[PatternSummary]:
    """Rank in-window patterns by frequency, keeping representative evidence.

    A pattern with no in-window evidence is absent, not zero.
    """
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.pattern_tag].append(observation)

    summaries: list[PatternSummary] = []
    for tag, group in grouped.items():
        if len(group) < thresholds.PROFILE_MIN_PATTERN_COUNT:
            continue
        ordered = sorted(group, key=lambda o: o.observed_at)
        summaries.append(PatternSummary(
            pattern_tag=tag,
            count=len(group),
            rate=round(len(group) / scored_count, 4) if scored_count else 0.0,
            evidence=[o.evidence_span for o in ordered[-thresholds.DIGEST_SPANS_PER_PATTERN:]],
            first_seen=ordered[0].observed_at.date(),
            last_seen=ordered[-1].observed_at.date(),
        ))
    summaries.sort(key=lambda s: (-s.count, s.pattern_tag))
    return summaries[:thresholds.PROFILE_MAX_ACTIVE_PATTERNS]


def _best_piece(submissions: list[Submission],
                scores: dict[str, Score]) -> SubmissionRef | None:
    """Highest total, ties broken by recency."""
    candidates = []
    for submission in submissions:
        score = scores.get(submission.submission_id)
        if score is None or score.status != "scored":
            continue
        candidates.append((score.total, submission.submitted_at, submission, score))
    if not candidates:
        return None
    _total, _when, submission, score = max(candidates, key=lambda c: (c[0], c[1]))
    return SubmissionRef(
        submission_id=submission.submission_id,
        rep_id=submission.rep_id,
        on=submission.submitted_at.date(),
        total=score.total,
        possible=score.possible,
    )


def _next_focus(rates: dict[str, float],
                open_directives: list[Directive],
                criteria_set: CriteriaSet | None) -> str:
    """The one thing to work on next.

    A lapsed directive outranks the weakest criterion: the student was already
    told this, they had it, and they let it go. That is more urgent than a
    criterion they have never held.
    """
    lapsed = [d for d in open_directives if d.status == "lapsed"]
    if lapsed:
        return lapsed[0].text
    if not rates:
        return ("No scored work in this window yet, so there is nothing to "
                "focus on from the record.")
    weakest = min(sorted(rates), key=lambda item_id: rates[item_id])
    if criteria_set:
        item = criteria_set.item(weakest)
        if item:
            return item.student_facing_text
    return weakest


def _ready_for_advance(rates: dict[str, float], criteria_set: CriteriaSet | None,
                       scored_count: int) -> bool:
    """Recommendation only. Nothing in this package promotes anyone."""
    if scored_count < thresholds.TIER_ADVANCE_MIN_SUBMISSIONS:
        return False
    required = ([item.item_id for item in criteria_set.items]
                if criteria_set else list(rates))
    if not required:
        return False
    return all(rates.get(item_id, 0.0) >= thresholds.TIER_ADVANCE_RATE
               for item_id in required)


def regenerate_profile(
    pseudonym_id: str,
    as_of: date,
    window_weeks: int = thresholds.PROFILE_WINDOW_WEEKS,
    *,
    source: ProfileSource | None = None,
    criteria_set: CriteriaSet | None = None,
    now: datetime | None = None,
) -> RollingProfile:
    """Rebuild one student's working summary from the record.

    Takes no `Score` argument on purpose: scores are pulled from the window,
    so a caller cannot hand this function a hand-picked result and have it
    treated as the student's recent history.
    """
    if source is None:
        from api.dailywriting.store.repo import Repository
        source = Repository.default()

    start, end = window_bounds(as_of, window_weeks)
    submissions = source.submissions_in_window(pseudonym_id, start, end)
    scores = source.scores_for([s.submission_id for s in submissions])
    observations = source.observations_in_window(pseudonym_id, start, end)
    directives = source.directives_for(pseudonym_id)
    tier = source.current_tier(pseudonym_id)

    scored = [scores[s.submission_id] for s in submissions
              if s.submission_id in scores
              and scores[s.submission_id].status == "scored"]
    rates = _per_criterion_rate(list(scores.values()))
    open_directives = [d for d in directives
                       if d.status in ("open", "met", "lapsed")]

    return build_profile(
        pseudonym_id=pseudonym_id,
        generated_at=now or utc_now(),
        window_start=start,
        window_end=end,
        tier=tier,
        per_criterion_rate=rates,
        active_patterns=_active_patterns(observations, len(scored)),
        open_directives=open_directives,
        best_piece=_best_piece(submissions, scores),
        next_focus=_next_focus(rates, open_directives, criteria_set),
        ready_for_tier_advance=_ready_for_advance(rates, criteria_set,
                                                 len(scored)),
    )


def student_view(profile: RollingProfile,
                 criteria_set: CriteriaSet | None = None) -> dict:
    """Render the whole profile as plain strings for the student (INV-6).

    Every field goes in. That is the test: a profile field that cannot be
    rendered here is a field that should not exist.
    """
    def label(item_id: str) -> str:
        if criteria_set:
            item = criteria_set.item(item_id)
            if item:
                return item.student_facing_text
        return item_id

    return {
        "student": profile.pseudonym_id,
        "updated": profile.generated_at.isoformat(),
        "window": (f"{profile.window_start.isoformat()} to "
                   f"{profile.window_end.isoformat()}"),
        "tier": f"Tier {profile.tier}",
        "checklist": [
            f"{label(item_id)} — {rate:.0%} of the time"
            for item_id, rate in sorted(profile.per_criterion_rate.items())
        ],
        "habits": [
            (f"{pattern.pattern_tag.replace('_', ' ')}: {pattern.count} times "
             f"since {pattern.first_seen.isoformat()}. For example: "
             f"\"{pattern.evidence[0]}\"" if pattern.evidence else "")
            for pattern in profile.active_patterns
        ],
        "what_i_was_asked": [d.text for d in profile.open_directives],
        "best_piece": (
            f"{profile.best_piece.rep_id} on "
            f"{profile.best_piece.on.isoformat()} "
            f"({profile.best_piece.total}/{profile.best_piece.possible})"
            if profile.best_piece else "No scored work in this window yet."
        ),
        "next_focus": profile.next_focus,
        "ready_for_next_tier": (
            "Your teacher may move you up soon."
            if profile.ready_for_tier_advance
            else "Keep working at this tier."
        ),
    }
