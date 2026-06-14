"""Answer balancer for Question model objects.

Shuffles choices for MC/MA/TF questions and balances distribution of correct
positions across the quiz.
"""
from __future__ import annotations

from typing import List, Optional
import random
from pathlib import Path

from engine.core.questions import MCQuestion, MAQuestion, TFQuestion, Question, MCChoice


def balance_answers(questions: List[Question], seed: Optional[int] = None) -> List[Question]:
    """Shuffle answers while balancing distributions for MC, MA, and TF.

    Args:
        questions: List of Question model objects to mutate
        seed: Optional random seed for deterministic behavior in tests

    Returns:
        The list of questions (mutated in-place)
    """
    if seed is not None:
        random.seed(seed)

    mc_questions = [q for q in questions if isinstance(q, MCQuestion)]
    ma_questions = [q for q in questions if isinstance(q, MAQuestion)]
    tf_questions = [q for q in questions if isinstance(q, TFQuestion)]

    if mc_questions:
        _balance_mc_questions(mc_questions)

    if ma_questions:
        _balance_ma_questions(ma_questions)

    if tf_questions:
        _balance_tf_questions(tf_questions)

    return questions


def _balance_mc_questions(mc_questions: List[MCQuestion]) -> None:
    if not mc_questions:
        return

    # Shuffle all choices first to break LLM's original answer bias
    # This must happen regardless of whether we can "balance" the distribution
    for q in mc_questions:
        random.shuffle(q.choices)

    # Determine number of positions (assume first question's number of choices)
    num_positions = len(mc_questions[0].choices)
    # Validate counts
    for q in mc_questions:
        if len(q.choices) != num_positions:
            # For simplicity, if varying lengths, skip balancing of this set
            # But they are already shuffled now!
            return

    num_questions = len(mc_questions)
    position_counts = [0] * num_positions

    random.shuffle(mc_questions)

    for q in mc_questions:
        # Determine current correct index
        current_correct = next((i for i, c in enumerate(q.choices) if c.correct), None)
        if current_correct is None:
            # malformed, skip
            continue

        min_count = min(position_counts)
        available_positions = [i for i, count in enumerate(position_counts) if count == min_count]
        target_position = random.choice(available_positions)

        _shuffle_mc_to_position(q, current_correct, target_position)

        position_counts[target_position] += 1

    # Second pass: avoid long streaks of the same correct position (e.g., D,D,D)
    correct_positions = [
        next((i for i, c in enumerate(q.choices) if c.correct), None) for q in mc_questions
    ]
    for idx in range(2, len(correct_positions)):
        a = correct_positions[idx]
        if a is None:
            continue
        if correct_positions[idx - 1] == a and correct_positions[idx - 2] == a:
            # Find earlier question with a different correct position to swap choices with
            swap_idx = next(
                (j for j in range(idx) if correct_positions[j] is not None and correct_positions[j] != a),
                None,
            )
            if swap_idx is not None:
                # Swap entire choices lists to preserve correctness flags
                mc_questions[idx].choices, mc_questions[swap_idx].choices = (
                    mc_questions[swap_idx].choices,
                    mc_questions[idx].choices,
                )
                correct_positions[idx], correct_positions[swap_idx] = (
                    correct_positions[swap_idx],
                    correct_positions[idx],
                )


def _shuffle_mc_to_position(question: MCQuestion, current_correct: int, target_position: int) -> None:
    """Move correct answer to target position.
    
    Assumes choices are already shuffled by caller.
    """
    choices = question.choices
    
    # If already at target, nothing to do
    if current_correct == target_position:
        return
    
    # Swap correct choice to target position
    choices[current_correct], choices[target_position] = choices[target_position], choices[current_correct]
    
    # Update correct flags
    for i, c in enumerate(choices):
        c.correct = (i == target_position)


def _balance_ma_questions(ma_questions: List[MAQuestion]) -> None:
    for q in ma_questions:
        choices = q.choices
        correct_choices = [c for c in choices if c.correct]
        incorrect_choices = [c for c in choices if not c.correct]

        # Shuffle both pools
        random.shuffle(correct_choices)
        random.shuffle(incorrect_choices)

        # Choose random target positions for correct choices
        total = len(choices)
        positions = list(range(total))
        random.shuffle(positions)
        correct_positions = positions[: len(correct_choices)]

        # Fill a new list with placeholders
        new_choices = [None] * total
        # Place correct choices
        for pos, choice in zip(sorted(correct_positions), correct_choices):
            new_choices[pos] = choice

        # Fill remaining positions with incorrect choices
        inc_iter = iter(incorrect_choices)
        for i in range(total):
            if new_choices[i] is None:
                new_choices[i] = next(inc_iter)

        q.choices = new_choices


def _balance_tf_questions(tf_questions: List[TFQuestion]) -> None:
    num_questions = len(tf_questions)
    target_true = num_questions // 2
    target_false = num_questions - target_true

    current_true = sum(1 for q in tf_questions if q.answer_true)
    current_false = num_questions - current_true

    need_to_flip_to_true = max(0, target_true - current_true)
    need_to_flip_to_false = max(0, target_false - current_false)

    random.shuffle(tf_questions)

    for q in tf_questions:
        if need_to_flip_to_true > 0 and not q.answer_true:
            q.answer_true = True
            need_to_flip_to_true -= 1
        elif need_to_flip_to_false > 0 and q.answer_true:
            q.answer_true = False
            need_to_flip_to_false -= 1


def log_distribution_stats(questions: List[Question], log_path: str) -> None:
    """Write distribution stats to a log file."""
    text = distribution_stats_text(questions)
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as log:
        log.write(text)


def distribution_stats_text(questions: List[Question]) -> str:
    """Return distribution stats as text (no file I/O)."""
    mc_questions = [q for q in questions if isinstance(q, MCQuestion)]
    ma_questions = [q for q in questions if isinstance(q, MAQuestion)]
    tf_questions = [q for q in questions if isinstance(q, TFQuestion)]

    lines = []
    lines.append('\n' + '=' * 60)
    lines.append('ANSWER DISTRIBUTION (AFTER BALANCING)')
    lines.append('=' * 60 + '\n')

    if mc_questions:
        lines.append('Multiple Choice Distribution:')
        position_counts = {}
        for q in mc_questions:
            idx = next((i for i, c in enumerate(q.choices) if c.correct), None)
            if idx is None:
                continue
            letter = chr(65 + idx)
            position_counts[letter] = position_counts.get(letter, 0) + 1

        for letter in sorted(position_counts.keys()):
            count = position_counts[letter]
            pct = (count / len(mc_questions)) * 100
            lines.append(f"  {letter}: {count} ({pct:.1f}%)")
        lines.append('')

    if tf_questions:
        lines.append('True/False Distribution:')
        true_count = sum(1 for q in tf_questions if q.answer_true)
        false_count = len(tf_questions) - true_count
        lines.append(f"  True: {true_count} ({true_count/len(tf_questions)*100:.1f}%)")
        lines.append(f"  False: {false_count} ({false_count/len(tf_questions)*100:.1f}%)")
        lines.append('')

    if ma_questions:
        lines.append(f"Multiple Answer Questions: {len(ma_questions)} (shuffled)")
        lines.append('')

    return '\n'.join(lines)
