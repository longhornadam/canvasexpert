"""Records for the daily writing substrate.

Frozen dataclasses throughout. The rest of this repository prefers plain
dicts with explicit validators, and the persistence layer in `store/codec.py`
converts to exactly that shape on the way to disk. Inside this package the
types are load-bearing: INV-1 is a claim about a function signature, and
INV-5 is a claim about a field set, and neither is checkable against a dict.

Datetime policy: every datetime here is timezone-aware. `AssignmentContext.date`
and the profile window bounds are plain dates, meaning school days as the
teacher would name them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime, timezone
from typing import Literal

# --- Vocabulary -------------------------------------------------------------

Origin = Literal["assignment", "scaffold", "student", "quoted_source", "unknown"]

SegmentMethod = Literal[
    "exact_match", "fuzzy_match", "stem_align", "classifier", "residual"
]

EvalResult = Literal["met", "unmet", "na"]

DirectiveStatus = Literal["open", "met", "lapsed", "retired"]

# Controlled vocabulary for observations. Keep it small: aggregation across a
# section is only possible while two teachers would tag the same thing the
# same way.
PATTERN_TAGS = frozenset({
    "off_prompt",
    "restates_prompt",
    "thesis_not_arguable",
    "thesis_too_general",
    "thesis_multi_sentence",
    "argument_mismatched_to_thesis",
    "evidence_missing",
    "evidence_irrelevant",
    "evidence_dropped_in_unintegrated",
    "commentary_restates_evidence",
    "commentary_hedges",
    "commentary_formulaic",
    "exceeds_word_cap",
    "no_student_text",
})


class PatternTagError(ValueError):
    """An observation used a pattern tag outside the controlled vocabulary."""


class ProfileFieldError(ValueError):
    """A profile was built with a field outside the writing-only whitelist."""


class EvidenceRequiredError(ValueError):
    """An observation was built without a quoted span (INV-3)."""


def utc_now() -> datetime:
    """Timezone-aware now. One place, so tests can monkeypatch it."""
    return datetime.now(timezone.utc)


# --- Text geometry ----------------------------------------------------------


@dataclass(frozen=True)
class Span:
    """A character range in a submission's stored (already scrubbed) text."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Segment:
    """One stretch of a submission attributed to a single origin.

    `confidence` is 1.0 only for an exact match against text the authoring
    record already held. Anything below `thresholds.LOW_CONFIDENCE_SEGMENT`
    is reported to the teacher digest rather than trusted.
    """

    span_start: int
    span_end: int
    text: str
    origin: Origin
    confidence: float
    method: SegmentMethod


@dataclass(frozen=True)
class ScrubFinding:
    """A name or id the scrubber removed.

    `detail` never carries the removed value: a finding is written to the same
    private store as everything else, and a "we redacted Diego" note would
    reintroduce exactly what the redaction removed.
    """

    kind: Literal["roster_name", "roster_id", "general_name"]
    replacement: str
    span_start: int
    span_end: int
    detail: str = ""


@dataclass(frozen=True)
class SegmentationFlag:
    """Something a human should look at before trusting a segmentation."""

    code: Literal[
        "empty_stem_blank",
        "no_student_text",
        "low_confidence_segment",
        "cross_submission_repeat",
        "exceeds_word_cap",
        "unscrubbed_name_removed",
    ]
    detail: str
    span: Span | None = None


# --- Assignment side --------------------------------------------------------


@dataclass(frozen=True)
class CriterionItem:
    """One checklist line.

    `student_facing_text` is verbatim what students were shown, and feedback
    renders that string rather than paraphrasing it, so the checklist a
    student was taught is the checklist they are graded against.
    `check_id` names the deterministic check in `core.scoring`.
    """

    item_id: str
    label: str
    student_facing_text: str
    check_description: str
    check_id: str


@dataclass(frozen=True)
class CriteriaSet:
    """A published, versioned checklist for one tier.

    `published_at` is load-bearing: scoring refuses to measure work that
    predates the criteria it would be measured against.
    """

    criteria_set_id: str
    tier: int
    version: int
    items: list[CriterionItem]
    published_at: datetime
    spot_emphasis: str | None = None

    def item(self, item_id: str) -> CriterionItem | None:
        for candidate in self.items:
            if candidate.item_id == item_id:
                return candidate
        return None


@dataclass(frozen=True)
class ScaffoldBlock:
    """A stem, frame, instruction, or example handed to students.

    Blanks in `template` are marked with the literal token `{{BLANK}}`, which
    is what makes stem alignment possible rather than guesswork.
    """

    block_id: str
    template: str
    kind: Literal["stem", "frame", "instruction", "example"]


@dataclass(frozen=True)
class AssignmentContext:
    """Everything the checker may know about the task itself.

    Passed to the scorer as labeled provided text so a checker can tell
    whether a thesis actually answers the prompt. Carries no student handle.
    """

    rep_id: str
    date: date
    tier: int
    prompt_text: str
    criteria_set_id: str
    scaffold_blocks: list[ScaffoldBlock] = field(default_factory=list)
    source_texts: list[str] = field(default_factory=list)
    word_cap: int | None = None
    section_id: str | None = None


# --- Student side -----------------------------------------------------------


@dataclass(frozen=True)
class Submission:
    """One rep from one student.

    `raw_text` holds the text as stored, which is the SCRUBBED text. Text is
    scrubbed at ingest and the unscrubbed original is never persisted, so
    every span derived downstream is scrubbed by construction. That ordering
    is the whole of INV-7's defence: names appear inside student writing, and
    a scrub applied later has already been outrun by the spans quoted from it.

    `student_word_count` counts `student` segments only. A student who copies
    the prompt and adds four words has written four words.
    """

    submission_id: str
    rep_id: str
    pseudonym_id: str
    submitted_at: datetime
    raw_text: str
    segments: list[Segment]
    student_word_count: int
    flags: list[SegmentationFlag] = field(default_factory=list)
    scrub_findings: list[ScrubFinding] = field(default_factory=list)

    def segments_for_scoring(self) -> list[Segment]:
        """Student prose plus legitimately quoted source, in document order.

        Quoted source is scored (from tier 3 on, quoting the passage is the
        assignment) but does not count toward `student_word_count`.
        """
        return [s for s in self.segments
                if s.origin in ("student", "quoted_source")]


@dataclass(frozen=True)
class SubmissionRef:
    """A pointer to a submission, for the profile's best-piece reference."""

    submission_id: str
    rep_id: str
    on: date
    total: int
    possible: int


# --- Scoring side -----------------------------------------------------------


@dataclass(frozen=True)
class ItemResult:
    """One checklist line's outcome.

    `needs_judgment` marks a line no deterministic check can settle. The
    substrate reports those honestly rather than guessing: a scorer that
    silently rules on "is this arguable" would make the whole instrument
    unfalsifiable.
    """

    item_id: str
    met: bool
    evidence_span: Span | None
    note: str
    needs_judgment: bool = False


@dataclass(frozen=True)
class Score:
    """A criterion-referenced result.

    `history_blind` is a literal True rather than a computed field: it records
    the contract the producing function was written under, and a Score built
    by any path that saw a profile would be lying about its own type.
    """

    submission_id: str
    criteria_set_id: str
    per_item: dict[str, ItemResult]
    total: int
    possible: int
    scored_at: datetime
    scorer_version: str
    history_blind: Literal[True] = True
    status: Literal["scored", "no_student_text"] = "scored"


# --- Observations -----------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    """One dated noticing about one submission, with the span that earned it.

    Build these through `core.observations.make_observation`, which enforces
    the controlled vocabulary and the evidence requirement.
    """

    obs_id: str
    pseudonym_id: str
    submission_id: str
    observed_at: datetime
    criterion_id: str | None
    pattern_tag: str
    claim_text: str
    evidence_span: str
    source: Literal["machine", "teacher"]

    def __post_init__(self) -> None:
        if self.pattern_tag not in PATTERN_TAGS:
            raise PatternTagError(
                f"pattern_tag {self.pattern_tag!r} is outside the controlled "
                "vocabulary in models.PATTERN_TAGS"
            )
        if not (self.evidence_span or "").strip():
            raise EvidenceRequiredError(
                "an observation needs a quoted span from the submission "
                f"(pattern_tag={self.pattern_tag!r})"
            )


@dataclass(frozen=True)
class PatternSummary:
    """An in-window pattern with the evidence that keeps it alive.

    Re-derived on every regeneration. A pattern with no in-window evidence is
    absent, not zero: it stops steering feedback the moment it stops being
    true (INV-4).
    """

    pattern_tag: str
    count: int
    rate: float
    evidence: list[str]
    first_seen: date
    last_seen: date


# --- Directives -------------------------------------------------------------


@dataclass(frozen=True)
class BannedPhraseDetector:
    """Deterministic: met when none of the phrases appear in student prose."""

    phrases: list[str]
    kind: Literal["banned_phrase"] = "banned_phrase"


@dataclass(frozen=True)
class RequiredMoveDetector:
    """Deterministic: met when the pattern matches somewhere in student prose."""

    pattern: str
    description: str = ""
    kind: Literal["required_move"] = "required_move"


@dataclass(frozen=True)
class JudgmentDetector:
    """Model-judged, for directives no regex can settle.

    Must cite the span it judged. Unresolved in the substrate: see the stub in
    `core.directives`, which returns `na` rather than inventing a verdict,
    because a fabricated met would produce unprovable praise.
    """

    question: str
    kind: Literal["judgment"] = "judgment"


DetectorSpec = BannedPhraseDetector | RequiredMoveDetector | JudgmentDetector


@dataclass(frozen=True)
class DirectiveEval:
    """One directive checked against one submission."""

    submission_id: str
    evaluated_at: datetime
    result: EvalResult
    evidence_span: str | None
    note: str


@dataclass(frozen=True)
class Directive:
    """A specific, checkable instruction given to one student.

    `text` is stored exactly as the student was told it, so an acknowledgment
    can quote it back recognisably instead of paraphrasing the teacher.
    """

    directive_id: str
    pseudonym_id: str
    issued_at: datetime
    text: str
    target_pattern: str
    detector: DetectorSpec
    status: DirectiveStatus = "open"
    current_streak: int = 0
    best_streak: int = 0
    evaluations: list[DirectiveEval] = field(default_factory=list)


# --- Rolling profile --------------------------------------------------------

# INV-5. The profile may hold writing facts and nothing else. Enforced by
# `build_profile`, by an import-time check that the whitelist itself stays
# writing-only, and by a test that the dataclass and the whitelist agree.
PROFILE_FIELD_WHITELIST = frozenset({
    "pseudonym_id",
    "generated_at",
    "window_start",
    "window_end",
    "tier",
    "per_criterion_rate",
    "active_patterns",
    "open_directives",
    "best_piece",
    "next_focus",
    "ready_for_tier_advance",
})

# Substring probes, not an exhaustive list. The point is that a future field
# named `behavior_notes` or `home_situation` fails at import rather than in
# review.
_BANNED_PROFILE_TOPICS = (
    "behavior", "behaviour", "conduct", "discipline", "referral",
    "effort", "motivation", "attitude", "participation",
    "attendance", "absence", "absent", "tardy",
    "home", "family", "parent", "guardian", "household",
    "service", "iep", "504", "accommodation", "modification",
    "disability", "diagnosis", "medical", "health", "counselor",
    "ell", "lep", "gifted", "economic", "lunch",
)


@dataclass(frozen=True)
class RollingProfile:
    """Derived, replaceable working summary of one student's recent writing.

    Never the source of truth: regenerated from the immutable record over a
    bounded window (INV-4), writing-only (INV-5), and renderable to the
    student in full (INV-6).
    """

    pseudonym_id: str
    generated_at: datetime
    window_start: date
    window_end: date
    tier: int
    per_criterion_rate: dict[str, float]
    active_patterns: list[PatternSummary]
    open_directives: list[Directive]
    best_piece: SubmissionRef | None
    next_focus: str
    ready_for_tier_advance: bool


def build_profile(**profile_fields) -> RollingProfile:
    """Construct a profile, refusing any field outside the whitelist.

    The frozen dataclass already rejects an unknown keyword, but this is the
    documented door, and it fails with a message that names the invariant.
    """
    unknown = sorted(set(profile_fields) - PROFILE_FIELD_WHITELIST)
    if unknown:
        raise ProfileFieldError(
            f"field(s) {unknown} are not in the writing-only profile "
            "whitelist (INV-5). A rolling profile carries writing facts "
            "only: no behavior, effort, attendance, home situation, "
            "services, or disability information."
        )
    missing = sorted(PROFILE_FIELD_WHITELIST - set(profile_fields))
    if missing:
        raise ProfileFieldError(f"missing required profile field(s) {missing}")
    return RollingProfile(**profile_fields)


def _assert_whitelist_is_writing_only() -> None:
    """Import-time guard: no whitelisted field names a non-writing topic."""
    for key in sorted(PROFILE_FIELD_WHITELIST):
        lowered = key.lower()
        for banned in _BANNED_PROFILE_TOPICS:
            if banned in lowered:
                raise ProfileFieldError(
                    f"profile field {key!r} touches {banned!r}, which INV-5 "
                    "keeps out of the profile"
                )
    declared = {f.name for f in fields(RollingProfile)}
    if declared != set(PROFILE_FIELD_WHITELIST):
        raise ProfileFieldError(
            "RollingProfile fields and PROFILE_FIELD_WHITELIST disagree: "
            f"only in dataclass {sorted(declared - set(PROFILE_FIELD_WHITELIST))}, "
            f"only in whitelist {sorted(set(PROFILE_FIELD_WHITELIST) - declared)}"
        )


_assert_whitelist_is_writing_only()
