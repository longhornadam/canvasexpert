"""Feedback assembly and ordering.

Scaffold only: the assembly, the ordering, the length discipline, and the
safety checks are real, and the places a model would write prose are marked
stubs. Production scoring and feedback prompts are out of scope for the
substrate.

Fixed order, and the order is the pedagogy:

  1. Checklist result, in the exact wording the student was shown. Not a
     paraphrase: the checklist they were taught is the checklist they are
     measured against, and a reworded criterion is a different criterion.
  2. Uptake acknowledgment, if one fired. Provable, or absent.
  3. One thing to work on. Exactly one.
  4. Optional exemplar pair, a strong response beside a near-miss on the same
     prompt, both anonymised, because a pair teaches what a single winner
     cannot.

Two hard constraints. Length: a 12-year-old reads about 120 words of feedback,
not 400, so the cap drops optional parts rather than truncating mid-sentence.
Names: no feedback message may contain any roster name or any other student's
pseudonym. The exemplar pair is where that would go wrong, and it is checked
rather than trusted.

Latency is a monitored property, not an aspiration. Feedback that arrives the
next morning is what makes the practice feel consequential; feedback that
arrives on Friday is a grade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from api.dailywriting.config import thresholds
from api.dailywriting.core.directives import Acknowledgment
from api.dailywriting.core.models import (
    CriteriaSet,
    Score,
    Submission,
    utc_now,
)

_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)*")


class PeerNameError(RuntimeError):
    """A feedback message would have named someone other than its recipient."""


class FeedbackLengthError(ValueError):
    """Required feedback alone exceeded the student-readable word cap."""


@dataclass(frozen=True)
class ExemplarPair:
    """Two anonymised responses to the same prompt, one strong, one near-miss."""

    rep_id: str
    strong_text: str
    near_miss_text: str
    what_separates_them: str


@dataclass(frozen=True)
class FeedbackMessage:
    submission_id: str
    pseudonym_id: str
    checklist_lines: list[str]
    one_thing: str
    generated_at: datetime
    acknowledgment: str | None = None
    exemplar: ExemplarPair | None = None
    latency_hours: float | None = None
    within_latency_target: bool = True
    dropped_for_length: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = ["Checklist:"]
        parts += [f"  {line}" for line in self.checklist_lines]
        if self.acknowledgment:
            parts += ["", self.acknowledgment]
        parts += ["", f"One thing to work on: {self.one_thing}"]
        if self.exemplar:
            parts += [
                "",
                "Two answers to the same prompt:",
                f"  Strong: {self.exemplar.strong_text}",
                f"  Close: {self.exemplar.near_miss_text}",
                f"  The difference: {self.exemplar.what_separates_them}",
            ]
        return "\n".join(parts)

    @property
    def word_count(self) -> int:
        return len(_WORD.findall(self.render()))


def word_count(text: str) -> int:
    return len(_WORD.findall(text or ""))


def assert_no_peer_names(text: str, *, forbidden: set[str]) -> None:
    """Refuse a message that names anyone but its recipient.

    `forbidden` should carry every roster real name, every nickname, and every
    other student's pseudonym. Comparison is word-bounded and case-insensitive,
    so a possessive still matches.
    """
    lowered = text or ""
    for name in forbidden:
        token = (name or "").strip()
        if not token:
            continue
        if re.search(rf"\b{re.escape(token)}\b", lowered, re.IGNORECASE):
            raise PeerNameError(
                "feedback would have named another student; the exemplar pair "
                "or an evidence span is carrying a name it should not"
            )


def checklist_lines(score: Score, criteria_set: CriteriaSet) -> list[str]:
    """One line per criterion, in the student's own published wording."""
    lines: list[str] = []
    for item in criteria_set.items:
        result = score.per_item.get(item.item_id)
        if result is None:
            continue
        if result.needs_judgment:
            mark = "?"
        else:
            mark = "yes" if result.met else "no"
        lines.append(f"[{mark}] {item.student_facing_text}")
    return lines


def draft_one_thing(next_focus: str, score: Score,
                    criteria_set: CriteriaSet) -> str:
    """The single thing to work on, in student-facing wording.

    Deterministic in the substrate. `MODEL_ONE_THING_PROMPT` marks where a
    model would later turn this into a sentence addressed to this piece of
    writing rather than to the criterion in general.
    """
    if next_focus.strip():
        return next_focus.strip()
    for item in criteria_set.items:
        result = score.per_item.get(item.item_id)
        if result and not result.met:
            return item.student_facing_text
    return "Keep doing what you did here."


# --- Model stubs ------------------------------------------------------------
# STUB. Production prompts are out of scope for the substrate. When these land,
# each must receive text and criteria only: no pseudonym, no profile, no
# record. Feedback may be shaped by history (INV-2), but it is shaped by the
# caller selecting `next_focus` and the acknowledgment, not by handing a model
# the student's file.

MODEL_ONE_THING_PROMPT = """\
STUB - not wired up.
Given: the student's own words, the criterion they missed in its published
student-facing wording, and the span the checker pointed at.
Produce: one sentence, addressed to this piece of writing, naming the fix.
Forbidden: any comparison to another student, any praise the detector did not
confirm, any mention of a pattern without the span that shows it.
"""

MODEL_EXEMPLAR_PROMPT = """\
STUB - not wired up.
Given: two anonymised responses to the same prompt, one strong and one near
miss, plus the criteria set.
Produce: one sentence naming what separates them.
Forbidden: naming or hinting at either author.
"""


def generate_one_thing(next_focus: str, evidence: str) -> str:
    raise NotImplementedError(
        "model-written feedback prose is a stub in the substrate; "
        "assemble_feedback uses the deterministic published criterion wording"
    )


# --- Assembly ---------------------------------------------------------------


def _trim_to_cap(message: FeedbackMessage,
                 cap: int) -> FeedbackMessage:
    """Drop optional parts, in reverse order of value, until under the cap.

    Never truncates mid-sentence: a half-finished piece of feedback reads as
    carelessness, and the checklist and the one thing are the parts that have
    to survive.
    """
    from dataclasses import replace as _replace

    dropped = list(message.dropped_for_length)
    current = message
    if current.word_count <= cap:
        return current
    if current.exemplar is not None:
        dropped.append("exemplar pair")
        current = _replace(current, exemplar=None, dropped_for_length=dropped)
    if current.word_count <= cap:
        return current
    if current.acknowledgment:
        dropped.append("uptake acknowledgment")
        current = _replace(current, acknowledgment=None,
                           dropped_for_length=dropped)
    if current.word_count > cap:
        raise FeedbackLengthError(
            f"required checklist and one focus are {current.word_count} words, "
            f"over the hard {cap}-word feedback cap"
        )
    return current


def assemble_feedback(
    submission: Submission,
    score: Score,
    criteria_set: CriteriaSet,
    *,
    next_focus: str = "",
    acknowledgment: Acknowledgment | None = None,
    exemplar: ExemplarPair | None = None,
    forbidden_names: set[str],
    now: datetime | None = None,
    word_cap: int | None = None,
) -> FeedbackMessage:
    """Build one student's feedback for one rep.

    `next_focus` and `acknowledgment` are where history enters (INV-2): the
    caller took them from the rolling profile and the directive evaluation.
    The score itself was produced without any of it.
    """
    stamped = now or utc_now()
    cap = thresholds.FEEDBACK_WORD_CAP if word_cap is None else word_cap

    latency = None
    if submission.submitted_at:
        latency = (stamped - submission.submitted_at).total_seconds() / 3600.0

    message = FeedbackMessage(
        submission_id=submission.submission_id,
        pseudonym_id=submission.pseudonym_id,
        checklist_lines=checklist_lines(score, criteria_set),
        one_thing=draft_one_thing(next_focus, score, criteria_set),
        acknowledgment=acknowledgment.text if acknowledgment else None,
        exemplar=exemplar,
        generated_at=stamped,
        latency_hours=None if latency is None else round(latency, 2),
        within_latency_target=(
            latency is None or latency <= thresholds.FEEDBACK_LATENCY_HOURS),
    )

    message = _trim_to_cap(message, cap)
    assert_no_peer_names(message.render(), forbidden=forbidden_names)
    return message


def build_exemplar_pair(
    rep_id: str,
    candidates: list[tuple[Submission, Score]],
    *,
    exclude_submission_id: str = "",
) -> ExemplarPair | None:
    """Pick a strong response and a near-miss on the same prompt.

    Both texts come from storage, which means both are already scrubbed. The
    caller still passes the roster to `assemble_feedback`, because a pseudonym
    is not a name the recipient should be reading either.
    """
    pool = [(s, sc) for s, sc in candidates
            if s.submission_id != exclude_submission_id
            and sc.status == "scored" and sc.possible]
    if len(pool) < 2:
        return None
    ranked = sorted(pool, key=lambda pair: (-pair[1].total,
                                            pair[0].submitted_at))
    strong_submission, strong_score = ranked[0]
    near_submission, near_score = None, None
    for submission, score in ranked[1:]:
        if score.total < strong_score.total:
            near_submission, near_score = submission, score
            break
    if near_submission is None:
        return None

    missed = [item_id for item_id, result in near_score.per_item.items()
              if not result.met and strong_score.per_item.get(item_id)
              and strong_score.per_item[item_id].met]
    difference = (", ".join(sorted(missed)) if missed
                  else "the stronger one commits to a position")
    return ExemplarPair(
        rep_id=rep_id,
        strong_text=strong_submission.raw_text.strip(),
        near_miss_text=near_submission.raw_text.strip(),
        what_separates_them=difference,
    )
