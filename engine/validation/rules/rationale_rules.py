"""Rationale coverage rules (hard fail).

Pedagogical requirement: every scorable item must ship a rationale so students
learn from mistakes. The engine can reshape formatting but cannot author the
explanations, so missing coverage is a hard failure the author must fix.

Coverage by type:
- MC / MA: per-choice rationales — the correct answer AND every distractor.
- TF / FITB / MATCHING / ORDERING / NUMERICAL / CATEGORIZATION: a single rationale.
- ESSAY / FILEUPLOAD: a single "what a strong response looks like" explanation.
- STIMULUS / STIMULUS_END: none (structural markers).
"""

from typing import Dict, List

from ...core.quiz import Quiz
from ...core.questions import (
    MCQuestion,
    MAQuestion,
    EssayQuestion,
    FileUploadQuestion,
    StimulusItem,
    StimulusEnd,
)


def check_rationale_coverage(quiz: Quiz) -> List[str]:
    """Return errors for scorable items lacking a usable rationale."""
    errors: List[str] = []

    rationale_by_item: Dict[str, dict] = {
        r.get("item_id"): r
        for r in (getattr(quiz, "rationales", None) or [])
        if isinstance(r, dict) and r.get("item_id")
    }

    for idx, q in enumerate(quiz.questions, 1):
        if isinstance(q, (StimulusItem, StimulusEnd)):
            continue

        qid = getattr(q, "forced_ident", None)
        label = f"Question #{idx}" + (f" ('{qid}')" if qid else "")

        if not qid:
            errors.append(
                f"{label}: this {q.qtype} item needs a unique \"id\" so its "
                f"rationale can be matched to it."
            )
            continue

        entry = rationale_by_item.get(qid)

        if isinstance(q, (MCQuestion, MAQuestion)):
            errors.extend(_check_per_choice(q, entry, label))
        else:
            errors.extend(_check_single(q, entry, label))

    return errors


def _check_per_choice(q, entry, label) -> List[str]:
    n_choices = len(getattr(q, "choices", []) or [])
    if not entry or not entry.get("choices"):
        return [
            f"{label}: no per-choice rationales. Add a rationales entry with a "
            f"\"choices\" array explaining the correct answer and every distractor "
            f"(why each one is wrong)."
        ]
    rchoices = entry.get("choices", []) or []
    if len(rchoices) != n_choices:
        return [
            f"{label}: has {n_choices} answer choices but {len(rchoices)} "
            f"rationale(s). Every choice needs its own explanation."
        ]
    empty = [i + 1 for i, rc in enumerate(rchoices)
             if not str((rc or {}).get("rationale", "")).strip()]
    if empty:
        return [
            f"{label}: rationale text is empty for choice(s) "
            f"{', '.join(map(str, empty))}. Each choice needs a specific explanation."
        ]
    return []


def _check_single(q, entry, label) -> List[str]:
    is_open = isinstance(q, (EssayQuestion, FileUploadQuestion))
    if not entry or not str(entry.get("rationale", "")).strip():
        if is_open:
            return [
                f"{label}: needs a short explanation of what a strong response "
                f"looks like (1-3 sentences) in its \"rationale\" field."
            ]
        return [
            f"{label}: needs a \"rationale\" explaining why the correct answer "
            f"is correct."
        ]
    return []
