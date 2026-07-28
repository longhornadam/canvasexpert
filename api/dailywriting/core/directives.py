"""Directives and uptake detection.

A directive is a specific, checkable instruction to one student. The system
then watches for compliance across subsequent reps and says so out loud when
it happens, which is the whole point: a student who is told the same thing
every week and never told they fixed it learns that feedback is weather.

Deterministic detectors are preferred. They are cheap, they are reliable, and
they can be shown to a teacher before activation, so a directive written in
prose gets compiled and the compilation gets confirmed rather than guessed at.
A judgment detector is the fallback and, in this substrate, it returns `na`
rather than a verdict: fabricating a met would produce praise the system
cannot prove, and unprovable praise is worse than silence.

Streak rules that matter more than they look:

  - A missing submission is `na`. Absence is not backsliding, and a student
    who was out sick on Thursday has not broken anything.
  - A submission at a tier where the directive does not apply is `na` too.
  - Praise fires once, at `PRAISE_THRESHOLD` consecutive met, citing the count
    it can actually back.
  - A directive retires at `RETIRE_THRESHOLD`. The file should not nag forever,
    and INV-4 says a pattern has to keep re-earning its place.

Uptake never changes a score (INV-1). It changes what the student is told.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from api.dailywriting.config import thresholds
from api.dailywriting.core.models import (
    BannedPhraseDetector,
    Directive,
    DirectiveEval,
    DetectorSpec,
    EvalResult,
    JudgmentDetector,
    RequiredMoveDetector,
    Submission,
    utc_now,
)

# Statuses that still get evaluated against new work. "met" marks a directive
# that has cleared the praise threshold but has not yet earned retirement.
ACTIVE_STATUSES = ("open", "met", "lapsed")

# Acknowledgment priority, highest value first. Uptake gets the slot over a
# lapse because the corrective already has its own slot in the feedback
# message ("one thing to work on"), and this one is the scarce one.
_ACK_PRIORITY = {"praise": 0, "return": 1, "lapse": 2}

# Nested quantifiers in a teacher-authored regex are the classic path to a
# pathological match. Rejected rather than run.
_CATASTROPHIC = re.compile(r"\([^)]*[+*]\)[+*]")

_MAX_PATTERN_LEN = 200

_QUOTED = re.compile(r"[\"“']([^\"”']{3,80})[\"”']")

# American punctuation puts the period inside the quotation marks, so a teacher
# writing `stop opening with "this shows that."` yields a phrase with a trailing
# period that would never match mid-sentence prose. Strip it.
_TRAILING_PUNCT = ".,;:!? \t"


def _extract_phrases(prose: str) -> list[str]:
    phrases = []
    for raw in _QUOTED.findall(prose or ""):
        phrase = raw.strip().rstrip(_TRAILING_PUNCT).strip()
        if len(phrase) >= 3:
            phrases.append(phrase)
    return phrases


class DetectorError(ValueError):
    """A detector spec cannot be compiled or is unsafe to run."""


@dataclass(frozen=True)
class Acknowledgment:
    """Something provable to say to the student about their own follow-through."""

    kind: Literal["praise", "lapse", "return"]
    directive_id: str
    text: str
    streak: int


@dataclass(frozen=True)
class CompiledDirective:
    """What a prose directive compiled to, and how to describe that to a teacher.

    `explanation` exists so the teacher confirms the compilation before the
    directive goes live. A detector that checks something subtly different from
    what the teacher meant will generate confident, wrong praise.
    """

    detector: DetectorSpec
    explanation: str
    deterministic: bool


def _student_text(submission: Submission) -> str:
    """Student prose only. A banned phrase inside a provided stem is not the
    student's doing, and a directive must not punish them for it."""
    return " ".join(s.text.strip() for s in submission.segments
                    if s.origin == "student" and s.text.strip())


def _normalize(text: str) -> str:
    lowered = (text or "").lower()
    lowered = lowered.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", lowered).strip()


def _sentence_around(text: str, needle: str) -> str:
    """The sentence containing `needle`, for use as the cited evidence span."""
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        if _normalize(needle) in _normalize(sentence):
            return sentence.strip()
    return (text or "").strip()[:160]


def compile_pattern(pattern: str) -> re.Pattern:
    """Compile a required-move pattern, refusing unsafe input."""
    if not pattern or len(pattern) > _MAX_PATTERN_LEN:
        raise DetectorError(
            f"pattern must be 1-{_MAX_PATTERN_LEN} characters")
    if _CATASTROPHIC.search(pattern):
        raise DetectorError(
            "pattern contains a nested quantifier, which can hang on ordinary "
            "student writing; rewrite it without a repeated group"
        )
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise DetectorError(f"pattern is not a valid regex: {exc}") from exc


def compile_directive(prose: str) -> CompiledDirective:
    """Attempt to turn a teacher's prose directive into a deterministic check.

    Falls back to a judgment detector, and says so, so the teacher can decide
    whether to rewrite the directive into something checkable instead.
    """
    quoted = _extract_phrases(prose)
    lowered = _normalize(prose)

    stop_words = ("stop", "don't", "dont", "do not", "quit", "avoid",
                  "cut", "no more", "without")
    if quoted and any(word in lowered for word in stop_words):
        phrases = list(quoted)
        return CompiledDirective(
            detector=BannedPhraseDetector(phrases=phrases),
            explanation=("Checks that none of these appear in the student's "
                         "own words: " + ", ".join(f'"{p}"' for p in phrases)
                         + ". A match inside a provided stem does not count."),
            deterministic=True,
        )
    if quoted:
        phrases = list(quoted)
        pattern = "|".join(re.escape(p) for p in phrases)
        return CompiledDirective(
            detector=RequiredMoveDetector(
                pattern=pattern,
                description="uses " + " or ".join(f'"{p}"' for p in phrases)),
            explanation=("Checks that the student's own words include "
                         + " or ".join(f'"{p}"' for p in phrases) + "."),
            deterministic=True,
        )
    if "line number" in lowered or "cite the line" in lowered:
        return CompiledDirective(
            detector=RequiredMoveDetector(
                pattern=r"\bline\s+\d+",
                description="cites a line number"),
            explanation="Checks that the student's own words cite a line "
                        "number, as in \"line 14\".",
            deterministic=True,
        )
    return CompiledDirective(
        detector=JudgmentDetector(question=prose.strip()),
        explanation=("No deterministic check could be built from this wording, "
                     "so it needs a model read. Rewriting it around an exact "
                     "phrase or a countable move would make it checkable, and "
                     "checkable directives are the ones that can be praised."),
        deterministic=False,
    )


def run_detector(detector: DetectorSpec,
                 submission: Submission) -> tuple[EvalResult, str | None, str]:
    """Evaluate one detector against one submission's student prose.

    Returns (result, evidence_span, note). The span is what the verdict was
    based on: a met with nothing to point at is not reportable.
    """
    text = _student_text(submission)

    if isinstance(detector, BannedPhraseDetector):
        normalized = _normalize(text)
        for phrase in detector.phrases:
            if _normalize(phrase) and _normalize(phrase) in normalized:
                return ("unmet", _sentence_around(text, phrase),
                        f'used the banned phrase "{phrase}"')
        return ("met", None,
                "none of the banned phrases appear in the student's own words")

    if isinstance(detector, RequiredMoveDetector):
        try:
            pattern = compile_pattern(detector.pattern)
        except DetectorError as exc:
            return "na", None, f"detector could not run: {exc}"
        match = pattern.search(text)
        if match:
            return ("met", _sentence_around(text, match.group()),
                    f"found the required move ({detector.description or detector.pattern})")
        return ("unmet", None,
                f"required move not found ({detector.description or detector.pattern})")

    if isinstance(detector, JudgmentDetector):
        # Deliberately unresolved in the substrate. See the module docstring:
        # an invented verdict here becomes unprovable praise downstream.
        return ("na", None,
                "needs a model read; not evaluated by the substrate, so this "
                "rep neither builds nor breaks the streak")

    raise DetectorError(f"unknown detector type {type(detector).__name__}")


def _ack_for(directive: Directive, kind: str, streak: int) -> Acknowledgment:
    """Build a provable acknowledgment.

    The directive is quoted exactly as the student was given it, so it is
    recognisable, and the count is the one the detector actually confirmed.
    """
    banned = isinstance(directive.detector, BannedPhraseDetector)
    quoted = f'"{directive.text}"'
    pieces = "piece" if streak == 1 else "pieces"

    if kind == "praise":
        if banned:
            body = (f"I asked you this: {quoted} You have gone {streak} "
                    f"{pieces} in a row without it. Keep going.")
        else:
            body = (f"I asked you this: {quoted} You have done it {streak} "
                    f"{pieces} in a row now. Keep going.")
    elif kind == "lapse":
        if banned:
            body = (f"You had gone {streak} {pieces} without it, and it is "
                    f"back in today's. I asked you this: {quoted} Cut it and "
                    "say the thing directly.")
        else:
            body = (f"You had done it {streak} {pieces} in a row, and today's "
                    f"does not. I asked you this: {quoted}")
    else:
        body = (f"Back on it. I asked you this: {quoted} Today's piece does it "
                "again after a slip.")
    return Acknowledgment(kind=kind, directive_id=directive.directive_id,
                          text=body, streak=streak)


def evaluate(
    directive: Directive,
    submission: Submission | None,
    *,
    applies: bool = True,
    now: datetime | None = None,
    rep_id: str | None = None,
) -> tuple[Directive, DirectiveEval, Acknowledgment | None]:
    """Evaluate one directive against one rep.

    Pass `submission=None` for a rep the student did not turn in, or
    `applies=False` for a rep at a tier where the directive is not in play.
    Both record `na` and leave the streak alone.
    """
    stamped = now or utc_now()

    if submission is None or not applies:
        reason = ("no submission for this rep" if submission is None
                  else "directive does not apply at this rep's tier")
        record = DirectiveEval(
            submission_id=(submission.submission_id if submission
                           else f"missing:{rep_id or 'unknown'}"),
            evaluated_at=stamped,
            result="na",
            evidence_span=None,
            note=reason + "; streak unchanged",
        )
        return (replace(directive,
                        evaluations=list(directive.evaluations) + [record]),
                record, None)

    result, span, note = run_detector(directive.detector, submission)
    record = DirectiveEval(
        submission_id=submission.submission_id,
        evaluated_at=stamped,
        result=result,
        evidence_span=span,
        note=note,
    )

    current = directive.current_streak
    best = directive.best_streak
    status = directive.status
    ack: Acknowledgment | None = None

    if result == "met":
        was_lapsed = status == "lapsed"
        current += 1
        best = max(best, current)
        if was_lapsed:
            status = "open"
            ack = _ack_for(directive, "return", current)
        if current == thresholds.PRAISE_THRESHOLD:
            status = "met"
            ack = _ack_for(directive, "praise", current)
        if current >= thresholds.RETIRE_THRESHOLD:
            status = "retired"
            ack = ack if ack else None
    elif result == "unmet":
        # Only lapse a directive that had earned a streak, and only announce it
        # once: a second lapse message for a directive already marked lapsed is
        # nagging, not information.
        lapsing = (best >= thresholds.LAPSE_MIN_BEST_STREAK
                   and status != "lapsed")
        if lapsing:
            ack = _ack_for(directive, "lapse", best)
            status = "lapsed"
        elif status == "met":
            status = "open"
        current = 0

    updated = replace(
        directive,
        status=status,
        current_streak=current,
        best_streak=best,
        evaluations=list(directive.evaluations) + [record],
    )
    return updated, record, ack


def evaluate_all(
    directives: list[Directive],
    submission: Submission | None,
    *,
    tier: int | None = None,
    directive_tiers: dict[str, int] | None = None,
    now: datetime | None = None,
    rep_id: str | None = None,
) -> tuple[list[Directive], list[Acknowledgment]]:
    """Evaluate every active directive for one student against one rep."""
    directive_tiers = directive_tiers or {}
    updated: list[Directive] = []
    acks: list[Acknowledgment] = []
    for directive in directives:
        if directive.status not in ACTIVE_STATUSES:
            updated.append(directive)
            continue
        required_tier = directive_tiers.get(directive.directive_id)
        applies = tier is None or required_tier is None or tier >= required_tier
        next_directive, _record, ack = evaluate(
            directive, submission, applies=applies, now=now, rep_id=rep_id)
        updated.append(next_directive)
        if ack:
            acks.append(ack)
    return updated, acks


def choose_acknowledgment(acks: list[Acknowledgment]) -> Acknowledgment | None:
    """One acknowledgment per feedback message, highest value first.

    Four stacked acknowledgments read as noise and teach nothing.
    """
    if not acks:
        return None
    return sorted(acks, key=lambda a: (_ACK_PRIORITY.get(a.kind, 9),
                                       -a.streak))[0]
