"""Point allocation calculator for QuizForge.

Assigns point values to Quiz question model objects using a simple weight-based
distribution logic. Designed to keep point logic out of the LLM by applying
deterministic, easy-to-audit rules.
"""
from __future__ import annotations

from typing import List, Optional
from pathlib import Path

from engine.core.questions import Question, StimulusItem, StimulusEnd
from engine.rendering.physical.styles.default_styles import DEFAULT_QUIZ_POINTS

# Share weights by question type (default = 1.0)
SHARE_WEIGHTS = {
    "TF": 1,
    "MC": 1,
    "MA": 1,
    "FITB": 1,
    "NUMERICAL": 1,
    "CATEGORIZATION": 1,
    "MATCHING": 2,
    "ORDERING": 2,
    "ESSAY": 4,
    "FILEUPLOAD": 4,
}


def calculate_points(questions: List[Question], total_points: int = DEFAULT_QUIZ_POINTS, log_path: Optional[str] = None) -> List[Question]:
    """Assign point values to a list of Question model objects.

    Rules:
    - ESSAY and FILEUPLOAD types count as heavy and receive HEAVY_QUESTION_WEIGHT multiplier
    - Other supported types receive 1x weight
    - Rounding uses integer rounding and any rounding error is corrected on the first scorable question

    Args:
        questions: List of Question model objects (will be mutated in-place)
        total_points: Target total points (defaults to DEFAULT_QUIZ_POINTS)
        log_path: Optional path to a log file to append calculation details

    Returns:
        The list of question objects with their ``points`` attributes modified
    """
    # Work with scorable questions only (ignore StimulusItem/StimulusEnd)
    scorable = [q for q in questions if not isinstance(q, (StimulusItem, StimulusEnd))]

    if not scorable:
        return questions

    # Ignore pre-set points; always recalc to avoid LLM/user overrides leaking through
    explicit = []
    to_assign = scorable
    explicit_total = 0
    remaining_total = total_points

    # Calculate shares per question
    shares = []
    for q in to_assign:
        shares.append((q, SHARE_WEIGHTS.get(q.qtype, 1)))

    total_shares = sum(weight for _, weight in shares)
    if total_shares == 0:
        return questions

    value_per_share = remaining_total / total_shares

    # First pass: floor values, track remainders
    provisional = []
    for q, weight in shares:
        raw = weight * value_per_share
        floor_points = int(raw)
        remainder = raw - floor_points
        provisional.append((q, floor_points, remainder))

    assigned_total = sum(floor for _, floor, _ in provisional)
    remainder_points = int(round(remaining_total - assigned_total))

    # Distribute remainder points to the highest remainders (largest remainder method)
    provisional.sort(key=lambda tup: tup[2], reverse=True)
    for idx in range(len(provisional)):
        q, floor_points, _ = provisional[idx]
        bonus = 1 if remainder_points > 0 else 0
        q.points = floor_points + bonus
        q.points_set = True
        remainder_points -= bonus

    # If any remainder is still negative/positive due to rounding quirks, adjust the last question
    final_total = sum(int(q.points) for q, _, _ in provisional) + explicit_total
    drift = int(total_points - final_total)
    if drift != 0 and provisional:
        provisional[-1][0].points = int(provisional[-1][0].points) + drift

    # Optionally append a log
    if log_path:
        _write_log(questions, total_points, explicit_total, remaining_total, provisional, log_path)

    return questions


def _write_log(
    questions: List[Question],
    total_points: int,
    explicit_total: float,
    remaining_total: float,
    provisional: List,
    log_path: str,
) -> None:
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as log:
        log.write('\n' + '=' * 60 + '\n')
        log.write('POINT ALLOCATION\n')
        log.write('=' * 60 + '\n')
        log.write(f'Total points target: {total_points}\n')
        log.write(f'Explicit points: {explicit_total}\n')
        log.write(f'Remaining for auto-assign: {remaining_total}\n')
        if provisional:
            total_shares = sum(SHARE_WEIGHTS.get(q.qtype, 1) for q, _, _ in provisional)
            value_per_share = remaining_total / total_shares if total_shares else 0
            log.write(f'Total shares: {total_shares}\n')
            log.write(f'Value per share: {value_per_share:.4f}\n')
        log.write('\nQuestion breakdown:\n')
        for idx, q in enumerate(questions, start=1):
            log.write(f"  Q{idx} ({q.qtype}): {int(q.points)} pts\n")
        log.write(f"\nTotal assigned: {sum(int(q.points) for q in questions)}\n\n")
