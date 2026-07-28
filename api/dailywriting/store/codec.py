"""Record to JSON document conversion.

The rest of Canvas Expert persists plain dicts with explicit validators rather
than schema classes, so the typed records in `core.models` stop at this
boundary and everything below it is ordinary JSON.

On-disk records carry `canvas_id`; in-memory records carry `pseudonym_id`. The
swap happens here and only here, so there is exactly one place to check when
asking whether a real identifier can reach a payload.
"""
from __future__ import annotations

from datetime import date, datetime

from api.dailywriting.core.models import (
    AssignmentContext,
    BannedPhraseDetector,
    Directive,
    DirectiveEval,
    ItemResult,
    JudgmentDetector,
    Observation,
    PatternSummary,
    RequiredMoveDetector,
    RollingProfile,
    ScaffoldBlock,
    Score,
    ScrubFinding,
    Segment,
    SegmentationFlag,
    Span,
    Submission,
    SubmissionRef,
    build_profile,
)

DOCUMENT_VERSION = 1


class RecordSchemaError(ValueError):
    """A stored document does not match the shape this codec reads."""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _require(document: dict, kind: str, *keys: str) -> None:
    missing = [key for key in keys if key not in document]
    if missing:
        raise RecordSchemaError(f"stored {kind} is missing {missing}")


# --- Span, Segment, flags ---------------------------------------------------


def span_to_dict(span: Span | None) -> dict | None:
    if span is None:
        return None
    return {"start": span.start, "end": span.end, "text": span.text}


def span_from_dict(document: dict | None) -> Span | None:
    if not document:
        return None
    return Span(start=int(document["start"]), end=int(document["end"]),
                text=document.get("text", ""))


def segment_to_dict(segment: Segment) -> dict:
    return {
        "span_start": segment.span_start,
        "span_end": segment.span_end,
        "text": segment.text,
        "origin": segment.origin,
        "confidence": segment.confidence,
        "method": segment.method,
    }


def segment_from_dict(document: dict) -> Segment:
    _require(document, "segment", "span_start", "span_end", "origin", "method")
    return Segment(
        span_start=int(document["span_start"]),
        span_end=int(document["span_end"]),
        text=document.get("text", ""),
        origin=document["origin"],
        confidence=float(document.get("confidence", 0.0)),
        method=document["method"],
    )


def flag_to_dict(flag: SegmentationFlag) -> dict:
    return {"code": flag.code, "detail": flag.detail,
            "span": span_to_dict(flag.span)}


def flag_from_dict(document: dict) -> SegmentationFlag:
    _require(document, "flag", "code")
    return SegmentationFlag(code=document["code"],
                            detail=document.get("detail", ""),
                            span=span_from_dict(document.get("span")))


def finding_to_dict(finding: ScrubFinding) -> dict:
    return {"kind": finding.kind, "replacement": finding.replacement,
            "span_start": finding.span_start, "span_end": finding.span_end,
            "detail": finding.detail}


def finding_from_dict(document: dict) -> ScrubFinding:
    _require(document, "scrub finding", "kind", "replacement")
    return ScrubFinding(
        kind=document["kind"],
        replacement=document["replacement"],
        span_start=int(document.get("span_start", 0)),
        span_end=int(document.get("span_end", 0)),
        detail=document.get("detail", ""),
    )


# --- Assignment context -----------------------------------------------------
# Reps are stored because a submission on its own cannot be re-scored: the
# checker needs the prompt and the scaffolds it was written against. Keeping
# them means a scorer fix can be replayed over past work instead of only
# applying going forward.


def rep_to_dict(context: AssignmentContext) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "rep_id": context.rep_id,
        "date": context.date.isoformat(),
        "tier": context.tier,
        "prompt_text": context.prompt_text,
        "criteria_set_id": context.criteria_set_id,
        "scaffold_blocks": [
            {"block_id": b.block_id, "template": b.template, "kind": b.kind}
            for b in context.scaffold_blocks
        ],
        "source_texts": list(context.source_texts),
        "word_cap": context.word_cap,
        "section_id": context.section_id,
    }


def rep_from_dict(document: dict) -> AssignmentContext:
    _require(document, "rep", "rep_id", "date", "tier", "prompt_text",
             "criteria_set_id")
    return AssignmentContext(
        rep_id=document["rep_id"],
        date=_parse_date(document["date"]),
        tier=int(document["tier"]),
        prompt_text=document["prompt_text"],
        criteria_set_id=document["criteria_set_id"],
        scaffold_blocks=[
            ScaffoldBlock(block_id=b["block_id"], template=b["template"],
                          kind=b.get("kind", "stem"))
            for b in document.get("scaffold_blocks", [])
        ],
        source_texts=list(document.get("source_texts", [])),
        word_cap=document.get("word_cap"),
        section_id=document.get("section_id"),
    )


# --- Submission -------------------------------------------------------------


def submission_to_dict(submission: Submission, *, canvas_id: str) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "submission_id": submission.submission_id,
        "rep_id": submission.rep_id,
        "canvas_id": str(canvas_id),
        "submitted_at": _dt(submission.submitted_at),
        "raw_text": submission.raw_text,
        "student_word_count": submission.student_word_count,
        "segments": [segment_to_dict(s) for s in submission.segments],
        "flags": [flag_to_dict(f) for f in submission.flags],
        "scrub_findings": [finding_to_dict(f) for f in submission.scrub_findings],
    }


def submission_from_dict(document: dict, *, pseudonym_id: str) -> Submission:
    _require(document, "submission", "submission_id", "rep_id", "submitted_at")
    return Submission(
        submission_id=document["submission_id"],
        rep_id=document["rep_id"],
        pseudonym_id=pseudonym_id,
        submitted_at=_parse_dt(document["submitted_at"]),
        raw_text=document.get("raw_text", ""),
        segments=[segment_from_dict(s) for s in document.get("segments", [])],
        student_word_count=int(document.get("student_word_count", 0)),
        flags=[flag_from_dict(f) for f in document.get("flags", [])],
        scrub_findings=[finding_from_dict(f)
                        for f in document.get("scrub_findings", [])],
    )


# --- Score ------------------------------------------------------------------


def item_result_to_dict(result: ItemResult) -> dict:
    return {
        "item_id": result.item_id,
        "met": bool(result.met),
        "evidence_span": span_to_dict(result.evidence_span),
        "note": result.note,
        "needs_judgment": bool(result.needs_judgment),
    }


def item_result_from_dict(document: dict) -> ItemResult:
    _require(document, "item result", "item_id", "met")
    return ItemResult(
        item_id=document["item_id"],
        met=bool(document["met"]),
        evidence_span=span_from_dict(document.get("evidence_span")),
        note=document.get("note", ""),
        needs_judgment=bool(document.get("needs_judgment", False)),
    )


def score_to_dict(score: Score, *, canvas_id: str) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "submission_id": score.submission_id,
        "canvas_id": str(canvas_id),
        "criteria_set_id": score.criteria_set_id,
        "per_item": {item_id: item_result_to_dict(result)
                     for item_id, result in score.per_item.items()},
        "total": score.total,
        "possible": score.possible,
        "scored_at": _dt(score.scored_at),
        "scorer_version": score.scorer_version,
        "history_blind": True,
        "status": score.status,
    }


def score_from_dict(document: dict) -> Score:
    _require(document, "score", "submission_id", "criteria_set_id", "scored_at")
    if not document.get("history_blind", False):
        raise RecordSchemaError(
            f"stored score for {document['submission_id']} does not claim "
            "history_blind; it was not produced by core.scoring and must not "
            "be treated as a criterion-referenced result"
        )
    return Score(
        submission_id=document["submission_id"],
        criteria_set_id=document["criteria_set_id"],
        per_item={item_id: item_result_from_dict(raw)
                  for item_id, raw in document.get("per_item", {}).items()},
        total=int(document.get("total", 0)),
        possible=int(document.get("possible", 0)),
        scored_at=_parse_dt(document["scored_at"]),
        scorer_version=document.get("scorer_version", ""),
        status=document.get("status", "scored"),
    )


# --- Observation ------------------------------------------------------------


def observation_to_dict(observation: Observation, *, canvas_id: str) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "obs_id": observation.obs_id,
        "canvas_id": str(canvas_id),
        "submission_id": observation.submission_id,
        "observed_at": _dt(observation.observed_at),
        "criterion_id": observation.criterion_id,
        "pattern_tag": observation.pattern_tag,
        "claim_text": observation.claim_text,
        "evidence_span": observation.evidence_span,
        "source": observation.source,
    }


def observation_from_dict(document: dict, *, pseudonym_id: str) -> Observation:
    _require(document, "observation", "obs_id", "submission_id",
             "observed_at", "pattern_tag", "evidence_span")
    return Observation(
        obs_id=document["obs_id"],
        pseudonym_id=pseudonym_id,
        submission_id=document["submission_id"],
        observed_at=_parse_dt(document["observed_at"]),
        criterion_id=document.get("criterion_id"),
        pattern_tag=document["pattern_tag"],
        claim_text=document.get("claim_text", ""),
        evidence_span=document["evidence_span"],
        source=document.get("source", "machine"),
    )


# --- Directive --------------------------------------------------------------


def detector_to_dict(detector) -> dict:
    if isinstance(detector, BannedPhraseDetector):
        return {"kind": "banned_phrase", "phrases": list(detector.phrases)}
    if isinstance(detector, RequiredMoveDetector):
        return {"kind": "required_move", "pattern": detector.pattern,
                "description": detector.description}
    if isinstance(detector, JudgmentDetector):
        return {"kind": "judgment", "question": detector.question}
    raise RecordSchemaError(f"unknown detector {type(detector).__name__}")


def detector_from_dict(document: dict):
    kind = document.get("kind")
    if kind == "banned_phrase":
        return BannedPhraseDetector(phrases=list(document.get("phrases", [])))
    if kind == "required_move":
        return RequiredMoveDetector(pattern=document.get("pattern", ""),
                                    description=document.get("description", ""))
    if kind == "judgment":
        return JudgmentDetector(question=document.get("question", ""))
    raise RecordSchemaError(f"unknown detector kind {kind!r}")


def eval_to_dict(record: DirectiveEval) -> dict:
    return {
        "submission_id": record.submission_id,
        "evaluated_at": _dt(record.evaluated_at),
        "result": record.result,
        "evidence_span": record.evidence_span,
        "note": record.note,
    }


def eval_from_dict(document: dict) -> DirectiveEval:
    _require(document, "directive evaluation", "submission_id", "result")
    return DirectiveEval(
        submission_id=document["submission_id"],
        evaluated_at=_parse_dt(document.get("evaluated_at")),
        result=document["result"],
        evidence_span=document.get("evidence_span"),
        note=document.get("note", ""),
    )


def directive_to_dict(directive: Directive, *, canvas_id: str) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "directive_id": directive.directive_id,
        "canvas_id": str(canvas_id),
        "issued_at": _dt(directive.issued_at),
        "text": directive.text,
        "target_pattern": directive.target_pattern,
        "detector": detector_to_dict(directive.detector),
        "status": directive.status,
        "current_streak": directive.current_streak,
        "best_streak": directive.best_streak,
        "evaluations": [eval_to_dict(e) for e in directive.evaluations],
    }


def directive_from_dict(document: dict, *, pseudonym_id: str) -> Directive:
    _require(document, "directive", "directive_id", "text", "detector")
    return Directive(
        directive_id=document["directive_id"],
        pseudonym_id=pseudonym_id,
        issued_at=_parse_dt(document.get("issued_at")),
        text=document["text"],
        target_pattern=document.get("target_pattern", ""),
        detector=detector_from_dict(document["detector"]),
        status=document.get("status", "open"),
        current_streak=int(document.get("current_streak", 0)),
        best_streak=int(document.get("best_streak", 0)),
        evaluations=[eval_from_dict(e) for e in document.get("evaluations", [])],
    )


# --- Rolling profile --------------------------------------------------------


def pattern_to_dict(pattern: PatternSummary) -> dict:
    return {
        "pattern_tag": pattern.pattern_tag,
        "count": pattern.count,
        "rate": pattern.rate,
        "evidence": list(pattern.evidence),
        "first_seen": pattern.first_seen.isoformat(),
        "last_seen": pattern.last_seen.isoformat(),
    }


def pattern_from_dict(document: dict) -> PatternSummary:
    return PatternSummary(
        pattern_tag=document["pattern_tag"],
        count=int(document.get("count", 0)),
        rate=float(document.get("rate", 0.0)),
        evidence=list(document.get("evidence", [])),
        first_seen=_parse_date(document.get("first_seen")),
        last_seen=_parse_date(document.get("last_seen")),
    )


def ref_to_dict(ref: SubmissionRef | None) -> dict | None:
    if ref is None:
        return None
    return {"submission_id": ref.submission_id, "rep_id": ref.rep_id,
            "on": ref.on.isoformat(), "total": ref.total,
            "possible": ref.possible}


def ref_from_dict(document: dict | None) -> SubmissionRef | None:
    if not document:
        return None
    return SubmissionRef(
        submission_id=document["submission_id"],
        rep_id=document["rep_id"],
        on=_parse_date(document.get("on")),
        total=int(document.get("total", 0)),
        possible=int(document.get("possible", 0)),
    )


def profile_to_dict(profile: RollingProfile, *, canvas_id: str) -> dict:
    return {
        "schema": DOCUMENT_VERSION,
        "canvas_id": str(canvas_id),
        "generated_at": _dt(profile.generated_at),
        "window_start": profile.window_start.isoformat(),
        "window_end": profile.window_end.isoformat(),
        "tier": profile.tier,
        "per_criterion_rate": dict(profile.per_criterion_rate),
        "active_patterns": [pattern_to_dict(p) for p in profile.active_patterns],
        "open_directives": [directive_to_dict(d, canvas_id=canvas_id)
                            for d in profile.open_directives],
        "best_piece": ref_to_dict(profile.best_piece),
        "next_focus": profile.next_focus,
        "ready_for_tier_advance": bool(profile.ready_for_tier_advance),
    }


def profile_from_dict(document: dict, *, pseudonym_id: str) -> RollingProfile:
    """Rebuild a profile through the whitelist door.

    `build_profile` rather than the dataclass on purpose: a stored document
    that picked up an extra key (a hand edit, an older writer, a merge of two
    OneDrive copies) fails here with INV-5 named, instead of quietly becoming
    a profile field nobody chose.
    """
    _require(document, "profile", "generated_at", "window_start", "window_end")
    known = {
        "pseudonym_id": pseudonym_id,
        "generated_at": _parse_dt(document["generated_at"]),
        "window_start": _parse_date(document["window_start"]),
        "window_end": _parse_date(document["window_end"]),
        "tier": int(document.get("tier", 1)),
        "per_criterion_rate": {k: float(v) for k, v in
                               document.get("per_criterion_rate", {}).items()},
        "active_patterns": [pattern_from_dict(p)
                            for p in document.get("active_patterns", [])],
        "open_directives": [directive_from_dict(d, pseudonym_id=pseudonym_id)
                            for d in document.get("open_directives", [])],
        "best_piece": ref_from_dict(document.get("best_piece")),
        "next_focus": document.get("next_focus", ""),
        "ready_for_tier_advance": bool(document.get("ready_for_tier_advance")),
    }
    reserved = {"schema", "canvas_id"}
    extra = sorted(set(document) - reserved - {
        "generated_at", "window_start", "window_end", "tier",
        "per_criterion_rate", "active_patterns", "open_directives",
        "best_piece", "next_focus", "ready_for_tier_advance",
    })
    if extra:
        from api.dailywriting.core.models import ProfileFieldError
        raise ProfileFieldError(
            f"stored profile carries unexpected field(s) {extra}; a rolling "
            "profile holds writing facts only (INV-5)"
        )
    return build_profile(**known)
