"""Assistant-facing projection of the longitudinal writing record.

The store (`store/repo.py`) is private and keyed by `canvas_id`; nothing above
it may hand a stored record to a payload builder wholesale, because
`canvas_id` alone would hard-block the outbound gate and because a field
added to `Submission`, `Score`, `Observation`, `Directive`, or `RollingProfile`
tomorrow must not silently become outbound today. This module is the one
place a record becomes assistant-facing data, and it works the way
`api.powergrader.writing_timeline.safe_projection` does: a strict whitelist
rebuild, naming every outbound key by hand, never a serialization of the
source object.

`include_text` gates every field that is, or can quote, student writing:
`Submission.raw_text`, `Observation.claim_text` and `.evidence_span`,
`ItemResult.evidence_span` AND `ItemResult.note` (`core.scoring` interpolates
a slice of the student's own thesis/argument/commentary straight into several
notes -- it is not machine-only prose, despite reading like a label; outbound
it is named `score_note`, not `note` -- see below), `DirectiveEval.evidence_span`,
and the quoted spans inside a profile's `active_patterns[].evidence` -- the
last one is not called out separately in `RollingProfile`'s own invariants,
but a pattern's evidence is exactly as identity-bearing as any other span
quoted out of a submission, so it gets the same gate. `DirectiveEval.note` is
the one exception, left unconditional, because `core.directives.run_detector`
builds it only from teacher-authored detector config and never from student
prose (see `_eval_row`). `AssignmentContext.prompt_text` is teacher-authored,
not student data, and is always included, truncated like everything else.

Every projected text field reuses a name already in
`feedback_safety._TEXT_FIELDS` (INV-7's outbound gate is field-name-keyed) so
the gate actually scans the bytes this module hands out -- with one deliberate
exception: `ItemResult.note` goes out as `score_note`, not `note`, because a
bare `note` key already carries different, non-text semantics elsewhere in
this codebase (see the comment above `feedback_safety._TEXT_FIELDS`); reusing
it here would have quietly widened that other usage into free-text scanning
too. Quoted spans that have no natural dict home of their own
(`PatternSummary.evidence` is a bare list of strings) are wrapped as
`{"evidence_span": ...}` rather than left as bare list entries, because the
gate only scans dict values under a matching key -- a bare string in a list
is invisible to it.
"""
from __future__ import annotations

from datetime import date

from api.dailywriting.core.models import (
    AssignmentContext,
    Directive,
    DirectiveEval,
    ItemResult,
    Observation,
    PatternSummary,
    RollingProfile,
    Score,
    Submission,
    SubmissionRef,
)


def _truncate(text: str, max_chars: int) -> str:
    """Trim with an explicit marker, same convention as
    `api.mcp_server.tools._truncate_text` (kept separate rather than shared,
    so this package takes no dependency on the MCP layer that depends on it)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f" …[truncated {len(text) - max_chars} more chars]"


def _item_result_row(result: ItemResult, *, include_text: bool,
                     max_text_chars: int) -> dict:
    """`note` is gated the same as `evidence_span`, not left unconditional:
    `core.scoring` interpolates a slice of the student's own thesis, argument,
    or commentary straight into several of these notes (for example
    `f'introduces the quotation ("{before[:40]}")'`), so it is exactly as
    identity-bearing as a quoted span, and the default call must not carry
    it. `item_id`, `met`, and `needs_judgment` are the per-criterion outcome
    AC1 asks for and never quote the student, so they stay unconditional.

    Emitted as `score_note`, not `note`: see the module docstring and the
    comment above `feedback_safety._TEXT_FIELDS`. A bare `note` key already
    means something else -- a structural exact-value id, not free text -- in
    other payloads this same gate scans, so reusing it here would have
    silently reclassified that other usage too."""
    row = {
        "item_id": result.item_id,
        "met": result.met,
        "needs_judgment": result.needs_judgment,
    }
    if include_text:
        row["score_note"] = _truncate(result.note, max_text_chars)
        if result.evidence_span is not None:
            row["evidence_span"] = _truncate(result.evidence_span.text,
                                             max_text_chars)
    return row


def _observation_row(observation: Observation, *, include_text: bool,
                     max_text_chars: int) -> dict:
    row = {
        "pattern_tag": observation.pattern_tag,
        "criterion_id": observation.criterion_id,
        "source": observation.source,
        "observed_at": observation.observed_at.isoformat(),
    }
    if include_text:
        row["claim_text"] = _truncate(observation.claim_text, max_text_chars)
        row["evidence_span"] = _truncate(observation.evidence_span, max_text_chars)
    return row


def _submission_row(submission: Submission, score: Score | None,
                    observations: list[Observation], rep: AssignmentContext | None,
                    *, include_text: bool, max_text_chars: int) -> dict:
    row = {
        "submission_id": submission.submission_id,
        "rep_id": submission.rep_id,
        "submitted_at": submission.submitted_at.isoformat(),
        "tier": rep.tier if rep is not None else None,
        "student_word_count": submission.student_word_count,
        "total": score.total if score is not None else None,
        "possible": score.possible if score is not None else None,
        "status": score.status if score is not None else None,
        "observation_count": len(observations),
        # Teacher-authored, not student data (AssignmentContext carries no
        # student handle) -- always included, unlike every text field below.
        "prompt_text": (_truncate(rep.prompt_text, max_text_chars)
                        if rep is not None else ""),
        "observations": [
            _observation_row(o, include_text=include_text,
                             max_text_chars=max_text_chars)
            for o in observations
        ],
    }
    if score is not None:
        row["per_item"] = {
            item_id: _item_result_row(result, include_text=include_text,
                                      max_text_chars=max_text_chars)
            for item_id, result in score.per_item.items()
        }
    if include_text:
        row["raw_text"] = _truncate(submission.raw_text, max_text_chars)
    return row


def _eval_row(evaluation: DirectiveEval, *, include_text: bool,
             max_text_chars: int) -> dict:
    """Unlike `ItemResult.note` above, `DirectiveEval.note` is left
    unconditional on purpose: `core.directives.run_detector` builds it only
    from teacher-authored detector config (a banned phrase, a pattern
    description -- see `directives.py:194-231`), never from student prose, so
    it carries no quoted span to gate. `evidence_span` still is gated: that
    one *is* a sentence pulled from the student's own writing."""
    row = {
        "submission_id": evaluation.submission_id,
        "evaluated_at": evaluation.evaluated_at.isoformat(),
        "result": evaluation.result,
        "note": evaluation.note,
    }
    if include_text and evaluation.evidence_span:
        row["evidence_span"] = _truncate(evaluation.evidence_span, max_text_chars)
    return row


def _directive_row(directive: Directive, *, include_text: bool,
                   max_text_chars: int) -> dict:
    return {
        "directive_id": directive.directive_id,
        # The directive text is what the teacher told the student, quoted
        # exactly -- teacher-authored, not a span pulled from student prose.
        "text": directive.text,
        "target_pattern": directive.target_pattern,
        "status": directive.status,
        "current_streak": directive.current_streak,
        "best_streak": directive.best_streak,
        "issued_at": directive.issued_at.isoformat(),
        "evaluations": [
            _eval_row(e, include_text=include_text, max_text_chars=max_text_chars)
            for e in directive.evaluations
        ],
    }


def _ref_row(ref: SubmissionRef | None) -> dict | None:
    if ref is None:
        return None
    return {
        "submission_id": ref.submission_id,
        "rep_id": ref.rep_id,
        "on": ref.on.isoformat(),
        "total": ref.total,
        "possible": ref.possible,
    }


def _pattern_row(pattern: PatternSummary, *, include_text: bool,
                 max_text_chars: int) -> dict:
    row = {
        "pattern_tag": pattern.pattern_tag,
        "count": pattern.count,
        "rate": pattern.rate,
        "first_seen": pattern.first_seen.isoformat(),
        "last_seen": pattern.last_seen.isoformat(),
    }
    if include_text:
        # Wrapped under the scanned key name rather than left as bare list
        # entries -- see the module docstring.
        row["evidence"] = [
            {"evidence_span": _truncate(quote, max_text_chars)}
            for quote in pattern.evidence
        ]
    return row


def _profile_row(profile: RollingProfile | None, *, include_text: bool,
                 max_text_chars: int) -> dict | None:
    """INV-6 already says anything in a profile is renderable to the student,
    so nothing here is withheld on identity grounds -- only the quoted
    evidence inside `active_patterns` follows the same include_text gate as
    every other span quoted from student writing (see the module docstring)."""
    if profile is None:
        return None
    return {
        "generated_at": profile.generated_at.isoformat(),
        "window_start": profile.window_start.isoformat(),
        "window_end": profile.window_end.isoformat(),
        "tier": profile.tier,
        "per_criterion_rate": dict(profile.per_criterion_rate),
        "active_patterns": [
            _pattern_row(p, include_text=include_text, max_text_chars=max_text_chars)
            for p in profile.active_patterns
        ],
        # The directives themselves are projected once, at the top level of
        # `build_history_payload`; duplicating their teacher-authored text
        # here would gain nothing.
        "open_directive_ids": [d.directive_id for d in profile.open_directives],
        "best_piece": _ref_row(profile.best_piece),
        "next_focus": profile.next_focus,
        "ready_for_tier_advance": profile.ready_for_tier_advance,
    }


def build_history_payload(
    *,
    pseudonym_id: str,
    current_tier: int,
    since: date,
    until: date,
    submissions: list[Submission],
    scores: dict[str, Score],
    observations: list[Observation],
    reps: dict[str, AssignmentContext | None],
    directives: list[Directive],
    profile: RollingProfile | None,
    include_text: bool,
    max_text_chars: int,
) -> dict:
    """Rebuild the outbound payload from already-resolved store reads.

    Takes domain objects, not a `Repository` -- the store reads happen at the
    call site (`api.mcp_server.tools.get_writing_history`), which is also
    where `store.identity.IdentityError` gets converted to a structured
    refusal. Nothing here calls back into the store, and nothing here reads
    or infers a `canvas_id`.
    """
    observations_by_submission: dict[str, list[Observation]] = {}
    for observation in observations:
        observations_by_submission.setdefault(
            observation.submission_id, []).append(observation)

    rows = [
        _submission_row(
            submission, scores.get(submission.submission_id),
            observations_by_submission.get(submission.submission_id, []),
            reps.get(submission.rep_id),
            include_text=include_text, max_text_chars=max_text_chars,
        )
        for submission in sorted(submissions, key=lambda s: s.submitted_at)
    ]

    return {
        "pseudonym": pseudonym_id,
        "current_tier": current_tier,
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "submissions": rows,
        "directives": [
            _directive_row(d, include_text=include_text, max_text_chars=max_text_chars)
            for d in directives
        ],
        "profile": _profile_row(profile, include_text=include_text,
                                max_text_chars=max_text_chars),
    }
