"""Staged validation report for front-ends.

Additive, read-only wrapper over the existing validation rules. The core
validator (`QuizValidator`) and the CLI are untouched.

Unlike `QuizValidator.validate` (which short-circuits on the first hard failure),
this runs every validation stage independently so a UI can show the outcome of
*each* stage even when an earlier one failed. Returns plain dicts/lists
(JSON-friendly) so it crosses the Pyodide boundary cleanly.

Stages produced here are the validation middle of the pipeline. The parse stage
(JSON Structure) and the packaging stage (Build Files) are owned by the caller,
since they need the raw spec text and file I/O respectively.
"""

from __future__ import annotations

import copy
from typing import Dict, List

from ..core.quiz import Quiz
from .rules import structure_rules, fairness_rules, rationale_rules
from .fixers import auto_fixer


def _stage(stage_id: str, label: str, status: str, messages: List[str]) -> Dict:
    return {"id": stage_id, "label": label, "status": status, "messages": messages}


def build_validation_stages(quiz: Quiz) -> List[Dict]:
    """Run each validation stage independently and return per-stage results.

    Operates on deep copies — never mutates the caller's quiz — and writes no
    files. Every stage is attempted regardless of earlier failures.

    Returns a list of stage dicts: {id, label, status, messages}.
    """
    quiz = copy.deepcopy(quiz)
    stages: List[Dict] = []

    # Stage — Question Fields (per-question structural validity)
    try:
        structure_errors = structure_rules.validate_structure(copy.deepcopy(quiz))
    except Exception as e:  # never let a rule bug abort the whole report
        structure_errors = [f"Validation crashed: {e}"]
    stages.append(_stage(
        "question_fields", "Question Fields",
        "fail" if structure_errors else "pass", structure_errors,
    ))

    # Stage — Points & Balance (auto-fixers). Produces the fixed quiz the
    # length check should run against (balancing affects which choice is longest).
    fixed = copy.deepcopy(quiz)
    fix_error = None
    autofix_msgs: List[str] = []
    try:
        fixed, autofix_msgs = auto_fixer.AutoFixer().fix_all(fixed)
    except Exception as e:
        fix_error = str(e)
    stages.append(_stage(
        "points_balance", "Points & Balance",
        "fail" if fix_error else "pass",
        [fix_error] if fix_error else autofix_msgs,
    ))

    # Stage — Answer Lengths (length-bias). Best-effort even if earlier stages
    # failed; run against the fixed quiz when available.
    target = quiz if fix_error else fixed
    try:
        length_errors = fairness_rules.check_length_bias(target)
    except Exception as e:
        length_errors = [f"Length check crashed: {e}"]
    stages.append(_stage(
        "answer_lengths", "Answer Lengths",
        "fail" if length_errors else "pass", length_errors,
    ))

    # Stage — Rationales (per-choice coverage for MC/MA; the engine can't author these).
    try:
        rationale_errors = rationale_rules.check_rationale_coverage(quiz)
    except Exception as e:
        rationale_errors = [f"Rationale check crashed: {e}"]
    stages.append(_stage(
        "rationales", "Rationales",
        "fail" if rationale_errors else "pass", rationale_errors,
    ))

    return stages
