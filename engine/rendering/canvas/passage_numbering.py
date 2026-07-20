"""Passage type detection and numbering helpers for Canvas HTML rendering."""

from __future__ import annotations

from typing import List, Tuple


def add_passage_numbering(text: str, passage_type: str = "auto") -> Tuple[str, str]:
    if passage_type == "none":
        return text, "none"

    lines = text.split("\n")

    if passage_type == "auto":
        detected_type, confidence = _analyze_passage_content(text, lines)
        passage_type = detected_type if round(confidence, 2) > 0.6 else "prose"

    if passage_type == "poetry":
        numbered: list[str] = []
        non_empty_index = 0
        for line in lines:
            if line.strip():
                non_empty_index += 1
                marker = f"{{LINENUM:{non_empty_index:2}}}     " if (non_empty_index == 1 or non_empty_index % 5 == 0) else "               "
                numbered.append(f"{marker}{line}")
            else:
                numbered.append("")
        return "\n".join(numbered), "poetry"

    if passage_type in ("prose_short", "prose_long", "prose"):
        paragraphs = text.split("\n\n")
        numbered = []
        for index, paragraph in enumerate(paragraphs, 1):
            if paragraph.strip():
                numbered.append(f"{{PARANUM:{index}}}     {paragraph}")
            else:
                numbered.append("")
        return "\n\n".join(numbered), "prose"

    return text, "unknown"


def _analyze_passage_content(text: str, lines: List[str]) -> Tuple[str, float]:
    """Analyze passage content to determine type with confidence score."""
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        return "unknown", 0.0

    total_lines = len(non_empty_lines)
    avg_line_len = sum(len(line) for line in non_empty_lines) / total_lines
    paragraph_breaks = text.count("\n\n")

    poetry_score = 0.0
    prose_score = 0.0

    if avg_line_len < 60:
        poetry_score += 0.3
    else:
        prose_score += 0.2

    if total_lines < 3:
        return "prose_short", 0.8
    elif total_lines > 10:
        prose_score += 0.2

    if paragraph_breaks >= 3:
        prose_score += 0.4
    elif paragraph_breaks == 0:
        poetry_score += 0.2

    sentence_endings = text.count(".") + text.count("!") + text.count("?")
    sentences_per_line = sentence_endings / max(total_lines, 1)

    if sentences_per_line < 0.5:
        poetry_score += 0.3
    else:
        prose_score += 0.2

    if total_lines >= 3:
        line_lengths = [len(line) for line in non_empty_lines]
        avg_len = sum(line_lengths) / len(line_lengths)
        variance = sum((length - avg_len) ** 2 for length in line_lengths) / len(line_lengths)
        std_dev = variance**0.5
        consistency_ratio = std_dev / max(avg_len, 1)

        if consistency_ratio < 0.3:
            poetry_score += 0.4
        elif consistency_ratio > 0.7:
            prose_score += 0.2

    double_breaks = 0
    for i in range(len(lines) - 1):
        if lines[i].strip() == "" and lines[i + 1].strip() == "":
            double_breaks += 1

    if double_breaks > 0:
        poetry_score += min(double_breaks * 0.2, 0.4)

    capitalized_starts = sum(1 for line in non_empty_lines if line.strip() and line.strip()[0].isupper())
    cap_ratio = capitalized_starts / total_lines

    if cap_ratio > 0.8:
        poetry_score += 0.2
    elif cap_ratio < 0.3:
        prose_score += 0.1

    total_score = poetry_score + prose_score
    if total_score == 0:
        return "prose_short", 0.5

    poetry_confidence = poetry_score / total_score
    prose_confidence = prose_score / total_score

    if poetry_confidence > prose_confidence:
        final_type = "poetry"
        confidence = poetry_confidence
    else:
        final_type = "prose"
        confidence = prose_confidence

    return final_type, min(confidence, 0.95)
